import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '@/auth/AuthProvider'
import { ConfigContext } from '@/AppContext'
import type { Config } from '@/lib/config'
import { appRoutes } from './router'
import { fakeAuth, jarsFromFixture } from '@/test/helpers'
import { validBlock } from '@/test/fixtures'
import { blockSnapshot, runFinished, runStarted, sseResponse, textMessage, toolCall } from '@/test/sse'

// Kiểm tích hợp ở mức ứng dụng: khung, Tổng quan, sheet chat, khối confirm -> receipt, với fetch giả (REST + Runtime).
// Đây là test; mock chỉ sống ở đây và ở dev-mocks/, không import từ src/.

const config: Config = {
  region: 'ap-southeast-1',
  userPoolId: 'p',
  clientId: 'c',
  apiUrl: 'https://api.example.invalid',
  agentUrl: 'https://rt.example.invalid/invocations?qualifier=DEFAULT',
  replayEnabled: false,
}

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>

function json(status: number, body?: unknown) {
  return new Response(body === undefined ? '' : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

function mountApp(handler: Handler, initial = '/') {
  const calls: Array<{ url: string; init: RequestInit }> = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(url), init: init ?? {} })
      return handler(String(url), init ?? {})
    }),
  )
  const router = createMemoryRouter(appRoutes(), { initialEntries: [initial] })
  const auth = fakeAuth()
  render(
    <ConfigContext.Provider value={config}>
      <AuthProvider client={auth}>
        <RouterProvider router={router} />
      </AuthProvider>
    </ConfigContext.Provider>,
  )
  return { calls, router, auth }
}

const bodyOf = (c: { init: RequestInit }) => JSON.parse(String(c.init.body))
const isWarmup = (c: { url: string; init: RequestInit }) => c.url === config.agentUrl && bodyOf(c).forwardedProps?.warmup === true
const runCalls = (calls: Array<{ url: string; init: RequestInit }>) => calls.filter((c) => c.url === config.agentUrl && !isWarmup(c))

describe('Tổng quan', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('skeleton khi tải, rồi tổng và 7 thẻ hũ đúng số của API; có nhãn Ví mô phỏng', async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    mountApp(async (url) => {
      if (url.endsWith('/jars')) {
        await gate
        return json(200, jarsFromFixture())
      }
      return json(404)
    })
    expect(await screen.findByTestId('overview-skeleton')).toBeInTheDocument()
    release()
    expect(await screen.findByTestId('balance-total')).toHaveTextContent('7.730.000 ₫')
    expect(screen.queryByTestId('overview-skeleton')).toBeNull()
    const list = screen.getByRole('list', { name: 'Danh sách hũ' })
    expect(within(list).getAllByRole('article')).toHaveLength(7)
    expect(screen.getByText(/Ví mô phỏng · ngày mô phỏng 21\/11\/2026/)).toBeInTheDocument()
    expect(within(list).getByText('Ăn uống')).toBeInTheDocument()
    expect(within(list).getByText('380.000 ₫')).toBeInTheDocument()
  })

  it('lỗi tải: thông báo tiếng Việt và nút Thử lại gọi lại API', async () => {
    let n = 0
    const { calls } = mountApp((url) => {
      if (url.endsWith('/jars')) {
        n += 1
        return n === 1 ? json(503, { error: { code: 'DATABASE_UNAVAILABLE', message: 'x' } }) : json(200, jarsFromFixture())
      }
      return json(404)
    })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Chưa tải được số dư')
    expect(alert).toHaveTextContent('Hệ thống đang khởi động')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByTestId('balance-total')).toHaveTextContent('7.730.000 ₫')
    expect(calls.filter((c) => c.url.endsWith('/jars'))).toHaveLength(2)
    expect(new Headers(calls[0]!.init.headers as HeadersInit).get('authorization')).toBe('Bearer access-1')
  })

  it('tab chưa làm hiện trạng thái rỗng, không số giả', async () => {
    mountApp(() => json(200, jarsFromFixture()), '/foresight')
    expect(await screen.findByTestId('empty-tab')).toHaveTextContent('Chưa có số liệu dự báo nào')
    expect(screen.getByRole('heading', { name: 'Nhìn trước' })).toBeInTheDocument()
  })

  it('tab bar có 5 mục, nút giữa Hỏi Yofina', async () => {
    mountApp(() => json(200, jarsFromFixture()))
    const nav = await screen.findByRole('navigation', { name: 'Điều hướng chính' })
    for (const name of ['Tổng quan', 'Hũ', 'Hỏi Yofina', 'Nhìn trước', 'Hồ sơ']) {
      expect(within(nav).getByText(name)).toBeInTheDocument()
    }
  })
})

