import { z } from 'zod'
import {
  BehaviorProfileData,
  BlockId,
  DataUsed,
  ExplainConfidence,
  IsoDate,
  IsoDateTime,
  JarCode,
  ProactiveCardBlock,
  Ratio,
  RuleCheck,
  TraceId,
  Uuid,
  Vnd,
} from '@/contracts/blocks'
import { ApiError } from './errors'
import { ConfirmPreview } from './schemas'

// Zod của REST phase 5 (F7, quyền riêng tư, trace) theo contracts/rest/openapi.yaml: hồ sơ hành vi, bản tin của cổng giá trị,
// bộ nhớ của trợ lý, xóa dữ liệu của tôi, bảng vận hành `/ops/*`. Phía đọc dễ tính (z.object bỏ trường lạ) như schemas.ts;
// test api/openapi.test.ts so trường bắt buộc với hợp đồng và chạy fixture contracts/fixtures/rest qua các schema này.

// ---------------------------------------------------------------- hồ sơ hành vi

/** GET /profile/behavior: cùng `data` với tool `forecast___get_behavior_profile`. `ready` sai không phải lỗi. */
export const BehaviorProfileResponse = BehaviorProfileData
export type BehaviorProfileResponse = z.infer<typeof BehaviorProfileResponse>

// ---------------------------------------------------------------- bản tin của cổng giá trị

export const NUDGE_KINDS = [
  'runout_warning', 'obligation_due', 'salary_pending', 'review_needed', 'low_data', 'purchase_review',
  'roadmap_proposed', 'resilience_drop', 'behavior_insight',
] as const
export const NudgeKind = z.enum(NUDGE_KINDS)
export const NUDGE_OUTCOMES = ['acted', 'dismissed', 'snoozed', 'less_like_this'] as const
export const NudgeOutcome = z.enum(NUDGE_OUTCOMES)
export type NudgeOutcome = z.infer<typeof NudgeOutcome>

export const NudgeGate = z.object({
  rank: z.int().min(1).max(20),
  score: z.number().min(0),
  threshold: z.number().min(0),
  candidates: z.int().min(1).max(20),
  demoted: z.boolean().optional(),
})

export const Nudge = z.object({
  nudge_id: Uuid,
  kind: NudgeKind,
  app_date: IsoDate,
  title: z.string().min(1).max(80),
  reason: z.string().min(1).max(200),
  jar_code: JarCode.optional(),
  value_vnd: Vnd.optional(),
  gate: NudgeGate,
  outcome: NudgeOutcome.optional(),
})
export type Nudge = z.infer<typeof Nudge>

export const NudgeSuppressed = z.object({
  kind: NudgeKind,
  reason: z.enum(['below_threshold', 'demoted', 'quiet_hours', 'lower_rank']),
})

/**
 * GET /nudges/today. `card` giữ dạng thô: nơi vẽ parse bằng schema khối (khối hỏng thì quay về thẻ tất định của Tổng quan chứ
 * không làm hỏng cả phản hồi). `nudge` và `card` cùng có hoặc cùng vắng.
 */
export const NudgeTodayResponse = z.object({
  app_date: IsoDate,
  nudge: Nudge.optional(),
  card: z.unknown().optional(),
  suppressed: z.array(NudgeSuppressed).max(10),
})
export type NudgeTodayResponse = z.infer<typeof NudgeTodayResponse>

export const NudgeFeedbackRequest = z.object({
  outcome: NudgeOutcome,
  reason: z.string().min(1).max(200).optional(),
})
export type NudgeFeedbackRequest = z.infer<typeof NudgeFeedbackRequest>

export const NudgeFeedbackResponse = z.object({
  nudge_id: Uuid,
  outcome: NudgeOutcome,
  recorded_at: IsoDateTime,
})
export type NudgeFeedbackResponse = z.infer<typeof NudgeFeedbackResponse>

