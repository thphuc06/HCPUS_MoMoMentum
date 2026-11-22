// GENERATED FILE. DO NOT EDIT.
// Nguồn: contracts/blocks/*.schema.json (JSON Schema draft 2020-12).
// Sinh bởi: node scripts/gen_contracts.mjs   (kiểm lệch: node scripts/gen_contracts.mjs --check)
// Sửa hợp đồng ở contracts/, rồi sinh lại; không sửa tay file này.
//
// Phía đọc: z.object thường (trường lạ bị bỏ), khác phía sinh dữ liệu (additionalProperties:false).
// Frontend parse TỪNG khối bằng `blockSchemas[type]`; khối lạ hoặc sai schema hiện fallback_text.
import { z } from 'zod'

/** Phiên bản hợp đồng của khối. Chỉ tăng khi đổi không tương thích ngược. */
export const SchemaVersion = z.literal(1)
export type SchemaVersion = z.infer<typeof SchemaVersion>

/** Id ổn định của khối trong một lượt: cùng id thì khối sau thay khối trước (ACTIVITY_SNAPSHOT replace). Quy tắc dựng id ở contracts/README.md. */
export const BlockId = z.string().min(1).max(128).regex(new RegExp("^[A-Za-z0-9_.:-]+$"))
export type BlockId = z.infer<typeof BlockId>

/** trace id của lượt (từ traceparent, hoặc do server sinh ở REST). */
export const TraceId = z.string().min(1).max(64).regex(new RegExp("^[A-Za-z0-9_-]+$"))
export type TraceId = z.infer<typeof TraceId>

/** Câu thay thế khi frontend không hiển thị được khối. Do code dựng từ số liệu thật, không do LLM viết. */
export const FallbackText = z.string().min(1).max(280)
export type FallbackText = z.infer<typeof FallbackText>

/** Ngày YYYY-MM-DD (ngày mô phỏng khi nói về 'hôm nay' của người dùng). */
export const IsoDate = z.string().regex(new RegExp("^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))
export type IsoDate = z.infer<typeof IsoDate>

/** Thời điểm RFC 3339, bắt buộc có múi giờ; server phát ở UTC với hậu tố Z. */
export const IsoDateTime = z.string().regex(new RegExp("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$"))
export type IsoDateTime = z.infer<typeof IsoDateTime>

/** Số tiền VND không âm, số nguyên (không có phần thập phân). Trần theo numeric(14,0). */
export const Vnd = z.int().min(0).max(99999999999999)
export type Vnd = z.infer<typeof Vnd>

/** Số tiền VND có dấu, số nguyên. Dùng cho đại lượng có thể âm: phân vị số dư dự báo (âm là hụt), số dư hũ Chưa phân loại. */
export const VndSigned = z.int().min(-99999999999999).max(99999999999999)
export type VndSigned = z.infer<typeof VndSigned>

/** Tỷ lệ từ 0 đến 1 (xác suất, độ phủ dữ liệu). Không phải tiền, không phải phần trăm 0..100. */
export const Ratio = z.number().min(0).max(1)
export type Ratio = z.infer<typeof Ratio>

/** Số tiền VND dương, số nguyên. */
export const VndPositive = z.int().min(1).max(99999999999999)
export type VndPositive = z.infer<typeof VndPositive>

/** Mã hũ ổn định, chữ thường không dấu (khóa của hũ trong một người dùng). */
export const JarCode = z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$"))
export type JarCode = z.infer<typeof JarCode>

/** Nguồn số liệu của khối. */
export const Source = z.object({
  tool: z.string().min(1).max(80),
  as_of: IsoDateTime,
  app_date: IsoDate,
})
export type Source = z.infer<typeof Source>

/** UUID chữ thường. */
export const Uuid = z.string().regex(new RegExp("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"))
export type Uuid = z.infer<typeof Uuid>

/** Phong bì chung của mọi khối UI. Schema này chấp nhận cả `type` chưa biết (để frontend vẫn hiện fallback_text); schema từng khối chặt hơn. */
export const BlockEnvelope = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.string().min(1).max(40).regex(new RegExp("^[a-z][a-z0-9_]*$")),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: z.record(z.string(), z.unknown()),
})
export type BlockEnvelope = z.infer<typeof BlockEnvelope>

/** Một hũ và số dư hiện tại. */
export const JarBalance = z.object({
  code: JarCode,
  name: z.string().min(1).max(40),
  color_key: z.string().regex(new RegExp("^[a-z][a-z0-9_-]{0,31}$")),
  icon_key: z.string().regex(new RegExp("^[a-z][a-z0-9_-]{0,31}$")),
  balance_vnd: Vnd,
  split_percent: z.number().min(0).max(100),
})
export type JarBalance = z.infer<typeof JarBalance>

export const JarSummaryData = z.object({
  jars: z.array(JarBalance).max(20),
  jars_total_vnd: Vnd,
})
export type JarSummaryData = z.infer<typeof JarSummaryData>

/** Số dư các hũ của người dùng. Số do code đọc từ sổ cái (tool ledger___get_jar_balances hoặc GET /jars), không do LLM viết. */
export const JarSummaryBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("jar_summary"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: JarSummaryData,
})
export type JarSummaryBlock = z.infer<typeof JarSummaryBlock>

