"""Chạy bộ kiểm phân hũ tự động, báo cáo độ đúng, tỷ lệ phải hỏi, ma trận nhầm; hiệu chỉnh ngưỡng (F2, phase 4 luồng B).

    # THẬT (cần AWS): nhúng bằng Cohere Embed v3 và gọi model nhỏ qua Bedrock, có lưu đệm trong results/
    $env:AWS_REGION='ap-southeast-1'; $env:YOFINA_USAGE_TABLE='yofina-usage'
    uv run python evals/classification/run_eval.py warm            # gọi model nhỏ cho mọi giao dịch một lượt (lưu đệm; chậm: 18 lượt/phút)
    uv run python evals/classification/run_eval.py calibrate --write-config   # hiệu chỉnh trên nửa đầu, đo trên nửa sau, ghi classify_defaults.json
    uv run python evals/classification/run_eval.py run             # báo cáo với ngưỡng đang cấu hình

    # KHÔ (không cần AWS; embedding và model giả, KHÔNG phản ánh chất lượng thật, không ghi cấu hình)
    uv run python evals/classification/run_eval.py run --mode dry
    uv run python evals/classification/run_eval.py calibrate --mode dry

Mô phỏng và quyết định: xem `sim.py` (chạy đúng `Classifier` của Lambda). Tập hiệu chỉnh = nửa đầu theo thời gian của mỗi persona, tập kiểm = nửa sau
(người dùng mô phỏng sửa và trả lời nên nhãn và luật tích lũy qua cả hai nửa như sản phẩm thật). Kết quả ghi `results/classification-<mode>-<ngày>.json`.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import sim

from yofina_ledger import classify_config
from yofina_ledger.classify_seed import decode_vector, encode_vector

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
EMB_CACHE = RESULTS / "embedding_cache.json"
LLM_CACHE = RESULTS / "llm_cache.json"
DEFAULTS = Path(classify_config.__file__).with_name(classify_config.DEFAULTS_FILE)

#: mục tiêu của phase 4 (tiêu chí hoàn thành số 6) và mức đúng riêng mà ngưỡng tự gán phải đạt trên tập hiệu chỉnh
TARGET_ACCURACY = 0.90
TARGET_ASK_RATE = 0.10
AUTO_ACCURACY = 0.95


# --- đệm -----------------------------------------------------------------------------------------------------------------
def load_caches(mode: str) -> sim.Caches:
    c = sim.Caches()
    if mode == "live":
        if EMB_CACHE.exists():
            raw = json.loads(EMB_CACHE.read_text(encoding="utf-8"))
            c.embeddings = {k: decode_vector(v) for k, v in raw["vectors"].items()}
        if LLM_CACHE.exists():
            c.verdicts = json.loads(LLM_CACHE.read_text(encoding="utf-8"))["verdicts"]
    return c


def save_caches(c: sim.Caches, model: str) -> None:
    RESULTS.mkdir(exist_ok=True)
    EMB_CACHE.write_text(
        json.dumps(
            {
                "model": model,
                "vectors": {k: encode_vector(v) for k, v in sorted(c.embeddings.items())},
            }
        ),
        encoding="utf-8",
    )
    LLM_CACHE.write_text(
        json.dumps({"verdicts": dict(sorted(c.verdicts.items()))}, ensure_ascii=False, indent=0),
        encoding="utf-8",
    )


def build_backends(mode: str, caches: sim.Caches, rows: list[dict[str, Any]]):
    """(embedder, judge, tên model embedding). Chế độ thật nhúng gộp mọi chuỗi còn thiếu trước (vài lời gọi)."""
    if mode == "dry":
        import fakes

        live_emb, model = fakes.HashingEmbedder(), fakes.MODEL_ID
        texts = sim.prefetch_texts(rows)
        _, vecs = live_emb.embed_many(texts)
        caches.embeddings.update(dict(zip(texts, vecs, strict=True)))
        return (
            sim.CachedEmbedder(caches, model),
            sim.CachedJudge(caches, fakes.KeywordJudge()),
            model,
        )
    from yofina_classify.adapters import GatewayEmbedder, GatewayJudge

    from yofina_core.llm import LlmGateway

    gw = LlmGateway()
    live_emb = GatewayEmbedder(gw)
    missing = [t for t in sim.prefetch_texts(rows) if t not in caches.embeddings]
    model = "cohere.embed-multilingual-v3"
    if missing:
        model, vecs = live_emb.embed_many(missing)
        caches.embeddings.update(dict(zip(missing, vecs, strict=True)))
    return (
        sim.CachedEmbedder(caches, model, live_emb),
        sim.CachedJudge(caches, GatewayJudge(gw)),
        model,
    )


# --- hiệu chỉnh ------------------------------------------------------------------------------------------------------------
def fit_logistic(x: np.ndarray, y: np.ndarray, l2: float = 1e-3, iters: int = 50) -> np.ndarray:
    """Hồi quy logistic (Platt) bằng Newton. `x` (n, d) không gồm hệ số tự do; trả [intercept, w...]."""
    a = np.hstack([np.ones((len(x), 1)), x])
    w = np.zeros(a.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(a @ w, -30, 30)))
        g = a.T @ (p - y) + l2 * w
        h = (a.T * (p * (1 - p))) @ a + l2 * np.eye(len(w))
        step = np.linalg.solve(h, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def collect_features(
    results: list[sim.Result],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    kx, ky, lx, ly = [], [], [], []
    for r in results:
        for e in r.decision.evidence:
            if e.source == "embedding" and e.detail.startswith("knn") and len(e.features) == 2:
                kx.append(e.features)
                ky.append(1.0 if e.jar == r.row["truth_jar"] else 0.0)
                break  # chỉ ứng viên dẫn đầu của k-NN
        for e in r.decision.evidence:
            if e.source == "llm" and e.detail.startswith("model báo") and len(e.features) == 1:
                lx.append(e.features)
                ly.append(1.0 if e.jar == r.row["truth_jar"] else 0.0)
                break
    return np.array(kx), np.array(ky), np.array(lx), np.array(ly)


def with_params(
    th: classify_config.ClassifyThresholds, **kw: Any
) -> classify_config.ClassifyThresholds:
    return dataclasses.replace(th, **kw)


def choose_thresholds(
    rows: list[dict[str, Any]],
    th: classify_config.ClassifyThresholds,
    caches: sim.Caches,
    emb,
    judge,
) -> tuple[classify_config.ClassifyThresholds, list[dict[str, Any]]]:
    """Quét lưới (auto_min, review_min), đo trên tập hiệu chỉnh, chọn: review_min thấp nhất mà độ đúng của mục đã gán >= 90% và tỷ lệ hỏi
    nhỏ nhất; auto_min thấp nhất mà độ đúng của mục tự gán >= 95%."""
    grid: list[dict[str, Any]] = []
    review_grid = [round(x, 2) for x in np.arange(0.30, 0.91, 0.05)]
    auto_grid = [round(x, 2) for x in np.arange(0.70, 0.995, 0.03)] + [0.99]
    for rv in review_grid:
        for au in auto_grid:
            if au < rv:
                continue
            res = sim.run_sim(
                rows,
                with_params(th, review_min_confidence=rv, auto_min_confidence=au),
                caches,
                emb,
                judge,
            )
            m = sim.metrics([r for r in res if r.split == "calibration"])
            grid.append(
                {
                    "review_min": rv,
                    "auto_min": au,
                    **{
                        k: m[k]
                        for k in (
                            "accuracy_assigned",
                            "accuracy_auto",
                            "ask_rate",
                            "review_rate",
                            "auto",
                            "n",
                        )
                    },
                }
            )
    ok_review = [g for g in grid if (g["accuracy_assigned"] or 0) >= TARGET_ACCURACY]
    pool = ok_review or grid
    best_rv = min(
        pool, key=lambda g: (g["ask_rate"], -(g["accuracy_assigned"] or 0), g["review_min"])
    )["review_min"]
    cands = [g for g in grid if g["review_min"] == best_rv]
    ok_auto = [g for g in cands if (g["accuracy_auto"] or 0) >= AUTO_ACCURACY and g["auto"] > 0]
    best_au = (
        min(ok_auto, key=lambda g: g["auto_min"])["auto_min"]
        if ok_auto
        else max(g["auto_min"] for g in cands)
    )
    return with_params(
        th, review_min_confidence=best_rv, auto_min_confidence=max(best_au, best_rv)
    ), grid


def calibrate(
    rows, th, caches, emb, judge
) -> tuple[classify_config.ClassifyThresholds, dict[str, Any]]:
    # 1. số đo thô với auto_min = 1 (không bao giờ dừng ở bước embedding) để mọi giao dịch có cả bằng chứng k-NN lẫn của model
    ref = sim.run_sim(
        rows,
        with_params(th, auto_min_confidence=1.0, review_min_confidence=0.0),
        caches,
        emb,
        judge,
    )
    cal = [r for r in ref if r.split == "calibration"]
    kx, ky, lx, ly = collect_features(cal)
    fitted: dict[str, Any] = {"knn_examples": len(kx), "llm_examples": len(lx)}
    new = th
    if len(kx) >= 20 and 0 < ky.sum() < len(ky):
        w = fit_logistic(kx, ky)
        new = with_params(
            new,
            knn_cal_intercept=float(w[0]),
            knn_cal_w_sim=float(w[1]),
            knn_cal_w_margin=float(w[2]),
        )
        fitted["knn"] = {
            "intercept": float(w[0]),
            "w_sim": float(w[1]),
            "w_margin": float(w[2]),
            "base_rate": float(ky.mean()),
        }
    if len(lx) >= 20 and 0 < ly.sum() < len(ly):
        w = fit_logistic(lx, ly)
        new = with_params(new, llm_cal_intercept=float(w[0]), llm_cal_slope=float(w[1]))
        fitted["llm"] = {
            "intercept": float(w[0]),
            "slope": float(w[1]),
            "base_rate": float(ly.mean()),
        }
    # 2. quét ngưỡng với hệ số đã ước lượng
    chosen, grid = choose_thresholds(rows, new, caches, emb, judge)
    return chosen, {"fitted": fitted, "grid": grid}


# --- báo cáo ---------------------------------------------------------------------------------------------------------------
def report(rows, th, caches, emb, judge, mode: str, model: str) -> dict[str, Any]:
    res = sim.run_sim(rows, th, caches, emb, judge)
    cal = [r for r in res if r.split == "calibration"]
    test = [r for r in res if r.split == "test"]
    mt = sim.metrics(test)
    return {
        "mode": mode,
        "representative": mode == "live",
        "date": date.today().isoformat(),
        "embedding_model": model,
        "thresholds": dataclasses.asdict(th),
        "n_rows": len(rows),
        "all": sim.metrics(res),
        "calibration_split": sim.metrics(cal),
        "test_split": mt,
        "targets": {
            "accuracy_assigned": TARGET_ACCURACY,
            "ask_rate_below": TARGET_ASK_RATE,
            "test_meets_accuracy": (mt["accuracy_assigned"] or 0) >= TARGET_ACCURACY,
            "test_meets_ask_rate": (mt["ask_rate"] if mt["ask_rate"] is not None else 1)
            < TARGET_ASK_RATE,
        },
        "confusion_test": sim.confusion(test),
        "top_errors_test": sim.errors(test),
        "llm_calls_this_run": getattr(judge, "calls", 0),
    }


def write_config(
    th: classify_config.ClassifyThresholds, fitted: dict[str, Any], rep: dict[str, Any]
) -> None:
    """Ghi các số đã hiệu chỉnh vào classify_defaults.json (giữ nguyên `note`, `unit`; cập nhật `value`, `source`, `version`)."""
    raw = json.loads(DEFAULTS.read_text(encoding="utf-8"))
    stamp = f"hiệu chỉnh {rep['date']} trên evals/classification/dataset.jsonl (nửa đầu theo thời gian), embedding {rep['embedding_model']}; đo trên nửa sau: đúng {rep['test_split']['accuracy_assigned']}, hỏi {rep['test_split']['ask_rate']}"
    for name in (
        "auto_min_confidence",
        "review_min_confidence",
        "knn_cal_intercept",
        "knn_cal_w_sim",
        "knn_cal_w_margin",
        "llm_cal_intercept",
        "llm_cal_slope",
    ):
        raw["thresholds"][name]["value"] = round(float(getattr(th, name)), 4)
        raw["thresholds"][name]["source"] = stamp
    raw["version"] = f"{rep['date']}-hieu-chinh-bedrock"
    DEFAULTS.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("command", choices=["run", "warm", "calibrate"])
    ap.add_argument("--mode", choices=["live", "dry"], default="live")
    ap.add_argument(
        "--write-config",
        action="store_true",
        help="ghi ngưỡng đã hiệu chỉnh vào classify_defaults.json (chỉ chế độ live)",
    )
    ap.add_argument("--limit", type=int, help="chỉ lấy N dòng đầu mỗi persona (thử nhanh)")
    args = ap.parse_args()

    rows = sim.load_dataset()
    if args.limit:
        rows = [r for r in rows if r["seq"] < args.limit]
    th = classify_config.load_thresholds()
    caches = load_caches(args.mode)
    emb, judge, model = build_backends(args.mode, caches, rows)
    if args.mode == "live":
        save_caches(caches, model)

    if args.command == "warm":
        if args.mode != "live":
            print("warm chỉ có nghĩa ở chế độ live")
            return 2
        todo = [
            p for p in sim.warm_prompts(rows, th, emb) if sim.prompt_key(p) not in caches.verdicts
        ]
        print(f"{len(todo)} thông điệp chưa có đệm (tốc độ giới hạn theo vai small)")
        t0 = time.time()
        from yofina_classify.adapters import GatewayJudge  # noqa: F401

        for i, p in enumerate(todo, 1):
            jars = sim.persona_jars(
                "minh"
            )  # chỉ dùng để kiểm mã hũ; kiểm thật ở lần chạy sim (đệm lưu mã model trả)
            judge(
                p,
                {
                    **jars,
                    **{c: j for pp in ("lan", "khoa") for c, j in sim.persona_jars(pp).items()},
                },
            )
            if i % 10 == 0:
                save_caches(caches, model)
                print(f"  {i}/{len(todo)} ({time.time() - t0:.0f}s)")
        save_caches(caches, model)
        print("xong")
        return 0

    fitted: dict[str, Any] = {}
    if args.command == "calibrate":
        th, extra = calibrate(rows, th, caches, emb, judge)
        fitted = extra["fitted"]
        RESULTS.mkdir(exist_ok=True)
        (RESULTS / f"calibration-{args.mode}-{date.today().isoformat()}.json").write_text(
            json.dumps({"fitted": fitted, "grid": extra["grid"]}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print("hệ số:", json.dumps(fitted, ensure_ascii=False))
    rep = report(rows, th, caches, emb, judge, args.mode, model)
    if args.mode == "live":
        save_caches(caches, model)
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"classification-{args.mode}-{date.today().isoformat()}.json"
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    t = rep["test_split"]
    print(
        f"[{args.mode}] n={rep['n_rows']}; tập kiểm n={t['n']}: độ đúng (đã gán) {t['accuracy_assigned']}, tự gán {t['accuracy_auto']}, "
        f"hỏi {t['ask_rate']}, xem lại {t['review_rate']}; mục tiêu đạt: {rep['targets']}"
    )
    print("ghi", out)
    if args.command == "calibrate" and args.write_config:
        if args.mode != "live":
            print("KHÔNG ghi cấu hình: chế độ khô không đại diện")
            return 2
        write_config(th, fitted, rep)
        print("đã ghi", DEFAULTS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
