import type { ZodType } from 'zod'
import { newTraceparent } from '@/lib/ids'
import { AuthError } from '@/auth/types'
import { ApiError, apiErrorFromResponse } from './errors'
import {
  ActionResponse,
  CancelConfirmationResponse,
  ConfirmationResponse,
  CreditLineResponse,
  ForecastResponse,
  JarDetailResponse,
  JarTemplatesResponse,
  JarsResponse,
  ObligationsResponse,
  OverviewResponse,
  PayeesResponse,
  ProfileResponse,
  ResetResponse,
  SalaryEventsResponse,
  TransactionsResponse,
  TxTypesResponse,
  type ActionRequest,
  type CancelConfirmationRequest,
  type ConfirmationRequest,
  type TransactionQuery,
} from './schemas'

export type ApiClientDeps = {
  baseUrl: string
  /** Trả access token còn hạn; `force` ép làm mới (dùng khi gặp 401). */
  getAccessToken: (opts?: { force?: boolean }) => Promise<string>
  fetchImpl?: typeof fetch
}

export type ApiClient = {
  getJars(): Promise<JarsResponse>
  getOverview(): Promise<OverviewResponse>
  getProfile(): Promise<ProfileResponse>
  getJar(jarCode: string): Promise<JarDetailResponse>
  getForecast(jarCode: string): Promise<ForecastResponse>
  listTransactions(query?: TransactionQuery): Promise<TransactionsResponse>
  listTxTypes(): Promise<TxTypesResponse>
  listPayees(): Promise<PayeesResponse>
  listObligations(): Promise<ObligationsResponse>
  getCreditLine(): Promise<CreditLineResponse>
  listSalaryEvents(): Promise<SalaryEventsResponse>
  listJarTemplates(): Promise<JarTemplatesResponse>
  createConfirmation(req: ConfirmationRequest): Promise<ConfirmationResponse>
  /** Ghi việc người dùng bấm "Không" với một đề nghị trong chat (server lưu `cancelled`). */
  cancelConfirmation(req: CancelConfirmationRequest): Promise<CancelConfirmationResponse>
  applyAction(req: ActionRequest): Promise<ActionResponse>
  resetDemo(): Promise<ResetResponse>
}

async function readBody(res: Response): Promise<unknown> {
  const text = await res.text()
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

/**
 * Lớp gọi REST `yofina-api`: gửi `Authorization: Bearer <access token>` và `traceparent`; mã lỗi
 * máy đọc được đổi thành ApiError với thông báo tiếng Việt. Gặp 401 thì làm mới token và thử lại một lần
 * (an toàn vì 401 của authorizer xảy ra trước khi Lambda chạy).
 */
export function createApiClient(deps: ApiClientDeps): ApiClient {
  const doFetch = deps.fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a))

  async function once(method: string, path: string, body: unknown, force: boolean): Promise<Response> {
    const token = await deps.getAccessToken({ force })
    const headers: Record<string, string> = {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
      traceparent: newTraceparent().header,
    }
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    try {
      return await doFetch(`${deps.baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      })
    } catch {
      throw new ApiError('NETWORK', 0)
    }
  }

  async function call<T>(method: string, path: string, schema: ZodType<T>, body?: unknown): Promise<T> {
    let res: Response
    try {
      res = await once(method, path, body, false)
      if (res.status === 401) res = await once(method, path, body, true)
    } catch (e) {
      if (e instanceof AuthError) throw new ApiError('SESSION_EXPIRED', 401)
      throw e
    }
    const data = await readBody(res)
    if (!res.ok) throw apiErrorFromResponse(res.status, data)
    const parsed = schema.safeParse(data)
    if (!parsed.success) throw new ApiError('INVALID_RESPONSE', res.status)
    return parsed.data
  }

  const enc = encodeURIComponent
  return {
    getJars: () => call('GET', '/jars', JarsResponse),
    getOverview: () => call('GET', '/overview', OverviewResponse),
    getProfile: () => call('GET', '/profile', ProfileResponse),
    getJar: (code) => call('GET', `/jars/${enc(code)}`, JarDetailResponse),
    getForecast: (code) => call('GET', `/forecasts/${enc(code)}`, ForecastResponse),
    listTransactions: (q = {}) => {
      const qs = new URLSearchParams()
      if (q.jar) qs.set('jar', q.jar)
      if (q.kind) qs.set('kind', q.kind)
      if (q.needsReview) qs.set('needs_review', 'true')
      if (q.limit) qs.set('limit', String(q.limit))
      if (q.cursor) qs.set('cursor', q.cursor)
      const tail = qs.toString()
      return call('GET', `/transactions${tail ? `?${tail}` : ''}`, TransactionsResponse)
    },
    listTxTypes: () => call('GET', '/tx-types', TxTypesResponse),
    listPayees: () => call('GET', '/payees', PayeesResponse),
    listObligations: () => call('GET', '/obligations', ObligationsResponse),
    getCreditLine: () => call('GET', '/credit-line', CreditLineResponse),
    listSalaryEvents: () => call('GET', '/salary-events', SalaryEventsResponse),
    listJarTemplates: () => call('GET', '/jar-templates', JarTemplatesResponse),
    createConfirmation: (req) => call('POST', '/confirmations', ConfirmationResponse, req),
    cancelConfirmation: (req) => call('POST', '/confirmations/cancel', CancelConfirmationResponse, req),
    applyAction: (req) => call('POST', '/actions', ActionResponse, req),
    resetDemo: () => call('POST', '/demo/reset', ResetResponse),
  }
}