/** Tham số đã chuẩn hóa của move_between_jars: mã hũ chữ thường, số tiền nguyên VND dương. Không có user_id (người dùng nằm ở sub của token). */
export const MoveParams = z.object({
  from_jar: JarCode,
  to_jar: JarCode,
  amount_vnd: VndPositive,
})
export type MoveParams = z.infer<typeof MoveParams>

/** Số dư một hũ trước và sau khi thao tác được thực hiện (xem trước). */
export const JarChange = z.object({
  code: JarCode,
  name: z.string().min(1).max(40),
  before_vnd: Vnd,
  after_vnd: Vnd,
})
export type JarChange = z.infer<typeof JarChange>

export const ConfirmData = z.object({
  tool: z.enum(["move_between_jars"]),
  params: MoveParams,
  params_hash: z.string().regex(new RegExp("^[0-9a-f]{64}$")),
  summary: z.string().min(1).max(120),
  preview: z.object({
    from: JarChange,
    to: JarChange,
  }),
  expires_at: IsoDateTime,
})
export type ConfirmData = z.infer<typeof ConfirmData>

/** Đề nghị xác nhận một thao tác ghi. `tool`, `params` và `params_hash` là đúng thứ sẽ được ký vào token một lần (ADR-0002); phần còn lại chỉ để hiển thị. Do code dựng từ kết quả NEEDS_CONFIRMATION của tool, không do LLM viết. */
export const ConfirmBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("confirm"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: ConfirmData,
})
export type ConfirmBlock = z.infer<typeof ConfirmBlock>

/** Một hũ và số dư sau thao tác. */
export const JarAfter = z.object({
  code: JarCode,
  name: z.string().min(1).max(40),
  balance_after_vnd: Vnd,
})
export type JarAfter = z.infer<typeof JarAfter>

export const ReceiptData = z.object({
  tool: z.enum(["move_between_jars"]),
  transaction_id: z.string().regex(new RegExp("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")),
  occurred_at: IsoDateTime,
  app_date: IsoDate,
  amount_vnd: VndPositive,
  summary: z.string().min(1).max(120),
  from_jar: JarAfter,
  to_jar: JarAfter,
})
export type ReceiptData = z.infer<typeof ReceiptData>

/** Biên nhận sau khi một thao tác ghi đã được thực hiện. Trả bởi POST /actions (và dựng lại từ kết quả tool). Số dư sau là số đã commit trong cùng transaction. */
export const ReceiptBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("receipt"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: ReceiptData,
})
export type ReceiptBlock = z.infer<typeof ReceiptBlock>

/** Một gợi ý bấm được. */
export const SuggestionItem = z.object({
  id: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$")),
  label: z.string().min(1).max(40),
  prompt: z.string().min(1).max(200),
})
export type SuggestionItem = z.infer<typeof SuggestionItem>

export const NoticeData = z.object({
  kind: z.enum(["out_of_scope", "degraded", "low_data", "error"]),
  title: z.string().min(1).max(80),
  message: z.string().min(1).max(280),
  code: z.string().regex(new RegExp("^[A-Z][A-Z0-9_]*$")).optional(),
  retryable: z.boolean().optional(),
  degraded_reason: z.enum(["model_budget", "model_error", "tool_error", "tool_timeout", "verifier_failed", "low_coverage", "short_history"]).optional(),
  missing: z.array(z.string().min(1).max(80)).max(5).optional(),
  suggestions: z.array(SuggestionItem).max(4).optional(),
})
export type NoticeData = z.infer<typeof NoticeData>

/** Thông báo trạng thái: ngoài phạm vi, chế độ rút gọn khi hệ thống chạm giới hạn, dữ liệu ít, lỗi (kèm 'Thử lại'). Không chứa số liệu tài chính. Phase 3 thêm các trường TÙY CHỌN `retryable`, `degraded_reason`, `missing`, `suggestions` (không tăng `v`). */
export const NoticeBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("notice"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: NoticeData,
})
export type NoticeBlock = z.infer<typeof NoticeBlock>

/** Đủ, sát, hụt (ok, tight, short). Luôn hiện kèm biểu tượng và chữ, không chỉ màu. Ngưỡng do engine dự báo quyết định theo cấu hình. */
export const JarStatus = z.enum(["ok", "tight", "short"])
export type JarStatus = z.infer<typeof JarStatus>

/** Nhóm tin cậy Cao, Vừa, Thấp (high, medium, low), kèm lý do do code dựng, không phải phần trăm do AI nói. Dựa trên độ phủ dữ liệu, số ngày lịch sử và độ phủ khoảng dự báo đã đo. */
export const ConfidenceBand = z.enum(["high", "medium", "low"])
export type ConfidenceBand = z.infer<typeof ConfidenceBand>

/** Hũ của dự báo (đủ để vẽ biểu tượng và tên mà không gọi thêm). */
export const ForecastJar = z.object({
  code: JarCode,
  name: z.string().min(1).max(40),
  color_key: z.string().regex(new RegExp("^[a-z][a-z0-9_-]{0,31}$")),
  icon_key: z.string().regex(new RegExp("^[a-z][a-z0-9_-]{0,31}$")),
})
export type ForecastJar = z.infer<typeof ForecastJar>

/** Kỳ lương kế tiếp dùng làm mốc 'trước kỳ lương'. */
export const ForecastPayday = z.object({
  date: IsoDate,
  days_until: z.int().min(0).max(400),
})
export type ForecastPayday = z.infer<typeof ForecastPayday>

