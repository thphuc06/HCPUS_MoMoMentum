import { describe, expect, it, vi } from 'vitest'
import { ChatSession, SESSION_HEADER, type ChatItem } from './session'
import { validBlock } from '@/test/fixtures'
import {
  blockSnapshot,
  emptyResponse,
  runError,
  runFinished,
  runStarted,
  sseBody,
  sseResponse,
  textMessage,
  toolCall,
  type Ev,
} from '@/test/sse'

const CONVERSATION = '11111111-2222-4333-8444-555555555555'
const URL = 'https://runtime.example.invalid/invocations?qualifier=DEFAULT'

type Call = { url: string; init: RequestInit }

function makeSession(responses: Array<() => Response | Promise<Response>>, tokens = ['tok-1', 'tok-2']) {
  const calls: Call[] = []
  const getAccessToken = vi.fn(async (opts?: { force?: boolean }) => (opts?.force ? tokens[1]! : tokens[0]!))
  const fetchImpl = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} })
    const next = responses.shift()
    if (!next) throw new Error('hết phản hồi giả')
    return next()
  }) as unknown as typeof fetch
  const session = new ChatSession({ agentUrl: URL, conversationId: CONVERSATION, getAccessToken, fetchImpl })
  return { session, calls, getAccessToken }
}

const kinds = (items: readonly ChatItem[]) => items.map((i) => i.kind)
const notices = (items: readonly ChatItem[]) => items.filter((i): i is Extract<ChatItem, { kind: 'notice' }> => i.kind === 'notice')

function headersOf(call: Call): Record<string, string> {
  const h = call.init.headers
  return Object.fromEntries(new Headers(h as HeadersInit).entries())
}

describe('ChatSession: luồng bình thường', () => {
  it('đọc chữ chạy dần, công cụ và khối; gửi đúng header và toàn bộ lịch sử', async () => {
    const jarBlock = validBlock('jar_summary.seven_jars')
    const events: Ev[] = [
      runStarted(),
      ...textMessage('m1', 'Mình ', 'đọc ', 'số dư.'),
      ...toolCall('tc1', 'ledger___get_jar_balances'),
      blockSnapshot(String(jarBlock.id), jarBlock),
      ...textMessage('m2', 'Đây là 7 hũ.'),
      runFinished(),
    ]
    const { session, calls } = makeSession([() => sseResponse(events)])
    await session.send('số dư các hũ của mình')

    const snap = session.getSnapshot()
    expect(snap.running).toBe(false)
    expect(kinds(snap.items)).toEqual(['user', 'assistant', 'tool', 'block', 'assistant'])
    expect(snap.items[1]).toMatchObject({ kind: 'assistant', text: 'Mình đọc số dư.', done: true })
    expect(snap.items[2]).toMatchObject({ kind: 'tool', status: 'done' })
    expect(snap.items[3]).toMatchObject({ kind: 'block', id: jarBlock.id })
    expect(notices(snap.items)).toHaveLength(0)

    expect(calls).toHaveLength(1)
    const call = calls[0]!
    expect(call.url).toBe(URL)
    expect(call.init.method).toBe('POST')
    expect(call.init.credentials).toBeUndefined() // không dùng credentials: 'include'
    const h = headersOf(call)
    expect(h['authorization']).toBe('Bearer tok-1')
    expect(h[SESSION_HEADER.toLowerCase()]).toBe(CONVERSATION)
    expect(CONVERSATION.length).toBeGreaterThanOrEqual(33)
    expect(h['traceparent']).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/)
    const body = JSON.parse(String(call.init.body))
    expect(body.threadId).toBe(CONVERSATION)
    expect(body.messages).toHaveLength(1)
    expect(body.messages[0]).toMatchObject({ role: 'user', content: 'số dư các hũ của mình' })

    // lịch sử sau lượt: user + assistant (văn bản, không có khối)
    expect(session.getHistory().map((m) => m.role)).toEqual(['user', 'assistant'])
  })

  it('lượt hai gửi lại toàn bộ messages, kèm ghi chú hệ thống nhưng không hiện cho người dùng', async () => {
    const { session, calls } = makeSession([
      () => sseResponse([runStarted(), ...textMessage('m1', 'Chào bạn'), runFinished()]),
      () => sseResponse([runStarted(), ...textMessage('m2', 'Ok'), runFinished()]),
    ])
    await session.send('xin chào')
    session.addSystemNote('Người dùng đã xác nhận chuyển tiền; hệ thống đã thực hiện.')
    await session.send('số dư mới?')

    const body2 = JSON.parse(String(calls[1]!.init.body))
    expect(body2.messages.map((m: { role: string }) => m.role)).toEqual(['user', 'assistant', 'system', 'user'])
    expect(body2.messages[2].content).toContain('đã xác nhận')
    expect(session.getSnapshot().items.some((i) => JSON.stringify(i).includes('đã xác nhận chuyển tiền'))).toBe(false)
  })

  it('hai lượt dùng trùng messageId/toolCallId vẫn thành các mục riêng, đúng thứ tự', async () => {
    const turn = (text: string) => () => sseResponse([runStarted(), ...toolCall('tc1', 'ledger___get_jar_balances'), ...textMessage('m1', text), runFinished()])
    const { session } = makeSession([turn('Lượt một'), turn('Lượt hai')])
    await session.send('một')
    await session.send('hai')
    const items = session.getSnapshot().items
    expect(items.map((i) => (i.kind === 'assistant' ? `assistant:${i.text}` : i.kind))).toEqual([
      'user',
      'tool',
      'assistant:Lượt một',
      'user',
      'tool',
      'assistant:Lượt hai',
    ])
  })

  it('ACTIVITY_SNAPSHOT cùng messageId thay khối tại chỗ', async () => {
    const a = validBlock('jar_summary.seven_jars')
    const b = { ...validBlock('jar_summary.empty'), id: a.id }
    const { session } = makeSession([
      () =>
        sseResponse([
          runStarted(),
          blockSnapshot(String(a.id), a),
          ...textMessage('m1', 'xong'),
          blockSnapshot(String(a.id), b),
          runFinished(),
        ]),
    ])
    await session.send('hi')
    const blocks = session.getSnapshot().items.filter((i) => i.kind === 'block')
    expect(blocks).toHaveLength(1)
    expect((blocks[0] as { raw: { data: { jars: unknown[] } } }).raw.data.jars).toHaveLength(0)
  })

  it('bỏ qua activityType lạ và event không biết', async () => {
    const { session } = makeSession([
      () =>
        sseResponse([
          runStarted(),
          { type: 'ACTIVITY_SNAPSHOT', messageId: 'x', activityType: 'khac', content: {}, replace: true },
          { type: 'STATE_SNAPSHOT', snapshot: {} },
          { type: 'RAW', event: {}, source: 'strands' },
          ...textMessage('m1', 'ok'),
          runFinished(),
        ]),
    ])
    await session.send('hi')
    expect(kinds(session.getSnapshot().items)).toEqual(['user', 'assistant'])
  })
})

