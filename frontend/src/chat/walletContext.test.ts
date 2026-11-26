import { describe, expect, it, vi } from 'vitest'
import { OverviewResponse } from '@/api/schemas'
import { restFixture } from '@/test/fixtures'
import { runFinished, runStarted, sseResponse, textMessage } from '@/test/sse'
import { ChatSession } from './session'
import { WALLET_CONTEXT, walletContext } from './walletContext'

const CONVERSATION = '11111111-2222-4333-8444-555555555555'
const URL = 'https://runtime.example.invalid/invocations?qualifier=DEFAULT'
const overview = () => OverviewResponse.parse(restFixture('OverviewResponse.minh'))

describe('walletContext: danh sách hũ gửi kèm lượt chat (#39)', () => {
  it('mã, tên, kind, purpose của hũ người dùng và ngày mô phỏng; không số dư, không hũ hệ thống', () => {
    const data = overview()
    const ctx = walletContext({ status: 'ready', refreshing: false, data })
    expect(ctx?.description).toBe(WALLET_CONTEXT)
    const value = JSON.parse(ctx!.value) as { app_date: string; jars: Array<Record<string, string>> }
    expect(value.app_date).toBe(data.app_date)
    expect(value.jars.map((j) => j.code)).toEqual(data.jars.map((j) => j.code))
    for (const j of value.jars) expect(Object.keys(j).sort()).toEqual(expect.arrayContaining(['code', 'kind', 'name']))
    expect(ctx!.value).not.toMatch(/balance|split_percent|goal_vnd/)
    expect(value.jars.some((j) => j.kind === 'system')).toBe(false)
  })

  it('không gửi khi dữ liệu chưa chắc đúng: đang tải, đang tải lại sau một lần ghi, lỗi, không có hũ', () => {
    const data = overview()
    expect(walletContext(null)).toBeNull()
    expect(walletContext({ status: 'loading', data: null })).toBeNull()
    expect(walletContext({ status: 'ready', refreshing: true, data })).toBeNull()
    expect(walletContext({ status: 'error', data })).toBeNull()
    expect(walletContext({ status: 'ready', refreshing: false, data: { ...data, jars: [] } })).toBeNull()
  })
})

describe('ChatSession: context của lượt', () => {
  function session(getContext?: () => Array<{ description: string; value: string }>) {
    const bodies: Array<Record<string, unknown>> = []
    const fetchImpl = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      bodies.push(JSON.parse(String(init?.body)) as Record<string, unknown>)
      return sseResponse([runStarted(), ...textMessage('m1', 'Chào bạn.'), runFinished()])
    }) as unknown as typeof fetch
    const s = new ChatSession({ agentUrl: URL, conversationId: CONVERSATION, getAccessToken: async () => 'tok', fetchImpl, getContext })
    return { s, bodies }
  }

  it('gửi mục danh sách hũ trong context, đọc lại mỗi lượt', async () => {
    const entries = [[{ description: WALLET_CONTEXT, value: '{"a":1}' }], []]
    const { s, bodies } = session(() => entries.shift() ?? [])
    await s.send('chào')
    await s.send('cảm ơn')
    expect(bodies[0]!.context).toEqual([{ description: WALLET_CONTEXT, value: '{"a":1}' }])
    expect(bodies[1]!.context).toEqual([])
  })

  it('không có nguồn context thì context rỗng như trước', async () => {
    const { s, bodies } = session()
    await s.send('chào')
    expect(bodies[0]!.context).toEqual([])
  })
})
