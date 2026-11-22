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
    "Yofina hiện giúp bạn xem số dư các hũ, tra giao dịch, xem dự báo một hũ và chuyển tiền giữa các hũ. "
    "Việc này nằm ngoài phạm vi đó.",
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
