import { z } from 'zod'

// Mã lỗi máy đọc được của REST, khớp contracts/rest/openapi.yaml (components.schemas.ErrorCode) và
// yofina_core.errors.ErrorCode. Test api/openapi.test.ts so khớp với file openapi.yaml.
export const ERROR_CODES = [
  'UNAUTHENTICATED',
  'FORBIDDEN',
  'PARAMS_INVALID',
  'JAR_NOT_FOUND',
  'INSUFFICIENT_FUNDS',
  'AMOUNT_LIMIT_EXCEEDED',
  'NEEDS_CONFIRMATION',
  'TOKEN_INVALID',
  'TOKEN_EXPIRED',
  'TOKEN_REUSED',
  'PARAMS_MISMATCH',
  'ALREADY_APPLIED',
  'RATE_LIMITED',
  'MODEL_BUDGET_EXCEEDED',
  'DATABASE_UNAVAILABLE',
  'INTERNAL_ERROR',
  'PROFILE_INCOMPLETE',
  'TRANSACTION_NOT_FOUND',
  'OBLIGATION_NOT_FOUND',
  'PAYEE_NOT_FOUND',
  'SALARY_EVENT_NOT_FOUND',
  'JAR_PROTECTED',
  'CREDIT_LIMIT_EXCEEDED',
  'DUPLICATE_TRANSACTION',
  'FORECAST_UNAVAILABLE',
] as const

export const ErrorCode = z.enum(ERROR_CODES)
export type ErrorCode = z.infer<typeof ErrorCode>

/** Mã do phía client tự đặt khi chưa có phản hồi hợp lệ từ server. */
export type ClientErrorCode = 'NETWORK' | 'TIMEOUT' | 'INVALID_RESPONSE' | 'SESSION_EXPIRED'
export type ApiErrorCode = ErrorCode | ClientErrorCode

/** Ánh xạ HTTP status của hợp đồng (x-http-status). */
export const HTTP_STATUS: Record<ErrorCode, number> = {
  UNAUTHENTICATED: 401,
  FORBIDDEN: 403,
  PARAMS_INVALID: 400,
  JAR_NOT_FOUND: 404,
  INSUFFICIENT_FUNDS: 422,
  AMOUNT_LIMIT_EXCEEDED: 422,
  NEEDS_CONFIRMATION: 428,
  TOKEN_INVALID: 403,
  TOKEN_EXPIRED: 403,
  TOKEN_REUSED: 409,
  PARAMS_MISMATCH: 409,
  ALREADY_APPLIED: 409,
  RATE_LIMITED: 429,
  MODEL_BUDGET_EXCEEDED: 503,
  DATABASE_UNAVAILABLE: 503,
  INTERNAL_ERROR: 500,
  PROFILE_INCOMPLETE: 422,
  TRANSACTION_NOT_FOUND: 404,
  OBLIGATION_NOT_FOUND: 404,
  PAYEE_NOT_FOUND: 404,
  SALARY_EVENT_NOT_FOUND: 404,
  JAR_PROTECTED: 422,
  CREDIT_LIMIT_EXCEEDED: 422,
  DUPLICATE_TRANSACTION: 409,
  FORECAST_UNAVAILABLE: 503,
}

