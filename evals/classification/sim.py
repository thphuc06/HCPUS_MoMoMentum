"""Mô phỏng trực tuyến của bộ kiểm phân hũ: chạy ĐÚNG mã quyết định của Lambda (`yofina_classify.pipeline.Classifier`) trên giao dịch có nhãn.

Khác Lambda ở ba cổng (và chỉ ba): kho nhãn k-NN trong bộ nhớ (numpy, cùng phép cosine với `app_knn_labeled`), embedding và model nhỏ có
lưu đệm (gọi Bedrock thật, hoặc bản giả ở chế độ khô, xem `fakes.py`), và sổ cái mô phỏng (lịch sử cùng người nhận, luật, số lần sửa).

Người dùng mô phỏng HỢP TÁC và biết đáp án (`truth_jar`):
- mức `auto` đúng: không làm gì; mức `review`: bấm "đúng rồi" (nếu đúng) hoặc sửa (nếu sai) -> thêm nhãn k-NN nguồn `user`;
- mức `ask`: trả lời đúng hũ -> thêm nhãn;
- chọn "luôn luôn" (luật) khi cửa hàng hoặc người nhận có hũ nhất quán (`consistent`), không thì "chỉ lần này" (đếm `once` cho đối tác);
- sửa một lần gán TỰ ĐỘNG sai thì nâng ngưỡng tự gán riêng của người nhận (hoặc đếm sửa của đối tác), đúng công thức của `classify_write`.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for extra in ("libs/yofina_core/src", "gateway/tools/ledger", "pipelines/classify"):
    p = str(ROOT / extra)
    if p not in sys.path:
        sys.path.insert(0, p)

from yofina_classify.model import (  # noqa: E402
    Decision,
    ExactLabel,
    JarInfo,
    Neighbor,
    RuleHit,
    TxFacts,
    TypeInfo,
    UserContext,
    Verdict,
)
from yofina_classify.pipeline import Classifier  # noqa: E402
from yofina_classify.text import mask_tx  # noqa: E402

from yofina_core.params import fold_text  # noqa: E402
from yofina_core.pii import PiiPolicy  # noqa: E402
from yofina_ledger.classify_config import ClassifyThresholds  # noqa: E402

DATASET = ROOT / "evals" / "classification" / "dataset.jsonl"
SPECS = ROOT / "data" / "personas" / "specs"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")
BIG_BALANCE = 10**9


def load_dataset(path: Path = DATASET) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def split_of(rows: list[dict[str, Any]], frac: float = 0.5) -> dict[str, str]:
    """id -> `calibration` (nửa đầu theo thời gian của mỗi persona) hoặc `test` (nửa sau)."""
    out: dict[str, str] = {}
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by[r["persona"]].append(r)
    for items in by.values():
        items.sort(key=lambda r: r["seq"])
        cut = int(len(items) * frac)
        for i, r in enumerate(items):
            out[r["id"]] = "calibration" if i < cut else "test"
    return out


def load_type_map() -> dict[str, TypeInfo]:
    """Bảng tra loại giao dịch từ `db/seed/tx_type_map.sql` (cùng dữ liệu seed của sản phẩm)."""
    sql = (ROOT / "db" / "seed" / "tx_type_map.sql").read_text(encoding="utf-8")
    out: dict[str, TypeInfo] = {}
    for m in re.finditer(
        r"^\s*\('([a-z_]+)',\s*'([^']*)',\s*'(\w+)',\s*(NULL|'[a-z_]+'),", sql, re.M
    ):
        tx, label, direction, jar = m.groups()
        out[tx] = TypeInfo(tx, label, direction, None if jar == "NULL" else jar.strip("'"))
    return out


def persona_jars(persona: str, extra: Sequence[JarInfo] = ()) -> dict[str, JarInfo]:
    """Hũ của persona theo spec; `extra` là hũ thêm (ví dụ hũ 'Khác' 0%) xếp sau cùng như `sort_order` lớn nhất của bảng `jars`.

    Hũ thêm trùng mã với hũ có sẵn của persona thì giữ bản của persona."""
    spec = json.loads((SPECS / f"{persona}.json").read_text(encoding="utf-8"))
    jars = {j["code"]: JarInfo(j["code"], j["name"], j["kind"], BIG_BALANCE) for j in spec["jars"]}
    for j in extra:
        jars.setdefault(j.code, j)
    return jars


def seed_texts(persona: str) -> list[tuple[str, str]]:
    """[(chuỗi đã chuẩn hóa, hũ)] của nhãn seed (cùng nguồn với `build_seed_labels.py`)."""
    sys.path.insert(0, str(Path(__file__).parent))
    import build_seed_labels

    return build_seed_labels.normalized_labels(persona)


# --- kho nhãn trong bộ nhớ -----------------------------------------------------------------------------------------------
class MemoryLabelIndex:
    """Cổng `LabelIndex` trong bộ nhớ: khớp chính xác (mới nhất trước) và k-NN cosine của MỘT persona."""

    def __init__(self) -> None:
        self.rows: list[
            tuple[str, str, str, np.ndarray]
        ] = []  # text_norm, jar, source, unit vector
        self.last_knn: list[Neighbor] = []

    @staticmethod
    def _unit(vec: Any) -> np.ndarray:
        v = np.asarray(vec, dtype=np.float64)
        n = np.linalg.norm(v)
        return v / n if n else v

    def add(self, text_norm: str, jar: str, source: str, vec: Any) -> None:
        # như UNIQUE (user_id, text_norm, jar_code): cùng chuỗi và hũ thì thay (mới nhất)
        self.rows = [r for r in self.rows if not (r[0] == text_norm and r[1] == jar)]
        self.rows.append((text_norm, jar, source, self._unit(vec)))

    def find_exact(self, user_id: str, text_norm: str) -> list[ExactLabel]:
        hits = [r for r in reversed(self.rows) if r[0] == text_norm][:5]
        return [ExactLabel(r[1], r[2], i) for i, r in enumerate(hits)]

    def knn(self, user_id: str, vector: Any, k: int) -> list[Neighbor]:
        if not self.rows:
            self.last_knn = []
            return []
        q = self._unit(vector)
        mat = np.stack([r[3] for r in self.rows])
        sims = mat @ q
        order = np.argsort(-sims)[:k]
        self.last_knn = [Neighbor(self.rows[i][1], float(sims[i]), self.rows[i][2]) for i in order]
        return list(self.last_knn)


@dataclass
class Caches:
    """Đệm theo đầu vào: embedding (chuỗi chuẩn hóa -> vector) và phán quyết model nhỏ (băm thông điệp -> kết quả)."""

    embeddings: dict[str, list[float]] = field(default_factory=dict)
    verdicts: dict[str, dict[str, Any]] = field(default_factory=dict)


class CachedEmbedder:
    def __init__(self, caches: Caches, model: str, live: Any | None = None) -> None:
        self.caches, self.model, self.live = caches, model, live

    def embed(self, text_norm: str) -> tuple[str, list[float]]:
        if text_norm not in self.caches.embeddings:
            if self.live is None:
                raise KeyError(f"chưa có embedding đệm cho {text_norm!r}")
            _, vecs = self.live.embed_many([text_norm])
            self.caches.embeddings[text_norm] = vecs[0]
        return self.model, self.caches.embeddings[text_norm]


def prompt_key(prompt: str) -> str:
    from yofina_classify.llm_step import SYSTEM

    return hashlib.sha256((SYSTEM + "\n" + prompt).encode("utf-8")).hexdigest()[:24]


class CachedJudge:
    def __init__(self, caches: Caches, live: Any | None = None, *, strict: bool = False) -> None:
        self.caches, self.live, self.strict = caches, live, strict
        self.calls = 0

    def __call__(self, prompt: str, jars: Any) -> Verdict:
        key = prompt_key(prompt)
        if key not in self.caches.verdicts:
            if self.live is None:
                if self.strict:
                    raise KeyError("chưa có phán quyết đệm cho thông điệp này")
                from yofina_core.llm import ModelBudgetExceeded

                raise ModelBudgetExceeded("không có model (chế độ ngoại tuyến)", role="small")
            v = self.live(prompt, jars)
            self.calls += 1
            self.caches.verdicts[key] = {
                "jar": v.jar_code,
                "conf": v.confidence,
                "runner": v.runner_up,
            }
        c = self.caches.verdicts[key]
        return Verdict(
            c["jar"] if c["jar"] in jars else None,
            float(c["conf"]),
            c["runner"] if c["runner"] in jars else None,
        )


# --- sổ cái mô phỏng của MỘT persona ---------------------------------------------------------------------------------------
class PersonaState:
    def __init__(self, persona: str, th: ClassifyThresholds) -> None:
        self.persona, self.th = persona, th
        self.labels = MemoryLabelIndex()
        self.history: dict[str, Counter[str]] = defaultdict(Counter)
        self.rules: dict[str, str] = {}
        self.payee_corr: Counter[str] = Counter()
        self.payee_auto_min: dict[str, float] = {}
        self.merchant_once: Counter[str] = Counter()

    @staticmethod
    def merchant_key(row: dict[str, Any]) -> str | None:
        return fold_text(row["counterparty"])[:120] if row.get("counterparty") else None

    def key_of(self, row: dict[str, Any]) -> str | None:
        return (
            f"payee:{row['payee_key']}"
            if row.get("payee_key")
            else (f"merchant:{row['counterparty'].lower()}" if row.get("counterparty") else None)
        )

    def context(
        self, row: dict[str, Any], jars: dict[str, JarInfo], types: dict[str, TypeInfo]
    ) -> UserContext:
        key = self.key_of(row)
        rule_key = (
            f"payee:{row['payee_key']}"
            if row.get("payee_key")
            else (f"merchant:{self.merchant_key(row)}" if self.merchant_key(row) else None)
        )
        rule = (
            RuleHit(
                "payee" if row.get("payee_key") else "merchant",
                rule_key or "",
                self.rules[rule_key],
            )
            if (rule_key and rule_key in self.rules)
            else None
        )
        return UserContext(
            jars=jars,
            type_map=types,
            rule=rule,
            payee_auto_min=self.payee_auto_min.get(row["payee_key"])
            if row.get("payee_key")
            else None,
            merchant_corrections=0
            if row.get("payee_key")
            else self.merchant_once[self.merchant_key(row) or ""],
            history=dict(self.history[key]) if key else {},
            tz=TZ,
        )

    def feedback(self, row: dict[str, Any], d: Decision) -> None:
        """Người dùng mô phỏng phản hồi (xem docstring module), rồi giao dịch vào lịch sử với hũ đúng."""
        truth = row["truth_jar"]
        th = self.th
        wrong_auto = d.assigned and d.jar != truth
        touched = (not d.assigned) or wrong_auto or d.tier == "review"
        if touched and d.embedding is not None:
            text_norm, _, vec = d.embedding
            self.labels.add(text_norm, truth, "user", vec)
        always = touched and bool(row.get("consistent"))
        if always:
            k = (
                f"payee:{row['payee_key']}"
                if row.get("payee_key")
                else (f"merchant:{self.merchant_key(row)}" if self.merchant_key(row) else None)
            )
            if k:
                self.rules[k] = truth
        elif touched and not row.get("payee_key") and self.merchant_key(row):
            self.merchant_once[self.merchant_key(row)] += 1  # luật `once` ghi lại lần xử lý tay
        if wrong_auto and row.get("payee_key"):
            p = row["payee_key"]
            self.payee_corr[p] += 1
            if self.payee_corr[p] >= th.correction_min_count:
                self.payee_auto_min[p] = min(
                    th.auto_min_confidence_cap,
                    self.payee_auto_min.get(p, th.auto_min_confidence)
                    + th.auto_min_confidence_step,
                )
        key = self.key_of(row)
        if key:
            self.history[key][truth] += 1


def facts_of(row: dict[str, Any]) -> TxFacts:
    at = datetime.fromisoformat(row["occurred_at"])
    return TxFacts(
        transaction_id=row["id"],
        user_id=f"eval-{row['persona']}",
        kind="expense",
        amount_vnd=int(row["amount_vnd"]),
        occurred_at=at,
        app_date=at.date(),
        tx_type=row["tx_type"],
        funding_source="jar",
        counterparty=row.get("counterparty"),
        note=row.get("note"),
        payee_id=f"payee-{row['payee_key']}" if row.get("payee_key") else None,
        is_person=bool(row.get("is_person")),
        jar_code=None,
        in_unclassified=True,
    )


@dataclass
class Result:
    row: dict[str, Any]
    decision: Decision
    split: str


def seed_state(state: PersonaState, caches: Caches, embedder: CachedEmbedder) -> int:
    """Nhãn seed của persona: nhúng (đệm) rồi nạp vào kho nhãn nguồn `seed`."""
    n = 0
    for text, jar in seed_texts(state.persona):
        _, vec = embedder.embed(text)
        state.labels.add(text, jar, "seed", vec)
        n += 1
    return n


def prefetch_texts(rows: list[dict[str, Any]]) -> list[str]:
    """Mọi chuỗi chuẩn hóa cần nhúng: nhãn seed của ba persona và chuỗi của từng giao dịch (để gom lô, tiết kiệm lời gọi)."""
    texts: set[str] = set()
    for p in {r["persona"] for r in rows}:
        texts.update(t for t, _ in seed_texts(p))
    policy = PiiPolicy()
    for r in rows:
        m = mask_tx(
            r.get("counterparty"), r.get("note"), is_person=bool(r.get("is_person")), policy=policy
        )
        if m.has_text:
            texts.add(m.text_norm)
    return sorted(texts)


def run_sim(
    rows: list[dict[str, Any]],
    th: ClassifyThresholds,
    caches: Caches,
    embedder: CachedEmbedder,
    judge: CachedJudge,
    extra_jars: Sequence[JarInfo] = (),
) -> list[Result]:
    types = load_type_map()
    splits = split_of(rows)
    results: list[Result] = []
    for persona in sorted({r["persona"] for r in rows}):
        jars = persona_jars(persona, extra_jars)
        state = PersonaState(persona, th)
        seed_state(state, caches, embedder)
        clf = Classifier(th, state.labels, embedder, judge)
        for row in sorted((r for r in rows if r["persona"] == persona), key=lambda r: r["seq"]):
            ctx = state.context(row, jars, types)
            d = clf.classify(facts_of(row), ctx)
            results.append(Result(row, d, splits[row["id"]]))
            state.feedback(row, d)
    return results


def warm_prompts(
    rows: list[dict[str, Any]],
    th: ClassifyThresholds,
    embedder: CachedEmbedder,
    extra_jars: Sequence[JarInfo] = (),
) -> list[str]:
    """Thông điệp model nhỏ của MỌI giao dịch (lịch sử chỉ theo đáp án nên không phụ thuộc quyết định): để gọi một lượt, lưu đệm."""
    types = load_type_map()
    prompts: list[str] = []
    for persona in sorted({r["persona"] for r in rows}):
        jars = persona_jars(persona, extra_jars)
        state = PersonaState(persona, th)
        clf = Classifier(th, state.labels, embedder, lambda p, j: Verdict(None, 0.0))
        for row in sorted((r for r in rows if r["persona"] == persona), key=lambda r: r["seq"]):
            ctx = state.context(row, jars, types)
            if row["tx_type"] not in types or types[row["tx_type"]].default_jar_code not in jars:
                prompts.append(clf.build_prompt(facts_of(row), ctx))
            key = state.key_of(row)
            if key:
                state.history[key][row["truth_jar"]] += 1
    return prompts


def small_one_off_eligible(rows: list[dict[str, Any]], th: ClassifyThresholds) -> set[str]:
    """id của giao dịch thỏa điều kiện KHÔNG phụ thuộc model của luật 'khoản nhỏ một lần' (`Classifier._is_small_one_off`): chi, số tiền
    không quá `small_one_off_max_vnd`, chưa có giao dịch trước cùng người nhận hoặc đối tác. Lịch sử chỉ theo đáp án (như `run_sim`) nên tập này
    cố định: luật chỉ có thể đổi mục hỏi gộp NẰM TRONG tập này, bất kể model trả gì."""
    out: set[str] = set()
    for persona in sorted({r["persona"] for r in rows}):
        state = PersonaState(persona, th)
        for row in sorted((r for r in rows if r["persona"] == persona), key=lambda r: r["seq"]):
            key = state.key_of(row)
            seen = sum(state.history[key].values()) if key else 0
            if int(row["amount_vnd"]) <= th.small_one_off_max_vnd and seen == 0:
                out.add(row["id"])
            if key:
                state.history[key][row["truth_jar"]] += 1
    return out


# --- chỉ số ---------------------------------------------------------------------------------------------------------------
def metrics(results: list[Result]) -> dict[str, Any]:
    n = len(results)
    assigned = [r for r in results if r.decision.assigned]
    auto = [r for r in assigned if r.decision.tier == "auto"]
    review = [r for r in assigned if r.decision.tier == "review"]
    ask = [r for r in results if not r.decision.assigned]
    ok = lambda rs: sum(1 for r in rs if r.decision.jar == r.row["truth_jar"])  # noqa: E731

    def rate(a: int, b: int) -> float | None:
        return round(a / b, 4) if b else None

    by_cat: dict[str, dict[str, Any]] = {}
    for cat in sorted({r.row["category"] for r in results}):
        rs = [r for r in results if r.row["category"] == cat]
        a = [r for r in rs if r.decision.assigned]
        by_cat[cat] = {
            "n": len(rs),
            "accuracy_assigned": rate(ok(a), len(a)),
            "ask_rate": rate(len(rs) - len(a), len(rs)),
        }
    return {
        "n": n,
        "assigned": len(assigned),
        "auto": len(auto),
        "review": len(review),
        "ask": len(ask),
        "accuracy_assigned": rate(ok(assigned), len(assigned)),
        "accuracy_auto": rate(ok(auto), len(auto)),
        "accuracy_review": rate(ok(review), len(review)),
        "ask_rate": rate(len(ask), n),
        "review_rate": rate(len(review), n),
        "correct_end_to_end": rate(ok(assigned), n),
        "silent_error_rate": rate(len(auto) - ok(auto), n),
        "by_category": by_cat,
    }


def confusion(results: list[Result]) -> dict[str, dict[str, int]]:
    m: dict[str, Counter[str]] = defaultdict(Counter)
    for r in results:
        m[r.row["truth_jar"]][r.decision.jar if r.decision.assigned else "HOI"] += 1
    return {t: dict(c) for t, c in sorted(m.items())}


def errors(results: list[Result], limit: int = 25) -> list[dict[str, Any]]:
    out = []
    for r in results:
        if r.decision.assigned and r.decision.jar != r.row["truth_jar"]:
            out.append(
                {
                    "id": r.row["id"],
                    "category": r.row["category"],
                    "counterparty": r.row.get("counterparty"),
                    "note": r.row.get("note"),
                    "truth": r.row["truth_jar"],
                    "predicted": r.decision.jar,
                    "tier": r.decision.tier,
                    "confidence": round(r.decision.confidence, 3),
                    "stage": r.decision.stage,
                }
            )
    out.sort(key=lambda e: -e["confidence"])
    return out[:limit]