/** Phân vị SỐ DƯ cuối một ngày của hũ (đã tính nghĩa vụ và lương). P10 là kịch bản xấu (số dư thấp), P90 là kịch bản tốt. Âm nghĩa là hụt. */
export const ForecastDay = z.object({
  date: IsoDate,
  p10_vnd: VndSigned,
  p50_vnd: VndSigned,
  p90_vnd: VndSigned,
})
export type ForecastDay = z.infer<typeof ForecastDay>

/** Mốc trên biểu đồ: một khoản nghĩa vụ đến hạn (tiền ra) hoặc lương về phần của hũ (tiền vào). Ghép lúc đọc từ obligations và lịch lương, không lưu trong bảng dự báo. */
export const ForecastEvent = z.object({
  date: IsoDate,
  kind: z.enum(["obligation", "salary"]),
  label: z.string().min(1).max(60),
  amount_vnd: VndPositive,
  amount_max_vnd: VndPositive.optional(),
})
export type ForecastEvent = z.infer<typeof ForecastEvent>

/** Đường dự báo của hũ SAU khi áp kịch bản. */
export const ForecastScenarioPath = z.object({
  status: JarStatus,
  runout_date: IsoDate.optional(),
  p_shortfall: Ratio.optional(),
  p_shortfall_se: Ratio.optional(),
  min_balance_p50_vnd: VndSigned.optional(),
  days: z.array(ForecastDay).min(1).max(90),
  events: z.array(ForecastEvent).max(60).optional(),
})
export type ForecastScenarioPath = z.infer<typeof ForecastScenarioPath>

/** Biến thể trước và sau của `forecast_timeline`. Các trường cấp trên (`status`, `days`, `events`, `runout_date`, `p_shortfall`...) là TRƯỚC (baseline, đúng như khối không có `compare`), nên frontend cũ không biết `compare` vẫn vẽ đúng baseline. Frontend mới vẽ thêm đường SAU và dải chênh lệch. */
export const ForecastCompare = z.object({
  label: z.string().min(1).max(80),
  kind: z.enum(["one_time_purchase", "bnpl_purchase", "income_change", "recurring_expense", "jar_transfer", "goal_delay"]),
  scenario_id: Uuid.optional(),
  after: ForecastScenarioPath,
  delta: z.object({
    min_balance_delta_vnd: VndSigned,
    runout_shift_days: z.int().min(-400).max(400).optional(),
    p_shortfall_delta: z.number().min(-1).max(1).optional(),
  }),
  n_paths: z.int().min(1),
  common_random_numbers: z.boolean(),
})
export type ForecastCompare = z.infer<typeof ForecastCompare>

export const ForecastTimelineData = z.object({
  jar: ForecastJar,
  status: JarStatus,
  origin_date: IsoDate,
  start_balance_vnd: VndSigned,
  horizon_days: z.int().min(1).max(90),
  payday: ForecastPayday,
  runout_date: IsoDate.optional(),
  p_shortfall: Ratio.optional(),
  p_shortfall_se: Ratio.optional(),
  confidence_band: ConfidenceBand,
  coverage: Ratio.optional(),
  history_days: z.int().min(0),
  is_initial_estimate: z.boolean(),
  model: z.string().min(1).max(40),
  computed_at: IsoDateTime,
  stale: z.boolean(),
  days: z.array(ForecastDay).min(1).max(90),
  events: z.array(ForecastEvent).max(60),
  compare: ForecastCompare.optional(),
})
export type ForecastTimelineData = z.infer<typeof ForecastTimelineData>

/** Cơ sở của một con số tính từ dự báo: độ tươi, nhóm tin cậy, độ dài lịch sử. Dùng chung cho `affordability_card`, `obligation_impact` và kết quả tool kịch bản, để mọi thẻ số liệu đều nói được 'dựa trên dữ liệu nào'. */
export const ForecastBasis = z.object({
  computed_at: IsoDateTime,
  stale: z.boolean(),
  confidence_band: ConfidenceBand,
  is_initial_estimate: z.boolean(),
  history_days: z.int().min(0),
  coverage: Ratio.optional(),
})
export type ForecastBasis = z.infer<typeof ForecastBasis>

/** Dự báo 30 ngày của MỘT hũ: đường số dư P10/P50/P90, mốc nghĩa vụ và lương, ngày cạn, xác suất hụt hoặc nhóm tin cậy. Dùng CHUNG cho màn Chi tiết hũ (GET /forecasts/{jar_code} trả đúng khối này) và chat (tool forecast___get_forecast), nên hai nơi luôn cùng số. Số do code đọc từ bảng forecasts, không do LLM viết. */
export const ForecastTimelineBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("forecast_timeline"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: ForecastTimelineData,
})
export type ForecastTimelineBlock = z.infer<typeof ForecastTimelineBlock>

