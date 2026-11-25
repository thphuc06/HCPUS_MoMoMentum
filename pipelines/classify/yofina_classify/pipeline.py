"""Bộ phân loại: bước 0 bảng tra loại giao dịch, bước 1 luật của người dùng, bước 2 embedding, bước 3 model nhỏ (phase 4 luồng B).

Hàm `Classifier.classify` KHÔNG chạm DB hay mạng trực tiếp: nhãn k-NN, embedding và model nhỏ đi qua ba cổng (`LabelIndex`, `Embedder`, `Judge`).
Lambda nối ba cổng với Aurora và Bedrock thật (`bootstrap.py`); bộ kiểm `evals/classification` nối với kho nhãn trong bộ nhớ và Bedrock thật,
nhưng chạy CÙNG mã quyết định này.

Thứ tự và quyết định:

1. Luật 'luôn luôn' của người dùng (`category_rules`) THẮNG bảng tra khi hai bên khác nhau (như luồng nạp dữ liệu phase 5: lời người dùng nói
   rõ hơn quy tắc chung). Luật luôn là mức `auto`.
2. Bảng tra `tx_type_map` (bước 0): hũ chuẩn của loại giao dịch, nếu người dùng có hũ đó. Độ tin cậy `type_map_confidence`; vẫn so với ngưỡng tự gán
   của người nhận (đã bị nâng sau nhiều lần sửa thì thành mức `review`).
3. Embedding: chuỗi đã chuẩn hóa và đã che; khớp chính xác nhãn trước (không tốn lời gọi nếu đủ chắc), rồi nhúng và k-NN.
4. Model nhỏ cộng tín hiệu hành vi (lặp lại cùng người nhận), trộn với bằng chứng embedding (`decide.fuse`).
5. Ràng buộc cuối: hũ đích không đủ số dư thì ở lại hỏi gộp; khoản nhỏ một lần không rõ vào hũ 'Khác' (nếu người dùng có) và không hỏi.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from yofina_classify import decide, llm_step
from yofina_classify.model import (
    Decision,
    Evidence,
    ExactLabel,
    JarInfo,
    Neighbor,
    TxFacts,
    UserContext,
    Verdict,
)
from yofina_classify.text import MaskedTx, mask_tx
from yofina_core.llm import AllModelsFailed, ModelBudgetExceeded, StructuredOutputError
from yofina_core.pii import PiiPolicy
from yofina_core.wallet import EMBEDDING_DIMENSIONS, transaction_jar
from yofina_ledger.classify_config import ClassifyThresholds

log = logging.getLogger("yofina.classify")


class LabelIndex(Protocol):
    def find_exact(self, user_id: str, text_norm: str) -> list[ExactLabel]: ...
    def knn(self, user_id: str, vector: Sequence[float], k: int) -> list[Neighbor]: ...


class Embedder(Protocol):
    def embed(self, text_norm: str) -> tuple[str, list[float]]:
        """(model, vector) của một chuỗi đã chuẩn hóa."""
        ...


class Classifier:
    def __init__(
        self,
        thresholds: ClassifyThresholds,
        labels: LabelIndex,
        embedder: Embedder,
        judge: Callable[[str, Mapping[str, JarInfo]], Verdict],
        *,
        policy: PiiPolicy | None = None,
    ) -> None:
        self.th = thresholds
        self.labels = labels
        self.embedder = embedder
        self.judge = judge
        self.policy = policy or PiiPolicy()

    # -- ngưỡng tự gán áp cho giao dịch này ---------------------------------------------------------
    def auto_threshold(self, facts: TxFacts, ctx: UserContext) -> float:
        th = self.th
        if facts.payee_id:
            return th.auto_threshold_for(ctx.payee_auto_min)
        if ctx.merchant_corrections >= th.correction_min_count:
            steps = ctx.merchant_corrections - th.correction_min_count + 1
            return min(
                th.auto_min_confidence_cap,
                th.auto_min_confidence + steps * th.auto_min_confidence_step,
            )
        return th.auto_min_confidence

    # -- điểm vào -------------------------------------------------------------------------------------
    def classify(
        self, facts: TxFacts, ctx: UserContext, *, degrade_on_transient: bool = True
    ) -> Decision:
        th = self.th
        auto_th = self.auto_threshold(facts, ctx)

        # bước 1 (luật) thắng bước 0
        if ctx.rule is not None and ctx.rule.jar_code in ctx.jars:
            return self._finish(
                facts,
                ctx,
                Decision(
                    ctx.rule.jar_code,
                    th.rule_confidence,
                    "auto",
                    "rule",
                    [(ctx.rule.jar_code, th.rule_confidence)],
                    [
                        Evidence(
                            ctx.rule.jar_code,
                            th.rule_confidence,
                            "rule",
                            "luật luôn luôn của người dùng",
                        )
                    ],
                    stage="rule",
                ),
                auto_th,
            )
        info = ctx.type_map.get(facts.tx_type)
        jar = (
            transaction_jar(info.default_jar_code, ctx.jars, tx_type=facts.tx_type)
            if info is not None and info.direction == "out" else None
        )
        if jar:
            conf = th.type_map_confidence
            return self._finish(
                facts,
                ctx,
                Decision(
                    jar,
                    conf,
                    decide.tier_of(conf, auto_th, th.review_min_confidence),
                    "type_map",
                    [(jar, conf)],
                    [Evidence(jar, conf, "type_map", f"loại {facts.tx_type}")],
                    stage="type_map",
                ),
                auto_th,
            )

        masked = mask_tx(
            facts.counterparty, facts.note, is_person=facts.is_person, policy=self.policy
        )
        evidence: list[Evidence] = []
        embedding: tuple[str, str, list[float]] | None = None
        stage = "none"

        # bước 2: embedding
        if masked.has_text:
            exact = decide.exact_evidence(
                self.labels.find_exact(facts.user_id, masked.text_norm), th
            )
            evidence.extend(e for e in exact if e.jar in ctx.jars)
            top = decide.fuse(evidence, th)
            if top and top[0][1] >= auto_th:
                stage = "embedding"
            else:
                try:
                    model, vec = self.embedder.embed(masked.text_norm)
                    if len(vec) != EMBEDDING_DIMENSIONS:
                        raise ValueError(f"embedding {len(vec)} chiều, cần {EMBEDDING_DIMENSIONS}")
                    embedding = (masked.text_norm, model, vec)
                    nbrs = [
                        n
                        for n in self.labels.knn(facts.user_id, vec, th.knn_k)
                        if n.jar_code in ctx.jars
                    ]
                    knn = [e for e in decide.knn_evidence(nbrs, th) if e.jar in ctx.jars]
                    # nhãn khớp chính xác đã vào `evidence`; k-NN bổ sung cho hũ khác hoặc củng cố
                    evidence.extend(
                        e
                        for e in knn
                        if not any(
                            x.jar == e.jar and x.detail.startswith("exact") for x in evidence
                        )
                    )
                    top = decide.fuse(evidence, th)
                    if top and top[0][1] >= auto_th:
                        stage = "embedding"
                except (AllModelsFailed, ModelBudgetExceeded) as exc:
                    if isinstance(exc, AllModelsFailed) and not degrade_on_transient:
                        raise
                    log.warning("embedding_degraded: %s", type(exc).__name__)

        # bước 3: model nhỏ + tín hiệu hành vi
        llm_called, llm_error = False, None
        if stage != "embedding":
            evidence.extend(
                e for e in decide.history_evidence(ctx.history, th) if e.jar in ctx.jars
            )
            verdict: Verdict | None = None
            prompt = self.build_prompt(facts, ctx, masked)
            try:
                llm_called = True
                verdict = self.judge(prompt, ctx.jars)
                stage = "llm"
            except AllModelsFailed:
                if not degrade_on_transient:
                    raise
                llm_error = "AllModelsFailed"
            except (ModelBudgetExceeded, StructuredOutputError) as exc:
                llm_error = type(exc).__name__
            evidence.extend(e for e in decide.llm_evidence(verdict, th) if e.jar in ctx.jars)

        fused = decide.fuse(evidence, th)
        if not fused:
            decision = Decision(None, 0.0, "ask", None, [], evidence, stage=stage)
        else:
            jar, conf = fused[0]
            decision = Decision(
                jar,
                conf,
                decide.tier_of(conf, auto_th, th.review_min_confidence),
                decide.dominant_source(evidence, jar),
                fused,
                evidence,
                stage=stage,
            )
        decision.embedding = embedding
        decision.llm_called, decision.llm_error = llm_called, llm_error
        return self._finish(facts, ctx, decision, auto_th, masked=masked)

    def build_prompt(self, facts: TxFacts, ctx: UserContext, masked: MaskedTx | None = None) -> str:
        """Thông điệp gửi model nhỏ cho giao dịch này (chỉ dữ kiện đã che và tín hiệu do code tính); bộ kiểm dùng để lưu đệm theo đầu vào."""
        masked = masked or mask_tx(
            facts.counterparty, facts.note, is_person=facts.is_person, policy=self.policy
        )
        info = ctx.type_map.get(facts.tx_type)
        local = facts.occurred_at.astimezone(ctx.tz)
        return llm_step.build_prompt(
            jars=ctx.jars,
            masked=masked,
            amount_vnd=facts.amount_vnd,
            hour_local=local.hour,
            weekday_local=local.weekday(),
            tx_type_label=info.label if info else None,
            history=ctx.history,
            note_present=bool(masked.note),
        )

    # -- ràng buộc cuối -------------------------------------------------------------------------------
    def _finish(
        self,
        facts: TxFacts,
        ctx: UserContext,
        d: Decision,
        auto_th: float,
        *,
        masked: MaskedTx | None = None,
    ) -> Decision:
        th = self.th
        # hũ đích không đủ số dư (chi từ hũ): không tự gán được, hỏi gộp
        if (
            d.assigned
            and d.jar is not None
            and facts.funding_source == "jar"
            and ctx.jars[d.jar].balance_vnd < facts.amount_vnd
        ):
            d.note = "hu_khong_du_so_du"
            d.tier = "ask"
        # khoản nhỏ một lần không rõ: vào hũ 'Khác' (nếu có), không hỏi
        if d.tier == "ask" and self._is_small_one_off(facts, ctx):
            other = ctx.jars[th.small_one_off_jar_code]
            if facts.funding_source != "jar" or other.balance_vnd >= facts.amount_vnd:
                d.jar = other.code
                d.tier = "auto"
                d.classified_by = decide.dominant_source(d.evidence, d.jar) if d.evidence else "llm"
                d.note = "khoan_nho_mot_lan"
        # hỏi gộp: bổ sung hũ chuẩn của loại giao dịch làm gợi ý nếu còn thiếu
        if d.tier == "ask":
            info = ctx.type_map.get(facts.tx_type)
            default = transaction_jar(info.default_jar_code, ctx.jars, tx_type=facts.tx_type) if info else None
            if default and all(j != default for j, _ in d.candidates):
                d.candidates.append((default, 0.0))
        return d

    def _is_small_one_off(self, facts: TxFacts, ctx: UserContext) -> bool:
        th = self.th
        return (
            facts.kind == "expense"
            and th.small_one_off_jar_code in ctx.jars
            and facts.amount_vnd <= th.small_one_off_max_vnd
            and sum(ctx.history.values()) == 0
        )

    # -- gợi ý cho hỏi gộp ---------------------------------------------------------------------------
    def suggestions(self, d: Decision) -> list[str]:
        """Tối đa `suggestions_max` mã hũ, không trùng, theo thứ tự ứng viên."""
        out: list[str] = []
        for jar, _ in d.candidates:
            if jar not in out:
                out.append(jar)
            if len(out) >= self.th.suggestions_max:
                break
        return out
