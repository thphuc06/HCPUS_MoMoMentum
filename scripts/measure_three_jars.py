"""Đo offline ví 3 hũ của tài khoản mới (Chi hằng ngày, Nghĩa vụ, Dự phòng; issue #39): phân loại, dự báo hũ gộp, phát hiện đổi
hành vi trên chuỗi gộp. CÔNG CỤ ĐO TRÊN MÁY: không gọi AWS, không gọi model, không ghi gì ngoài tệp `--out`.

    uv run python scripts/measure_three_jars.py classify                    # phân loại 7 hũ và 3 hũ, đệm embedding đã commit, không model
    uv run python scripts/measure_three_jars.py forecast [--quick]          # backtest rolling-origin: hũ riêng, hũ gộp, ví 3 hũ
    uv run python scripts/measure_three_jars.py pelt                        # PELT trên chuỗi gộp Chi hằng ngày của `minh` (cảnh 4)
    uv run python scripts/measure_three_jars.py pelt-synth [--quick]        # báo nhầm và độ nhạy của PELT trên chuỗi gộp tổng hợp

Mọi lệnh nhận `--out tệp.json` để ghi số đo. Kết quả và cách đọc: `docs/research/2026-11-26-do-vi-ba-hu.md`.

Quy tắc ánh xạ hũ là của sản phẩm, không viết lại: `yofina_core.wallet.transaction_jar` (dùng `LEGACY_JAR_ALIASES`) đưa một mã hũ cũ của
bộ bảy sang hũ của ví mới (Ăn uống, Đi lại, Giải trí, Du lịch vào Chi hằng ngày; Hóa đơn và loại `subscription` vào Nghĩa vụ). Bộ hũ
của tài khoản mới đọc từ migration 0059 (`is_default` true), bảng loại giao dịch từ `db/seed/tx_type_map.sql`.

- `classify`: chạy đúng `Classifier` của Lambda qua mô phỏng của `evals/classification/sim.py` (người dùng mô phỏng, kho nhãn k-NN trong
  bộ nhớ). Model nhỏ KHÔNG được gọi: thông điệp gửi model chứa danh sách hũ nên đệm của bộ bảy không dùng được cho ví 3 hũ (#28). Phép đo
  chính chạy bộ phân loại không có bước model (đường suy giảm `ModelBudgetExceeded` của sản phẩm) trên cả hai ví. Kèm hai phép TÍNH
  (không phải số đo): chiếu quyết định của bộ bảy (có model, đệm thật) sang ba hũ, và chạy ví 3 hũ với phán quyết đệm của bộ bảy đổi
  mã hũ theo cùng quy tắc (giả định model chọn hũ gộp tương ứng, cùng độ chắc).
- `forecast`: `forecast_user` với hiệu chỉnh hiện hành (CQR hũ dày, PAV hũ thưa), cổng % tắt khi chạy để luôn có p, cờ hiện % theo cổng
  thật. Persona tổng hợp giữ ra ngoài (seed 201-206, hai họ bộ sinh), origin từ ngày 120 bước 7, chân trời 30 ngày, lịch sử cắt 47 / 120
  ngày / đủ, 2.000 đường, hạt `seed * 1000 + origin` (như `backtest/recalibrate.py`). Ba biến thể: hũ riêng (bộ sinh gốc), `gop3` (Ăn
  uống + Đi lại + Giải trí cộng thành một chuỗi), `ba_hu` (mọi hũ chi tiêu cộng lại, như ví 3 hũ). Số dư thật của hũ gộp là tổng số dư
  của các hũ thành phần. Không ghi bảng hiệu chỉnh.
- `pelt`: lịch sử 120 ngày của `minh` trên ví demo; khoản chi thêm vào hũ Ăn uống như `scripts/measure_scene4_pelt.py` (cùng `plan_shift`,
  cùng mức chi tuần cũ của hũ Ăn uống), nhưng PELT chạy trên chuỗi ngày gộp Ăn uống + Đi lại + Giải trí. Hệ số tính theo mức cũ của
  hũ Ăn uống để so được với 2,04 / 2,1 của hũ riêng. Kèm tệp sao kê cảnh 4 thật (`minh_sao_ke_2_tuan.csv`).
- `pelt-synth`: như `yofina_ml.backtest.change_calibration` (mỗi đêm một lần, chỉ nhìn tới hôm qua, chấm theo điểm gãy thật của bộ sinh)
  trên seed 201-208: từng hũ chi tiêu riêng, rồi chuỗi gộp.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import importlib.util
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# một luồng BLAS mỗi tiến trình: nhiều tiến trình song song mà mỗi cái mở đủ luồng OpenBLAS thì hết bộ nhớ (đặt trước khi nhập numpy)
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
# thêm vào CUỐI sys.path: không che module trùng tên (ví dụ `handler`) của gói khác khi test nạp script này
for _extra in (
    "libs/yofina_core/src",
    "gateway/tools/ledger",
    "pipelines/classify",
    "evals/classification",
    "data",
):
    if str(REPO / _extra) not in sys.path:
        sys.path.append(str(REPO / _extra))

from yofina_core.wallet import transaction_jar  # noqa: E402

#: mã hũ gộp (mã của hũ Chi hằng ngày trong danh mục 0059)
MERGED_CODE = "chi_hang_ngay"
ONBOARDING_MIGRATION = REPO / "db" / "migrations" / "0059_activate_onboarding_jar_layout.sql"


# =====================================================================================================================
# Ví 3 hũ và ánh xạ nhãn
# =====================================================================================================================
def onboarding_layout(path: Path = ONBOARDING_MIGRATION) -> list[tuple[str, str, str]]:
    """[(mã, tên, loại)] của các hũ `is_default` true trong migration 0059, theo `sort_order`."""
    sql = path.read_text(encoding="utf-8")
    pat = re.compile(
        r"\('([a-z_]+)',\s*'([^']+)',\s*'[a-z]+',\s*'[a-z]+',\s*'([a-z]+)',\s*\d+,\s*(true|false),\s*(\d+),"
    )
    rows = [m.groups() for m in pat.finditer(sql)]
    picked = sorted(
        (int(order), code, name, kind) for code, name, kind, on, order in rows if on == "true"
    )
    return [(code, name, kind) for _, code, name, kind in picked]


def to_layout(code: str | None, jar_codes: Iterable[str], tx_type: str = "") -> str | None:
    """Mã hũ của bộ bảy sang hũ của ví đích, đúng quy tắc của sản phẩm (`transaction_jar`)."""
    return transaction_jar(code, jar_codes, tx_type=tx_type)


def type_routes(types: dict[str, Any], wallets: dict[str, Sequence[str]]) -> list[dict[str, Any]]:
    """Mỗi loại giao dịch chi (`direction` out): hũ bước 0 đưa vào trên từng ví (None: Chưa phân loại, tới luật, embedding, model)."""
    out = []
    for tx, info in types.items():
        if info.direction != "out":
            continue
        out.append(
            {
                "tx_type": tx,
                "label": info.label,
                "default": info.default_jar_code,
                **{w: to_layout(info.default_jar_code, codes, tx) for w, codes in wallets.items()},
            }
        )
    return out


# =====================================================================================================================
# classify
# =====================================================================================================================
def _sim():
    import sim

    return sim


def three_jar_wallet() -> dict[str, Any]:
    sim = _sim()
    from yofina_classify.model import JarInfo

    return {c: JarInfo(c, n, k, sim.BIG_BALANCE) for c, n, k in onboarding_layout()}


def three_jar_rows(
    rows: list[dict[str, Any]], codes: Sequence[str], *, recompute_consistent: bool = True
) -> list[dict[str, Any]]:
    """Bộ dữ liệu nhãn với đáp án đổi sang ví đích. `truth_jar_7` giữ đáp án cũ.

    Cờ `consistent` của chuyển khoản tên riêng không lời nhắn (người dùng mô phỏng chọn "luôn luôn" khi người nhận có hũ nhất quán) tính
    lại theo thói quen của bộ sinh (`build_dataset.HABITS`): người nhận có hũ chính và hũ nhiễu cùng rơi vào một hũ của ví đích thì nhất
    quán. Các loại khác giữ cờ của bộ dữ liệu (cửa hàng luôn một hũ thì vẫn một hũ). `recompute_consistent` False: giữ mọi cờ cũ."""
    import build_dataset

    out = []
    for r in rows:
        truth = to_layout(r["truth_jar"], codes, r["tx_type"])
        if truth is None:
            raise ValueError(f"{r['id']}: hũ {r['truth_jar']} không có chỗ trên ví {list(codes)}")
        new = {**r, "truth_jar": truth, "truth_jar_7": r["truth_jar"]}
        if recompute_consistent and r["category"] == "person_no_note" and r.get("payee_key"):
            main, share, noise = build_dataset.HABITS[r["persona"]][r["payee_key"]]
            same = to_layout(main, codes, r["tx_type"]) == to_layout(noise, codes, r["tx_type"])
            new["consistent"] = share >= 0.85 or same
        out.append(new)
    return out


class OfflineEmbedder:
    """Embedding chỉ từ đệm đã commit. Chuỗi chưa có đệm thì ném `ModelBudgetExceeded`, đúng đường suy giảm của sản phẩm (bước
    embedding bị bỏ, quyết định dựa vào bằng chứng còn lại). Ghi lại các chuỗi thiếu để báo."""

    def __init__(self, embeddings: dict[str, list[float]], model: str) -> None:
        self.embeddings, self.model = embeddings, model
        self.missing: set[str] = set()

    def embed(self, text_norm: str) -> tuple[str, list[float]]:
        if text_norm not in self.embeddings:
            from yofina_core.llm import ModelBudgetExceeded

            self.missing.add(text_norm)
            raise ModelBudgetExceeded("không có embedding đệm (đo offline)", role="embedding")
        return self.model, self.embeddings[text_norm]


class NoModelJudge:
    """Không có model nhỏ: mọi lời gọi ném `ModelBudgetExceeded` (sản phẩm ghi `llm_error`, không có bằng chứng của model)."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, prompt: str, jars: Any):
        from yofina_core.llm import ModelBudgetExceeded

        self.calls += 1
        raise ModelBudgetExceeded("không gọi model (đo offline)", role="small")


