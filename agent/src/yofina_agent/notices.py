"""Lời nhắn hệ thống của khối `notice` (nội dung giao diện, không phải câu trả lời cho người dùng).

Đây là chuỗi sản phẩm cố định theo **mã lỗi** (ví dụ chạm trần model, hết lượt), không phụ thuộc câu
hỏi của người dùng và không chứa số liệu tài chính. Câu trả lời trong chat luôn do model sinh ở lượt đó.
"""

from __future__ import annotations

from yofina_core.errors import ErrorCode

# mã -> (tiêu đề <= 80, nội dung <= 280)
DEGRADED: dict[str, tuple[str, str]] = {
    ErrorCode.MODEL_BUDGET_EXCEEDED: (
        "Đang ở chế độ rút gọn",
        "Hôm nay mình đã dùng hết lượt trả lời bằng AI nên chỉ hiện số liệu. "
        "Bạn vẫn xem và thao tác được bình thường.",
    ),
    ErrorCode.RATE_LIMITED: (
        "Trợ lý đang bận",
        "Dịch vụ AI đang quá tải nên lúc này mình chỉ hiện số liệu. Bạn thử hỏi lại sau ít phút nhé.",
    ),
    ErrorCode.INTERNAL_ERROR: (
        "Đang ở chế độ rút gọn",
        "Phần trả lời bằng AI đang gặp sự cố nên mình chỉ hiện số liệu lấy trực tiếp từ sổ cái của bạn.",
    ),
    "NUMERIC_UNVERIFIED": (
        "Hãy đối chiếu số liệu",
        "Một số con số trong câu trả lời chưa khớp với dữ liệu lấy từ sổ cái. "
        "Hãy lấy số trên thẻ số liệu làm chuẩn.",
    ),
    "NOT_UNDERSTOOD": (
        "Chưa xử lý được yêu cầu",
        "Bộ hiểu câu hỏi bằng AI đang tạm nghỉ nên mình chưa hiểu được yêu cầu này. "
        "Bạn thử hỏi số dư, giao dịch, dự báo một hũ hoặc chuyển tiền giữa các hũ nhé.",
    ),
}

OUT_OF_SCOPE: tuple[str, str] = (
    "Ngoài phạm vi hiện tại",
    "Yofina giúp bạn quản lý chi tiêu theo hũ: xem số dư, dự báo hũ, thử kịch bản \"nếu mua...\" và kiểm tra trước khi chi. "
    "Mình không tư vấn đầu tư (mã cổ phiếu, quỹ, tiền mã hóa) và chưa làm được việc này.",
)

# Chip và danh sách gợi ý cho khối `suggestions` (nhãn giao diện, không phải câu trả lời).
CAN_DO: tuple[str, ...] = (
    "Xem số dư và dự báo từng hũ",
    "Thử kịch bản \"nếu mua...\" (cả bằng Trả sau)",
    "Kiểm tra trước khi chi hoặc chuyển tiền",
    "Chuyển tiền giữa các hũ, khai lương và nghĩa vụ",
    "Điểm chống chịu, thử cú sốc và lộ trình tiết kiệm",
    "Thói quen chi tiêu, phí Trả sau và nạp sao kê ngoài ví",
)
CANNOT_DO: tuple[str, ...] = (
    "Tư vấn mua cổ phiếu, quỹ, tiền mã hóa",
    "Tự ghi hay chuyển tiền khi bạn chưa xác nhận",
)
SUGGESTION_ITEMS: tuple[dict[str, str], ...] = (
    # Hai chip đầu đưa người dùng quay về chống chịu (intent resilience) và lộ trình đang dùng (intent roadmap, xem):
    # cảnh 4 của kịch bản demo (docs/research/figma-ui-design.md §8.2, frame H7 → R1, L1).
    {"id": "resilience", "label": "Điểm chống chịu của mình", "prompt": "Điểm chống chịu tài chính của mình hiện là bao nhiêu?"},
    {"id": "roadmap", "label": "Xem lộ trình", "prompt": "Cho mình xem lộ trình tiết kiệm đang dùng"},
    {"id": "balances", "label": "Xem số dư các hũ", "prompt": "Số dư các hũ của mình"},
    {"id": "forecast", "label": "Hũ nào sắp cạn?", "prompt": "Hũ nào của mình sắp cạn?"},
    {"id": "what_if", "label": "Thử kịch bản mua sắm", "prompt": "Nếu mua tai nghe 1,2 triệu bằng Trả sau thì sao?"},
    {"id": "check", "label": "Kiểm tra trước khi chi", "prompt": "Mình chi 500 nghìn lúc này có ổn không?"},
)
SUGGESTIONS_TITLE = "Mình có thể giúp bạn"

