import { parse } from 'yaml'
import type { ZodObject, ZodType } from 'zod'
import { describe, expect, it } from 'vitest'
import { ERROR_CODES, HTTP_STATUS } from './errors'
import { ConversationResponse, Resolution, StoredTurn } from '@/chat/repository'
import {
  ActionRequest,
  ActionResponse,
  AffordabilityRequest,
  AffordabilityResponse,
  CancelConfirmationRequest,
  CancelConfirmationResponse,
  ConfirmationRequest,
  ConfirmationResponse,
  CreditLine,
  CreditLineResponse,
  FeedbackRequest,
  FeedbackResponse,
  FeeLine,
  ForecastMeta,
  JarDetailResponse,
  JarFull,
  JarTemplate,
  JarTemplatesResponse,
  JarsResponse,
  NextPayday,
  Obligation,
  ObligationsResponse,
  OverviewResponse,
  Payee,
  PayeesResponse,
  Profile,
  ProfileResponse,
  ResetResponse,
  SalaryEvent,
  SalaryEventsResponse,
  Transaction,
  TraceResponse,
  TransactionsResponse,
  TxType,
  TxTypesResponse,
  INGEST_TOOL_NAMES,
  TOOL_NAMES,
} from './schemas'
import { createApiClient } from './client'
import { IngestJobListResponse, IngestJobResponse, IngestJobSummary, IngestRowJarRequest, IngestRowJarResponse, IngestUploadRequest, IngestUploadResponse } from './ingestSchemas'
import { IngestReviewBlock, CoverageChangeBlock } from '@/contracts/blocks'
import { jarsFromFixture } from '@/test/helpers'
import {
  BehaviorProfileResponse,
  DataDeletion,
  DeleteDataConfirmationRequest,
  DeleteDataConfirmationResponse,
  DeleteDataRequest,
  DeletionStep,
  MemoryClearResponse,
  MemoryListResponse,
  MemoryRecord,
  MemoryRecordDeleteResponse,
  Nudge,
  NudgeFeedbackRequest,
  NudgeFeedbackResponse,
  NudgeTodayResponse,
  OpsDayModelCalls,
  OpsModelDayCalls,
  OpsSummaryResponse,
  OpsToolCall,
  OpsTraceDetail,
  OpsTraceListResponse,
  OpsTraceSummary,
  parseNudgeCard,
} from './phase5Schemas'
import { restFixtureEntries, restInvalidEntries } from '@/test/fixtures'

// Đối chiếu code frontend với contracts/rest/openapi.yaml (nguồn duy nhất của hợp đồng REST).
const raw = Object.values(
  import.meta.glob('../../../contracts/rest/openapi.yaml', { eager: true, query: '?raw', import: 'default' }),
)[0] as string
const ledgerResults = Object.values(
  import.meta.glob('../../../contracts/tools/ledger.results.schema.json', { eager: true, import: 'default' }),
)[0] as { $defs: Record<string, { required?: string[] }> }
const spec = parse(raw) as {
  paths: Record<string, Record<string, { operationId: string }>>
  components: {
    schemas: Record<string, { required?: string[]; enum?: string[]; 'x-http-status'?: Record<string, number>; properties?: Record<string, unknown>; oneOf?: Array<{ properties: { status: { const?: string; enum?: string[] } } }> }>
  }
}
const schemas = spec.components.schemas

