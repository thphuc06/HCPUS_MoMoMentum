import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/errors'
import { HttpConversationRepository, NullConversationRepository, clearConversationId, loadConversationId, saveConversationId } from './repository'
import { ChatSession } from './session'
import { validBlock } from '@/test/fixtures'

const BASE = 'https://api.example.invalid'
const ID = '11111111-2222-4333-8444-555555555555'

function repo(res: Response | Error) {
  const fetchImpl = vi.fn(async () => {
    if (res instanceof Error) throw res
    return res
  }) as unknown as typeof fetch
  const getAccessToken = vi.fn(async () => 'tok')
  return { r: new HttpConversationRepository({ baseUrl: BASE, getAccessToken, fetchImpl }), fetchImpl, getAccessToken }
}

const turn = () => ({
  trace_id: 'a'.repeat(32),
  created_at: '2026-11-21T10:00:00Z',
  user_text: 'số dư các hũ của mình',
  assistant_text: 'Đây là số dư các hũ.',
  blocks: [validBlock('jar_summary.seven_jars')],
})

describe('phát lại hội thoại từ server', () => {
  it('GET /conversations/{id} với Bearer, trả các lượt', async () => {
    const { r, fetchImpl } = repo(new Response(JSON.stringify({ conversation_id: ID, turns: [turn()] }), { status: 200 }))
    const turns = await r.load(ID)
    expect(turns).toHaveLength(1)
    expect(turns[0]!.blocks).toHaveLength(1)
    const [url, init] = (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit]
    expect(url).toBe(`${BASE}/conversations/${ID}`)
    expect(new Headers(init.headers as HeadersInit).get('authorization')).toBe('Bearer tok')
  })

  it('hội thoại chưa có gì: turns rỗng; route chưa deploy (404) cũng coi như rỗng', async () => {
    expect(await repo(new Response(JSON.stringify({ conversation_id: ID, turns: [] }), { status: 200 })).r.load(ID)).toEqual([])
    expect(await repo(new Response('{"message":"Not Found"}', { status: 404 })).r.load(ID)).toEqual([])
  })

  it('thân sai schema: INVALID_RESPONSE; 401: UNAUTHENTICATED; mất mạng: NETWORK', async () => {
    await expect(repo(new Response('{"turns":"x"}', { status: 200 })).r.load(ID)).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
    await expect(repo(new Response('', { status: 401 })).r.load(ID)).rejects.toMatchObject({ code: 'UNAUTHENTICATED' })
    const err = await repo(new TypeError('Failed to fetch')).r.load(ID).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.code).toBe('NETWORK')
  })

  it('mã hội thoại được mã hóa trong đường dẫn', async () => {
    const { r, fetchImpl } = repo(new Response(JSON.stringify({ conversation_id: 'a/b', turns: [] }), { status: 200 }))
    await r.load('a/b')
    expect((fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0]![0]).toBe(`${BASE}/conversations/a%2Fb`)
  })

  it('repository rỗng không phát lại gì', async () => {
    expect(await new NullConversationRepository().load()).toEqual([])
  })

  it('lượt đã lưu dựng lại thành tin nhắn + khối + lịch sử gửi agent (tiêu chí: tải lại trang vẫn còn khối)', async () => {
    const { r } = repo(new Response(JSON.stringify({ conversation_id: ID, turns: [turn()] }), { status: 200 }))
    const session = new ChatSession({ agentUrl: 'https://rt.example.invalid/i', conversationId: ID, getAccessToken: async () => 't' })
    session.hydrate(await r.load(ID))
    expect(session.getSnapshot().items.map((i) => i.kind)).toEqual(['user', 'block', 'assistant'])
    expect(session.getHistory().map((m) => m.role)).toEqual(['user', 'assistant'])
  })

  it('lượt chỉ có khối (assistant_text rỗng): không sinh tin nhắn trợ lý rỗng', () => {
    const session = new ChatSession({ agentUrl: 'https://rt.example.invalid/i', conversationId: ID, getAccessToken: async () => 't' })
    session.hydrate([{ ...turn(), assistant_text: '' }])
    expect(session.getSnapshot().items.map((i) => i.kind)).toEqual(['user', 'block'])
  })
})

describe('chỉ conversation id nằm ở trình duyệt', () => {
  beforeEach(() => localStorage.clear())

  it('lưu, đọc, xóa theo người dùng; không lưu khối hay tin nhắn', () => {
    expect(loadConversationId('a@example.invalid')).toBeNull()
    saveConversationId('a@example.invalid', ID)
    expect(loadConversationId('a@example.invalid')).toBe(ID)
    expect(loadConversationId('b@example.invalid')).toBeNull()
    clearConversationId('a@example.invalid')
    expect(loadConversationId('a@example.invalid')).toBeNull()
    saveConversationId('a@example.invalid', ID)
    const all = JSON.stringify(Object.entries(localStorage))
    expect(all).not.toMatch(/jar_summary|balance_vnd/)
  })
})
