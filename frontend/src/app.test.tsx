import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { WALLET_CONTEXT } from '@/chat/walletContext'
import type { Config } from '@/lib/config'
import { bodyOf, config, isWarmup, json, mountApp, restDefault, runCalls } from '@/test/mountApp'
import { restFixture, validBlock } from '@/test/fixtures'
import { blockSnapshot, runFinished, runStarted, sseResponse, textMessage, toolCall } from '@/test/sse'

// Kiểm tích hợp ở mức ứng dụng: khung, Tổng quan, sheet chat, khối confirm -> receipt, với fetch giả (REST + Runtime).
// Đây là test; mock chỉ sống ở đây (test/mountApp) và ở dev-mocks/, không import từ src/ sản phẩm.

describe('Tổng quan', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('skeleton khi tải, rồi tổng và 7 thẻ hũ đúng số của API; có nhãn Ví mô phỏng', async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    mountApp(async (url) => {
      if (url.endsWith('/overview')) {
        await gate
        return restDefault(url)
      }
      return json(404)
    })
    expect(await screen.findByTestId('overview-skeleton')).toBeInTheDocument()
    release()
    expect(await screen.findByTestId('balance-total')).toHaveTextContent('7.900.000 ₫')
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
      if (url.endsWith('/overview')) {
        n += 1
        return n === 1 ? json(503, { error: { code: 'DATABASE_UNAVAILABLE', message: 'x' } }) : json(200, restFixture('OverviewResponse.minh'))
      }
      return json(404)
    })
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Chưa tải được tổng quan')
    expect(alert).toHaveTextContent('Hệ thống đang khởi động')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByTestId('balance-total')).toHaveTextContent('7.900.000 ₫')
    expect(calls.filter((c) => c.url.endsWith('/overview'))).toHaveLength(2)
    expect(new Headers(calls[0]!.init.headers as HeadersInit).get('authorization')).toBe('Bearer access-1')
  })

  it('tab Nhìn trước: hũ cần chú ý nhất lên đầu, số lấy từ API', async () => {
    mountApp((url) => restDefault(url), '/foresight')
    const list = await screen.findByRole('list', { name: 'Hũ theo mức cần chú ý' })
    expect(screen.getByRole('heading', { name: 'Nhìn trước' })).toBeInTheDocument()
    const first = within(list).getAllByRole('listitem')[0]!
    expect(first).toHaveTextContent('Ăn uống')
    expect(first).toHaveTextContent('Hụt · cạn 29/11')
  })

  it('tab bar có 5 mục, nút giữa Hỏi Yofina', async () => {
    mountApp((url) => restDefault(url))
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
      if (url.endsWith('/overview')) return restDefault(url)
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
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith('/overview')).length).toBeGreaterThanOrEqual(2))
  })

  it('Đăng xuất đưa về màn Đăng nhập', async () => {
    const { router } = mountApp((url) => restDefault(url), '/profile')
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
      if (url.endsWith('/overview')) return restDefault(url)
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
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith('/overview')).length).toBeGreaterThanOrEqual(2)) // Tổng quan được làm mới

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
      return restDefault(url)
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

  it('lượt chat gửi kèm danh sách hũ của Tổng quan trong context (agent không phải đọc ví trước router, #39)', async () => {
    const { calls } = mountApp((url, init) => {
      if (url === config.agentUrl && JSON.parse(String(init.body)).forwardedProps?.warmup) return sseResponse([runStarted(), runFinished()])
      if (url === config.agentUrl) return sseResponse([runStarted(), ...textMessage('m1', 'Chào bạn.'), runFinished()])
      return restDefault(url)
    })
    const user = userEvent.setup()
    await screen.findByTestId('balance-total')
    await user.click(screen.getByRole('button', { name: /Hỏi Yofina/ }))
    const sheet = await screen.findByTestId('chat-sheet')
    await user.type(within(sheet).getByLabelText('Tin nhắn'), 'xin chào')
    await user.click(within(sheet).getByRole('button', { name: 'Gửi' }))
    expect(await within(sheet).findByText('Chào bạn.')).toBeInTheDocument()
    const context = bodyOf(runCalls(calls)[0]!).context as Array<{ description: string; value: string }>
    const wallet = context.find((c) => c.description === WALLET_CONTEXT)
    const overview = restFixture('OverviewResponse.minh') as { app_date: string; jars: Array<{ code: string }> }
    const value = JSON.parse(wallet!.value) as { app_date: string; jars: Array<{ code: string }> }
    expect(value.app_date).toBe(overview.app_date)
    expect(value.jars.map((j) => j.code)).toEqual(overview.jars.map((j) => j.code))
  })
})