/** Một nút trên thẻ. kind quyết định giao diện làm gì: open_forecast (mở Chi tiết hũ, cần jar_code), confirm_salary (mở bước xác nhận lương về), review_unclassified (mở danh sách xem lại), open_obligations (mở màn nghĩa vụ), ask_why (mở chat và gửi `prompt`), snooze ('Để sau'), mute_kind ('Ít nhắc loại này'). snooze và mute_kind phase 2 chỉ lưu phía giao diện; lưu ở server khi có bảng nudges (F7). */
export const ProactiveAction = z.object({
  kind: z.enum(["open_forecast", "confirm_salary", "review_unclassified", "open_obligations", "ask_why", "snooze", "mute_kind"]),
  label: z.string().min(1).max(40),
  jar_code: JarCode.optional(),
  prompt: z.string().min(1).max(200).optional(),
})
export type ProactiveAction = z.infer<typeof ProactiveAction>

export const ProactiveCardData = z.object({
  kind: z.enum(["runout_warning", "obligation_due", "salary_pending", "review_needed", "low_data"]),
  status: JarStatus,
  title: z.string().min(1).max(80),
  reason: z.string().min(1).max(200),
  jar_code: JarCode.optional(),
  actions: z.array(ProactiveAction).min(1).max(4),
})
export type ProactiveCardData = z.infer<typeof ProactiveCardData>

/** Thẻ chủ động: MỘT việc cần chú ý, trên Tổng quan. Lý do ngắn, một hành động chính và các hành động phụ. Phase 2 do ledger dựng từ số liệu thật (ví dụ hũ sắp cạn từ dự báo); phase 4-5 cổng nhắc dùng cùng khối. Không chứa lời khuyên đầu tư. */
export const ProactiveCardBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("proactive_card"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: ProactiveCardData,
})
export type ProactiveCardBlock = z.infer<typeof ProactiveCardBlock>

/** Tool ghi dùng khối này (tên ngắn, không có tiền tố target). `schedule_nudge` (target planner, phase 3) đi qua cùng luồng token. confirm_rows (phase 5) là tool của target ingest: chốt các dòng của một lần nạp vào sổ cái. */
export const ConfirmActionTool = z.enum(["record_transaction", "assign_jar", "update_profile", "save_jars", "confirm_salary", "schedule_nudge", "confirm_rows"])
export type ConfirmActionTool = z.infer<typeof ConfirmActionTool>

/** Một dòng 'trước -> sau' để hiển thị, do code định dạng sẵn (ví dụ nhãn 'Số dư Ăn uống', trước '380.000 ₫', sau '180.000 ₫'). Giao diện chỉ vẽ, không tính lại. */
export const ActionChange = z.object({
  label: z.string().min(1).max(60),
  before: z.string().min(1).max(80).optional(),
  after: z.string().min(1).max(120),
})
export type ActionChange = z.infer<typeof ActionChange>

export const ConfirmActionData = z.object({
  tool: ConfirmActionTool,
  params: z.record(z.string(), z.unknown()),
  params_hash: z.string().regex(new RegExp("^[0-9a-f]{64}$")),
  summary: z.string().min(1).max(120),
  changes: z.array(ActionChange).min(1).max(20),
  warnings: z.array(z.string().min(1).max(140)).max(5).optional(),
  expires_at: IsoDateTime,
})
export type ConfirmActionData = z.infer<typeof ConfirmActionData>

/** Đề nghị xác nhận một thao tác ghi KHÔNG phải chuyển hũ (record_transaction, assign_jar, update_profile, save_jars, confirm_salary). Cùng cơ chế với khối `confirm` của phase 1 (ADR-0002): `tool`, `params` và `params_hash` là đúng thứ sẽ được ký vào token một lần; `summary`, `changes`, `warnings` và `expires_at` chỉ để hiển thị. Chuyển hũ (move_between_jars) vẫn dùng khối `confirm` (xem contracts/README.md, mục 'Khối xác nhận và biên nhận'). Id khối giữ quy tắc `confirm:{trace_id}:{params_hash[:12]}`. Do code dựng từ kết quả NEEDS_CONFIRMATION của tool, không do LLM viết. */
export const ConfirmActionBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("confirm_action"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: ConfirmActionData,
})
export type ConfirmActionBlock = z.infer<typeof ConfirmActionBlock>

/** Một dòng chi tiết do code định dạng sẵn (ví dụ nhãn 'Nghĩa vụ mới', giá trị '333.000 ₫ đến hạn 05/12'). */
export const ReceiptDetail = z.object({
  label: z.string().min(1).max(60),
  value: z.string().min(1).max(120),
})
export type ReceiptDetail = z.infer<typeof ReceiptDetail>

/** Việc kế tiếp mà thao tác này mở ra. confirm_salary: tiền vào được nhận diện là lương, cần người dùng xác nhận một chạm để chia vào hũ (kèm cờ ask_update_salary khi lệch nhiều so với lương đã khai). review_unclassified: khoản chi vừa ghi chưa xếp được hũ. */
export const ReceiptFollowUp = z.object({
  kind: z.enum(["confirm_salary", "review_unclassified"]),
  label: z.string().min(1).max(80),
  salary_event_id: z.string().regex(new RegExp("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")).optional(),
  expected_vnd: VndPositive.optional(),
  received_vnd: VndPositive.optional(),
  deviation_percent: z.number().min(-100000).max(100000).optional(),
  ask_update_salary: z.boolean().optional(),
})
export type ReceiptFollowUp = z.infer<typeof ReceiptFollowUp>

