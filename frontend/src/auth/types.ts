// Giao diện máy khách xác thực. Bản thật dùng Cognito (cognito.ts); test và `npm run dev:mock` thay bằng bản giả.

export type AuthSession = {
  /** Access token Cognito (không phải ID token): gửi làm Bearer cho REST và Runtime. */
  accessToken: string
  /** Epoch mili giây lúc access token hết hạn. */
  expiresAt: number
  email: string
  displayName?: string
  /**
   * Nhóm Cognito của người dùng (claim `cognito:groups` của access token). Chỉ để giao diện ẩn hay hiện lối vào (ví dụ màn trace
   * của nhóm `ops`); server tự kiểm nhóm ở mọi lời gọi `/ops/*` (403 nếu không thuộc nhóm).
   */
  groups?: string[]
}

/** Nhóm Cognito được xem bảng vận hành và màn trace (`x-required-group: ops` của hợp đồng REST). */
export const OPS_GROUP = 'ops'

export type AuthErrorCode =
  | 'INVALID_CREDENTIALS'
  | 'NEW_PASSWORD_REQUIRED'
  | 'PASSWORD_RESET_REQUIRED'
  | 'TOO_MANY_ATTEMPTS'
  | 'SESSION_EXPIRED'
  | 'NETWORK'
  | 'UNKNOWN'

export const AUTH_MESSAGES: Record<AuthErrorCode, string> = {
  INVALID_CREDENTIALS: 'Email hoặc mật khẩu chưa đúng. Bạn thử lại nhé.',
  NEW_PASSWORD_REQUIRED: 'Tài khoản này cần đặt mật khẩu mới. Bản demo chưa hỗ trợ bước này.',
  PASSWORD_RESET_REQUIRED: 'Tài khoản cần đặt lại mật khẩu. Bản demo chưa hỗ trợ bước này.',
  TOO_MANY_ATTEMPTS: 'Bạn thử quá nhiều lần. Đợi một lát rồi đăng nhập lại.',
  SESSION_EXPIRED: 'Phiên đăng nhập đã hết hạn. Bạn đăng nhập lại nhé.',
  NETWORK: 'Không kết nối được tới máy chủ đăng nhập. Kiểm tra mạng rồi thử lại.',
  UNKNOWN: 'Đăng nhập chưa được. Bạn thử lại sau ít phút.',
}

export class AuthError extends Error {
  readonly code: AuthErrorCode
  constructor(code: AuthErrorCode, message?: string) {
    super(message ?? AUTH_MESSAGES[code])
    this.name = 'AuthError'
    this.code = code
  }
}

export type GetSessionOptions = {
  /** Làm mới nếu access token còn sống ít hơn số mili giây này. */
  minTtlMs?: number
  /** Ép làm mới bằng refresh token dù token còn hạn. */
  force?: boolean
}

export interface AuthClient {
  /** Khôi phục phiên đã lưu (refresh token theo cách thư viện lưu); null nếu chưa đăng nhập. */
  restore(): Promise<AuthSession | null>
  signIn(email: string, password: string): Promise<AuthSession>
  getSession(options?: GetSessionOptions): Promise<AuthSession | null>
  signOut(): void
}