describe('ChatSession: lỗi', () => {
  it('RUN_ERROR hiện notice, không ghi trợ lý vào lịch sử, có nút thử lại cho lỗi tạm thời', async () => {
    const { session } = makeSession([() => sseResponse([runStarted(), runError('INTERNAL_ERROR', 'boom')])])
    await session.send('hi')
    const ns = notices(session.getSnapshot().items)
    expect(ns).toHaveLength(1)
    expect(ns[0]).toMatchObject({ code: 'INTERNAL_ERROR', retry: true })
    expect(session.getHistory().map((m) => m.role)).toEqual(['user'])
  })

  it('luồng rỗng (200 + thân rỗng) là lỗi, có thử lại', async () => {
    const { session } = makeSession([() => emptyResponse()])
    await session.send('hi')
    const ns = notices(session.getSnapshot().items)
    expect(ns).toHaveLength(1)
    expect(ns[0]).toMatchObject({ retry: true })
    expect(ns[0]!.title).toMatch(/chưa trả lời/i)
    expect(session.getSnapshot().running).toBe(false)
  })

  it('luồng đứt giữa chừng (không có RUN_FINISHED) là lỗi, giữ phần chữ đã nhận', async () => {
    const events = [runStarted(), ...textMessage('m1', 'Mình đang đọc'), runFinished()]
    // cắt sau RUN_STARTED + TEXT_MESSAGE_START + 1 CONTENT
    const { session } = makeSession([() => sseResponse(events, { truncateAfter: 3 })])
    await session.send('hi')
    const items = session.getSnapshot().items
    expect(items.find((i) => i.kind === 'assistant')).toMatchObject({ text: 'Mình đang đọc', done: true })
    const ns = notices(items)
    expect(ns).toHaveLength(1)
    expect(ns[0]!.title).toMatch(/gián đoạn/i)
    expect(ns[0]!.retry).toBe(true)
    // lượt lỗi không đi vào lịch sử gửi agent
    expect(session.getHistory().map((m) => m.role)).toEqual(['user'])
  })

  it('mạng đứt khi đang đọc luồng là lỗi gián đoạn', async () => {
    const events = [runStarted(), ...textMessage('m1', 'a')]
    const { session } = makeSession([() => sseResponse(events.slice(0, 3), { errorAfter: true })])
    await session.send('hi')
    expect(notices(session.getSnapshot().items)).toHaveLength(1)
    expect(session.getSnapshot().running).toBe(false)
  })

  it('RUN_FINISHED nhưng không có nội dung gì cũng báo lỗi', async () => {
    const { session } = makeSession([() => sseResponse([runStarted(), runFinished()])])
    await session.send('hi')
    const ns = notices(session.getSnapshot().items)
    expect(ns).toHaveLength(1)
    expect(ns[0]!.retry).toBe(true)
  })

  it('401: làm mới token (force) rồi thử lại đúng một lần và thành công', async () => {
    const unauthorized = () =>
      new Response(sseBody([runError('UNAUTHORIZED', 'Missing Authentication Token')]), {
        status: 401,
        headers: { 'content-type': 'text/event-stream' },
      })
    const { session, calls, getAccessToken } = makeSession([
      unauthorized,
      () => sseResponse([runStarted(), ...textMessage('m1', 'ok'), runFinished()]),
    ])
    await session.send('hi')
    expect(calls).toHaveLength(2)
    expect(headersOf(calls[0]!)['authorization']).toBe('Bearer tok-1')
    expect(headersOf(calls[1]!)['authorization']).toBe('Bearer tok-2')
    expect(getAccessToken).toHaveBeenLastCalledWith({ force: true })
    expect(notices(session.getSnapshot().items)).toHaveLength(0)
    expect(session.getSnapshot().items.some((i) => i.kind === 'assistant')).toBe(true)
  })

  it('401 hai lần liên tiếp: dừng, báo hết phiên, không thử lần ba', async () => {
    const unauthorized = () => new Response('', { status: 401, headers: { 'content-type': 'text/event-stream' } })
    const { session, calls } = makeSession([unauthorized, unauthorized])
    await session.send('hi')
    expect(calls).toHaveLength(2)
    const ns = notices(session.getSnapshot().items)
    expect(ns).toHaveLength(1)
    expect(ns[0]).toMatchObject({ code: 'UNAUTHORIZED', retry: false })
  })

  it('403: thông báo không có quyền dùng phiên chat, không thử lại', async () => {
    const { session, calls } = makeSession([
      () => new Response(sseBody([runError('ACCESS_DENIED')]), { status: 403, headers: { 'content-type': 'text/event-stream' } }),
    ])
    await session.send('hi')
    expect(calls).toHaveLength(1)
    expect(notices(session.getSnapshot().items)[0]).toMatchObject({ code: 'ACCESS_DENIED', retry: false })
  })

  it('409 SESSION_BUSY: thông báo bận, cho thử lại', async () => {
    const { session } = makeSession([
      () => new Response(sseBody([runError('SESSION_BUSY')]), { status: 409, headers: { 'content-type': 'text/event-stream' } }),
    ])
    await session.send('hi')
    expect(notices(session.getSnapshot().items)[0]).toMatchObject({ code: 'SESSION_BUSY', retry: true })
  })

  it('retry() bỏ phần dở dang và gửi lại cùng lịch sử (không nhân đôi tin nhắn người dùng)', async () => {
    const { session, calls } = makeSession([
      () => emptyResponse(),
      () => sseResponse([runStarted(), ...textMessage('m1', 'đây rồi'), runFinished()]),
    ])
    await session.send('hỏi gì đó')
    expect(notices(session.getSnapshot().items)).toHaveLength(1)
    await session.retry()
    const items = session.getSnapshot().items
    expect(kinds(items)).toEqual(['user', 'assistant'])
    const body = JSON.parse(String(calls[1]!.init.body))
    expect(body.messages).toHaveLength(1)
  })

  it('gửi khi đang chạy bị bỏ qua', async () => {
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    const { session, calls } = makeSession([
      async () => {
        await gate
        return sseResponse([runStarted(), ...textMessage('m1', 'x'), runFinished()])
      },
    ])
    const first = session.send('một')
    await session.send('hai')
    expect(session.getSnapshot().items.filter((i) => i.kind === 'user')).toHaveLength(1)
    release()
    await first
    expect(calls).toHaveLength(1)
  })
})