# Ô còn thiếu -> câu hỏi và chip (khối `clarify`). Chỉ là nhãn của ô thiếu, không gắn với câu mẫu nào.
CLARIFY: dict[str, dict] = {
    "amount": {
        "question": "Khoản này khoảng bao nhiêu tiền?",
        "chips": [
            {"label": "500 nghìn", "value": "500 nghìn"},
            {"label": "1 triệu", "value": "1 triệu"},
            {"label": "5 triệu", "value": "5 triệu"},
        ],
    },
    "funding_source": {
        "question": "Bạn định trả bằng tiền trong hũ hay bằng Trả sau (mô phỏng)?",
        "chips": [
            {"label": "Trừ vào hũ", "value": "Trả bằng tiền trong hũ"},
            {"label": "Trả sau (mô phỏng)", "value": "Trả bằng Trả sau (mô phỏng)"},
        ],
    },
    "jar": {
        "question": "Bạn muốn chuyển từ hũ nào sang hũ nào?",
        "chips": [],
    },
    "pay_jar": {
        "question": "Bạn định trả bằng tiền của hũ nào?",
        "chips": [],
    },
    "obligation_kind": {
        "question": "Khoản này là tiền trọ, hóa đơn, thuê bao hay khoản vay?",
        "chips": [
            {"label": "Tiền trọ", "value": "Đây là tiền trọ"},
            {"label": "Hóa đơn", "value": "Đây là hóa đơn"},
            {"label": "Thuê bao", "value": "Đây là thuê bao"},
            {"label": "Khoản vay", "value": "Đây là khoản vay"},
        ],
    },
    "other": {
        "question": "Bạn muốn khai hoặc sửa thông tin nào (lương, ngày nhận lương hay một khoản nghĩa vụ)?",
        "chips": [
            {"label": "Lương", "value": "Lương của mình là"},
            {"label": "Tiền trọ", "value": "Tiền trọ của mình là"},
        ],
    },
}

