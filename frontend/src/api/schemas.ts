import { z } from 'zod'
import {
  ActionChange,
  AffordabilityCardBlock,
  BlockId,
  ExplainBlock,
  TraceId,
  ConfidenceBand,
  ForecastTimelineBlock,
  IsoDate,
  IsoDateTime,
  JarBalance,
  JarCode,
  JarStatus,
  ProactiveCardBlock,
  Ratio,
  ReceiptActionBlock,
  ReceiptBlock,
  Vnd,
  VndPositive,
  VndSigned,
} from '@/contracts/blocks'

// Zod cho thân phản hồi và yêu cầu REST, theo contracts/rest/openapi.yaml; dùng lại kiểu nguyên tử từ
// contracts/blocks (sinh tự động) để một nguồn sự thật. Test api/openapi.test.ts so khớp các trường bắt buộc với
// openapi.yaml và chạy toàn bộ fixture contracts/fixtures/rest qua các schema này.
// Phía đọc dễ tính (z.object bỏ trường lạ): server thêm trường tùy chọn thì bản frontend cũ vẫn chạy.

const Uuid = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/)
const Key = z.string().regex(/^[a-z][a-z0-9_-]{0,31}$/)
const TxTypeKey = z.string().regex(/^[a-z][a-z0-9_]{0,39}$/)

// ---------------------------------------------------------------- hũ (phase 1)

export const JarsResponse = z.object({
  app_date: IsoDate,
  as_of: IsoDateTime,
  jars: z.array(JarBalance).max(20),
  jars_total_vnd: Vnd,
})
export type JarsResponse = z.infer<typeof JarsResponse>

// ---------------------------------------------------------------- thành phần dùng chung (ledger.results)

export const Transaction = z.object({
  id: Uuid,
  occurred_at: IsoDateTime,
  app_date: IsoDate,
  kind: z.enum(['expense', 'income', 'transfer']),
  jar: JarCode.optional(),
  amount_vnd: VndSigned,
  merchant: z.string().max(120).optional(),
  note: z.string().max(200).optional(),
  transfer_id: Uuid.optional(),
  tx_type: TxTypeKey.optional(),
  // external (phase 5): chi hoặc thu ngoài ví, nạp từ ảnh hay CSV; không đổi số dư hũ.
  funding_source: z.enum(['jar', 'credit', 'external']).optional(),
  payee_id: Uuid.optional(),
  payee_name: z.string().max(120).optional(),
  obligation_id: Uuid.optional(),
  needs_review: z.boolean().optional(),
})
export type Transaction = z.infer<typeof Transaction>

export const OBLIGATION_KINDS = ['bnpl', 'loan', 'rent', 'bill', 'subscription'] as const
export const OBLIGATION_CYCLES = ['once', 'weekly', 'monthly', 'yearly'] as const

export const Obligation = z.object({
  id: Uuid,
  kind: z.enum(OBLIGATION_KINDS),
  name: z.string().min(1).max(80),
  amount_vnd: VndPositive,
  amount_min_vnd: VndPositive.optional(),
  amount_max_vnd: VndPositive.optional(),
  fee_vnd: Vnd,
  principal_vnd: VndPositive.optional(),
  due_date: IsoDate,
  cycle: z.enum(OBLIGATION_CYCLES),
  due_day: z.int().min(1).max(31).optional(),
  status: z.enum(['active', 'paid', 'cancelled']),
  pay_jar: JarCode.optional(),
  is_essential: z.boolean(),
  source: z.enum(['declared', 'bnpl_auto']),
  paid_at: IsoDateTime.optional(),
})
export type Obligation = z.infer<typeof Obligation>

export const CreditLine = z.object({
  product_code: z.string().regex(/^[a-z][a-z0-9_]{0,31}$/),
  product_label: z.string().max(60),
  limit_vnd: Vnd,
  outstanding_vnd: Vnd,
  available_vnd: Vnd,
  due_day: z.int().min(1).max(31),
  status: z.enum(['active', 'suspended']),
})
export type CreditLine = z.infer<typeof CreditLine>