/** Một hũ và số dư sau thao tác (có dấu, khác JarAfter của biên nhận chuyển hũ vốn không âm). */
export const JarBalanceAfter = z.object({
  code: JarCode,
  name: z.string().min(1).max(40),
  balance_after_vnd: VndSigned,
})
export type JarBalanceAfter = z.infer<typeof JarBalanceAfter>

export const CoverageJar = z.object({
  code: JarCode,
  name: z.string().min(1).max(40),
})
export type CoverageJar = z.infer<typeof CoverageJar>

export const CoverageChangeData = z.object({
  job_id: z.string().regex(new RegExp("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")),
  before: Ratio.optional(),
  after: Ratio.optional(),
  rows_added: z.int().min(0),
  external_spend_added_vnd: Vnd,
  external_income_added_vnd: Vnd.optional(),
  jars_affected: z.array(CoverageJar).max(20),
  forecast_refresh: z.enum(["queued", "done", "skipped"]),
})
export type CoverageChangeData = z.infer<typeof CoverageChangeData>

/** Độ phủ dữ liệu trước và sau khi chốt MỘT lần nạp (confirm_rows). Số do code tính bằng đúng công thức của dự báo (quality.data_coverage trên các thành phần của app_get_data_coverage, migration 0050), nên khớp dải độ phủ của dự báo. Đi kèm biên nhận của confirm_rows (trường `coverage_change` của `receipt_action.data`, cả ở POST /ingest/actions lẫn tool ingest___confirm_rows) và trong phản hồi GET /ingest/jobs/{job_id} khi job đã xong. Id khối `coverage_change:{job_id}`. */
export const CoverageChangeBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("coverage_change"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: CoverageChangeData,
})
export type CoverageChangeBlock = z.infer<typeof CoverageChangeBlock>

export const ReceiptActionData = z.object({
  tool: ConfirmActionTool,
  reference_id: z.string().regex(new RegExp("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")).optional(),
  occurred_at: IsoDateTime,
  app_date: IsoDate,
  amount_vnd: VndPositive.optional(),
  summary: z.string().min(1).max(120),
  jars_after: z.array(JarBalanceAfter).max(20),
  details: z.array(ReceiptDetail).max(20),
  follow_up: ReceiptFollowUp.optional(),
  coverage_change: CoverageChangeBlock.optional(),
})
export type ReceiptActionData = z.infer<typeof ReceiptActionData>

/** Biên nhận của thao tác ghi KHÔNG phải chuyển hũ (record_transaction, assign_jar, update_profile, save_jars, confirm_salary, schedule_nudge, confirm_rows; với schedule_nudge `reference_id` là id của nhắc, cũng là thứ Hoàn tác dùng để hủy). Trả bởi POST /actions (cùng với `receipt` của chuyển hũ) và, với confirm_rows, bởi POST /ingest/actions và dựng lại từ kết quả tool. Id khối `receipt:{tool}:{reference_id}`, hoặc `receipt:{tool}:{trace_id}` khi thao tác không có reference_id (kèm tool vì assign_jar và record_transaction dùng chung id giao dịch). */
export const ReceiptActionBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("receipt_action"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: ReceiptActionData,
})
export type ReceiptActionBlock = z.infer<typeof ReceiptActionBlock>

export const SuggestionsData = z.object({
  context: z.enum(["welcome", "after_answer", "out_of_scope", "degraded"]),
  title: z.string().min(1).max(80).optional(),
  can_do: z.array(z.string().min(1).max(80)).max(6).optional(),
  cannot_do: z.array(z.string().min(1).max(80)).max(6).optional(),
  items: z.array(SuggestionItem).min(1).max(6),
})
export type SuggestionsData = z.infer<typeof SuggestionsData>

/** Gợi ý bấm được: mở đầu chat (H1, kèm 'mình làm được / chưa làm'), sau câu trả lời, kèm từ chối ngoài phạm vi (H7). Nội dung từ cấu hình hoặc code. Id khối `suggestions:{trace_id}:{context}`. */
export const SuggestionsBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("suggestions"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: SuggestionsData,
})
export type SuggestionsBlock = z.infer<typeof SuggestionsBlock>

/** Dòng biểu phí đã áp cho khoản này (lấy từ `fee_schedules`, không gắn cứng). */
export const FeeApplied = z.object({
  fee_type: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,39}$")),
  amount_vnd: Vnd,
  source_name: z.string().min(1).max(200),
  effective_from: IsoDate,
})
export type FeeApplied = z.infer<typeof FeeApplied>

/** Cảnh báo do một luật suitability sinh ra (ví dụ 'không khuyến khích' khi nghĩa vụ vượt ngưỡng thu nhập). Do code dựng từ luật, không do LLM viết. */
export const Caution = z.object({
  rule_id: z.string().max(64).regex(new RegExp("^[a-z][a-z0-9_]{0,63}$")),
  text: z.string().min(1).max(140),
})
export type Caution = z.infer<typeof Caution>

/** Chi phí thật của một món mua bằng Trả sau, TÁCH 'chi phí của món này' (`item_cost_vnd`) khỏi 'tổng phải trả ngày đến hạn' (`total_due_vnd`, cộng dồn với nghĩa vụ đã có). Bất biến: item_cost_vnd = principal_vnd + fee_added_vnd; total_due_vnd = existing_due_vnd + item_cost_vnd (test kiểm). */
export const CreditCost = z.object({
  product_label: z.string().min(1).max(60),
  principal_vnd: VndPositive,
  fee_added_vnd: Vnd,
  item_cost_vnd: VndPositive,
  due_date: IsoDate,
  existing_due_vnd: Vnd,
  total_due_vnd: VndPositive,
  fee: FeeApplied.optional(),
  late_penalty_vnd: Vnd.optional(),
  limit_vnd: Vnd.optional(),
  available_before_vnd: Vnd.optional(),
  available_after_vnd: Vnd.optional(),
})
export type CreditCost = z.infer<typeof CreditCost>