describe('khớp openapi.yaml', () => {
  it('có các endpoint frontend gọi, đúng method và operationId', () => {
    const expected: Array<[string, string, string]> = [
      ['/jars', 'get', 'getJars'],
      ['/overview', 'get', 'getOverview'],
      ['/profile', 'get', 'getProfile'],
      ['/jars/{jar_code}', 'get', 'getJar'],
      ['/forecasts/{jar_code}', 'get', 'getForecast'],
      ['/transactions', 'get', 'listTransactions'],
      ['/tx-types', 'get', 'listTxTypes'],
      ['/payees', 'get', 'listPayees'],
      ['/obligations', 'get', 'listObligations'],
      ['/credit-line', 'get', 'getCreditLine'],
      ['/salary-events', 'get', 'listSalaryEvents'],
      ['/jar-templates', 'get', 'listJarTemplates'],
      ['/confirmations', 'post', 'createConfirmation'],
      ['/confirmations/cancel', 'post', 'cancelConfirmation'],
      ['/actions', 'post', 'applyAction'],
      ['/demo/reset', 'post', 'resetDemo'],
      ['/conversations/{conversation_id}', 'get', 'getConversation'],
      ['/affordability', 'post', 'checkAffordability'],
      ['/traces/{trace_id}', 'get', 'getTrace'],
      ['/feedback', 'post', 'submitFeedback'],
      ['/ingest/uploads', 'post', 'createIngestUpload'],
      ['/ingest/jobs', 'get', 'listIngestJobs'],
      ['/ingest/jobs/{job_id}', 'get', 'getIngestJob'],
      ['/ingest/rows/{row_id}/jar', 'post', 'setIngestRowJar'],
      ['/ingest/confirmations', 'post', 'createIngestConfirmation'],
      ['/ingest/actions', 'post', 'applyIngestAction'],
      // phase 5 (F7, quyền riêng tư, trace)
      ['/profile/behavior', 'get', 'getBehaviorProfile'],
      ['/nudges/today', 'get', 'getTodayNudge'],
      ['/nudges/{nudge_id}/feedback', 'post', 'submitNudgeFeedback'],
      ['/memory', 'get', 'listMemory'],
      ['/memory', 'delete', 'clearMemory'],
      ['/memory/{record_id}', 'delete', 'deleteMemoryRecord'],
      ['/me/delete-data/confirmations', 'post', 'createDeleteDataConfirmation'],
      ['/me/delete-data', 'post', 'deleteMyData'],
      ['/ops/traces', 'get', 'listOpsTraces'],
      ['/ops/traces/{trace_id}', 'get', 'getOpsTrace'],
      ['/ops/summary', 'get', 'getOpsSummary'],
    ]
    for (const [path, method, op] of expected) expect(spec.paths[path]?.[method]?.operationId, `${method} ${path}`).toBe(op)
  })

  it('ErrorCode: cùng danh sách và cùng HTTP status (kể cả 9 mã phase 2)', () => {
    expect([...ERROR_CODES].sort()).toEqual([...schemas.ErrorCode!.enum!].sort())
    expect(HTTP_STATUS).toEqual(schemas.ErrorCode!['x-http-status'])
  })

  it('ToolName: đủ bảy tool ghi của ledger; confirm_rows (phase 5) chỉ ở IngestToolName', () => {
    expect([...TOOL_NAMES].sort()).toEqual([...(schemas.ToolName!.enum ?? [])].sort())
    expect(TOOL_NAMES).not.toContain('confirm_rows')
    expect([...INGEST_TOOL_NAMES]).toEqual(schemas.IngestToolName!.enum)
  })

  it('hợp đồng không có PATCH nào (CORS của HTTP API chung chỉ cho GET, POST, OPTIONS)', () => {
    for (const [path, item] of Object.entries(spec.paths)) expect(Object.keys(item), path).not.toContain('patch')
  })

  // Trường bắt buộc của hợp đồng phải có trong Zod; trường Zod bắt buộc phải nằm trong `required` của hợp đồng (frontend
  // không đòi thứ server được phép bỏ).
  const pairs: Array<[string, ZodObject<Record<string, ZodType>>, string[]]> = [
    ['JarsResponse', JarsResponse, schemas.JarsResponse!.required!],
    ['ResetResponse', ResetResponse, schemas.ResetResponse!.required!],
    ['Profile', Profile, schemas.Profile!.required!],
    ['ProfileResponse', ProfileResponse, schemas.ProfileResponse!.required!],
    ['JarFull', JarFull, schemas.JarFull!.required!],
    ['NextPayday', NextPayday, schemas.NextPayday!.required!],
    ['ForecastMeta', ForecastMeta, schemas.ForecastMeta!.required!],
    ['OverviewResponse', OverviewResponse, schemas.OverviewResponse!.required!],
    ['JarDetailResponse', JarDetailResponse, schemas.JarDetailResponse!.required!],
    ['TransactionsResponse', TransactionsResponse, schemas.TransactionsResponse!.required!],
    ['TxType', TxType, schemas.TxType!.required!],
    ['ObligationsResponse', ObligationsResponse, schemas.ObligationsResponse!.required!],
    ['FeeLine', FeeLine, schemas.FeeLine!.required!],
    ['CreditLineResponse', CreditLineResponse, schemas.CreditLineResponse!.required!],
    ['JarTemplate', JarTemplate, schemas.JarTemplate!.required!],
    ['ConfirmationResponse', ConfirmationResponse, schemas.ConfirmationResponse!.required!],
    ['CancelConfirmationRequest', CancelConfirmationRequest, schemas.CancelConfirmationRequest!.required!],
    ['CancelConfirmationResponse', CancelConfirmationResponse, schemas.CancelConfirmationResponse!.required!],
    ['AffordabilityRequest', AffordabilityRequest, schemas.AffordabilityRequest!.required!],
    ['FeedbackRequest', FeedbackRequest, schemas.FeedbackRequest!.required!],
    ['FeedbackResponse', FeedbackResponse, schemas.FeedbackResponse!.required!],
    ['IngestUploadRequest', IngestUploadRequest, schemas.IngestUploadRequest!.required!],
    ['IngestUploadResponse', IngestUploadResponse, schemas.IngestUploadResponse!.required!],
    ['IngestJobResponse', IngestJobResponse, schemas.IngestJobResponse!.required!],
    ['IngestJobSummary', IngestJobSummary, schemas.IngestJobSummary!.required!],
    ['IngestJobListResponse', IngestJobListResponse, schemas.IngestJobListResponse!.required!],
    ['IngestRowJarRequest', IngestRowJarRequest, schemas.IngestRowJarRequest!.required!],
    ['IngestRowJarResponse', IngestRowJarResponse, schemas.IngestRowJarResponse!.required!],
    ['Transaction', Transaction, ledgerResults.$defs.Transaction!.required!],
    ['Obligation', Obligation, ledgerResults.$defs.Obligation!.required!],
    ['CreditLine', CreditLine, ledgerResults.$defs.CreditLine!.required!],
    ['Payee', Payee, ledgerResults.$defs.Payee!.required!],
    ['SalaryEvent', SalaryEvent, ledgerResults.$defs.SalaryEvent!.required!],
    ['Nudge', Nudge, schemas.Nudge!.required!],
    ['NudgeTodayResponse', NudgeTodayResponse, schemas.NudgeTodayResponse!.required!],
    ['NudgeFeedbackRequest', NudgeFeedbackRequest, schemas.NudgeFeedbackRequest!.required!],
    ['NudgeFeedbackResponse', NudgeFeedbackResponse, schemas.NudgeFeedbackResponse!.required!],
    ['MemoryRecord', MemoryRecord, schemas.MemoryRecord!.required!],
    ['MemoryListResponse', MemoryListResponse, schemas.MemoryListResponse!.required!],
    ['MemoryRecordDeleteResponse', MemoryRecordDeleteResponse, schemas.MemoryRecordDeleteResponse!.required!],
    ['MemoryClearResponse', MemoryClearResponse, schemas.MemoryClearResponse!.required!],
    ['DeleteDataConfirmationRequest', DeleteDataConfirmationRequest, schemas.DeleteDataConfirmationRequest!.required!],
    ['DeleteDataConfirmationResponse', DeleteDataConfirmationResponse, schemas.ConfirmationResponse!.required!],
    ['DeleteDataRequest', DeleteDataRequest, schemas.DeleteDataRequest!.required!],
    ['DeletionStep', DeletionStep, schemas.DeletionStep!.required!],
    ['DataDeletion', DataDeletion, schemas.DataDeletion!.required!],
    ['OpsTraceSummary', OpsTraceSummary, schemas.OpsTraceSummary!.required!],
    ['OpsTraceListResponse', OpsTraceListResponse, schemas.OpsTraceListResponse!.required!],
    ['OpsToolCall', OpsToolCall, schemas.OpsToolCall!.required!],
    ['OpsTraceDetail', OpsTraceDetail, schemas.OpsTraceDetail!.required!],
    ['OpsDayModelCalls', OpsDayModelCalls, schemas.OpsDayModelCalls!.required!],
    ['OpsModelDayCalls', OpsModelDayCalls, schemas.OpsModelDayCalls!.required!],
    ['OpsSummaryResponse', OpsSummaryResponse, schemas.OpsSummaryResponse!.required!],
  ]
  for (const [name, zod, required] of pairs) {
    it(`${name}: trường bắt buộc khớp hợp đồng`, () => {
      const shape = zod.shape
      for (const k of required) expect(Object.keys(shape), `${name}.${k}`).toContain(k)
      const zodRequired = Object.keys(shape).filter((k) => !shape[k]!.isOptional())
      for (const k of zodRequired) expect(required, `${name}.${k} đang bắt buộc ở Zod`).toContain(k)
    })
  }

  it('JarsResponse parse được fixture phase 1', () => {
    expect(JarsResponse.safeParse(jarsFromFixture()).success).toBe(true)
  })

  it('trạng thái đề nghị: Resolution khớp ConfirmResolution; hai yêu cầu nhận conversation_id + confirm_block_id', () => {
    const statuses = schemas.ConfirmResolution!.oneOf!.flatMap((o) => o.properties.status.enum ?? [o.properties.status.const!])
    expect(statuses.sort()).toEqual([...Resolution.shape.status.options].sort())
    for (const name of ['ActionRequest', 'ConfirmationRequest'] as const) {
      const props = Object.keys(schemas[name]!.properties!)
      expect(props).toEqual(expect.arrayContaining(['conversation_id', 'confirm_block_id']))
    }
    expect(Object.keys(ActionRequest.shape)).toEqual(expect.arrayContaining(['conversation_id', 'confirm_block_id']))
    expect(Object.keys(ConfirmationRequest.shape)).toEqual(expect.arrayContaining(['conversation_id', 'confirm_block_id']))
  })

  it('ConversationResponse và ConversationTurn (phát lại hội thoại) có đúng các trường bắt buộc', () => {
    expect(Object.keys(ConversationResponse.shape).sort()).toEqual([...schemas.ConversationResponse!.required!].sort())
    expect(Object.keys(StoredTurn.shape).sort()).toEqual([...schemas.ConversationTurn!.required!].sort())
  })

  it('lượt gọi model theo ngày: Zod có đủ mọi trường của hợp đồng (by_model không bị bỏ khi parse)', () => {
    expect(Object.keys(OpsDayModelCalls.shape).sort()).toEqual(Object.keys(schemas.OpsDayModelCalls!.properties!).sort())
    expect(Object.keys(OpsModelDayCalls.shape).sort()).toEqual(Object.keys(schemas.OpsModelDayCalls!.properties!).sort())
  })
})