describe('Hồ sơ', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('Đặt lại dữ liệu: hộp xác nhận -> POST /demo/reset -> tải lại số dư; Hủy thì không gọi', async () => {
    const { calls } = mountApp((url, init) => {
      if (url.endsWith('/jars')) return json(200, jarsFromFixture())
      if (url.endsWith('/demo/reset') && init.method === 'POST')
        return json(200, { reset_at: '2026-12-10T03:00:00Z', app_date: '2026-11-21', clock_offset_days: -19, jars_count: 7, transactions_count: 41 })
      return json(404)
    }, '/profile')
    const user = userEvent.setup()
    expect(await screen.findByTestId('profile-email')).toHaveTextContent('nguoi.dung@example.invalid')

    await user.click(screen.getByRole('button', { name: 'Đặt lại dữ liệu' }))
    await user.click(await screen.findByRole('button', { name: 'Hủy' }))
    expect(calls.some((c) => c.url.endsWith('/demo/reset'))).toBe(false)

    await user.click(screen.getByRole('button', { name: 'Đặt lại dữ liệu' }))
    await user.click(await screen.findByRole('button', { name: 'Đặt lại' }))
    expect(await screen.findByText(/Đã đặt lại: 7 hũ, 41 giao dịch\. Ngày mô phỏng 21\/11\/2026/)).toBeInTheDocument()
    expect(calls.filter((c) => c.url.endsWith('/demo/reset'))).toHaveLength(1)
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith('/jars')).length).toBeGreaterThanOrEqual(2))
  })

  it('Đăng xuất đưa về màn Đăng nhập', async () => {
    const { router } = mountApp(() => json(200, jarsFromFixture()), '/profile')
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Đăng xuất' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
  })
})

