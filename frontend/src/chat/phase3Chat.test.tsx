import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { bodyOf, callsTo, config, isWarmup, json, mountApp, restDefault, runCalls, type Call } from '@/test/mountApp'
import { restFixture, validBlock } from '@/test/fixtures'
import { blockSnapshot, runFinished, runStarted, sseResponse, textMessage, toolCall } from '@/test/sse'
import type { Config } from '@/lib/config'

// Cảnh 2 của demo trong chat (H3a–H3c, H4, H6a, H6b): what-if -> khối số liệu trước, lời giải thích sau -> "Vì sao" ->
// "Chọn" phương án -> khối xác nhận -> thực hiện -> Hoàn tác. Backend và agent giả ở mức fetch.

type Json = Record<string, any>

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

function turn() {
  const fc = validBlock('forecast_timeline.what_if') as Json
  const impact = validBlock('obligation_impact.minh_headphones') as Json
  const options = validBlock('options.move_remind_skip') as Json
  const refs = options.data.options.filter((o: Json) => o.action).map((o: Json) => o.action.block_id as string)
  const confirm = validBlock('confirm.move') as Json
  confirm.id = refs[0]
  confirm.data.expires_at = new Date(Date.now() + 5 * 60_000).toISOString().replace(/\.\d+Z$/, 'Z')
  const nudge = validBlock('confirm_action.schedule_nudge') as Json
  nudge.id = refs[1]
  nudge.data.expires_at = confirm.data.expires_at
  return { fc, impact, options, confirm, nudge }
}

function setup(opts: { cfg?: Config } = {}) {
  const t = turn()
  const receipt = validBlock('receipt.move') as Json
  const undoReceipt = { ...(validBlock('receipt.move') as Json), id: 'receipt:undo' }
  let runs = 0
  let applied = 0
  const { calls } = mountApp((url, init) => {
    const path = new URL(url).pathname
    if (url === config.agentUrl && JSON.parse(String(init.body)).forwardedProps?.warmup) return sseResponse([runStarted(), runFinished()])
    if (url === config.agentUrl) {
      runs += 1
      return sseResponse([
        runStarted(),
        ...toolCall('t1', 'forecast___run_scenario'),
        blockSnapshot(t.fc.id, t.fc),
        blockSnapshot(t.impact.id, t.impact),
        blockSnapshot(t.options.id, t.options),
        blockSnapshot(t.confirm.id, t.confirm),
        blockSnapshot(t.nudge.id, t.nudge),
        ...textMessage('m1', 'Đây là tác động của món này.'),
        runFinished(),
      ])
    }
    if (path === '/confirmations')
      return json(200, { confirm_token: 'aaa.bbb', expires_at: '2026-12-10T03:02:00Z', ttl_seconds: 120, tool: 'move_between_jars', params: JSON.parse(String(init.body)).params, params_hash: 'a'.repeat(64) })
    if (path === '/actions') return json(200, ++applied === 1 ? receipt : undoReceipt)
    if (path.startsWith('/traces/')) return json(200, restFixture('TraceResponse.what_if'))
    if (path === '/feedback') return json(200, restFixture('FeedbackResponse.default'))
    return restDefault(url)
  }, '/', opts.cfg)
  return { calls, t, receipt, runs: () => runs }
}

async function openAndAsk(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByTestId('balance-total')
  await user.click(screen.getByRole('button', { name: /Hỏi Yofina/ }))
  const sheet = await screen.findByTestId('chat-sheet')
  await user.type(within(sheet).getByLabelText('Tin nhắn'), 'nếu mua tai nghe 1,2 triệu bằng Trả sau thì sao')
  await user.click(within(sheet).getByRole('button', { name: 'Gửi' }))
  await within(sheet).findByText('Đây là tác động của món này.', {}, { timeout: 5000 })
  return sheet
}

