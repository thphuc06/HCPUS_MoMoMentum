"""Truy cập Aurora của luồng nạp: toàn bộ SQL nằm ở đây, qua `yofina_core.db.DataApi`.

- **Đọc và ghi từng bước**: hàm `app_*` của migration 0050 (một lệnh gọi, tự đặt `app.user_id`, RLS áp theo người dùng).
- **Chốt dòng (`confirm_rows`)**: MỘT transaction (`DataApi.transaction(user_id)`): khóa job, ghi mỗi dòng được duyệt vào `transactions` với
  `funding_source = 'external'` (không đụng bảng `jars`), đánh dấu dòng, chuyển job sang `done`, ghi audit. Mọi câu lệnh ghi đều có `user_id = :uid`.
- Không câu lệnh nào chứa ảnh hay văn bản thô: chỉ trường đã che PII.
- Mỗi lệnh gọi chèn hay tìm khớp chia lô tối đa `BATCH` dòng (giới hạn kích thước một yêu cầu Data API).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from yofina_core.db import DataApi, Row
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.ingest import LEDGER_SOURCE, coverage_ratio
from yofina_core.params import TxTypeInfo, fold_text
from yofina_ingest.context import Rule

BATCH = 100

SQL_USER = "SELECT * FROM app_get_user(CAST(:uid AS text))"
SQL_JARS = "SELECT * FROM app_list_jars(CAST(:uid AS text))"
SQL_PAYEES = "SELECT * FROM app_list_payees(CAST(:uid AS text), 100)"
SQL_TX_TYPES = (
    "SELECT tx_type, label, direction, default_jar_code, system_role, is_selectable, is_person_transfer "
    "FROM tx_type_map ORDER BY sort_order, tx_type LIMIT 100"
)
SQL_RULES = (
    "SELECT r.merchant_key, p.name AS payee_name, r.jar_code FROM category_rules r "
    "LEFT JOIN payees p ON p.user_id = r.user_id AND p.id = r.payee_id "
    "WHERE r.user_id = :uid AND r.scope = 'always' ORDER BY r.hit_count DESC, r.created_at LIMIT 200"
)
SQL_CREATE_JOB = (
    "SELECT * FROM app_create_ingest_job(CAST(:uid AS text), CAST(:id AS uuid), CAST(:kind AS text), "
    "CAST(:key AS text), CAST(:mime AS text), CAST(:size AS bigint))"
)
SQL_FIND_BY_CONTENT = (
    "SELECT * FROM app_find_ingest_job_by_content(CAST(:uid AS text), CAST(:sha AS text))"
)
SQL_UPDATE_JOB = (
    "SELECT * FROM app_update_ingest_job(CAST(:uid AS text), CAST(:id AS uuid), CAST(:status AS text), "
    "CAST(:progress AS integer), CAST(:patch AS jsonb))"
)
SQL_INSERT_ROWS = "SELECT * FROM app_insert_ingest_rows(CAST(:uid AS text), CAST(:job AS uuid), CAST(:rows AS jsonb))"
SQL_GET_JOB = (
    "SELECT * FROM app_get_ingest_job(CAST(:uid AS text), CAST(:id AS uuid), CAST(:lim AS integer))"
)
SQL_LIST_JOBS = "SELECT * FROM app_list_ingest_jobs(CAST(:uid AS text), CAST(:lim AS integer))"
SQL_SET_ROW_JAR = "SELECT * FROM app_set_ingest_row_jar(CAST(:uid AS text), CAST(:row AS uuid), CAST(:jar AS text))"
SQL_ROW_STATE = (
    "SELECT r.kind, r.review_status, j.status AS job_status FROM ingest_rows r "
    "JOIN ingest_jobs j ON j.user_id = r.user_id AND j.id = r.job_id "
    "WHERE r.id = CAST(:row AS uuid) AND r.user_id = :uid LIMIT 1"
)
SQL_GRANT_CONSENT = "SELECT * FROM app_grant_consent(CAST(:uid AS text), CAST(:source AS text), CAST(:version AS text))"
SQL_CONSENTS = "SELECT * FROM app_get_consents(CAST(:uid AS text))"
SQL_COVERAGE = (
    "SELECT * FROM app_get_data_coverage(CAST(:uid AS text), CAST(:now AS timestamptz), CAST(:tz AS text), "
    "CAST(:win AS integer))"
)
SQL_MATCHES = "SELECT * FROM app_find_ingest_matches(CAST(:uid AS text), CAST(:rows AS jsonb), CAST(:win AS integer))"
# Đối tác (cùng định nghĩa `who` của `app_find_ingest_matches`: tên người nhận đã lưu, không thì merchant) và ghi chú của các giao dịch
# vừa khớp, để worker phân biệt đối tác đã che hay rỗng ("không biết") với đối tác khác và so nội dung (`worker.is_duplicate_match`).
SQL_MATCHED_TX = (
    "SELECT t.id AS transaction_id, coalesce(p.name, t.merchant) AS merchant, t.note FROM transactions t "
    "LEFT JOIN payees p ON p.user_id = t.user_id AND p.id = t.payee_id "
    "WHERE t.user_id = :uid AND t.id IN (SELECT CAST(x AS uuid) FROM jsonb_array_elements_text(CAST(:ids AS jsonb)) AS x) "
    "LIMIT 2000"
)

# Tự chữa sau khi đặt lại demo bằng Lambda ledger CŨ (chưa xóa bảng nạp): job nào có dòng đã duyệt mà giao dịch của dòng không còn
# thì xóa cả job (dòng đi theo, ON DELETE CASCADE) để nạp lại cùng tệp không vướng khóa khử trùng hay trùng nội dung; rồi xóa job
# `done` không còn dòng nào.
SQL_HEAL_ORPHAN_JOBS = (
    "DELETE FROM ingest_jobs j WHERE j.user_id = :uid AND j.id IN ("
    "SELECT r.job_id FROM ingest_rows r WHERE r.user_id = :uid AND r.review_status = 'approved' "
    "AND NOT EXISTS (SELECT 1 FROM transactions t WHERE t.id = r.transaction_id)) RETURNING j.id"
)
SQL_HEAL_EMPTY_JOBS = (
    "DELETE FROM ingest_jobs j WHERE j.user_id = :uid AND j.status = 'done' "
    "AND NOT EXISTS (SELECT 1 FROM ingest_rows r WHERE r.job_id = j.id) RETURNING j.id"
)

SQL_LOCK_JOB = "SELECT status, source_kind FROM ingest_jobs WHERE id = CAST(:job AS uuid) AND user_id = :uid FOR UPDATE"
SQL_JOB_ROWS = (
    "SELECT id, seq, kind, app_date, amount_vnd, counterparty, description, suggested_jar_code, jar_confidence, "
    "jar_source, tx_type, review_status, dedupe_key FROM ingest_rows "
    "WHERE job_id = CAST(:job AS uuid) AND user_id = :uid ORDER BY seq LIMIT 501 FOR UPDATE"
)
SQL_JAR_CODES = (
    "SELECT code, name, kind FROM jars WHERE user_id = :uid ORDER BY sort_order, code LIMIT 40"
)
SQL_INSERT_TX = (
    "WITH src AS (SELECT CAST(e ->> 'tx_id' AS uuid) AS id, e ->> 'kind' AS kind, CAST(e ->> 'app_date' AS date) AS app_date, "
    "e ->> 'jar' AS jar, CAST(e ->> 'signed' AS numeric) AS signed, e ->> 'merchant' AS merchant, e ->> 'note' AS note, "
    "e ->> 'tx_type' AS tx_type, e ->> 'dedupe_key' AS dedupe_key, e ->> 'classified_by' AS classified_by "
    "FROM jsonb_array_elements(CAST(:rows AS jsonb)) AS x(e)), "
    "ins AS (INSERT INTO transactions (id, user_id, occurred_at, app_date, kind, jar_code, amount_vnd, merchant, note, "
    "source, tx_type, funding_source, dedupe_key, classified_by, needs_review) "
    "SELECT s.id, CAST(:uid AS text), CAST(:occurred_at AS timestamptz), s.app_date, s.kind, s.jar, s.signed, s.merchant, "
    "s.note, CAST(:source AS text), s.tx_type, 'external', s.dedupe_key, s.classified_by, false FROM src s "
    "ON CONFLICT (user_id, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING RETURNING id) "
    "SELECT count(*) AS n FROM ins"
)
SQL_APPROVE_ROWS = (
    "WITH s AS (SELECT CAST(e ->> 'row_id' AS uuid) AS row_id, CAST(e ->> 'tx_id' AS uuid) AS tx_id, e ->> 'jar' AS jar, "
    "e ->> 'jar_source' AS jar_source, CAST(e ->> 'jar_confidence' AS numeric) AS jar_conf "
    "FROM jsonb_array_elements(CAST(:rows AS jsonb)) AS x(e)), "
    "u AS (UPDATE ingest_rows r SET review_status = 'approved', transaction_id = s.tx_id, suggested_jar_code = s.jar, "
    "jar_source = s.jar_source, jar_confidence = s.jar_conf, updated_at = now() FROM s "
    "WHERE r.id = s.row_id AND r.user_id = :uid AND r.job_id = CAST(:job AS uuid) "
    "AND r.review_status IN ('auto_added', 'pending') RETURNING r.id) "
    "SELECT count(*) AS n FROM u"
)
SQL_REJECT_REST = (
    "WITH u AS (UPDATE ingest_rows SET review_status = 'rejected', updated_at = now() "
    "WHERE job_id = CAST(:job AS uuid) AND user_id = :uid AND review_status IN ('auto_added', 'pending') RETURNING id) "
    "SELECT count(*) AS n FROM u"
)
# Bộ phân loại phase 4 cho dòng nạp (`yofina_ingest.classify`): số giao dịch chi trước đó theo (đối tác, hũ) và số luật `once` theo khóa đối
# tác, cho MỌI đối tác của một tệp trong một câu (cùng định nghĩa với `SQL_CONTEXT` của `yofina_classify.repo`, chỉ khác là gom nhiều đối tác).
SQL_MERCHANT_HISTORY = (
    "SELECT lower(t.merchant) AS merchant, t.jar_code, count(*) AS n FROM transactions t "
    "JOIN jars j ON j.user_id = t.user_id AND j.code = t.jar_code "
    "WHERE t.user_id = :uid AND t.kind = 'expense' AND j.system_role IS NULL "
    "AND lower(t.merchant) IN (SELECT lower(x) FROM jsonb_array_elements_text(CAST(:merchants AS jsonb)) AS x) "
    "GROUP BY lower(t.merchant), t.jar_code LIMIT 2000"
)
SQL_MERCHANT_CORRECTIONS = (
    "SELECT merchant_key, count(*) AS n FROM category_rules WHERE user_id = :uid AND scope = 'once' "
    "AND merchant_key IN (SELECT x FROM jsonb_array_elements_text(CAST(:keys AS jsonb)) AS x) "
    "GROUP BY merchant_key LIMIT 500"
)
SQL_AUDIT = (
    "INSERT INTO audit_events (user_id, trace_id, event_type, tool, outcome, code, params, details) "
    "VALUES (:uid, :trace_id, 'confirm_rows', 'confirm_rows', 'ok', NULL, CAST(:params AS jsonb), CAST(:details AS jsonb))"
)


def _chunks(items: Sequence[Any], size: int = BATCH):
    for i in range(0, len(items), size):
        yield i, items[i : i + size]


@dataclass(frozen=True)
class UserContext:
    clock_offset_days: int
    display_name: str | None


@dataclass(frozen=True)
class ConfirmOutcome:
    rows_added: int
    external_spend_added_vnd: int
    external_income_added_vnd: int
    jar_codes: tuple[str, ...]
    coverage_before: float | None
    coverage_after: float | None
    transaction_ids: tuple[str, ...]


class IngestRepo:
    def __init__(self, db: DataApi) -> None:
        self.db = db

    # --- ngữ cảnh người dùng -------------------------------------------------------------------------------------------------
    def user(self, uid: str) -> UserContext | None:
        rows = self.db.query(SQL_USER, {"uid": uid}, max_rows=1)
        if not rows:
            return None
        return UserContext(int(rows[0]["clock_offset_days"] or 0), rows[0].get("display_name"))

    def jar_rows(self, uid: str) -> list[Row]:
        return self.db.query(SQL_JARS, {"uid": uid}, max_rows=40)

    def payee_names(self, uid: str) -> list[str]:
        return [str(r["name"]) for r in self.db.query(SQL_PAYEES, {"uid": uid}, max_rows=100)]

    def tx_types(self) -> dict[str, TxTypeInfo]:
        return {
            r["tx_type"]: TxTypeInfo(
                tx_type=r["tx_type"],
                direction=r["direction"],
                default_jar_code=r["default_jar_code"],
                system_role=r["system_role"],
                label=r["label"],
                is_selectable=bool(r["is_selectable"]),
                is_person_transfer=bool(r.get("is_person_transfer", False)),
            )
            for r in self.db.query(SQL_TX_TYPES, max_rows=100)
        }

    def rules(self, uid: str) -> list[Rule]:
        with self.db.transaction(uid) as tx:
            rows = tx.execute(SQL_RULES, {"uid": uid})
        out = []
        for r in rows:
            key = r.get("merchant_key") or fold_text(r.get("payee_name") or "")
            if key:
                out.append(Rule(key=str(key), jar_code=str(r["jar_code"])))
        return out

    # --- job -----------------------------------------------------------------------------------------------------------------
    def create_job(
        self, uid: str, job_id: str, kind: str, s3_key: str, mime: str, size_bytes: int | None
    ) -> Row:
        rows = self.db.query(
            SQL_CREATE_JOB,
            {
                "uid": uid,
                "id": job_id,
                "kind": kind,
                "key": s3_key,
                "mime": mime,
                "size": size_bytes,
            },
            max_rows=1,
        )
        return rows[0]

    def find_job_by_content(self, uid: str, sha: str) -> Row | None:
        rows = self.db.query(SQL_FIND_BY_CONTENT, {"uid": uid, "sha": sha}, max_rows=1)
        return rows[0] if rows else None

    def update_job(
        self,
        uid: str,
        job_id: str,
        status: str,
        progress: int | None = None,
        patch: Mapping[str, Any] | None = None,
    ) -> Row | None:
        """Chuyển trạng thái hợp lệ (xem `app_update_ingest_job`). None = không có job hoặc chuyển sai (không đổi gì)."""
        rows = self.db.query(
            SQL_UPDATE_JOB,
            {
                "uid": uid,
                "id": job_id,
                "status": status,
                "progress": progress,
                "patch": dict(patch or {}),
            },
            max_rows=1,
        )
        return rows[0] if rows else None

    def get_job(self, uid: str, job_id: str, row_limit: int = 200) -> tuple[Row, list[Row]] | None:
        out = self.db.query(SQL_GET_JOB, {"uid": uid, "id": job_id, "lim": row_limit}, max_rows=501)
        job = next((r["payload"] for r in out if r["section"] == "job"), None)
        if job is None:
            return None
        return job, [r["payload"] for r in out if r["section"] == "row"]

    def list_jobs(self, uid: str, limit: int) -> list[Row]:
        return self.db.query(SQL_LIST_JOBS, {"uid": uid, "lim": limit}, max_rows=20)

    def insert_rows(
        self, uid: str, job_id: str, rows: Sequence[Mapping[str, Any]]
    ) -> dict[int, str]:
        """Chèn dòng đã che PII; trả `seq -> row_id` của các dòng thật sự được chèn (trùng khóa khử trùng thì bỏ qua)."""
        ids: dict[int, str] = {}
        for _, chunk in _chunks(rows):
            for r in self.db.query(
                SQL_INSERT_ROWS, {"uid": uid, "job": job_id, "rows": list(chunk)}, max_rows=BATCH
            ):
                ids[int(r["seq"])] = str(r["row_id"])
        return ids

    def find_matches(
        self, uid: str, candidates: Sequence[Mapping[str, Any]], window_days: int
    ) -> list[Row]:
        out: list[Row] = []
        for _, chunk in _chunks(candidates):
            out.extend(
                self.db.query(
                    SQL_MATCHES,
                    {"uid": uid, "rows": list(chunk), "win": window_days},
                    max_rows=2000,
                )
            )
        return out

    def matched_transactions(self, uid: str, tx_ids: Sequence[str]) -> dict[str, Row]:
        """`transaction_id -> {merchant, note}` của các giao dịch đã có mà `find_matches` trả (RLS theo người dùng)."""
        out: dict[str, Row] = {}
        for _, chunk in _chunks(list(tx_ids), 500):
            with self.db.transaction(uid) as tx:
                for r in tx.execute(SQL_MATCHED_TX, {"uid": uid, "ids": list(chunk)}):
                    out[str(r["transaction_id"])] = r
        return out

    def set_row_jar(self, uid: str, row_id: str, jar: str) -> Row | None:
        rows = self.db.query(SQL_SET_ROW_JAR, {"uid": uid, "row": row_id, "jar": jar}, max_rows=1)
        return rows[0] if rows else None

    def row_state(self, uid: str, row_id: str) -> Row | None:
        """Loại dòng, trạng thái dòng và trạng thái job của một dòng (để báo đúng lý do khi không đổi được hũ)."""
        with self.db.transaction(uid) as tx:
            rows = tx.execute(SQL_ROW_STATE, {"row": row_id, "uid": uid})
        return rows[0] if rows else None

    # --- đồng ý ----------------------------------------------------------------------------------------------------------------
    def consents(self, uid: str) -> dict[str, Row]:
        return {r["source"]: r for r in self.db.query(SQL_CONSENTS, {"uid": uid}, max_rows=2)}

    def grant_consent(self, uid: str, source: str, version: str) -> Row:
        return self.db.query(
            SQL_GRANT_CONSENT, {"uid": uid, "source": source, "version": version}, max_rows=1
        )[0]

    # --- bộ phân loại phase 4 -------------------------------------------------------------------------------------------------
    def label_store(self) -> IngestLabelStore:
        return IngestLabelStore(self.db)

    # --- độ phủ và tự chữa ----------------------------------------------------------------------------------------------------
    def coverage_facts(self, uid: str, now: datetime, tz: str, window_days: int) -> Row | None:
        rows = self.db.query(
            SQL_COVERAGE, {"uid": uid, "now": now, "tz": tz, "win": window_days}, max_rows=1
        )
        return rows[0] if rows else None

    def heal_after_reset(self, uid: str) -> int:
        """Xóa job mồ côi sau khi ledger cũ đặt lại demo mà không xóa bảng nạp. Trả số job đã xóa."""
        with self.db.transaction(uid) as tx:
            n = len(tx.execute(SQL_HEAL_ORPHAN_JOBS, {"uid": uid}))
            n += len(tx.execute(SQL_HEAL_EMPTY_JOBS, {"uid": uid}))
        return n

    # --- chốt dòng ---------------------------------------------------------------------------------------------------------------
    def confirm_rows(
        self,
        uid: str,
        *,
        job_id: str,
        approvals: Mapping[str, str | None],
        reject_ids: Sequence[str],
        now: datetime,
        tz: str,
        window_days: int,
        trace_id: str,
        params: Mapping[str, Any],
    ) -> ConfirmOutcome:
        """Ghi các dòng được duyệt vào sổ cái và đóng job, trong MỘT transaction. `approvals`: `row_id -> hũ người dùng chọn`
        (None = giữ hũ đề xuất). Lỗi nghiệp vụ ném `YofinaError` và transaction rollback (không ghi gì)."""
        with self.db.transaction(uid) as tx:
            job = tx.execute(SQL_LOCK_JOB, {"job": job_id, "uid": uid})
            if not job:
                raise YofinaError(ErrorCode.INGEST_JOB_NOT_FOUND, "Không tìm thấy lần nạp này.")
            if job[0]["status"] == "done":
                raise YofinaError(
                    ErrorCode.ALREADY_APPLIED, "Lần nạp này đã được chốt rồi. Chưa ghi thêm gì."
                )
            if job[0]["status"] != "review":
                raise YofinaError(
                    ErrorCode.INGEST_JOB_NOT_READY,
                    "Lần nạp này chưa đọc xong hoặc không còn chốt được.",
                )
            rows = {str(r["id"]): r for r in tx.execute(SQL_JOB_ROWS, {"job": job_id, "uid": uid})}
            jars = {r["code"]: r for r in tx.execute(SQL_JAR_CODES, {"uid": uid})}
            for rid in [*approvals, *reject_ids]:
                if rid not in rows:
                    raise YofinaError(ErrorCode.PARAMS_INVALID, "Có dòng không thuộc lần nạp này.")
            tx_rows: list[dict[str, Any]] = []
            approve_rows: list[dict[str, Any]] = []
            spend = income = 0
            affected: list[str] = []
            for rid, chosen in approvals.items():
                r = rows[rid]
                if r["review_status"] not in ("auto_added", "pending"):
                    raise YofinaError(
                        ErrorCode.PARAMS_INVALID,
                        "Dòng đã được xử lý hoặc là dòng trùng nên không chốt được.",
                    )
                amount = int(r["amount_vnd"])
                jar = r["suggested_jar_code"]
                jar_source, jar_conf = r["jar_source"], r["jar_confidence"]
                classified: str | None = None
                if r["kind"] == "expense":
                    if chosen and chosen != jar:
                        jar, jar_source, jar_conf = chosen, "user", 1
                    if not jar:
                        raise YofinaError(
                            ErrorCode.PARAMS_INVALID, "Dòng chi cần chọn hũ trước khi ghi."
                        )
                    if jar not in jars or jars[jar]["kind"] == "system":
                        raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ đã chọn.")
                    classified = {
                        "type_map": "type_map",
                        "rule": "rule",
                        "model": "llm",
                        "user": "user",
                    }[str(jar_source)]
                    spend += amount
                    if jar not in affected:
                        affected.append(jar)
                else:
                    jar, jar_source, jar_conf = None, None, None
                    income += amount
                tx_id = str(uuid.uuid4())
                tx_rows.append(
                    {
                        "tx_id": tx_id,
                        "kind": r["kind"],
                        "app_date": _date_text(r["app_date"]),
                        "jar": jar,
                        "signed": -amount if r["kind"] == "expense" else amount,
                        "merchant": r["counterparty"],
                        "note": r["description"],
                        "tx_type": r["tx_type"]
                        or ("other_expense" if r["kind"] == "expense" else "income_other"),
                        "dedupe_key": r["dedupe_key"],
                        "classified_by": classified,
                    }
                )
                approve_rows.append(
                    {
                        "row_id": rid,
                        "tx_id": tx_id,
                        "jar": jar,
                        "jar_source": jar_source,
                        "jar_confidence": None if jar_conf is None else float(jar_conf),
                    }
                )
            before = coverage_ratio(self._facts(tx, uid, now, tz, window_days))
            for _, chunk in _chunks(tx_rows):
                n = tx.execute(
                    SQL_INSERT_TX,
                    {"uid": uid, "rows": list(chunk), "occurred_at": now, "source": LEDGER_SOURCE},
                )[0]["n"]
                if int(n) != len(chunk):  # một khóa khử trùng đã có trong sổ cái: đã chốt trước đó
                    raise YofinaError(
                        ErrorCode.ALREADY_APPLIED,
                        "Có dòng đã được ghi vào lịch sử rồi. Chưa ghi thêm gì.",
                    )
            for _, chunk in _chunks(approve_rows):
                n = tx.execute(SQL_APPROVE_ROWS, {"uid": uid, "job": job_id, "rows": list(chunk)})[
                    0
                ]["n"]
                if int(n) != len(chunk):
                    raise YofinaError(
                        ErrorCode.ALREADY_APPLIED, "Dòng đã được xử lý. Chưa ghi thêm gì."
                    )
            tx.execute(SQL_REJECT_REST, {"uid": uid, "job": job_id})
            after = coverage_ratio(self._facts(tx, uid, now, tz, window_days))
            patch: dict[str, Any] = {}
            if before is not None:
                patch["coverage_before"] = before
            if after is not None:
                patch["coverage_after"] = after
            done = tx.execute(
                SQL_UPDATE_JOB,
                {"uid": uid, "id": job_id, "status": "done", "progress": 100, "patch": patch},
            )
            if not done:
                raise YofinaError(ErrorCode.ALREADY_APPLIED, "Lần nạp này đã được chốt rồi.")
            tx.execute(
                SQL_AUDIT,
                {
                    "uid": uid,
                    "trace_id": trace_id,
                    "params": dict(params),
                    "details": {
                        "rows_added": len(tx_rows),
                        "rows_rejected": len(rows) - len(tx_rows),
                        "spend_vnd": spend,
                        "income_vnd": income,
                    },
                },
            )
        return ConfirmOutcome(
            rows_added=len(tx_rows),
            external_spend_added_vnd=spend,
            external_income_added_vnd=income,
            jar_codes=tuple(affected),
            coverage_before=before,
            coverage_after=after,
            transaction_ids=tuple(t["tx_id"] for t in tx_rows),
        )

    @staticmethod
    def _facts(tx: Any, uid: str, now: datetime, tz: str, window_days: int) -> Row | None:
        rows = tx.execute(SQL_COVERAGE, {"uid": uid, "now": now, "tz": tz, "win": window_days})
        return rows[0] if rows else None


class IngestLabelStore:
    """`yofina_ingest.classify.LabelStore` trên Aurora: nhãn k-NN qua `app_find_labeled_exact`, `app_knn_labeled` (0052, cùng
    `PgLabelIndex` của Lambda phân loại), lịch sử và số lần sửa theo đối tác bằng một câu cho cả tệp (RLS theo `app.user_id`)."""

    def __init__(self, db: DataApi) -> None:
        from yofina_classify.repo import PgLabelIndex

        self.db = db
        self._index = PgLabelIndex(db)

    def find_exact(self, user_id: str, text_norm: str) -> list[Any]:
        return self._index.find_exact(user_id, text_norm)

    def knn(self, user_id: str, vector: Sequence[float], k: int) -> list[Any]:
        return self._index.knn(user_id, vector, k)

    def history(self, user_id: str, merchants: Sequence[str]) -> dict[str, dict[str, int]]:
        unique = sorted({m.lower() for m in merchants if m})[:500]
        if not unique:
            return {}
        with self.db.transaction(user_id) as tx:
            rows = tx.execute(SQL_MERCHANT_HISTORY, {"uid": user_id, "merchants": unique})
        out: dict[str, dict[str, int]] = {}
        for r in rows:
            out.setdefault(str(r["merchant"]), {})[str(r["jar_code"])] = int(r["n"])
        return out

    def corrections(self, user_id: str, merchant_keys: Sequence[str]) -> dict[str, int]:
        unique = sorted({k for k in merchant_keys if k})[:500]
        if not unique:
            return {}
        with self.db.transaction(user_id) as tx:
            rows = tx.execute(SQL_MERCHANT_CORRECTIONS, {"uid": user_id, "keys": unique})
        return {str(r["merchant_key"]): int(r["n"]) for r in rows}


def _date_text(value: date | str) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)