/** Thẻ của bản tin hôm nay: null nếu không có bản tin hoặc khối sai schema. */
export function parseNudgeCard(res: NudgeTodayResponse | null | undefined): z.infer<typeof ProactiveCardBlock> | null {
  if (!res?.nudge || res.card === undefined) return null
  const r = ProactiveCardBlock.safeParse(res.card)
  return r.success && r.data.data.nudge_id === res.nudge.nudge_id ? r.data : null
}

// ---------------------------------------------------------------- bộ nhớ của trợ lý

export const MEMORY_KINDS = ['preference', 'fact', 'session_summary', 'behavior', 'lesson'] as const
export const MemoryKind = z.enum(MEMORY_KINDS)
export type MemoryKind = z.infer<typeof MemoryKind>
export const MemoryRecordId = z.string().regex(/^mem-[A-Za-z0-9_-]{36,46}$/)

export const MemoryRecord = z.object({
  record_id: MemoryRecordId,
  kind: MemoryKind,
  source: z.enum(['conversation', 'system']),
  text: z.string().min(1).max(1000),
  created_at: IsoDateTime,
})
export type MemoryRecord = z.infer<typeof MemoryRecord>

export const MemoryListResponse = z.object({
  records: z.array(MemoryRecord).max(100),
  next_cursor: z.string().min(1).max(2048).optional(),
})
export type MemoryListResponse = z.infer<typeof MemoryListResponse>

export const MemoryRecordDeleteResponse = z.object({ record_id: MemoryRecordId, deleted: z.literal(true) })
export type MemoryRecordDeleteResponse = z.infer<typeof MemoryRecordDeleteResponse>

export const MemoryClearResponse = z.object({
  deleted_records: z.int().min(0),
  deleted_events: z.int().min(0),
  failed: z.int().min(0),
})
export type MemoryClearResponse = z.infer<typeof MemoryClearResponse>

export type MemoryQuery = { kind?: MemoryKind; limit?: number; cursor?: string }

// ---------------------------------------------------------------- xóa dữ liệu của tôi

export const PRIVACY_TOOL_NAMES = ['delete_my_data'] as const
export const PrivacyToolName = z.enum(PRIVACY_TOOL_NAMES)
export const DeleteMyDataParams = z.object({ scope: z.literal('all').optional() })

export const DeleteDataConfirmationRequest = z.object({
  tool: PrivacyToolName,
  params: DeleteMyDataParams,
  params_hash: z.string().regex(/^[0-9a-f]{64}$/).optional(),
})
export type DeleteDataConfirmationRequest = z.infer<typeof DeleteDataConfirmationRequest>

/** `ConfirmationResponse` của `/me/delete-data/confirmations`: cùng hình dạng, `tool` là `delete_my_data`. */
export const DeleteDataConfirmationResponse = z.object({
  confirm_token: z.string().min(3).max(1024),
  expires_at: IsoDateTime,
  ttl_seconds: z.int().min(1),
  tool: PrivacyToolName,
  params: z.record(z.string(), z.unknown()),
  params_hash: z.string().regex(/^[0-9a-f]{64}$/),
  preview: ConfirmPreview.optional().catch(undefined),
})
export type DeleteDataConfirmationResponse = z.infer<typeof DeleteDataConfirmationResponse>

export const DeleteDataRequest = z.object({
  tool: PrivacyToolName,
  params: DeleteMyDataParams,
  confirm_token: z.string().regex(/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/).max(1024).optional(),
})
export type DeleteDataRequest = z.infer<typeof DeleteDataRequest>

export const DeletionStep = z.object({
  status: z.enum(['pending', 'done', 'failed', 'skipped']),
  deleted: z.int().min(0).optional(),
  error_code: z.string().regex(/^[A-Z][A-Z0-9_]*$/).max(40).optional(),
})
export type DeletionStep = z.infer<typeof DeletionStep>

