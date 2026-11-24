// Thông báo lỗi của luồng chat (tiếng Việt). Mã RUN_ERROR và HTTP status theo
// docs/research/spike-agentcore-runtime-cors.md §2, §5.

export type ChatNoticeSpec = { title: string; message: string; code?: string; retry: boolean }

export const CHAT_MESSAGES = {
  genericTitle: 'Yofina gặp lỗi',
  genericMessage: 'Có lỗi khi xử lý tin nhắn. Bạn thử lại nhé.',
  interruptedTitle: 'Kết nối bị gián đoạn',
  interruptedMessage: 'Câu trả lời chưa đến đủ. Bấm thử lại để hỏi lại.',
  emptyTitle: 'Yofina chưa trả lời',
  emptyMessage: 'Máy chủ không gửi gì về. Bấm thử lại để hỏi lại.',
  noAnswerTitle: 'Chưa có câu trả lời',
  noAnswerMessage: 'Lượt này kết thúc mà không có nội dung. Bấm thử lại để hỏi lại.',
} as const

/** Lỗi HTTP khi gọi Runtime: 401 (hết phiên), 403 (không có quyền/phiên của người khác), 409 SESSION_BUSY. */
export function chatErrorForHttp(status: number): ChatNoticeSpec {
  if (status === 401) {
    return {
      title: 'Phiên đăng nhập đã hết hạn',
      message: 'Bạn đăng nhập lại để tiếp tục trò chuyện.',
      code: 'UNAUTHORIZED',
      retry: false,
    }
  }
  if (status === 403) {
    return {
      title: 'Không dùng được cuộc trò chuyện này',
      message: 'Phiên chat này không thuộc tài khoản của bạn. Hãy bắt đầu một cuộc trò chuyện mới.',
      code: 'ACCESS_DENIED',
      retry: false,
    }
  }
  if (status === 409) {
    return {
      title: 'Yofina đang bận',
      message: 'Yofina còn đang xử lý tin nhắn trước. Đợi một chút rồi thử lại.',
      code: 'SESSION_BUSY',
      retry: true,
    }
  }
  return { title: CHAT_MESSAGES.genericTitle, message: CHAT_MESSAGES.genericMessage, code: `HTTP_${status}`, retry: true }
}

/** Lỗi do agent phát qua event RUN_ERROR. `message` của server có thể là tiếng Anh nên không hiện thô. */
export function chatErrorForCode(code: string | undefined, _message?: string): ChatNoticeSpec {
  switch (code) {
    case 'SESSION_BUSY':
      return chatErrorForHttp(409)
    case 'UNAUTHORIZED':
    case 'UNAUTHENTICATED':
      return chatErrorForHttp(401)
    case 'ACCESS_DENIED':
    case 'FORBIDDEN':
      return chatErrorForHttp(403)
    case 'MODEL_BUDGET_EXCEEDED':
      return {
        title: 'Chế độ rút gọn',
        message: 'Trợ lý đã dùng hết lượt hôm nay nên chưa trả lời bằng lời được. Số liệu vẫn xem được ở Tổng quan.',
        code,
        retry: false,
      }
    default:
      return { title: CHAT_MESSAGES.genericTitle, message: CHAT_MESSAGES.genericMessage, code, retry: true }
  }
}

/** Nhãn tiến độ cho từng công cụ; tên công cụ của Gateway có dạng `ledger___get_jar_balances`. Mọi tool trong `contracts/tools/*.json`
 * phải có nhãn ở đây (test `toolLabels.test.ts` và `tests/unit/agent/test_tool_labels.py`), để thẻ "Yofina đã làm" không hiện "Đã xử lý". */
