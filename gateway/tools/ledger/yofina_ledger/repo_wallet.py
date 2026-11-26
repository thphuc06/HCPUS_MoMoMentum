"""SQL của ví mô phỏng (phase 2): đọc gộp cho màn hình, bảng tra, và các thao tác ghi (mỗi thao tác MỘT transaction).

Quy ước (giống `repo.py`):
- Đọc qua hàm plpgsql `app_*` (một lệnh gọi, RLS theo `set_config` trong hàm) hoặc truy vấn bảng tra dùng chung.
- Ghi trong `DataApi.transaction(user_id)`: khóa dòng liên quan (`FOR UPDATE`), kiểm nghiệp vụ trên dòng đã khóa,
  rồi MỘT câu lệnh CTE biến đổi dữ liệu ghi sổ cái + số dư + audit. Mọi câu ghi đều ép `user_id = :uid`; RLS là lớp phụ.
- Nếu có `claim` (đề nghị `confirm_block_id`) thì CUỐI transaction chèn `confirm_resolutions` kèm biên nhận; trùng khóa
  thì ném ALREADY_APPLIED và cả transaction rollback (không ghi gì).
- Repo KHÔNG biết hợp đồng khối UI: trả `WriteResult` (sự kiện thật của lần ghi) cho service dựng biên nhận và sự kiện.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from yofina_core.db import DataApi, Row, Transaction
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.money import to_vnd
from yofina_core.params import ParamsError, fold_text, jar_commitments
from yofina_core.wallet import (
    OTHER_INCOME_JAR_CODE,
    TX_TYPE_JAR_TRANSFER,
    TX_TYPE_SALARY_SPLIT,
)
from yofina_ledger.jar_layout import onboarding_override

ALREADY_APPLIED_MESSAGE = "Đề nghị này đã được thực hiện rồi. Chưa ghi thêm gì."
CANCELLED_MESSAGE = "Đề nghị này đã bị hủy. Hãy hỏi lại nếu bạn vẫn muốn thực hiện."


@dataclass
class WriteResult:
    """Kết quả một lần ghi thành công (sự thật lấy từ DB trong cùng transaction)."""

    tool: str
    reference_id: str | None
    occurred_at: datetime
    app_date: date
    #: số dư SAU của các hũ bị đổi (code, name, balance_vnd); rỗng nếu không hũ nào đổi
    jars_after: list[dict[str, Any]] = field(default_factory=list)
    #: delta có dấu theo hũ (cho sự kiện `effects`)
    deltas: dict[str, int] = field(default_factory=dict)
    #: dữ kiện riêng của từng tool (nghĩa vụ, sự kiện lương, hồ sơ...)
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClaimSpec:
    """Đề nghị mà thao tác ghi này thực hiện; `receipt_for` dựng biên nhận (JSON gửi ra ngoài) từ kết quả."""

    conversation_id: str
    confirm_block_id: str
    receipt_for: Callable[[WriteResult], Mapping[str, Any]]


# --- đọc -----------------------------------------------------------------------------------------------------
SQL_OVERVIEW = "SELECT app_get_overview_with_purpose(:uid, CAST(:now AS timestamptz), :tz) AS data"
SQL_JAR_DETAIL = (
    "SELECT app_get_jar_detail_with_purpose(:uid, :jar, CAST(:now AS timestamptz), :tz) AS data"
)
SQL_LIST_TRANSACTIONS = (
    "SELECT * FROM app_list_transactions(CAST(:uid AS text), CAST(:jar AS text), CAST(:from_date AS date), "
    "CAST(:to_date AS date), CAST(:kind AS text), CAST(:tx_type AS text), CAST(:needs_review AS boolean), "
    "CAST(:cursor_at AS timestamptz), CAST(:cursor_id AS uuid), CAST(:lim AS integer))"
)
SQL_LIST_OBLIGATIONS = (
    "SELECT * FROM app_list_obligations(CAST(:uid AS text), CAST(:status AS text), CAST(:due_before AS date), "
    "CAST(:lim AS integer))"
)
SQL_LIST_PAYEES = "SELECT * FROM app_list_payees(:uid, CAST(:lim AS integer))"
SQL_CREDIT_LINE = "SELECT * FROM app_get_credit_line(:uid)"
SQL_SALARY_EVENTS = "SELECT * FROM app_list_salary_events(CAST(:uid AS text), CAST(:status AS text), CAST(:lim AS integer))"
SQL_CASHFLOW = "SELECT app_get_cashflow_summary(:uid, CAST(:from_date AS date), CAST(:to_date AS date)) AS data"
#: chuỗi chi theo ngày của từng hũ trong `win` ngày gần nhất: CHÍNH hàm ngữ cảnh mà Lambda forecast (LP phân bổ) đọc, chỉ lấy phần meta và hũ
SQL_SPEND_CONTEXT = (
    "SELECT section, jar_code, payload FROM app_get_forecast_context("
    "CAST(:uid AS text), CAST(:now AS timestamptz), CAST(:tz AS text), CAST(:win AS integer)) "
    "WHERE section IN ('meta', 'jar')"
)
SQL_UNCLASSIFIED = "SELECT * FROM app_get_unclassified(:uid, CAST(:lim AS integer))"
SQL_REVIEW_STATS = "SELECT * FROM app_get_review_stats(:uid)"
SQL_GET_TRANSACTION = "SELECT * FROM app_get_transaction(:uid, CAST(:id AS uuid))"
SQL_FORECAST_SUMMARIES = (
    "SELECT * FROM app_get_forecast_summaries(CAST(:uid AS text), CAST(:jar AS text))"
)
SQL_FORECAST_SERIES = "SELECT * FROM app_get_forecast_series(:uid, :jar)"
SQL_CONFIRM_BLOCK = "SELECT * FROM app_get_confirm_block(:uid, :conv, :bid)"
SQL_USER = "SELECT * FROM app_get_user(:uid)"
SQL_JAR_USAGE = "SELECT * FROM app_get_jar_usage(:uid)"

SQL_REF_TX_TYPES = (
    "SELECT tx_type, label, direction, default_jar_code, system_role, is_selectable, sort_order, "
    "is_person_transfer "
    "FROM tx_type_map ORDER BY sort_order, tx_type LIMIT 100"
)
SQL_REF_FEES = (
    "SELECT id, product_code, product_label, fee_type, amount_vnd, rate_percent, period, condition_code, "
    "condition_note, source_name, source_url, effective_from, effective_to "
    "FROM fee_schedules ORDER BY product_code, fee_type, effective_from DESC LIMIT 100"
)
SQL_ONBOARDING_TEMPLATES = (
    "SELECT t.code, t.name, t.color_key, t.icon_key, t.kind, "
    "coalesce(l.split_percent, t.default_split_percent) AS default_split_percent, "
    "CASE WHEN CAST(:layout AS jsonb) IS NULL THEN t.is_default ELSE l.code IS NOT NULL END AS is_default, "
    "coalesce(l.sort_order, t.sort_order) AS sort_order, "
    "CASE WHEN l.code IS NULL THEN t.purpose END AS purpose "
    "FROM jar_templates t LEFT JOIN "
    "jsonb_to_recordset(coalesce(CAST(:layout AS jsonb), '[]'::jsonb)) "
    "AS l(code text, split_percent numeric, sort_order smallint) ON l.code = t.code"
)
SQL_REF_TEMPLATES = SQL_ONBOARDING_TEMPLATES + " ORDER BY sort_order, code LIMIT 40"

# --- ghi: dùng chung --------------------------------------------------------------------------------------
SQL_AUDIT_TX = (
    "INSERT INTO audit_events (user_id, trace_id, event_type, tool, outcome, code, params, details) "
    "VALUES (:uid, :trace_id, :event_type, :tool, 'ok', NULL, CAST(:params AS jsonb), CAST(:details AS jsonb))"
)
SQL_CLAIM_DONE = (
    "INSERT INTO confirm_resolutions "
    "(user_id, confirm_block_id, conversation_id, transfer_id, receipt, status, action_tool) "
    "VALUES (:uid, :cbid, :conv, CAST(:ref AS uuid), CAST(:receipt AS jsonb), 'done', :tool) "
    "ON CONFLICT (user_id, confirm_block_id) DO NOTHING RETURNING id"
)
SQL_CLAIM_CANCELLED = (
    "INSERT INTO confirm_resolutions "
    "(user_id, confirm_block_id, conversation_id, transfer_id, receipt, status, action_tool) "
    "VALUES (:uid, :cbid, :conv, NULL, NULL, 'cancelled', NULL) "
    "ON CONFLICT (user_id, confirm_block_id) DO NOTHING RETURNING id, resolved_at"
)

# Cột chung của một dòng sổ cái do `record_transaction` ghi.
_TX_COLUMNS = (
    "(id, user_id, occurred_at, app_date, kind, jar_code, amount_vnd, merchant, note, source, tx_type, "
    "funding_source, payee_id, obligation_id, dedupe_key, classified_by, needs_review)"
)
_TX_VALUES = (
    "(CAST(:tx_id AS uuid), :uid, CAST(:occurred_at AS timestamptz), CAST(:app_date AS date), :kind, :jar, "
    "CAST(:signed AS numeric), :merchant, :note, :source, :tx_type, :funding, CAST(:payee_id AS uuid), "
    "CAST(:obligation_id AS uuid), :dedupe_key, :classified_by, :needs_review)"
)
_TX_CONFLICT = "ON CONFLICT (user_id, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING"
_AUDIT_CTE = (
    "aud AS (INSERT INTO audit_events (user_id, trace_id, event_type, tool, outcome, params, details) "
    "SELECT CAST(:uid AS text), CAST(:trace_id AS text), CAST(:event_type AS text), CAST(:tool AS text), 'ok', "
    "CAST(:params AS jsonb), CAST(:details AS jsonb) WHERE EXISTS (SELECT 1 FROM ins) RETURNING id)"
)
_PAYEE_CTE = (
    "pay AS (UPDATE payees SET last_used_at = now() WHERE user_id = :uid AND id = CAST(:payee_id AS uuid) "
    "AND EXISTS (SELECT 1 FROM ins) RETURNING id)"
)

SQL_LOCK_JAR = (
    "SELECT j.code, j.name, j.kind, j.system_role, j.balance_vnd FROM jars j "
    "WHERE j.user_id = :uid AND j.code = :jar FOR UPDATE"
)

# chi hoặc nhận tiền bằng số dư hũ (cả lương: thêm sự kiện lương chờ xác nhận)
SQL_WRITE_JAR_TX = (
    "WITH ins AS (INSERT INTO transactions "
    + _TX_COLUMNS
    + " VALUES "
    + _TX_VALUES
    + " "
    + _TX_CONFLICT
    + " RETURNING id), "
    "upd AS (UPDATE jars SET balance_vnd = balance_vnd + CAST(:signed AS numeric), updated_at = now() "
    "WHERE user_id = :uid AND code = :jar AND EXISTS (SELECT 1 FROM ins) RETURNING code, name, balance_vnd), "
    + _PAYEE_CTE
    + ", sal AS (INSERT INTO salary_events (id, user_id, period_date, transaction_id, received_on, expected_vnd, "
    "amount_vnd, deviation_percent, ask_update_salary, status) "
    "SELECT CAST(:se_id AS uuid), CAST(:uid AS text), CAST(:period_date AS date), (SELECT id FROM ins), "
    "CAST(:app_date AS date), CAST(:expected AS numeric), CAST(:amount AS numeric), CAST(:deviation AS numeric), "
    "CAST(:ask AS boolean), 'pending' "
    "WHERE EXISTS (SELECT 1 FROM ins) AND :is_salary RETURNING id), "
    + _AUDIT_CTE
    + " SELECT (SELECT id FROM ins) AS tx_id, (SELECT balance_vnd FROM upd) AS balance_after, "
    "(SELECT name FROM upd) AS jar_name"
)

SQL_LOCK_CREDIT_LINE = "SELECT limit_vnd, outstanding_vnd, due_day, status FROM credit_lines WHERE user_id = :uid FOR UPDATE"

# mua bằng Trả sau (mô phỏng): dòng chi funding credit (không đổi số dư hũ) + nghĩa vụ bnpl sinh hoặc cộng dồn + dư nợ
SQL_WRITE_CREDIT_TX = (
    "WITH ins AS (INSERT INTO transactions "
    + _TX_COLUMNS
    + " VALUES "
    + _TX_VALUES
    + " "
    + _TX_CONFLICT
    + " RETURNING id), "
    "ob AS (INSERT INTO obligations (id, user_id, kind, name, amount_vnd, fee_vnd, principal_vnd, due_date, cycle, "
    "status, pay_jar_code, source, source_transaction_id, fee_schedule_id) "
    "SELECT CAST(:ob_id AS uuid), CAST(:uid AS text), 'bnpl', CAST(:ob_name AS text), "
    "CAST(:amount AS numeric) + CAST(:fee AS numeric), CAST(:fee AS numeric), CAST(:amount AS numeric), "
    "CAST(:due_date AS date), 'once', 'active', CAST(:pay_jar AS text), "
    "'bnpl_auto', (SELECT id FROM ins), CAST(:fee_id AS uuid) WHERE EXISTS (SELECT 1 FROM ins) "
    "ON CONFLICT (user_id, due_date) WHERE kind = 'bnpl' AND status = 'active' DO UPDATE SET "
    "principal_vnd = obligations.principal_vnd + CAST(:amount AS numeric), "
    "amount_vnd = obligations.amount_vnd + CAST(:amount AS numeric), "
    "pay_jar_code = coalesce((SELECT j.code FROM jars j "
    "WHERE j.user_id = obligations.user_id AND j.code = obligations.pay_jar_code AND j.kind <> 'system'), "
    "EXCLUDED.pay_jar_code), updated_at = now() "
    "RETURNING id, principal_vnd, fee_vnd, amount_vnd, due_date, pay_jar_code, (xmax = 0) AS created), "
    "cl AS (UPDATE credit_lines SET outstanding_vnd = outstanding_vnd + CAST(:amount AS numeric), updated_at = now() "
    "WHERE user_id = :uid AND EXISTS (SELECT 1 FROM ins) RETURNING outstanding_vnd, limit_vnd), "
    + _PAYEE_CTE
    + ", "
    + _AUDIT_CTE
    + " SELECT (SELECT id FROM ins) AS tx_id, (SELECT id FROM ob) AS ob_id, "
    "(SELECT principal_vnd FROM ob) AS ob_principal, (SELECT fee_vnd FROM ob) AS ob_fee, "
    "(SELECT amount_vnd FROM ob) AS ob_amount, (SELECT due_date FROM ob) AS ob_due, "
    "(SELECT created FROM ob) AS ob_created, (SELECT pay_jar_code FROM ob) AS ob_pay_jar, "
    "(SELECT outstanding_vnd FROM cl) AS outstanding, "
    "(SELECT limit_vnd FROM cl) AS credit_limit"
)

SQL_LOCK_OBLIGATION = (
    "SELECT id, kind, name, status, amount_vnd, principal_vnd, fee_vnd, due_date, cycle, due_day, pay_jar_code "
    "FROM obligations WHERE user_id = :uid AND id = CAST(:oid AS uuid) FOR UPDATE"
)

# trả một nghĩa vụ bằng tiền hũ: dòng chi gắn obligation_id, số dư hũ, nghĩa vụ xong hoặc dời hạn, dư nợ gốc (trả sau)
SQL_WRITE_PAY_OBLIGATION = (
    "WITH ins AS (INSERT INTO transactions "
    + _TX_COLUMNS
    + " VALUES "
    + _TX_VALUES
    + " "
    + _TX_CONFLICT
    + " RETURNING id), "
    "upd AS (UPDATE jars SET balance_vnd = balance_vnd + CAST(:signed AS numeric), updated_at = now() "
    "WHERE user_id = :uid AND code = :jar AND EXISTS (SELECT 1 FROM ins) RETURNING code, name, balance_vnd), "
    "ob AS (UPDATE obligations SET status = CASE WHEN CAST(:next_due AS date) IS NULL THEN 'paid' ELSE status END, "
    "due_date = coalesce(CAST(:next_due AS date), due_date), paid_at = CAST(:occurred_at AS timestamptz), "
    "paid_transaction_id = (SELECT id FROM ins), updated_at = now() "
    "WHERE user_id = :uid AND id = CAST(:obligation_id AS uuid) AND EXISTS (SELECT 1 FROM ins) "
    "RETURNING id, status, due_date), "
    "cl AS (UPDATE credit_lines SET outstanding_vnd = greatest(outstanding_vnd - CAST(:principal AS numeric), 0), "
    "updated_at = now() WHERE user_id = :uid AND :is_bnpl AND EXISTS (SELECT 1 FROM ins) "
    "RETURNING outstanding_vnd), "
    + _PAYEE_CTE
    + ", "
    + _AUDIT_CTE
    + " SELECT (SELECT id FROM ins) AS tx_id, (SELECT balance_vnd FROM upd) AS balance_after, "
    "(SELECT name FROM upd) AS jar_name, (SELECT status FROM ob) AS ob_status, "
    "(SELECT due_date FROM ob) AS ob_due, (SELECT outstanding_vnd FROM cl) AS outstanding"
)

SQL_LOCK_SALARY_EVENT = (
    "SELECT id, status, amount_vnd, period_date, received_on, expected_vnd, transaction_id FROM salary_events "
    "WHERE user_id = :uid AND id = CAST(:eid AS uuid) FOR UPDATE"
)
SQL_LOCK_ALL_JARS = (
    "SELECT code, name, kind, system_role, split_percent, sort_order, balance_vnd FROM jars "
    "WHERE user_id = :uid ORDER BY code FOR UPDATE"
)
SQL_WRITE_SALARY_SPLIT = (
    "WITH rws AS (SELECT * FROM jsonb_to_recordset(CAST(:rows AS jsonb)) "
    "AS r(id uuid, jar_code text, amount numeric, note text)), "
    "ins AS (INSERT INTO transactions (id, user_id, occurred_at, app_date, kind, jar_code, amount_vnd, note, "
    "transfer_id, source, tx_type, funding_source) "
    "SELECT r.id, CAST(:uid AS text), CAST(:occurred_at AS timestamptz), CAST(:app_date AS date), 'transfer', r.jar_code, "
    "r.amount, r.note, CAST(:transfer_id AS uuid), 'salary_split', 'salary_split', 'jar' FROM rws r RETURNING id), "
    "upd AS (UPDATE jars j SET balance_vnd = j.balance_vnd + r.amount, updated_at = now() FROM rws r "
    "WHERE j.user_id = :uid AND j.code = r.jar_code RETURNING j.code, j.name, j.balance_vnd), "
    "ev AS (UPDATE salary_events SET status = 'confirmed', split = CAST(:split AS jsonb), confirmed_at = now() "
    "WHERE user_id = :uid AND id = CAST(:eid AS uuid) RETURNING id), "
    "usr AS (UPDATE users SET monthly_salary_vnd = CAST(:new_salary AS numeric), updated_at = now() "
    "WHERE id = :uid AND :update_salary RETURNING id), "
    "aud AS (INSERT INTO audit_events (user_id, trace_id, event_type, tool, outcome, params, details) "
    "VALUES (:uid, :trace_id, :event_type, :tool, 'ok', CAST(:params AS jsonb), CAST(:details AS jsonb)) "
    "RETURNING id) "
    "SELECT code, name, balance_vnd FROM upd"
)
SQL_WRITE_SALARY_KEEP = (
    "WITH ev AS (UPDATE salary_events SET status = 'kept_other', confirmed_at = now() "
    "WHERE user_id = :uid AND id = CAST(:eid AS uuid) RETURNING id), "
    "aud AS (INSERT INTO audit_events (user_id, trace_id, event_type, tool, outcome, params, details) "
    "VALUES (:uid, :trace_id, :event_type, :tool, 'ok', CAST(:params AS jsonb), CAST(:details AS jsonb)) "
    "RETURNING id) SELECT id FROM ev"
)

SQL_LOCK_TX = (
    "SELECT t.id, t.kind, t.jar_code, t.amount_vnd, t.funding_source, t.tx_type, t.payee_id, t.merchant "
    "FROM transactions t WHERE t.user_id = :uid AND t.id = CAST(:id AS uuid) FOR UPDATE"
)
SQL_LOCK_TWO_JARS = (
    "SELECT code, name, kind, system_role, balance_vnd FROM jars "
    "WHERE user_id = :uid AND code IN (:a, :b) ORDER BY code FOR UPDATE"
)
_ASSIGN_HEAD = (
    "WITH utx AS (UPDATE transactions SET jar_code = :to_jar, classified_by = 'user', needs_review = false, "
    "classification_confidence = NULL, suggested_jars = NULL WHERE user_id = :uid AND id = CAST(:id AS uuid) "
    "RETURNING id), "
    "upd AS (UPDATE jars j SET balance_vnd = j.balance_vnd + d.delta, updated_at = now() "
    "FROM jsonb_to_recordset(CAST(:deltas AS jsonb)) AS d(code text, delta numeric) "
    "WHERE j.user_id = :uid AND j.code = d.code RETURNING j.code, j.name, j.balance_vnd), "
)
_ASSIGN_RULE_PAYEE_ALWAYS = (
    "rule AS (INSERT INTO category_rules (user_id, match_type, payee_id, jar_code, scope, transaction_id, "
    "last_used_at) VALUES (:uid, 'payee', CAST(:payee_id AS uuid), :to_jar, 'always', CAST(:id AS uuid), now()) "
    "ON CONFLICT (user_id, payee_id) WHERE scope = 'always' AND match_type = 'payee' DO UPDATE SET "
    "jar_code = EXCLUDED.jar_code, transaction_id = EXCLUDED.transaction_id, "
    "hit_count = category_rules.hit_count + 1, last_used_at = now() RETURNING id), "
)
_ASSIGN_RULE_MERCHANT_ALWAYS = (
    "rule AS (INSERT INTO category_rules (user_id, match_type, merchant_key, jar_code, scope, transaction_id, "
    "last_used_at) VALUES (:uid, 'merchant', :merchant_key, :to_jar, 'always', CAST(:id AS uuid), now()) "
    "ON CONFLICT (user_id, merchant_key) WHERE scope = 'always' AND match_type = 'merchant' DO UPDATE SET "
    "jar_code = EXCLUDED.jar_code, transaction_id = EXCLUDED.transaction_id, "
    "hit_count = category_rules.hit_count + 1, last_used_at = now() RETURNING id), "
)
_ASSIGN_RULE_ONCE_PAYEE = (
    "rule AS (INSERT INTO category_rules (user_id, match_type, payee_id, jar_code, scope, transaction_id) "
    "VALUES (:uid, 'payee', CAST(:payee_id AS uuid), :to_jar, 'once', CAST(:id AS uuid)) RETURNING id), "
)
_ASSIGN_RULE_ONCE_MERCHANT = (
    "rule AS (INSERT INTO category_rules (user_id, match_type, merchant_key, jar_code, scope, transaction_id) "
    "VALUES (:uid, 'merchant', :merchant_key, :to_jar, 'once', CAST(:id AS uuid)) RETURNING id), "
)
_ASSIGN_TAIL = (
    "aud AS (INSERT INTO audit_events (user_id, trace_id, event_type, tool, outcome, params, details) "
    "VALUES (:uid, :trace_id, :event_type, :tool, 'ok', CAST(:params AS jsonb), CAST(:details AS jsonb)) "
    "RETURNING id) SELECT (SELECT id FROM utx) AS tx_id"
)

SQL_UPSERT_USER = (
    "INSERT INTO users (id, display_name, monthly_salary_vnd, payday_day, risk_tolerance, clock_offset_days) "
    "VALUES (:uid, coalesce(CAST(:dn AS text), :dn_default), CAST(:sal AS numeric), CAST(:pd AS smallint), "
    "CAST(:risk AS text), 0) "
    "ON CONFLICT (id) DO UPDATE SET display_name = coalesce(CAST(:dn AS text), users.display_name), "
    "monthly_salary_vnd = coalesce(CAST(:sal AS numeric), users.monthly_salary_vnd), "
    "payday_day = coalesce(CAST(:pd AS smallint), users.payday_day), "
    "risk_tolerance = coalesce(CAST(:risk AS text), users.risk_tolerance), updated_at = now() "
    "RETURNING (xmax = 0) AS created, display_name, monthly_salary_vnd, payday_day, risk_tolerance"
)
SQL_TEMPLATE_JARS = (
    "INSERT INTO jars (user_id, code, name, color_key, icon_key, balance_vnd, split_percent, sort_order, kind, purpose) "
    "SELECT CAST(:uid AS text), t.code, t.name, t.color_key, t.icon_key, 0, t.default_split_percent, t.sort_order, t.kind, t.purpose "
    f"FROM ({SQL_ONBOARDING_TEMPLATES}) t WHERE t.is_default AND NOT EXISTS "
    "(SELECT 1 FROM jars j WHERE j.user_id = :uid AND j.kind <> 'system') RETURNING code"
)
SQL_DEFAULT_CREDIT_LINE = (
    "INSERT INTO credit_lines (user_id, product_code, limit_vnd) VALUES (:uid, :product, CAST(:lim AS numeric)) "
    "ON CONFLICT (user_id) DO NOTHING"
)
SQL_ENSURE_SYSTEM_JARS = "SELECT app_ensure_system_jars(:uid) AS created"
SQL_INSERT_OBLIGATION = (
    "INSERT INTO obligations (id, user_id, kind, name, amount_vnd, amount_min_vnd, amount_max_vnd, fee_vnd, "
    "due_date, cycle, due_day, pay_jar_code, is_essential, source) "
    "VALUES (CAST(:id AS uuid), :uid, :kind, :name, CAST(:amount AS numeric), CAST(:amount_min AS numeric), "
    "CAST(:amount_max AS numeric), CAST(:fee AS numeric), CAST(:due_date AS date), :cycle, CAST(:due_day AS smallint), "
    ":pay_jar, :is_essential, 'declared') "
    "RETURNING id, kind, name, amount_vnd, amount_min_vnd, amount_max_vnd, fee_vnd, principal_vnd, due_date, cycle, "
    "due_day, status, pay_jar_code, is_essential, source"
)
SQL_UPDATE_OBLIGATION = (
    "UPDATE obligations SET kind = coalesce(:kind, kind), name = coalesce(:name, name), "
    "amount_vnd = coalesce(CAST(:amount AS numeric), amount_vnd), "
    "amount_min_vnd = CASE WHEN :set_range THEN CAST(:amount_min AS numeric) ELSE amount_min_vnd END, "
    "amount_max_vnd = CASE WHEN :set_range THEN CAST(:amount_max AS numeric) ELSE amount_max_vnd END, "
    "fee_vnd = coalesce(CAST(:fee AS numeric), fee_vnd), due_date = coalesce(CAST(:due_date AS date), due_date), "
    "cycle = coalesce(:cycle, cycle), due_day = coalesce(CAST(:due_day AS smallint), due_day), "
    "pay_jar_code = coalesce(:pay_jar, pay_jar_code), is_essential = coalesce(CAST(:is_essential AS boolean), is_essential), "
    "updated_at = now() WHERE user_id = :uid AND id = CAST(:id AS uuid) "
    "RETURNING id, kind, name, amount_vnd, amount_min_vnd, amount_max_vnd, fee_vnd, principal_vnd, due_date, cycle, "
    "due_day, status, pay_jar_code, is_essential, source"
)
SQL_CANCEL_OBLIGATION = (
    "UPDATE obligations SET status = 'cancelled', updated_at = now() WHERE user_id = :uid AND id = CAST(:id AS uuid) "
    "RETURNING id, kind, name, amount_vnd, amount_min_vnd, amount_max_vnd, fee_vnd, principal_vnd, due_date, cycle, "
    "due_day, status, pay_jar_code, is_essential, source"
)
SQL_RELEASE_CANCELLED_CREDIT = (
    "UPDATE credit_lines SET outstanding_vnd = greatest(outstanding_vnd - CAST(:principal AS numeric), 0), "
    "updated_at = now() WHERE user_id = :uid"
)

SQL_JARS_FOR_SAVE = (
    "SELECT j.code, j.name, j.balance_vnd, j.purpose, j.goal_vnd, j.goal_date, j.sinking_items, "
    "(SELECT count(*) FROM obligations o WHERE o.user_id = j.user_id AND o.pay_jar_code = j.code "
    "AND o.status = 'active') AS active_obligations, "
    "(SELECT count(*) FROM transactions t WHERE t.user_id = j.user_id AND t.jar_code = j.code) AS tx_count "
    "FROM jars j WHERE j.user_id = :uid AND j.kind <> 'system' ORDER BY j.code FOR UPDATE OF j"
)
SQL_RELEASE_PAY_JAR = (
    "UPDATE obligations SET pay_jar_code = NULL, updated_at = now() WHERE user_id = :uid AND status <> 'active' "
    "AND pay_jar_code IN (SELECT jsonb_array_elements_text(CAST(:removed AS jsonb)))"
)
SQL_DELETE_JARS = (
    "DELETE FROM jars WHERE user_id = :uid AND kind <> 'system' "
    "AND code IN (SELECT jsonb_array_elements_text(CAST(:removed AS jsonb)))"
)
SQL_UPSERT_JARS = (
    "INSERT INTO jars (user_id, code, name, color_key, icon_key, balance_vnd, split_percent, sort_order, kind, "
    "goal_vnd, goal_date, purpose, sinking_items) "
    "SELECT CAST(:uid AS text), r.code, r.name, r.color_key, r.icon_key, 0, r.split_percent, r.sort_order, r.kind, r.goal_vnd, "
    "r.goal_date, r.purpose, r.sinking_items FROM jsonb_to_recordset(CAST(:jars AS jsonb)) AS r(code text, name text, color_key text, "
    "icon_key text, split_percent numeric, sort_order integer, kind text, goal_vnd numeric, goal_date date, purpose text, sinking_items jsonb) "
    "ON CONFLICT (user_id, code) DO UPDATE SET name = EXCLUDED.name, color_key = EXCLUDED.color_key, "
    "icon_key = EXCLUDED.icon_key, kind = EXCLUDED.kind, split_percent = EXCLUDED.split_percent, "
    "sort_order = EXCLUDED.sort_order, goal_vnd = EXCLUDED.goal_vnd, goal_date = EXCLUDED.goal_date, "
    "purpose = EXCLUDED.purpose, sinking_items = EXCLUDED.sinking_items, "
    "updated_at = now() RETURNING code, name, balance_vnd"
)

#: bước chuyển hũ của phase 1 (ghi dòng `tx_type` đúng thay vì mặc định)
MOVE_TX_TYPE = TX_TYPE_JAR_TRANSFER
SPLIT_TX_TYPE = TX_TYPE_SALARY_SPLIT


def _vnd(value: Any) -> int:
    return to_vnd(value if isinstance(value, (int, Decimal, str)) else Decimal(str(value)))


class WalletRepo:
    """Mixin cho `LedgerRepo`: dùng `self.db` (DataApi)."""

    db: DataApi

    # --- đọc --------------------------------------------------------------------------------------------------
    def overview(self, user_id: str, now: datetime, tz: str) -> dict[str, Any]:
        rows = self.db.query(SQL_OVERVIEW, {"uid": user_id, "now": now, "tz": tz}, max_rows=1)
        return rows[0]["data"]

    def jar_detail(self, user_id: str, jar: str, now: datetime, tz: str) -> dict[str, Any]:
        rows = self.db.query(
            SQL_JAR_DETAIL, {"uid": user_id, "jar": jar, "now": now, "tz": tz}, max_rows=1
        )
        return rows[0]["data"]

    def list_transactions(
        self,
        user_id: str,
        *,
        jar: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        kind: str | None = None,
        tx_type: str | None = None,
        needs_review: bool | None = None,
        cursor: tuple[datetime, str] | None = None,
        limit: int = 20,
    ) -> list[Row]:
        """Tối đa `limit` dòng (hàm SQL tự chặn 51). Người gọi xin `limit + 1` để biết còn nữa không."""
        return self.db.query(
            SQL_LIST_TRANSACTIONS,
            {
                "uid": user_id,
                "jar": jar,
                "from_date": from_date,
                "to_date": to_date,
                "kind": kind,
                "tx_type": tx_type,
                "needs_review": needs_review,
                "cursor_at": cursor[0] if cursor else None,
                "cursor_id": cursor[1] if cursor else None,
                "lim": limit,
            },
            max_rows=51,
        )

    def list_obligations(
        self,
        user_id: str,
        *,
        status: str = "active",
        due_before: date | None = None,
        limit: int = 50,
    ) -> list[Row]:
        return self.db.query(
            SQL_LIST_OBLIGATIONS,
            {"uid": user_id, "status": status, "due_before": due_before, "lim": limit},
            max_rows=100,
        )

    def list_payees(self, user_id: str, limit: int = 100) -> list[Row]:
        return self.db.query(SQL_LIST_PAYEES, {"uid": user_id, "lim": limit}, max_rows=100)

    def credit_line(self, user_id: str) -> Row | None:
        rows = self.db.query(SQL_CREDIT_LINE, {"uid": user_id}, max_rows=1)
        return rows[0] if rows else None

    def salary_events(self, user_id: str, status: str = "pending", limit: int = 20) -> list[Row]:
        return self.db.query(
            SQL_SALARY_EVENTS, {"uid": user_id, "status": status, "lim": limit}, max_rows=20
        )

    def cashflow(self, user_id: str, from_date: date, to_date: date) -> dict[str, Any]:
        rows = self.db.query(
            SQL_CASHFLOW,
            {"uid": user_id, "from_date": from_date, "to_date": to_date},
            max_rows=1,
        )
        return rows[0]["data"]

    def spend_context(self, user_id: str, now: datetime, tz: str, window_days: int) -> list[Row]:
        """Phần meta (ngày mô phỏng, đầu lịch sử) và hũ (chuỗi `spend`) của `app_get_forecast_context` cho sàn chi của đề xuất tỷ lệ."""
        return self.db.query(
            SQL_SPEND_CONTEXT,
            {"uid": user_id, "now": now, "tz": tz, "win": window_days},
            max_rows=41,
        )

    def unclassified(self, user_id: str, limit: int) -> list[Row]:
        return self.db.query(SQL_UNCLASSIFIED, {"uid": user_id, "lim": limit}, max_rows=50)

    def review_stats(self, user_id: str) -> Row:
        rows = self.db.query(SQL_REVIEW_STATS, {"uid": user_id}, max_rows=1)
        return rows[0]

    def transaction_by_id(self, user_id: str, tx_id: str) -> Row | None:
        rows = self.db.query(SQL_GET_TRANSACTION, {"uid": user_id, "id": tx_id}, max_rows=1)
        return rows[0] if rows else None

    def user_row(self, user_id: str) -> Row | None:
        """Hồ sơ đã khai (lương, ngày nhận, mức rủi ro, độ lệch đồng hồ) hoặc None nếu chưa có hồ sơ."""
        rows = self.db.query(SQL_USER, {"uid": user_id}, max_rows=1)
        return rows[0] if rows else None

    def jars_usage(self, user_id: str) -> list[Row]:
        return self.db.query(SQL_JAR_USAGE, {"uid": user_id}, max_rows=40)

    def forecast_summaries(self, user_id: str, jar: str | None = None) -> list[Row]:
        return self.db.query(SQL_FORECAST_SUMMARIES, {"uid": user_id, "jar": jar}, max_rows=40)

    def forecast_series(self, user_id: str, jar: str) -> list[Row]:
        return self.db.query(SQL_FORECAST_SERIES, {"uid": user_id, "jar": jar}, max_rows=90)

    def confirm_block(
        self, user_id: str, conversation_id: str, block_id: str
    ) -> dict[str, Any] | None:
        """Khối confirm đã lưu (mới nhất) của đề nghị, hoặc None nếu chưa lưu."""
        rows = self.db.query(
            SQL_CONFIRM_BLOCK,
            {"uid": user_id, "conv": conversation_id, "bid": block_id},
            max_rows=1,
        )
        return rows[0]["block"] if rows else None

    # --- bảng tra dùng chung (không user_id) --------------------------------------------------------------------
    def reference_tx_types(self) -> list[Row]:
        return self.db.query(SQL_REF_TX_TYPES, max_rows=100)

    def reference_fees(self) -> list[Row]:
        return self.db.query(SQL_REF_FEES, max_rows=100)

    def reference_templates(self) -> list[Row]:
        return self.db.query(SQL_REF_TEMPLATES, {"layout": onboarding_override()}, max_rows=40)

    # --- ghi: tiện ích -----------------------------------------------------------------------------------------
    @staticmethod
    def _claim(tx: Transaction, user_id: str, claim: ClaimSpec | None, result: WriteResult) -> None:
        if claim is None:
            return
        claimed = tx.execute(
            SQL_CLAIM_DONE,
            {
                "uid": user_id,
                "cbid": claim.confirm_block_id,
                "conv": claim.conversation_id,
                "ref": result.reference_id,
                "receipt": dict(claim.receipt_for(result)),
                "tool": result.tool,
            },
        )
        if not claimed:
            raise YofinaError(ErrorCode.ALREADY_APPLIED, ALREADY_APPLIED_MESSAGE)

    def cancel_offer(
        self, user_id: str, conversation_id: str, confirm_block_id: str
    ) -> tuple[str, datetime | None]:
        """Ghi việc người dùng bấm "Không". Trả (`cancelled` hoặc `done`, thời điểm xử lý): đề nghị đã có dòng
        thì không ghi đè (đã thực hiện thì `done`, để người gọi báo ALREADY_APPLIED)."""
        with self.db.transaction(user_id) as tx:
            rows = tx.execute(
                SQL_CLAIM_CANCELLED,
                {"uid": user_id, "cbid": confirm_block_id, "conv": conversation_id},
            )
            if rows:
                return "cancelled", rows[0]["resolved_at"]
            existing = tx.execute(
                "SELECT status, resolved_at FROM confirm_resolutions "
                "WHERE user_id = :uid AND confirm_block_id = :cbid",
                {"uid": user_id, "cbid": confirm_block_id},
            )
        row = existing[0] if existing else {"status": "cancelled", "resolved_at": None}
        return str(row["status"]), row["resolved_at"]

    # --- ghi: record_transaction --------------------------------------------------------------------------------
    def _tx_params(self, p: Mapping[str, Any]) -> dict[str, Any]:
        """Tham số chung của `_TX_VALUES` từ dict `p` (service dựng)."""
        return {
            "uid": p["uid"],
            "tx_id": p["tx_id"],
            "occurred_at": p["occurred_at"],
            "app_date": p["app_date"],
            "kind": p["kind"],
            "jar": p["jar"],
            "signed": p["signed"],
            "merchant": p.get("merchant"),
            "note": p.get("note"),
            "source": p.get("source", "app"),
            "tx_type": p["tx_type"],
            "funding": p["funding"],
            "payee_id": p.get("payee_id"),
            "obligation_id": p.get("obligation_id"),
            "dedupe_key": p.get("dedupe_key"),
            "classified_by": p.get("classified_by"),
            "needs_review": bool(p.get("needs_review")),
        }

    def write_jar_transaction(
        self,
        user_id: str,
        *,
        tx: Mapping[str, Any],
        salary: Mapping[str, Any] | None,
        audit: Mapping[str, Any],
        claim: ClaimSpec | None,
        tool: str,
    ) -> WriteResult:
        """Chi (funding jar) hoặc tiền vào: dòng sổ cái, số dư hũ, và sự kiện lương chờ nếu là lương."""
        amount = abs(int(tx["signed"]))
        with self.db.transaction(user_id) as t:
            locked = t.execute(SQL_LOCK_JAR, {"uid": user_id, "jar": tx["jar"]})
            if not locked:
                raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ bạn chọn.")
            jar = locked[0]
            if (
                tx["signed"] < 0
                and jar["system_role"] != "unclassified"
                and _vnd(jar["balance_vnd"]) < amount
            ):
                raise YofinaError(ErrorCode.INSUFFICIENT_FUNDS, f"Hũ {jar['name']} không đủ số dư.")
            params = {
                **self._tx_params({**tx, "uid": user_id}),
                "se_id": salary["id"] if salary else None,
                "period_date": salary["period_date"] if salary else None,
                "expected": salary.get("expected_vnd") if salary else None,
                "amount": amount,
                "deviation": salary["deviation_percent"] if salary else Decimal(0),
                "ask": bool(salary and salary["ask_update_salary"]),
                "is_salary": salary is not None,
                "trace_id": audit["trace_id"],
                "event_type": audit["event_type"],
                "tool": tool,
                "params": audit["params"],
                "details": audit["details"],
            }
            out = t.execute(SQL_WRITE_JAR_TX, params)
            row = out[0] if out else {}
            if not row.get("tx_id"):
                raise YofinaError(
                    ErrorCode.DUPLICATE_TRANSACTION,
                    "Giao dịch này đã được ghi rồi (trùng mã tham chiếu). Chưa ghi thêm gì.",
                )
            result = WriteResult(
                tool=tool,
                reference_id=str(row["tx_id"]),
                occurred_at=tx["occurred_at"],
                app_date=tx["app_date"],
                jars_after=[
                    {
                        "code": tx["jar"],
                        "name": row["jar_name"],
                        "balance_vnd": _vnd(row["balance_after"]),
                    }
                ],
                deltas={tx["jar"]: int(tx["signed"])},
                facts={"salary_event_id": salary["id"] if salary else None},
            )
            self._claim(t, user_id, claim, result)
        return result

    def write_credit_purchase(
        self,
        user_id: str,
        *,
        tx: Mapping[str, Any],
        fee: Mapping[str, Any],
        pay_jar: str | None,
        audit: Mapping[str, Any],
        claim: ClaimSpec | None,
        tool: str,
        due_date_for: Callable[[int], date],
        limit_check: Callable[[Mapping[str, Any]], None],
    ) -> WriteResult:
        """Mua bằng Trả sau: kiểm hạn mức trên dòng đã khóa, rồi ghi dòng chi + nghĩa vụ bnpl + dư nợ."""
        amount = abs(int(tx["signed"]))
        with self.db.transaction(user_id) as t:
            locked = t.execute(SQL_LOCK_CREDIT_LINE, {"uid": user_id})
            line = locked[0] if locked else None
            limit_check(line or {})
            due = due_date_for(int(line["due_day"]))
            params = {
                **self._tx_params({**tx, "uid": user_id}),
                "ob_id": str(uuid.uuid4()),
                "ob_name": fee["name"],
                "amount": amount,
                "fee": int(fee["amount_vnd"]),
                "fee_id": fee.get("id"),
                "due_date": due,
                "pay_jar": pay_jar,
                "trace_id": audit["trace_id"],
                "event_type": audit["event_type"],
                "tool": tool,
                "params": audit["params"],
                "details": audit["details"],
            }
            out = t.execute(SQL_WRITE_CREDIT_TX, params)
            row = out[0] if out else {}
            if not row.get("tx_id"):
                raise YofinaError(
                    ErrorCode.DUPLICATE_TRANSACTION,
                    "Giao dịch này đã được ghi rồi (trùng mã tham chiếu). Chưa ghi thêm gì.",
                )
            result = WriteResult(
                tool=tool,
                reference_id=str(row["tx_id"]),
                occurred_at=tx["occurred_at"],
                app_date=tx["app_date"],
                jars_after=[],
                deltas={},
                facts={
                    "obligation_id": str(row["ob_id"]),
                    "obligation_created": bool(row["ob_created"]),
                    "pay_jar": row["ob_pay_jar"],
                    "principal_vnd": _vnd(row["ob_principal"]),
                    "fee_vnd": _vnd(row["ob_fee"]),
                    "amount_vnd": _vnd(row["ob_amount"]),
                    "due_date": row["ob_due"],
                    "outstanding_vnd": _vnd(row["outstanding"]),
                    "limit_vnd": _vnd(row["credit_limit"]),
                    "jar": tx["jar"],
                },
            )
            self._claim(t, user_id, claim, result)
        return result

    def write_obligation_payment(
        self,
        user_id: str,
        *,
        tx: Mapping[str, Any],
        audit: Mapping[str, Any],
        claim: ClaimSpec | None,
        tool: str,
        next_due_for: Callable[[Mapping[str, Any]], date | None],
    ) -> WriteResult:
        """Trả một nghĩa vụ bằng tiền hũ: khóa hũ và nghĩa vụ, rồi ghi dòng chi gắn `obligation_id`."""
        amount = abs(int(tx["signed"]))
        with self.db.transaction(user_id) as t:
            locked = t.execute(SQL_LOCK_JAR, {"uid": user_id, "jar": tx["jar"]})
            if not locked:
                raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ bạn chọn.")
            jar = locked[0]
            if _vnd(jar["balance_vnd"]) < amount:
                raise YofinaError(ErrorCode.INSUFFICIENT_FUNDS, f"Hũ {jar['name']} không đủ số dư.")
            obs = t.execute(SQL_LOCK_OBLIGATION, {"uid": user_id, "oid": tx["obligation_id"]})
            if not obs:
                raise YofinaError(ErrorCode.OBLIGATION_NOT_FOUND, "Không tìm thấy khoản nghĩa vụ.")
            ob = obs[0]
            if ob["status"] != "active":
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, "Khoản nghĩa vụ này không còn hoạt động."
                )
            next_due = next_due_for(ob)
            is_bnpl = ob["kind"] == "bnpl"
            if is_bnpl and amount != _vnd(ob["amount_vnd"]):
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID, "Trả sau cần thanh toán đủ tổng tiền đến hạn."
                )
            params = {
                **self._tx_params({**tx, "uid": user_id}),
                "next_due": next_due,
                "principal": _vnd(ob["principal_vnd"]) if is_bnpl and ob["principal_vnd"] else 0,
                "is_bnpl": is_bnpl,
                "trace_id": audit["trace_id"],
                "event_type": audit["event_type"],
                "tool": tool,
                "params": audit["params"],
                "details": audit["details"],
            }
            out = t.execute(SQL_WRITE_PAY_OBLIGATION, params)
            row = out[0] if out else {}
            if not row.get("tx_id"):
                raise YofinaError(
                    ErrorCode.DUPLICATE_TRANSACTION,
                    "Giao dịch này đã được ghi rồi (trùng mã tham chiếu). Chưa ghi thêm gì.",
                )
            result = WriteResult(
                tool=tool,
                reference_id=str(row["tx_id"]),
                occurred_at=tx["occurred_at"],
                app_date=tx["app_date"],
                jars_after=[
                    {
                        "code": tx["jar"],
                        "name": row["jar_name"],
                        "balance_vnd": _vnd(row["balance_after"]),
                    }
                ],
                deltas={tx["jar"]: int(tx["signed"])},
                facts={
                    "obligation_id": str(tx["obligation_id"]),
                    "obligation_name": ob["name"],
                    "obligation_kind": ob["kind"],
                    "obligation_status": row["ob_status"],
                    "obligation_due": row["ob_due"],
                    "expected_amount_vnd": _vnd(ob["amount_vnd"]),
                    "pay_jar": ob["pay_jar_code"],
                    "outstanding_vnd": (
                        _vnd(row["outstanding"]) if row.get("outstanding") is not None else None
                    ),
                },
            )
            self._claim(t, user_id, claim, result)
        return result

    # --- ghi: confirm_salary --------------------------------------------------------------------------------------
    def write_confirm_salary(
        self,
        user_id: str,
        *,
        norm: Mapping[str, Any],
        now: datetime,
        app_date: date,
        shares_for: Callable[[Sequence[Mapping[str, Any]], int], dict[str, int]],
        audit: Mapping[str, Any],
        claim: ClaimSpec | None,
        tool: str,
    ) -> WriteResult:
        """Chia lương (hoặc giữ ở Tiền vào khác) trên sự kiện lương đã khóa. `shares_for(jars, amount)` trả phần của
        từng hũ người dùng theo `split_amount` (hàm thuần của service)."""
        eid = norm["salary_event_id"]
        with self.db.transaction(user_id) as t:
            evs = t.execute(SQL_LOCK_SALARY_EVENT, {"uid": user_id, "eid": eid})
            if not evs:
                raise YofinaError(ErrorCode.SALARY_EVENT_NOT_FOUND, "Không tìm thấy lương này.")
            ev = evs[0]
            if ev["status"] != "pending":
                raise YofinaError(ErrorCode.ALREADY_APPLIED, "Khoản lương này đã được xử lý rồi.")
            amount = _vnd(ev["amount_vnd"])
            audit_args = {
                "uid": user_id,
                "trace_id": audit["trace_id"],
                "event_type": audit["event_type"],
                "tool": tool,
                "params": audit["params"],
                "details": audit["details"],
            }
            if norm["decision"] == "keep_as_other":
                t.execute(SQL_WRITE_SALARY_KEEP, {**audit_args, "eid": eid})
                result = WriteResult(
                    tool=tool,
                    reference_id=eid,
                    occurred_at=now,
                    app_date=app_date,
                    facts={
                        "decision": "keep_as_other",
                        "amount_vnd": amount,
                        "period_date": ev["period_date"],
                        "split": [],
                    },
                )
                self._claim(t, user_id, claim, result)
                return result
            jars = t.execute(SQL_LOCK_ALL_JARS, {"uid": user_id})
            other = next((j for j in jars if j["code"] == OTHER_INCOME_JAR_CODE), None)
            if other is None or _vnd(other["balance_vnd"]) < amount:
                raise YofinaError(
                    ErrorCode.INSUFFICIENT_FUNDS,
                    "Hũ Tiền vào khác không còn đủ số tiền lương để chia.",
                )
            user_jars = [j for j in jars if j["kind"] != "system"]
            parts = shares_for(user_jars, amount)
            transfer_id = str(uuid.uuid4())
            rows: list[dict[str, Any]] = [
                {
                    "id": str(uuid.uuid4()),
                    "jar_code": OTHER_INCOME_JAR_CODE,
                    "amount": -amount,
                    "note": "Chia lương vào các hũ",
                }
            ]
            names = {j["code"]: j["name"] for j in jars}
            rows.extend(
                {
                    "id": str(uuid.uuid4()),
                    "jar_code": code,
                    "amount": part,
                    "note": f"Lương chia vào hũ {names[code]}",
                }
                for code, part in parts.items()
                if part > 0
            )
            split_doc = [
                {"jar": code, "amount_vnd": part} for code, part in parts.items() if part > 0
            ]
            out = t.execute(
                SQL_WRITE_SALARY_SPLIT,
                {
                    **audit_args,
                    "rows": rows,
                    "occurred_at": now,
                    "app_date": app_date,
                    "transfer_id": transfer_id,
                    "split": split_doc,
                    "eid": eid,
                    "new_salary": amount,
                    "update_salary": bool(norm.get("update_declared_salary")),
                },
            )
            after = {r["code"]: r for r in out}
            deltas = {r["jar_code"]: int(r["amount"]) for r in rows}
            result = WriteResult(
                tool=tool,
                reference_id=transfer_id,
                occurred_at=now,
                app_date=app_date,
                jars_after=[
                    {
                        "code": c,
                        "name": after[c]["name"],
                        "balance_vnd": _vnd(after[c]["balance_vnd"]),
                    }
                    for c in deltas
                    if c in after
                ],
                deltas=deltas,
                facts={
                    "decision": "split",
                    "amount_vnd": amount,
                    "period_date": ev["period_date"],
                    "split": split_doc,
                    "salary_event_id": eid,
                    "salary_updated": bool(norm.get("update_declared_salary")),
                },
            )
            self._claim(t, user_id, claim, result)
        return result

    # --- ghi: assign_jar ------------------------------------------------------------------------------------------
    def write_assign_jar(
        self,
        user_id: str,
        *,
        norm: Mapping[str, Any],
        now: datetime,
        app_date: date,
        audit: Mapping[str, Any],
        claim: ClaimSpec | None,
        tool: str,
    ) -> WriteResult:
        """Gán lại hũ cho một dòng sổ cái: dòng chuyển sang hũ mới, số dư hai hũ đổi tương ứng (nếu trả bằng hũ)."""
        tid, target = norm["transaction_id"], norm["jar"]
        with self.db.transaction(user_id) as t:
            txs = t.execute(SQL_LOCK_TX, {"uid": user_id, "id": tid})
            if not txs:
                raise YofinaError(ErrorCode.TRANSACTION_NOT_FOUND, "Không tìm thấy giao dịch.")
            row = txs[0]
            source = row["jar_code"]
            if row["kind"] == "transfer":
                raise YofinaError(ErrorCode.PARAMS_INVALID, "Dòng chuyển hũ không gán lại được.")
            if row["kind"] == "income" and row["tx_type"] == "salary":
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID,
                    "Tiền lương được chia bằng bước xác nhận lương, không gán vào một hũ.",
                )
            if source == target:
                raise YofinaError(ErrorCode.PARAMS_INVALID, "Giao dịch đã nằm ở hũ này rồi.")
            jars = {
                j["code"]: j
                for j in t.execute(SQL_LOCK_TWO_JARS, {"uid": user_id, "a": source, "b": target})
            }
            dst = jars.get(target)
            src = jars.get(source)
            if dst is None or src is None:
                raise YofinaError(ErrorCode.JAR_NOT_FOUND, "Không tìm thấy hũ bạn chọn.")
            if dst["kind"] == "system":
                raise YofinaError(ErrorCode.JAR_PROTECTED, "Không gán vào hũ hệ thống.")
            signed = _vnd(row["amount_vnd"])
            moves_money = row["funding_source"] == "jar"
            deltas: dict[str, int] = {}
            if moves_money:
                deltas = {source: -signed, target: signed}
                if (
                    _vnd(src["balance_vnd"]) + deltas[source] < 0
                    and src["system_role"] != "unclassified"
                ):
                    raise YofinaError(
                        ErrorCode.INSUFFICIENT_FUNDS, f"Hũ {src['name']} không đủ số dư."
                    )
                if _vnd(dst["balance_vnd"]) + deltas[target] < 0:
                    raise YofinaError(
                        ErrorCode.INSUFFICIENT_FUNDS, f"Hũ {dst['name']} không đủ số dư."
                    )
            remember = norm.get("remember", "once")
            payee_id = str(row["payee_id"]) if row["payee_id"] else None
            merchant_key = fold_text(row["merchant"])[:120] if row["merchant"] else None
            if payee_id:
                rule = (
                    _ASSIGN_RULE_PAYEE_ALWAYS if remember == "always" else _ASSIGN_RULE_ONCE_PAYEE
                )
            elif merchant_key:
                rule = (
                    _ASSIGN_RULE_MERCHANT_ALWAYS
                    if remember == "always"
                    else _ASSIGN_RULE_ONCE_MERCHANT
                )
            elif remember == "always":
                raise YofinaError(
                    ErrorCode.PARAMS_INVALID,
                    "Giao dịch này không có người nhận hay đối tác để nhớ thành luật.",
                )
            else:
                rule = ""
            sql = _ASSIGN_HEAD + rule + _ASSIGN_TAIL
            params: dict[str, Any] = {
                "uid": user_id,
                "id": tid,
                "to_jar": target,
                "deltas": [{"code": c, "delta": d} for c, d in deltas.items()],
                "trace_id": audit["trace_id"],
                "event_type": audit["event_type"],
                "tool": tool,
                "params": audit["params"],
                "details": audit["details"],
            }
            if rule:
                params["payee_id" if payee_id else "merchant_key"] = payee_id or merchant_key
            out = t.execute(sql, params)
            if not out or not out[0].get("tx_id"):
                raise YofinaError(ErrorCode.INTERNAL_ERROR, "Không gán được hũ.")
            after = {c: _vnd(jars[c]["balance_vnd"]) + d for c, d in deltas.items()}
            result = WriteResult(
                tool=tool,
                reference_id=tid,
                occurred_at=now,
                app_date=app_date,
                jars_after=[
                    {
                        "code": c,
                        "name": jars[c]["name"],
                        "balance_vnd": after.get(c, _vnd(jars[c]["balance_vnd"])),
                    }
                    for c in (source, target)
                ],
                deltas=deltas,
                facts={
                    "from_jar": source,
                    "from_jar_name": src["name"],
                    "to_jar": target,
                    "to_jar_name": dst["name"],
                    "amount_vnd": abs(signed),
                    "kind": row["kind"],
                    "moves_money": moves_money,
                    "funding_source": row["funding_source"],
                    "remember": remember if rule else "once",
                    "rule_saved": bool(rule and remember == "always"),
                },
            )
            self._claim(t, user_id, claim, result)
        return result

    # --- ghi: update_profile --------------------------------------------------------------------------------------
    def write_update_profile(
        self,
        user_id: str,
        *,
        norm: Mapping[str, Any],
        display_name_default: str,
        credit_limit_default: int,
        credit_product_code: str,
        obligation_values: Mapping[str, Any] | None,
        now: datetime,
        app_date: date,
        audit: Mapping[str, Any],
        claim: ClaimSpec | None,
        tool: str,
    ) -> WriteResult:
        """Khai và sửa hồ sơ; onboarding (người dùng chưa có hồ sơ) tạo hồ sơ, hai hũ hệ thống, hũ mẫu và hạn mức."""
        with self.db.transaction(user_id) as t:
            row = t.execute(
                SQL_UPSERT_USER,
                {
                    "uid": user_id,
                    "dn": norm.get("display_name"),
                    "dn_default": display_name_default,
                    "sal": norm.get("monthly_salary_vnd"),
                    "pd": norm.get("payday_day"),
                    "risk": norm.get("risk_tolerance"),
                },
            )[0]
            created = bool(row["created"])
            facts: dict[str, Any] = {
                "created": created,
                "display_name": row["display_name"],
                "monthly_salary_vnd": _vnd(row["monthly_salary_vnd"])
                if row["monthly_salary_vnd"] is not None
                else None,
                "payday_day": int(row["payday_day"]) if row["payday_day"] is not None else None,
                "risk_tolerance": row["risk_tolerance"],
            }
            jars_after: list[dict[str, Any]] = []
            if created:
                t.execute(SQL_ENSURE_SYSTEM_JARS, {"uid": user_id})
                made = t.execute(SQL_TEMPLATE_JARS, {"uid": user_id, "layout": onboarding_override()})
                facts["template_jars"] = [m["code"] for m in made]
                t.execute(
                    SQL_DEFAULT_CREDIT_LINE,
                    {"uid": user_id, "product": credit_product_code, "lim": credit_limit_default},
                )
            if obligation_values is not None:
                facts["obligation"] = self._write_obligation(t, user_id, obligation_values)
            t.execute(
                SQL_AUDIT_TX,
                {
                    "uid": user_id,
                    "trace_id": audit["trace_id"],
                    "event_type": audit["event_type"],
                    "tool": tool,
                    "params": audit["params"],
                    "details": audit["details"],
                },
            )
            result = WriteResult(
                tool=tool,
                reference_id=None,
                occurred_at=now,
                app_date=app_date,
                jars_after=jars_after,
                facts=facts,
            )
            self._claim(t, user_id, claim, result)
        return result

    def _write_obligation(
        self, t: Transaction, user_id: str, v: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Thêm, sửa hoặc hủy MỘT nghĩa vụ trên dòng đã khóa. `v` do service dựng từ bản chuẩn hóa."""
        op = v["op"]
        if op == "create":
            oid = str(uuid.uuid4())
            out = t.execute(
                SQL_INSERT_OBLIGATION,
                {
                    "id": oid,
                    "uid": user_id,
                    "kind": v["kind"],
                    "name": v["name"],
                    "amount": v["amount_vnd"],
                    "amount_min": v.get("amount_min_vnd"),
                    "amount_max": v.get("amount_max_vnd"),
                    "fee": v["fee_vnd"],
                    "due_date": v["due_date"],
                    "cycle": v["cycle"],
                    "due_day": v.get("due_day"),
                    "pay_jar": v.get("pay_jar"),
                    "is_essential": v["is_essential"],
                },
            )
            return {"op": "created", **out[0]}
        locked = t.execute(SQL_LOCK_OBLIGATION, {"uid": user_id, "oid": v["obligation_id"]})
        if not locked:
            raise YofinaError(ErrorCode.OBLIGATION_NOT_FOUND, "Không tìm thấy khoản nghĩa vụ.")
        cur = locked[0]
        if cur["kind"] == "bnpl":
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, "Khoản Trả sau tự sinh khi mua, không sửa hay xóa được."
            )
        if cur["status"] != "active":
            raise YofinaError(ErrorCode.PARAMS_INVALID, "Khoản nghĩa vụ này không còn hoạt động.")
        if op == "delete":
            out = t.execute(SQL_CANCEL_OBLIGATION, {"uid": user_id, "id": v["obligation_id"]})
            return {"op": "cancelled", **out[0]}
        has_range = v.get("amount_min_vnd") is not None
        sets_amount_only = v.get("amount_vnd") is not None and not has_range
        out = t.execute(
            SQL_UPDATE_OBLIGATION,
            {
                "uid": user_id,
                "id": v["obligation_id"],
                "kind": v.get("kind"),
                "name": v.get("name"),
                "amount": v.get("amount_vnd"),
                "set_range": has_range or sets_amount_only,
                "amount_min": v.get("amount_min_vnd"),
                "amount_max": v.get("amount_max_vnd"),
                "fee": v.get("fee_vnd"),
                "due_date": v.get("due_date"),
                "cycle": v.get("cycle"),
                "due_day": v.get("due_day"),
                "pay_jar": v.get("pay_jar"),
                "is_essential": v.get("is_essential"),
            },
        )
        return {"op": "updated", **out[0]}

    # --- ghi: save_jars -------------------------------------------------------------------------------------------
    def write_save_jars(
        self,
        user_id: str,
        *,
        norm: Mapping[str, Any],
        now: datetime,
        app_date: date,
        audit: Mapping[str, Any],
        claim: ClaimSpec | None,
        tool: str,
    ) -> WriteResult:
        """Thay cả danh sách hũ người dùng; hũ bị bỏ chỉ khi số dư 0, không nghĩa vụ trả bằng nó, không lịch sử."""
        wanted = [j["code"] for j in norm["jars"]]
        with self.db.transaction(user_id) as t:
            existing = t.execute(SQL_JARS_FOR_SAVE, {"uid": user_id})
            removed = [j for j in existing if j["code"] not in wanted]
            for j in removed:
                if (
                    _vnd(j["balance_vnd"]) != 0
                    or int(j["active_obligations"])
                    or int(j["tx_count"])
                ):
                    reason = (
                        "còn tiền"
                        if _vnd(j["balance_vnd"]) != 0
                        else "còn nghĩa vụ trả bằng hũ này"
                        if int(j["active_obligations"])
                        else "đã có lịch sử giao dịch"
                    )
                    raise YofinaError(
                        ErrorCode.JAR_PROTECTED, f"Hũ {j['name']} {reason} nên chưa bỏ được."
                    )
            removed_codes = [j["code"] for j in removed]
            if removed_codes:
                t.execute(SQL_RELEASE_PAY_JAR, {"uid": user_id, "removed": removed_codes})
                t.execute(SQL_DELETE_JARS, {"uid": user_id, "removed": removed_codes})
            previous = {j["code"]: j for j in existing}
            payload = []
            for i, jar in enumerate(norm["jars"]):
                old = previous.get(jar["code"], {})
                try:
                    metadata = jar_commitments(jar, old)
                except ParamsError as exc:
                    raise YofinaError(ErrorCode.PARAMS_INVALID, str(exc)) from exc
                payload.append({**jar, **metadata, "sort_order": i})
            out = t.execute(SQL_UPSERT_JARS, {"uid": user_id, "jars": payload})
            t.execute(
                SQL_AUDIT_TX,
                {
                    "uid": user_id,
                    "trace_id": audit["trace_id"],
                    "event_type": audit["event_type"],
                    "tool": tool,
                    "params": audit["params"],
                    "details": audit["details"],
                },
            )
            result = WriteResult(
                tool=tool,
                reference_id=None,
                occurred_at=now,
                app_date=app_date,
                jars_after=[
                    {"code": r["code"], "name": r["name"], "balance_vnd": _vnd(r["balance_vnd"])}
                    for r in out
                ],
                facts={"removed": removed_codes, "count": len(payload)},
            )
            self._claim(t, user_id, claim, result)
        return result
