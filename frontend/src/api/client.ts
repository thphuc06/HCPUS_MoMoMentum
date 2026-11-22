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
  INGEST_TOOL_NAMES,
  type ActionRequest,
  type CancelConfirmationRequest,
  type ConfirmationRequest,
  type TransactionQuery,
} from './schemas'
import {
  IngestJobListResponse,
  IngestJobResponse,
  IngestRowJarResponse,
  IngestUploadResponse,
  type IngestRowJarRequest,
  type IngestUploadRequest,
} from './ingestSchemas'

/** Thời gian chờ mỗi lời gọi: dài hơn trần 30 giây của HTTP API nên lỗi hết giờ ở server luôn tới trước. */
export const REQUEST_TIMEOUT_MS = 40_000
/** `POST /demo/reset` mất 2,6 đến 8 giây (sinh lại dữ liệu và tính dự báo đồng bộ): cho dư địa rộng hơn. */
export const RESET_TIMEOUT_MS = 60_000

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
  // ---- nạp dữ liệu (phase 5, F6): REST `/ingest/*` của Lambda ingest
  /** Xin presigned POST để tải tệp thẳng lên S3 và tạo job. */
  createIngestUpload(req: IngestUploadRequest): Promise<IngestUploadResponse>
  getIngestJob(jobId: string): Promise<IngestJobResponse>
  /** Đổi hũ ĐỀ XUẤT của một dòng chi (không ghi sổ cái, không token). `POST .../jar` vì CORS của HTTP API chỉ cho GET, POST, OPTIONS. */
  setIngestRowJar(rowId: string, req: IngestRowJarRequest): Promise<IngestRowJarResponse>
  /** Các lần nạp gần đây (mới nhất trước), để quay lại một lần đang chờ duyệt. */
  listIngestJobs(limit?: number): Promise<IngestJobListResponse>
  /** Xin token + xem trước cho `confirm_rows` (`POST /ingest/confirmations`, cùng hình dạng `POST /confirmations`). */
  createIngestConfirmation(req: ConfirmationRequest): Promise<ConfirmationResponse>
  /** Chốt các dòng bằng token (`POST /ingest/actions`); trả `receipt_action` kèm `coverage_change`. */
  applyIngestAction(req: ActionRequest): Promise<ActionResponse>
}

/**
 * `confirm_rows` chỉ đi qua cặp endpoint của Lambda `ingest`; ledger từ chối nó (PARAMS_INVALID). Chọn theo `tool` ở MỘT nơi để
 * mọi nơi gọi (màn Nạp dữ liệu, khối `confirm_action` trong chat) đều đúng mà không phải tự biết.
 */
const isIngestTool = (tool: string) => (INGEST_TOOL_NAMES as readonly string[]).includes(tool)
const confirmPath = (tool: string) => (isIngestTool(tool) ? '/ingest/confirmations' : '/confirmations')
const actionPath = (tool: string) => (isIngestTool(tool) ? '/ingest/actions' : '/actions')

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

  async function once(method: string, path: string, body: unknown, force: boolean, timeoutMs: number): Promise<Response> {
    const token = await deps.getAccessToken({ force })
    const headers: Record<string, string> = {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
      traceparent: newTraceparent().header,
    }
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    const ctrl = new AbortController()
    const timer = setTimeout(() => ctrl.abort(), timeoutMs)
    try {
      return await doFetch(`${deps.baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: ctrl.signal,
      })
    } catch {
      throw new ApiError(ctrl.signal.aborted ? 'TIMEOUT' : 'NETWORK', 0)
    } finally {
      clearTimeout(timer)
    }
  }

  async function call<T>(method: string, path: string, schema: ZodType<T>, body?: unknown, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
    let res: Response
    try {
      res = await once(method, path, body, false, timeoutMs)
      if (res.status === 401) res = await once(method, path, body, true, timeoutMs)
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
    createConfirmation: (req) => call('POST', confirmPath(req.tool), ConfirmationResponse, req),
    cancelConfirmation: (req) => call('POST', '/confirmations/cancel', CancelConfirmationResponse, req),
    applyAction: (req) => call('POST', actionPath(req.tool), ActionResponse, req),
    resetDemo: () => call('POST', '/demo/reset', ResetResponse, undefined, RESET_TIMEOUT_MS),
    createIngestUpload: (req) => call('POST', '/ingest/uploads', IngestUploadResponse, req),
    listIngestJobs: (limit) => call('GET', `/ingest/jobs${limit ? `?limit=${limit}` : ''}`, IngestJobListResponse),
    getIngestJob: (id) => call('GET', `/ingest/jobs/${enc(id)}`, IngestJobResponse),
    setIngestRowJar: (id, req) => call('POST', `/ingest/rows/${enc(id)}/jar`, IngestRowJarResponse, req),
    createIngestConfirmation: (req) => call('POST', '/ingest/confirmations', ConfirmationResponse, req),
    applyIngestAction: (req) => call('POST', '/ingest/actions', ActionResponse, req),
  }
}
