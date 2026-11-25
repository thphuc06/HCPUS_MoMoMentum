"""Lõi của Lambda `yofina-forecast-batch`: các thao tác mà Step Functions `yofina-nightly`, ledger (đặt lại, đọc cũ) và người vận hành gọi.

Sự kiện đầu vào là JSON `{"op": ..., ...}`:

| op | Việc |
|---|---|
| `list_users` | trả `{"user_ids": [...]}` người dùng đã khai lương và ngày nhận (đầu vào của Map trong `yofina-nightly`) |
| `run_user` | tính dự báo cho `user_id` với `trigger` (`nightly`, `reset`, `read`, `manual`); trả `RunOutcome` |
| `run_users` | như `run_user` cho một danh sách `user_ids`, lỗi một người không làm hỏng người khác (trả `results`) |
| `optimize_allocation` | N1 (phase 4): ledger gọi `Invoke` đồng bộ `{"op": "optimize_allocation", "user_id", "args"}`; trả NGUYÊN phong bì tool của `planner___optimize_allocation` (`{status, as_of, app_date, data}` hoặc `{status: ERROR, code, message}`). Vô nghiệm KHÔNG phải lỗi: `data.status` là `infeasible` |
| `summarize` | gộp `results` của Map: đếm ok/bỏ qua/lỗi; có lỗi thì NÉM `NightlyHadFailures` để execution thất bại (alarm) |

Lỗi của `run_user` và `list_users` được ném dưới tên lớp ổn định để Step Functions `Retry` theo `Error`: `DatabaseUnavailable` (thử lại được),
`ForecastFailed` (còn lại, chỉ `run_user`).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from yofina_core.errors import ErrorCode, ToolStatus, YofinaError
from yofina_forecast.allocation import AllocationEngine
from yofina_forecast.runner import TRIGGERS, Pipeline

log = logging.getLogger("yofina.forecast.batch")


class DatabaseUnavailable(Exception):
    """Aurora chưa sẵn sàng (đang dậy): Step Functions thử lại."""


class ForecastFailed(Exception):
    """Lần dự báo của một người dùng thất bại (không thử lại tự động)."""


class NightlyHadFailures(Exception):
    """Batch đêm chạy xong nhưng có người dùng lỗi: execution thất bại để alarm kêu."""


def _require_user(event: Mapping[str, Any]) -> str:
    uid = event.get("user_id")
    if not isinstance(uid, str) or not uid:
        raise ForecastFailed("thiếu user_id")
    return uid


def _trigger(event: Mapping[str, Any]) -> str:
    trig = str(event.get("trigger", "manual"))
    if trig not in TRIGGERS:
        raise ForecastFailed(f"trigger không hợp lệ: {trig}")
    return trig


#: Trigger chạy thêm bước phase 4 sau dự báo (điểm chống chịu, phát hiện đổi hành vi): batch đêm và đặt lại dữ liệu
#: (file phase 4: "Tính trong batch đêm và khi đặt lại dữ liệu"). `read`, `event` chỉ tính dự báo cho nhanh.
POST_STEP_TRIGGERS = ("nightly", "reset", "manual")


def after_forecast(pipeline: Pipeline, user_id: str, trigger: str) -> dict[str, Any]:
    """N2 (phase 4): dự báo → điểm chống chịu → phát hiện đổi hành vi; phase 5 (luồng B) thêm hồ sơ hành vi → cổng bản tin. Mỗi
    bước bọc lỗi riêng: một bước hỏng không làm hỏng bước khác và không làm hỏng lần dự báo đã ghi (trả trạng thái từng bước để
    Step Functions và log thấy)."""
    from yofina_forecast import (  # nhập muộn: bước `read`/`event` không trả giá nhập module
        behavior,
        change,
        resilience,
    )

    steps: dict[str, Any] = {}
    now = pipeline.now()
    try:
        data = resilience.compute_and_store(
            pipeline, user_id, now, source="reset" if trigger == "reset" else "nightly"
        )
        steps["resilience"] = {"status": "ok", "score": data.score}
    except YofinaError as exc:
        steps["resilience"] = {"status": "skipped", "code": str(exc.code)}
    except Exception as exc:
        log.exception("resilience_step_failed")
        steps["resilience"] = {"status": "failed", "error": type(exc).__name__}
    try:
        report = change.detect_and_store(pipeline, user_id, now)
        steps["change"] = {"status": "ok", **_report_summary(report)}
    except YofinaError as exc:
        steps["change"] = {"status": "skipped", "code": str(exc.code)}
    except Exception as exc:
        log.exception("change_step_failed")
        steps["change"] = {"status": "failed", "error": type(exc).__name__}
    steps.update(phase5_steps(pipeline, user_id, trigger, now, behavior))
    return steps


def phase5_steps(pipeline: Pipeline, user_id: str, trigger: str, now: Any, behavior: Any) -> dict[str, Any]:
    """Phase 5 (luồng B): hồ sơ hành vi (`behavior_profiles`; batch đêm gọi model nhỏ, đặt lại dùng câu mẫu) rồi cổng bản tin
    (tối đa một dòng `nudges` của hôm nay). Cổng vẫn chạy khi bước hồ sơ hỏng (chỉ thiếu ứng viên nhận xét hành vi)."""
    steps: dict[str, Any] = {}
    profile: dict[str, Any] | None = None
    try:
        profile = behavior.compute_and_store(pipeline, user_id, now, trigger=trigger)
        steps["behavior"] = {"status": "ok", "ready": profile["ready"], "insights": len(profile["insights"])}
    except YofinaError as exc:
        steps["behavior"] = {"status": "skipped", "code": str(exc.code)}
    except Exception as exc:
        log.exception("behavior_step_failed")
        steps["behavior"] = {"status": "failed", "error": type(exc).__name__}
    try:
        steps["nudge_gate"] = behavior.run_nudge_gate(pipeline, user_id, now, profile=profile)
    except YofinaError as exc:
        steps["nudge_gate"] = {"status": "skipped", "code": str(exc.code)}
    except Exception as exc:
        log.exception("nudge_gate_step_failed")
        steps["nudge_gate"] = {"status": "failed", "error": type(exc).__name__}
    return steps


def _report_summary(report: Any) -> dict[str, Any]:
    """Phần gọn của `ChangeReport` cho kết quả batch (hũ vừa nghi, vừa xác nhận, sự kiện đã phát, lỗi từng hũ)."""
    to_dict = getattr(report, "to_dict", None)
    d = to_dict() if callable(to_dict) else {}
    keys = ("suspected", "confirmed", "published", "errors", "reason")
    return {k: d[k] for k in keys if isinstance(d, Mapping) and d.get(k)}


def run_one(
    pipeline: Pipeline, user_id: str, trigger: str, *, raise_errors: bool
) -> dict[str, Any]:
    try:
        out = pipeline.run_user(user_id, trigger=trigger)
        result = {"status": out.status, **out.to_dict()}
        if out.status == "ok" and trigger in POST_STEP_TRIGGERS:
            result["phase4"] = after_forecast(pipeline, user_id, trigger)
        return result
    except YofinaError as exc:
        if exc.code in (ErrorCode.PROFILE_INCOMPLETE, ErrorCode.FORECAST_UNAVAILABLE):
            return {"status": "skipped", "reason": str(exc.code), "trigger": trigger}
        log.error(json.dumps({"msg": "run_user_failed", "trigger": trigger, "code": str(exc.code)}))
        if not raise_errors:
            return {"status": "failed", "code": str(exc.code), "message": exc.message[:200]}
        if exc.code == ErrorCode.DATABASE_UNAVAILABLE:
            raise DatabaseUnavailable(exc.message) from exc
        raise ForecastFailed(f"{exc.code}: {exc.message}"[:300]) from exc
    except Exception as exc:
        log.exception("run_user_unhandled trigger=%s", trigger)
        if not raise_errors:
            return {"status": "failed", "code": "INTERNAL_ERROR", "message": type(exc).__name__}
        raise ForecastFailed(f"{type(exc).__name__}: {exc}"[:300]) from exc


def optimize_allocation(event: Mapping[str, Any], pipeline: Pipeline) -> dict[str, Any]:
    """Op N1: tối ưu phân bổ cho `user_id`, tham số `args` (đã bỏ `user_id`). Lỗi nghiệp vụ trả phong bì lỗi như Gateway (không ném)
    để ledger chuyển nguyên văn; lỗi ngoài dự kiến trả INTERNAL_ERROR."""
    try:
        uid = event.get("user_id")
        if not isinstance(uid, str) or not uid:
            raise YofinaError(ErrorCode.UNAUTHENTICATED, "Thiếu thông tin người dùng.")
        args = event.get("args")
        if args is None:
            args = {}
        if not isinstance(args, Mapping):
            raise YofinaError(ErrorCode.PARAMS_INVALID, "args phải là một đối tượng.")
        return AllocationEngine(pipeline).optimize(uid, args)
    except YofinaError as exc:
        return {"status": str(ToolStatus.ERROR), "code": str(exc.code), "message": exc.message}
    except Exception:
        log.exception("optimize_allocation_unhandled")
        return {
            "status": str(ToolStatus.ERROR),
            "code": str(ErrorCode.INTERNAL_ERROR),
            "message": "Có lỗi hệ thống, thử lại sau.",
        }


def handle_batch(event: Mapping[str, Any], pipeline: Pipeline) -> dict[str, Any]:
    op = event.get("op", "run_user")
    if op == "list_users":
        try:
            ids = pipeline.repo.users(pipeline.settings.nightly_max_users)
        except YofinaError as exc:
            # Aurora ngủ quá ngân sách chờ của client: đổi tên lớp để Retry của bước ListUsers bắt được (#14)
            if exc.code == ErrorCode.DATABASE_UNAVAILABLE:
                raise DatabaseUnavailable(exc.message) from exc
            raise
        return {"user_ids": ids, "count": len(ids)}
    if op == "run_user":
        return run_one(pipeline, _require_user(event), _trigger(event), raise_errors=True)
    if op == "run_users":
        ids = event.get("user_ids") or []
        trig = _trigger(event)
        return {"results": [run_one(pipeline, str(u), trig, raise_errors=False) for u in ids]}
    if op == "optimize_allocation":
        return optimize_allocation(event, pipeline)
    if op == "summarize":
        results = [r for r in event.get("results") or [] if isinstance(r, Mapping)]
        counts = {"total": len(results), "ok": 0, "skipped": 0, "failed": 0}
        codes: list[str] = []
        for r in results:
            st = r.get("status")
            counts["failed" if st not in ("ok", "skipped") else st] += 1
            if st not in ("ok", "skipped") and r.get("error"):
                codes.append(str(r["error"])[:80])
        if counts["failed"]:
            raise NightlyHadFailures(
                json.dumps({**counts, "errors": codes[:5]}, ensure_ascii=False)
            )
        return counts
    raise ForecastFailed(f"op không hợp lệ: {op}")
