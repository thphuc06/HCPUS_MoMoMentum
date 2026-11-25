import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChatSession, SESSION_BUSY_RETRY_DELAYS_MS, WARMUP_WAIT_MS, type ChatItem } from './session'
import { runError, runFinished, runStarted, sseBody, sseResponse, textMessage } from '@/test/sse'

// Lỗi 409 SESSION_BUSY ở tin đầu tiên sau khi mở chat (#11): lượt làm nóng và lượt chat dùng cùng session id của Runtime,
// nên lượt chat phải đợi lượt làm nóng xong (có trần), và 409 SESSION_BUSY được thử lại có giới hạn. Runtime giả ở mức fetch.

const CONVERSATION = '11111111-2222-4333-8444-555555555555'
const URL = 'https://runtime.example.invalid/invocations?qualifier=DEFAULT'

type Call = { kind: 'warmup' | 'chat'; init: RequestInit }

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

/** `warmup`: phản hồi của lượt làm nóng; `chat`: lần lượt các phản hồi của lượt chat. */
function makeSession(opts: { warmup?: () => Response | Promise<Response>; chat: Array<() => Response | Promise<Response>> }) {
  const calls: Call[] = []
  const fetchImpl = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
    const warm = JSON.parse(String(init?.body)).forwardedProps?.warmup === true
    calls.push({ kind: warm ? 'warmup' : 'chat', init: init ?? {} })
    if (warm) return opts.warmup ? opts.warmup() : sseResponse([runStarted(), runFinished()])
    const next = opts.chat.shift()
    if (!next) throw new Error('hết phản hồi giả')
    return next()
  }) as unknown as typeof fetch
  const getAccessToken = vi.fn(async (o?: { force?: boolean }) => (o?.force ? 'tok-2' : 'tok-1'))
  const session = new ChatSession({ agentUrl: URL, conversationId: CONVERSATION, getAccessToken, fetchImpl })
  return { session, calls }
}

const answer = (text: string) => () => sseResponse([runStarted(), ...textMessage('m1', text), runFinished()])
const busy = () => new Response(sseBody([runError('SESSION_BUSY', 'Session operation in progress, please retry')]), { status: 409, headers: { 'content-type': 'text/event-stream' } })
const notices = (items: readonly ChatItem[]) => items.filter((i): i is Extract<ChatItem, { kind: 'notice' }> => i.kind === 'notice')
const assistantTexts = (items: readonly ChatItem[]) => items.flatMap((i) => (i.kind === 'assistant' ? [i.text] : []))
/** Cho các promise đang chờ chạy hết (fetch giả, dynamic import, đọc luồng). */
const settle = async () => {
  for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 0))
}

afterEach(() => vi.useRealTimers())

describe('ChatSession: chờ lượt làm nóng trước khi gửi', () => {
  it('gửi khi lượt làm nóng chưa trả về: yêu cầu chat chỉ đi sau khi làm nóng xong, không hiện lỗi', async () => {
    const gate = deferred<void>()
    const { session, calls } = makeSession({
      warmup: async () => {
        await gate.promise
        return sseResponse([runStarted(), runFinished()])
      },
      chat: [answer('Chào bạn')],
    })
    void session.warmUp()
    const sent = session.send('xin chào')
    await settle()
    expect(calls.map((c) => c.kind)).toEqual(['warmup'])
    expect(session.getSnapshot().running).toBe(true) // giao diện vẫn ở trạng thái đang gửi
    expect(notices(session.getSnapshot().items)).toHaveLength(0)

    gate.resolve()
    await sent
    expect(calls.map((c) => c.kind)).toEqual(['warmup', 'chat'])
    expect(notices(session.getSnapshot().items)).toHaveLength(0)
    expect(assistantTexts(session.getSnapshot().items)).toEqual(['Chào bạn'])
  })

  it('làm nóng treo quá trần: tin vẫn được gửi khi hết trần', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const { session, calls } = makeSession({ warmup: () => new Promise<Response>(() => {}), chat: [answer('ok')] })
    void session.warmUp()
    const sent = session.send('hi')
    await vi.advanceTimersByTimeAsync(WARMUP_WAIT_MS - 1)
    expect(calls.map((c) => c.kind)).toEqual(['warmup'])
    await vi.advanceTimersByTimeAsync(1)
    await sent
    expect(calls.map((c) => c.kind)).toEqual(['warmup', 'chat'])
    expect(assistantTexts(session.getSnapshot().items)).toEqual(['ok'])
    expect(notices(session.getSnapshot().items)).toHaveLength(0)
  })

  it('làm nóng lỗi: gửi ngay, không hiện lỗi của lượt làm nóng', async () => {
    const { session, calls } = makeSession({ warmup: () => Promise.reject(new TypeError('network error')), chat: [answer('ok')] })
    void session.warmUp()
    await session.send('hi')
    expect(calls.map((c) => c.kind)).toEqual(['warmup', 'chat'])
    expect(notices(session.getSnapshot().items)).toHaveLength(0)
  })

  it('Dừng trong lúc chờ làm nóng: kết thúc lượt ngay, không gửi tin', async () => {
    const { session, calls } = makeSession({ warmup: () => new Promise<Response>(() => {}), chat: [answer('ok')] })
    void session.warmUp()
    const sent = session.send('hi')
    await settle()
    session.stop()
    await sent
    expect(session.getSnapshot().running).toBe(false)
    expect(calls.map((c) => c.kind)).toEqual(['warmup'])
    expect(notices(session.getSnapshot().items)).toHaveLength(0)
  })

  it('lượt làm nóng của hội thoại cũ không chặn hội thoại mới', async () => {
    const { session, calls } = makeSession({ warmup: () => new Promise<Response>(() => {}), chat: [answer('ok')] })
    void session.warmUp()
    session.reset('99999999-2222-4333-8444-555555555555')
    await session.send('hi')
    expect(calls.map((c) => c.kind)).toEqual(['warmup', 'chat'])
  })
})

