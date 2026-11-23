"""Phía ĐỌC và phản hồi của phase 3 trong Lambda ledger: biểu phí (`knowledge`), kiểm suitability (`planner`), bản ghi lượt và
phản hồi phương án (`audit`). Mixin của `LedgerService`.

Người điều phối chốt (2026-11-22): mã `audit`, `planner`, `knowledge` chạy CHUNG Lambda `yofina-ledger` (cùng lớp DB, token xác
nhận và dữ liệu tham chiếu); ba target Gateway mới cùng trỏ vào Lambda này. Logic nằm ở gói riêng `yofina_knowledge`,
`yofina_planner`, `yofina_audit`; file này chỉ nối chúng với repo và đồng hồ mô phỏng.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from yofina_audit.record import parse_turn_record
from yofina_audit.trace import build_trace_data
from yofina_core.blocks import format_instant
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.suitability import Proposal
from yofina_core.wallet import FEEDBACK_DECISIONS
from yofina_knowledge.fees import fee_schedule_data
from yofina_planner.engine import evaluate
from yofina_planner.facts import facts_from_rows
from yofina_planner.rules import cached_rules

TRACE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
BLOCK_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
OPTION_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
REASON_MAX = 200
FEEDBACK_BODY_FIELDS = frozenset(
    {"trace_id", "block_id", "option_id", "decision", "scenario_id", "reason"}
)
TRACE_TOOL = "audit___get_trace"
#: loại phương án chính là việc thực hiện khoản của kịch bản (vay Trả sau, hoặc vẫn mua đúng khoản đó). Khớp `CREDIT_OPTION_KINDS`
#: của agent (`yofina_agent.whatif`).
SCENARIO_OBLIGATION_KINDS = frozenset({"use_credit", "proceed"})


def adds_scenario_obligation(prop: Proposal) -> bool:
    """Đề xuất có làm phát sinh khoản nghĩa vụ của kịch bản không: dùng tín dụng, hoặc vẫn mua đúng khoản đó. Cùng luật với
    `yofina_agent.whatif.adds_scenario_obligation`. Phương án không mua (hoãn, bỏ, nhắc lại, chuyển bù hũ, dùng hũ khác) không thêm
    nghĩa vụ nào, nên không được cộng nghĩa vụ của kịch bản vào tỷ lệ nghĩa vụ trên thu nhập."""
    return prop.funding_source == "credit" or prop.kind in SCENARIO_OBLIGATION_KINDS


class Phase3Reads:
    """Mixin: thuộc tính dùng: repo, ref, settings, now(), _app_date()."""

    # --- knowledge ----------------------------------------------------------------------------------------
    def fee_schedule_result(
        self, user_id: str, *, product: Any = None, fee_type: Any = None
    ) -> dict[str, Any]:
        """`knowledge___get_fee_schedule`: biểu phí có cấu trúc đang hiệu lực tại ngày mô phỏng của người gọi."""
        now = self.now()
        today = self._app_date(self.repo.clock_offset(user_id), now)
        data = fee_schedule_data(self.ref, today, product=product, fee_type=fee_type)
        return {
            "status": "OK",
            "as_of": format_instant(now),
            "app_date": today.isoformat(),
            "data": data,
        }

    # --- planner ------------------------------------------------------------------------------------------
    def check_suitability_result(
        self, user_id: str, *, proposal: Any, scenario_id: Any = None
    ) -> dict[str, Any]:
        """`planner___check_suitability`: đề xuất đối chiếu bộ luật (tất định, không model). Có `scenario_id` và đề xuất thật sự
        thêm nghĩa vụ của kịch bản (`adds_scenario_obligation`) thì lấy nghĩa vụ phát sinh đã tính của kịch bản thay vì ước lượng từ
        số tiền; đề xuất không thêm nghĩa vụ (hoãn, bỏ...) thì kịch bản chỉ được kiểm tồn tại, không cộng gì."""
        if not isinstance(proposal, Mapping):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "proposal phải là một đối tượng.")
        clean = {k: v for k, v in proposal.items() if v is not None and v != ""}
        try:
            prop = Proposal.model_validate(clean, strict=False)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first.get("loc", ()))
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, f"proposal không hợp lệ ({where or 'proposal'})."
            ) from None
        if scenario_id not in (None, "") and not (
            isinstance(scenario_id, str) and UUID_RE.fullmatch(scenario_id.strip().lower())
        ):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "scenario_id phải là UUID.")
        now = self.now()
        view = self.repo.jar_view(user_id)
        user = self.repo.user_row(user_id)
        if user is None or user["monthly_salary_vnd"] is None or user["payday_day"] is None:
            raise YofinaError(
                ErrorCode.PROFILE_INCOMPLETE, "Bạn chưa khai lương và ngày nhận lương."
            )
        today = self._app_date(view.clock_offset_days, now)
        if prop.jar_code is not None:
            jar = view.jar(prop.jar_code)
            if jar is None or jar.get("kind") == "system":
                raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ bạn chọn.")
        added: int | None = None
        if scenario_id not in (None, ""):
            row = self.repo.get_scenario(user_id, str(scenario_id).strip().lower())
            if row is None:
                raise YofinaError(ErrorCode.PARAMS_INVALID, "Không tìm thấy kịch bản này.")
            cost = ((row.get("result") or {}).get("obligation_impact") or {}).get("cost") or {}
            if adds_scenario_obligation(prop) and isinstance(cost.get("item_cost_vnd"), int):
                added = int(cost["item_cost_vnd"])
        facts = facts_from_rows(
            today=today,
            user=user,
            jars=view.jars,
            obligations=self.repo.list_obligations(user_id, status="active", limit=100),
            window_days=self.settings.suitability_window_days,
        )
        verdict = evaluate(prop, facts, cached_rules(), added_obligation_vnd=added)
        return {
            "status": "OK",
            "as_of": format_instant(now),
            "app_date": today.isoformat(),
            "data": verdict.model_dump(mode="json", exclude_none=True),
        }

    # --- audit --------------------------------------------------------------------------------------------
    def trace_data(self, user_id: str, trace_id: Any, *, source_tool: str) -> dict[str, Any]:
        """`TraceData` của một lượt CỦA CHÍNH người gọi. Của người khác, không tồn tại hoặc sai dạng đều TRACE_NOT_FOUND
        như nhau (không lộ sự tồn tại; RLS cộng điều kiện `user_id`)."""
        if not isinstance(trace_id, str) or not TRACE_ID_RE.fullmatch(trace_id):
            raise YofinaError(ErrorCode.TRACE_NOT_FOUND, "Không tìm thấy lượt trả lời này.")
        row = self.repo.get_trace(user_id, trace_id)
        if row is None:
            raise YofinaError(ErrorCode.TRACE_NOT_FOUND, "Không tìm thấy lượt trả lời này.")
        now = self.now()
        today = self._app_date(self.repo.clock_offset(user_id), now)
        return build_trace_data(
            row,
            request_trace_id=trace_id,
            source_tool=source_tool,
            now=now,
            app_date=today,
        )

    def trace_result(self, user_id: str, trace_id: Any) -> dict[str, Any]:
        """Tool `audit___get_trace`."""
        if trace_id in (None, ""):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Thiếu trace_id.")
        data = self.trace_data(user_id, trace_id, source_tool=TRACE_TOOL)
        return {
            "status": "OK",
            "as_of": data["explain"]["source"]["as_of"],
            "app_date": data["explain"]["source"]["app_date"],
            "data": data,
        }

    def record_turn_result(self, user_id: str, **args: Any) -> dict[str, Any]:
        """Tool `audit___record_turn`: ghi MỘT bản ghi lượt của chính người gọi (`user_id` do interceptor ghi đè từ JWT, không
        nhận từ thân). Đã có bản ghi cùng trace thì không ghi thêm (`recorded` false). Không đụng tiền nên không qua token."""
        rec = parse_turn_record(args)
        recorded = self.repo.record_turn(user_id, rec)
        return {
            "status": "OK",
            "as_of": format_instant(self.now()),
            "data": {"trace_id": rec["trace_id"], "recorded": recorded},
        }

    def trace_response(self, user_id: str, trace_id: Any) -> dict[str, Any]:
        """`GET /traces/{trace_id}`: `TraceData`."""
        return self.trace_data(user_id, trace_id, source_tool="rest:GET /traces/{trace_id}")

    def feedback_response(self, user_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """`POST /feedback`: chấp nhận hoặc từ chối một phương án. Không đụng tiền nên KHÔNG qua token; idempotent theo
        (trace, khối, phương án): gửi lại thì cập nhật quyết định và lý do."""
        trace_id = body.get("trace_id")
        option_id = body.get("option_id")
        decision = body.get("decision")
        block_id = body.get("block_id")
        scenario_id = body.get("scenario_id")
        reason = body.get("reason")
        extra = sorted(set(body) - FEEDBACK_BODY_FIELDS)
        if extra:  # hợp đồng FeedbackRequest không có trường lạ (đặc biệt không có user_id: danh tính chỉ đến từ JWT)
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, "Trường không hợp lệ: " + ", ".join(extra)[:80]
            )
        if not isinstance(trace_id, str) or not TRACE_ID_RE.fullmatch(trace_id):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "trace_id không hợp lệ.")
        if not isinstance(option_id, str) or not OPTION_ID_RE.fullmatch(option_id):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "option_id không hợp lệ.")
        if decision not in FEEDBACK_DECISIONS:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "decision phải là accepted hoặc rejected.")
        if block_id is not None and (
            not isinstance(block_id, str) or not BLOCK_ID_RE.fullmatch(block_id)
        ):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "block_id không hợp lệ.")
        if scenario_id is not None and (
            not isinstance(scenario_id, str) or not UUID_RE.fullmatch(scenario_id)
        ):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "scenario_id phải là UUID.")
        if reason is not None and (
            not isinstance(reason, str) or not 1 <= len(reason.strip()) <= REASON_MAX
        ):
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, f"reason phải dài từ 1 đến {REASON_MAX} ký tự."
            )
        row = self.repo.upsert_feedback(
            user_id,
            trace_id=trace_id,
            block_id=block_id or "",
            option_id=option_id,
            decision=decision,
            reason=reason.strip() if isinstance(reason, str) else None,
            scenario_id=scenario_id,
        )
        return {
            "feedback_id": str(row["id"]),
            "decision": row["decision"],
            "recorded_at": format_instant(row["updated_at"]),
        }
