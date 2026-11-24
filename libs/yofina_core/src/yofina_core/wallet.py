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
#: phase 5 (F6): chốt các dòng của một lần nạp vào sổ cái (funding external). Target Gateway là `ingest`, không phải `ledger`;
#: REST phục vụ ở `POST /ingest/confirmations` và `POST /ingest/actions` (Lambda `ingest`), KHÔNG ở /confirmations và /actions.
CONFIRM_ROWS = "confirm_rows"

#: Mọi `tool` mà `POST /confirmations` và `POST /actions` của Lambda `ledger` nhận, theo thứ tự trong OpenAPI (không có
#: `confirm_rows`: tool đó chỉ đi qua hai endpoint `/ingest/*` ở dưới).
ACTION_TOOLS = (
    MOVE_BETWEEN_JARS,
    RECORD_TRANSACTION,
    ASSIGN_JAR,
    UPDATE_PROFILE,
    SAVE_JARS,
    CONFIRM_SALARY,
    SCHEDULE_NUDGE,
)
#: `tool` mà `POST /ingest/confirmations` và `POST /ingest/actions` (Lambda `ingest`) nhận: chỉ `confirm_rows`. Cùng schema
#: yêu cầu và biên nhận với ledger, cùng khóa HMAC và bảng `jti`; tool khác gửi vào đó bị 422 PARAMS_INVALID.
INGEST_ACTION_TOOLS = (CONFIRM_ROWS,)
#: Phase 5 (quyền riêng tư): "Xóa dữ liệu của tôi". Chỉ đi qua `POST /me/delete-data/confirmations` rồi `POST /me/delete-data`
#: (Lambda `ledger`), cùng khóa HMAC và bảng `jti`; không phải tool Gateway (agent không xóa dữ liệu được) và không dùng khối
#: `confirm_action` (màn Hồ sơ tự dựng bước xác nhận).
DELETE_MY_DATA = "delete_my_data"
PRIVACY_ACTION_TOOLS = (DELETE_MY_DATA,)
#: Phạm vi của `delete_my_data`: chỉ "tất cả" (xóa riêng bộ nhớ thì dùng `DELETE /memory`).
DATA_DELETION_SCOPES = ("all",)
#: Tool ghi mà agent gọi qua Gateway (target `ledger`); phần còn lại chỉ có ở REST (màn hình).
AGENT_WRITE_TOOLS = (UPDATE_PROFILE, RECORD_TRANSACTION, MOVE_BETWEEN_JARS, ASSIGN_JAR)
#: Tool ghi mà agent gọi qua Gateway ở target `planner` (phase 3). Cùng luồng token; REST `/actions` cũng nhận.
PLANNER_WRITE_TOOLS = (SCHEDULE_NUDGE,)
#: Tool ghi dùng khối `confirm_action` / `receipt_action` (move_between_jars giữ `confirm` / `receipt` của phase 1), gồm
#: cả tool của `ingest`.
GENERIC_ACTION_TOOLS = tuple(t for t in ACTION_TOOLS + INGEST_ACTION_TOOLS if t != MOVE_BETWEEN_JARS)

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
#: Phase 4 thêm `get_resilience_score` và `stress_test` ở cuối target `forecast`; phase 5 thêm `get_behavior_profile`.
FORECAST_TOOLS = (
    "get_forecast",
    "run_scenario",
    "list_scenarios",
    "affordability_check",
    "get_resilience_score",
    "stress_test",
    "get_behavior_profile",
)
#: Phase 5 không thêm tool vào target `knowledge` (chủ dự án cắt luồng RAG ngày 24/11): khối `citation` dựng từ kết quả
#: `get_fee_schedule`.
KNOWLEDGE_TOOLS = ("get_fee_schedule",)
#: Phase 4 thêm `optimize_allocation`, `save_roadmap`, `get_roadmap` ở cuối target `planner`. `save_roadmap` là tool GHI nhưng
#: KHÔNG qua token (không đổi số dư; quyết định số 3 của phase 4), nên KHÔNG nằm trong `PLANNER_WRITE_TOOLS` hay `ACTION_TOOLS`.
PLANNER_TOOLS = (
    "check_suitability",
    "schedule_nudge",
    "optimize_allocation",
    "save_roadmap",
    "get_roadmap",
)
#: Tool phase 5 mà hợp đồng đã khai báo nhưng Lambda chưa cài. Rỗng từ 24/11: `forecast___get_behavior_profile` đã cài (luồng
#: p5-behavior, `yofina_forecast.behavior`). Luồng cài tool mới thì xóa tên khỏi đây và thêm vào `_ARG_KEYS` của Lambda.
PHASE5_TOOLS: tuple[str, ...] = ()
#: Tool đã khai báo trong hợp đồng mà Lambda chưa cài (test `test_ledger_wallet` dùng tập này để khỏi đòi `_ARG_KEYS` có chúng).
#: Năm tool phase 4 đã cài từ 23/11; tên giữ nguyên cho test cũ, nay là "tool chưa cài" của mọi phase, tức `PHASE5_TOOLS`.
PHASE4_TOOLS: tuple[str, ...] = PHASE5_TOOLS
AUDIT_TOOLS = ("get_trace", "record_turn")

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
#: Phase 5 (FR13): loại bản tin do CỔNG GIÁ TRỊ của batch đêm chọn (`nudges.source = 'system'`), theo THỨ TỰ ƯU TIÊN của cổng:
#: hũ thiết yếu sắp cạn, nghĩa vụ trong 3 ngày, lộ trình mới chờ chọn, hỏi gộp, điểm chống chịu tụt nhóm, nhận xét hành vi.
#: Ba loại mới không nằm trong `NUDGE_KINDS` vì người dùng và agent không tự lên lịch được chúng bằng `schedule_nudge`.
NUDGE_GATE_ORDER = (
    "runout_warning",
    "obligation_due",
    "roadmap_proposed",
    "review_needed",
    "resilience_drop",
    "behavior_insight",
)
SYSTEM_NUDGE_KINDS = NUDGE_GATE_ORDER
#: Mọi loại của cột `nudges.kind` (migration 0053 nới CHECK của 0010): loại lên lịch được, rồi ba loại chỉ cổng giá trị sinh.
ALL_NUDGE_KINDS = (*NUDGE_KINDS, *(k for k in NUDGE_GATE_ORDER if k not in NUDGE_KINDS))
NUDGE_STATUSES = ("scheduled", "sent", "cancelled", "dismissed")
#: Phản hồi của người dùng với một bản tin (`POST /nudges/{nudge_id}/feedback`, cột `nudges.outcome`): đã làm theo, bỏ qua lần
#: này, "Để sau", "Ít nhắc loại này" (hạ loại đó một bậc ở cổng).
NUDGE_OUTCOMES = ("acted", "dismissed", "snoozed", "less_like_this")
NUDGE_SOURCES = ("user_option", "agent", "system")
NUDGE_OPS = ("create", "cancel")
FEEDBACK_DECISIONS = ("accepted", "rejected")
#: Ý định của router (L1) ở phase 3. Cột `audit_events.intent` của migration 0010 chỉ chấp nhận bảy giá trị này; migration
#: 0052 nới CHECK thành `INTENTS` (test_migration_0010 khóa bản cũ bằng tuple này, test_migration_0052 khóa bản mới).
INTENTS_PHASE3 = (
    "lookup",
    "what_if",
    "affordability",
    "profile_update",
    "move",
    "out_of_scope",
    "chitchat",
)
#: Ý định của router (L1): bảy ý định phase 3 và ba ý định phase 4 (`resilience`: hỏi điểm chống chịu, `stress`: bấm hoặc hỏi một
#: cú sốc, `roadmap`: xin hoặc hỏi lộ trình). Luồng C cài router và xử lý chúng; hợp đồng chỉ khai báo. Phase 5 thêm dần các ý định
#: đã cài: `behavior` (luồng p5-behavior, `yofina_agent.behavior_chat`).
INTENTS = (*INTENTS_PHASE3, "resilience", "stress", "roadmap", "behavior")
#: Ý định của phase 5 CHƯA cài (router chưa chọn được, `agent/.../schemas.py` `Intent` khớp `INTENTS`):
#: `knowledge` (hỏi biểu phí kèm trích dẫn: số từ `get_fee_schedule`,
#: khối `citation` dựng từ nguồn của chính bảng phí; không có tìm kiếm tài liệu), `ingest` ("mình vừa nạp ảnh": trạng thái lần
#: nạp và bảng duyệt), `memory` (người dùng nói một sở thích để nhớ, hoặc hỏi trợ lý nhớ gì về mình). Luồng nào cài bộ xử lý thì
#: chuyển ý định của mình vào `INTENTS` cùng lúc với `Intent` của agent. `behavior` (hỏi về thói quen chi tiêu) đã chuyển.
PHASE5_INTENTS = ("knowledge", "ingest", "memory")
#: Ý định mà cột `audit_events.intent` chấp nhận (migration 0053 nới CHECK): mọi ý định đã cài và bốn ý định phase 5, để
#: `audit___record_turn` không vỡ ở lượt có ý định mới trong lúc các luồng cài dần.
AUDIT_INTENTS = (*INTENTS, *PHASE5_INTENTS)
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