LOW_DATA: tuple[str, str] = (
    "Dữ liệu còn ít",
    "Dự báo này dựa trên ít dữ liệu hoặc là ước lượng ban đầu nên độ tin cậy còn thấp. "
    "Bạn nạp thêm lịch sử giao dịch để mình ước lượng chính xác hơn.",
)
LOW_COVERAGE: tuple[str, str] = (
    "Độ tin cậy thấp",
    "Khoảng dự báo của hũ này đang kém chắc chắn, hãy xem con số như một ước lượng.",
)
PARTIAL: tuple[str, str] = (
    "Mới có một phần kết quả",
    "Một số dữ liệu chưa lấy được nên mình chỉ hiện phần đã có. Bạn thử lại sau ít phút nhé.",
)
VERIFIER_FAILED: tuple[str, str] = (
    "Chỉ hiện số liệu",
    "Mình chưa kiểm chứng được phần giải thích và gợi ý, nên chỉ hiện số liệu tính trực tiếp từ dữ liệu của bạn.",
)
#: Verifier hết vòng sửa nhưng vẫn còn ít nhất 2 phương án tự qua kiểm tra: bỏ lời giải thích, giữ số liệu và phương án.
VERIFIER_FAILED_OPTIONS_ONLY: tuple[str, str] = (
    "Chưa có lời giải thích",
    "Mình chưa kiểm chứng được phần giải thích, nên chỉ hiện số liệu và các phương án đã qua kiểm tra luật.",
)
#: Phương án dựng bằng mã cho đường suy giảm của khoản chi what-if: loại phương án -> (nhãn <= 60, tóm tắt <= 140).
#: Không chi tiền ngay và không chứa số liệu.
SAFE_OPTION_TEXTS: dict[str, tuple[str, str]] = {
    "skip": (
        "Chưa mua lúc này",
        "Giữ nguyên số dư các hũ, không phát sinh khoản chi hay khoản phải trả mới.",
    ),
    "defer": (
        "Hoãn tới sau kỳ lương",
        "Xem lại khoản này sau kỳ lương tới thay vì quyết định ngay bây giờ.",
    ),
}
GUARDRAIL_OUTPUT_BLOCKED: tuple[str, str] = (
    "Chỉ hiện số liệu",
    "Phần lời giải thích không đạt kiểm tra an toàn nên mình chỉ hiện số liệu.",
)
#: Phương án "dùng hũ khác" (switch_jar) của what-if: nhãn và tóm tắt dựng bằng mã từ hũ THẬT của đề xuất (`proposal.jar_code`) và số dư
#: của hũ đó, để tiêu đề và nội dung không lệch nhau (model từng ghi "Mua bằng hũ Giải trí" cho đề xuất lấy tiền hũ Dự phòng).
#: {name}: tên hũ; {amount}: số tiền lấy ra; {balance}: số dư hiện tại của hũ (đều đã định dạng).
SWITCH_JAR_LABEL = "Mua bằng hũ {name}"
SWITCH_JAR_SUMMARY_ENOUGH = "Trả {amount} bằng tiền hũ {name}; hũ đang có {balance}, đủ cho khoản này."
SWITCH_JAR_SUMMARY_SHORT = "Hũ {name} chỉ còn {balance}, không đủ trả {amount}."
#: Tên hũ người dùng gõ không khớp hũ nào (hoặc khớp nhiều hũ): đúng một câu hỏi, chip là các hũ có thật.
UNKNOWN_JAR_QUESTION = "Mình chưa thấy hũ “{name}” trong ví của bạn. Bạn muốn dùng hũ nào?"
UNKNOWN_JAR_QUESTION_NO_NAME = "Mình chưa xác định được hũ bạn nói. Bạn muốn dùng hũ nào?"
#: Lượt chỉ đọc tự chọn hũ trả khi người dùng không nêu hũ (`clarify.infer_pay_jar`): khối `notice` thông tin nói đang tính theo hũ nào
#: và cách đổi. {name}: tên hũ; {label}: nhãn loại chi của bảng tra loại giao dịch (chỉ khi hũ suy từ loại chi). Không có dấu hỏi (lịch
#: sử không coi đây là câu hỏi đang chờ).
INFERRED_JAR_CODE = "PAY_JAR_INFERRED"
INFERRED_JAR_TITLE = "Tính theo hũ {name}"
INFERRED_JAR_MESSAGE = (
    "Bạn chưa nói hũ nào nên mình tính theo hũ {name}, hũ nhận các khoản loại “{label}” trong ví của bạn. "
    "Muốn tính theo hũ khác, bạn nhắn tên hũ đó nhé."
)
#: Như trên khi router chọn hũ theo mục đích khoản chi trong danh sách hũ của ví (`spend_jar_code`).
INFERRED_JAR_MESSAGE_INTENT = (
    "Bạn chưa nói hũ nào nên mình tính theo hũ {name}, hũ hợp với mục đích khoản chi này trong ví của bạn. "
    "Muốn tính theo hũ khác, bạn nhắn tên hũ đó nhé."
)

