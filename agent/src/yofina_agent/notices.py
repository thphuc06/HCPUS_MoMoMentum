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
)
CANNOT_DO: tuple[str, ...] = (
    "Tư vấn mua cổ phiếu, quỹ, tiền mã hóa",
    "Tự ghi hay chuyển tiền khi bạn chưa xác nhận",
)
SUGGESTION_ITEMS: tuple[dict[str, str], ...] = (
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
GUARDRAIL_OUTPUT_BLOCKED: tuple[str, str] = (
    "Chỉ hiện số liệu",
    "Phần lời giải thích không đạt kiểm tra an toàn nên mình chỉ hiện số liệu.",
)
#: Tên hũ người dùng gõ không khớp hũ nào (hoặc khớp nhiều hũ): đúng một câu hỏi, chip là các hũ có thật.
UNKNOWN_JAR_QUESTION = "Mình chưa thấy hũ “{name}” trong ví của bạn. Bạn muốn dùng hũ nào?"
UNKNOWN_JAR_QUESTION_NO_NAME = "Mình chưa xác định được hũ bạn nói. Bạn muốn dùng hũ nào?"

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
PROFILE_PREPARED_HINT = "Đã chuẩn bị thay đổi hồ sơ; chưa lưu gì cho tới khi bạn bấm Xác nhận."

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

ASK_MOVE_DETAILS = (
    "Bạn muốn chuyển bao nhiêu tiền, từ hũ nào sang hũ nào?"  # hỏi lại khi router không trả reply
)
EMPTY_INPUT_MESSAGE = "Không thấy câu hỏi nào của người dùng trong yêu cầu."
