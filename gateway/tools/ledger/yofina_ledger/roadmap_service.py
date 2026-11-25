"""Phía ledger của lộ trình (phase 4, F5): tool Gateway `planner___save_roadmap`, `planner___get_roadmap`, `planner___optimize_allocation`
(proxy) và logic của tám REST `/roadmap*` (`roadmap_rest.py` chỉ phân tuyến và kiểm đầu vào).

Quyết định giữ nguyên từ hợp đồng (file phase 4, "Quyết định hợp đồng phase 4"):
- Lưu và đổi trạng thái lộ trình KHÔNG đổi số dư nên KHÔNG qua token (như `POST /feedback`). Bù lại Lambda chạy lại `check_suitability` cho
  từng bước khi lưu (và khi sửa một bước): bước vi phạm mức block thì `ROADMAP_INVALID`, không lưu (quyết định 16).
- Hành động đổi tiền của một bước (`action`) vẫn đi qua `POST /confirmations` rồi `POST /actions`; chấp nhận một bước không thực hiện nó.
- Mọi thao tác đổi trạng thái ghi `audit_events` và một dòng `feedback`; sửa một bước lưu bản MỚI `active` (lý do `step_edited`), không gọi
  model, không sinh lại toàn bộ; sinh lại chạy nền qua `roadmap_jobs` và sự kiện `roadmap.regeneration_requested` phát SAU commit.
- `planner___optimize_allocation` là proxy mỏng sang Lambda forecast (N1: scipy nằm ở đó, không nằm ở zip ledger).

Không sửa được `service.py` nên lớp này đứng cạnh `LedgerService` (cùng repo, đồng hồ, cấu hình, bus sự kiện): `roadmap_ops(service)`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from yofina_core.blocks import (
    block_to_wire,
    build_roadmap,
    build_roadmap_diff,
    format_instant,
)
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.pii import mask_pii
from yofina_core.roadmap import status_for_new_version
from yofina_core.wallet import (
    FEEDBACK_DECISIONS,
    ROADMAP_DECISIONS,
    ROADMAP_VERSION_DECISIONS,
    ROADMAP_WHICH,
)
from yofina_ledger import events
from yofina_ledger import roadmap_logic as rl
from yofina_ledger.roadmap_repo import RoadmapRepo
from yofina_planner.facts import SuitabilityFacts, facts_from_rows
from yofina_planner.rules import cached_rules, rules_version

NO_ROADMAP = "Bạn chưa có lộ trình nào. Hãy nhờ Yofina lập một lộ trình."
NO_VERSION = "Không có phiên bản lộ trình này."
NO_PROPOSED = "Hiện không có bản lộ trình nào đang chờ bạn chọn."
NO_STEP = "Không có bước này trong phiên bản."
NO_JOB = "Không tìm thấy lần sinh lại này."
NOTE_MAX = 200
REASON_MAX = 200
ALIVE = ("active", "proposed")
VERSION_FEEDBACK = {"adopt": "accepted", "keep_previous": "rejected"}
_PROFILE_MSG = "Bạn chưa khai lương và ngày nhận lương."


def _masked_reason(reason: str | None) -> str | None:
    """Lý do người dùng gõ, đã che PII và cắt theo cột `feedback.reason` (1..200 ký tự; thẻ giữ chỗ có thể dài hơn chữ gốc)."""
    text = reason.strip() if reason else ""
    return mask_pii(text).text[:REASON_MAX] if text else None


def _ok(now: datetime, today: date, data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "OK",
        "as_of": format_instant(now),
        "app_date": today.isoformat(),
        "data": dict(data),
    }


@dataclass(frozen=True)
class Context:
    """Dữ kiện của một lần gọi: giờ, ngày mô phỏng và (khi cần kiểm luật) dữ kiện suitability."""

    now: datetime
    today: date
    jar_kinds: dict[str, str]
    jar_names: dict[str, str]
    facts: SuitabilityFacts | None


class RoadmapOps:
    def __init__(self, service: Any, repo: RoadmapRepo | None = None) -> None:
        self.svc = service
        self.repo: RoadmapRepo = repo or RoadmapRepo(service.repo.db)

    # --- ngữ cảnh -------------------------------------------------------------------------------------------
    def _today(self, user_id: str, now: datetime) -> date:
        return self.svc._app_date(self.svc.repo.clock_offset(user_id), now)

    def _context(self, user_id: str, *, with_facts: bool) -> Context:
        """Giờ, ngày mô phỏng, hũ của người dùng (không kể hũ hệ thống) và (với `with_facts`) dữ kiện cho luật suitability. Chưa khai
        lương và ngày nhận thì PROFILE_INCOMPLETE (cùng quy tắc `check_suitability`)."""
        svc = self.svc
        now = svc.now()
        view = svc.repo.jar_view(user_id)
        today = svc._app_date(view.clock_offset_days, now)
        jars = [j for j in view.jars if j.get("kind") != "system"]
        facts = None
        if with_facts:
            user = svc.repo.user_row(user_id)
            if user is None or user["monthly_salary_vnd"] is None or user["payday_day"] is None:
                raise YofinaError(ErrorCode.PROFILE_INCOMPLETE, _PROFILE_MSG)
            facts = facts_from_rows(
                today=today,
                user=user,
                jars=view.jars,
                obligations=svc.repo.list_obligations(user_id, status="active", limit=100),
                window_days=svc.settings.suitability_window_days,
            )
        return Context(
            now=now,
            today=today,
            jar_kinds={j["code"]: j["kind"] for j in jars},
            jar_names={j["code"]: j["name"] for j in jars},
            facts=facts,
        )

    def _basis(self, user_id: str, ctx: Context) -> dict[str, Any]:
        """`basis` của lộ trình: độ tươi và độ tin cậy của lần chạy dự báo mới nhất (cùng cách tính `forecast_meta` của Tổng quan).
        Chưa có dự báo thì không lập được lộ trình (FORECAST_UNAVAILABLE): mọi số của lộ trình dựa vào dự báo."""
        from yofina_ledger import convert

        summaries = self.svc.repo.forecast_summaries(user_id)
        if not summaries:
            raise YofinaError(
                ErrorCode.FORECAST_UNAVAILABLE,
                "Chưa có dự báo nên chưa lập được lộ trình. Dự báo được tính mỗi đêm và khi có giao dịch, thử lại sau ít phút.",
            )
        latest = max(summaries, key=lambda s: (str(s["computed_at"]), str(s["run_id"])))
        computed = convert.to_instant(latest["computed_at"])
        assert computed is not None
        basis: dict[str, Any] = {
            "computed_at": format_instant(computed),
            "stale": bool(self.svc._is_stale(latest, ctx.today, computed, ctx.now)),
            "confidence_band": latest["confidence_label"],
            "is_initial_estimate": bool(latest["is_initial_estimate"]),
            "history_days": int(latest["history_days"]),
        }
        if latest.get("data_coverage") is not None:
            basis["coverage"] = float(latest["data_coverage"])
        return basis

    def _block(
        self, ctx: Context, data: Mapping[str, Any], trace_id: str, source_tool: str
    ) -> dict[str, Any]:
        return block_to_wire(
            build_roadmap(
                data=data,
                trace_id=trace_id,
                source_tool=source_tool,
                as_of=ctx.now,
                app_date=ctx.today,
            )
        )

    @staticmethod
    def _need_row(row: Mapping[str, Any] | None, message: str) -> Mapping[str, Any]:
        if row is None:
            raise YofinaError(ErrorCode.ROADMAP_NOT_FOUND, message)
        return row

    # --- tool: planner___optimize_allocation (proxy N1) ---------------------------------------------------------
    def optimize_allocation_result(self, user_id: str, **args: Any) -> dict[str, Any]:
        """Chuyển nguyên văn sang Lambda forecast (`op optimize_allocation`) và trả nguyên văn phong bì của nó. Chưa cấu hình Lambda
        forecast hoặc lỗi gọi thì FORECAST_UNAVAILABLE; ledger không tự giải bài toán và không đoán số."""
        forecast = getattr(self.svc, "forecast", None)
        if forecast is None:
            raise YofinaError(
                ErrorCode.FORECAST_UNAVAILABLE,
                "Chưa tính được phân bổ lúc này, thử lại sau ít phút.",
            )
        clean = {k: v for k, v in args.items() if v is not None}
        return forecast.optimize_allocation(user_id, clean)

    # --- tool: planner___save_roadmap -------------------------------------------------------------------------------
    def save_roadmap_result(self, user_id: str, *, trace_id: str, **args: Any) -> dict[str, Any]:
        """Lưu MỘT phiên bản mới từ bản nháp của agent. Chạy lại luật suitability cho từng bước (vi phạm mức block thì
        ROADMAP_INVALID, không lưu). Phiên bản, trạng thái, `reason.text`, `headline`, `counts`, `basis`, `rules_version` do đây điền.
        Lý do `step_edited` chỉ có ở REST sửa bước của người dùng: agent dùng nó sẽ tự đặt bản `active` thay người dùng."""
        draft = rl.parse_draft(args)
        if draft.reason_code == "step_edited":
            raise YofinaError(
                ErrorCode.ROADMAP_INVALID,
                "Lý do step_edited chỉ dành cho việc người dùng tự sửa một bước, không dùng khi sinh lộ trình.",
            )
        if draft.behavior_flag_id is not None and draft.reason_code != "behavior_changed":
            raise YofinaError(
                ErrorCode.ROADMAP_INVALID, "behavior_flag_id chỉ đi với lý do behavior_changed."
            )
        ctx = self._context(user_id, with_facts=True)
        assert ctx.facts is not None
        phases = rl.draft_phases(draft)
        goals = [g.model_dump(mode="json", exclude_none=True) for g in draft.goals]
        alternatives = [a.model_dump(mode="json", exclude_none=True) for a in draft.alternatives]
        rl.validate_jar_refs(phases, goals, alternatives, ctx.jar_kinds)
        rules = cached_rules()
        violations, checked = rl.check_steps(phases, ctx.facts, rules)
        if violations:
            raise rl.violation_error(violations)
        flag = self._confirmed_flag(user_id, draft.behavior_flag_id)
        text, detail = rl.reason_for(
            draft.reason_code,
            flag=flag,
            jar_name=ctx.jar_names.get(str(flag["jar_code"])) if flag else None,
        )
        current = self.repo.get_roadmap(user_id, None, "active")
        status = status_for_new_version(
            draft.reason_code, current is not None and current["status"] == "active"
        )
        plan = rl.build_plan(
            feasibility=draft.feasibility,
            goals=goals,
            phases=phases,
            alternatives=alternatives,
            checked=checked,
            basis=self._basis(user_id, ctx),
        )
        saved = self.repo.save_roadmap(
            user_id,
            reason_code=draft.reason_code,
            reason_text=text,
            reason_detail=detail,
            behavior_flag_id=draft.behavior_flag_id,
            based_on_version=draft.based_on_version,
            feasibility=draft.feasibility,
            app_date=ctx.today,
            plan=plan,
            rules_version=rules_version(rules),
            status=status,
            trace_id=trace_id,
            audit={
                "event_type": "roadmap_saved",
                "tool": "save_roadmap",
                "params": {
                    "reason_code": draft.reason_code,
                    "based_on_version": draft.based_on_version,
                    "feasibility": draft.feasibility,
                    "steps": sum(len(p["steps"]) for p in phases),
                },
                "details": {"channel": "gateway", "rules_version": rules_version(rules)},
            },
        )
        row = self._need_row(self.repo.get_roadmap(user_id, int(saved["version"])), NO_VERSION)
        return _ok(ctx.now, ctx.today, rl.roadmap_data(row))

    def _confirmed_flag(self, user_id: str, flag_id: str | None) -> Mapping[str, Any] | None:
        """Dòng `behavior_flags` mà lộ trình `behavior_changed` dựa vào: của chính người gọi và đã được XÁC NHẬN (PELT). Dấu hiệu 'nghi'
        hoặc báo nhầm không đủ để sinh lại lộ trình."""
        if flag_id is None:
            return None
        flags = self.repo.list_behavior_flags(user_id)
        flag = next((f for f in flags if str(f["id"]) == flag_id), None)
        if flag is None:
            raise YofinaError(ErrorCode.ROADMAP_INVALID, "Không tìm thấy dấu hiệu đổi hành vi này.")
        if flag["status"] not in ("confirmed", "applied"):
            raise YofinaError(
                ErrorCode.ROADMAP_INVALID,
                "Dấu hiệu đổi hành vi này chưa được xác nhận nên chưa dùng để sinh lại lộ trình.",
            )
        return flag

    # --- tool: planner___get_roadmap và GET /roadmap ------------------------------------------------------------------
    @staticmethod
    def _version_arg(value: Any) -> int | None:
        """`version` của tool hoặc query: số nguyên 1..10000 (query đến dạng chuỗi); vắng thì None."""
        if value in (None, ""):
            return None
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10000:
            raise YofinaError(ErrorCode.PARAMS_INVALID, "version phải là số nguyên từ 1 đến 10000.")
        return value

    def _read(self, user_id: str, version: Any, which: Any) -> tuple[Context, dict[str, Any]]:
        v = self._version_arg(version)
        if which in (None, ""):
            which = "active"
        if which not in ROADMAP_WHICH:
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, "which phải là active, proposed hoặc latest."
            )
        row = self.repo.get_roadmap(user_id, v, str(which))
        if row is None:
            if v is not None:
                raise YofinaError(ErrorCode.ROADMAP_NOT_FOUND, NO_VERSION)
            if which == "proposed":
                raise YofinaError(ErrorCode.ROADMAP_NOT_FOUND, NO_PROPOSED)
            raise YofinaError(ErrorCode.ROADMAP_NOT_FOUND, NO_ROADMAP)
        ctx = self._context(user_id, with_facts=False)
        return ctx, rl.roadmap_data(row)

    def get_roadmap_result(
        self, user_id: str, *, version: Any = None, which: Any = None
    ) -> dict[str, Any]:
        ctx, data = self._read(user_id, version, which)
        return _ok(ctx.now, ctx.today, data)

    def roadmap_response(
        self, user_id: str, *, version: Any, which: Any, trace_id: str
    ) -> dict[str, Any]:
        """`GET /roadmap`: khối `roadmap`."""
        ctx, data = self._read(user_id, version, which)
        return self._block(ctx, data, trace_id, "rest:GET /roadmap")

    # --- GET /roadmap/versions ------------------------------------------------------------------------------------
    def versions_response(self, user_id: str, *, limit: int) -> dict[str, Any]:
        rows = self.repo.list_versions(user_id, limit)
        versions = [rl.version_summary(r) for r in rows]
        out: dict[str, Any] = {"versions": versions}
        for v in versions:
            if v["status"] == "active" and "active_version" not in out:
                out["active_version"] = v["version"]
            if v["status"] == "proposed" and "proposed_version" not in out:
                out["proposed_version"] = v["version"]
        job = self.repo.get_job(user_id)
        if job is not None and job["status"] in ("queued", "running"):
            out["current_job"] = rl.job_data(job)
        return out

    # --- GET /roadmap/diff ----------------------------------------------------------------------------------------------
    def diff_response(
        self, user_id: str, *, from_version: int | None, to_version: int | None, trace_id: str
    ) -> dict[str, Any]:
        """Bước thêm, bỏ, đổi giữa hai phiên bản. Vắng `to_version`: bản chờ chọn, không có thì bản đang dùng. Vắng `from_version`: bản
        gốc của bản `to`."""
        if to_version is not None:
            to_row = self._need_row(self.repo.get_roadmap(user_id, to_version), NO_VERSION)
        else:
            to_row = self.repo.get_roadmap(user_id, None, "proposed") or self.repo.get_roadmap(
                user_id, None, "active"
            )
            to_row = self._need_row(to_row, NO_ROADMAP)
        if from_version is None:
            from_version = to_row.get("based_on_version")
            if from_version is None:
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID,
                    "Bản này không có bản gốc để so, hãy nêu from_version.",
                )
        if int(from_version) == int(to_row["version"]):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Hai phiên bản so sánh phải khác nhau.")
        from_row = self._need_row(self.repo.get_roadmap(user_id, int(from_version)), NO_VERSION)
        ctx = self._context(user_id, with_facts=False)
        data = rl.diff_roadmaps(rl.roadmap_data(from_row), rl.roadmap_data(to_row), ctx.jar_names)
        return block_to_wire(
            build_roadmap_diff(
                data=data,
                trace_id=trace_id,
                source_tool="rest:GET /roadmap/diff",
                as_of=ctx.now,
                app_date=ctx.today,
            )
        )

    # --- POST /roadmap/steps/{step_id}/decision ---------------------------------------------------------------------------
    def decide_step_response(
        self,
        user_id: str,
        *,
        step_id: str,
        version: int,
        decision: str,
        reason: str | None,
        trace_id: str,
    ) -> dict[str, Any]:
        """Chấp nhận, từ chối hoặc đưa về chờ một bước của bản `active` hoặc `proposed`. KHÔNG đổi số dư và KHÔNG thực hiện `action` của
        bước. Idempotent: quyết định trùng quyết định đã ghi thì không ghi gì. Ghi audit và (accepted, rejected) một dòng feedback."""
        if decision not in ROADMAP_DECISIONS:
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, "decision phải là accepted, rejected hoặc pending."
            )
        row = self._need_row(self.repo.get_roadmap(user_id, version), NO_VERSION)
        if row["status"] not in ALIVE:
            raise YofinaError(
                ErrorCode.ROADMAP_VERSION_CONFLICT,
                "Phiên bản này đã bị thay hoặc bỏ, hãy đọc lại lộ trình.",
            )
        step = next(
            (s for _p, s in rl.iter_steps(row["plan"]["phases"]) if s["step_id"] == step_id), None
        )
        if step is None:
            raise YofinaError(ErrorCode.ROADMAP_NOT_FOUND, NO_STEP)
        state = (row.get("step_states") or {}).get(step_id) or {}
        previous = state.get("status", "pending")
        if previous != decision:
            self.repo.set_step_state(
                user_id,
                version=version,
                step_id=step_id,
                status=decision,
                edited=True if state.get("edited") else None,
                trace_id=trace_id,
                audit={
                    "event_type": "roadmap_step_decided",
                    "tool": "roadmap_step_decision",
                    "params": {"version": version, "step_id": step_id, "decision": decision},
                    "details": {"channel": "rest", "previous": previous},
                },
                feedback=(
                    {
                        "option_id": step_id,
                        "decision": decision,
                        "reason": reason.strip() if decision == "rejected" and reason else None,
                    }
                    if decision in FEEDBACK_DECISIONS
                    else None
                ),
            )
        fresh = self._need_row(self.repo.get_roadmap(user_id, version), NO_VERSION)
        return self._block(
            self._context(user_id, with_facts=False),
            rl.roadmap_data(fresh),
            trace_id,
            "rest:POST /roadmap/steps/{step_id}/decision",
        )

    # --- POST /roadmap/steps/{step_id}/edit -------------------------------------------------------------------------------
    def edit_step_response(
        self,
        user_id: str,
        *,
        step_id: str,
        version: int,
        amount_vnd: int | None,
        due_date: str | None,
        trace_id: str,
    ) -> dict[str, Any]:
        """Người dùng đổi số tiền hoặc ngày của MỘT bước: lưu một phiên bản MỚI `active` (lý do `step_edited`), bước đã sửa `accepted` và
        `edited`, các bước khác giữ trạng thái; bản gốc thành `superseded` và bản chờ (nếu có) bị bỏ. Chạy lại luật suitability cho
        bước đã sửa. Không gọi model, không sinh lại toàn bộ."""
        row = self._need_row(self.repo.get_roadmap(user_id, version), NO_VERSION)
        if row["status"] not in ALIVE:
            raise YofinaError(
                ErrorCode.ROADMAP_VERSION_CONFLICT,
                "Phiên bản này đã bị thay hoặc bỏ, hãy đọc lại lộ trình.",
            )
        ctx = self._context(user_id, with_facts=True)
        assert ctx.facts is not None
        if due_date is not None and due_date < ctx.today.isoformat():
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Ngày mới không được trước hôm nay.")
        plan, step, changes = rl.apply_step_edit(
            row["plan"], step_id, amount_vnd=amount_vnd, due_date=due_date
        )
        rules = cached_rules()
        violations, checked = rl.check_steps(plan["phases"], ctx.facts, rules, only_step=step_id)
        if violations:
            raise rl.violation_error(violations)
        if checked.get(step_id):
            step["checked_rules"] = checked[step_id]
        else:
            step.pop("checked_rules", None)
        text, detail = rl.reason_for("step_edited", step_title=step["title"], changes=changes)
        states = {
            sid: dict(s)
            for sid, s in (row.get("step_states") or {}).items()
            if any(st["step_id"] == sid for _p, st in rl.iter_steps(plan["phases"]))
        }
        states[step_id] = {
            "status": "accepted",
            "decided_at": format_instant(ctx.now),
            "edited": True,
        }
        saved = self.repo.save_roadmap(
            user_id,
            reason_code="step_edited",
            reason_text=text,
            reason_detail=detail,
            behavior_flag_id=None,
            based_on_version=version,
            feasibility=row["feasibility"],
            app_date=ctx.today,
            plan=plan,
            rules_version=rules_version(rules),
            status=status_for_new_version("step_edited", True),
            trace_id=trace_id,
            step_states=states,
            audit={
                "event_type": "roadmap_step_edited",
                "tool": "roadmap_step_edit",
                "params": {
                    "version": version,
                    "step_id": step_id,
                    **({"amount_vnd": amount_vnd} if amount_vnd is not None else {}),
                    **({"due_date": due_date} if due_date is not None else {}),
                },
                "details": {"channel": "rest", "based_on_version": version},
            },
            feedback={"option_id": step_id, "decision": "accepted", "reason": "edited"},
        )
        fresh = self._need_row(self.repo.get_roadmap(user_id, int(saved["version"])), NO_VERSION)
        return self._block(
            ctx, rl.roadmap_data(fresh), trace_id, "rest:POST /roadmap/steps/{step_id}/edit"
        )

    # --- POST /roadmap/versions/{version}/decision --------------------------------------------------------------------------
    def decide_version_response(
        self,
        user_id: str,
        *,
        version: int,
        decision: str,
        trace_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """ "Dùng bản mới" (`adopt`) hoặc "Giữ bản cũ" (`keep_previous`) với bản chờ. Idempotent: quyết định đã có hiệu lực thì không
        ghi gì. Trả khối của bản được chọn (ở `keep_previous` là bản đã bỏ để giao diện hiện trạng thái). `reason` (một câu lý do tùy
        chọn, chỉ với `keep_previous`) là chữ người dùng gõ: che PII (`yofina_core.pii`, như lý do của bản tin) rồi lưu ở dòng
        `feedback` của quyết định; không vào audit, không vào prompt."""
        if decision not in ROADMAP_VERSION_DECISIONS:
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, "decision phải là adopt hoặc keep_previous."
            )
        row = self._need_row(self.repo.get_roadmap(user_id, version), NO_VERSION)
        done = (decision == "adopt" and row["status"] == "active") or (
            decision == "keep_previous" and row["status"] == "discarded"
        )
        if not done:
            self.repo.decide_version(
                user_id,
                version=version,
                decision=decision,
                trace_id=trace_id,
                audit={
                    "event_type": "roadmap_version_decided",
                    "tool": "roadmap_version_decision",
                    "params": {"version": version, "decision": decision},
                    "details": {"channel": "rest", "previous": row["status"]},
                },
                feedback={
                    "option_id": f"version_{decision}",
                    "decision": VERSION_FEEDBACK[decision],
                    "reason": _masked_reason(reason) if decision == "keep_previous" else None,
                },
            )
        fresh = self._need_row(self.repo.get_roadmap(user_id, version), NO_VERSION)
        return self._block(
            self._context(user_id, with_facts=False),
            rl.roadmap_data(fresh),
            trace_id,
            "rest:POST /roadmap/versions/{version}/decision",
        )

    # --- POST /roadmap/regenerate -------------------------------------------------------------------------------------------
    def regenerate_response(
        self,
        user_id: str,
        *,
        note: str | None,
        alternative_id: str | None,
        based_on_version: int | None,
        trace_id: str,
    ) -> dict[str, Any]:
        """Ghi một dòng `roadmap_jobs` (`user_request`) rồi phát `roadmap.regeneration_requested` SAU commit, trả job NGAY. Người dùng đã
        có một job đang chạy thì trả CHÍNH job đó (không ghi, không phát gì thêm)."""
        live = self._live_job(user_id)
        if live is not None:
            return rl.job_data(live)
        base: Mapping[str, Any] | None = None
        if based_on_version is not None:
            base = self._need_row(self.repo.get_roadmap(user_id, based_on_version), NO_VERSION)
            if base["status"] not in ALIVE:
                raise YofinaError(
                    ErrorCode.ROADMAP_VERSION_CONFLICT,
                    "Bản gốc đã bị thay hoặc không còn, hãy đọc lại lộ trình.",
                )
        else:
            current = self.repo.get_roadmap(user_id, None, "active")
            if current is not None and current["status"] == "active":
                base = current
        if alternative_id is not None:
            options = {
                a["option_id"] for a in ((base or {}).get("plan") or {}).get("alternatives", [])
            }
            if alternative_id not in options:
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID,
                    "alternative_id không phải một trong các lựa chọn của lộ trình gốc.",
                )
        base_version = int(base["version"]) if base is not None else None
        ctx = self._context(user_id, with_facts=False)
        job_id = self.repo.create_job(
            user_id,
            alternative_id=alternative_id,
            note=note,
            based_on_version=base_version,
            trace_id=trace_id,
            audit={
                "event_type": "roadmap_regenerate_requested",
                "tool": "roadmap_regenerate",
                "params": {
                    "based_on_version": base_version,
                    **({"alternative_id": alternative_id} if alternative_id else {}),
                },
                "details": {"channel": "rest", "has_note": note is not None},
            },
        )
        if job_id is None:  # thua cuộc đua với yêu cầu song song: trả job đang chạy
            live = self._live_job(user_id)
            if live is None:
                raise YofinaError(ErrorCode.INTERNAL_ERROR, "Không tạo được lần sinh lại.")
            return rl.job_data(live)
        self.svc._publish(
            user_id,
            trace_id,
            [
                events.roadmap_regeneration_requested(
                    user_id=user_id,
                    trace_id=trace_id,
                    job_id=job_id,
                    occurred_at=ctx.now,
                    app_date=ctx.today,
                    trigger="user_request",
                    based_on_version=base_version,
                    alternative_id=alternative_id,
                )
            ],
        )
        job = self._need_row(self.repo.get_job(user_id, job_id), NO_JOB)
        return rl.job_data(job)

    def _live_job(self, user_id: str) -> Mapping[str, Any] | None:
        job = self.repo.get_job(user_id)
        return job if job is not None and job["status"] in ("queued", "running") else None

    # --- GET /roadmap/jobs/{job_id} -------------------------------------------------------------------------------------------
    def job_response(self, user_id: str, job_id: str) -> dict[str, Any]:
        job = self._need_row(self.repo.get_job(user_id, job_id), NO_JOB)
        return rl.job_data(job)


def roadmap_ops(service: Any) -> RoadmapOps:
    """`RoadmapOps` của một `LedgerService` (dựng một lần, nhớ ngay trên `service`). Test đặt `service.roadmap_repo` trước lần gọi đầu để
    thay kho dữ liệu."""
    ops = service.__dict__.get("_roadmap_ops")
    if ops is None:
        ops = RoadmapOps(service, service.__dict__.get("roadmap_repo"))
        service.__dict__["_roadmap_ops"] = ops
    return ops