/** Tỷ lệ nghĩa vụ trên thu nhập so với ngưỡng của luật suitability. */
export const ObligationRatio = z.object({
  obligations_vnd: Vnd,
  income_vnd: Vnd,
  ratio: z.number().min(0),
  threshold: Ratio,
  exceeds: z.boolean(),
})
export type ObligationRatio = z.infer<typeof ObligationRatio>

/** Một hũ trả nghĩa vụ vào ngày đến hạn: đủ hay hụt. */
export const JarAtDue = z.object({
  jar: ForecastJar,
  status: JarStatus,
  balance_before_due_vnd: VndSigned,
  due_vnd: Vnd,
  shortfall_vnd: Vnd,
})
export type JarAtDue = z.infer<typeof JarAtDue>

/** Tác động của một món Trả sau lên nghĩa vụ: chi phí của món này, tổng phải trả ngày đến hạn, hũ nào hụt khi đến hạn, tỷ lệ nghĩa vụ trên thu nhập. Dùng trong chat (kết quả what-if) và trong `affordability_card.credit`. */
export const ObligationImpactData = z.object({
  status: JarStatus,
  headline: z.string().min(1).max(160),
  cost: CreditCost,
  at_due: z.array(JarAtDue).min(1).max(8),
  shortfall_vnd: Vnd,
  ratio: ObligationRatio.optional(),
  cautions: z.array(Caution).max(3).optional(),
  basis: ForecastBasis,
})
export type ObligationImpactData = z.infer<typeof ObligationImpactData>

/** Tác động nghĩa vụ của một món mua bằng Trả sau (mô phỏng). TÁCH `cost.item_cost_vnd` (món này tốn thêm bao nhiêu, gồm phần phí phát sinh thêm) khỏi `cost.total_due_vnd` (ngày đến hạn phải trả tổng bao nhiêu, cộng dồn với nghĩa vụ đã có), để giao diện nói thật khi tháng đó đã có phí. Số do engine tính (tool `forecast___run_scenario`), không do LLM viết. Id khối `obligation_impact:{trace_id}:{due_date}`. */
export const ObligationImpactBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("obligation_impact"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: ObligationImpactData,
})
export type ObligationImpactBlock = z.infer<typeof ObligationImpactBlock>

/** Hành động của một phương án, dẫn tới khối xác nhận đã có. Phương án không có action (chỉ để cân nhắc) thì không có trường này. */
export const OptionAction = z.object({
  kind: z.enum(["confirm", "confirm_action"]),
  tool: z.enum(["move_between_jars", "record_transaction", "assign_jar", "update_profile", "save_jars", "confirm_salary", "schedule_nudge"]),
  block_id: z.string().max(128).regex(new RegExp("^confirm:[A-Za-z0-9_-]+:[0-9a-f]{12}$")),
})
export type OptionAction = z.infer<typeof OptionAction>

/** Một phương án: nhãn, mô tả, trạng thái nếu chọn, vài số, và `action` tùy chọn dẫn tới khối xác nhận. */
export const OptionItem = z.object({
  option_id: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$")),
  kind: z.enum(["defer", "switch_jar", "split", "pay_now", "use_credit", "proceed", "reduce_amount", "move_between_jars", "remind_later", "skip"]),
  label: z.string().min(1).max(60),
  summary: z.string().min(1).max(200),
  status: JarStatus,
  recommended: z.boolean().optional(),
  metrics: z.array(ActionChange).max(4).optional(),
  checked_rules: z.array(z.string().max(64).regex(new RegExp("^[a-z][a-z0-9_]{0,63}$"))).max(8).optional(),
  action: OptionAction.optional(),
})
export type OptionItem = z.infer<typeof OptionItem>

export const OptionsData = z.object({
  title: z.string().min(1).max(80).optional(),
  scenario_id: Uuid.optional(),
  options: z.array(OptionItem).min(2).max(3),
})
export type OptionsData = z.infer<typeof OptionsData>

/** Hai đến ba phương án sau khi phân tích. Mỗi phương án có `action` tùy chọn dẫn tới một khối `confirm` hoặc `confirm_action` đã phát trong cùng lượt (agent gọi tool ghi KHÔNG token để lấy NEEDS_CONFIRMATION, phát khối, rồi tham chiếu theo id). Phương án chỉ cân nhắc thì không có action. Lời mô tả do Analyst viết nhưng số phải qua NumericGrounding; trạng thái và `checked_rules` do Verifier điền. Id khối `options:{trace_id}`. */
export const OptionsBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("options"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: OptionsData,
})
export type OptionsBlock = z.infer<typeof OptionsBlock>

