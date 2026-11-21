import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ConfigContext } from '@/AppContext'
import { LoginPage } from '@/pages/LoginPage'
import type { Config } from '@/lib/config'
import { fakeAuth, session } from '@/test/helpers'
import { AuthProvider, MIN_TTL_FOR_CALL_MS, REFRESH_LEAD_MS, useAuth } from './AuthProvider'
import { RequireAuth } from './RequireAuth'
import { AuthError, type AuthSession } from './types'

const config: Config = {
  region: 'ap-southeast-1',
  userPoolId: 'p',
  clientId: 'c',
  apiUrl: 'https://api.example.invalid',
  agentUrl: 'https://rt.example.invalid/i',
  replayEnabled: false,
}

function renderRoutes(auth: ReturnType<typeof fakeAuth>, cfg: Config = config, initial = '/') {
  const router = createMemoryRouter(
    [
      { path: '/login', element: <LoginPage /> },
      {
        path: '/',
        element: (
          <RequireAuth>
            <p>Nội dung riêng tư</p>
          </RequireAuth>
        ),
      },
    ],
    { initialEntries: [initial] },
  )
  render(
    <ConfigContext.Provider value={cfg}>
      <AuthProvider client={auth}>
        <RouterProvider router={router} />
      </AuthProvider>
    </ConfigContext.Provider>,
  )
  return router
}

