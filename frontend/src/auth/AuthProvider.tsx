import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { AUTH_MESSAGES, AuthError, type AuthClient, type AuthSession } from './types'

/** Làm mới access token khi còn ít hơn khoảng này (access token sống 60 phút). */
export const REFRESH_LEAD_MS = 5 * 60_000
/** Trước mỗi lượt chat và mỗi lời gọi REST: bảo đảm token còn sống ít nhất chừng này. */
export const MIN_TTL_FOR_CALL_MS = 2 * 60_000

type Status = 'loading' | 'signedOut' | 'signedIn'

export type AuthContextValue = {
  status: Status
  session: AuthSession | null
  /** Thông báo khi bị đăng xuất ngoài ý muốn (hết phiên). */
  notice: string | null
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => void
  /** Access token còn hạn (làm mới nếu cần). Ném AuthError SESSION_EXPIRED nếu hết phiên. */
  getAccessToken: (opts?: { force?: boolean }) => Promise<string>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ client, children }: { client: AuthClient; children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [session, setSession] = useState<AuthSession | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const sessionRef = useRef<AuthSession | null>(null)

  const apply = useCallback((s: AuthSession | null) => {
    sessionRef.current = s
    setSession(s)
    setStatus(s ? 'signedIn' : 'signedOut')
  }, [])

  const expire = useCallback(() => {
    client.signOut()
    apply(null)
    setNotice(AUTH_MESSAGES.SESSION_EXPIRED)
  }, [client, apply])

  useEffect(() => {
    let cancelled = false
    client
      .restore()
      .then((s) => {
        if (!cancelled) apply(s)
      })
      .catch(() => {
        if (!cancelled) apply(null)
      })
    return () => {
      cancelled = true
    }
  }, [client, apply])

  // Hẹn làm mới trước khi access token hết hạn.
  useEffect(() => {
    if (!session) return
    const delay = Math.max(5_000, session.expiresAt - Date.now() - REFRESH_LEAD_MS)
    const timer = setTimeout(() => {
      client
        .getSession({ force: true })
        .then((s) => (s ? apply(s) : expire()))
        .catch(() => expire())
    }, delay)
    return () => clearTimeout(timer)
  }, [client, session, apply, expire])

  const signIn = useCallback(
    async (email: string, password: string) => {
      setNotice(null)
      apply(await client.signIn(email, password))
    },
    [client, apply],
  )

  const signOut = useCallback(() => {
    client.signOut()
    setNotice(null)
    apply(null)
  }, [client, apply])

  const getAccessToken = useCallback(
    async (opts?: { force?: boolean }) => {
      const s = await client.getSession({ minTtlMs: MIN_TTL_FOR_CALL_MS, force: opts?.force })
      if (!s) {
        expire()
        throw new AuthError('SESSION_EXPIRED')
      }
      if (s.accessToken !== sessionRef.current?.accessToken) apply(s)
      return s.accessToken
    },
    [client, apply, expire],
  )

  const value = useMemo<AuthContextValue>(
    () => ({ status, session, notice, signIn, signOut, getAccessToken }),
    [status, session, notice, signIn, signOut, getAccessToken],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth phải nằm trong <AuthProvider>')
  return ctx
}
