"""SQL của lộ trình (phase 4, migration 0052): `roadmaps`, `roadmap_jobs`, `behavior_flags` (đọc), cùng `audit_events` và `feedback` của
các thao tác đổi trạng thái.

Cùng quy ước `repo_wallet.py`: đọc qua hàm `app_*` (RLS theo `set_config` trong hàm, một lệnh gọi Data API), ghi trong
`DataApi.transaction(user_id)`. Lỗi nghiệp vụ của các hàm ghi (`ROADMAP_VERSION_CONFLICT`...) là `RAISE EXCEPTION` có tiền tố mã;
`_business_errors` đổi chúng thành `YofinaError` đúng mã (DataApi chỉ đưa chúng ra dưới dạng INTERNAL_ERROR).

Repo không biết hợp đồng khối UI. Nó là một đối tượng riêng (không phải mixin của `LedgerRepo`) vì `repo.py` chỉ được sửa ở phần đặt lại
dữ liệu; `LedgerService` không giữ nó, `roadmap_service.roadmap_ops(service)` dựng nó từ `service.repo.db`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from yofina_core.db import DataApi, Row
from yofina_core.errors import YofinaError
from yofina_ledger.roadmap_logic import db_business_error

SQL_GET_ROADMAP = "SELECT * FROM app_get_roadmap(CAST(:uid AS text), CAST(:version AS integer), CAST(:which AS text))"
SQL_LIST_VERSIONS = (
    "SELECT * FROM app_list_roadmap_versions(CAST(:uid AS text), CAST(:lim AS integer))"
)
SQL_GET_JOB = "SELECT * FROM app_get_roadmap_job(CAST(:uid AS text), CAST(:job_id AS uuid))"
SQL_LIST_FLAGS = "SELECT * FROM app_list_behavior_flags(CAST(:uid AS text), CAST(:status AS text), CAST(:lim AS integer))"
SQL_SAVE = (
    "SELECT * FROM app_save_roadmap(CAST(:uid AS text), CAST(:reason_code AS text), CAST(:reason_text AS text), "
    "CAST(:reason_detail AS jsonb), CAST(:flag AS uuid), CAST(:based_on AS integer), CAST(:feasibility AS text), "
    "CAST(:app_date AS date), CAST(:plan AS jsonb), CAST(:rules_version AS text), CAST(:status AS text), "
    "CAST(:trace_id AS text))"
)
SQL_SET_STEP = (
    "SELECT * FROM app_set_roadmap_step_state(CAST(:uid AS text), CAST(:version AS integer), CAST(:step_id AS text), "
    "CAST(:status AS text), CAST(:edited AS boolean))"
)
SQL_DECIDE_VERSION = "SELECT * FROM app_decide_roadmap_version(CAST(:uid AS text), CAST(:version AS integer), CAST(:decision AS text))"
#: ghi cả `step_states` của bản vừa lưu (mang trạng thái các bước sang bản mới, giữ nguyên `decided_at` cũ); `yofina_app` chỉ được
#: UPDATE `status`, `step_states`, `updated_at` của `roadmaps`.
SQL_SET_STATES = (
    "UPDATE roadmaps SET step_states = CAST(:states AS jsonb), updated_at = now() "
    "WHERE user_id = :uid AND version = CAST(:version AS integer)"
)
#: dấu hiệu đổi hành vi đã được một phiên bản lộ trình dùng: `confirmed` -> `applied` (idempotent: bản đã `applied` không đổi)
SQL_APPLY_FLAG = (
    "UPDATE behavior_flags SET status = 'applied', applied_at = now(), updated_at = now() "
    "WHERE user_id = :uid AND id = CAST(:id AS uuid) AND status = 'confirmed'"
)
SQL_AUDIT = (
    "INSERT INTO audit_events (user_id, trace_id, event_type, tool, outcome, code, params, details) "
    "VALUES (:uid, :trace_id, :event_type, :tool, 'ok', NULL, CAST(:params AS jsonb), CAST(:details AS jsonb))"
)
#: phản hồi của người dùng (cùng bảng `feedback` với `POST /feedback`): khóa duy nhất (user, trace, khối, phương án). Trace của thao tác
#: đã có dòng audit cùng transaction nên `GET /traces/{id}` biết nó.
SQL_FEEDBACK = (
    "INSERT INTO feedback (user_id, trace_id, block_id, option_id, decision, reason) "
    "VALUES (:uid, :trace_id, :block_id, :option_id, :decision, :reason) "
    "ON CONFLICT (user_id, trace_id, block_id, option_id) DO UPDATE SET decision = EXCLUDED.decision, "
    "reason = EXCLUDED.reason, updated_at = now()"
)
#: một người dùng tối đa MỘT job đang chạy (chỉ mục duy nhất một phần): job thứ hai không chèn được và không trả dòng nào
SQL_INSERT_JOB = (
    "INSERT INTO roadmap_jobs (user_id, trigger, alternative_id, note, based_on_version) "
    "VALUES (:uid, 'user_request', :alt, :note, CAST(:based_on AS integer)) ON CONFLICT DO NOTHING RETURNING id"
)

FLAGS_LIMIT = 50
VERSIONS_LIMIT = 50


def roadmap_block_id(trace_id: str, version: int) -> str:
    """Id của khối `roadmap` (`roadmap:{trace_id}:v{version}`): `block_id` của dòng `feedback`."""
    return f"roadmap:{trace_id}:v{version}"


def save_in_tx(
    tx: Any,
    user_id: str,
    *,
    reason_code: str,
    reason_text: str,
    reason_detail: Sequence[Mapping[str, str]] | None,
    behavior_flag_id: str | None,
    based_on_version: int | None,
    feasibility: str,
    app_date: Any,
    plan: Mapping[str, Any],
    rules_version: str,
    status: str,
    trace_id: str | None,
    step_states: Mapping[str, Any] | None = None,
    apply_flag: bool = True,
) -> Row:
    """Lưu MỘT phiên bản trong transaction `tx` đang mở (`app_save_roadmap`), rồi ghi `step_states` mang từ bản gốc sang và đánh dấu dấu
    hiệu đổi hành vi đã dùng (`apply_flag`). Dùng chung cho tool, REST và seed persona (seed nằm trong transaction đặt lại demo)."""
    saved = tx.execute(
        SQL_SAVE,
        {
            "uid": user_id,
            "reason_code": reason_code,
            "reason_text": reason_text,
            "reason_detail": list(reason_detail) if reason_detail else None,
            "flag": behavior_flag_id,
            "based_on": based_on_version,
            "feasibility": feasibility,
            "app_date": app_date,
            "plan": dict(plan),
            "rules_version": rules_version,
            "status": status,
            "trace_id": trace_id,
        },
    )[0]
    if step_states:
        tx.execute(
            SQL_SET_STATES,
            {"uid": user_id, "version": saved["version"], "states": dict(step_states)},
        )
    if behavior_flag_id and apply_flag:
        tx.execute(SQL_APPLY_FLAG, {"uid": user_id, "id": behavior_flag_id})
    return saved


def set_step_in_tx(
    tx: Any, user_id: str, *, version: int, step_id: str, status: str, edited: bool | None
) -> Row:
    """Chấp nhận, từ chối hoặc đưa về chờ MỘT bước trong transaction `tx` (`app_set_roadmap_step_state`)."""
    return tx.execute(
        SQL_SET_STEP,
        {
            "uid": user_id,
            "version": version,
            "step_id": step_id,
            "status": status,
            "edited": edited,
        },
    )[0]


@contextmanager
def _business_errors() -> Iterator[None]:
    """Lỗi nghiệp vụ của hàm SQL -> `YofinaError` đúng mã (còn lại giữ nguyên)."""
    try:
        yield
    except YofinaError as exc:
        mapped = db_business_error(exc)
        if mapped is None:
            raise
        raise mapped from exc


class RoadmapRepo:
    def __init__(self, db: DataApi) -> None:
        self.db = db

    # --- đọc ----------------------------------------------------------------------------------------------
    def get_roadmap(
        self, user_id: str, version: int | None = None, which: str = "active"
    ) -> Row | None:
        """MỘT phiên bản. `version` có thì đúng bản đó (không có thì None); không thì theo `which`: `active` (không có bản đang dùng
        thì bản mới nhất), `proposed` (không có thì None), `latest`. RLS nên bản của người khác ra None."""
        rows = self.db.query(
            SQL_GET_ROADMAP, {"uid": user_id, "version": version, "which": which}, max_rows=1
        )
        return rows[0] if rows else None

    def list_versions(self, user_id: str, limit: int = 20) -> list[Row]:
        return self.db.query(
            SQL_LIST_VERSIONS, {"uid": user_id, "lim": limit}, max_rows=VERSIONS_LIMIT
        )

    def get_job(self, user_id: str, job_id: str | None = None) -> Row | None:
        """Job của CHÍNH người gọi theo id; không nêu id thì job mới nhất."""
        rows = self.db.query(SQL_GET_JOB, {"uid": user_id, "job_id": job_id}, max_rows=1)
        return rows[0] if rows else None

    def list_behavior_flags(self, user_id: str, status: str | None = None) -> list[Row]:
        return self.db.query(
            SQL_LIST_FLAGS,
            {"uid": user_id, "status": status, "lim": FLAGS_LIMIT},
            max_rows=FLAGS_LIMIT,
        )

    # --- ghi: một phiên bản mới ------------------------------------------------------------------------------
    def save_roadmap(
        self,
        user_id: str,
        *,
        reason_code: str,
        reason_text: str,
        reason_detail: Sequence[Mapping[str, str]] | None,
        behavior_flag_id: str | None,
        based_on_version: int | None,
        feasibility: str,
        app_date: Any,
        plan: Mapping[str, Any],
        rules_version: str,
        status: str,
        trace_id: str | None,
        step_states: Mapping[str, Any] | None = None,
        audit: Mapping[str, Any] | None = None,
        feedback: Mapping[str, Any] | None = None,
    ) -> Row:
        """Lưu MỘT phiên bản (nguyên tử trong DB, xem `app_save_roadmap`), rồi trong CÙNG transaction: ghi `step_states` mang từ bản
        gốc sang (nếu có), đánh dấu dấu hiệu đổi hành vi đã dùng, ghi `audit_events` và (nếu có) `feedback`. Trả dòng
        `(id, version, status, created_at)`."""
        with _business_errors(), self.db.transaction(user_id) as tx:
            saved = save_in_tx(
                tx,
                user_id,
                reason_code=reason_code,
                reason_text=reason_text,
                reason_detail=reason_detail,
                behavior_flag_id=behavior_flag_id,
                based_on_version=based_on_version,
                feasibility=feasibility,
                app_date=app_date,
                plan=plan,
                rules_version=rules_version,
                status=status,
                trace_id=trace_id,
                step_states=step_states,
            )
            self._audit(tx, user_id, trace_id, audit, saved)
            self._feedback(tx, user_id, trace_id, feedback, saved["version"])
        return saved

    # --- ghi: đổi trạng thái ---------------------------------------------------------------------------------
    def set_step_state(
        self,
        user_id: str,
        *,
        version: int,
        step_id: str,
        status: str,
        edited: bool | None,
        trace_id: str,
        audit: Mapping[str, Any],
        feedback: Mapping[str, Any] | None,
    ) -> Row:
        """Chấp nhận, từ chối hoặc đưa về chờ MỘT bước (`app_set_roadmap_step_state`) cùng audit và feedback, một transaction."""
        with _business_errors(), self.db.transaction(user_id) as tx:
            row = set_step_in_tx(
                tx, user_id, version=version, step_id=step_id, status=status, edited=edited
            )
            self._audit(tx, user_id, trace_id, audit, row)
            self._feedback(tx, user_id, trace_id, feedback, version)
        return row

    def decide_version(
        self,
        user_id: str,
        *,
        version: int,
        decision: str,
        trace_id: str,
        audit: Mapping[str, Any],
        feedback: Mapping[str, Any] | None,
    ) -> Row:
        """ "Dùng bản mới" hoặc "Giữ bản cũ" với bản chờ (`app_decide_roadmap_version`) cùng audit và feedback, một transaction."""
        with _business_errors(), self.db.transaction(user_id) as tx:
            row = tx.execute(
                SQL_DECIDE_VERSION, {"uid": user_id, "version": version, "decision": decision}
            )[0]
            self._audit(tx, user_id, trace_id, audit, row)
            self._feedback(tx, user_id, trace_id, feedback, version)
        return row

    def create_job(
        self,
        user_id: str,
        *,
        alternative_id: str | None,
        note: str | None,
        based_on_version: int | None,
        trace_id: str,
        audit: Mapping[str, Any],
    ) -> str | None:
        """Ghi một job sinh lại (`user_request`, `queued`). Trả id job mới, hoặc None khi người dùng đã có một job đang chạy (chỉ mục duy
        nhất một phần từ chối) và khi đó không ghi gì thêm (kể cả audit)."""
        with self.db.transaction(user_id) as tx:
            rows = tx.execute(
                SQL_INSERT_JOB,
                {
                    "uid": user_id,
                    "alt": alternative_id,
                    "note": note,
                    "based_on": based_on_version,
                },
            )
            if not rows:
                return None
            self._audit(tx, user_id, trace_id, audit, {"job_id": str(rows[0]["id"])})
        return str(rows[0]["id"])

    # --- phần chung ------------------------------------------------------------------------------------------
    @staticmethod
    def _audit(
        tx: Any,
        user_id: str,
        trace_id: str | None,
        audit: Mapping[str, Any] | None,
        saved: Mapping[str, Any],
    ) -> None:
        if audit is None:
            return
        extra = {
            k: str(saved[k]) if k == "id" else saved[k]
            for k in ("id", "version", "status")
            if k in saved
        }
        if "id" in extra:
            extra["roadmap_id"] = extra.pop("id")
        extra.update({k: v for k, v in saved.items() if k == "job_id"})
        tx.execute(
            SQL_AUDIT,
            {
                "uid": user_id,
                "trace_id": trace_id,
                "event_type": audit["event_type"],
                "tool": audit.get("tool"),
                "params": audit.get("params"),
                "details": {**(audit.get("details") or {}), **extra},
            },
        )

    @staticmethod
    def _feedback(
        tx: Any,
        user_id: str,
        trace_id: str | None,
        feedback: Mapping[str, Any] | None,
        version: int,
    ) -> None:
        if feedback is None or trace_id is None:
            return
        tx.execute(
            SQL_FEEDBACK,
            {
                "uid": user_id,
                "trace_id": trace_id,
                "block_id": roadmap_block_id(trace_id, int(version)),
                "option_id": feedback["option_id"],
                "decision": feedback["decision"],
                "reason": feedback.get("reason"),
            },
        )