class CachedVerdictJudge:
    """Phán quyết model nhỏ THẬT đã lưu đệm (`results/llm_cache.json`), khóa theo băm thông điệp. Thiếu đệm thì như không có model."""

    def __init__(self, verdicts: dict[str, dict[str, Any]]) -> None:
        self.verdicts = verdicts
        self.calls = self.hits = 0

    def __call__(self, prompt: str, jars: Any):
        from yofina_classify.model import Verdict

        from yofina_core.llm import ModelBudgetExceeded

        sim = _sim()
        self.calls += 1
        c = self.verdicts.get(sim.prompt_key(prompt))
        if c is None:
            raise ModelBudgetExceeded("không có phán quyết đệm (đo offline)", role="small")
        self.hits += 1
        return Verdict(
            c["jar"] if c["jar"] in jars else None,
            float(c["conf"]),
            c["runner"] if c["runner"] in jars else None,
        )


class RemappedJudge:
    """GIẢ ĐỊNH, không phải số đo: trên ví đích, model trả đúng phán quyết đệm của bộ bảy cho cùng giao dịch (cùng lịch sử người nhận),
    mã hũ đổi theo `to_layout`, độ chắc giữ nguyên. Thông điệp của bộ bảy dựng lại như `sim.warm_prompts` (`prompt_keys_7`)."""

    def __init__(self, verdicts: dict[str, dict[str, Any]], keys_7: dict[str, str]) -> None:
        self.verdicts, self.keys_7 = verdicts, keys_7
        self.row: dict[str, Any] | None = None
        self.calls = self.hits = 0

    def __call__(self, prompt: str, jars: Any):
        from yofina_classify.model import Verdict

        from yofina_core.llm import ModelBudgetExceeded

        assert self.row is not None
        self.calls += 1
        c = self.verdicts.get(self.keys_7.get(self.row["id"], ""))
        if c is None:
            raise ModelBudgetExceeded("không có phán quyết đệm (đo offline)", role="small")
        self.hits += 1
        tx = self.row["tx_type"]
        jar = to_layout(c["jar"], jars, tx) if c["jar"] else None
        runner = to_layout(c["runner"], jars, tx) if c["runner"] else None
        return Verdict(jar, float(c["conf"]) if jar else 0.0, runner if runner != jar else None)


def prompt_keys_7(rows: list[dict[str, Any]], th: Any, embedder: Any) -> dict[str, str]:
    """id giao dịch -> khóa đệm của thông điệp model nhỏ trên ví persona (bộ bảy), dựng như `sim.warm_prompts`."""
    from yofina_classify.model import Verdict
    from yofina_classify.pipeline import Classifier

    sim = _sim()
    types = sim.load_type_map()
    out: dict[str, str] = {}
    for persona in sorted({r["persona"] for r in rows}):
        jars = sim.persona_jars(persona)
        state = sim.PersonaState(persona, th)
        clf = Classifier(th, state.labels, embedder, lambda p, j: Verdict(None, 0.0))
        for row in sorted((r for r in rows if r["persona"] == persona), key=lambda r: r["seq"]):
            ctx = state.context(row, jars, types)
            out[row["id"]] = sim.prompt_key(clf.build_prompt(sim.facts_of(row), ctx))
            key = state.key_of(row)
            if key:
                state.history[key][row["truth_jar"]] += 1
    return out