describe('ChatSession: khối và phát lại', () => {
  it('replaceBlock thay confirm bằng receipt ở đúng vị trí', async () => {
    const confirm = validBlock('confirm.move')
    const receipt = validBlock('receipt.move')
    const { session } = makeSession([
      () => sseResponse([runStarted(), blockSnapshot(String(confirm.id), confirm), ...textMessage('m1', 'Bạn xác nhận nhé'), runFinished()]),
    ])
    await session.send('chuyển')
    session.replaceBlock(String(confirm.id), receipt, String(receipt.id))
    const items = session.getSnapshot().items
    expect(kinds(items)).toEqual(['user', 'block', 'assistant'])
    expect(items[1]).toMatchObject({ id: receipt.id })
  })

  it('hydrate dựng lại tin nhắn, khối và lịch sử từ dữ liệu server', () => {
    const { session } = makeSession([])
    session.hydrate([
      { trace_id: 'a'.repeat(32), created_at: '2026-11-21T01:00:00Z', user_text: 'số dư', assistant_text: 'đây', blocks: [validBlock('jar_summary.seven_jars')] },
    ])
    const items = session.getSnapshot().items
    expect(kinds(items)).toEqual(['user', 'block', 'assistant'])
    expect(session.getHistory().map((m) => m.role)).toEqual(['user', 'assistant'])
  })

  it('replaceBlock đánh dấu khối là kết quả của đề nghị đã thực hiện (resolved)', async () => {
    const confirm = validBlock('confirm.move')
    const receipt = validBlock('receipt.move')
    const { session } = makeSession([() => sseResponse([runStarted(), blockSnapshot(String(confirm.id), confirm), runFinished()])])
    await session.send('chuyển')
    session.replaceBlock(String(confirm.id), receipt, String(receipt.id))
    expect(session.getSnapshot().items[1]).toMatchObject({ kind: 'block', id: receipt.id, resolved: true })
  })

  it('addSystemNote cùng key chỉ thêm một lần', () => {
    const { session } = makeSession([])
    session.addSystemNote('đã chuyển', 'receipt:x')
    session.addSystemNote('đã chuyển', 'receipt:x')
    expect(session.getHistory().filter((m) => m.role === 'system')).toHaveLength(1)
  })
})

