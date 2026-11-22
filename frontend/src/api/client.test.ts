import { describe, expect, it, vi } from 'vitest'
import { createApiClient, REQUEST_TIMEOUT_MS, RESET_TIMEOUT_MS } from './client'
import { ApiError, ERROR_CODES, ERROR_MESSAGES, HTTP_STATUS, apiErrorFromResponse } from './errors'
import { restFixture, validBlock } from '@/test/fixtures'
import { jarsFromFixture } from '@/test/helpers'
import { AuthError } from '@/auth/types'

const BASE = 'https://api.example.invalid'
const move = { from_jar: 'giai_tri', to_jar: 'an_uong', amount_vnd: 100000 }

function json(status: number, body?: unknown): Response {
  return new Response(body === undefined ? '' : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

function setup(responses: Array<Response | Error>, getAccessToken = vi.fn(async (o?: { force?: boolean }) => (o?.force ? 'tok-moi' : 'tok-cu'))) {
  const calls: Array<{ url: string; init: RequestInit }> = []
  const fetchImpl = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} })
    const r = responses.shift()
    if (!r) throw new Error('hết phản hồi giả')
    if (r instanceof Error) throw r
    return r
  }) as unknown as typeof fetch
  return { api: createApiClient({ baseUrl: BASE, getAccessToken, fetchImpl }), calls, getAccessToken }
}

const headers = (c: { init: RequestInit }) => Object.fromEntries(new Headers(c.init.headers as HeadersInit).entries())

describe('lớp REST', () => {
  it('GET /jars: Bearer access token + traceparent, trả dữ liệu đã kiểm schema', async () => {
    const { api, calls } = setup([json(200, jarsFromFixture())])
    const r = await api.getJars()
    expect(r.jars).toHaveLength(7)
    expect(calls[0]!.url).toBe(`${BASE}/jars`)
    expect(calls[0]!.init.method).toBe('GET')
    const h = headers(calls[0]!)
    expect(h.authorization).toBe('Bearer tok-cu')
    expect(h.traceparent).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/)
  })

  it('POST /confirmations và /actions gửi đúng thân JSON', async () => {
    const receipt = validBlock('receipt.move')
    const { api, calls } = setup([
      json(200, { confirm_token: 'abc.def', expires_at: '2026-12-10T03:02:00Z', ttl_seconds: 120, tool: 'move_between_jars', params: move, params_hash: 'a'.repeat(64) }),
      json(200, receipt),
    ])
    const c = await api.createConfirmation({ tool: 'move_between_jars', params: move, params_hash: 'a'.repeat(64) })
    expect(c.confirm_token).toBe('abc.def')
    const r = await api.applyAction({ tool: 'move_between_jars', params: move, confirm_token: c.confirm_token })
    expect(r.type).toBe('receipt')
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ tool: 'move_between_jars', params: move, params_hash: 'a'.repeat(64) })
    expect(JSON.parse(String(calls[1]!.init.body))).toEqual({ tool: 'move_between_jars', params: move, confirm_token: 'abc.def' })
    expect(headers(calls[1]!)['content-type']).toBe('application/json')
  })

  it('POST /demo/reset không có thân', async () => {
    const { api, calls } = setup([json(200, { reset_at: '2026-12-10T03:00:00Z', app_date: '2026-11-21', clock_offset_days: -19, jars_count: 7, transactions_count: 40 })])
    const r = await api.resetDemo()
    expect(r.jars_count).toBe(7)
    expect(calls[0]!.init.body).toBeUndefined()
  })

  it('mã lỗi máy đọc được thành thông báo tiếng Việt, kèm trace_id', async () => {
    const { api } = setup([json(403, { error: { code: 'TOKEN_EXPIRED', message: 'Token expired', trace_id: 'ab12' } })])
    const err = await api.applyAction({ tool: 'move_between_jars', params: move, confirm_token: 'x.y' }).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.code).toBe('TOKEN_EXPIRED')
    expect(err.status).toBe(403)
    expect(err.traceId).toBe('ab12')
    expect(err.message).toBe(ERROR_MESSAGES.TOKEN_EXPIRED)
    expect(err.message).toMatch(/hết hạn/)
  })

  it('401: làm mới token (force) rồi thử lại một lần', async () => {
    const { api, calls, getAccessToken } = setup([json(401), json(200, jarsFromFixture())])
    await api.getJars()
    expect(calls).toHaveLength(2)
    expect(headers(calls[0]!).authorization).toBe('Bearer tok-cu')
    expect(headers(calls[1]!).authorization).toBe('Bearer tok-moi')
    expect(getAccessToken).toHaveBeenLastCalledWith({ force: true })
  })

  it('401 hai lần: UNAUTHENTICATED, không thử lần ba', async () => {
    const { api, calls } = setup([json(401), json(401)])
    const err = await api.getJars().catch((e) => e)
    expect(err.code).toBe('UNAUTHENTICATED')
    expect(calls).toHaveLength(2)
  })

  it('hết phiên khi lấy token: SESSION_EXPIRED, không gọi mạng', async () => {
    const getAccessToken = vi.fn(async () => {
      throw new AuthError('SESSION_EXPIRED')
    })
    const { api, calls } = setup([], getAccessToken)
    const err = await api.getJars().catch((e) => e)
    expect(err.code).toBe('SESSION_EXPIRED')
    expect(calls).toHaveLength(0)
  })

  it('mất mạng: NETWORK, có thể thử lại', async () => {
    const { api } = setup([new TypeError('Failed to fetch')])
    const err = await api.getJars().catch((e) => e)
    expect(err.code).toBe('NETWORK')
    expect(err.retryable).toBe(true)
  })

  it('thân 200 sai schema: INVALID_RESPONSE', async () => {
    const { api } = setup([json(200, { jars: 'khong-phai-mang' })])
    const err = await api.getJars().catch((e) => e)
    expect(err.code).toBe('INVALID_RESPONSE')
  })

  it('503 thân rỗng: DATABASE_UNAVAILABLE (Aurora đang thức dậy), thử lại được', async () => {
    const { api } = setup([json(503)])
    const err = await api.getJars().catch((e) => e)
    expect(err.code).toBe('DATABASE_UNAVAILABLE')
    expect(err.retryable).toBe(true)
  })
})