describe('chat phase 3: what-if, Vì sao, chọn phương án, xác nhận, Hoàn tác', () => {
  it('khối số liệu hiện theo thứ tự, trước lời giải thích; khối xác nhận được phương án tham chiếu bị ẩn tới khi chọn', async () => {
    setup()
    const user = userEvent.setup()
    const sheet = await openAndAsk(user)
    const order = [...sheet.querySelectorAll('[data-block], [data-testid="assistant-text"]')].map((e) => e.getAttribute('data-block') ?? 'text').filter((x, i, a) => a.indexOf(x) === i)
    expect(order.slice(0, 3)).toEqual(['forecast_timeline', 'obligation_impact', 'options'])
    expect(order.indexOf('text')).toBeGreaterThan(order.indexOf('options')) // số liệu đến trước lời
    expect(sheet.querySelector('[data-block="confirm"]')).toBeNull()
    expect(sheet.querySelector('[data-block="confirm_action"]')).toBeNull()
    expect(within(sheet).getByTestId('forecast-compare')).toBeInTheDocument()
    expect(within(sheet).getByTestId('item-cost')).toHaveTextContent('1.200.000 ₫')
    expect(within(sheet).getByTestId('total-due')).toHaveTextContent('2.200.000 ₫')
    expect(within(sheet).getByText('Yofina đã làm')).toBeInTheDocument()
    expect(within(sheet).getByText('Đã chạy kịch bản "nếu"')).toBeInTheDocument() // nhãn bước công cụ của kịch bản (không còn "Đã xử lý")
  })

  it('"Vì sao" (H4): GET /traces/{trace_id} của khối, bảng có dữ liệu đã dùng, luật đã kiểm, nhóm tin cậy kèm lý do, mã trace; đóng được', async () => {
    const { calls, t } = setup()
    const user = userEvent.setup()
    const sheet = await openAndAsk(user)
    const why = within(sheet).getAllByRole('button', { name: 'Vì sao' })
    expect(why.length).toBeGreaterThanOrEqual(3) // dự báo, nghĩa vụ, phương án
    await user.click(why[why.length - 1]!)
    const panel = await screen.findByRole('dialog', { name: 'Vì sao' })
    await within(panel).findByTestId('explain-data-used')
    expect(callsTo(calls, 'GET', `/traces/${t.options.trace_id}`)).toHaveLength(1)
    expect(within(panel).getByTestId('explain-rules')).toHaveTextContent('Nghĩa vụ trên thu nhập')
    expect(within(panel).getByRole('region', { name: 'Độ tin cậy' })).toHaveTextContent('Vừa')
    expect(within(panel).getByTestId('explain-trace-id')).toBeInTheDocument()
    await user.click(within(panel).getByRole('button', { name: 'Đóng bảng Vì sao' }))
    expect(screen.queryByRole('dialog', { name: 'Vì sao' })).toBeNull()
  })

  it('"Vì sao" lỗi (trace không thuộc người dùng): báo bằng tiếng Việt, có Thử lại', async () => {
    const t = turn()
    mountApp((url, init) => {
      const path = new URL(url).pathname
      if (url === config.agentUrl && JSON.parse(String(init.body)).forwardedProps?.warmup) return sseResponse([runStarted(), runFinished()])
      if (url === config.agentUrl) return sseResponse([runStarted(), blockSnapshot(t.options.id, t.options), ...textMessage('m1', 'Xong.'), runFinished()])
      if (path.startsWith('/traces/')) return json(404, { error: { code: 'TRACE_NOT_FOUND', message: 'x' } })
      return restDefault(url)
    })
    const user = userEvent.setup()
    await screen.findByTestId('balance-total')
    await user.click(screen.getByRole('button', { name: /Hỏi Yofina/ }))
    const sheet = await screen.findByTestId('chat-sheet')
    await user.type(within(sheet).getByLabelText('Tin nhắn'), 'gợi ý')
    await user.click(within(sheet).getByRole('button', { name: 'Gửi' }))
    await user.click(await within(sheet).findByRole('button', { name: 'Vì sao' }))
    const panel = await screen.findByRole('dialog', { name: 'Vì sao' })
    expect(await within(panel).findByRole('alert')).toHaveTextContent('Không tìm thấy bản ghi của câu trả lời này')
    expect(within(panel).getByRole('button', { name: 'Thử lại' })).toBeInTheDocument()
  })

  it('chọn phương án (feedback) -> khối xác nhận hiện -> xác nhận -> biên nhận có Hoàn tác -> Hoàn tác chuyển ngược qua cùng luồng token', async () => {
    const { calls, receipt } = setup()
    const user = userEvent.setup()
    const sheet = await openAndAsk(user)

    await user.click(within(sheet).getByRole('button', { name: 'Chọn: Bù 100.000 ₫ từ hũ Giải trí' }))
    await waitFor(() => expect(callsTo(calls, 'POST', '/feedback')).toHaveLength(1))
    expect(bodyOf(callsTo(calls, 'POST', '/feedback')[0]!)).toMatchObject({ option_id: 'move_from_giai_tri', decision: 'accepted' })
    expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(0) // chọn chưa tạo token
    const confirm = await waitFor(() => {
      const el = sheet.querySelector('[data-block="confirm"]')
      expect(el).not.toBeNull()
      return el as HTMLElement
    })
    // khối xác nhận của phương án kia (nhắc lại) vẫn ẩn
    expect(sheet.querySelector('[data-block="confirm_action"]')).toBeNull()

    await user.click(within(confirm).getByRole('button', { name: /Xác nhận chuyển/ }))
    await within(sheet).findByRole("heading", { name: /^Đã chuyển 100.000/ })
    expect(sheet.querySelector('[data-block="confirm"]')).toBeNull()
    const undo = within(sheet).getByRole('button', { name: /Hoàn tác · còn \d\d:\d\d/ })

    await user.click(undo)
    await waitFor(() => expect(callsTo(calls, 'POST', '/actions')).toHaveLength(2))
    const conf2 = bodyOf(callsTo(calls, 'POST', '/confirmations')[1]!)
    expect(conf2).toEqual({ tool: 'move_between_jars', params: { from_jar: receipt.data.to_jar.code, to_jar: receipt.data.from_jar.code, amount_vnd: receipt.data.amount_vnd } })
    expect(await within(sheet).findByTestId('undone-note')).toHaveTextContent('Đã hoàn tác')
    expect(within(sheet).queryByRole('button', { name: /Hoàn tác/ })).toBeNull()
  })

  it('lượt sau gửi kèm dòng hệ thống về việc đã thực hiện và việc đã hoàn tác', async () => {
    const { calls } = setup()
    const user = userEvent.setup()
    const sheet = await openAndAsk(user)
    await user.click(within(sheet).getByRole('button', { name: 'Chọn: Bù 100.000 ₫ từ hũ Giải trí' }))
    const confirm = await waitFor(() => {
      const el = sheet.querySelector('[data-block="confirm"]')
      expect(el).not.toBeNull()
      return el as HTMLElement
    })
    await user.click(within(confirm).getByRole('button', { name: /Xác nhận chuyển/ }))
    await user.click(await within(sheet).findByRole('button', { name: /Hoàn tác/ }))
    await within(sheet).findByTestId('undone-note')
    await user.type(within(sheet).getByLabelText('Tin nhắn'), 'xong chưa')
    await user.click(within(sheet).getByRole('button', { name: 'Gửi' }))
    await waitFor(() => expect(runCalls(calls)).toHaveLength(2))
    const sys = (bodyOf(runCalls(calls)[1]!).messages as Array<{ role: string; content: string }>).filter((m) => m.role === 'system')
    expect(sys).toHaveLength(2)
    expect(sys[0]!.content).toContain('đã xác nhận')
    expect(sys[1]!.content).toContain('Hoàn tác')
  })

  it('làm nóng phiên khi mở sheet; tắt được bằng cấu hình warmupEnabled = false', async () => {
    const a = setup()
    const user = userEvent.setup()
    await screen.findByTestId('balance-total')
    await user.click(screen.getByRole('button', { name: /Hỏi Yofina/ }))
    await waitFor(() => expect(a.calls.some(isWarmup)).toBe(true))
  })
})

