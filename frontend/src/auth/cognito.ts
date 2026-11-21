import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
  type CognitoUserSession,
} from 'amazon-cognito-identity-js'
import {
  AuthError,
  type AuthClient,
  type AuthErrorCode,
  type AuthSession,
  type GetSessionOptions,
} from './types'

type CognitoLikeError = { code?: string; name?: string; message?: string }

function mapCognitoError(err: unknown): AuthError {
  const e = (err ?? {}) as CognitoLikeError
  const name = e.code ?? e.name ?? ''
  let code: AuthErrorCode = 'UNKNOWN'
  if (name === 'NotAuthorizedException' || name === 'UserNotFoundException') code = 'INVALID_CREDENTIALS'
  else if (name === 'PasswordResetRequiredException') code = 'PASSWORD_RESET_REQUIRED'
  else if (name === 'TooManyRequestsException' || name === 'LimitExceededException') code = 'TOO_MANY_ATTEMPTS'
  else if (name === 'NetworkError' || /network|failed to fetch/i.test(e.message ?? '')) code = 'NETWORK'
  return new AuthError(code)
}

function toSession(s: CognitoUserSession, fallbackEmail?: string): AuthSession {
  const access = s.getAccessToken()
  const idPayload = s.getIdToken().decodePayload() as { email?: string; name?: string }
  return {
    accessToken: access.getJwtToken(),
    expiresAt: access.getExpiration() * 1000,
    email: idPayload.email ?? fallbackEmail ?? '',
    displayName: idPayload.name,
  }
}

export type CognitoConfig = { userPoolId: string; clientId: string }

/**
 * Đăng nhập email + mật khẩu qua Cognito SRP bằng amazon-cognito-identity-js. Thư viện lưu token
 * theo mặc định của nó (localStorage, khóa CognitoIdentityServiceProvider.*): refresh token nằm ở đó
 * để tải lại trang không phải đăng nhập lại; access token cũng được giữ trong bộ nhớ ở AuthProvider.
 */
export class CognitoAuthClient implements AuthClient {
  private readonly pool: CognitoUserPool
  private inflight: Promise<AuthSession | null> | null = null

  constructor(cfg: CognitoConfig) {
    this.pool = new CognitoUserPool({ UserPoolId: cfg.userPoolId, ClientId: cfg.clientId })
  }

  private readSession(user: CognitoUser): Promise<CognitoUserSession | null> {
    return new Promise((resolve) => {
      // getSession tự dùng refresh token nếu access token đã hết hạn.
      user.getSession((err: unknown, session: CognitoUserSession | null) => {
        resolve(err || !session ? null : session)
      })
    })
  }

  private refresh(user: CognitoUser, session: CognitoUserSession): Promise<CognitoUserSession | null> {
    return new Promise((resolve) => {
      user.refreshSession(session.getRefreshToken(), (err: unknown, fresh: CognitoUserSession | null) => {
        resolve(err || !fresh ? null : fresh)
      })
    })
  }

  async restore(): Promise<AuthSession | null> {
    return this.getSession()
  }

  signIn(email: string, password: string): Promise<AuthSession> {
    const username = email.trim()
    const user = new CognitoUser({ Username: username, Pool: this.pool })
    const details = new AuthenticationDetails({ Username: username, Password: password })
    return new Promise((resolve, reject) => {
      user.authenticateUser(details, {
        onSuccess: (s) => resolve(toSession(s, username)),
        onFailure: (err) => reject(mapCognitoError(err)),
        newPasswordRequired: () => reject(new AuthError('NEW_PASSWORD_REQUIRED')),
        mfaRequired: () => reject(new AuthError('UNKNOWN')),
        totpRequired: () => reject(new AuthError('UNKNOWN')),
        customChallenge: () => reject(new AuthError('UNKNOWN')),
      })
    })
  }

  getSession(options: GetSessionOptions = {}): Promise<AuthSession | null> {
    // Gộp các lần gọi đồng thời để không làm mới nhiều lần song song.
    if (this.inflight) return this.inflight
    const run = async (): Promise<AuthSession | null> => {
      const user = this.pool.getCurrentUser()
      if (!user) return null
      let session = await this.readSession(user)
      if (!session) return null
      const ttl = session.getAccessToken().getExpiration() * 1000 - Date.now()
      if (options.force || (options.minTtlMs !== undefined && ttl < options.minTtlMs)) {
        const fresh = await this.refresh(user, session)
        // Làm mới thất bại mà token cũ còn hạn thì dùng tiếp token cũ (trừ khi ép làm mới).
        if (fresh) session = fresh
        else if (options.force || ttl <= 0) return null
      }
      return toSession(session)
    }
    this.inflight = run().finally(() => {
      this.inflight = null
    })
    return this.inflight
  }

  signOut(): void {
    this.pool.getCurrentUser()?.signOut()
  }
}