describe('hết giờ chờ', () => {
  // fetch treo mãi (chỉ kết thúc khi bị hủy bằng AbortSignal): GET hết giờ ở 40 giây, đặt lại demo được chờ tới 60 giây.
  const hanging = (calls: Array<number>) =>
    vi.fn((_url: RequestInfo | URL, init?: RequestInit) => {
      calls.push(Date.now())
      return new Promise<Response>((_res, rej) => init?.signal?.addEventListener('abort', () => rej(new DOMException('aborted', 'AbortError'))))
    }) as unknown as typeof fetch

  it('GET treo quá 40 giây thì báo TIMEOUT (có thể thử lại); POST /demo/reset được chờ lâu hơn (60 giây)', async () => {
    vi.useFakeTimers()
    try {
      const calls: number[] = []
      const api = createApiClient({ baseUrl: BASE, getAccessToken: async () => 'tok', fetchImpl: hanging(calls) })
      const get = api.getJars().catch((e) => e)
      await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS - 1)
      let settled = false
      void get.then(() => (settled = true))
      await vi.advanceTimersByTimeAsync(0)
      expect(settled).toBe(false)
      await vi.advanceTimersByTimeAsync(2)
      const err = await get
      expect(err).toBeInstanceOf(ApiError)
      expect(err.code).toBe('TIMEOUT')
      expect(err.retryable).toBe(true)
      expect(err.message).toMatch(/Hoạt động/) // nhắc kiểm tra trước khi ghi lại

      const reset = api.resetDemo().catch((e) => e)
      await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS + 5_000) // quá 40 giây mà reset vẫn đang chờ
      let resetSettled = false
      void reset.then(() => (resetSettled = true))
      await vi.advanceTimersByTimeAsync(0)
      expect(resetSettled).toBe(false)
      await vi.advanceTimersByTimeAsync(RESET_TIMEOUT_MS)
      expect((await reset).code).toBe('TIMEOUT')
    } finally {
      vi.useRealTimers()
    }
  })

  it('lỗi mạng thường vẫn là NETWORK', async () => {
    const { api } = setup([new TypeError('Failed to fetch')])
    expect((await api.getJars().catch((e) => e)).code).toBe('NETWORK')
  })
})