export const Payee = z.object({
  id: Uuid,
  name: z.string().min(1).max(120),
  account_hint: z.string().max(40).optional(),
  is_favorite: z.boolean(),
  last_used_at: IsoDateTime.optional(),
})
export type Payee = z.infer<typeof Payee>

export const SalaryEvent = z.object({
  id: Uuid,
  period_date: IsoDate,
  received_on: IsoDate,
  expected_vnd: VndPositive.optional(),
  amount_vnd: VndPositive,
  deviation_percent: z.number().min(-100000).max(100000),
  ask_update_salary: z.boolean(),
  status: z.enum(['pending', 'confirmed', 'kept_other']),
  confirmed_at: IsoDateTime.optional(),
})
export type SalaryEvent = z.infer<typeof SalaryEvent>

// ---------------------------------------------------------------- hồ sơ, hũ đầy đủ, Tổng quan

export const Profile = z.object({
  display_name: z.string().min(1).max(80),
  monthly_salary_vnd: VndPositive.optional(),
  payday_day: z.int().min(1).max(31).optional(),
  risk_tolerance: z.enum(['low', 'medium', 'high']).optional(),
  onboarded: z.boolean(),
})
export type Profile = z.infer<typeof Profile>

export const ProfileResponse = z.object({ app_date: IsoDate, as_of: IsoDateTime, profile: Profile })
export type ProfileResponse = z.infer<typeof ProfileResponse>

export const JarKind = z.enum(['spending', 'saving', 'obligation', 'system'])
export type JarKind = z.infer<typeof JarKind>

export const JarFull = z.object({
  code: JarCode,
  name: z.string().min(1).max(40),
  color_key: Key,
  icon_key: Key,
  kind: JarKind,
  system_role: z.enum(['other_income', 'unclassified']).optional(),
  balance_vnd: VndSigned,
  split_percent: z.number().min(0).max(100),
  goal_vnd: VndPositive.optional(),
  goal_date: IsoDate.optional(),
  status: JarStatus.optional(),
  runout_date: IsoDate.optional(),
  /** #25: sai ở hũ thưa (server đã bỏ `runout_date`), giao diện nói "Có thể cạn trước ngày lương"; vắng nghĩa là đúng. */
  runout_date_shown: z.boolean().optional(),
  p_shortfall: Ratio.optional(),
  confidence_band: ConfidenceBand.optional(),
  /** Số dư dự báo P50 thấp nhất từ ngày mai tới trước kỳ lương (có dấu, có thể âm); vắng khi hũ chưa có dự báo. */
  forecast_floor_vnd: VndSigned.optional(),
})
export type JarFull = z.infer<typeof JarFull>

export const OverviewBalance = z.object({
  total_vnd: VndSigned,
  jars_total_vnd: VndSigned,
  other_income_vnd: Vnd,
  unclassified_vnd: VndSigned,
})

export const NextPayday = z.object({
  date: IsoDate,
  days_until: z.int().min(1).max(400),
  expected_vnd: VndPositive.optional(),
  state: z.enum(['expected', 'pending_confirmation', 'confirmed']),
  salary_event_id: Uuid.optional(),
})
export type NextPayday = z.infer<typeof NextPayday>

export const ForecastMeta = z.object({
  computed_at: IsoDateTime,
  run_app_date: IsoDate,
  stale: z.boolean(),
  is_initial_estimate: z.boolean(),
  confidence_band: ConfidenceBand,
  coverage: Ratio.optional(),
  history_days: z.int().min(0),
  model: z.string().min(1).max(40),
})
export type ForecastMeta = z.infer<typeof ForecastMeta>

export const OverviewResponse = z.object({
  app_date: IsoDate,
  as_of: IsoDateTime,
  profile: Profile,
  balance: OverviewBalance,
  jars: z.array(JarFull).max(20),
  system_jars: z.array(JarFull).max(2),
  next_payday: NextPayday.nullable(),
  forecast: ForecastMeta.nullable(),
  // Thẻ chủ động: parse riêng ở nơi vẽ (khối sai schema thì ẩn thẻ chứ không làm hỏng Tổng quan).
  proactive_card: z.unknown().nullable(),
  credit_line: CreditLine.nullable(),
  obligations_due: z.array(Obligation).max(5),
  recent_transactions: z.array(Transaction).max(5),
  needs_review_count: z.int().min(0),
})
export type OverviewResponse = z.infer<typeof OverviewResponse>