describe('ChatSession: thử lại khi 409 SESSION_BUSY', () => {
  it('lần đầu 409, lần hai 200: câu trả lời hiện bình thường, đúng 2 yêu cầu gửi, lùi 1 s', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const { session, calls } = makeSession({ chat: [busy, answer('Đây rồi')] })
    const sent = session.send('hi')
    await vi.advanceTimersByTimeAsync(SESSION_BUSY_RETRY_DELAYS_MS[0]! - 1)
    expect(calls.filter((c) => c.kind === 'chat')).toHaveLength(1)
    expect(notices(session.getSnapshot().items)).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(1)
    await sent
    expect(calls.filter((c) => c.kind === 'chat')).toHaveLength(2)
    expect(notices(session.getSnapshot().items)).toHaveLength(0)
    expect(assistantTexts(session.getSnapshot().items)).toEqual(['Đây rồi'])
    expect(session.getHistory().map((m) => m.role)).toEqual(['user', 'assistant'])
  })

  it('409 liên tục quá số lần: hiện lỗi SESSION_BUSY như cũ sau 1 + 3 lần gửi (lùi 1 s, 2 s, 4 s)', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    expect(SESSION_BUSY_RETRY_DELAYS_MS).toEqual([1000, 2000, 4000])
    const { session, calls } = makeSession({ chat: [busy, busy, busy, busy, answer('không tới')] })
    const sent = session.send('hi')
    await vi.advanceTimersByTimeAsync(1000 + 2000 + 4000 + 10_000)
    await sent
    expect(calls.filter((c) => c.kind === 'chat')).toHaveLength(4)
    const ns = notices(session.getSnapshot().items)
    expect(ns).toHaveLength(1)
    expect(ns[0]).toMatchObject({ code: 'SESSION_BUSY', retry: true, title: 'Yofina đang bận' })
  })

  it('500: không thử lại, báo lỗi ngay', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const { session, calls } = makeSession({ chat: [() => new Response('', { status: 500 }), answer('không tới')] })
    const sent = session.send('hi')
    await vi.advanceTimersByTimeAsync(20_000)
    await sent
    expect(calls.filter((c) => c.kind === 'chat')).toHaveLength(1)
    expect(notices(session.getSnapshot().items)[0]).toMatchObject({ code: 'HTTP_500' })
  })

  it('401: chỉ làm mới token một lần như cũ, không thử lại kiểu bận', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const unauthorized = () => new Response('', { status: 401, headers: { 'content-type': 'text/event-stream' } })
    const { session, calls } = makeSession({ chat: [unauthorized, unauthorized, answer('không tới')] })
    const sent = session.send('hi')
    await vi.advanceTimersByTimeAsync(20_000)
    await sent
    expect(calls.filter((c) => c.kind === 'chat')).toHaveLength(2)
    expect(notices(session.getSnapshot().items)[0]).toMatchObject({ code: 'UNAUTHORIZED', retry: false })
  })
})