describe('Chat trong ứng dụng', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('mở sheet, hỏi số dư, thấy khối jar_summary; rồi chuyển tiền: confirm -> bấm -> receipt, số dư tải lại, lượt sau gửi kèm dòng hệ thống', async () => {
    const jarsBlock = validBlock('jar_summary.seven_jars') as { id: string }
    const confirm = validBlock('confirm.move') as { id: string; data: { expires_at: string; params_hash: string; params: unknown } }
    confirm.data.expires_at = new Date(Date.now() + 5 * 60_000).toISOString().replace(/\.\d+Z$/, 'Z')
    const receipt = validBlock('receipt.move')

    let runs = 0
    const { calls } = mountApp((url, init) => {
      if (url === config.agentUrl && JSON.parse(String(init.body)).forwardedProps?.warmup) return sseResponse([runStarted(), runFinished()])
      if (url === config.agentUrl) {
        runs += 1
        const sse =
          runs === 1
            ? [runStarted(), ...toolCall('t1', 'ledger___get_jar_balances'), blockSnapshot(jarsBlock.id, jarsBlock), ...textMessage('m1', 'Đây là số dư các hũ.'), runFinished()]
            : runs === 2
              ? [runStarted(), ...toolCall('t1', 'ledger___move_between_jars'), blockSnapshot(confirm.id, confirm), ...textMessage('m1', 'Bạn xem lại nhé.'), runFinished()]
              : [runStarted(), ...textMessage('m1', 'Đã ghi nhận.'), runFinished()]
        return sseResponse(sse)
      }
      if (url.endsWith('/jars')) return json(200, jarsFromFixture())
      if (url.endsWith('/confirmations'))
        return json(200, { confirm_token: 'aaa.bbb', expires_at: '2026-12-10T03:02:00Z', ttl_seconds: 120, tool: 'move_between_jars', params: confirm.data.params, params_hash: confirm.data.params_hash })
      if (url.endsWith('/actions')) return json(200, receipt)
      void init
      return json(404)
    })
    const user = userEvent.setup()
    await screen.findByTestId('balance-total')

    await user.click(screen.getByRole('button', { name: /Hỏi Yofina/ }))
    const sheet = await screen.findByTestId('chat-sheet')
    expect(within(sheet).getByRole('heading', { name: 'Hỏi Yofina' })).toBeInTheDocument()
    expect(within(sheet).getByText('Do AI tạo')).toBeInTheDocument()

    // mở sheet thì làm nóng phiên Runtime: POST /invocations với forwardedProps.warmup, không có tin nhắn nào
    await waitFor(() => expect(calls.some(isWarmup)).toBe(true))
    const warm = calls.find(isWarmup)!
    expect(bodyOf(warm).messages).toEqual([])
    expect(new Headers(warm.init.headers as HeadersInit).get('authorization')).toBe('Bearer access-1')

    const input = within(sheet).getByLabelText('Tin nhắn')
    await user.type(input, 'số dư các hũ của mình')
    await user.click(within(sheet).getByRole('button', { name: 'Gửi' }))
    await waitFor(() => expect(within(sheet).getAllByTestId('block-item')).toHaveLength(1))
    expect(within(sheet).getByText('Số dư các hũ')).toBeInTheDocument()
    expect(within(sheet).getByText('Đây là số dư các hũ.')).toBeInTheDocument()
    await waitFor(() => expect(within(sheet).getByRole('button', { name: 'Gửi' })).toBeDisabled()) // ô trống, lượt đã xong

    const run1 = runCalls(calls)[0]!
    const h1 = new Headers(run1.init.headers as HeadersInit)
    expect(h1.get('authorization')).toBe('Bearer access-1')
    expect(h1.get('x-amzn-bedrock-agentcore-runtime-session-id')).toMatch(/^[0-9a-f-]{36}$/)

    await user.type(within(sheet).getByLabelText('Tin nhắn'), 'chuyển 100 nghìn từ Giải trí sang Ăn uống')
    await user.click(within(sheet).getByRole('button', { name: 'Gửi' }))
    const btn = await within(sheet).findByRole('button', { name: /Xác nhận chuyển 100\.000\s₫/ })
    await user.click(btn)

    await waitFor(() => expect(within(sheet).getByText('Đã chuyển 100.000 ₫')).toBeInTheDocument())
    expect(within(sheet).queryByRole('button', { name: /Xác nhận chuyển/ })).toBeNull() // confirm đã được thay bằng receipt
    expect(calls.filter((c) => c.url.endsWith('/confirmations'))).toHaveLength(1)
    expect(calls.filter((c) => c.url.endsWith('/actions'))).toHaveLength(1)
    expect(JSON.parse(String(calls.find((c) => c.url.endsWith('/actions'))!.init.body)).confirm_token).toBe('aaa.bbb')
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith('/jars')).length).toBeGreaterThanOrEqual(2)) // Tổng quan được làm mới

    // lượt sau: lịch sử gửi lại đủ, gồm một dòng hệ thống về việc đã làm; người dùng không thấy dòng đó
    await user.type(within(sheet).getByLabelText('Tin nhắn'), 'xong chưa')
    await user.click(within(sheet).getByRole('button', { name: 'Gửi' }))
    await waitFor(() => expect(runs).toBe(3))
    const run3 = bodyOf(runCalls(calls)[2]!)
    const roles = run3.messages.map((m: { role: string }) => m.role)
    expect(roles).toEqual(['user', 'assistant', 'user', 'assistant', 'system', 'user'])
    expect(run3.messages[4].content).toContain('đã xác nhận')
    expect(within(sheet).queryByText(/Hệ thống ghi nhận/)).toBeNull()
  })

  it('luồng rỗng từ Runtime hiện thông báo lỗi có nút Thử lại; bấm thử lại gửi lại và nhận câu trả lời', async () => {
    let runs = 0
    mountApp((url, init) => {
      if (url === config.agentUrl && JSON.parse(String(init.body)).forwardedProps?.warmup) return sseResponse([runStarted(), runFinished()])
      if (url === config.agentUrl) {
        runs += 1
        return runs === 1 ? sseResponse([]) : sseResponse([runStarted(), ...textMessage('m1', 'Đây rồi.'), runFinished()])
      }
      return json(200, jarsFromFixture())
    })
    const user = userEvent.setup()
    await screen.findByTestId('balance-total')
    await user.click(screen.getByRole('button', { name: /Hỏi Yofina/ }))
    const sheet = await screen.findByTestId('chat-sheet')
    await user.type(within(sheet).getByLabelText('Tin nhắn'), 'xin chào')
    await user.click(within(sheet).getByRole('button', { name: 'Gửi' }))
    const alert = await within(sheet).findByRole('alert')
    expect(alert).toHaveTextContent('Yofina chưa trả lời')
    await user.click(within(alert).getByRole('button', { name: 'Thử lại' }))
    expect(await within(sheet).findByText('Đây rồi.')).toBeInTheDocument()
    expect(within(sheet).queryByRole('alert')).toBeNull()
  })
})
