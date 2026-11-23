"""Phát hiện đổi hành vi chi tiêu trong pipeline (F5, luồng A phase 4): nối `yofina_ml.change` với Aurora và EventBridge.

Hai điểm vào, đúng máy trạng thái của `behavior_flags` (migration 0052):

| Hàm | Chạy ở đâu | Việc |
|---|---|---|
| `suspect_and_store` | đường sự kiện (`consumer.py`, sau mỗi `transaction.recorded`) | CUSUM trên chuỗi tuần: ghi dấu hiệu `suspected`; KHÔNG phát sự kiện |
| `detect_and_store` (N2) | batch đêm (người điều phối nối sau bước dự báo của `run_user`) | PELT trên chuỗi tuần: xác nhận (`confirmed`, nâng dấu hiệu nghi hoặc tạo mới) và phát `behavior.changed`; dấu hiệu nghi quá hạn chuyển `dismissed` |

Quy tắc dữ liệu:

- Nguồn chuỗi: `Pipeline.load_context` (hàm DB `app_get_forecast_context`): chi tiêu từng NGÀY của hũ `spending` từ ngày có dữ liệu sớm nhất
  tới hôm qua, chỉ chi trừ tiền hũ và KHÔNG gắn nghĩa vụ (tiền trọ, hóa đơn theo lịch không phải thói quen chi). Tuần cắt lùi từ hôm qua.
- Đọc dấu hiệu qua `app_list_behavior_flags`; ghi bằng INSERT/UPDATE của role `yofina_app` trong transaction đặt `app.user_id` (RLS),
  mỗi dấu hiệu một transaction nên lỗi của một hũ không hủy hũ khác. Mỗi (người dùng, hũ) tối đa MỘT dấu hiệu mở (chỉ mục duy nhất
  một phần); INSERT dùng `ON CONFLICT DO NOTHING` nên hai lần chạy song song (đêm và sự kiện) không làm nhau lỗi.
- Điểm gãy đã có dấu hiệu `confirmed` hoặc `applied` của cùng hũ lệch không quá `dedupe_days` ngày thì KHÔNG tạo dấu hiệu mới
  (PELT vẫn thấy điểm gãy cũ trong lịch sử mỗi đêm).
- `behavior.changed` phát SAU commit, `event_id` = `flag_id`; phát thất bại không làm hỏng lần chạy: dấu hiệu `confirmed` chưa có
  `detail.event_published_at` được phát lại ở lần chạy sau (consumer dedupe theo `event_id`, nên phát hai lần vô hại).
- Một khoản lớn đơn lẻ không phải đổi hành vi: bước z bền MAD đánh dấu và cắt nó khỏi chuỗi, PELT chỉ xác nhận mức mới giữ đủ tuần.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Protocol

import numpy as np

from yofina_core.db import DataApi
from yofina_core.errors import ErrorCode, YofinaError
from yofina_forecast.events import emf
from yofina_forecast.runner import Pipeline
from yofina_ml import change as ml

log = logging.getLogger("yofina.forecast.change")

SPENDING_KIND = "spending"  # chỉ hũ chi tiêu có "thói quen chi"; hũ tiết kiệm và nghĩa vụ thì không
OPEN_STATUSES = ("suspected", "confirmed")
DONE_STATUSES = ("confirmed", "applied")

SQL_LIST = "SELECT * FROM app_list_behavior_flags(CAST(:uid AS text), CAST(:status AS text), CAST(:lim AS integer))"
SQL_INSERT = (
    "INSERT INTO behavior_flags (id, user_id, jar_code, status, method, direction, old_weekly_vnd, new_weekly_vnd, "
    "suspected_app_date, change_point_date, confirmed_app_date, weeks_held, detail) "
    "VALUES (CAST(:id AS uuid), :uid, :jar, :status, :method, :direction, CAST(:old AS numeric), CAST(:new AS numeric), "
    "CAST(:suspected AS date), CAST(:cp AS date), CAST(:confirmed AS date), CAST(:weeks_held AS integer), CAST(:detail AS jsonb)) "
    "ON CONFLICT (user_id, jar_code) WHERE status IN ('suspected', 'confirmed') DO NOTHING RETURNING id"
)
#: nâng dấu hiệu nghi thành xác nhận, hoặc cập nhật số của dấu hiệu nghi đang mở; chỉ khi dấu hiệu còn đúng trạng thái đã đọc
SQL_UPDATE = (
    "UPDATE behavior_flags SET status = :status, method = :method, direction = :direction, "
    "old_weekly_vnd = CAST(:old AS numeric), new_weekly_vnd = CAST(:new AS numeric), "
    "change_point_date = CAST(:cp AS date), confirmed_app_date = CAST(:confirmed AS date), "
    "weeks_held = CAST(:weeks_held AS integer), detail = CAST(:detail AS jsonb), updated_at = now() "
    "WHERE id = CAST(:id AS uuid) AND user_id = :uid AND status = :expected RETURNING id"
)
SQL_DISMISS = (
    "UPDATE behavior_flags SET status = 'dismissed', detail = CAST(:detail AS jsonb), updated_at = now() "
    "WHERE id = CAST(:id AS uuid) AND user_id = :uid AND status = 'suspected' RETURNING id"
)
SQL_MARK_PUBLISHED = (
    "UPDATE behavior_flags SET detail = detail || CAST(:patch AS jsonb), updated_at = now() "
    "WHERE id = CAST(:id AS uuid) AND user_id = :uid AND status = 'confirmed' RETURNING id"
)
MAX_FLAGS = 50  # giới hạn của `app_list_behavior_flags`


class FlagStore(Protocol):
    """Kho dấu hiệu. Bản thật là `DbFlagStore` (Aurora); test dùng bản trong bộ nhớ."""

    def list(self, user_id: str) -> list[Mapping[str, Any]]: ...

    def insert(self, user_id: str, flag: Mapping[str, Any]) -> bool: ...

    def update(self, user_id: str, flag: Mapping[str, Any], expected: str) -> bool: ...

    def dismiss(self, user_id: str, flag_id: str, detail: Mapping[str, Any]) -> bool: ...

    def mark_published(self, user_id: str, flag_id: str, patch: Mapping[str, Any]) -> bool: ...


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


class DbFlagStore:
    def __init__(self, db: DataApi) -> None:
        self.db = db

    def list(self, user_id: str) -> list[Mapping[str, Any]]:
        return self.db.query(
            SQL_LIST, {"uid": user_id, "status": None, "lim": MAX_FLAGS}, max_rows=MAX_FLAGS
        )

    def insert(self, user_id: str, flag: Mapping[str, Any]) -> bool:
        with self.db.transaction(user_id) as tx:
            rows = tx.execute(SQL_INSERT, {"uid": user_id, **_bind(flag)})
        return bool(rows)

    def update(self, user_id: str, flag: Mapping[str, Any], expected: str) -> bool:
        with self.db.transaction(user_id) as tx:
            rows = tx.execute(SQL_UPDATE, {"uid": user_id, "expected": expected, **_bind(flag)})
        return bool(rows)

    def dismiss(self, user_id: str, flag_id: str, detail: Mapping[str, Any]) -> bool:
        with self.db.transaction(user_id) as tx:
            rows = tx.execute(SQL_DISMISS, {"uid": user_id, "id": flag_id, "detail": _json(detail)})
        return bool(rows)

    def mark_published(self, user_id: str, flag_id: str, patch: Mapping[str, Any]) -> bool:
        with self.db.transaction(user_id) as tx:
            rows = tx.execute(
                SQL_MARK_PUBLISHED, {"uid": user_id, "id": flag_id, "patch": _json(patch)}
            )
        return bool(rows)


def _bind(flag: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": flag["id"],
        "jar": flag["jar_code"],
        "status": flag["status"],
        "method": flag["method"],
        "direction": flag["direction"],
        "old": int(flag["old_weekly_vnd"]),
        "new": int(flag["new_weekly_vnd"]),
        "suspected": flag.get("suspected_app_date"),
        "cp": flag.get("change_point_date"),
        "confirmed": flag.get("confirmed_app_date"),
        "weeks_held": flag.get("weeks_held"),
        "detail": _json(flag.get("detail") or {}),
    }


def store_for(pipeline: Pipeline) -> FlagStore | None:
    """Kho thật của pipeline (cùng `DataApi` với `ForecastRepo`); None khi repo không có DB (repo trong bộ nhớ của test)."""
    db = getattr(pipeline.repo, "db", None)
    return DbFlagStore(db) if db is not None else None


@dataclass
class ChangeReport:
    """Kết quả một lần chạy cho một người dùng (log, test, báo cáo của batch)."""

    user_id: str
    app_date: str | None = None
    checked: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)  # hũ -> lý do không phân tích
    suspected: list[str] = field(default_factory=list)  # hũ có dấu hiệu nghi mới
    confirmed: list[str] = field(default_factory=list)  # hũ vừa được xác nhận
    dismissed: list[str] = field(default_factory=list)  # hũ có dấu hiệu nghi quá hạn nên báo nhầm
    published: list[str] = field(default_factory=list)  # flag_id đã phát `behavior.changed`
    errors: list[str] = field(default_factory=list)  # lỗi từng hũ (không làm hỏng hũ khác)
    reason: str | None = None  # lý do cả lần chạy không làm gì (hồ sơ chưa đủ...)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [], {})}


# --- đọc chuỗi ---------------------------------------------------------------------------------------------
def spending_series(
    pipeline: Pipeline, user_id: str, now: datetime, jar_codes: Sequence[str] | None
) -> tuple[date, dict[str, np.ndarray]]:
    """(ngày mô phỏng hôm nay, chi tiêu từng ngày của các hũ `spending`) từ `app_get_forecast_context`. Hồ sơ chưa có -> PROFILE_INCOMPLETE."""
    ctx = pipeline.load_context(user_id, now)
    want = set(jar_codes) if jar_codes is not None else None
    out: dict[str, np.ndarray] = {}
    for j in sorted(ctx.jars, key=lambda j: (j["sort_order"], j["code"])):
        if j["kind"] != SPENDING_KIND or (want is not None and j["code"] not in want):
            continue
        out[j["code"]] = np.asarray([max(float(v or 0), 0.0) for v in j.get("spend") or []])
    return ctx.app_date, out


def _calibration_detail(kind: str) -> dict[str, Any]:
    cal = ml.calibration_for(kind)
    return {"calibration": cal} if cal else {}


def _near(a: date | None, b: date, days: int) -> bool:
    return a is not None and abs((_as_date(a) - b).days) <= days


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _detail_of(flag: Mapping[str, Any]) -> Mapping[str, Any]:
    detail = flag.get("detail") or {}
    return detail if isinstance(detail, Mapping) else {}


def _owned(flag: Mapping[str, Any]) -> bool:
    """Dấu hiệu do chính bộ phát hiện PELT này tạo (có `detail.detector` là pelt và phiên bản tham số)."""
    d = _detail_of(flag)
    return flag.get("method") == "pelt" and d.get("detector") == "pelt" and "params_version" in d


def _is_open(flag: Mapping[str, Any]) -> bool:
    return flag["status"] in OPEN_STATUSES


def _covered(flags: Sequence[Mapping[str, Any]], jar: str, when: date, days: int) -> bool:
    """Điểm gãy `when` của hũ đã có dấu hiệu xác nhận hoặc đã dùng gần đó chưa?"""
    return any(
        f["jar_code"] == jar
        and f["status"] in DONE_STATUSES
        and _near(f["change_point_date"], when, days)
        for f in flags
    )


def _open_flag(flags: Sequence[Mapping[str, Any]], jar: str) -> Mapping[str, Any] | None:
    return next((f for f in flags if f["jar_code"] == jar and _is_open(f)), None)


def _expired(flag: Mapping[str, Any], app_date: date, params: ml.ChangeParams) -> bool:
    return (app_date - _as_date(flag["suspected_app_date"])).days > params.suspect_expire_weeks * 7


# --- đường sự kiện: nghi --------------------------------------------------------------------------------------
def suspect_and_store(
    pipeline: Pipeline,
    user_id: str,
    now: datetime,
    jar_codes: Sequence[str] | None = None,
    *,
    store: FlagStore | None = None,
    params: ml.ChangeParams | None = None,
) -> ChangeReport:
    """CUSUM trên chuỗi tuần của các hũ chi tiêu (`jar_codes` None thì mọi hũ): ghi dấu hiệu `suspected`, KHÔNG phát sự kiện.

    Hũ đã có dấu hiệu mở (nghi hoặc đã xác nhận) thì chỉ cập nhật số của dấu hiệu nghi khi CUSUM còn báo; điểm gãy đã có dấu hiệu xác
    nhận hoặc đã dùng thì bỏ qua. Dấu hiệu nghi quá hạn thì để batch đêm chuyển thành báo nhầm (sự kiện không làm việc đó để tránh
    hai nơi cùng sửa)."""
    store = store or store_for(pipeline)
    report = ChangeReport(user_id)
    if store is None:
        report.reason = "no_store"
        return report
    params = params or ml.load_params()
    try:
        app_date, series = spending_series(pipeline, user_id, now, jar_codes)
    except YofinaError as exc:
        if exc.code in (ErrorCode.PROFILE_INCOMPLETE, ErrorCode.FORECAST_UNAVAILABLE):
            report.reason = str(exc.code)
            return report
        raise
    report.app_date = app_date.isoformat()
    last_day = app_date - timedelta(days=1)
    flags = store.list(user_id)
    for jar, daily in series.items():
        try:
            weekly = ml.prepare_weekly(daily, params)
            if weekly.skipped:
                report.skipped[jar] = weekly.skipped
                continue
            report.checked.append(jar)
            hit = ml.detect_suspect(weekly, params)
            if hit is None:
                continue
            when = ml.week_start_date(last_day, weekly.n_weeks, hit.start_index)
            if _covered(flags, jar, when, params.dedupe_days):
                continue
            existing = _open_flag(flags, jar)
            detail = _detail(params, weekly, hit.to_detail(), "suspect_cusum")
            row = {
                "jar_code": jar,
                "status": "suspected",
                "method": "cusum",
                "direction": hit.direction,
                "old_weekly_vnd": hit.old_weekly_vnd,
                "new_weekly_vnd": hit.new_weekly_vnd,
                "suspected_app_date": app_date,
                "change_point_date": when,
                "detail": detail,
            }
            if existing is None:
                if store.insert(user_id, {"id": str(uuid.uuid4()), **row}):
                    report.suspected.append(jar)
            elif existing["status"] == "suspected":
                store.update(
                    user_id,
                    {
                        **row,
                        "id": str(existing["id"]),
                        "suspected_app_date": existing["suspected_app_date"],
                    },
                    expected="suspected",
                )
        except YofinaError:
            raise
        except Exception as exc:  # lỗi một hũ không làm hỏng hũ khác
            log.exception("suspect_failed jar=%s", jar)
            report.errors.append(f"{jar}: {type(exc).__name__}")
    _log(report, "suspect")
    return report


# --- batch đêm: xác nhận (N2) ---------------------------------------------------------------------------------------
def detect_and_store(
    pipeline: Pipeline,
    user_id: str,
    now: datetime,
    *,
    store: FlagStore | None = None,
    params: ml.ChangeParams | None = None,
) -> ChangeReport:
    """N2: PELT trên chuỗi tuần của mọi hũ chi tiêu; xác nhận điểm gãy, ghi/cập nhật `behavior_flags`, phát `behavior.changed`.

    Không tự nối vào `run_user`: người điều phối gọi sau bước dự báo (thứ tự: dự báo, điểm chống chịu, phát hiện đổi hành vi) và
    bọc lỗi riêng để một bước hỏng không làm hỏng bước khác."""
    store = store or store_for(pipeline)
    report = ChangeReport(user_id)
    if store is None:
        report.reason = "no_store"
        return report
    params = params or ml.load_params()
    try:
        app_date, series = spending_series(pipeline, user_id, now, None)
    except YofinaError as exc:
        if exc.code in (ErrorCode.PROFILE_INCOMPLETE, ErrorCode.FORECAST_UNAVAILABLE):
            report.reason = str(exc.code)
            return report
        raise
    report.app_date = app_date.isoformat()
    last_day = app_date - timedelta(days=1)
    flags = store.list(user_id)
    to_publish: dict[str, Mapping[str, Any]] = {}  # flag_id -> chi tiết sự kiện (đã commit)
    for jar, daily in series.items():
        try:
            weekly = ml.prepare_weekly(daily, params)
            existing = _open_flag(flags, jar)
            if weekly.skipped:
                report.skipped[jar] = weekly.skipped
            else:
                report.checked.append(jar)
            hit = None if weekly.skipped else ml.detect_confirmed(weekly, params)
            if hit is not None:
                when = ml.week_start_date(last_day, weekly.n_weeks, hit.change_index)
                if existing is not None and existing["status"] == "confirmed":
                    pass  # đã xác nhận, chờ dùng để sinh lại lộ trình
                elif _covered(flags, jar, when, params.dedupe_days):
                    pass  # điểm gãy cũ, đã xử lý
                else:
                    detail = _detail(params, weekly, hit.to_detail(), "confirm_pelt")
                    if existing is not None:  # nâng dấu hiệu nghi
                        detail["suspected"] = _detail_of(existing)
                    flag_id = str(existing["id"]) if existing is not None else str(uuid.uuid4())
                    row = {
                        "id": flag_id,
                        "jar_code": jar,
                        "status": "confirmed",
                        "method": "pelt",
                        "direction": hit.direction,
                        "old_weekly_vnd": hit.old_weekly_vnd,
                        "new_weekly_vnd": hit.new_weekly_vnd,
                        "suspected_app_date": (
                            existing["suspected_app_date"] if existing is not None else app_date
                        ),
                        "change_point_date": when,
                        "confirmed_app_date": app_date,
                        "weeks_held": hit.weeks_held,
                        "detail": detail,
                    }
                    ok = (
                        store.update(user_id, row, expected="suspected")
                        if existing is not None
                        else store.insert(user_id, row)
                    )
                    if ok:
                        report.confirmed.append(jar)
                        to_publish[flag_id] = row
            elif (
                existing is not None
                and existing["status"] == "suspected"
                and _expired(existing, app_date, params)
            ):
                detail = dict(_detail_of(existing))
                detail["dismissed"] = {
                    "reason": "not_confirmed",
                    "app_date": app_date.isoformat(),
                    "after_weeks": params.suspect_expire_weeks,
                }
                if store.dismiss(user_id, str(existing["id"]), detail):
                    report.dismissed.append(jar)
        except YofinaError:
            raise
        except Exception as exc:  # lỗi một hũ không làm hỏng hũ khác
            log.exception("detect_failed jar=%s", jar)
            report.errors.append(f"{jar}: {type(exc).__name__}")
    # phát lại các dấu hiệu CỦA bộ phát hiện này đã xác nhận mà sự kiện chưa tới bus (lần phát trước thất bại hoặc chưa có bus).
    # Dấu hiệu nạp sẵn của persona (detail.source) hay của nguồn khác không thuộc việc của hàm này.
    for f in flags:
        if _owned(f) and f["status"] == "confirmed" and not _detail_of(f).get("event_published_at"):
            to_publish.setdefault(str(f["id"]), f)
    _publish_all(pipeline, store, user_id, now, app_date, to_publish, report)
    _log(report, "detect")
    return report


def _publish_all(
    pipeline: Pipeline,
    store: FlagStore,
    user_id: str,
    now: datetime,
    app_date: date,
    rows: Mapping[str, Mapping[str, Any]],
    report: ChangeReport,
) -> None:
    publisher = pipeline.publisher
    if publisher is None:
        return
    for flag_id, row in rows.items():
        try:
            ok = publisher.behavior_changed(
                user_id=user_id,
                flag_id=flag_id,
                occurred_at=now,
                app_date=app_date,
                jar_code=str(row["jar_code"]),
                direction=str(row["direction"]),
                old_weekly_vnd=int(row["old_weekly_vnd"]),
                new_weekly_vnd=int(row["new_weekly_vnd"]),
                weeks_held=int(row["weeks_held"] or 0),
                change_point_date=(
                    _as_date(row["change_point_date"]) if row.get("change_point_date") else None
                ),
            )
            if ok:
                store.mark_published(user_id, flag_id, {"event_published_at": now.isoformat()})
                report.published.append(flag_id)
        except Exception as exc:  # phát không bao giờ làm hỏng lần chạy; lần sau phát lại
            log.error(emf("BehaviorEventPublishFailed", 1, error=type(exc).__name__))


def _detail(
    params: ml.ChangeParams,
    weekly: ml.WeeklySeries,
    detector: Mapping[str, Any],
    calibration_kind: str,
) -> dict[str, Any]:
    """`behavior_flags.detail`: bộ phát hiện và tham số đã dùng, tỷ lệ báo nhầm đã hiệu chỉnh (quyết định 6 của phase 4). Không PII."""
    return {
        **detector,
        "params_version": params.version,
        "params": params.to_dict(),
        "weeks_total": weekly.n_weeks,
        "one_off_days_flagged": len(weekly.one_off_days),
        **_calibration_detail(calibration_kind),
    }


def _log(report: ChangeReport, mode: str) -> None:
    log.info(
        json.dumps({"msg": "behavior_change", "mode": mode, **report.to_dict()}, ensure_ascii=False)
    )
    if report.confirmed:
        log.info(emf("BehaviorChangeConfirmed", len(report.confirmed)))