# --- phase 4: điểm chống chịu, cú sốc, lộ trình, phân hũ tự động -------------------------------------
#: Bốn thành phần của Điểm chống chịu (proposal §11), theo thứ tự hiển thị.
RESILIENCE_COMPONENTS = ("save", "spend", "borrow", "plan")
#: Nhóm điểm (luôn kèm chữ ở giao diện, không chỉ màu): yếu, vừa, tốt. Ngưỡng nằm ở `resilience_defaults.json`.
RESILIENCE_BANDS = ("weak", "fair", "strong")
#: Điểm được tính do đâu (cột `resilience_scores.source`).
RESILIENCE_SOURCES = ("nightly", "reset", "event", "read")
#: Loại cú sốc (dữ liệu ở `shocks.json`; mỗi loại đòi các tham số riêng, xem `yofina_core.resilience.ShockParams`).
SHOCK_KINDS = ("income_loss", "expense_increase", "health_event")
#: Lý do một phiên bản lộ trình ra đời (cột `roadmaps.reason_code`).
ROADMAP_REASON_CODES = (
    "initial",
    "behavior_changed",
    "goal_changed",
    "income_changed",
    "forecast_drift",
    "user_request",
    "step_edited",
)
#: Lý do mà phiên bản mới được dùng NGAY (`active`); mọi lý do khác tạo bản `proposed` để người dùng chọn "Dùng bản mới" hay "Giữ bản cũ".
ROADMAP_ACTIVE_REASONS = ("initial", "step_edited")
#: Trạng thái một phiên bản: đang dùng, bản mới chờ chọn, đã bị thay, đã bỏ ("Giữ bản cũ").
ROADMAP_VERSION_STATUSES = ("active", "proposed", "superseded", "discarded")
#: Trạng thái một bước: chờ, đã chấp nhận, đã từ chối.
ROADMAP_STEP_STATUSES = ("pending", "accepted", "rejected")
ROADMAP_STEP_KINDS = (
    "set_aside",
    "adjust_split",
    "pay_obligation",
    "cut_spending",
    "review_goal",
    "remind",
)
#: Tool mà một bước có thể gắn để người dùng thực hiện bằng luồng xác nhận (ADR-0002): chuyển hũ, đổi tỷ lệ chia, nhắc.
ROADMAP_STEP_ACTION_TOOLS = ("move_between_jars", "save_jars", "schedule_nudge")
ROADMAP_FEASIBILITIES = ("on_track", "relaxed", "infeasible")
#: Kết quả của `optimize_allocation` (trùng `ROADMAP_FEASIBILITIES`: lộ trình thừa hưởng).
ALLOCATION_STATUSES = ("optimal", "relaxed", "infeasible")
ALLOCATION_RELAXATION_KINDS = ("goal_delayed", "discretionary_reduced")
#: Lựa chọn nói thẳng khi mục tiêu không khả thi (đúng hai lựa chọn).
ALTERNATIVE_KINDS = ("delay_goal", "reduce_goal", "cut_discretionary")
ROADMAP_JOB_STATUSES = ("queued", "running", "done", "failed")
ROADMAP_JOB_STAGES = ("context", "draft", "allocate", "suitability", "save")
ROADMAP_JOB_TRIGGERS = ("user_request", "behavior_changed", "goal_changed", "income_changed", "forecast_drift")
ROADMAP_DECISIONS = ("accepted", "rejected", "pending")
ROADMAP_VERSION_DECISIONS = ("adopt", "keep_previous")
ROADMAP_WHICH = ("active", "proposed", "latest")
#: Đổi hành vi (bảng `behavior_flags`): nghi (CUSUM hoặc PageHinkley trong đường sự kiện), đã xác nhận (PELT trong batch đêm),
#: báo nhầm, đã dùng để sinh lại lộ trình.
BEHAVIOR_FLAG_STATUSES = ("suspected", "confirmed", "dismissed", "applied")
BEHAVIOR_METHODS = ("cusum", "page_hinkley", "pelt")
BEHAVIOR_DIRECTIONS = ("up", "down")
#: Ba mức tin cậy của phân loại tự động (ngưỡng ở cấu hình, hiệu chỉnh trên dữ liệu): tự gán; tự gán và vào "Xem lại"; hỏi gộp.
CLASSIFICATION_TIERS = ("auto", "review", "ask")
#: Hai chế độ của khối `review_list`: A1 "Xem lại" (mức `review`) và A2 hỏi gộp một lần mỗi ngày (mức `ask`).
REVIEW_MODES = ("review", "daily_ask")
REVIEW_ASK_STATUSES = ("open", "answered", "skipped")
#: Nguồn của một dòng trong bộ nhãn k-NN (`tx_embeddings_labeled`): người dùng sửa, hoặc nhãn seed của persona.
LABEL_SOURCES = ("user", "seed")
#: Số chiều vector của vai `embedding` (`cohere.embed-multilingual-v3`, xem `llm_defaults.json`); khớp `vector(1024)` ở 0052.
EMBEDDING_DIMENSIONS = 1024

# --- phase 5: hồ sơ hành vi, bản tin, xóa dữ liệu ----------------------------------------------------
#: Hồ sơ hành vi được tính do đâu (cột `behavior_profiles.source`, migration 0053).
BEHAVIOR_PROFILE_SOURCES = ("nightly", "reset", "manual")
BEHAVIOR_INSIGHT_KINDS = (
    "payday_cycle",
    "weekday_pattern",
    "time_of_day",
    "bnpl_usage",
    "category_trend",
    "spending_cluster",
)
#: Lý do cổng giá trị bỏ một loại bản tin (`NudgeSuppressed.reason` của `GET /nudges/today`).
NUDGE_SUPPRESS_REASONS = ("below_threshold", "demoted", "quiet_hours", "lower_rank")