describe('route guard', () => {
  it('chưa đăng nhập: chuyển tới /login và không lộ nội dung', async () => {
    const router = renderRoutes(fakeAuth(null))
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(screen.queryByText('Nội dung riêng tư')).toBeNull()
    expect(screen.getByRole('heading', { name: 'Đăng nhập' })).toBeInTheDocument()
  })

  it('đã có phiên: vào được trang', async () => {
    renderRoutes(fakeAuth(session()))
    expect(await screen.findByText('Nội dung riêng tư')).toBeInTheDocument()
  })

  it('trong lúc khôi phục phiên thì hiện chờ, không nháy sang /login', async () => {
    const auth = fakeAuth(session())
    let release!: (s: AuthSession | null) => void
    auth.restore = vi.fn(() => new Promise<AuthSession | null>((r) => (release = r)))
    const router = renderRoutes(auth)
    expect(screen.getByRole('status', { name: 'Đang tải' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/')
    await act(async () => release(session()))
    expect(await screen.findByText('Nội dung riêng tư')).toBeInTheDocument()
  })

  it('đăng nhập xong quay lại trang đã định vào', async () => {
    const auth = fakeAuth(null)
    const router = renderRoutes(auth)
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'a@example.invalid')
    await user.type(screen.getByLabelText('Mật khẩu'), 'mat-khau-test')
    await user.click(screen.getByRole('button', { name: 'Đăng nhập' }))
    expect(await screen.findByText('Nội dung riêng tư')).toBeInTheDocument()
    expect(auth.signIn).toHaveBeenCalledWith('a@example.invalid', 'mat-khau-test')
  })
})

describe('màn Đăng nhập', () => {
  it('"Dùng tài khoản demo" chỉ điền sẵn email demo từ cấu hình và đưa con trỏ vào ô mật khẩu', async () => {
    renderRoutes(fakeAuth(null), { ...config, demoEmail: 'demo@example.invalid' })
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Dùng tài khoản demo' }))
    expect(screen.getByLabelText('Email')).toHaveValue('demo@example.invalid')
    expect(screen.getByLabelText('Mật khẩu')).toHaveValue('') // không có mật khẩu nào nhúng sẵn
    expect(screen.getByLabelText('Mật khẩu')).toHaveFocus()
  })

  it('không có VITE_DEMO_EMAIL thì không có nút demo', async () => {
    renderRoutes(fakeAuth(null))
    await screen.findByRole('heading', { name: 'Đăng nhập' })
    expect(screen.queryByRole('button', { name: 'Dùng tài khoản demo' })).toBeNull()
  })

  it('sai mật khẩu: hiện lỗi tiếng Việt, ở lại trang, bấm lại được', async () => {
    const auth = fakeAuth(null)
    auth.signIn = vi.fn(async () => {
      throw new AuthError('INVALID_CREDENTIALS')
    })
    const router = renderRoutes(auth)
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'a@example.invalid')
    await user.type(screen.getByLabelText('Mật khẩu'), 'sai-mat-khau')
    await user.click(screen.getByRole('button', { name: 'Đăng nhập' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Email hoặc mật khẩu chưa đúng')
    expect(router.state.location.pathname).toBe('/login')
    expect(screen.getByRole('button', { name: 'Đăng nhập' })).toBeEnabled()
  })

  it('ô mật khẩu ẩn ký tự, có nút hiện/ẩn', async () => {
    renderRoutes(fakeAuth(null))
    const input = await screen.findByLabelText('Mật khẩu')
    expect(input).toHaveAttribute('type', 'password')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Hiện mật khẩu' }))
    expect(input).toHaveAttribute('type', 'text')
  })
})

function Probe({ onReady }: { onReady: (a: ReturnType<typeof useAuth>) => void }) {
  const a = useAuth()
  onReady(a)
  return <p data-testid="status">{a.status}</p>
}

describe('AuthProvider: làm mới token', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('getAccessToken yêu cầu token còn sống ít nhất MIN_TTL; force thì ép làm mới', async () => {
    const auth = fakeAuth(session())
    let api!: ReturnType<typeof useAuth>
    render(
      <AuthProvider client={auth}>
        <Probe onReady={(a) => (api = a)} />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signedIn'))
    auth.getSession.mockClear()
    await act(async () => {
      await api.getAccessToken()
    })
    expect(auth.getSession).toHaveBeenLastCalledWith({ minTtlMs: MIN_TTL_FOR_CALL_MS, force: undefined })
    await act(async () => {
      await api.getAccessToken({ force: true })
    })
    expect(auth.getSession).toHaveBeenLastCalledWith({ minTtlMs: MIN_TTL_FOR_CALL_MS, force: true })
  })

  it('hết phiên khi lấy token: ném SESSION_EXPIRED và đăng xuất kèm thông báo', async () => {
    const auth = fakeAuth(session())
    let api!: ReturnType<typeof useAuth>
    render(
      <AuthProvider client={auth}>
        <Probe onReady={(a) => (api = a)} />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('signedIn'))
    auth.getSession.mockResolvedValue(null)
    await act(async () => {
      await expect(api.getAccessToken()).rejects.toMatchObject({ code: 'SESSION_EXPIRED' })
    })
    expect(screen.getByTestId('status')).toHaveTextContent('signedOut')
    expect(api.notice).toMatch(/hết hạn/)
    expect(auth.signOut).toHaveBeenCalled()
  })

  it('tự hẹn làm mới trước khi hết hạn REFRESH_LEAD_MS, và token mới thay token cũ', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] })
    const first = session({ accessToken: 'tok-1', expiresAt: Date.now() + 60 * 60_000 })
    const auth = fakeAuth(first)
    let api!: ReturnType<typeof useAuth>
    render(
      <AuthProvider client={auth}>
        <Probe onReady={(a) => (api = a)} />
      </AuthProvider>,
    )
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10)
    })
    expect(api.session?.accessToken).toBe('tok-1')
    auth.getSession.mockClear()
    auth.getSession.mockResolvedValue(session({ accessToken: 'tok-2', expiresAt: Date.now() + 120 * 60_000 }))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60 * 60_000 - REFRESH_LEAD_MS - 1000)
    })
    expect(auth.getSession).not.toHaveBeenCalled() // chưa tới lúc
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(auth.getSession).toHaveBeenCalledWith({ force: true })
    expect(api.session?.accessToken).toBe('tok-2')
  })

  it('làm mới theo hẹn thất bại: đăng xuất và báo hết phiên', async () => {
    vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'] })
    const auth = fakeAuth(session({ expiresAt: Date.now() + 10 * 60_000 }))
    let api!: ReturnType<typeof useAuth>
    render(
      <AuthProvider client={auth}>
        <Probe onReady={(a) => (api = a)} />
      </AuthProvider>,
    )
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10)
    })
    auth.getSession.mockResolvedValue(null)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10 * 60_000)
    })
    expect(api.status).toBe('signedOut')
    expect(api.notice).toMatch(/hết hạn/)
  })
})