// Trạng thái của khối confirm do server giữ (`resolutions`); phát lại phải theo đó, không theo số dư hay đồng hồ.
describe('ChatSession: phát lại trạng thái đề nghị từ server', () => {
  const TRACE = 'a'.repeat(32)
  const confirm = () => validBlock('confirm.move') as { id: string; data: { expires_at: string } }
  const turnWith = (block: unknown, resolutions: unknown[]) =>
    ({ trace_id: TRACE, created_at: '2026-11-21T01:00:00Z', user_text: 'chuyển 100 nghìn', assistant_text: 'Chưa có khoản tiền nào được chuyển. Bạn bấm Xác nhận.', blocks: [block], resolutions }) as never

  it('done: biên nhận thay chỗ khối confirm (không còn nút), kèm ghi chú hệ thống cho agent', () => {
    const { session } = makeSession([])
    const c = confirm()
    const receipt = validBlock('receipt.move')
    session.hydrate([turnWith(c, [{ block_id: c.id, status: 'done', resolved_at: '2026-11-21T01:01:00Z', receipt }])])
    const items = session.getSnapshot().items
    expect(kinds(items)).toEqual(['user', 'block', 'assistant'])
    expect(items[1]).toMatchObject({ kind: 'block', id: receipt.id, raw: receipt, resolved: true })
    expect(items.some((i) => i.kind === 'block' && i.id === c.id)).toBe(false)
    // agent biết việc đã làm, ngay sau lượt đó
    expect(session.getHistory().map((m) => m.role)).toEqual(['user', 'assistant', 'system'])
    expect(session.getHistory()[2]!.content).toContain(String((receipt.data as { transaction_id: string }).transaction_id))
  })

  it('done mà biên nhận hỏng: giữ khối confirm nhưng khóa (ui=done), không để bấm lại', () => {
    const { session } = makeSession([])
    const c = confirm()
    session.hydrate([turnWith(c, [{ block_id: c.id, status: 'done', receipt: { type: 'receipt' } }])])
    expect(session.getSnapshot().items[1]).toMatchObject({ id: c.id, ui: 'done', resolved: true })
  })

  it('expired: khối confirm được đánh dấu hết hạn (ui=expired)', () => {
    const { session } = makeSession([])
    const c = confirm()
    session.hydrate([turnWith(c, [{ block_id: c.id, status: 'expired' }])])
    expect(session.getSnapshot().items[1]).toMatchObject({ id: c.id, ui: 'expired' })
    expect(session.getSnapshot().items[1]).not.toHaveProperty('resolved', true)
    expect(session.getHistory().map((m) => m.role)).toEqual(['user', 'assistant']) // chưa thực hiện: không có ghi chú
  })

  it('cancelled (đã bấm "Không", server giữ): khối giữ lại, đánh dấu hủy, không ghi chú hệ thống; hũ khối confirm_action cũng vậy', () => {
    const { session } = makeSession([])
    const c = confirm()
    session.hydrate([turnWith(c, [{ block_id: c.id, status: 'cancelled', resolved_at: '2026-11-21T01:01:00Z' }])])
    expect(session.getSnapshot().items[1]).toMatchObject({ id: c.id, ui: 'cancelled' })
    expect(session.getSnapshot().items[1]).not.toHaveProperty('resolved', true)
    expect(session.getHistory().map((m) => m.role)).toEqual(['user', 'assistant'])
    const a = validBlock('confirm_action.record_transaction') as { id: string }
    session.hydrate([turnWith(a, [{ block_id: a.id, status: 'cancelled', resolved_at: '2026-11-21T01:01:00Z' }])])
    expect(session.getSnapshot().items[1]).toMatchObject({ id: a.id, ui: 'cancelled' })
  })

  it('done với biên nhận receipt_action (thao tác ghi khác chuyển hũ): biên nhận thay chỗ khối confirm_action', () => {
    const { session } = makeSession([])
    const a = validBlock('confirm_action.record_transaction') as { id: string }
    const receipt = validBlock('receipt_action.record_transaction') as { id: string }
    session.hydrate([turnWith(a, [{ block_id: a.id, status: 'done', resolved_at: '2026-11-21T01:01:00Z', receipt }])])
    const items = session.getSnapshot().items
    expect(items[1]).toMatchObject({ kind: 'block', id: receipt.id, resolved: true })
    expect(session.getHistory().map((m) => m.role)).toEqual(['user', 'assistant', 'system'])
    expect(session.getHistory()[2]!.content).toContain('Hệ thống ghi nhận')
  })

  it('pending và server cũ không có resolutions: khối nguyên vẹn, chưa đánh dấu gì', () => {
    const { session } = makeSession([])
    const c = confirm()
    session.hydrate([turnWith(c, [{ block_id: c.id, status: 'pending' }])])
    expect(session.getSnapshot().items[1]).toMatchObject({ id: c.id, raw: c })
    expect(session.getSnapshot().items[1]).toMatchObject({ ui: undefined, resolved: undefined })
    session.hydrate([{ trace_id: TRACE, created_at: '2026-11-21T01:00:00Z', user_text: 'q', assistant_text: 'a', blocks: [c] }])
    expect(session.getSnapshot().items[1]).toMatchObject({ id: c.id, ui: undefined })
  })

  it('applyResolutions: chỉ vá khối đang hiện, không dựng lại hội thoại (giữ thông báo lỗi chưa lưu)', async () => {
    const c = confirm()
    const receipt = validBlock('receipt.move')
    const { session } = makeSession([
      () => sseResponse([runStarted(), blockSnapshot(c.id, c), runFinished()]),
      () => sseResponse([]), // lượt lỗi: sinh thông báo, chưa được server lưu
    ])
    await session.send('chuyển')
    await session.send('thử tiếp')
    const before = session.getSnapshot().items
    expect(before.some((i) => i.kind === 'notice')).toBe(true)

    session.applyResolutions([turnWith(c, [{ block_id: c.id, status: 'done', receipt }])])
    const items = session.getSnapshot().items
    expect(items.some((i) => i.kind === 'notice')).toBe(true) // không bị xóa
    const blk = items.find((i) => i.kind === 'block')!
    expect(blk).toMatchObject({ id: receipt.id, resolved: true })
    expect(session.getHistory().filter((m) => m.role === 'system')).toHaveLength(1)

    // gọi lại cùng dữ liệu: không đổi, không thêm ghi chú thứ hai
    session.applyResolutions([turnWith(c, [{ block_id: c.id, status: 'done', receipt }])])
    expect(session.getHistory().filter((m) => m.role === 'system')).toHaveLength(1)
  })
})
