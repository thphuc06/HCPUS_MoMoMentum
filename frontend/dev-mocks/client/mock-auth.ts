// CHỈ cho `npm run dev:mock`: đăng nhập giả để xem giao diện khi chưa có backend. Không được import từ src/
// ngoài nhánh `import.meta.env.MODE === 'mock'` ở main.tsx (bản build production loại nhánh đó).
import { AuthError, type AuthClient, type AuthSession } from '@/auth/types'

const KEY = 'yofina.mock.session'
const TTL_MS = 60 * 60_000

function make(email: string): AuthSession {
  return { accessToken: 'mock-access-token', expiresAt: Date.now() + TTL_MS, email, displayName: undefined }
}

export class MockAuthClient implements AuthClient {
  async restore(): Promise<AuthSession | null> {
    const email = sessionStorage.getItem(KEY)
    return email ? make(email) : null
  }

  async signIn(email: string, password: string): Promise<AuthSession> {
    // Mật khẩu "sai" để thử màn lỗi; mọi giá trị khác được chấp nhận.
    if (password === 'sai') throw new AuthError('INVALID_CREDENTIALS')
    sessionStorage.setItem(KEY, email.trim())
    return make(email.trim())
  }

  async getSession(): Promise<AuthSession | null> {
    const email = sessionStorage.getItem(KEY)
    return email ? make(email) : null
  }

  signOut(): void {
    sessionStorage.removeItem(KEY)
  }
}
