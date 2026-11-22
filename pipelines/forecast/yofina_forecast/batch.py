"""Lõi của Lambda `yofina-forecast-batch`: các thao tác mà Step Functions `yofina-nightly`, ledger (đặt lại, đọc cũ) và người vận hành gọi.

Sự kiện đầu vào là JSON `{"op": ..., ...}`:

| op | Việc |
|---|---|
| `list_users` | trả `{"user_ids": [...]}` người dùng đã khai lương và ngày nhận (đầu vào của Map trong `yofina-nightly`) |
| `run_user` | tính dự báo cho `user_id` với `trigger` (`nightly`, `reset`, `read`, `manual`); trả `RunOutcome` |
| `run_users` | như `run_user` cho một danh sách `user_ids`, lỗi một người không làm hỏng người khác (trả `results`) |
| `summarize` | gộp `results` của Map: đếm ok/bỏ qua/lỗi; có lỗi thì NÉM `NightlyHadFailures` để execution thất bại (alarm) |

Lỗi của `run_user` được ném dưới tên lớp ổn định để Step Functions `Retry` theo `Error`: `DatabaseUnavailable` (thử lại được),
`ForecastFailed` (còn lại).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from yofina_core.errors import ErrorCode, YofinaError
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


def run_one(
    pipeline: Pipeline, user_id: str, trigger: str, *, raise_errors: bool
) -> dict[str, Any]:
    try:
        out = pipeline.run_user(user_id, trigger=trigger)
        return {"status": out.status, **out.to_dict()}
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


def handle_batch(event: Mapping[str, Any], pipeline: Pipeline) -> dict[str, Any]:
    op = event.get("op", "run_user")
    if op == "list_users":
        ids = pipeline.repo.users(pipeline.settings.nightly_max_users)
        return {"user_ids": ids, "count": len(ids)}
    if op == "run_user":
        return run_one(pipeline, _require_user(event), _trigger(event), raise_errors=True)
    if op == "run_users":
        ids = event.get("user_ids") or []
        trig = _trigger(event)
        return {"results": [run_one(pipeline, str(u), trig, raise_errors=False) for u in ids]}
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