// Mọi fixture REST của hợp đồng đi qua Zod của frontend: hợp lệ thì parse được, sai thì bị từ chối.
describe('fixture REST của hợp đồng', () => {
  const byName: Record<string, ZodType> = {
    OverviewResponse,
    JarDetailResponse,
    TransactionsResponse,
    ObligationsResponse,
    CreditLineResponse,
    ProfileResponse,
    PayeesResponse,
    TxTypesResponse,
    JarTemplatesResponse,
    SalaryEventsResponse,
    ConfirmationRequest,
    ActionRequest,
    IngestConfirmationRequest: ConfirmationRequest,
    IngestActionRequest: ActionRequest,
    ActionResponse,
    AffordabilityRequest,
    AffordabilityResponse,
    TraceResponse,
    FeedbackRequest,
    FeedbackResponse,
    IngestUploadRequest,
    IngestUploadResponse,
    IngestJobResponse,
    IngestJobListResponse,
    IngestRowJarRequest,
    IngestRowJarResponse,
    BehaviorProfileResponse,
    NudgeTodayResponse,
    NudgeFeedbackRequest,
    NudgeFeedbackResponse,
    MemoryListResponse,
    MemoryRecordDeleteResponse,
    MemoryClearResponse,
    DeleteDataConfirmationRequest,
    DeleteDataRequest,
    DataDeletion,
    OpsTraceListResponse,
    OpsTraceDetail,
    OpsSummaryResponse,
  }

  for (const [file, body] of restFixtureEntries()) {
    const kind = file.split('.')[0]!
    if (!byName[kind]) continue
    it(`hợp lệ: ${file}`, () => {
      const r = byName[kind]!.safeParse(body)
      expect(r.success, r.success ? '' : JSON.stringify(r.error.issues.slice(0, 3))).toBe(true)
    })
  }

  // Các ca sai về phía phản hồi mà Zod của frontend phải từ chối (ca sai theo tham số yêu cầu do server kiểm, không phải ở đây).
  const MUST_REJECT = new Set([
    'OverviewResponse.balance_float',
    'OverviewResponse.thieu_balance',
    'TransactionsResponse.hon_50_dong',
    'CreditLineResponse.http_source',
    'JarDetailResponse.thieu_obligations',
    'BehaviorProfileResponse.evidence_rong',
    'MemoryListResponse.record_id_sai',
    'OpsTraceListResponse.user_ref_la_sub',
    'NudgeFeedbackRequest.outcome_la',
    'DeleteDataConfirmationRequest.tool_khac',
    'DeleteDataRequest.scope_khac',
  ])
  for (const [file, body] of restInvalidEntries()) {
    if (!MUST_REJECT.has(file)) continue
    it(`sai bị từ chối: ${file}`, () => {
      expect(byName[file.split('.')[0]!]!.safeParse(body).success).toBe(false)
    })
  }

  it('IngestJobResponse review/done: khối review và coverage_change đi kèm parse được bằng schema khối', () => {
    const entries = Object.fromEntries(restFixtureEntries())
    for (const name of ['IngestJobResponse.review', 'IngestJobResponse.done']) {
      const j = IngestJobResponse.parse(entries[name])
      expect(IngestReviewBlock.safeParse(j.review).success, name).toBe(true)
    }
    expect(CoverageChangeBlock.safeParse(IngestJobResponse.parse(entries['IngestJobResponse.done']).coverage_change).success).toBe(true)
  })

  it('confirm_rows đi qua /ingest/confirmations và /ingest/actions; tool khác vẫn qua /confirmations và /actions', async () => {
    const entries = Object.fromEntries(restFixtureEntries())
    const urls: string[] = []
    const api = createApiClient({
      baseUrl: 'https://api.example.invalid',
      getAccessToken: async () => 't',
      fetchImpl: (async (url: string) => {
        urls.push(new URL(url).pathname)
        return new Response('{}', { status: 400 })
      }) as unknown as typeof fetch,
    })
    const rows = entries['IngestActionRequest.confirm_rows'] as { params: Record<string, unknown> }
    await api.createConfirmation({ tool: 'confirm_rows', params: rows.params }).catch(() => {})
    await api.applyAction({ tool: 'confirm_rows', params: rows.params, confirm_token: 'a.b' }).catch(() => {})
    await api.createConfirmation({ tool: 'assign_jar', params: {} }).catch(() => {})
    await api.applyAction({ tool: 'assign_jar', params: {}, confirm_token: 'a.b' }).catch(() => {})
    expect(urls).toEqual(['/ingest/confirmations', '/ingest/actions', '/confirmations', '/actions'])
  })

  it('ConfirmationResponse của /me/delete-data/confirmations: tool delete_my_data, có preview của server', () => {
    const r = DeleteDataConfirmationResponse.parse(Object.fromEntries(restFixtureEntries())['ConfirmationResponse.delete_my_data'])
    expect(r.tool).toBe('delete_my_data')
    expect(r.preview?.warnings?.length).toBeGreaterThan(0)
  })

  it('NudgeTodayResponse: thẻ có nudge_id đúng bản tin thì dùng; vắng hoặc không phải proactive_card thì bỏ', () => {
    const entries = Object.fromEntries(restFixtureEntries())
    const card = parseNudgeCard(NudgeTodayResponse.parse(entries['NudgeTodayResponse.co_ban_tin']))
    expect(card?.data.nudge_id).toBe('2d4e6f80-1a3c-4e5b-8d7f-9a1b3c5d7e9f')
    expect(parseNudgeCard(NudgeTodayResponse.parse(entries['NudgeTodayResponse.trong']))).toBeNull()
    const wrong = Object.fromEntries(restInvalidEntries())['NudgeTodayResponse.card_khong_phai_the']
    expect(parseNudgeCard(NudgeTodayResponse.parse(wrong))).toBeNull()
  })

  it('OpsTraceDetail có user_id (sai hợp đồng): phía đọc bỏ trường lạ, giao diện không bao giờ thấy user_id', () => {
    const parsed = OpsTraceDetail.parse(Object.fromEntries(restInvalidEntries())['OpsTraceDetail.co_user_id'])
    expect(parsed).not.toHaveProperty('user_id')
  })

  it('IngestJobListResponse: parse được dạng rỗng và dạng có phần tử không kèm review', () => {
    expect(IngestJobListResponse.safeParse({ jobs: [] }).success).toBe(true)
    const entries = Object.fromEntries(restFixtureEntries())
    const { review: _r, coverage_change: _c, ...summary } = entries['IngestJobResponse.review'] as Record<string, unknown>
    expect(IngestJobListResponse.safeParse({ jobs: [summary] }).success).toBe(true)
  })

  it('POST /actions: nhận cả khối receipt lẫn receipt_action', async () => {
    const entries = Object.fromEntries(restFixtureEntries())
    for (const name of ['ActionResponse.receipt', 'ActionResponse.receipt_action']) {
      const body = entries[name]
      const api = createApiClient({
        baseUrl: 'https://api.example.invalid',
        getAccessToken: async () => 't',
        fetchImpl: (async () => new Response(JSON.stringify(body), { status: 200 })) as typeof fetch,
      })
      const r = await api.applyAction({ tool: 'record_transaction', params: {} })
      expect(r.type).toBe((body as { type: string }).type)
    }
  })
})