STRESS_QUESTION = "Bạn muốn thử cú sốc nào?"
STRESS_CHIP_VALUE = "Thử cú sốc {label}"
#: Câu trả lời "hũ nào sắp cạn?" dựng bằng mã từ dự báo của từng hũ (`compact.compact_forecast_overview`), không cần lượt gọi model.
#: {jar}: tên hũ; {date}: ngày cạn dd/mm; {days}: số ngày trước kỳ lương; {payday}: ngày lương dd/mm; {items}: danh sách hũ và ngày cạn;
#: {count}: số hũ; {names}: tên các hũ nối bằng dấu phẩy.
FORECAST_OVERVIEW_ONE = "Hũ {jar} dự kiến cạn ngày {date}, sớm {days} ngày so với kỳ lương {payday}."
FORECAST_OVERVIEW_MANY = "Trước kỳ lương {payday} có {count} hũ dự kiến cạn: {items}."
FORECAST_OVERVIEW_ITEM = "{jar} ngày {date}"
FORECAST_OVERVIEW_NONE = "Chưa hũ nào dự kiến cạn trước kỳ lương {payday}."
FORECAST_OVERVIEW_NONE_NO_PAYDAY = "Chưa hũ nào dự kiến cạn trong khoảng dự báo."
FORECAST_OVERVIEW_TIGHT = "Hũ {names} đang sát số dư trước kỳ lương."
#: Hũ thưa hụt (#25, `runout_date_shown` sai): không nêu ngày cạn, chỉ nói có thể cạn trước ngày lương (cùng chữ với thẻ và giao diện).
FORECAST_OVERVIEW_MAY_RUN_OUT = "Hũ {names} có thể cạn trước ngày lương."
FORECAST_OVERVIEW_REST_OK = "Các hũ còn lại đủ tới kỳ lương."
FORECAST_OVERVIEW_UNAVAILABLE = "Chưa có dự báo cho hũ {names}."
FORECAST_OVERVIEW_CHART = "Biểu đồ bên dưới là của hũ {jar}."
ROADMAP_UNBUILDABLE: tuple[str, str] = (
    "Chưa lập được lộ trình",
    "Mình chưa lập được lộ trình phù hợp với dữ liệu hiện có. Bạn có thể thử lại sau.",
)
#: Lý do ngắn của một phiên bản lộ trình theo `reason_code` (nhãn giao diện, không chứa số).
ROADMAP_REASON_LABELS: dict[str, str] = {
    "initial": "bản đầu tiên",
    "behavior_changed": "hành vi thay đổi",
    "goal_changed": "mục tiêu thay đổi",
    "income_changed": "thu nhập thay đổi",
    "forecast_drift": "dự báo lệch",
    "user_request": "bạn yêu cầu lập lại",
    "step_edited": "bạn sửa một bước",
}
ROADMAP_REASON_FALLBACK = "có thay đổi"
#: Người dùng nêu mục tiêu lộ trình (số tiền hoặc hạn) mà chưa rõ hũ nào: đúng một câu hỏi, chip là các hũ gắn được mục tiêu lộ trình.
ROADMAP_GOAL_JAR_QUESTION = "Mục tiêu này thuộc hũ nào để mình lập lộ trình?"
#: Bản vừa lưu làm bản đề xuất đang chờ bị bỏ (`discarded`). {old}: số phiên bản bị thay; {reason}: nhãn lý do ở trên;
#: {active}: số phiên bản đang dùng.
ROADMAP_PROPOSAL_REPLACED_TITLE = "Đã thay bản đề xuất đang chờ"
ROADMAP_PROPOSAL_REPLACED = "Bản này thay bản đề xuất phiên bản {old} (lý do: {reason}) đang chờ bạn chọn."
ROADMAP_PROPOSED_NEXT = (
    "Bản đang dùng vẫn là phiên bản {active}. Mở trang Lộ trình để so với bản đang dùng, rồi chọn Dùng bản mới "
    "hoặc Giữ bản cũ."
)
#: Lời kết của lượt lập lộ trình, dựng bằng mã từ dữ liệu khối (không cần lượt gọi model): bản này là gì, bản nào đang dùng,
#: khả năng kịp mục tiêu và bước tiếp theo. {version}: phiên bản vừa lưu; {phases}, {steps}: số giai đoạn, số bước;
#: {active}: phiên bản đang dùng; {goal}: mục tiêu người dùng nói ("1.000.000.000 ₫ cho hũ Du lịch trước 30/11/2026").
ROADMAP_CLOSING_PROPOSED = (
    "Đây là bản đề xuất phiên bản {version} ({phases} giai đoạn, {steps} bước), chưa thay lộ trình bạn đang dùng."
)
ROADMAP_CLOSING_IN_USE = "Bản đang dùng vẫn là phiên bản {active}."
ROADMAP_CLOSING_ACTIVE = "Đây là lộ trình bạn đang dùng, phiên bản {version} ({phases} giai đoạn, {steps} bước)."
ROADMAP_CLOSING_OTHER = "Đây là lộ trình phiên bản {version} ({phases} giai đoạn, {steps} bước)."
ROADMAP_CLOSING_FEASIBILITY: dict[str, str] = {
    "on_track": "Theo phương án phân bổ đề xuất, mục tiêu kịp hạn.",
    "relaxed": "Mục tiêu chỉ kịp sau khi nới hạn hoặc mức, chi tiết ở thẻ.",
    "infeasible": "Với thu nhập hiện tại, mục tiêu chưa khả thi trong hạn.",
}
ROADMAP_CLOSING_GOAL_INFEASIBLE = "Với thu nhập hiện tại, mục tiêu {goal} chưa khả thi."
ROADMAP_CLOSING_GOAL_NOTE = "Mục tiêu {goal} chỉ dùng để lập lộ trình này, chưa lưu vào hũ."
ROADMAP_CLOSING_GOAL_NOTE_SHORT = "Mục tiêu này chỉ dùng để lập lộ trình, chưa lưu vào hũ."
ROADMAP_CLOSING_ALTERNATIVES = "Thẻ có {count} lựa chọn thay thế để bạn cân nhắc."
ROADMAP_CLOSING_NEXT_COMPARE = (
    "Bước tiếp theo: bấm So với bản đang dùng trên thẻ, rồi chọn Dùng bản mới hoặc Giữ bản cũ."
)
ROADMAP_CLOSING_NEXT_REVIEW = (
    "Bước tiếp theo: mở trang Lộ trình để chấp nhận, sửa hoặc từ chối từng bước."
)
#: Người dùng muốn sửa một bước trong chat (chat chưa có tool sửa bước): chỗ sửa trên giao diện. Vừa là dữ kiện `cach_sua` cho writer
#: (writer chỉ ra bước người dùng nói tới từ bản gọn các bước), vừa là lời đáp khi writer không viết được. Không chứa số.
ROADMAP_EDIT_HOW = (
    "Mình chưa sửa được bước ngay trong chat nên chưa đổi gì. Bấm Mở trang Lộ trình trên thẻ, rồi bấm Sửa ở bước đó "
    "để đổi số tiền hoặc ngày."
)
ROADMAP_EDIT_NO_ROADMAP = (
    "Bạn chưa có lộ trình đang dùng nên chưa có bước nào để sửa. Muốn lập lộ trình, bạn nhắn “Lập lộ trình giúp mình” nhé."
)