export const DataDeletion = z.object({
  deletion_id: Uuid,
  status: z.enum(['running', 'done', 'partial', 'failed']),
  scope: z.literal('all'),
  requested_at: IsoDateTime,
  finished_at: IsoDateTime.optional(),
  steps: z.object({ s3: DeletionStep, memory: DeletionStep, aurora: DeletionStep }),
})
export type DataDeletion = z.infer<typeof DataDeletion>

// ---------------------------------------------------------------- bảng vận hành (chỉ nhóm Cognito `ops`)

const OpsIntent = z.string().regex(/^[a-z][a-z_]{0,31}$/)
const OpsOutcome = z.enum(['ok', 'rejected', 'error'])
/** Mã lỗi trên màn vận hành: dễ tính (mã mới của server vẫn hiện nguyên văn). */
const OpsCode = z.string().regex(/^[A-Z][A-Z0-9_]*$/).max(64)
export const UserRef = z.string().regex(/^[0-9a-f]{12}$/)

export const OpsTraceSummary = z.object({
  trace_id: TraceId,
  created_at: IsoDateTime,
  user_ref: UserRef,
  intent: OpsIntent.optional(),
  outcome: OpsOutcome,
  code: OpsCode.optional(),
  duration_ms: z.int().min(0),
  model_calls: z.int().min(0),
  input_tokens: z.int().min(0),
  output_tokens: z.int().min(0),
  est_cost_vnd: Vnd,
  tool_calls: z.int().min(0),
  tool_errors: z.int().min(0),
  rules_failed: z.int().min(0),
})
export type OpsTraceSummary = z.infer<typeof OpsTraceSummary>

export const OpsTraceListResponse = z.object({
  traces: z.array(OpsTraceSummary).max(100),
  next_cursor: z.string().min(1).max(200).optional(),
})
export type OpsTraceListResponse = z.infer<typeof OpsTraceListResponse>

export const OpsTraceStep = z.object({
  step: z.string().regex(/^[a-z][a-z0-9_]{0,39}$/),
  ms: z.int().min(0),
  status: z.enum(['ok', 'error', 'denied']).optional(),
  code: OpsCode.optional(),
})
export type OpsTraceStep = z.infer<typeof OpsTraceStep>

export const OpsToolCall = z.object({
  target: z.enum(['ledger', 'forecast', 'knowledge', 'planner', 'audit', 'ingest']),
  tool: z.string().regex(/^[a-z][a-z0-9_]{0,39}$/),
  ms: z.int().min(0),
  status: z.enum(['ok', 'error', 'denied']),
  code: OpsCode.optional(),
})
export type OpsToolCall = z.infer<typeof OpsToolCall>

export const OpsTraceDetail = z.object({
  trace_id: TraceId,
  created_at: IsoDateTime,
  user_ref: UserRef,
  intent: OpsIntent.optional(),
  outcome: OpsOutcome,
  code: OpsCode.optional(),
  duration_ms: z.int().min(0),
  steps: z.array(OpsTraceStep).max(30),
  tool_calls: z.array(OpsToolCall).max(30),
  rules_checked: z.array(RuleCheck).max(20),
  data_used: z.array(DataUsed).max(20),
  confidence: ExplainConfidence.optional(),
  blocks_emitted: z.array(z.object({ id: BlockId, type: z.string().min(1).max(40) })).max(40),
  token_usage: z.object({
    input_tokens: z.int().min(0),
    output_tokens: z.int().min(0),
    model_calls: z.int().min(0),
    cache_read_tokens: z.int().min(0).optional(),
  }),
  est_cost_vnd: Vnd,
  pii_masked: z.literal(true),
})
export type OpsTraceDetail = z.infer<typeof OpsTraceDetail>

/** Lượt gọi một model trong ngày; `cap` là trần ngày của chính model đó, vắng khi model không còn trong cấu hình. */
export const OpsModelDayCalls = z.object({
  model: z.string().min(1).max(200),
  model_calls: z.int().min(0),
  cap: z.int().min(0).optional(),
})
export type OpsModelDayCalls = z.infer<typeof OpsModelDayCalls>