export const JarDetailResponse = z.object({
  app_date: IsoDate,
  as_of: IsoDateTime,
  jar: JarFull,
  forecast: ForecastMeta.nullable(),
  recent_transactions: z.array(Transaction).max(10),
  obligations: z.array(Obligation).max(10),
})
export type JarDetailResponse = z.infer<typeof JarDetailResponse>

/** Tách thẻ chủ động khỏi phản hồi Tổng quan: null nếu vắng hoặc sai schema. */
export function parseProactiveCard(raw: unknown): z.infer<typeof ProactiveCardBlock> | null {
  const r = ProactiveCardBlock.safeParse(raw)
  return r.success ? r.data : null
}

// ---------------------------------------------------------------- danh sách

export const TransactionsResponse = z.object({
  app_date: IsoDate,
  as_of: IsoDateTime,
  transactions: z.array(Transaction).max(50),
  next_cursor: z.string().min(1).max(200).optional(),
})
export type TransactionsResponse = z.infer<typeof TransactionsResponse>

export const TxType = z.object({
  tx_type: TxTypeKey,
  label: z.string().min(1).max(60),
  direction: z.enum(['out', 'in']),
  /** Đúng với loại "chuyển tiền cho người khác": màn chuyển tiền tìm loại này theo cờ, không theo mã gõ cứng. */
  is_person_transfer: z.boolean().optional(),
  default_jar: JarCode.optional(),
  system_role: z.enum(['other_income', 'unclassified']).optional(),
})
export type TxType = z.infer<typeof TxType>
export const TxTypesResponse = z.object({ tx_types: z.array(TxType).max(60) })
export type TxTypesResponse = z.infer<typeof TxTypesResponse>

export const PayeesResponse = z.object({ payees: z.array(Payee).max(100) })
export type PayeesResponse = z.infer<typeof PayeesResponse>

export const ObligationsResponse = z.object({
  app_date: IsoDate,
  obligations: z.array(Obligation).max(100),
  total_due_vnd: Vnd,
})
export type ObligationsResponse = z.infer<typeof ObligationsResponse>