describe('REST phase 3', () => {
  it('POST /affordability gửi thân yêu cầu và trả khối affordability_card đã kiểm schema', async () => {
    const req = restFixture('AffordabilityRequest.transfer') as { amount_vnd: number; label: string }
    const { api, calls } = setup([json(200, restFixture('AffordabilityResponse.transfer'))])
    const r = await api.checkAffordability(req)
    expect(r.type).toBe('affordability_card')
    expect(calls[0]!.url).toBe(`${BASE}/affordability`)
    expect(calls[0]!.init.method).toBe('POST')
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual(req)
  })

  it('GET /traces/{id}: mã trace được mã hóa trong đường dẫn; trả khối explain và chi tiết', async () => {
    const { api, calls } = setup([json(200, restFixture('TraceResponse.what_if'))])
    const r = await api.getTrace('8f3a21c94b7e4d0aa1c25e6f7b8c9d01')
    expect(calls[0]!.url).toBe(`${BASE}/traces/8f3a21c94b7e4d0aa1c25e6f7b8c9d01`)
    expect(calls[0]!.init.method).toBe('GET')
    expect(r.explain.type).toBe('explain')
    expect(r.detail.token_usage.model_calls).toBeGreaterThan(0)
  })

  it('GET /traces: 404 TRACE_NOT_FOUND là lỗi có thông báo tiếng Việt', async () => {
    const { api } = setup([json(404, { error: { code: 'TRACE_NOT_FOUND', message: 'x' } })])
    const e = await api.getTrace('abc').catch((x) => x)
    expect(e).toBeInstanceOf(ApiError)
    expect(e.code).toBe('TRACE_NOT_FOUND')
    expect(e.message).toBe(ERROR_MESSAGES.TRACE_NOT_FOUND)
  })

  it('POST /feedback gửi đúng thân JSON, không có Authorization nào khác ngoài Bearer', async () => {
    const req = restFixture('FeedbackRequest.accepted')
    const { api, calls } = setup([json(200, restFixture('FeedbackResponse.default'))])
    const r = await api.submitFeedback(req as never)
    expect(r.decision).toBe('accepted')
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual(req)
    expect(headers(calls[0]!).authorization).toBe('Bearer tok-cu')
  })

  it('410 OFFER_EXPIRED giữ mã riêng (khác TOKEN_EXPIRED)', async () => {
    const { api } = setup([json(410, { error: { code: 'OFFER_EXPIRED', message: 'x' } })])
    const e = await api.applyAction({ tool: 'move_between_jars', params: move }).catch((x) => x)
    expect(e.code).toBe('OFFER_EXPIRED')
    expect(e.status).toBe(410)
  })
})

describe('bảng mã lỗi', () => {
  it('mọi mã đều có thông báo tiếng Việt và HTTP status', () => {
    for (const code of ERROR_CODES) {
      expect(ERROR_MESSAGES[code]).toMatch(/[a-zàáảãạăâđêôơư]/i)
      expect(HTTP_STATUS[code]).toBeGreaterThanOrEqual(400)
    }
  })
  it('thân lạ rơi về mã theo HTTP status', () => {
    expect(apiErrorFromResponse(500, { error: { code: 'MA_LA', message: 'x' } }).code).toBe('INTERNAL_ERROR')
    expect(apiErrorFromResponse(403, undefined).code).toBe('FORBIDDEN')
    expect(apiErrorFromResponse(429, undefined).code).toBe('RATE_LIMITED')
  })
})