/** Kết quả kiểm một hũ làm nguồn trả. */
export const JarCheck = z.object({
  jar: ForecastJar,
  status: JarStatus,
  balance_before_vnd: VndSigned,
  balance_after_vnd: VndSigned,
  runout_date_before: IsoDate.optional(),
  runout_date_after: IsoDate.optional(),
  days_earlier: z.int().min(0).max(400).optional(),
  shortfall_vnd: Vnd.optional(),
  p_shortfall_after: Ratio.optional(),
})
export type JarCheck = z.infer<typeof JarCheck>

export const AffordabilityCardData = z.object({
  verdict: JarStatus,
  headline: z.string().min(1).max(160),
  amount_vnd: VndPositive,
  label: z.string().min(1).max(60).optional(),
  pay_date: IsoDate.optional(),
  funding_source: z.enum(["jar", "credit"]),
  selected_jar_code: JarCode.optional(),
  jar_checks: z.array(JarCheck).max(8),
  credit: ObligationImpactData.optional(),
  cautions: z.array(Caution).max(3).optional(),
  options: z.array(OptionItem).max(4),
  basis: ForecastBasis,
})
export type AffordabilityCardData = z.infer<typeof AffordabilityCardData>

/** Thẻ kiểm tra trước khi quẹt (F3): đủ, sát hay hụt, nguồn là hũ hoặc Trả sau, tổng chi phí thật, các phương án tất định. Tất định, không qua LLM: `POST /affordability` (màn chuyển tiền) và tool `forecast___affordability_check` (chat) trả CÙNG khối này nên hai nơi cùng số. Ba trạng thái luôn có chữ (`headline`, `status`), không chỉ màu. Id khối `affordability_card:{trace_id}`. */
export const AffordabilityCardBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("affordability_card"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: AffordabilityCardData,
})
export type AffordabilityCardBlock = z.infer<typeof AffordabilityCardBlock>

export const DataUsed = z.object({
  label: z.string().min(1).max(80),
  value: z.string().min(1).max(120).optional(),
  tool: z.string().min(1).max(80),
  as_of: IsoDateTime.optional(),
})
export type DataUsed = z.infer<typeof DataUsed>

/** Một luật đã kiểm và kết quả. */
export const RuleCheck = z.object({
  rule_id: z.string().max(64).regex(new RegExp("^[a-z][a-z0-9_]{0,63}$")),
  label: z.string().min(1).max(80),
  outcome: z.enum(["pass", "warn", "fail", "skipped"]),
  detail: z.string().min(1).max(200).optional(),
})
export type RuleCheck = z.infer<typeof RuleCheck>

/** Nhóm tin cậy Cao, Vừa, Thấp kèm lý do. */
export const ExplainConfidence = z.object({
  band: ConfidenceBand,
  reasons: z.array(z.string().min(1).max(140)).min(1).max(4),
})
export type ExplainConfidence = z.infer<typeof ExplainConfidence>

export const ExplainData = z.object({
  subject_trace_id: TraceId,
  headline: z.string().min(1).max(80).optional(),
  data_used: z.array(DataUsed).min(1).max(20),
  rules_checked: z.array(RuleCheck).max(20),
  confidence: ExplainConfidence,
  ai_generated: z.boolean().optional(),
})
export type ExplainData = z.infer<typeof ExplainData>

/** Bảng 'Vì sao' (H4): dữ liệu đã dùng, luật đã kiểm, nhóm tin cậy Cao/Vừa/Thấp kèm lý do, mã trace. Dựng từ bản ghi lượt trong `audit_events` (code, không do LLM viết); `GET /traces/{trace_id}` trả khối này. Id khối `explain:{subject_trace_id}`. */
export const ExplainBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("explain"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: ExplainData,
})
export type ExplainBlock = z.infer<typeof ExplainBlock>

export const ClarifyChip = z.object({
  id: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$")),
  label: z.string().min(1).max(40),
  value: z.string().min(1).max(80).optional(),
})
export type ClarifyChip = z.infer<typeof ClarifyChip>

export const ClarifyData = z.object({
  question: z.string().min(1).max(200),
  slot: z.enum(["amount", "funding_source", "jar", "date", "scenario_kind", "other"]),
  chips: z.array(ClarifyChip).max(6),
  pending_intent: z.enum(["what_if", "affordability", "move", "profile_update"]).optional(),
  allow_free_text: z.boolean().optional(),
})
export type ClarifyData = z.infer<typeof ClarifyData>

/** Hỏi lại đúng MỘT câu khi thiếu thông tin (số tiền, cách trả, hũ, ngày) kèm chip trả lời (H5). Kết thúc lượt; không gọi tool số liệu. Chip bấm thì gửi `value` (hoặc `label`) như tin nhắn kế tiếp. Id khối `clarify:{trace_id}`. */
export const ClarifyBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("clarify"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: ClarifyData,
})
export type ClarifyBlock = z.infer<typeof ClarifyBlock>

/** Một hũ người dùng (không phải hũ hệ thống) để hiển thị hoặc chọn. */
export const IngestJar = z.object({
  code: JarCode,
  name: z.string().min(1).max(40),
  color_key: z.string().regex(new RegExp("^[a-z][a-z0-9_-]{0,31}$")),
  icon_key: z.string().regex(new RegExp("^[a-z][a-z0-9_-]{0,31}$")),
})
export type IngestJar = z.infer<typeof IngestJar>

