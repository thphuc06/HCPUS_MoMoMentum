import { render } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { vi } from 'vitest'
import { AuthProvider } from '@/auth/AuthProvider'
import { ConfigContext } from '@/AppContext'
import type { Config } from '@/lib/config'
import { appRoutes } from '@/router'
import { fakeAuth } from './helpers'
import { restFixture, validBlock } from './fixtures'

// Mount cả ứng dụng (router + khung + provider) với fetch giả ở mức REST/Runtime. Đây là test: mock chỉ sống ở đây và
// ở dev-mocks/, không import từ src/ sản phẩm.

export const config: Config = {
  region: 'ap-southeast-1',
  userPoolId: 'p',
  clientId: 'c',
  apiUrl: 'https://api.example.invalid',
  agentUrl: 'https://rt.example.invalid/invocations?qualifier=DEFAULT',
  replayEnabled: false,
  warmupEnabled: true,
  undoWindowSeconds: 30,
}

export type Handler = (url: string, init: RequestInit) => Response | Promise<Response>
export type Call = { url: string; init: RequestInit }

export function json(status: number, body?: unknown) {
  return new Response(body === undefined ? '' : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

export function mountApp(handler: Handler, initial = '/', cfg: Config = config) {
  const calls: Call[] = []
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
    <ConfigContext.Provider value={cfg}>
      <AuthProvider client={auth}>
        <RouterProvider router={router} />
      </AuthProvider>
    </ConfigContext.Provider>,
  )
  return { calls, router, auth }
}

// Mặc định của REST giả: các GET trả fixture hợp đồng (contracts/fixtures/rest); đường lạ thì 404.
const REST_FIXTURES: Record<string, string> = {
  '/overview': 'OverviewResponse.minh',
  '/profile': 'ProfileResponse.minh',
  '/jars': 'JarDetailResponse.an_uong',
  '/transactions': 'TransactionsResponse.page',
  '/payees': 'PayeesResponse.default',
  '/tx-types': 'TxTypesResponse.default',
  '/obligations': 'ObligationsResponse.active',
  '/credit-line': 'CreditLineResponse.default',
  '/salary-events': 'SalaryEventsResponse.pending',
  '/jar-templates': 'JarTemplatesResponse.default',
  '/resilience': 'ResilienceScoreResponse.minh',
  '/resilience/shocks': 'ShocksResponse.default',
}

export function restDefault(url: string): Response {
  const path = new URL(url).pathname
  if (path.startsWith('/forecasts/')) return json(200, validBlock('forecast_timeline.short'))
  const name = path.startsWith('/jars/') ? 'JarDetailResponse.an_uong' : REST_FIXTURES[path]
  return name ? json(200, restFixture(name)) : json(404)
}

export type Reply = Response | object | undefined
export type Routes = Record<string, Reply | ((init: RequestInit, url: URL) => Reply | Promise<Reply>)>

const wrap = (r: Reply): Response => (r instanceof Response ? r : json(200, r))

/**
 * Backend giả theo bảng "METHOD /path" -> thân phản hồi (đối tượng = 200, Response = nguyên văn, hàm = tính theo yêu cầu).
 * Không có trong bảng thì GET trả fixture mặc định; POST /confirmations trả token mờ lặp lại tool + params kèm `preview` (xem trước do "server" tính);
 * POST /actions trả biên nhận `receipt_action` của fixture. Có thể ghi đè từng cái.
 */
export function backend(routes: Routes = {}): Handler {
  return async (url, init) => {
    const u = new URL(url)
    const key = `${init.method ?? 'GET'} ${u.pathname}`
    // Khóa có dấu * ở cuối khớp theo tiền tố ("GET /jars/*").
    const hit = routes[key] ?? Object.entries(routes).find(([k]) => k.endsWith('*') && key.startsWith(k.slice(0, -1)))?.[1]
    if (hit) return wrap(typeof hit === 'function' ? await hit(init, u) : hit)
    if (key === 'POST /confirmations') {
      const b = JSON.parse(String(init.body)) as { tool: string; params: unknown }
      return json(200, {
        confirm_token: 'aaa.bbb',
        expires_at: '2026-12-10T03:02:00Z',
        ttl_seconds: 120,
        tool: b.tool,
        params: b.params,
        params_hash: 'a'.repeat(64),
        preview: { summary: 'Xem trước thao tác', changes: [{ label: 'Số dư Ăn uống', before: '380.000 ₫', after: '180.000 ₫' }] },
      })
    }
    if (key === 'POST /actions') return json(200, restFixture('ActionResponse.receipt_action'))
    if (key === 'POST /affordability') return json(200, restFixture('AffordabilityResponse.transfer'))
    if (key === 'POST /feedback') return json(200, restFixture('FeedbackResponse.default'))
    if (path0(key) === 'GET /traces') return json(200, restFixture('TraceResponse.what_if'))
    return restDefault(url)
  }
}

const path0 = (key: string) => key.replace(/^(\w+ \/[^/]+)\/.*$/, '$1')

export const bodyOf = (c: Call) => JSON.parse(String(c.init.body))
export const isWarmup = (c: Call) => c.url === config.agentUrl && bodyOf(c).forwardedProps?.warmup === true
export const runCalls = (calls: Call[]) => calls.filter((c) => c.url === config.agentUrl && !isWarmup(c))
export const callsTo = (calls: Call[], method: string, path: string) => calls.filter((c) => (c.init.method ?? 'GET') === method && new URL(c.url).pathname === path)
