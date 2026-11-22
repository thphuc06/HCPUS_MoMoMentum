"""Hằng số của ví mô phỏng (phase 2): định danh và tập giá trị, cộng đúng MỘT quy tắc dùng chung là `split_amount`.

Các tập giá trị ở đây khớp `enum` trong `contracts/` và `CHECK` trong `db/migrations/0005_wallet.sql`,
0006_forecast.sql; `tests/unit/test_contracts_phase2.py` so khớp ba nơi (lệch là test đỏ). Mã hũ hệ thống là
mã cố định theo hợp đồng (người dùng không đổi được); tên hiển thị và khóa màu do `app_ensure_system_jars` đặt.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_FLOOR, Decimal

# --- hũ ----------------------------------------------------------------------------------------
OTHER_INCOME_JAR_CODE = "tien_vao_khac"  # "Tiền vào khác": tính vào tổng số dư, không phải thu nhập
UNCLASSIFIED_JAR_CODE = (
    "chua_phan_loai"  # "Chưa phân loại": tiền đã chi chưa xếp hũ, số dư có thể âm
)
SYSTEM_ROLES = ("other_income", "unclassified")
SYSTEM_JAR_CODES = {"other_income": OTHER_INCOME_JAR_CODE, "unclassified": UNCLASSIFIED_JAR_CODE}
JAR_KINDS = ("spending", "saving", "obligation", "system")
USER_JAR_KINDS = ("spending", "saving", "obligation")  # hũ người dùng tạo được (không có system)

# --- giao dịch ---------------------------------------------------------------------------------
TRANSACTION_KINDS = ("expense", "income", "transfer")
#: jar: trừ hoặc cộng số dư hũ. credit: mua bằng hạn mức trả sau, không đổi số dư hũ. external (phase 5, migration 0050): chi
#: hoặc thu NGOÀI ví, nạp từ ảnh hay CSV, không bao giờ đổi số dư hũ (jar_code chỉ để tính hành vi chi của hũ).
FUNDING_SOURCES = ("jar", "credit", "external")
EXTERNAL_FUNDING = "external"
#: nguồn trả mà `record_transaction` nhận (external chỉ vào sổ cái qua `confirm_rows` của luồng nạp)
RECORDABLE_FUNDING_SOURCES = ("jar", "credit")
CLASSIFIED_BY = ("user", "type_map", "rule", "embedding", "llm", "seed")
TX_TYPE_SALARY = "salary"
TX_TYPE_SALARY_SPLIT = "salary_split"
TX_TYPE_JAR_TRANSFER = "jar_transfer"
TX_TYPE_OBLIGATION_PAYMENT = "obligation_payment"
TX_TYPE_BNPL_PURCHASE = "bnpl_purchase"

# --- nghĩa vụ, hạn mức, lương ------------------------------------------------------------------
OBLIGATION_KINDS = ("bnpl", "loan", "rent", "bill", "subscription")
DECLARABLE_OBLIGATION_KINDS = ("loan", "rent", "bill", "subscription")  # bnpl chỉ tự sinh
OBLIGATION_CYCLES = ("once", "weekly", "monthly", "yearly")
OBLIGATION_STATUSES = ("active", "paid", "cancelled")
OBLIGATION_SOURCES = ("declared", "bnpl_auto")
BNPL_PRODUCT_CODE = "bnpl_sim"
BNPL_MONTHLY_FEE_TYPE = "monthly_service_fee"
SALARY_EVENT_STATUSES = ("pending", "confirmed", "kept_other")
SALARY_DECISIONS = ("split", "keep_as_other")
RULE_SCOPES = ("once", "always")

# --- dự báo ------------------------------------------------------------------------------------
JAR_STATUSES = ("ok", "tight", "short")  # đủ, sát, hụt
CONFIDENCE_BANDS = ("high", "medium", "low")  # Cao, Vừa, Thấp
FORECAST_TRIGGERS = ("nightly", "event", "manual", "reset", "read")
FORECAST_SERIES_KINDS = ("dense", "sparse", "cold_start")
FORECAST_EVENT_KINDS = ("obligation", "salary")

# --- thao tác ghi qua POST /confirmations và POST /actions --------------------------------------
MOVE_BETWEEN_JARS = "move_between_jars"
RECORD_TRANSACTION = "record_transaction"
ASSIGN_JAR = "assign_jar"
UPDATE_PROFILE = "update_profile"
SAVE_JARS = "save_jars"
CONFIRM_SALARY = "confirm_salary"
SCHEDULE_NUDGE = (
    "schedule_nudge"  # phase 3: nhắc (target planner); ghi bảng nudges, đi qua cùng luồng token
)
#: phase 5 (F6): chốt các dòng của một lần nạp vào sổ cái (funding external). Target Gateway là `ingest`, không phải `ledger`.
CONFIRM_ROWS = "confirm_rows"

#: Mọi `tool` mà /confirmations và /actions nhận, theo thứ tự trong OpenAPI.
ACTION_TOOLS = (
    MOVE_BETWEEN_JARS,
    RECORD_TRANSACTION,
    ASSIGN_JAR,
    UPDATE_PROFILE,
    SAVE_JARS,
    CONFIRM_SALARY,
    SCHEDULE_NUDGE,
    CONFIRM_ROWS,
)
#: Tool ghi mà agent gọi qua Gateway (target `ledger`); phần còn lại chỉ có ở REST (màn hình).
AGENT_WRITE_TOOLS = (UPDATE_PROFILE, RECORD_TRANSACTION, MOVE_BETWEEN_JARS, ASSIGN_JAR)
#: Tool ghi mà agent gọi qua Gateway ở target `planner` (phase 3). Cùng luồng token; REST `/actions` cũng nhận.
PLANNER_WRITE_TOOLS = (SCHEDULE_NUDGE,)
#: Tool ghi dùng khối `confirm_action` / `receipt_action` (move_between_jars giữ `confirm` / `receipt` của phase 1).
GENERIC_ACTION_TOOLS = tuple(t for t in ACTION_TOOLS if t != MOVE_BETWEEN_JARS)

#: Tool đọc của target `ledger` và target `forecast` (đúng thứ tự trong contracts/tools/*.json).
LEDGER_TOOLS = (
    "get_jar_balances",
    "query_transactions",
    "get_cashflow_summary",
    "get_obligations",
    "get_unclassified",
    "update_profile",
    "record_transaction",
    "move_between_jars",
    "assign_jar",
    "save_turn",
)
FORECAST_TOOLS = ("get_forecast", "run_scenario", "affordability_check")
KNOWLEDGE_TOOLS = ("get_fee_schedule",)
PLANNER_TOOLS = ("check_suitability", "schedule_nudge")
AUDIT_TOOLS = ("get_trace",)

# --- phase 3: kịch bản, nhắc, phản hồi, ý định ---------------------------------------------------
#: Sáu loại kịch bản của FR5 (khớp `kind` trong contracts/scenario/scenario_spec.schema.json).
SCENARIO_KINDS = (
    "one_time_purchase",
    "bnpl_purchase",
    "income_change",
    "recurring_expense",
    "jar_transfer",
    "goal_delay",
)
#: Loại nhắc (khớp CHECK của `nudges.kind` ở migration 0010 và `ScheduleNudge` params).
NUDGE_KINDS = (
    "runout_warning",
    "obligation_due",
    "salary_pending",
    "review_needed",
    "low_data",
    "purchase_review",
)
NUDGE_STATUSES = ("scheduled", "sent", "cancelled", "dismissed")
NUDGE_OPS = ("create", "cancel")
FEEDBACK_DECISIONS = ("accepted", "rejected")
#: Ý định của router (L1).
INTENTS = (
    "lookup",
    "what_if",
    "affordability",
    "profile_update",
    "move",
    "out_of_scope",
    "chitchat",
)
#: Loại phương án của khối `options` và `affordability_card`.
OPTION_KINDS = (
    "defer",
    "switch_jar",
    "split",
    "pay_now",
    "use_credit",
    "proceed",
    "reduce_amount",
    "move_between_jars",
    "remind_later",
    "skip",
)


# --- quy tắc chia lương (dùng chung ledger.confirm_salary và lịch lương của dự báo, để hai nơi không lệch) -----------
def split_amount(
    amount_vnd: int, shares: Sequence[tuple[str, int | float | str | Decimal]]
) -> dict[str, int]:
    """Chia `amount_vnd` cho các hũ theo tỷ lệ phần trăm.

    Mỗi hũ nhận `floor(amount * percent / 100)` (VND nguyên); phần dư do làm tròn xuống (nhỏ hơn số hũ) cộng cho hũ có
    tỷ lệ LỚN NHẤT, hòa thì hũ đứng trước trong `shares`. Tổng tỷ lệ phải bằng đúng 100 (so bằng Decimal để không lệch
    số thực), tổng các phần luôn bằng `amount_vnd`. Hũ tỷ lệ 0 nhận 0 và vẫn có mặt trong kết quả.

    >>> split_amount(1_000_000, [("a", 33), ("b", 33), ("c", 34)])
    {'a': 330000, 'b': 330000, 'c': 340000}
    >>> split_amount(100, [("a", "33.33"), ("b", "33.33"), ("c", "33.34")])
    {'a': 33, 'b': 33, 'c': 34}
    """
    if amount_vnd < 0:
        raise ValueError("amount_vnd không được âm")
    if not shares:
        raise ValueError("cần ít nhất một hũ để chia")
    percents = [Decimal(str(p)) for _, p in shares]
    if any(p < 0 for p in percents) or sum(percents) != Decimal(100):
        raise ValueError("tổng tỷ lệ chia phải bằng đúng 100 và không có tỷ lệ âm")
    parts = [
        int((Decimal(amount_vnd) * p / Decimal(100)).to_integral_value(rounding=ROUND_FLOOR))
        for p in percents
    ]
    remainder = amount_vnd - sum(parts)
    biggest = max(range(len(percents)), key=lambda i: (percents[i], -i))
    parts[biggest] += remainder
    out: dict[str, int] = {}
    for (code, _), part in zip(shares, parts, strict=True):
        if code in out:
            raise ValueError(f"mã hũ trùng: {code}")
        out[code] = part
    return out