/** awaiting_upload (đã cấp URL), queued, processing, review (chờ duyệt), done (đã chốt), failed (lỗi hoặc không đọc được), rejected (không phải tài liệu tài chính, loại không hỗ trợ, trùng tệp). */
export const IngestJobStatus = z.enum(["awaiting_upload", "queued", "processing", "review", "done", "failed", "rejected"])
export type IngestJobStatus = z.infer<typeof IngestJobStatus>

/** auto_added (tin cậy cao, chọn sẵn, chưa ghi), pending (chờ người dùng), approved (đã ghi vào sổ cái), rejected (người dùng bỏ), duplicate (trùng một giao dịch đã có, không ghi). */
export const IngestRowStatus = z.enum(["auto_added", "pending", "approved", "rejected", "duplicate"])
export type IngestRowStatus = z.infer<typeof IngestRowStatus>

export const IngestRow = z.object({
  row_id: z.string().regex(new RegExp("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")),
  seq: z.int().min(1).max(10000),
  kind: z.enum(["expense", "income"]),
  app_date: IsoDate,
  amount_vnd: VndPositive,
  counterparty: z.string().min(1).max(120).optional(),
  description: z.string().min(1).max(200).optional(),
  extract_confidence: Ratio,
  suggested_jar: IngestJar.optional(),
  jar_confidence: Ratio.optional(),
  jar_source: z.enum(["type_map", "rule", "model", "user"]).optional(),
  review_status: IngestRowStatus,
  duplicate_of: z.string().regex(new RegExp("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")).optional(),
})
export type IngestRow = z.infer<typeof IngestRow>

export const IngestCounts = z.object({
  auto_added: z.int().min(0),
  pending: z.int().min(0),
  approved: z.int().min(0),
  rejected: z.int().min(0),
  duplicate: z.int().min(0),
})
export type IngestCounts = z.infer<typeof IngestCounts>

export const IngestReviewData = z.object({
  job_id: z.string().regex(new RegExp("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")),
  status: IngestJobStatus,
  source_kind: z.enum(["image", "csv"]),
  rows: z.array(IngestRow).max(200),
  rows_total: z.int().min(0),
  counts: IngestCounts,
  jars: z.array(IngestJar).max(20),
})
export type IngestReviewData = z.infer<typeof IngestReviewData>

/** Bảng duyệt các dòng trích được từ MỘT lần nạp ảnh hoặc CSV (F6): chi tiêu và thu nhập NGOÀI ví. Dòng được duyệt vào sổ cái với funding_source external (không đổi số dư hũ). Dòng auto_added (tin cậy cao) được CHỌN SẴN nhưng chưa ghi; chỉ confirm_rows (có token, ADR-0002) ghi sổ cái. Văn bản đã che PII trước khi lưu. Đổi hũ một chạm: POST /ingest/rows/{row_id}/jar với một mã trong `jars` (không ghi sổ cái). Id khối `ingest_review:{job_id}`; cùng id thì khối sau thay khối trước. */
export const IngestReviewBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("ingest_review"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: IngestReviewData,
})
export type IngestReviewBlock = z.infer<typeof IngestReviewBlock>

/** Hợp của các khối đã biết (mười sáu), phân biệt theo `type`. Frontend không parse cả mảng bằng schema này: nó parse từng khối theo registry và hiện fallback_text khi type lạ hoặc sai schema. */
export const Block = z.discriminatedUnion('type', [JarSummaryBlock, ConfirmBlock, ReceiptBlock, NoticeBlock, ForecastTimelineBlock, ProactiveCardBlock, ConfirmActionBlock, ReceiptActionBlock, AffordabilityCardBlock, ObligationImpactBlock, OptionsBlock, ExplainBlock, ClarifyBlock, SuggestionsBlock, IngestReviewBlock, CoverageChangeBlock])
export type Block = z.infer<typeof Block>

/** type -> schema của MỌI khối, thứ tự như contracts/blocks/block.schema.json. */
export const blockSchemas = {
  jar_summary: JarSummaryBlock,
  confirm: ConfirmBlock,
  receipt: ReceiptBlock,
  notice: NoticeBlock,
  forecast_timeline: ForecastTimelineBlock,
  proactive_card: ProactiveCardBlock,
  confirm_action: ConfirmActionBlock,
  receipt_action: ReceiptActionBlock,
  affordability_card: AffordabilityCardBlock,
  obligation_impact: ObligationImpactBlock,
  options: OptionsBlock,
  explain: ExplainBlock,
  clarify: ClarifyBlock,
  suggestions: SuggestionsBlock,
  ingest_review: IngestReviewBlock,
  coverage_change: CoverageChangeBlock,
} as const

export type AnyBlockType = keyof typeof blockSchemas
export const ALL_BLOCK_TYPES = ["jar_summary", "confirm", "receipt", "notice", "forecast_timeline", "proactive_card", "confirm_action", "receipt_action", "affordability_card", "obligation_impact", "options", "explain", "clarify", "suggestions", "ingest_review", "coverage_change"] as const

/** Khối mà registry frontend đã đăng ký (xem scripts/gen_contracts.mjs, REGISTERED_BY_FRONTEND). */
export const BLOCK_TYPES = ["jar_summary", "confirm", "receipt", "notice", "forecast_timeline", "proactive_card", "confirm_action", "receipt_action", "ingest_review", "coverage_change"] as const
export type BlockType = (typeof BLOCK_TYPES)[number]