def seed_labels(persona: str, jar_codes: Sequence[str], mode: str) -> list[tuple[str, str]]:
    """Nhãn seed nạp vào kho k-NN. `persona`: nhãn của persona như bộ kiểm (ví bộ bảy). `mapped`: cùng nhãn, mã hũ đổi theo
    `to_layout`. `alias`: như `classify_seed.apply_seed_labels(jar_aliases=LEGACY_JAR_ALIASES)` (đổi mã theo bảng alias, bỏ nhãn của hũ
    ví không có). `none`: không có nhãn (tài khoản mới qua onboarding: sản phẩm chỉ nạp nhãn seed khi đặt lại demo)."""
    from yofina_core.wallet import LEGACY_JAR_ALIASES

    sim = _sim()
    if mode == "none":
        return []
    labels = sim.seed_texts(persona)
    if mode == "persona":
        return labels
    if mode == "mapped":
        return [(t, j3) for t, j in labels if (j3 := to_layout(j, jar_codes)) is not None]
    if mode == "alias":
        return [(t, a) for t, j in labels if (a := LEGACY_JAR_ALIASES.get(j, j)) in set(jar_codes)]
    raise ValueError(mode)


def simulate(
    rows: list[dict[str, Any]],
    th: Any,
    embedder: OfflineEmbedder,
    judge: Callable[..., Any],
    *,
    wallet: Callable[[str], dict[str, Any]],
    seeds: Callable[[str, Sequence[str]], list[tuple[str, str]]],
) -> list[Any]:
    """Như `sim.run_sim` nhưng ví và nhãn seed truyền vào (mã quyết định, người dùng mô phỏng, tách tập giữ nguyên)."""
    from yofina_classify.pipeline import Classifier

    sim = _sim()
    types = sim.load_type_map()
    splits = sim.split_of(rows)
    results = []
    for persona in sorted({r["persona"] for r in rows}):
        jars = wallet(persona)
        state = sim.PersonaState(persona, th)
        for text, jar in seeds(persona, list(jars)):
            try:
                _, vec = embedder.embed(text)
            except Exception:  # thiếu đệm: bỏ nhãn đó (không có ở bộ hiện tại, báo qua `missing`)
                continue
            state.labels.add(text, jar, "seed", vec)
        clf = Classifier(th, state.labels, embedder, judge)
        for row in sorted((r for r in rows if r["persona"] == persona), key=lambda r: r["seq"]):
            if isinstance(judge, RemappedJudge):
                judge.row = row
            ctx = state.context(row, jars, types)
            d = clf.classify(sim.facts_of(row), ctx)
            results.append(sim.Result(row, d, splits[row["id"]]))
            state.feedback(row, d)
    return results


def project(results: list[Any], codes: Sequence[str]) -> list[Any]:
    """Quyết định của bộ bảy chiếu sang ví đích: hũ đã gán và đáp án cùng đổi theo `to_layout`; mức (auto, review, hỏi) giữ nguyên."""
    sim = _sim()
    out = []
    for r in results:
        tx = r.row["tx_type"]
        d = dataclasses.replace(
            r.decision, jar=to_layout(r.decision.jar, codes, tx) if r.decision.jar else None
        )
        row = {**r.row, "truth_jar": to_layout(r.row["truth_jar"], codes, tx)}
        out.append(sim.Result(row, d, r.split))
    return out


def _brief(m: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "n",
        "assigned",
        "auto",
        "review",
        "ask",
        "accuracy_assigned",
        "accuracy_auto",
        "ask_rate",
        "review_rate",
        "correct_end_to_end",
        "silent_error_rate",
    )
    return {k: m[k] for k in keys}


def classify_report(results: list[Any]) -> dict[str, Any]:
    sim = _sim()
    test = [r for r in results if r.split == "test"]
    asks = [r for r in results if not r.decision.assigned]
    return {
        "test": _brief(sim.metrics(test)),
        "all": _brief(sim.metrics(results)),
        "test_by_category": sim.metrics(test)["by_category"],
        "confusion_test": sim.confusion(test),
        "ask_by_tx_type_all": dict(Counter(r.row["tx_type"] for r in asks).most_common()),
        "ask_by_tx_type_test": dict(
            Counter(r.row["tx_type"] for r in asks if r.split == "test").most_common()
        ),
        "stage_all": dict(Counter(r.decision.stage for r in results).most_common()),
        "top_errors_test": sim.errors(test, limit=10),
    }


def run_classify() -> dict[str, Any]:
    sim = _sim()
    import run_eval

    from yofina_ledger import classify_config

    rows7 = sim.load_dataset()
    th = classify_config.load_thresholds()
    caches = run_eval.load_caches("cache")
    model = json.loads(run_eval.EMB_CACHE.read_text(encoding="utf-8"))["model"]
    wallet3 = three_jar_wallet()
    codes3 = list(wallet3)
    rows3 = three_jar_rows(rows7, codes3)
    rows3_old = three_jar_rows(rows7, codes3, recompute_consistent=False)

    def wallet7(persona: str) -> dict[str, Any]:
        return sim.persona_jars(persona)

    def wallet_3(persona: str) -> dict[str, Any]:
        return dict(wallet3)

    def seeds_of(mode: str):
        return lambda persona, codes: seed_labels(persona, codes, mode)

    probe = OfflineEmbedder(caches.embeddings, model)
    keys7 = prompt_keys_7(rows7, th, probe)
    runs: dict[str, dict[str, Any]] = {}
    specs = {
        # tên: (bộ dữ liệu, ví, nhãn seed, judge, loại số)
        "bay_hu_co_model": (rows7, wallet7, "persona", lambda: CachedVerdictJudge(caches.verdicts), "đo (đệm model thật)"),
        "bay_hu_khong_model": (rows7, wallet7, "persona", NoModelJudge, "đo"),
        "ba_hu_khong_model": (rows3, wallet_3, "mapped", NoModelJudge, "đo"),
        "bay_hu_khong_seed_khong_model": (rows7, wallet7, "none", NoModelJudge, "đo"),
        "ba_hu_khong_seed_khong_model": (rows3, wallet_3, "none", NoModelJudge, "đo"),
        "ba_hu_model_doi_ma": (rows3, wallet_3, "mapped", lambda: RemappedJudge(caches.verdicts, keys7), "tính (giả định)"),
        "ba_hu_khong_seed_model_doi_ma": (rows3, wallet_3, "none", lambda: RemappedJudge(caches.verdicts, keys7), "tính (giả định)"),
        # người dùng mô phỏng giữ cờ "luôn luôn" của bộ bảy (không đặt thêm luật cho người nhận chỉ nhất quán trên ví 3 hũ)
        "ba_hu_khong_model_co_nhat_quan_cu": (rows3_old, wallet_3, "mapped", NoModelJudge, "đo"),
        "ba_hu_model_doi_ma_co_nhat_quan_cu": (rows3_old, wallet_3, "mapped", lambda: RemappedJudge(caches.verdicts, keys7), "tính (giả định)"),
    }  # fmt: skip
    results_of: dict[str, list[Any]] = {}
    for name, (rows, wallet, seed_mode, make_judge, kind) in specs.items():
        emb = OfflineEmbedder(caches.embeddings, model)
        judge = make_judge()
        res = simulate(rows, th, emb, judge, wallet=wallet, seeds=seeds_of(seed_mode))
        results_of[name] = res
        runs[name] = {
            "kind": kind,
            "seed_labels": seed_mode,
            "model_calls": getattr(judge, "calls", 0),
            "model_cache_hits": getattr(judge, "hits", 0),
            "embedding_missing": sorted(emb.missing),
            **classify_report(res),
        }
    proj = project(results_of["bay_hu_co_model"], codes3)
    runs["chieu_bay_hu_co_model_sang_ba_hu"] = {
        "kind": "tính (chiếu quyết định)",
        **classify_report(proj),
    }
    from yofina_ledger.jar_layout import DEMO_LAYOUT

    types = sim.load_type_map()
    personas_ = sorted({r["persona"] for r in rows7})
    wallets = {
        **{f"bay_hu_{p}": list(sim.persona_jars(p)) for p in personas_},
        "vi_demo": [j.code for j in DEMO_LAYOUT],
        "ba_hu": codes3,
    }
    seed_counts = {
        p: {m: len(seed_labels(p, codes3 if m != "persona" else list(sim.persona_jars(p)), m)) for m in ("persona", "mapped", "alias", "none")}
        for p in personas_
    }  # fmt: skip
    label_map = {j: to_layout(j, codes3) for j in sorted({r["truth_jar"] for r in rows7})}
    return {
        "wallet_3": [dataclasses.asdict(j) for j in wallet3.values()],
        "thresholds": {k: getattr(th, k) for k in ("auto_min_confidence", "review_min_confidence")},
        "label_map": label_map,
        "subscription_rows": sum(1 for r in rows7 if r["tx_type"] == "subscription"),
        "consistent_changed": sum(
            1 for a, b in zip(rows7, rows3, strict=True) if a["consistent"] != b["consistent"]
        ),
        "truth_3_counts": dict(Counter(r["truth_jar"] for r in rows3)),
        "seed_counts": seed_counts,
        "type_routes": type_routes(types, wallets),
        "runs": runs,
    }