# Gộp kịch bản trong một cuộc trò chuyện: khoản mới cùng hũ với khoản người dùng đã hỏi trước đó.
# {previous}: nhãn các khoản trước (do engine dựng, ví dụ "mua giày 800k"); {jar}: tên hũ; {new}: nhãn khoản mới.
# Router xếp "ngoài phạm vi" nhưng câu có dấu hiệu chi tiêu của chính người dùng (số tiền, món mua): hỏi xác nhận thay vì từ chối cứng.
# {what}: nhãn khoản ("đi du lịch 5.000.000 ₫") dựng bằng mã từ tham số router; rỗng thì dùng câu không tên.
CONFIRM_SPENDING_QUESTION = "Mình chưa chắc bạn muốn làm gì với khoản {what}. Bạn muốn mình làm việc nào?"
CONFIRM_SPENDING_QUESTION_NO_NAME = "Mình chưa chắc ý bạn. Bạn muốn mình xem khoản chi này theo cách nào?"
CONFIRM_SPENDING_CHIPS: list[dict[str, str]] = [
    {"label": "Thử nếu chi khoản này", "value": "Mô phỏng giúp mình nếu chi khoản này"},
    {"label": "Kiểm tra có đủ tiền không", "value": "Kiểm tra giúp mình khoản này có ổn không"},
    {"label": "Không cần", "value": "Không cần đâu, cảm ơn"},
]