/** `cap` là tổng trần mọi model (chỉ để tham khảo); so với trần thì dùng `by_model`, vắng khi số lấy từ bản ghi lượt. */
export const OpsDayModelCalls = z.object({
  day: IsoDate,
  model_calls: z.int().min(0),
  cap: z.int().min(1),
  by_model: z.array(OpsModelDayCalls).max(20).optional(),
})
export type OpsDayModelCalls = z.infer<typeof OpsDayModelCalls>

export const OpsSummaryResponse = z.object({
  from: IsoDateTime,
  to: IsoDateTime,
  turns: z.int().min(0),
  turns_rejected: z.int().min(0),
  turns_error: z.int().min(0),
  latency_ms: z.object({ p50: z.int().min(0), p95: z.int().min(0) }).optional(),
  tool_calls: z.int().min(0),
  tool_errors: z.int().min(0),
  tool_error_rate: Ratio,
  rule_fails: z.int().min(0),
  model_calls_by_day: z.array(OpsDayModelCalls).max(31),
  est_cost_vnd: Vnd,
})
export type OpsSummaryResponse = z.infer<typeof OpsSummaryResponse>

export type OpsTraceQuery = { outcome?: 'ok' | 'rejected' | 'error'; intent?: string; limit?: number; cursor?: string }

// ---------------------------------------------------------------- lời gọi

type Call = <T>(method: string, path: string, schema: z.ZodType<T>, body?: unknown) => Promise<T>

function withQuery(path: string, query: Record<string, string | number | undefined>) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) if (value !== undefined) params.set(key, String(value))
  return params.size ? `${path}?${params}` : path
}

const DELETE_ALL = { tool: 'delete_my_data', params: { scope: 'all' } } as const

export function createPhase5Api(call: Call) {
  const enc = encodeURIComponent
  return {
    getBehaviorProfile: () => call('GET', '/profile/behavior', BehaviorProfileResponse),
    getTodayNudge: () => call('GET', '/nudges/today', NudgeTodayResponse),
    submitNudgeFeedback: async (nudgeId: string, req: NudgeFeedbackRequest) => {
      const parsed = NudgeFeedbackRequest.safeParse(req)
      if (!parsed.success || !Uuid.safeParse(nudgeId).success) throw new ApiError('PARAMS_INVALID', 0)
      return call('POST', `/nudges/${enc(nudgeId)}/feedback`, NudgeFeedbackResponse, parsed.data)
    },
    listMemory: (q: MemoryQuery = {}) => call('GET', withQuery('/memory', q), MemoryListResponse),
    deleteMemoryRecord: (recordId: string) => {
      if (!MemoryRecordId.safeParse(recordId).success) return Promise.reject(new ApiError('PARAMS_INVALID', 0))
      return call('DELETE', `/memory/${enc(recordId)}`, MemoryRecordDeleteResponse)
    },
    clearMemory: () => call('DELETE', '/memory', MemoryClearResponse),
    /** Token + xem trước cho "Xóa dữ liệu của tôi" (không ghi gì). */
    createDeleteDataConfirmation: () => call('POST', '/me/delete-data/confirmations', DeleteDataConfirmationResponse, DELETE_ALL),
    /** Xóa thật, kèm token vừa cấp. Thiếu token thì server trả 428 và không xóa gì. */
    deleteMyData: (confirmToken: string) =>
      call('POST', '/me/delete-data', DataDeletion, { ...DELETE_ALL, confirm_token: confirmToken }),
    listOpsTraces: (q: OpsTraceQuery = {}) => call('GET', withQuery('/ops/traces', q), OpsTraceListResponse),
    getOpsTrace: (traceId: string) => call('GET', `/ops/traces/${enc(traceId)}`, OpsTraceDetail),
    getOpsSummary: () => call('GET', '/ops/summary', OpsSummaryResponse),
  }
}