// Tải lại trang rồi mở chat: hội thoại phát lại từ GET /conversations/{id}; trạng thái của từng khối confirm do server
// giữ (resolutions). Đây là lỗi đã gặp khi tự kiểm: khối đã bấm hiện lại như chưa bấm và bấm lần nữa sẽ chuyển tiền hai lần.
describe('Phát lại hội thoại sau khi tải lại trang', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  const replayConfig: Config = { ...config, replayEnabled: true }
  const TRACES = ['1'.repeat(32), '2'.repeat(32), '3'.repeat(32)]

  function confirmFor(trace: string, hash12: string, expiresInMs: number) {
    const b = validBlock('confirm.move') as { id: string; trace_id: string; data: { expires_at: string; params: unknown; params_hash: string } }
    b.id = `confirm:${trace}:${hash12}`
    b.trace_id = trace
    b.data.expires_at = new Date(Date.now() + expiresInMs).toISOString().replace(/\.\d+Z$/, 'Z')
    return b
  }

  function turn(trace: string, block: { id: string }, resolution: Record<string, unknown>) {
    return {
      trace_id: trace,
      created_at: '2026-11-22T01:00:00Z',
      user_text: 'chuyển 100 nghìn từ Giải trí sang Ăn uống',
      assistant_text: 'Chưa có khoản tiền nào được chuyển. Bạn bấm Xác nhận trên thẻ.',
      blocks: [block],
      resolutions: [{ block_id: block.id, ...resolution }],
    }
  }

  it('đã thực hiện -> biên nhận (không nút, lời cũ làm mờ); hết hạn -> không bấm được; còn hạn -> vẫn bấm được', async () => {
    const done = confirmFor(TRACES[0]!, 'aaaaaaaaaaaa', 10 * 60_000)
    const expired = confirmFor(TRACES[1]!, 'bbbbbbbbbbbb', -60_000)
    const pending = confirmFor(TRACES[2]!, 'cccccccccccc', 10 * 60_000)
    const receipt = validBlock('receipt.move')
    const { calls } = mountApp((url, init) => {
      if (url === config.agentUrl && JSON.parse(String(init.body)).forwardedProps?.warmup) return sseResponse([runStarted(), runFinished()])
      if (url.includes('/conversations/'))
        return json(200, {
          conversation_id: 'x',
          turns: [
            turn(TRACES[0]!, done, { status: 'done', resolved_at: '2026-11-22T01:01:00Z', receipt }),
            turn(TRACES[1]!, expired, { status: 'expired' }),
            turn(TRACES[2]!, pending, { status: 'pending' }),
          ],
        })
      return restDefault(url)
    }, '/', replayConfig)
    const user = userEvent.setup()
    await screen.findByTestId('balance-total')
    await user.click(screen.getByRole('button', { name: /Hỏi Yofina/ }))
    const sheet = await screen.findByTestId('chat-sheet')

    await within(sheet).findByText('Đã chuyển 100.000 ₫') // biên nhận thay khối confirm đã thực hiện
    const buttons = within(sheet).getAllByRole('button', { name: /Xác nhận chuyển/ })
    expect(buttons).toHaveLength(2) // đã thực hiện không còn nút; hết hạn + còn hạn
    expect(buttons[0]).toBeDisabled() // hết hạn
    expect(buttons[1]).toBeEnabled() // còn hạn, chưa thực hiện
    expect(within(sheet).getByText(/đã hết hạn nên số dư xem trước có thể đã cũ/)).toBeInTheDocument()

    // lời "chưa chuyển" ngay dưới biên nhận được làm mờ và ghi rõ là trước khi xác nhận; hai lượt kia không
    const messages = within(sheet).getAllByTestId('assistant-message')
    expect(messages.map((m) => m.getAttribute('data-superseded'))).toEqual(['true', null, null])
    expect(calls.some((c) => c.url.endsWith('/actions'))).toBe(false) // phát lại không ghi gì
  })

  it('bấm vào đề nghị mà server báo đã thực hiện (ALREADY_APPLIED): không ghi, tải lại trạng thái và khối đổi thành biên nhận', async () => {
    const block = confirmFor(TRACES[0]!, 'dddddddddddd', 10 * 60_000)
    const receipt = validBlock('receipt.move')
    let applied = false // server: sau lần thực hiện (ở nơi khác), trạng thái chuyển thành done
    const { calls } = mountApp((url, init) => {
      if (url === config.agentUrl && JSON.parse(String(init.body)).forwardedProps?.warmup) return sseResponse([runStarted(), runFinished()])
      if (url.includes('/conversations/'))
        return json(200, {
          conversation_id: 'x',
          turns: [turn(TRACES[0]!, block, applied ? { status: 'done', resolved_at: '2026-11-22T01:01:00Z', receipt } : { status: 'pending' })],
        })
      if (url.endsWith('/confirmations')) {
        applied = true
        return json(409, { error: { code: 'ALREADY_APPLIED', message: 'Đề nghị này đã được thực hiện rồi.' } })
      }
      return restDefault(url)
    }, '/', replayConfig)
    const user = userEvent.setup()
    await screen.findByTestId('balance-total')
    await user.click(screen.getByRole('button', { name: /Hỏi Yofina/ }))
    const sheet = await screen.findByTestId('chat-sheet')
    await user.click(await within(sheet).findByRole('button', { name: /Xác nhận chuyển/ }))

    await within(sheet).findByText('Đã chuyển 100.000 ₫')
    expect(within(sheet).queryByRole('button', { name: /Xác nhận chuyển/ })).toBeNull()
    const confirmCall = calls.find((c) => c.url.endsWith('/confirmations'))!
    expect(bodyOf(confirmCall)).toMatchObject({ confirm_block_id: block.id, conversation_id: expect.any(String) })
    expect(calls.some((c) => c.url.endsWith('/actions'))).toBe(false) // không cấp token thì không gọi /actions
  })
})