KEEP_PREVIOUS_MARKER = "Bạn vẫn giữ ý định đó chứ?"
KEEP_PREVIOUS_QUESTION = "Trước đó bạn có hỏi {previous} từ hũ {jar}. " + KEEP_PREVIOUS_MARKER + " Nếu giữ, mình tính gộp với {new}."
KEEP_PREVIOUS_CHIPS: list[dict[str, str]] = [
    {"label": "Vẫn giữ, tính gộp", "value": "Vẫn giữ khoản trước, tính gộp cả hai"},
    {"label": "Chỉ tính khoản mới", "value": "Bỏ khoản trước, chỉ tính khoản mới"},
]

SCENARIO_UNBUILDABLE: tuple[str, str] = (
    "Chưa dựng được kịch bản",
    "Mình chưa hiểu đủ để dựng kịch bản này. Bạn nói rõ món gì, bao nhiêu tiền và trả bằng cách nào nhé.",
)

# Tiêu đề cho lỗi của tool (nội dung lấy từ chính thông điệp tiếng Việt của tool).
ERROR_TITLES: dict[str, str] = {
    ErrorCode.INSUFFICIENT_FUNDS: "Không đủ số dư",
    ErrorCode.JAR_NOT_FOUND: "Không tìm thấy hũ",
    ErrorCode.AMOUNT_LIMIT_EXCEEDED: "Vượt hạn mức",
    ErrorCode.PARAMS_INVALID: "Thông tin chưa hợp lệ",
    ErrorCode.FORBIDDEN: "Không có quyền thực hiện",
    ErrorCode.UNAUTHENTICATED: "Cần đăng nhập lại",
    ErrorCode.DATABASE_UNAVAILABLE: "Dữ liệu tạm thời chưa dùng được",
    ErrorCode.RATE_LIMITED: "Đang có quá nhiều yêu cầu",
    ErrorCode.FORECAST_UNAVAILABLE: "Chưa có dự báo",
    ErrorCode.PROFILE_INCOMPLETE: "Chưa khai lương",
    ErrorCode.SCENARIO_INVALID: "Kịch bản chưa hợp lệ",
}
DEFAULT_ERROR_TITLE = "Không thực hiện được"

GENERIC_ERROR_MESSAGE = "Mình chưa lấy được dữ liệu lúc này. Bạn thử lại sau ít phút nhé."
FORBIDDEN_MESSAGE = "Bạn không có quyền thực hiện thao tác này."
SESSION_EXPIRED_MESSAGE = "Phiên đăng nhập đã hết hạn. Bạn đăng nhập lại rồi hỏi tiếp nhé."
UNAVAILABLE_MESSAGE = "Dịch vụ dữ liệu đang tạm thời không phản hồi. Bạn thử lại sau ít phút nhé."

EMPTY_INPUT_MESSAGE = "Không thấy câu hỏi nào của người dùng trong yêu cầu."
