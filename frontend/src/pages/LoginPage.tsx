import { useRef, useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router'
import { Eye, EyeOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/auth/AuthProvider'
import { AUTH_MESSAGES, AuthError } from '@/auth/types'
import { useConfig } from '@/AppContext'

function Logo() {
  return (
    <span className="grid size-14 place-items-center rounded-2xl bg-white/20" aria-hidden>
      <svg viewBox="0 0 24 24" className="size-8" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="8" y="2.5" width="8" height="3.5" rx="1" />
        <path d="M7 8.5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2V18a3.5 3.5 0 0 1-3.5 3.5h-3A3.5 3.5 0 0 1 7 18z" />
        <path d="M7 13h10" />
      </svg>
    </span>
  )
}

// Figma S0 Đăng nhập (31:2715). "Dùng tài khoản demo" chỉ điền sẵn email demo (VITE_DEMO_EMAIL, tùy chọn)
// rồi đưa con trỏ vào ô mật khẩu; không có mật khẩu nào nằm trong mã hay bundle.
export function LoginPage() {
  const { status, signIn, notice } = useAuth()
  const { demoEmail } = useConfig()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const passwordRef = useRef<HTMLInputElement>(null)

  if (status === 'signedIn') {
    const from = (location.state as { from?: string } | null)?.from
    return <Navigate to={from && from !== '/login' ? from : '/'} replace />
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy || !email.trim() || !password) return
    setBusy(true)
    setError(null)
    try {
      await signIn(email, password)
    } catch (err) {
      setError(err instanceof AuthError ? err.message : AUTH_MESSAGES.UNKNOWN)
      setBusy(false)
    }
  }

  const useDemo = () => {
    if (!demoEmail) return
    setEmail(demoEmail)
    setError(null)
    passwordRef.current?.focus()
  }

  const message = error ?? notice

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-background">
      <header
        className="rounded-b-[40px] px-7 pt-[max(56px,env(safe-area-inset-top))] pb-10 text-white"
        style={{ background: 'var(--gradient-hero)' }}
      >
        <Logo />
        <h1 className="mt-5 text-[40px] leading-[44px] font-extrabold">Yofina</h1>
        <p className="mt-2 text-subtitle">Hũ nhìn trước: biết trước lúc nào thiếu tiền</p>
      </header>

      <form onSubmit={submit} className="flex flex-1 flex-col px-6 pt-6 pb-6" noValidate>
        <h2 className="text-title font-bold text-ink">Đăng nhập</h2>

        <label htmlFor="email" className="mt-4 mb-1.5 text-small font-semibold text-ink-2">
          Email
        </label>
        <Input
          id="email"
          type="email"
          inputMode="email"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-invalid={!!error}
        />

        <label htmlFor="password" className="mt-4 mb-1.5 text-small font-semibold text-ink-2">
          Mật khẩu
        </label>
        <div className="relative">
          <Input
            id="password"
            ref={passwordRef}
            type={showPassword ? 'text' : 'password'}
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={!!error}
            className="pr-14"
          />
          <button
            type="button"
            onClick={() => setShowPassword((s) => !s)}
            aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
            className="absolute top-1 right-1 grid size-11 place-items-center rounded-full text-ink-2"
          >
            {showPassword ? <EyeOff className="size-5" aria-hidden /> : <Eye className="size-5" aria-hidden />}
          </button>
        </div>

        {message && (
          <p role="alert" className="mt-3 rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
            {message}
          </p>
        )}

        <Button
          type="submit"
          variant={demoEmail ? 'outline' : 'default'}
          className="mt-5 w-full"
          disabled={busy || !email.trim() || !password}
          aria-busy={busy}
        >
          {busy ? 'Đang đăng nhập…' : 'Đăng nhập'}
        </Button>

        {demoEmail && (
          <>
            <div className="my-4 flex items-center gap-3 text-small text-ink-2" aria-hidden>
              <span className="h-px flex-1 bg-line" />
              hoặc
              <span className="h-px flex-1 bg-line" />
            </div>
            <Button type="button" className="w-full" onClick={useDemo}>
              Dùng tài khoản demo
            </Button>
          </>
        )}

        <p className="mt-auto pt-8 text-center text-note text-ink-2">Ví mô phỏng · dữ liệu minh họa · không phải tài khoản thật</p>
      </form>
    </div>
  )
}
