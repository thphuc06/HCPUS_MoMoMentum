"""Chạy bộ kiểm phân hũ tự động, báo cáo độ đúng, tỷ lệ phải hỏi, ma trận nhầm; hiệu chỉnh ngưỡng (F2, phase 4 luồng B).

    # THẬT (cần AWS): nhúng bằng Cohere Embed v3 và gọi model nhỏ qua Bedrock, có lưu đệm trong results/
    $env:AWS_REGION='ap-southeast-1'; $env:YOFINA_USAGE_TABLE='yofina-usage'
    uv run python evals/classification/run_eval.py warm            # gọi model nhỏ cho mọi giao dịch một lượt (lưu đệm; chậm: 18 lượt/phút)
    uv run python evals/classification/run_eval.py calibrate --write-config   # hiệu chỉnh trên nửa đầu, đo trên nửa sau, ghi classify_defaults.json
    uv run python evals/classification/run_eval.py run             # báo cáo với ngưỡng đang cấu hình

    # KHÔ (không cần AWS; embedding và model giả, KHÔNG phản ánh chất lượng thật, không ghi cấu hình)
    uv run python evals/classification/run_eval.py run --mode dry
    uv run python evals/classification/run_eval.py calibrate --mode dry

    # CHỈ ĐỆM (không tạo client AWS; dùng đệm Bedrock thật đã commit trong results/, thiếu đệm thì dừng và báo số lời gọi cần, không chạy mô phỏng)
    uv run python evals/classification/run_eval.py run --mode cache --out $env:TEMP/cls-base.json
    uv run python evals/classification/run_eval.py run --mode cache --add-jar khac:Khác:spending --out $env:TEMP/cls-khac.json

`--add-jar ma:tên:loại[:số dư]` thêm một hũ vào hũ của mọi persona (như persona có hũ đó trong bảng `jars`, xếp sau cùng); mã quyết định không đổi.
Thông điệp model nhỏ chứa danh sách hũ nên thêm hũ làm đổi khóa đệm: muốn đo thì `warm --add-jar ...` (chế độ live, tốn lời gọi) trước.

`--wallet multi|three` chọn ví đo (chỉ với `run` và `warm`; `calibrate` chỉ chạy trên ví nhiều hũ vì nó ghi ngưỡng của sản phẩm):
- `multi` (mặc định): hũ của từng persona trong spec (ví nhiều hũ theo loại chi), đệm `results/llm_cache.json` đã commit.
- `three`: ví 3 hũ của tài khoản mới (các hũ `is_default` của migration 0059: Chi hằng ngày, Nghĩa vụ, Dự phòng). Danh sách hũ trong lời
  nhắn là 3 hũ đó; đáp án, cờ "luôn luôn" của người dùng mô phỏng và nhãn seed đổi mã theo đúng quy tắc sản phẩm qua
  `scripts/measure_three_jars.py` (`yofina_core.wallet.transaction_jar`). `--seed-labels mapped` (mặc định, nhãn seed của persona đổi mã)
  hay `none` (tài khoản mới không có nhãn seed); hai chế độ dùng chung thông điệp nên chung đệm. Đệm model riêng `results/llm_cache_three.json`.

    # đo ví 3 hũ bằng model thật (cần AWS; khoảng 294 lời gọi model nhỏ, chạy tiếp được khi đứt): xem ước tính trước, gọi, rồi chấm từ đệm
    uv run python evals/classification/run_eval.py run --mode cache --wallet three           # chỉ in ước tính lời gọi và chi phí, không gọi gì
    uv run python evals/classification/run_eval.py warm --wallet three                       # gọi model nhỏ cho thông điệp còn thiếu, ghi đệm dần
    uv run python evals/classification/run_eval.py run --mode cache --wallet three --out $env:TEMP/cls-three.json

Chế độ live luôn in ước tính (số lời gọi model nhỏ và embedding, token, chi phí theo giá trong `SMALL_PRICE_USD_PER_MTOK`, thời gian theo tốc
độ của vai) TRƯỚC lời gọi đầu tiên, và ghi đệm sau mỗi `SAVE_EVERY` phán quyết mới cùng lúc kết thúc (kể cả khi lỗi): chạy lại cùng lệnh thì
chỉ gọi phần còn thiếu. `--limit N` lấy N dòng đầu của mỗi persona (thử ít lời gọi trước).

Mô phỏng và quyết định: xem `sim.py` (chạy đúng `Classifier` của Lambda). Tập hiệu chỉnh = nửa đầu theo thời gian của mỗi persona, tập kiểm = nửa sau
(người dùng mô phỏng sửa và trả lời nên nhãn và luật tích lũy qua cả hai nửa như sản phẩm thật). Kết quả ghi `results/classification-<mode>-<ngày>.json`.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import math
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import sim
from yofina_classify.llm_step import SYSTEM as JUDGE_SYSTEM
from yofina_classify.model import JarInfo

from yofina_ledger import classify_config
from yofina_ledger.classify_seed import decode_vector, encode_vector

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
EMB_CACHE = RESULTS / "embedding_cache.json"
LLM_CACHE = RESULTS / "llm_cache.json"
DEFAULTS = Path(classify_config.__file__).with_name(classify_config.DEFAULTS_FILE)
REPO = HERE.parents[1]

#: mục tiêu của phase 4 (tiêu chí hoàn thành số 6) và mức đúng riêng mà ngưỡng tự gán phải đạt trên tập hiệu chỉnh
TARGET_ACCURACY = 0.90
TARGET_ASK_RATE = 0.10
AUTO_ACCURACY = 0.95

#: ví đo được (`--wallet`) và tệp đệm phán quyết model nhỏ của từng ví (cùng thư mục với `LLM_CACHE`): thông điệp chứa danh sách hũ nên
#: mỗi ví một bộ khóa, để riêng tệp cho đệm đã commit của ví nhiều hũ không lẫn phán quyết của ví khác
WALLETS = ("multi", "three")
LLM_CACHE_FILES = {"multi": "llm_cache.json", "three": "llm_cache_three.json"}
#: nhãn seed trên ví 3 hũ (`scripts/measure_three_jars.py` `seed_labels`): đổi mã nhãn của persona, hoặc không có (tài khoản mới)
SEED_LABELS = ("mapped", "none")
#: chế độ live ghi đệm ra tệp sau mỗi chừng này phán quyết mới (và luôn ghi khi kết thúc, kể cả khi lỗi)
SAVE_EVERY = 10

# --- ước tính trước khi gọi model (chỉ để in, không quyết định gì) ------------------------------------------------------------
#: giá model nhỏ, USD mỗi 1 triệu token vào / ra: AWS Price List `ap-southeast-1` ngày 25/11/2026 (bảng model của
#: docs/research/agentcore-memory-design.md); model không có trong bảng thì không ước tính tiền
SMALL_PRICE_USD_PER_MTOK = {
    "global.amazon.nova-2-lite-v1:0": (0.41, 3.39),
    "global.anthropic.claude-haiku-4-5-20251001-v1:0": (1.0, 5.0),
}
#: Cohere Embed Multilingual v3, USD mỗi 1 triệu token (docs/research/bedrock.md)
EMBED_PRICE_USD_PER_MTOK = 0.10
#: giả định thô: số ký tự mỗi token cho JSON tiếng Việt có dấu
CHARS_PER_TOKEN = 3.0
#: như `yofina_classify.llm_step.judge`: trần token ra mỗi lời gọi, số lần thử của `structured_json`
JUDGE_MAX_OUTPUT_TOKENS = 256
JUDGE_MAX_ATTEMPTS = 2
#: `GatewayEmbedder.embed_many` gom lô tối đa 96 chuỗi mỗi lời gọi
EMBED_BATCH = 96


# --- ví đo -------------------------------------------------------------------------------------------------------------------
_MEASURE3: Any = None


def _measure_three_jars() -> Any:
    """`scripts/measure_three_jars.py` (nạp một lần theo đường dẫn): nơi giữ quy tắc ví 3 hũ của các phép đo offline (ví đọc từ migration
    0059, đáp án và nhãn seed đổi mã bằng `yofina_core.wallet.transaction_jar`). Dùng lại để số của bộ kiểm khớp số của ghi chú đo."""
    global _MEASURE3
    if _MEASURE3 is None:
        spec = importlib.util.spec_from_file_location(
            "_run_eval_measure_three_jars", REPO / "scripts" / "measure_three_jars.py"
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MEASURE3 = mod
    return _MEASURE3


@dataclasses.dataclass(frozen=True)
class WalletSetup:
    """Một ví đo: đổi đáp án của bộ dữ liệu (`rows`), hũ đưa vào lời nhắn và vào quyết định (`jars`, như `sim.JarsOf`), nhãn seed
    (`seeds`, như `sim.SeedsOf`; None là nhãn của persona)."""

    name: str
    seed_labels: str
    rows: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
    jars: sim.JarsOf
    seeds: sim.SeedsOf | None


def wallet_setup(name: str, seed_labels: str = "mapped") -> WalletSetup:
    """`multi`: ví của từng persona theo spec, đáp án và nhãn seed giữ nguyên. `three`: ví 3 hũ của tài khoản mới; đáp án và cờ nhất
    quán của người dùng mô phỏng đổi theo `measure_three_jars.three_jar_rows`, nhãn seed theo `measure_three_jars.seed_labels`
    (`seed_labels`: `mapped` hoặc `none`); hũ thêm (`--add-jar`) xếp sau ba hũ."""
    if name == "multi":
        return WalletSetup("multi", "persona", lambda rows: rows, sim.persona_jars, None)
    if name != "three":
        raise ValueError(f"ví không biết: {name!r}")
    if seed_labels not in SEED_LABELS:
        raise ValueError(f"nhãn seed không biết: {seed_labels!r}")
    m3 = _measure_three_jars()
    wallet = m3.three_jar_wallet()
    codes = list(wallet)

    def jars(persona: str, extra: Sequence[JarInfo] = ()) -> dict[str, JarInfo]:
        out = dict(wallet)
        for j in extra:
            out.setdefault(j.code, j)
        return out

    return WalletSetup(
        "three",
        seed_labels,
        lambda rows: m3.three_jar_rows(rows, codes),
        jars,
        lambda persona, jar_codes: m3.seed_labels(persona, jar_codes, seed_labels),
    )


def llm_cache_path(wallet: str) -> Path:
    """Tệp đệm phán quyết model nhỏ của ví (`LLM_CACHE_FILES`), cùng thư mục với `LLM_CACHE`; ví nhiều hũ là chính `LLM_CACHE`."""
    return LLM_CACHE if wallet == "multi" else LLM_CACHE.with_name(LLM_CACHE_FILES[wallet])


# --- đệm -----------------------------------------------------------------------------------------------------------------
def load_caches(mode: str, wallet: str = "multi") -> sim.Caches:
    c = sim.Caches()
    if mode in ("live", "cache"):
        if EMB_CACHE.exists():
            raw = json.loads(EMB_CACHE.read_text(encoding="utf-8"))
            c.embeddings = {k: decode_vector(v) for k, v in raw["vectors"].items()}
        llm = llm_cache_path(wallet)
        if llm.exists():
            c.verdicts = json.loads(llm.read_text(encoding="utf-8"))["verdicts"]
    return c


def save_caches(c: sim.Caches, model: str, wallet: str = "multi") -> None:
    """Ghi đệm embedding (chung mọi ví: khóa là chuỗi đã chuẩn hóa) và đệm phán quyết của ví `wallet`."""
    EMB_CACHE.parent.mkdir(parents=True, exist_ok=True)
    EMB_CACHE.write_text(
        json.dumps(
            {
                "model": model,
                "vectors": {k: encode_vector(v) for k, v in sorted(c.embeddings.items())},
            }
        ),
        encoding="utf-8",
    )
    llm_cache_path(wallet).write_text(
        json.dumps({"verdicts": dict(sorted(c.verdicts.items()))}, ensure_ascii=False, indent=0),
        encoding="utf-8",
    )


def live_backends() -> tuple[Any, Any, str]:
    """Cổng Bedrock thật của chế độ live: (embedding có `embed_many`, model nhỏ `judge(prompt, jars)`, tên model embedding), đều qua
    `yofina_core.llm` (giới hạn tốc độ, trần ngày chung). Test thay hàm này bằng bản giả."""
    from yofina_classify.adapters import GatewayEmbedder, GatewayJudge

    from yofina_core.llm import LlmGateway

    gw = LlmGateway()
    return GatewayEmbedder(gw), GatewayJudge(gw), "cohere.embed-multilingual-v3"


def build_backends(mode: str, caches: sim.Caches, rows: list[dict[str, Any]]):
    """(embedder, judge, tên model embedding). Chế độ thật nhúng gộp mọi chuỗi còn thiếu trước (vài lời gọi)."""
    if mode == "cache":
        # không có cổng `live`: thiếu đệm thì CachedEmbedder ném KeyError, CachedJudge(strict) ném KeyError (không suy giảm âm thầm)
        model = (
            json.loads(EMB_CACHE.read_text(encoding="utf-8"))["model"]
            if EMB_CACHE.exists()
            else "?"
        )
        return sim.CachedEmbedder(caches, model), sim.CachedJudge(caches, strict=True), model
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
    live_emb, live_judge, model = live_backends()
    missing = [t for t in sim.prefetch_texts(rows) if t not in caches.embeddings]
    if missing:
        model, vecs = live_emb.embed_many(missing)
        caches.embeddings.update(dict(zip(missing, vecs, strict=True)))
    return (
        sim.CachedEmbedder(caches, model, live_emb),
        sim.CachedJudge(caches, live_judge),
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


# --- chế độ chỉ đệm và hũ thêm ---------------------------------------------------------------------------------------------
JAR_KINDS = ("spending", "saving", "obligation")


def parse_jar(spec: str) -> JarInfo:
    """`ma:tên:loại[:số dư]` (ví dụ `khac:Khác:spending` hoặc `khac:Khác:spending:0`) thành hũ thêm cho mọi persona.

    Không ghi số dư thì lấy như các hũ khác của mô phỏng (`sim.BIG_BALANCE`, số dư không bao giờ chặn). Hũ 0% mới tạo của sản phẩm có số dư 0,
    và `Classifier._finish` không đưa khoản chi từ hũ (`funding_source` jar) vào hũ không đủ số dư: ghi `:0` để đo đúng trường hợp đó."""
    parts = spec.split(":")
    ok = len(parts) in (3, 4) and parts[0] and parts[1] and parts[2] in JAR_KINDS
    if ok and len(parts) == 4:
        ok = parts[3].isdigit()
    if not ok:
        raise argparse.ArgumentTypeError(
            f"cần dạng ma:tên:loại[:số dư] với loại thuộc {JAR_KINDS}, nhận {spec!r}"
        )
    balance = int(parts[3]) if len(parts) == 4 else sim.BIG_BALANCE
    return JarInfo(parts[0], parts[1], parts[2], balance)


def missing_calls(
    rows: list[dict[str, Any]],
    th: classify_config.ClassifyThresholds,
    caches: sim.Caches,
    extra_jars: Sequence[JarInfo],
    jars_of: sim.JarsOf | None = None,
) -> tuple[list[str], list[str]]:
    """(thông điệp model nhỏ chưa có phán quyết đệm, chuỗi chưa có embedding đệm): đúng tập mà chế độ live sẽ gọi, KHÔNG gọi gì (dựng
    thông điệp không cần embedding)."""
    emb = sim.CachedEmbedder(caches, "?")
    seen: set[str] = set()
    prompts = []
    for p in sim.warm_prompts(rows, th, emb, extra_jars, jars_of=jars_of):
        key = sim.prompt_key(p)
        if key not in caches.verdicts and key not in seen:
            seen.add(key)
            prompts.append(p)
    texts = [t for t in sim.prefetch_texts(rows) if t not in caches.embeddings]
    return prompts, texts


def cache_gaps(
    rows: list[dict[str, Any]],
    th: classify_config.ClassifyThresholds,
    caches: sim.Caches,
    emb: sim.CachedEmbedder,
    extra_jars: Sequence[JarInfo],
    jars_of: sim.JarsOf | None = None,
) -> dict[str, Any]:
    """Số chuỗi chưa có embedding đệm và số thông điệp model nhỏ chưa có phán quyết đệm (đúng tập mà `warm` sẽ gọi), KHÔNG gọi gì."""
    emb_missing = [t for t in sim.prefetch_texts(rows) if t not in caches.embeddings]
    keys = {sim.prompt_key(p) for p in sim.warm_prompts(rows, th, emb, extra_jars, jars_of=jars_of)}
    llm_missing = sorted(k for k in keys if k not in caches.verdicts)
    return {
        "embedding_texts": len(sim.prefetch_texts(rows)),
        "embedding_missing": len(emb_missing),
        "llm_prompts": len(keys),
        "llm_missing": len(llm_missing),
        "llm_calls_needed": len(llm_missing),
    }


def _role_models(role: str) -> list[dict[str, Any]]:
    from yofina_core.llm import load_defaults

    return list(((load_defaults().get("roles") or {}).get(role) or {}).get("models") or [])


def estimate(prompts: Sequence[str], *, embed_texts: Sequence[str] = ()) -> dict[str, Any]:
    """Ước tính TRƯỚC khi gọi: số lời gọi model nhỏ (một mỗi thông điệp; tối đa `JUDGE_MAX_ATTEMPTS` lần nếu đầu ra sai dạng), số lời
    gọi embedding (gom lô `EMBED_BATCH`), token (ký tự / `CHARS_PER_TOKEN`, cộng lời nhắn hệ thống; chưa tính schema của tool), chi phí
    theo `SMALL_PRICE_USD_PER_MTOK` của model đầu của vai `small` (tối đa: mọi lần thử, giá của model đắt nhất trong chuỗi dự phòng) và
    thời gian theo tốc độ của vai. Số thô, chỉ để quyết định có chạy không."""
    small = _role_models("small")
    embed = _role_models("embedding")
    model = small[0]["id"] if small else None
    calls = len(prompts)
    tokens_in = sum(len(JUDGE_SYSTEM) + len(p) for p in prompts) / CHARS_PER_TOKEN
    tokens_out = calls * JUDGE_MAX_OUTPUT_TOKENS
    embed_calls = math.ceil(len(embed_texts) / EMBED_BATCH)
    embed_tokens = sum(len(t) for t in embed_texts) / CHARS_PER_TOKEN
    embed_cost = embed_tokens * EMBED_PRICE_USD_PER_MTOK / 1e6

    def cost(model_id: str | None, attempts: int) -> float | None:
        price = SMALL_PRICE_USD_PER_MTOK.get(model_id or "")
        if price is None:
            return None
        return attempts * (tokens_in * price[0] + tokens_out * price[1]) / 1e6 + embed_cost

    per_model = [c for m in small if (c := cost(m.get("id"), JUDGE_MAX_ATTEMPTS)) is not None]
    rpm = float(small[0].get("rpm") or 0) if small else 0.0
    embed_rpm = float(embed[0].get("rpm") or 0) if embed else 0.0
    minutes = (calls / rpm if rpm else 0.0) + (embed_calls / embed_rpm if embed_rpm else 0.0)
    return {
        "llm_calls": calls,
        "llm_calls_max_with_retry": calls * JUDGE_MAX_ATTEMPTS,
        "embed_calls": embed_calls,
        "model": model,
        "rpm": rpm,
        "input_tokens": round(tokens_in),
        "output_tokens_max": tokens_out,
        "cost_usd": round(cost(model, 1) or 0.0, 4) if calls or embed_calls else 0.0,
        "cost_usd_max": round(max(per_model, default=embed_cost), 4)
        if calls or embed_calls
        else 0.0,
        "minutes": round(minutes, 1),
    }


def render_estimate(est: Mapping[str, Any], wallet: str) -> str:
    return (
        f"ước tính (ví {wallet}): {est['llm_calls']} lời gọi model nhỏ {est['model']} (tối đa {est['llm_calls_max_with_retry']} nếu phải "
        f"thử lại), {est['embed_calls']} lời gọi embedding; khoảng {est['input_tokens']} token vào, tối đa {est['output_tokens_max']} "
        f"token ra; chi phí khoảng {est['cost_usd']} USD, tối đa {est['cost_usd_max']} USD; khoảng {est['minutes']} phút ở "
        f"{est['rpm']:.0f} lượt/phút"
    )


def small_one_off_reach(
    rows: list[dict[str, Any]], th: classify_config.ClassifyThresholds, res: list[sim.Result]
) -> dict[str, Any]:
    """Phạm vi tối đa của luật 'khoản nhỏ một lần' trên từng tập, tính từ điều kiện không phụ thuộc model (`sim.small_one_off_eligible`)
    và quyết định của lượt chạy này (mục hỏi gộp nằm trong tập đủ điều kiện). Không phải số đo của biến thể có hũ thêm."""
    eligible = sim.small_one_off_eligible(rows, th)
    out: dict[str, Any] = {"max_vnd": th.small_one_off_max_vnd}
    for split in ("calibration", "test"):
        rs = [r for r in res if r.split == split]
        el = [r for r in rs if r.row["id"] in eligible]
        out[split] = {
            "n": len(rs),
            "eligible": len(el),
            "eligible_share": round(len(el) / len(rs), 4) if rs else None,
            "eligible_and_ask": sum(1 for r in el if not r.decision.assigned),
            "eligible_by_category": dict(Counter(r.row["category"] for r in el)),
        }
    return out


# --- báo cáo ---------------------------------------------------------------------------------------------------------------
def report(
    rows,
    th,
    caches,
    emb,
    judge,
    mode: str,
    model: str,
    extra_jars: Sequence[JarInfo] = (),
    setup: WalletSetup | None = None,
) -> dict[str, Any]:
    setup = setup or wallet_setup("multi")
    res = sim.run_sim(
        rows, th, caches, emb, judge, extra_jars, jars_of=setup.jars, seeds_of=setup.seeds
    )
    cal = [r for r in res if r.split == "calibration"]
    test = [r for r in res if r.split == "test"]
    mt = sim.metrics(test)
    return {
        "mode": mode,
        "representative": mode in ("live", "cache"),
        "date": date.today().isoformat(),
        "wallet": setup.name,
        "wallet_jars": [dataclasses.asdict(j) for j in setup.jars("minh", extra_jars).values()]
        if setup.name != "multi"
        else None,
        "seed_labels": setup.seed_labels,
        "llm_cache": llm_cache_path(setup.name).name,
        "embedding_model": model,
        "extra_jars": [dataclasses.asdict(j) for j in extra_jars],
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
        "small_one_off_reach": small_one_off_reach(rows, th, res),
        "llm_calls_this_run": getattr(judge, "calls", 0),
        "llm_errors": dict(Counter(r.decision.llm_error for r in res if r.decision.llm_error)),
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
    ap.add_argument("--mode", choices=["live", "dry", "cache"], default="live")
    ap.add_argument(
        "--write-config",
        action="store_true",
        help="ghi ngưỡng đã hiệu chỉnh vào classify_defaults.json (chỉ chế độ live)",
    )
    ap.add_argument("--limit", type=int, help="chỉ lấy N dòng đầu mỗi persona (thử nhanh)")
    ap.add_argument(
        "--add-jar",
        type=parse_jar,
        action="append",
        default=[],
        metavar="MA:TEN:LOAI",
        help="thêm hũ cho mọi persona, ví dụ khac:Khác:spending hoặc khac:Khác:spending:0 (chỉ với run và warm; lặp được)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        help="ghi báo cáo vào tệp này thay cho results/classification-<chế độ>[-three]-<ngày>.json",
    )
    ap.add_argument(
        "--wallet",
        choices=WALLETS,
        default="multi",
        help="ví đo: multi (hũ của persona, mặc định) hoặc three (ví 3 hũ của tài khoản mới, đệm model riêng); chỉ với run và warm",
    )
    ap.add_argument(
        "--seed-labels",
        choices=SEED_LABELS,
        default="mapped",
        help="ví three: nhãn seed của persona đổi mã theo quy tắc sản phẩm (mapped) hoặc không có nhãn seed (none, tài khoản mới)",
    )
    args = ap.parse_args()
    extra_jars: list[JarInfo] = args.add_jar
    if extra_jars and args.command == "calibrate":
        print("--add-jar chỉ dùng với run và warm")
        return 2
    if args.wallet != "multi" and args.command == "calibrate":
        print(
            "--wallet three chỉ dùng với run và warm: hiệu chỉnh ghi ngưỡng của sản phẩm, chỉ làm trên ví nhiều hũ"
        )
        return 2

    setup = wallet_setup(args.wallet, args.seed_labels)
    rows = sim.load_dataset()
    if args.limit:
        rows = [r for r in rows if r["seq"] < args.limit]
    rows = setup.rows(rows)
    th = classify_config.load_thresholds()
    caches = load_caches(args.mode, args.wallet)
    if args.mode in ("live", "cache"):
        # ước tính TRƯỚC lời gọi đầu tiên (chế độ live nhúng chuỗi còn thiếu ngay trong build_backends)
        todo_prompts, todo_texts = missing_calls(rows, th, caches, extra_jars, setup.jars)
        print(
            render_estimate(estimate(todo_prompts, embed_texts=todo_texts), args.wallet), flush=True
        )
    emb, judge, model = build_backends(args.mode, caches, rows)
    if args.mode == "live":
        save_caches(caches, model, args.wallet)

        def checkpoint(n: int) -> None:
            if n % SAVE_EVERY == 0:
                save_caches(caches, model, args.wallet)

        judge.on_store = checkpoint

    if args.mode == "cache":
        if args.command != "run":
            print("chế độ cache chỉ chạy run")
            return 2
        gaps = cache_gaps(rows, th, caches, emb, extra_jars, setup.jars)
        print("đệm:", json.dumps(gaps, ensure_ascii=False))
        if gaps["embedding_missing"] or gaps["llm_missing"]:
            print(
                f"DỪNG: thiếu {gaps['embedding_missing']} embedding và {gaps['llm_missing']} phán quyết model nhỏ trong đệm "
                f"({llm_cache_path(args.wallet).name}); không chạy mô phỏng (không có cổng gọi model ở chế độ này). Lấp đệm bằng "
                f"`warm --wallet {args.wallet}` ở chế độ live (tốn lời gọi, xem ước tính ở trên)."
            )
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(
                    json.dumps(
                        {
                            "mode": "cache",
                            "date": date.today().isoformat(),
                            "wallet": args.wallet,
                            "extra_jars": [dataclasses.asdict(j) for j in extra_jars],
                            "cache_gaps": gaps,
                        },
                        ensure_ascii=False,
                        indent=1,
                    ),
                    encoding="utf-8",
                )
                print("ghi", args.out)
            return 3

    if args.command == "warm":
        if args.mode != "live":
            print("warm chỉ có nghĩa ở chế độ live")
            return 2
        todo = [
            p
            for p in dict.fromkeys(sim.warm_prompts(rows, th, emb, extra_jars, jars_of=setup.jars))
            if sim.prompt_key(p) not in caches.verdicts
        ]
        print(f"{len(todo)} thông điệp chưa có đệm (tốc độ giới hạn theo vai small)")
        t0 = time.time()
        # chỉ dùng để kiểm mã hũ model trả; kiểm thật ở lần chạy sim (đệm lưu mã model trả)
        jars = {
            c: j
            for p in sorted({r["persona"] for r in rows})
            for c, j in setup.jars(p, extra_jars).items()
        }
        try:
            for i, p in enumerate(todo, 1):
                judge(p, jars)
                if i % 10 == 0:
                    print(f"  {i}/{len(todo)} ({time.time() - t0:.0f}s)")
        finally:
            save_caches(
                caches, model, args.wallet
            )  # đứt giữa chừng: chạy lại chỉ gọi phần còn thiếu
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
    try:
        rep = report(rows, th, caches, emb, judge, args.mode, model, extra_jars, setup)
    finally:
        if args.mode == "live":
            save_caches(caches, model, args.wallet)
    # lời gọi model lỗi thì quyết định đó suy giảm như Lambda (không có bằng chứng của model): báo để không đọc nhầm số
    if rep["llm_errors"]:
        print(
            f"CẢNH BÁO: lời gọi model lỗi {rep['llm_errors']}; số đo thiếu phần model ở các dòng đó, chạy lại để lấp đệm."
        )
    RESULTS.mkdir(exist_ok=True)
    suffix = "" if args.wallet == "multi" else f"-{args.wallet}"
    out = (
        args.out or RESULTS / f"classification-{args.mode}{suffix}-{date.today().isoformat()}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    t = rep["test_split"]
    print(
        f"[{args.mode}] n={rep['n_rows']}; tập kiểm n={t['n']}: độ đúng (đã gán) {t['accuracy_assigned']}, tự gán {t['accuracy_auto']}, "
        f"hỏi {t['ask_rate']}, xem lại {t['review_rate']}; mục tiêu đạt: {rep['targets']}"
    )
    print(
        "phạm vi luật khoản nhỏ một lần:",
        json.dumps(rep["small_one_off_reach"], ensure_ascii=False),
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
