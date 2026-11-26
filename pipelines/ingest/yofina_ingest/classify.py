"""Gán hũ cho dòng chi nạp được bằng ĐÚNG bộ phân loại phase 4 (`yofina_classify.pipeline.Classifier`), thay bộ gán riêng cũ của ingest.

Thứ tự (của `Classifier`, không viết lại ở đây): luật "luôn luôn" của người dùng > bảng `tx_type_map` > embedding (khớp chuỗi chính xác
rồi k-NN trên nhãn của chính người dùng) > model nhỏ cộng tín hiệu lặp lại cùng đối tác; ba mức tin cậy `auto`, `review`, `ask` theo
ngưỡng của `classify_defaults.json`. Dòng nạp chỉ được CHỌN SẴN (`auto_added`) khi mức là `auto`; `review` và `ask` vào hàng chờ duyệt.
Không dòng nào vào sổ cái ở bước này (chỉ `confirm_rows` có token ghi).

Khác với giao dịch trong ví, ba chỗ được nối riêng cho dòng nạp:

- **Model nhỏ**: không gọi thêm một lượt model cho mỗi dòng. Đề xuất hũ (kèm độ chắc) đã có từ lượt đọc tệp: CSV là lượt gắn nhãn theo
  lô của vai `ingest_columns` (cùng chuỗi model với vai `small` của phase 4), ảnh là lượt đọc ảnh. `ProposalJudge` trả đúng đề xuất đó
  làm `Verdict`, bộ phân loại hiệu chỉnh (`llm_cal_*`) và trộn với các bằng chứng khác như với giao dịch trong ví. Lý do: một tệp CSV tới
  500 dòng; một lượt mỗi dòng vượt giới hạn tốc độ của model và trần ngày.
- **Embedding**: chuỗi cần nhúng được gom và nhúng theo lô (tối đa 96 mỗi lời gọi Cohere) trước khi phân loại (`BatchEmbedder`). Không
  có kho nhãn (chế độ eval không DB) thì bước k-NN bị bỏ như khi model embedding lỗi (bộ phân loại suy giảm, không ném lỗi).
- **Loại giao dịch là đoán của model** (với giao dịch trong ví nó là dữ kiện): bảng loại giao dịch và đề xuất hũ của model bất đồng thì
  dòng xuống mức `review` (vào hàng chờ) thay vì tự chọn sẵn.

`jar_source` của `ingest_rows` (CHECK của 0050, enum của khối `ingest_review`) chỉ có `type_map`, `rule`, `model`, `user`: hũ do embedding
hay model nhỏ chọn đều ghi `model`.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo


def _ensure_repo_paths() -> None:
    """Trong Lambda, `yofina_classify` và `yofina_ledger` nằm ở gốc zip (`--extra` của `INGEST_BUILD_COMMAND`). Chạy từ repo (script
    `scripts/eval_ingest.py`, test) thì thêm hai thư mục nguồn của chúng vào cuối `sys.path` nếu chưa import được."""
    try:
        import yofina_classify  # noqa: F401

        import yofina_ledger  # noqa: F401
    except ImportError:
        here = Path(__file__).resolve()
        for root in here.parents:
            for rel in ("pipelines/classify", "gateway/tools/ledger"):
                p = root / rel
                if p.is_dir() and str(p) not in sys.path:
                    sys.path.append(str(p))
            if (root / "pipelines" / "classify").is_dir():
                break


_ensure_repo_paths()

from yofina_classify.model import (  # noqa: E402
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

from yofina_core.llm import (  # noqa: E402
    EMBED_INPUT_DOCUMENT,
    AllModelsFailed,
    LlmGateway,
    ModelBudgetExceeded,
)
from yofina_core.params import TxTypeInfo, fold_text  # noqa: E402
from yofina_core.pii import PiiPolicy  # noqa: E402
from yofina_core.wallet import transaction_jar, transaction_jar_chain  # noqa: E402
from yofina_ledger.classify_config import ClassifyThresholds, load_thresholds  # noqa: E402

log = logging.getLogger("yofina.ingest.classify")

#: vai embedding của `llm_defaults.json` (cùng vai bộ phân loại phase 4 dùng: `yofina_classify.adapters.EMBED_ROLE`)
EMBED_ROLE = "embedding"
#: model đề xuất hũ mà không nêu độ chắc (giữ như bộ gán cũ: dưới mọi ngưỡng tự chọn sau hiệu chỉnh)
DEFAULT_PROPOSAL_CONFIDENCE = 0.6
#: `classified_by` của bộ phân loại -> `jar_source` của dòng nạp
JAR_SOURCE_OF = {"rule": "rule", "type_map": "type_map"}
MERCHANT_KEY_MAX = 120


class LabelStore(Protocol):
    """Kho nhãn và lịch sử của MỘT người dùng mà bộ phân loại cần (Aurora ở worker; vắng ở chế độ eval)."""

    def find_exact(self, user_id: str, text_norm: str) -> list[ExactLabel]: ...
    def knn(self, user_id: str, vector: Sequence[float], k: int) -> list[Neighbor]: ...
    def history(self, user_id: str, merchants: Sequence[str]) -> dict[str, dict[str, int]]:
        """`{lower(đối tác): {mã hũ: số giao dịch chi trước đó}}` (hũ người dùng, không tính Chưa phân loại)."""
        ...

    def corrections(self, user_id: str, merchant_keys: Sequence[str]) -> dict[str, int]:
        """`{khóa đối tác: số luật 'once' (số lần người dùng tự tay đổi hũ)}`."""
        ...


@dataclass(frozen=True)
class Rule:
    """Luật `category_rules` đang áp dụng (scope always): khóa đã chuẩn hóa (`fold_text`) và hũ."""

    key: str
    jar_code: str


@dataclass(frozen=True)
class RowInput:
    """Một dòng chi cần gán hũ. Văn bản ĐÃ che PII. `proposal_*` là đề xuất của lượt model đọc tệp (có thể vắng)."""

    app_date: date
    amount_vnd: int
    counterparty: str | None
    description: str | None
    is_person: bool | None
    tx_type: str | None
    proposal_jar: str | None
    proposal_confidence: float | None


@dataclass(frozen=True)
class JarChoice:
    code: str
    confidence: float
    source: str  # rule | type_map | model
    tier: str  # auto | review | ask


def match_rule(
    rules: Sequence[Rule], counterparty: str | None, description: str | None
) -> Rule | None:
    """Luật khớp đối tác: bằng nhau, hoặc khóa (từ 4 ký tự) là cụm nguyên từ trong đối tác hay nội dung. Khóa dài nhất thắng.

    Dòng nạp không có `payee_id` hay đối tác đã chuẩn hóa như giao dịch trong ví (sao kê ghi "MBVCB.123.GRAB*TRIP..."), nên khớp theo
    cụm từ thay vì đúng `merchant_key`."""
    import re

    cp, desc = fold_text(counterparty or ""), fold_text(description or "")
    best: Rule | None = None
    for r in rules:
        if not r.key:
            continue
        hit = r.key == cp
        if not hit and len(r.key) >= 4:
            pat = re.compile(rf"(?<!\w){re.escape(r.key)}(?!\w)")
            hit = bool(pat.search(cp) or pat.search(desc))
        if hit and (best is None or len(r.key) > len(best.key)):
            best = r
    return best


class _NoLabels:
    def find_exact(self, user_id: str, text_norm: str) -> list[ExactLabel]:
        return []

    def knn(self, user_id: str, vector: Sequence[float], k: int) -> list[Neighbor]:
        return []


class _CachedLabels:
    """Khớp chính xác và k-NN có đệm trong MỘT tệp (sao kê lặp lại cùng đối tác nhiều lần): mỗi chuỗi một lần gọi DB. `BatchEmbedder`
    trả CÙNG đối tượng vector cho cùng chuỗi nên k-NN đệm theo đối tượng đó."""

    def __init__(self, store: LabelStore) -> None:
        self.store = store
        self._exact: dict[str, list[ExactLabel]] = {}
        self._knn: dict[tuple[int, int], tuple[Sequence[float], list[Neighbor]]] = {}

    def find_exact(self, user_id: str, text_norm: str) -> list[ExactLabel]:
        if text_norm not in self._exact:
            self._exact[text_norm] = self.store.find_exact(user_id, text_norm)
        return self._exact[text_norm]

    def knn(self, user_id: str, vector: Sequence[float], k: int) -> list[Neighbor]:
        key = (id(vector), k)
        hit = self._knn.get(key)
        if hit is None or hit[0] is not vector:
            hit = (vector, self.store.knn(user_id, vector, k))
            self._knn[key] = hit
        return hit[1]


class BatchEmbedder:
    """`Embedder` của bộ phân loại trên các vector đã nhúng trước theo lô. Chuỗi không có trong lô, hoặc lô lỗi, thì ném `AllModelsFailed`
    (hay `ModelBudgetExceeded`) để bộ phân loại suy giảm như khi Bedrock lỗi: bỏ bước k-NN, không làm hỏng lần nạp."""

    def __init__(self, gateway: LlmGateway | None, texts: Sequence[str]) -> None:
        self.model = ""
        self.vectors: dict[str, list[float]] = {}
        self.error: Exception | None = None
        unique = list(dict.fromkeys(t for t in texts if t))
        if gateway is None:
            self.error = AllModelsFailed(EMBED_ROLE, [("none", "no_gateway")])
            return
        if not unique:
            return
        try:
            res = gateway.embed(EMBED_ROLE, unique, input_type=EMBED_INPUT_DOCUMENT)
        except (AllModelsFailed, ModelBudgetExceeded) as exc:
            self.error = exc
            log.warning("ingest_embedding_unavailable error=%s", type(exc).__name__)
            return
        except Exception as exc:  # quyền, mạng: k-NN chỉ là một bằng chứng, lần nạp vẫn chạy tiếp
            self.error = AllModelsFailed(EMBED_ROLE, [("embed", type(exc).__name__)])
            log.warning("ingest_embedding_failed error=%s", type(exc).__name__)
            return
        self.model = res.model_id
        self.vectors = dict(zip(unique, res.vectors, strict=True))

    def embed(self, text_norm: str) -> tuple[str, list[float]]:
        vec = self.vectors.get(text_norm)
        if vec is None:
            raise self.error or AllModelsFailed(EMBED_ROLE, [("none", "not_prefetched")])
        return self.model, vec


class ProposalJudge:
    """`judge(prompt, jars)` của bộ phân loại: đề xuất hũ có sẵn từ lượt đọc tệp (không gọi model). Hũ không thuộc người dùng thì bỏ."""

    def __init__(self, jar: str | None, confidence: float | None) -> None:
        self.jar, self.confidence = jar, confidence

    def __call__(self, prompt: str, jars: Mapping[str, JarInfo]) -> Verdict:
        if self.jar is None or self.jar not in jars:
            return Verdict(None, 0.0)
        conf = DEFAULT_PROPOSAL_CONFIDENCE if self.confidence is None else float(self.confidence)
        return Verdict(self.jar, max(0.0, min(1.0, conf)))


@dataclass
class ClassifyInputs:
    """Ngữ cảnh người dùng cho một lần gán hũ (dựng một lần mỗi tệp)."""

    user_id: str
    jars: list[dict[str, Any]]
    type_map: Mapping[str, TxTypeInfo]
    rules: Sequence[Rule]
    policy: PiiPolicy
    store: LabelStore | None = None
    gateway: LlmGateway | None = None
    thresholds: ClassifyThresholds | None = None
    tz: ZoneInfo | None = None


def classify_rows(rows: Sequence[RowInput], inputs: ClassifyInputs) -> list[JarChoice | None]:
    """Hũ đề xuất cho từng dòng chi (cùng thứ tự `rows`); None khi không có ứng viên nào."""
    if not rows:
        return []
    th = inputs.thresholds or load_thresholds()
    tz = inputs.tz or ZoneInfo("UTC")
    jars = {
        j["code"]: JarInfo(
            j["code"], j["name"], str(j.get("kind") or ""), int(j.get("balance_vnd") or 0)
        )
        for j in inputs.jars
        if j.get("kind") != "system"
    }
    type_map = {
        k: TypeInfo(k, v.label, v.direction, transaction_jar(v.default_jar_code, jars, tx_type=k))
        for k, v in inputs.type_map.items()
    }
    #: mọi hũ "của" từng loại (hũ riêng rồi hũ chung), để so đề xuất hũ của model với loại nó đoán
    type_jars = {
        k: transaction_jar_chain(v.default_jar_code, tx_type=k) for k, v in inputs.type_map.items()
    }
    person_types = {k for k, v in inputs.type_map.items() if v.is_person_transfer}
    merchants = [r.counterparty for r in rows if r.counterparty]
    keys = [fold_text(m)[:MERCHANT_KEY_MAX] for m in merchants]
    history = inputs.store.history(inputs.user_id, merchants) if inputs.store and merchants else {}
    corrections = inputs.store.corrections(inputs.user_id, keys) if inputs.store and keys else {}
    labels: Any = _CachedLabels(inputs.store) if inputs.store else _NoLabels()

    prepared = []
    to_embed: list[str] = []
    for r in rows:
        is_person = bool(r.is_person) or (r.tx_type in person_types)
        rule = match_rule(inputs.rules, r.counterparty, r.description)
        info = type_map.get(r.tx_type or "")
        decided_early = (rule is not None and rule.jar_code in jars) or (
            info is not None and info.direction == "out" and info.default_jar_code in jars
        )
        masked = mask_tx(r.counterparty, r.description, is_person=is_person, policy=inputs.policy)
        # chuỗi đã có nhãn khớp chính xác thì bộ phân loại thường không cần nhúng (khớp chính xác đi trước k-NN)
        if (
            inputs.store is not None
            and not decided_early
            and masked.has_text
            and not labels.find_exact(inputs.user_id, masked.text_norm)
        ):
            to_embed.append(masked.text_norm)
        prepared.append((r, is_person, rule))
    embedder = (
        BatchEmbedder(inputs.gateway, to_embed)
        if inputs.store is not None
        else BatchEmbedder(None, [])
    )

    out: list[JarChoice | None] = []
    for i, (r, is_person, rule) in enumerate(prepared):
        key = fold_text(r.counterparty)[:MERCHANT_KEY_MAX] if r.counterparty else None
        facts = TxFacts(
            transaction_id=f"ingest-row-{i + 1}",
            user_id=inputs.user_id,
            kind="expense",
            amount_vnd=int(r.amount_vnd),
            # dòng nạp chỉ có ngày; giờ chỉ đi vào lời nhắc của model nhỏ, mà ở đây không gọi model nhỏ
            occurred_at=datetime.combine(r.app_date, time(12), tzinfo=tz).astimezone(UTC),
            app_date=r.app_date,
            tx_type=r.tx_type or "",
            funding_source="external",  # không bao giờ đổi số dư hũ: bỏ ràng buộc "hũ đích đủ số dư"
            counterparty=r.counterparty,
            note=r.description,
            payee_id=None,
            is_person=is_person,
            jar_code=None,
            in_unclassified=True,
        )
        ctx = UserContext(
            jars=jars,
            type_map=type_map,
            rule=RuleHit("merchant", rule.key, rule.jar_code) if rule else None,
            payee_auto_min=None,
            merchant_corrections=int(corrections.get(key, 0)) if key else 0,
            history=dict(history.get(r.counterparty.lower(), {})) if r.counterparty else {},
            tz=tz,
        )
        judge = ProposalJudge(r.proposal_jar, r.proposal_confidence)
        clf = Classifier(th, labels, embedder, judge, policy=inputs.policy)
        d = clf.classify(facts, ctx, degrade_on_transient=True)
        jar = d.jar or (d.candidates[0][0] if d.candidates else None)
        if jar is None or jar not in jars:
            out.append(None)
            continue
        tier, conf = d.tier, float(d.confidence)
        if (
            d.stage == "type_map"
            and judge.jar in jars
            and judge.jar != jar
            and judge.jar not in type_jars.get(r.tx_type or "", ())
        ):
            # Đề xuất hũ của model trái với loại giao dịch nó đoán: một trong hai đoán sai, nên dòng vào hàng chờ. Đề xuất là một hũ khác
            # CỦA CHÍNH loại đó (hũ chung Chi hằng ngày khi ví có hũ riêng Ăn uống, #39) thì không trái: quy tắc "hũ riêng thắng hũ chung"
            # đã chọn hũ, độ tin cậy của bảng loại giao dịch giữ nguyên dù ví có thêm hũ chung.
            tier, conf = "review", min(conf, th.review_min_confidence)
        out.append(
            JarChoice(
                code=jar,
                confidence=round(max(0.0, min(1.0, conf)), 3),
                source=JAR_SOURCE_OF.get(d.classified_by or "", "model"),
                tier=tier,
            )
        )
    return out