export const FeeLine = z.object({
  fee_type: TxTypeKey,
  amount_vnd: Vnd.optional(),
  rate_percent: z.number().min(0).optional(),
  period: z.enum(['per_month', 'per_transaction', 'once']),
  condition_code: z.enum(['always', 'month_has_transaction', 'overdue']),
  condition_note: z.string().max(200).optional(),
  source_name: z.string().max(200),
  source_url: z.string().regex(/^https:\/\//),
  effective_from: IsoDate,
})
export type FeeLine = z.infer<typeof FeeLine>

export const CreditLineResponse = z.object({
  app_date: IsoDate,
  credit_line: CreditLine.nullable(),
  fees: z.array(FeeLine).max(20),
})
export type CreditLineResponse = z.infer<typeof CreditLineResponse>

export const SalaryEventsResponse = z.object({ salary_events: z.array(SalaryEvent).max(20) })
export type SalaryEventsResponse = z.infer<typeof SalaryEventsResponse>

export const JarTemplate = z.object({
  code: JarCode,
  name: z.string().min(1).max(40),
  color_key: Key,
  icon_key: Key,
  kind: z.enum(['spending', 'saving', 'obligation']),
  default_split_percent: z.number().min(0).max(100),
  is_default: z.boolean(),
})
export type JarTemplate = z.infer<typeof JarTemplate>
export const JarTemplatesResponse = z.object({ templates: z.array(JarTemplate).max(20) })
export type JarTemplatesResponse = z.infer<typeof JarTemplatesResponse>

export type TransactionQuery = {
  jar?: string
  kind?: 'expense' | 'income' | 'transfer'
  needsReview?: boolean
  limit?: number
  cursor?: string
}

// ---------------------------------------------------------------- ghi: xác nhận và hành động

/** Tool ghi của Lambda `ledger` (`POST /confirmations`, `POST /actions`): bảy tool, KHÔNG có `confirm_rows`. */
export const TOOL_NAMES = ['move_between_jars', 'record_transaction', 'assign_jar', 'update_profile', 'save_jars', 'confirm_salary', 'schedule_nudge'] as const
export const ToolName = z.enum(TOOL_NAMES)
export type ToolName = z.infer<typeof ToolName>

/** Tool ghi của Lambda `ingest` (`POST /ingest/confirmations`, `POST /ingest/actions`): chỉ `confirm_rows` (phase 5). */
export const INGEST_TOOL_NAMES = ['confirm_rows'] as const
export const IngestToolName = z.enum(INGEST_TOOL_NAMES)
export type IngestToolName = z.infer<typeof IngestToolName>

/** Mọi tool ghi mà màn hình hoặc khối `confirm_action` có thể yêu cầu; `ApiClient` tự chọn cặp endpoint theo tool. */
export const AnyToolName = z.enum([...TOOL_NAMES, ...INGEST_TOOL_NAMES])
export type AnyToolName = z.infer<typeof AnyToolName>

/** Tham số của tool: object đã (hoặc chưa) chuẩn hóa; server chuẩn hóa lại và chỉ ký bản chuẩn hóa. */
export type ToolParams = Record<string, unknown>

/**
 * Đề nghị (khối `confirm`/`confirm_action`) đang được thực hiện: server chỉ cho thực hiện một lần và lưu biên nhận
 * gắn với nó. Gửi cả hai trường hoặc không gửi (màn hình tự dựng thì không gửi).
 */
const ConfirmRef = {
  conversation_id: z.string().min(1).max(256).optional(),
  confirm_block_id: z.string().max(128).optional(),
}

export const ConfirmationRequest = z.object({
  tool: AnyToolName,
  params: z.record(z.string(), z.unknown()),
  params_hash: z.string().regex(/^[0-9a-f]{64}$/).optional(),
  ...ConfirmRef,
})
export type ConfirmationRequest = z.infer<typeof ConfirmationRequest>

/**
 * Bản xem trước do SERVER tính (không ghi gì): số dư trước và sau, phí và hạn mức của Trả sau, phần chia lương. Màn "Xem
 * lại" chỉ vẽ, không tự tính. Cùng hình dạng `changes`/`warnings` của khối `confirm_action`.
 */
export const ConfirmPreview = z.object({
  summary: z.string().min(1).max(120),
  changes: z.array(ActionChange).min(1).max(20),
  warnings: z.array(z.string().min(1).max(140)).max(5).optional(),
})
export type ConfirmPreview = z.infer<typeof ConfirmPreview>

export const ConfirmationResponse = z.object({
  confirm_token: z.string().min(3).max(1024),
  expires_at: IsoDateTime,
  ttl_seconds: z.int().min(1),
  tool: AnyToolName,
  params: z.record(z.string(), z.unknown()),
  params_hash: z.string().regex(/^[0-9a-f]{64}$/),
  // Chỉ để hiển thị: sai hình dạng thì bỏ xem trước chứ không chặn việc ghi.
  preview: ConfirmPreview.optional().catch(undefined),
})
export type ConfirmationResponse = z.infer<typeof ConfirmationResponse>

/** POST /confirmations/cancel: ghi việc người dùng bấm "Không" (không ghi sổ cái, không cần token). */
export const CancelConfirmationRequest = z.object({
  conversation_id: z.string().min(1).max(256),
  confirm_block_id: z.string().max(128),
})
export type CancelConfirmationRequest = z.infer<typeof CancelConfirmationRequest>

export const CancelConfirmationResponse = z.object({
  block_id: z.string().min(1),
  status: z.literal('cancelled'),
  resolved_at: IsoDateTime,
})
export type CancelConfirmationResponse = z.infer<typeof CancelConfirmationResponse>

export const ActionRequest = z.object({
  tool: AnyToolName,
  params: z.record(z.string(), z.unknown()),
  confirm_token: z.string().max(1024).optional(),
  ...ConfirmRef,
})
export type ActionRequest = z.infer<typeof ActionRequest>

/** POST /actions trả khối `receipt` (chuyển hũ) hoặc `receipt_action` (mọi thao tác ghi khác), phân biệt bằng `type`. */
export const ActionResponse = z.discriminatedUnion('type', [ReceiptBlock, ReceiptActionBlock])
export type ActionResponse = z.infer<typeof ActionResponse>

export const ResetResponse = z.object({
  reset_at: IsoDateTime,
  app_date: IsoDate,
  clock_offset_days: z.int(),
  jars_count: z.int().min(0),
  transactions_count: z.int().min(0),
  obligations_count: z.int().min(0).optional(),
  forecast_ready: z.boolean().optional(),
})
export type ResetResponse = z.infer<typeof ResetResponse>

/** Khối dự báo do GET /forecasts/{jar_code} trả (cùng khối `forecast_timeline` trong chat). */
export const ForecastResponse = ForecastTimelineBlock
export type ForecastResponse = z.infer<typeof ForecastResponse>

// ---------------------------------------------------------------- phase 3: kiểm tra trước khi quẹt, "Vì sao", phản hồi

/** POST /affordability: `funding_source` vắng thì xét cả hai nguồn; `jar` chỉ có nghĩa khi nguồn là hũ; `date` vắng là hôm nay mô phỏng. */
export const AffordabilityRequest = z.object({
  amount_vnd: VndPositive,
  funding_source: z.enum(['jar', 'credit']).optional(),
  jar: JarCode.optional(),
  label: z.string().min(1).max(60).optional(),
  date: IsoDate.optional(),
})
export type AffordabilityRequest = z.infer<typeof AffordabilityRequest>

/** Trả khối `affordability_card` (cả phong bì), cùng khối và cùng số với tool `forecast___affordability_check` trong chat. */
export const AffordabilityResponse = AffordabilityCardBlock
export type AffordabilityResponse = z.infer<typeof AffordabilityResponse>

const TraceBlockRef = z.object({ id: BlockId, type: z.string().min(1).max(40) })
const TraceStep = z.object({ step: z.string().min(1).max(40), ms: z.int().min(0) })
const TokenUsage = z.object({
  input_tokens: z.int().min(0),
  output_tokens: z.int().min(0),
  model_calls: z.int().min(0),
  cache_read_tokens: z.int().min(0).optional(),
})
export const TraceDetail = z.object({
  intent: z.string().max(32).optional(),
  outcome: z.enum(['ok', 'rejected', 'error']).optional(),
  blocks_emitted: z.array(TraceBlockRef).max(40),
  token_usage: TokenUsage,
  step_timings: z.array(TraceStep).max(30),
  duration_ms: z.int().min(0),
})
export type TraceDetail = z.infer<typeof TraceDetail>

/** GET /traces/{trace_id}: khối `explain` đã dựng (đúng thứ bảng "Vì sao" hiển thị) cộng chi tiết kỹ thuật. */
export const TraceResponse = z.object({
  trace_id: TraceId,
  created_at: IsoDateTime,
  explain: ExplainBlock,
  detail: TraceDetail,
})
export type TraceResponse = z.infer<typeof TraceResponse>

/** POST /feedback: không qua token (không đụng tiền). Idempotent theo (trace_id, block_id, option_id). */
export const FeedbackRequest = z.object({
  trace_id: TraceId,
  block_id: BlockId.optional(),
  option_id: z.string().regex(/^[a-z][a-z0-9_]{0,31}$/),
  decision: z.enum(['accepted', 'rejected']),
  scenario_id: Uuid.optional(),
  reason: z.string().min(1).max(200).optional(),
})
export type FeedbackRequest = z.infer<typeof FeedbackRequest>

export const FeedbackResponse = z.object({
  feedback_id: Uuid,
  decision: z.enum(['accepted', 'rejected']),
  recorded_at: IsoDateTime,
})
export type FeedbackResponse = z.infer<typeof FeedbackResponse>