describe('chat phase 3: làm nóng tắt được', () => {
  it('warmupEnabled = false: mở sheet không gọi Runtime', async () => {
    const { calls } = setup({ cfg: { ...config, warmupEnabled: false } })
    const user = userEvent.setup()
    await screen.findByTestId('balance-total')
    await user.click(screen.getByRole('button', { name: /Hỏi Yofina/ }))
    await screen.findByTestId('chat-sheet')
    await new Promise((r) => setTimeout(r, 150))
    expect(calls.filter((c: Call) => c.url === config.agentUrl)).toHaveLength(0)
  })
})

describe('chat phase 3: H1, H5, H7, H8', () => {
  function oneTurn(events: (t: ReturnType<typeof turn>) => unknown[]) {
    const t = turn()
    const { calls } = mountApp((url, init) => {
      if (url === config.agentUrl && JSON.parse(String(init.body)).forwardedProps?.warmup) return sseResponse([runStarted(), runFinished()])
      if (url === config.agentUrl) return sseResponse(events(t) as never)
      return restDefault(url)
    })
    return { calls }
  }
  async function ask(user: ReturnType<typeof userEvent.setup>, text: string) {
    await screen.findByTestId('balance-total')
    await user.click(screen.getByRole('button', { name: /Hỏi Yofina/ }))
    const sheet = await screen.findByTestId('chat-sheet')
    await user.type(within(sheet).getByLabelText('Tin nhắn'), text)
    await user.click(within(sheet).getByRole('button', { name: 'Gửi' }))
    return sheet
  }

  it('H1: mở đầu có "Mình làm được / Mình chưa làm" và gợi ý bấm được (gửi như tin nhắn)', async () => {
    const { calls } = oneTurn(() => [runStarted(), ...textMessage('m1', 'ok'), runFinished()])
    const user = userEvent.setup()
    await screen.findByTestId('balance-total')
    await user.click(screen.getByRole('button', { name: /Hỏi Yofina/ }))
    const sheet = await screen.findByTestId('chat-sheet')
    expect(within(sheet).getByText('Mình làm được')).toBeInTheDocument()
    expect(within(sheet).getByText('Mình chưa làm')).toBeInTheDocument()
    await user.click(within(sheet).getByRole('button', { name: /Nếu mua tai nghe 1,2 triệu bằng Trả sau thì sao/ }))
    await waitFor(() => expect(runCalls(calls)).toHaveLength(1))
    expect(bodyOf(runCalls(calls)[0]!).messages.at(-1).content).toBe('Nếu mua tai nghe 1,2 triệu bằng Trả sau thì sao?')
  })

  it('H5: hỏi lại một câu kèm chip; bấm chip gửi câu trả lời và chip cũ hết bấm được', async () => {
    let n = 0
    const { calls } = oneTurn(() => {
      n += 1
      const c = validBlock('clarify.amount') as Json
      return n === 1 ? [runStarted(), blockSnapshot(c.id, c), runFinished()] : [runStarted(), ...textMessage('m1', 'Đã rõ.'), runFinished()]
    })
    const user = userEvent.setup()
    const sheet = await ask(user, 'nếu mua cái điện thoại thì sao')
    const q = await within(sheet).findByTestId('clarify-question')
    expect(q).toBeInTheDocument()
    const chip = (validBlock('clarify.amount') as Json).data.chips[0]
    await user.click(within(sheet).getByRole('button', { name: chip.label }))
    await within(sheet).findByText('Đã rõ.')
    expect(bodyOf(runCalls(calls)[1]!).messages.at(-1).content).toBe(chip.value ?? chip.label)
    expect(within(sheet).getByRole('button', { name: chip.label })).toBeDisabled()
  })

  it('H7: từ chối đúng phạm vi kèm việc làm được; bấm gợi ý gửi câu hỏi', async () => {
    const { calls } = oneTurn(() => {
      const nb = validBlock('notice.out_of_scope_suggestions') as Json
      return [runStarted(), blockSnapshot(nb.id, nb), runFinished()]
    })
    const user = userEvent.setup()
    const sheet = await ask(user, 'nên mua cổ phiếu nào')
    const sg = await within(sheet).findByTestId('notice-suggestions')
    expect(within(sheet).getByRole('status')).toHaveAttribute('data-notice', 'out_of_scope')
    await user.click(within(sg).getAllByRole('button')[0]!)
    await waitFor(() => expect(runCalls(calls)).toHaveLength(2))
  })

  it('H8a: suy giảm có "Thử lại" gửi lại lượt', async () => {
    let n = 0
    const { calls } = oneTurn(() => {
      n += 1
      const nb = validBlock('notice.error_retry') as Json
      return n === 1 ? [runStarted(), blockSnapshot(nb.id, nb), runFinished()] : [runStarted(), ...textMessage('m1', 'Giờ đã có.'), runFinished()]
    })
    const user = userEvent.setup()
    const sheet = await ask(user, 'nếu mua tai nghe thì sao')
    await user.click(await within(sheet).findByRole('button', { name: 'Thử lại' }))
    await within(sheet).findByText('Giờ đã có.')
    expect(runCalls(calls)).toHaveLength(2)
  })

  it('Dừng: bấm Dừng giữa lượt kết thúc lượt, không hiện lỗi', async () => {
    mountApp((url, init) => {
      if (url === config.agentUrl && JSON.parse(String(init.body)).forwardedProps?.warmup) return sseResponse([runStarted(), runFinished()])
      if (url === config.agentUrl) {
        const stream = new ReadableStream<Uint8Array>({
          start(c) {
            ;(init as RequestInit).signal?.addEventListener('abort', () => c.error(new DOMException('aborted', 'AbortError')))
          },
        })
        return new Response(stream, { status: 200, headers: { 'content-type': 'text/event-stream' } })
      }
      return restDefault(url)
    })
    const user = userEvent.setup()
    const sheet = await ask(user, 'chạy lâu')
    await user.click(await within(sheet).findByRole('button', { name: 'Dừng' }))
    await within(sheet).findByRole('button', { name: 'Gửi' })
    expect(within(sheet).queryByRole('alert')).toBeNull()
  })
})