def render_classify(out: dict[str, Any]) -> str:
    lines = [f"Ví 3 hũ: {[j['code'] for j in out['wallet_3']]}; ngưỡng {out['thresholds']}"]
    lines.append(
        f"Ánh xạ đáp án: {out['label_map']} (+ {out['subscription_rows']} dòng loại subscription vào nghia_vu)"
    )
    lines.append(
        f"Cờ nhất quán đổi ở {out['consistent_changed']} dòng; đáp án 3 hũ: {out['truth_3_counts']}"
    )
    lines.append(f"Nhãn seed theo chế độ: {out['seed_counts']}")
    lines.append(
        "\n| Lượt | Loại số | Seed | Tập kiểm: đúng (đã gán) | hỏi | xem lại | tự gán sai | đúng trên tổng | Mọi dòng: đúng / hỏi | model gọi/đệm trúng |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for name, r in out["runs"].items():
        t, a = r["test"], r["all"]
        lines.append(
            f"| {name} | {r['kind']} | {r.get('seed_labels', '-')} | {t['accuracy_assigned']} ({t['assigned']}) | {t['ask_rate']} ({t['ask']}) "
            f"| {t['review_rate']} | {t['silent_error_rate']} | {t['correct_end_to_end']} | {a['accuracy_assigned']} / {a['ask_rate']} "
            f"| {r.get('model_calls', '-')}/{r.get('model_cache_hits', '-')} |"
        )
    for name in ("ba_hu_khong_model", "ba_hu_model_doi_ma", "chieu_bay_hu_co_model_sang_ba_hu"):
        r = out["runs"][name]
        lines.append(f"\n{name}: ma trận nhầm (tập kiểm) {r['confusion_test']}")
        lines.append(
            f"  hỏi theo loại giao dịch (mọi dòng) {r['ask_by_tx_type_all']}; theo nhóm (tập kiểm) "
            + str({k: v["ask_rate"] for k, v in r["test_by_category"].items()})
        )
    lines.append("\nBước 0 theo ví (None = Chưa phân loại, tới luật / embedding / model):")
    for t in out["type_routes"]:
        lines.append("  " + json.dumps(t, ensure_ascii=False))
    return "\n".join(lines)


# =====================================================================================================================
# forecast
# =====================================================================================================================
MERGES: dict[str, tuple[str, ...]] = {
    "gop3": ("an_uong", "di_chuyen", "giai_tri"),
    "ba_hu": ("an_uong", "di_chuyen", "giai_tri", "mua_sam", "du_lich"),
}
VARIANTS = ("rieng", *MERGES)
FULL = "full"
LENGTHS: tuple[int | str, ...] = (47, 120, FULL)
PROB_BAND = (0.75, 0.85)


def merge_persona(p: Any, members: Sequence[str], code: str = MERGED_CODE) -> Any:
    """Persona tổng hợp với các hũ `members` cộng thành một hũ chi tiêu `code` (đặt ở chỗ hũ đầu tiên): chi từng ngày, tỷ lệ chia và số
    dư cuối ngày là tổng của các hũ thành phần; hũ khác và nghĩa vụ giữ nguyên."""
    from yofina_ml.synth.base import SynthJar

    parts = [p.jar(c) for c in members]
    merged = SynthJar(
        code,
        "spending",
        float(sum(j.split_percent for j in parts)),
        np.sum([j.spend for j in parts], axis=0).astype(np.int64),
    )
    jars: list[Any] = []
    for j in p.jars:
        if j.code not in members:
            jars.append(j)
        elif j.code == members[0]:
            jars.append(merged)
    balances = {k: v for k, v in p.balances.items() if k not in members}
    balances[code] = np.sum([p.balances[c] for c in members], axis=0)
    return dataclasses.replace(p, jars=tuple(jars), balances=balances)


def _forecast_job(job: tuple[str, str, int, str, tuple[int | str, ...], int, int, bool]):
    """Một persona, một biến thể: bản ghi dải số dư (mọi hũ) và bản ghi số dư kịch bản (hũ chi tiêu, tiết kiệm). `recal` False: tắt
    công tắc hiệu chỉnh sau Monte Carlo (không CQR, không PAV), để tách phần do bảng hiệu chỉnh học trên hũ riêng."""
    family, config, seed, variant, lengths, n_paths, step, recal = job
    from yofina_ml.backtest import recalibrate as rc
    from yofina_ml.backtest.common import HORIZON, origins
    from yofina_ml.backtest.studies import _truncate
    from yofina_ml.calibration import calibrated_config, default_calibration
    from yofina_ml.forecast import forecast_user
    from yofina_ml.synth import generate
    from yofina_ml.synth.base import build_inputs

    p = generate(family, config, seed)
    if variant != "rieng":
        p = merge_persona(p, MERGES[variant])
    ungated: dict[str, Any] = {k: {"probability_min_history_days": 0} for k in ("dense", "sparse")}
    if not recal:
        ungated["recalibrate"] = False
    base = dataclasses.replace(
        calibrated_config(), probability_enabled=True, extra={"calibration": ungated}
    )
    cal = dataclasses.replace(default_calibration(), recalibrate=recal)
    bands: list[dict[str, Any]] = []
    scen: list[dict[str, Any]] = []
    for o in origins(p.n_days, HORIZON, rc.FIRST_ORIGIN, step):
        full = build_inputs(
            p, o, HORIZON, dataclasses.replace(base, n_paths=n_paths, seed=p.seed * 1000 + o)
        )
        for length in lengths:
            inputs = full if length == FULL else _truncate(full, int(length))
            res = forecast_user(inputs)
            for jar, jf in zip(inputs.jars, res.jars, strict=True):
                s = jf.summary
                truth = p.balances[jar.code][o + 1 : o + 1 + HORIZON].astype(float)
                scale = rc._scale(jar.daily_spend_vnd)
                d30 = jf.days[HORIZON - 1]
                rec: dict[str, Any] = {
                    "variant": variant,
                    "length": str(length),
                    "family": family,
                    "jar": jar.code,
                    "kind": s.series_kind,
                    # cờ hiện % theo cổng thật (lần chạy tắt cổng để luôn có p)
                    "shown": s.series_kind != "cold_start"
                    and cal.for_kind(s.series_kind).probability_ok_at(jar.history_days),
                    "below30": float(truth[HORIZON - 1] < d30.balance_p10_vnd),
                    "above30": float(truth[HORIZON - 1] > d30.balance_p90_vnd),
                    "width30": (d30.balance_p90_vnd - d30.balance_p10_vnd) / (scale * HORIZON)
                    if scale > 0
                    else None,
                }
                for h in (7, 14, 30):
                    d = jf.days[h - 1]
                    rec[f"in{h}"] = float(d.balance_p10_vnd <= truth[h - 1] <= d.balance_p90_vnd)
                bands.append(rec)
                if jar.kind == "obligation":
                    continue
                one = dataclasses.replace(inputs, jars=(jar,))
                for r in rc._scenarios(p, o, one, res, length, HORIZON):
                    iso = cal.for_kind(r["bucket"]).p_isotonic
                    p_prod = iso(r["p"]) if cal.recalibrate and iso is not None else r["p"]
                    scen.append(
                        {
                            "variant": variant,
                            "length": str(length),
                            "family": family,
                            "jar": jar.code,
                            "bucket": r["bucket"],
                            "shown": r["shown"],
                            "p": p_prod,
                            "event": r["event"],
                            "pred_day": r["pred_day"],
                            "true_day": r["true_day"],
                        }
                    )
    return bands, scen


def _r(v: float | None, nd: int = 3) -> float | None:
    return None if v is None else round(float(v), nd)


def band_cells(bands: list[dict[str, Any]], key: str) -> dict[str, dict[str, dict[str, Any]]]:
    """{biến thể: {độ dài: {nhóm: số đo dải}}}, nhóm theo `key` (`jar` hoặc `kind`)."""
    out: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for b in bands:
        groups[(b["variant"], b["length"], b[key])].append(b)
    for (variant, length, g), sel in sorted(groups.items()):
        fams = sorted({r["family"] for r in sel})
        widths = [r["width30"] for r in sel if r["width30"] is not None]
        out[variant][length][g] = {
            "n": len(sel),
            "kind_share": {k: _r(v / len(sel)) for k, v in Counter(r["kind"] for r in sel).items()},
            "shown_share": _r(np.mean([r["shown"] for r in sel])),
            "cov7": _r(np.mean([r["in7"] for r in sel])),
            "cov14": _r(np.mean([r["in14"] for r in sel])),
            "cov30": _r(np.mean([r["in30"] for r in sel])),
            "cov30_by_family": {
                f: _r(np.mean([r["in30"] for r in sel if r["family"] == f])) for f in fams
            },
            "below_p10_30": _r(np.mean([r["below30"] for r in sel])),
            "above_p90_30": _r(np.mean([r["above30"] for r in sel])),
            "width30": _r(np.mean(widths), 2) if widths else None,
        }
    return out


def scenario_cells(scen: list[dict[str, Any]], key: str) -> dict[str, dict[str, dict[str, Any]]]:
    """{biến thể: {độ dài: {nhóm: xác suất hụt trên ca có hiện %, ngày cạn trên mọi ca}}}."""
    from yofina_ml.backtest.evaluate import reliability

    out: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for s in scen:
        groups[(s["variant"], s["length"], s[key])].append(s)
    for (variant, length, g), sel in sorted(groups.items()):
        cell: dict[str, Any] = {"n": len(sel)}
        shown = [r for r in sel if r["shown"]]
        cell["n_shown"] = len(shown)
        if shown:
            rel = reliability(shown)
            gaps = [abs(t["mean_p"] - t["freq"]) for t in rel["table"] if t["n"] >= 30]
            cell.update(
                brier=_r(rel["brier"], 4),
                brier_climatology=_r(rel["brier_climatology"], 4),
                max_gap=_r(max(gaps)) if gaps else None,
                table=[
                    f"{t['bin']}: {t['mean_p']:.2f}->{t['freq']:.2f} (n={t['n']})"
                    for t in rel["table"]
                ],
            )
        pred = [r for r in sel if r["pred_day"] is not None]
        both = [r for r in pred if r["true_day"] is not None]
        err = [abs(r["pred_day"] - r["true_day"]) for r in both]
        cell["runout_n_pred"] = len(pred)
        cell["runout_within3"] = _r(sum(e <= 3 for e in err) / len(pred)) if pred else None
        cell["runout_mae_days"] = _r(np.mean(err), 2) if err else None
        out[variant][length][g] = cell
    return out


def band_gate(cell: dict[str, Any] | None) -> bool:
    """Ô dải đạt cổng BR-31: độ phủ ngày 30 gộp và từng họ trong [0,75; 0,85] (luật của `history_gate`)."""
    if not cell:
        return False
    covs = [cell["cov30"], *cell["cov30_by_family"].values()]
    return all(v is not None and PROB_BAND[0] <= v <= PROB_BAND[1] for v in covs)


def run_forecast(
    *,
    quick: bool = False,
    workers: int | None = None,
    n_paths: int = 2000,
    recalibrate: bool = True,
    progress: bool = True,
) -> dict[str, Any]:
    from yofina_ml.backtest.common import EVAL_SEEDS
    from yofina_ml.synth import FAMILIES, config_names

    seeds = EVAL_SEEDS[:2] if quick else EVAL_SEEDS
    step = 28 if quick else 7
    jobs = [
        (fam, cfg, sd, variant, LENGTHS, n_paths, step, recalibrate)
        for variant in VARIANTS
        for fam in FAMILIES
        for cfg in config_names(fam)
        for sd in seeds
    ]
    t0 = time.time()
    n_workers = workers or min(os.cpu_count() or 1, 12)
    bands: list[dict[str, Any]] = []
    scen: list[dict[str, Any]] = []
    if n_workers > 1:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            for i, (b, s) in enumerate(pool.map(_forecast_job, jobs), 1):
                bands += b
                scen += s
                if progress:
                    print(f"  [{i}/{len(jobs)}] {time.time() - t0:.0f}s", flush=True)
    else:
        for i, job in enumerate(jobs, 1):
            b, s = _forecast_job(job)
            bands += b
            scen += s
            if progress:
                print(f"  [{i}/{len(jobs)}] {time.time() - t0:.0f}s", flush=True)
    by_jar = band_cells(bands, "jar")
    by_kind = band_cells(bands, "kind")
    gates = {
        v: {length: {g: band_gate(c) for g, c in cells.items()} for length, cells in lens.items()}
        for v, lens in by_jar.items()
    }
    return {
        "method": f"seed {list(seeds)}, hai họ, mọi cấu hình; origin từ 120 bước {step}, chân trời 30, lịch sử {list(LENGTHS)}, "
        f"{n_paths} đường; hiệu chỉnh hiện hành{'' if recalibrate else ' với công tắc recalibrate TẮT (không CQR, không PAV)'}, "
        "cổng % tắt khi chạy",
        "recalibrate": recalibrate,
        "merges": {k: list(v) for k, v in MERGES.items()},
        "rows": {"bands": len(bands), "scenarios": len(scen)},
        "seconds": round(time.time() - t0, 1),
        "band_by_jar": by_jar,
        "band_by_kind": by_kind,
        "gate_by_jar": gates,
        "scenario_by_jar": scenario_cells(scen, "jar"),
        "scenario_by_kind": scenario_cells(scen, "bucket"),
    }


def _f(v: Any, nd: int = 3) -> str:
    return (
        "-" if v is None else (f"{v:.{nd}f}".replace(".", ",") if isinstance(v, float) else str(v))
    )


def render_forecast(
    out: dict[str, Any],
    jars: Sequence[str] = ("an_uong", "di_chuyen", "giai_tri", "mua_sam", "du_lich", MERGED_CODE),
) -> str:
    lines = [out["method"], f"{out['rows']}, {out['seconds']} s", ""]
    lines.append(
        "| Biến thể | Lịch sử | Hũ | n | Loại chuỗi | Hiện % | Phủ 7 / 14 / 30 | Phủ 30 theo họ | Dưới P10 / trên P90 | Độ rộng | Cổng |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for v, lens in out["band_by_jar"].items():
        for length, cells in lens.items():
            for g in jars:
                c = cells.get(g)
                if not c:
                    continue
                fam = " / ".join(_f(x) for x in c["cov30_by_family"].values())
                kinds = ", ".join(f"{k} {_f(s, 2)}" for k, s in sorted(c["kind_share"].items()))
                lines.append(
                    f"| {v} | {length} | {g} | {c['n']} | {kinds} | {_f(c['shown_share'], 2)} | {_f(c['cov7'])} / {_f(c['cov14'])} / {_f(c['cov30'])} "
                    f"| {fam} | {_f(c['below_p10_30'])} / {_f(c['above_p90_30'])} | {_f(c['width30'], 2)} | {'đạt' if out['gate_by_jar'][v][length][g] else 'trượt'} |"
                )
    lines.append("")
    lines.append(
        "| Biến thể | Lịch sử | Nhóm loại chuỗi | n | Phủ 30 | Phủ 30 theo họ | Dưới / trên |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for v, lens in out["band_by_kind"].items():
        for length, cells in lens.items():
            for g, c in cells.items():
                fam = " / ".join(_f(x) for x in c["cov30_by_family"].values())
                lines.append(
                    f"| {v} | {length} | {g} | {c['n']} | {_f(c['cov30'])} | {fam} | {_f(c['below_p10_30'])} / {_f(c['above_p90_30'])} |"
                )
    lines.append("")
    lines.append(
        "| Biến thể | Lịch sử | Hũ | Kịch bản | Có hiện % | Brier / tần suất chung | Sai lệch lớn nhất | Ngày cạn: ca có ngày, trong ±3, sai TB |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for v, lens in out["scenario_by_jar"].items():
        for length, cells in lens.items():
            for g in jars:
                c = cells.get(g)
                if not c:
                    continue
                lines.append(
                    f"| {v} | {length} | {g} | {c['n']} | {c['n_shown']} | {_f(c.get('brier'), 4)} / {_f(c.get('brier_climatology'), 4)} "
                    f"| {_f(c.get('max_gap'))} | {c['runout_n_pred']}, {_f(c['runout_within3'])}, {_f(c['runout_mae_days'], 2)} |"
                )
    return "\n".join(lines)


# =====================================================================================================================
# pelt (minh)
# =====================================================================================================================
DEMO_SPEND_JARS = ("an_uong", "di_lai", "giai_tri")
SCENE4_CSV = REPO / "data" / "personas" / "samples" / "minh_sao_ke_2_tuan.csv"


def _load_script(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def merged_history(
    anchor: date | None = None, *, seed: int | None = None, members: Sequence[str] = DEMO_SPEND_JARS
):
    """(lịch sử hũ Ăn uống, lịch sử với chuỗi ngày gộp `members`): cùng khoản chi, mức cũ và nơi chi của hũ Ăn uống (để `plan_shift`
    thêm khoản như cảnh 4), chỉ chuỗi ngày đưa vào PELT là tổng của các hũ (ví demo sau `POST /demo/reset`)."""
    msp = _load_script("measure_scene4_pelt")
    anchor = anchor or msp.DEFAULT_ANCHOR
    own = msp.persona_history(anchor=anchor, jar=members[0], seed=seed, layout="demo")
    daily = np.sum(
        [
            msp.persona_history(anchor=anchor, jar=j, seed=seed, layout="demo").daily
            for j in members
        ],
        axis=0,
    )
    return own, dataclasses.replace(own, daily=daily)


def scene4_rows(path: Path = SCENE4_CSV) -> list[Any]:
    """Các dòng chi của tệp sao kê cảnh 4 dạng `PlannedRow` (ngày, số tiền) để cộng vào chuỗi ngày."""
    sc = _load_script("measure_scene4_pelt").load_shift_module()
    out = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            debit = (r.get("Số tiền ghi nợ") or "").replace(",", "").strip()
            if not debit:
                continue
            day = datetime.strptime(r["Ngày giao dịch"], "%d/%m/%Y").date()
            out.append(sc.PlannedRow(day, int(debit), r.get("Đối tác")))
    return out


def run_pelt(*, persona_seeds: int = 8, drift_days: int = 3) -> dict[str, Any]:
    from yofina_ml import change as ch

    msp = _load_script("measure_scene4_pelt")
    sc = msp.load_shift_module()
    params = ch.load_params()
    own, merged = merged_history()
    base_own = sc.baseline_weekly(list(own.spends), own.anchor, msp.SHIFT_WEEKS)
    weeks_own = ch.prepare_weekly(own.daily, params)
    weeks_m = ch.prepare_weekly(merged.daily, params)
    # mức chi tuần cũ của chuỗi gộp: trung vị các tuần đầy đủ trước hai tuần cuối (như `baseline_weekly`, trên tuần lịch của PELT)
    raw_m = np.asarray(weeks_m.raw, dtype=float)
    base_m = float(np.median(raw_m[: -msp.SHIFT_WEEKS]))
    raw_o = np.asarray(weeks_own.raw, dtype=float)
    grid_main = msp.grid(1.5, 4.0, 0.1)
    table_m = msp.scan(merged, params, sorted({*msp.grid(1.5, 4.0, 0.5), 2.1, 2.2, 2.3}))
    fmin_own = msp.minimal_factor(own, params)
    fmin_m = msp.minimal_factor(merged, params, factors=msp.grid(1.1, 8.0, 0.1))
    exact_own = msp.exact_threshold(
        own, params, lo=max(1.1, (fmin_own or 4.0) - 0.1), hi=fmin_own or 4.0
    )
    exact_m = (
        msp.exact_threshold(merged, params, lo=max(1.1, fmin_m - 0.1), hi=fmin_m)
        if fmin_m
        else None
    )
    rows = scene4_rows()
    scene4 = {}
    for k in range(0, drift_days + 1):
        res = {}
        for name, h in (("an_uong", own), ("gop", merged)):
            hit = msp.detect(h, rows, params, drift_days=k)
            res[name] = (
                {"old": hit.old_weekly_vnd, "new": hit.new_weekly_vnd, "held": hit.weeks_held}
                if hit
                else None
            )
        scene4[k] = res
    drift = {
        k: {
            "an_uong": msp.scan(own, params, [3.5], drift_days=k)[0]["confirmed"],
            "gop": msp.scan(merged, params, [3.5], drift_days=k)[0]["confirmed"],
        }
        for k in range(0, drift_days + 1)
    }
    seeds = {}
    for s in range(1, persona_seeds + 1):
        o, m = merged_history(seed=s)
        seeds[s] = {
            "an_uong": msp.minimal_factor(o, params, split_seeds=5),
            "gop": msp.minimal_factor(m, params, factors=msp.grid(1.1, 8.0, 0.1), split_seeds=5),
            "share_an_uong": round(float(o.daily.sum() / m.daily.sum()), 3),
            "preexisting_gop": ch.detect_confirmed(ch.prepare_weekly(m.daily, params), params)
            is not None,
        }
    file_total = sum(r.amount_vnd for r in rows)
    return {
        "params_version": params.version,
        "anchor": own.anchor.isoformat(),
        "members": list(DEMO_SPEND_JARS),
        "weekly_an_uong": [round(float(x)) for x in raw_o],
        "weekly_gop": [round(float(x)) for x in raw_m],
        "share_an_uong": round(float(own.daily.sum() / merged.daily.sum()), 3),
        "baseline_weekly_an_uong": base_own,
        "baseline_weekly_gop": round(base_m),
        "preexisting_gop": ch.detect_confirmed(weeks_m, params) is not None,
        "table_gop": table_m,
        "minimal_factor_an_uong": fmin_own,
        "exact_threshold_an_uong": exact_own,
        "minimal_factor_gop": fmin_m,
        "exact_threshold_gop": exact_m,
        "gop_level_ratio_at_min": round((base_m + (fmin_m - 1) * base_own) / base_m, 3)
        if fmin_m
        else None,
        "scene4_file": {"rows": len(rows), "total_vnd": file_total, "by_drift": scene4},
        "factor_3_5_by_drift_of_20": drift,
        "persona_seeds": seeds,
        "grid": [grid_main[0], 8.0],
    }


def render_pelt(out: dict[str, Any]) -> str:
    lines = [
        f"minh (ví demo), ngày neo {out['anchor']}, tham số {out['params_version']}; chuỗi gộp {out['members']}, Ăn uống chiếm {out['share_an_uong']}",
        f"chi tuần hũ Ăn uống: {out['weekly_an_uong']}",
        f"chi tuần chuỗi gộp:  {out['weekly_gop']}",
        f"mức tuần cũ: Ăn uống {out['baseline_weekly_an_uong']:,} ₫, gộp {out['baseline_weekly_gop']:,} ₫; chuỗi gộp tự có điểm gãy: {out['preexisting_gop']}",
        "",
        "Hệ số (theo mức cũ của Ăn uống) -> PELT trên chuỗi gộp xác nhận (20 hạt chia khoản):",
    ]
    for r in out["table_gop"]:
        lvl = f"{r['old_weekly_vnd']:,} -> {r['new_weekly_vnd']:,}" if r["old_weekly_vnd"] else "-"
        lines.append(f"  {r['factor']}: {r['confirmed']}/{r['of']}  {lvl}")
    lines += [
        f"hệ số tối thiểu: hũ riêng {out['minimal_factor_an_uong']} (mịn {out['exact_threshold_an_uong']}), chuỗi gộp {out['minimal_factor_gop']} (mịn {out['exact_threshold_gop']}); "
        f"mức gộp mới / cũ ở hệ số đó: {out['gop_level_ratio_at_min']}",
        f"tệp cảnh 4 ({out['scene4_file']['rows']} dòng, {out['scene4_file']['total_vnd']:,} ₫) theo lệch ngày: {out['scene4_file']['by_drift']}",
        f"hệ số 3,5 theo lệch ngày (số hạt trên 20): {out['factor_3_5_by_drift_of_20']}",
        f"seed persona: {out['persona_seeds']}",
    ]
    return "\n".join(lines)


# =====================================================================================================================
# pelt-synth
# =====================================================================================================================
HOLDOUT_SEEDS = (201, 202, 203, 204, 205, 206, 207, 208)
TOL_DAYS = 21


def merged_cases(
    seeds: Sequence[int], params: Any, members: Sequence[str], n_days: int = 330
) -> list[Any]:
    """`JarCase` của chuỗi gộp `members` cho mọi (họ, cấu hình, seed) có điểm gãy; tỷ lệ dịch mức tính như `build_cases`."""
    from yofina_ml import change as ch
    from yofina_ml.backtest import change_calibration as cc
    from yofina_ml.synth import FAMILIES, config_names
    from yofina_ml.synth import generate as synth_generate

    out = []
    for family in FAMILIES:
        for config in config_names(family):
            for seed in seeds:
                p = synth_generate(family, config, seed, n_days)
                if p.break_index is None:
                    continue
                daily = np.sum([p.jar(c).spend for c in members], axis=0).astype(float)
                clean = ch.winsorize_daily(daily, params)
                b = p.break_index
                pre = clean[max(0, b - 56) : b].sum() / 8.0
                post = clean[b : b + 56].sum() / 8.0
                ratio = post / pre if pre > 0 else float("inf")
                out.append(cc.JarCase(family, config, seed, MERGED_CODE, daily, b, ratio))
    return out


def _tp_events(case: Any, events: Sequence[tuple[int, date, str]]) -> bool:
    from yofina_ml.backtest import change_calibration as cc

    brk = cc.SYNTH_START + timedelta(days=case.break_index)
    for origin, when, _ in events:
        origin_day = cc.SYNTH_START + timedelta(days=origin - 1)
        if abs((when - brk).days) <= TOL_DAYS and origin_day >= brk:
            return True
    return False


def run_pelt_synth(*, quick: bool = False, workers: int | None = None) -> dict[str, Any]:
    from yofina_ml import change as ch
    from yofina_ml.backtest import change_calibration as cc

    params = ch.load_params()
    seeds = HOLDOUT_SEEDS[:2] if quick else HOLDOUT_SEEDS
    t0 = time.time()
    single = cc.build_cases(seeds, params)
    sims_single = cc._pool_map(cc._simulate_job, [(c, params, "confirm") for c in single], workers)
    out: dict[str, Any] = {
        "seeds": list(seeds),
        "params_version": params.version,
        "single_all_spending": cc.evaluate(
            single, [(e, o) for e, o, _ in sims_single], params, "confirm"
        ),
    }
    by_key = {c.key: (c, s) for c, s in zip(single, sims_single, strict=True)}
    for name, members in MERGES.items():
        cases = merged_cases(seeds, params, members)
        sims = cc._pool_map(cc._simulate_job, [(c, params, "confirm") for c in cases], workers)
        ev = cc.evaluate(cases, [(e, o) for e, o, _ in sims], params, "confirm")
        comps = [by_key[f"{c.family}/{c.config}/{c.seed}/{j}"] for c in cases for j in members]
        sub = cc.evaluate(
            [c for c, _ in comps], [(s[0], s[1]) for _, s in comps], params, "confirm"
        )
        # thay đổi thật của một hũ thành phần (tỷ lệ 8 tuần ngoài (1/1,3; 1,3)): bắt được bởi chính hũ đó, hay bởi chuỗi gộp
        merged_tp = {
            (c.family, c.config, c.seed): _tp_events(c, s[0])
            for c, s in zip(cases, sims, strict=True)
        }
        n = own_hit = merged_hit = either = 0
        by_jar: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        for comp, (evs, obs, _) in comps:
            if not cc._is_true_shift(comp.shift_ratio, cc.TRUTH_SHIFT):
                continue
            n += 1
            a = bool(obs) and _tp_events(comp, evs)
            b = merged_tp[(comp.family, comp.config, comp.seed)]
            own_hit += a
            merged_hit += b
            either += a or b
            by_jar[comp.jar][0] += 1
            by_jar[comp.jar][1] += a
            by_jar[comp.jar][2] += b
        out[name] = {
            "members": list(members),
            "merged": ev,
            "components": sub,
            "component_true_shifts": n,
            "found_by_component": own_hit,
            "found_by_merged": merged_hit,
            "found_by_either": either,
            "by_component": {
                j: {"true_shifts": v[0], "by_own": v[1], "by_merged": v[2]}
                for j, v in by_jar.items()
            },
            "merged_shift_ratios": sorted(round(c.shift_ratio, 3) for c in cases),
        }
    out["seconds"] = round(time.time() - t0, 1)
    return out


def render_pelt_synth(out: dict[str, Any]) -> str:
    keys = (
        "series_eligible",
        "series_total",
        "series_with_true_shift",
        "tp",
        "fa",
        "obs_jar_years",
        "fa_per_jar_year",
        "fa_series_share",
        "recall_any",
        "recall_big_shift",
        "delay_days_median",
    )
    lines = [f"seed {out['seeds']}, tham số {out['params_version']}, {out['seconds']} s"]
    lines.append(
        "mọi hũ chi tiêu riêng: "
        + json.dumps({k: out["single_all_spending"][k] for k in keys}, ensure_ascii=False)
    )
    for name in MERGES:
        r = out[name]
        lines.append(f"\n{name} {r['members']}")
        lines.append(
            "  chuỗi gộp:   " + json.dumps({k: r["merged"][k] for k in keys}, ensure_ascii=False)
        )
        lines.append(
            "  hũ thành phần: "
            + json.dumps({k: r["components"][k] for k in keys}, ensure_ascii=False)
        )
        lines.append(
            f"  thay đổi thật của hũ thành phần: {r['component_true_shifts']}; bắt bởi chính hũ {r['found_by_component']}, "
            f"bởi chuỗi gộp {r['found_by_merged']}, bởi một trong hai {r['found_by_either']}; theo hũ {r['by_component']}"
        )
    return "\n".join(lines)


# =====================================================================================================================
def _json_default(o: Any) -> Any:
    if isinstance(o, np.integer | np.floating):
        return o.item()
    if isinstance(o, date):
        return o.isoformat()
    if dataclasses.is_dataclass(o):
        return dataclasses.asdict(o)
    raise TypeError(type(o))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=("classify", "forecast", "pelt", "pelt-synth"))
    ap.add_argument("--out", type=Path, help="ghi số đo (JSON) vào tệp này")
    ap.add_argument(
        "--quick",
        action="store_true",
        help="forecast, pelt-synth: kiểm khói (ít seed, origin thưa)",
    )
    ap.add_argument("--workers", type=int, help="số tiến trình (mặc định: min(số CPU, 12))")
    ap.add_argument(
        "--recalibrate",
        choices=("on", "off"),
        default="on",
        help="forecast: công tắc hiệu chỉnh sau Monte Carlo (mặc định on như sản phẩm; off để tách phần của CQR/PAV)",
    )
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    # đường suy giảm có chủ đích (không embedding, không model) ghi WARNING mỗi giao dịch: tắt để bảng đọc được
    import logging

    logging.getLogger("yofina.classify").setLevel(logging.ERROR)
    if args.command == "classify":
        out = run_classify()
        text = render_classify(out)
    elif args.command == "forecast":
        out = run_forecast(
            quick=args.quick, workers=args.workers, recalibrate=args.recalibrate == "on"
        )
        text = render_forecast(out)
    elif args.command == "pelt":
        out = run_pelt()
        text = render_pelt(out)
    else:
        out = run_pelt_synth(quick=args.quick, workers=args.workers)
        text = render_pelt_synth(out)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(out, ensure_ascii=False, indent=1, default=_json_default), encoding="utf-8"
        )
        print("ghi", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