const TOOL_LABELS: Record<string, { running: string; done: string }> = {
  // ledger
  get_jar_balances: { running: 'Đang đọc số dư các hũ…', done: 'Đã đọc số dư các hũ' },
  query_transactions: { running: 'Đang đọc lịch sử giao dịch…', done: 'Đã đọc lịch sử giao dịch' },
  get_cashflow_summary: { running: 'Đang tổng hợp thu chi…', done: 'Đã tổng hợp thu chi' },
  get_obligations: { running: 'Đang đọc các khoản nghĩa vụ…', done: 'Đã đọc các khoản nghĩa vụ' },
  get_unclassified: { running: 'Đang đọc các khoản chưa phân loại…', done: 'Đã đọc các khoản chưa phân loại' },
  update_profile: { running: 'Đang chuẩn bị thay đổi hồ sơ…', done: 'Đã chuẩn bị thay đổi hồ sơ' },
  record_transaction: { running: 'Đang chuẩn bị ghi giao dịch…', done: 'Đã chuẩn bị ghi giao dịch' },
  move_between_jars: { running: 'Đang chuẩn bị chuyển tiền giữa hai hũ…', done: 'Đã chuẩn bị chuyển tiền giữa hai hũ' },
  assign_jar: { running: 'Đang chuẩn bị gán hũ cho giao dịch…', done: 'Đã chuẩn bị gán hũ cho giao dịch' },
  save_turn: { running: 'Đang lưu cuộc trò chuyện…', done: 'Đã lưu cuộc trò chuyện' },
  // forecast
  get_forecast: { running: 'Đang đọc dự báo 30 ngày của hũ…', done: 'Đã đọc dự báo 30 ngày của hũ' },
  run_scenario: { running: 'Đang chạy kịch bản "nếu"…', done: 'Đã chạy kịch bản "nếu"' },
  list_scenarios: { running: 'Đang xem các khoản bạn đang cân nhắc…', done: 'Đã xem các khoản bạn đang cân nhắc' },
  affordability_check: { running: 'Đang kiểm tra trước khi trả…', done: 'Đã kiểm tra trước khi trả' },
  get_resilience_score: { running: 'Đang tính điểm chống chịu…', done: 'Đã tính điểm chống chịu' },
  stress_test: { running: 'Đang thử cú sốc tài chính…', done: 'Đã thử cú sốc tài chính' },
  get_behavior_profile: { running: 'Đang đọc thói quen chi tiêu…', done: 'Đã đọc thói quen chi tiêu' },
  // planner
  check_suitability: { running: 'Đang kiểm tra các luật tài chính…', done: 'Đã kiểm tra các luật tài chính' },
  schedule_nudge: { running: 'Đang chuẩn bị lời nhắc…', done: 'Đã chuẩn bị lời nhắc' },
  optimize_allocation: { running: 'Đang tính cách phân bổ tiền vào các hũ…', done: 'Đã tính cách phân bổ tiền vào các hũ' },
  get_roadmap: { running: 'Đang đọc lộ trình…', done: 'Đã đọc lộ trình' },
  save_roadmap: { running: 'Đang lưu bản lộ trình…', done: 'Đã lưu bản lộ trình' },
  // knowledge
  get_fee_schedule: { running: 'Đang tra biểu phí…', done: 'Đã tra biểu phí' },
  get_exchange_rate: { running: 'Đang tra tỷ giá…', done: 'Đã tra tỷ giá' },
  // ingest
  start_job: { running: 'Đang tạo lượt nạp dữ liệu…', done: 'Đã tạo lượt nạp dữ liệu' },
  get_job_status: { running: 'Đang xem tiến độ nạp dữ liệu…', done: 'Đã xem tiến độ nạp dữ liệu' },
  confirm_rows: { running: 'Đang chuẩn bị chốt các dòng đã nạp…', done: 'Đã chuẩn bị chốt các dòng đã nạp' },
  // audit
  get_trace: { running: 'Đang đọc bản ghi của lượt trả lời…', done: 'Đã đọc bản ghi của lượt trả lời' },
  record_turn: { running: 'Đang ghi lại lượt trả lời…', done: 'Đã ghi lại lượt trả lời' },
}

/** Có nhãn riêng cho công cụ này không (test dùng để bắt tool mới chưa có nhãn). */
export function hasToolLabel(name: string): boolean {
  const short = name.includes('___') ? name.slice(name.lastIndexOf('___') + 3) : name
  return short in TOOL_LABELS
}

export function toolLabel(name: string, status: 'running' | 'done'): string {
  const short = name.includes('___') ? name.slice(name.lastIndexOf('___') + 3) : name
  const l = TOOL_LABELS[short]
  if (l) return l[status]
  return status === 'running' ? 'Đang xử lý…' : 'Đã xử lý'
}
