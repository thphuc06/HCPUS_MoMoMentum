"""Phân loại MỘT giao dịch từ đầu đến cuối: đọc, quyết định, ghi (đường ghi của ledger), phát sự kiện.

Ghi:
- mức `auto` hoặc `review`: giao dịch được gán hũ qua `classify_write.write_auto_assign` (cộng trừ số dư bằng SQL của `write_assign_jar`),
  `classified_by` là bước đã gán, `needs_review` đúng với mức `review`; sự kiện `transaction.recorded` (loại `jar_assign`) phát SAU commit để
  dự báo của hai hũ chỉnh nhanh (và bộ "nghi" đổi hành vi chạy tiếp ở consumer dự báo);
- mức `ask` hoặc hũ đích không đủ số dư: ở lại Chưa phân loại kèm tối đa 2 gợi ý, mở hoặc cập nhật câu hỏi gộp của ngày (một câu mỗi ngày).
Giao dịch người dùng đã tự chọn hũ (không còn ở Chưa phân loại) thì bỏ qua: đây cũng là lớp idempotency thứ hai (nghiệp vụ).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from yofina_classify.model import Decision
from yofina_classify.pipeline import Classifier
from yofina_classify.repo import ClassifyRepo
from yofina_core.errors import ErrorCode, YofinaError
from yofina_ledger import events
from yofina_ledger.classify_write import (
    AlreadyResolved,
    AutoAssignResult,
    vector_literal,
    write_ask_suggestions,
    write_auto_assign,
)

log = logging.getLogger("yofina.classify.service")


@dataclass
class Outcome:
    status: str  # assigned | asked | skipped
    reason: str = ""
    tier: str | None = None
    jar: str | None = None
    confidence: float | None = None
    stage: str | None = None
    classified_by: str | None = None
    llm_called: bool = False

    def log_dict(self, transaction_id: str) -> dict[str, Any]:
        return {"msg": "classified", "transaction_id": transaction_id, **self.__dict__}


class ClassifyService:
    def __init__(
        self,
        repo: ClassifyRepo,
        classifier: Classifier,
        publisher: Any,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repo = repo
        self.classifier = classifier
        self.publisher = publisher
        self.clock = clock

    def run(
        self,
        user_id: str,
        transaction_id: str,
        *,
        trace_id: str | None = None,
        degrade_on_transient: bool = True,
    ) -> Outcome:
        loaded = self.repo.load(user_id, transaction_id)
        if loaded is None:
            return Outcome("skipped", "not_found")
        facts, ctx = loaded
        if facts.kind != "expense":
            return Outcome("skipped", "not_expense")
        if not facts.in_unclassified:
            return Outcome(
                "skipped", "already_has_jar"
            )  # người dùng đã tự chọn hũ, hoặc đã được phân loại
        d = self.classifier.classify(facts, ctx, degrade_on_transient=degrade_on_transient)
        trace = trace_id or uuid.uuid4().hex
        emb = (
            (d.embedding[0], d.embedding[1], vector_literal(d.embedding[2]))
            if d.embedding is not None
            else None
        )
        if d.assigned and d.jar is not None:
            try:
                res = write_auto_assign(
                    self.repo.db,
                    user_id,
                    transaction_id=transaction_id,
                    target_jar=d.jar,
                    classified_by=d.classified_by or "llm",
                    confidence=d.confidence,
                    needs_review=d.tier == "review",
                    trace_id=trace,
                    audit_params={
                        "transaction_id": transaction_id,
                        "jar": d.jar,
                        "stage": d.stage,
                        "tier": d.tier,
                    },
                    suggested=self._alt(d),
                    embedding=emb,
                    rule_hit=(ctx.rule.match_type, ctx.rule.key)
                    if d.stage == "rule" and ctx.rule
                    else None,
                )
            except AlreadyResolved:
                return Outcome("skipped", "already_has_jar")
            except YofinaError as exc:
                if exc.code != ErrorCode.INSUFFICIENT_FUNDS:
                    raise
                d.tier, d.note = "ask", "hu_khong_du_so_du"
                return self._ask(user_id, facts.transaction_id, facts.app_date, d, emb)
            self._publish(user_id, trace, facts, res)
            out = Outcome(
                "assigned",
                d.note,
                d.tier,
                d.jar,
                d.confidence,
                d.stage,
                d.classified_by,
                d.llm_called,
            )
            log.info(json.dumps(out.log_dict(transaction_id), ensure_ascii=False))
            return out
        return self._ask(user_id, facts.transaction_id, facts.app_date, d, emb)

    def _alt(self, d: Decision) -> list[str]:
        """Hũ thay thế cho mục `review` (đổi bằng một chạm): ứng viên kế tiếp, nếu có."""
        if d.tier != "review":
            return []
        return [j for j, _ in d.candidates if j != d.jar][:1]

    def _ask(
        self, user_id: str, transaction_id: str, app_date: Any, d: Decision, emb: Any
    ) -> Outcome:
        suggested = self.classifier.suggestions(d)
        top_conf = d.confidence if d.candidates else None
        n, total = write_ask_suggestions(
            self.repo.db,
            user_id,
            transaction_id=transaction_id,
            suggested=suggested,
            confidence=top_conf,
            ask_date=app_date,
            embedding=emb,
        )
        out = Outcome(
            "asked",
            d.note or (d.llm_error or ""),
            "ask",
            suggested[0] if suggested else None,
            top_conf,
            d.stage,
            None,
            d.llm_called,
        )
        log.info(
            json.dumps(
                {**out.log_dict(transaction_id), "pending": n, "pending_vnd": total},
                ensure_ascii=False,
            )
        )
        return out

    def _publish(self, user_id: str, trace_id: str, facts: Any, res: AutoAssignResult) -> None:
        try:
            self.publisher.publish(
                [
                    events.transaction_recorded(
                        user_id=user_id,
                        trace_id=trace_id,
                        transaction_id=res.transaction_id,
                        event_id=str(uuid.uuid4()),
                        occurred_at=self.clock(),
                        app_date=facts.app_date,
                        kind=res.kind,
                        tx_type="jar_assign",
                        funding_source=res.funding_source,
                        amount_vnd=res.amount_vnd,
                        jar_codes=[res.from_jar, res.to_jar],
                        deltas=res.deltas,
                        balances=res.balances,
                    )
                ],
                trace_id=trace_id,
            )
        except Exception:  # phát lỗi không làm hỏng phân loại đã commit (nightly bù)
            log.warning("publish_failed", exc_info=True)