/** Thông báo tiếng Việt cho từng mã lỗi (thay vì hiện mã thô hay chữ tiếng Anh của server). */
export const ERROR_MESSAGES: Record<ApiErrorCode, string> = {
  UNAUTHENTICATED: 'Phiên đăng nhập đã hết hạn. Bạn đăng nhập lại nhé.',
  FORBIDDEN: 'Bạn không có quyền thực hiện thao tác này.',
  PARAMS_INVALID: 'Thông tin gửi đi chưa hợp lệ.',
  JAR_NOT_FOUND: 'Không tìm thấy hũ này trong tài khoản của bạn.',
  INSUFFICIENT_FUNDS: 'Hũ nguồn không đủ số dư cho khoản này.',
  AMOUNT_LIMIT_EXCEEDED: 'Số tiền vượt hạn mức cho một lần chuyển.',
  NEEDS_CONFIRMATION: 'Thao tác này cần bạn xác nhận trước. Chưa có gì được ghi.',
  TOKEN_INVALID: 'Phiên xác nhận không hợp lệ. Bấm xác nhận lại để lấy phiên mới.',
  TOKEN_EXPIRED: 'Phiên xác nhận đã hết hạn. Bấm xác nhận lại để lấy phiên mới.',
  TOKEN_REUSED: 'Thao tác này đã được thực hiện trước đó. Bạn kiểm tra lại số dư nhé.',
  PARAMS_MISMATCH: 'Nội dung thao tác đã khác với nội dung bạn xác nhận. Chưa có gì được ghi.',
  ALREADY_APPLIED: 'Đề nghị này đã được thực hiện rồi, không ghi thêm gì. Bạn kiểm tra lại số dư nhé.',
  RATE_LIMITED: 'Bạn thao tác hơi nhanh. Đợi vài giây rồi thử lại.',
  MODEL_BUDGET_EXCEEDED: 'Trợ lý đã dùng hết lượt hôm nay. Số liệu vẫn xem được.',
  DATABASE_UNAVAILABLE: 'Hệ thống đang khởi động. Thử lại sau vài giây.',
  INTERNAL_ERROR: 'Có lỗi ở phía hệ thống. Thử lại sau ít phút.',
  PROFILE_INCOMPLETE: 'Bạn cần khai lương và ngày nhận lương trước thì mới làm được việc này.',
  TRANSACTION_NOT_FOUND: 'Không tìm thấy giao dịch này trong tài khoản của bạn.',
  OBLIGATION_NOT_FOUND: 'Không tìm thấy khoản nghĩa vụ này. Có thể nó đã được xóa.',
  PAYEE_NOT_FOUND: 'Không tìm thấy người nhận này trong danh bạ của bạn.',
  SALARY_EVENT_NOT_FOUND: 'Không tìm thấy khoản lương cần xác nhận. Có thể nó đã được xử lý.',
  JAR_PROTECTED: 'Hũ hệ thống, hũ còn tiền hoặc còn nghĩa vụ thì chưa sửa hay bỏ được.',
  CREDIT_LIMIT_EXCEEDED: 'Vượt hạn mức Trả sau còn lại. Chọn số tiền nhỏ hơn hoặc trả từ hũ.',
  DUPLICATE_TRANSACTION: 'Giao dịch này đã được ghi rồi, không ghi thêm. Bạn kiểm tra ở Hoạt động nhé.',
  FORECAST_UNAVAILABLE: 'Chưa có dự báo cho hũ này và chưa tính được ngay. Thử lại sau ít phút.',
  NETWORK: 'Không kết nối được tới máy chủ. Kiểm tra mạng rồi thử lại.',
  TIMEOUT: 'Máy chủ phản hồi quá lâu. Nếu bạn vừa ghi một giao dịch, kiểm tra ở Hoạt động trước khi thử lại.',
  INVALID_RESPONSE: 'Máy chủ trả dữ liệu không đọc được. Thử lại sau ít phút.',
  SESSION_EXPIRED: 'Phiên đăng nhập đã hết hạn. Bạn đăng nhập lại nhé.',
}

export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status: number
  readonly traceId?: string
  /** Gửi lại lệnh này có hợp lý không (lỗi tạm thời). */
  readonly retryable: boolean

  constructor(code: ApiErrorCode, status: number, traceId?: string) {
    super(ERROR_MESSAGES[code])
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.traceId = traceId
    this.retryable = code === 'DATABASE_UNAVAILABLE' || code === 'FORECAST_UNAVAILABLE' || code === 'NETWORK' || code === 'TIMEOUT' || code === 'RATE_LIMITED' || code === 'INTERNAL_ERROR'
  }
}

export const ErrorResponse = z.object({
  error: z.object({
    code: z.string(),
    message: z.string().optional(),
    trace_id: z.string().optional(),
  }),
})

/** Đổi phản hồi lỗi (status + thân) thành ApiError với thông báo tiếng Việt. */
export function apiErrorFromResponse(status: number, body: unknown): ApiError {
  const parsed = ErrorResponse.safeParse(body)
  if (parsed.success) {
    const code = ErrorCode.safeParse(parsed.data.error.code)
    if (code.success) return new ApiError(code.data, status, parsed.data.error.trace_id)
  }
  // Thân rỗng hoặc lạ: JWT authorizer của HTTP API trả 401/403 thân rỗng trước khi tới Lambda.
  if (status === 401) return new ApiError('UNAUTHENTICATED', status)
  if (status === 403) return new ApiError('FORBIDDEN', status)
  if (status === 429) return new ApiError('RATE_LIMITED', status)
  if (status === 503) return new ApiError('DATABASE_UNAVAILABLE', status)
  return new ApiError('INTERNAL_ERROR', status)
}
