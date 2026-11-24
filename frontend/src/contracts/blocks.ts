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
  kind: z.enum(["spending", "saving", "obligation"]).optional(),
  goal_vnd: VndPositive.optional(),
  goal_date: IsoDate.optional(),
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
  kind: z.enum(["out_of_scope", "degraded", "low_data", "error", "info"]),
  title: z.string().min(1).max(80),
  message: z.string().min(1).max(280),
  code: z.string().regex(new RegExp("^[A-Z][A-Z0-9_]*$")).optional(),
  retryable: z.boolean().optional(),
  degraded_reason: z.enum(["model_budget", "model_error", "tool_error", "tool_timeout", "verifier_failed", "low_coverage", "short_history"]).optional(),
  missing: z.array(z.string().min(1).max(80)).max(5).optional(),
  suggestions: z.array(SuggestionItem).max(4).optional(),
})
export type NoticeData = z.infer<typeof NoticeData>

/** Thông báo trạng thái: ngoài phạm vi, chế độ rút gọn khi hệ thống chạm giới hạn, dữ liệu ít, lỗi (kèm 'Thử lại'), thông tin (trạng thái trống, không phải lỗi). Không chứa số liệu tài chính. Phase 3 thêm các trường TÙY CHỌN `retryable`, `degraded_reason`, `missing`, `suggestions`; phase 4 thêm giá trị `kind` `info` (cả hai không tăng `v`). */
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

/** Một nút trên thẻ. kind quyết định giao diện làm gì: open_forecast (mở Chi tiết hũ, cần jar_code), confirm_salary (mở bước xác nhận lương về), review_unclassified (mở danh sách xem lại), open_obligations (mở màn nghĩa vụ), ask_why (mở chat và gửi `prompt`), snooze ('Để sau'), mute_kind ('Ít nhắc loại này'); phase 5 thêm open_roadmap (mở Lộ trình, bản chờ chọn), open_resilience (mở Nhìn trước), open_profile (mở Hồ sơ, phần nhận xét hành vi). Thẻ có `nudge_id` (bản tin của cổng giá trị) thì snooze và mute_kind gửi `POST /nudges/{nudge_id}/feedback` (outcome snoozed, less_like_this); thẻ không có `nudge_id` (thẻ tất định của GET /overview) chỉ lưu phía giao diện như phase 2. */
export const ProactiveAction = z.object({
  kind: z.enum(["open_forecast", "confirm_salary", "review_unclassified", "open_obligations", "ask_why", "snooze", "mute_kind", "open_roadmap", "open_resilience", "open_profile"]),
  label: z.string().min(1).max(40),
  jar_code: JarCode.optional(),
  prompt: z.string().min(1).max(200).optional(),
})
export type ProactiveAction = z.infer<typeof ProactiveAction>

export const ProactiveCardData = z.object({
  kind: z.enum(["runout_warning", "obligation_due", "salary_pending", "review_needed", "low_data", "roadmap_proposed", "resilience_drop", "behavior_insight"]),
  status: JarStatus,
  title: z.string().min(1).max(80),
  reason: z.string().min(1).max(200),
  jar_code: JarCode.optional(),
  nudge_id: Uuid.optional(),
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

/** Điểm nguyên từ 0 đến 100. */
export const Score = z.int().min(0).max(100)
export type Score = z.infer<typeof Score>

/** Nhóm điểm: weak (yếu), fair (vừa), strong (tốt). Ngưỡng cắt nằm ở cấu hình, không trong mã. Giao diện luôn hiện chữ của nhóm. */
export const ResilienceBand = z.enum(["weak", "fair", "strong"])
export type ResilienceBand = z.infer<typeof ResilienceBand>

/** Bốn thành phần theo thứ tự hiển thị: save (số ngày sống được bằng số dư khả dụng), spend (tỷ lệ chi trên thu và trả đúng hạn), borrow (nghĩa vụ trên thu nhập), plan (tiến độ mục tiêu). */
export const ResilienceComponentKey = z.enum(["save", "spend", "borrow", "plan"])
export type ResilienceComponentKey = z.infer<typeof ResilienceComponentKey>

/** Một đầu vào đã dùng để tính một thành phần. Tiền (`vnd`) và số đếm (`count`) là số nguyên (Pydantic kiểm, JSON Schema chỉ biết `number`); `days` và `ratio` không âm. */
export const ResilienceInput = z.object({
  key: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$")),
  label: z.string().min(1).max(60),
  value: z.number().min(-99999999999999).max(99999999999999),
  unit: z.enum(["vnd", "days", "ratio", "count"]),
})
export type ResilienceInput = z.infer<typeof ResilienceInput>

/** Một thành phần. Không áp dụng được (ví dụ chưa có mục tiêu thì Plan) thì `applicable` sai, không có `score` và `band`, `weight` bằng 0; trọng số của các thành phần áp dụng được chuẩn hóa để cộng lại bằng 1. */
export const ResilienceComponent = z.object({
  key: ResilienceComponentKey,
  label: z.string().min(1).max(40),
  score: Score.optional(),
  weight: z.number().min(0).max(1),
  applicable: z.boolean(),
  band: ResilienceBand.optional(),
  explanation: z.string().min(1).max(200),
  inputs: z.array(ResilienceInput).max(6),
})
export type ResilienceComponent = z.infer<typeof ResilienceComponent>

/** Bất biến (Pydantic và test kiểm): đủ bốn thành phần đúng thứ tự save, spend, borrow, plan; trọng số của các thành phần áp dụng cộng lại bằng 1; `score` bằng trung bình có trọng số (lệch tối đa 1 do làm tròn); `weakest` là thành phần áp dụng có điểm thấp nhất (hòa thì đứng trước). */
export const ResilienceScoreData = z.object({
  score: Score,
  band: ResilienceBand,
  headline: z.string().min(1).max(160),
  app_date: IsoDate,
  computed_at: IsoDateTime,
  components: z.array(ResilienceComponent).min(4).max(4),
  weakest: ResilienceComponentKey,
  previous_score: Score.optional(),
  config_version: z.string().min(1).max(40),
  disclaimer: z.string().min(1).max(160),
  basis: ForecastBasis,
})
export type ResilienceScoreData = z.infer<typeof ResilienceScoreData>

/** Điểm chống chịu 0 đến 100 với bốn thành phần Save, Spend, Borrow, Plan (F4, proposal §11). Tất định: tool `forecast___get_resilience_score` (chat) và `GET /resilience` (màn Nhìn trước) trả CÙNG khối nên hai nơi cùng số. Mọi con số và câu giải thích do code dựng từ đầu vào thật và từ cấu hình trọng số, ngưỡng (`yofina_core/resilience_defaults.json`); LLM không viết. Nhóm điểm (`band`) luôn kèm chữ ở giao diện, không chỉ màu. Điểm này KHÔNG phải điểm tín dụng (`disclaimer`). Id khối `resilience_score:{trace_id}`. */
export const ResilienceScoreBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("resilience_score"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: ResilienceScoreData,
})
export type ResilienceScoreBlock = z.infer<typeof ResilienceScoreBlock>

/** Cú sốc đã áp: bản gọn của một mục trong `shocks.json`. Nhãn và mô tả lấy từ file dữ liệu, không viết trong mã. */
export const ShockSummary = z.object({
  shock_id: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$")),
  kind: z.enum(["income_loss", "expense_increase", "health_event"]),
  label: z.string().min(1).max(60),
  description: z.string().min(1).max(160),
  duration_days: z.int().min(1).max(365).optional(),
})
export type ShockSummary = z.infer<typeof ShockSummary>

/** Điểm một thành phần trước và sau cú sốc. Thành phần không áp dụng thì không có điểm. */
export const StressComponentDelta = z.object({
  key: ResilienceComponentKey,
  score_before: Score.optional(),
  score_after: Score.optional(),
})
export type StressComponentDelta = z.infer<typeof StressComponentDelta>

/** Bất biến (Pydantic và test kiểm): cú sốc không làm điểm tăng; `score_delta` bằng sau trừ trước; đủ bốn thành phần đúng thứ tự; có khoản thiếu thì `status` không phải ok và có `shortfall_from`; `runway_days_emergency` chỉ có khi có `emergency_jar`. */
export const StressResultData = z.object({
  shock: ShockSummary,
  status: JarStatus,
  headline: z.string().min(1).max(160),
  score_before: Score,
  score_after: Score,
  score_delta: z.int().min(-100).max(0),
  band_before: ResilienceBand,
  band_after: ResilienceBand,
  runway_days_total: z.int().min(0).max(400).optional(),
  runway_days_emergency: z.int().min(0).max(400).optional(),
  emergency_jar: ForecastJar.optional(),
  horizon_days: z.int().min(1).max(400),
  shortfall_vnd: Vnd,
  shortfall_from: IsoDate.optional(),
  components: z.array(StressComponentDelta).min(4).max(4),
  method: z.literal("monte_carlo"),
  n_paths: z.int().min(1),
  common_random_numbers: z.literal(true),
  basis: ForecastBasis,
})
export type StressResultData = z.infer<typeof StressResultData>

/** Kết quả một cú sốc (F4): điểm chống chịu trước và sau, số ngày trụ được (toàn bộ ví và riêng hũ Dự phòng), khoản thiếu. Engine áp cú sốc (định nghĩa dạng dữ liệu ở `shocks.json`: mất việc 2 tháng, tiền trọ tăng, ốm một tuần) lên dự báo bằng Monte Carlo cùng dãy số ngẫu nhiên với dự báo nền. Tool `forecast___stress_test` và `POST /resilience/stress` trả CÙNG khối. Trạng thái (`status`) và `headline` luôn có chữ, không chỉ màu. Id khối `stress_result:{trace_id}:{shock_id}`. */
export const StressResultBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("stress_result"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: StressResultData,
})
export type StressResultBlock = z.infer<typeof StressResultBlock>

/** Số phiên bản, tăng dần theo người dùng từ 1. */
export const RoadmapVersion = z.int().min(1).max(10000)
export type RoadmapVersion = z.infer<typeof RoadmapVersion>

/** active (đang dùng; mỗi người dùng tối đa một), proposed (bản mới do hệ thống sinh lại, chờ người dùng chọn 'Dùng bản mới' hay 'Giữ bản cũ'; tối đa một), superseded (đã bị bản khác thay), discarded (người dùng chọn giữ bản cũ nên bản này bị bỏ). */
export const RoadmapVersionStatus = z.enum(["active", "proposed", "superseded", "discarded"])
export type RoadmapVersionStatus = z.infer<typeof RoadmapVersionStatus>

/** Trạng thái một bước: pending (chờ), accepted (đã chấp nhận), rejected (đã từ chối). Giao diện luôn hiện chữ. Chấp nhận KHÔNG tự thực hiện hành động của bước và không đổi số dư. */
export const RoadmapStepStatus = z.enum(["pending", "accepted", "rejected"])
export type RoadmapStepStatus = z.infer<typeof RoadmapStepStatus>

/** initial (lần đầu), behavior_changed (điểm gãy hành vi đã xác nhận), goal_changed, income_changed, forecast_drift (dự báo lệch quá ngưỡng), user_request (người dùng bấm sinh lại), step_edited (người dùng sửa một bước, lưu bản mới, không sinh lại toàn bộ). */
export const RoadmapReasonCode = z.enum(["initial", "behavior_changed", "goal_changed", "income_changed", "forecast_drift", "user_request", "step_edited"])
export type RoadmapReasonCode = z.infer<typeof RoadmapReasonCode>

/** Vì sao có phiên bản này (frame L1: 'hành vi thay đổi'). `text` do code dựng từ sự kiện kích hoạt, không do LLM viết; `detail` là các con số của sự kiện (ví dụ chi Ăn uống mỗi tuần trước và sau). */
export const RoadmapReason = z.object({
  code: RoadmapReasonCode,
  text: z.string().min(1).max(160),
  detail: z.array(ActionChange).max(3).optional(),
  behavior_flag_id: Uuid.optional(),
})
export type RoadmapReason = z.infer<typeof RoadmapReason>

export const RoadmapHorizon = z.object({
  start_date: IsoDate,
  end_date: IsoDate,
})
export type RoadmapHorizon = z.infer<typeof RoadmapHorizon>

/** Một mục tiêu (hũ có `goal_vnd`) so với kế hoạch. Bất biến (Pydantic kiểm): `on_track` thì `shortfall_vnd` bằng 0. */
export const GoalProjection = z.object({
  jar: ForecastJar,
  target_vnd: VndPositive,
  target_date: IsoDate.optional(),
  projected_date: IsoDate.optional(),
  on_track: z.boolean(),
  shortfall_vnd: Vnd,
  monthly_needed_vnd: Vnd,
})
export type GoalProjection = z.infer<typeof GoalProjection>

/** Việc đổi tiền gắn vào bước. Người dùng thực hiện bằng luồng xác nhận (ADR-0002): `POST /confirmations` rồi `POST /actions` với đúng `tool` và `params` (server chuẩn hóa lại và tính bản xem trước). Không chứa `user_id` hay `confirm_token`. */
export const RoadmapStepAction = z.object({
  tool: z.enum(["move_between_jars", "save_jars", "schedule_nudge"]),
  params: z.record(z.string(), z.unknown()),
})
export type RoadmapStepAction = z.infer<typeof RoadmapStepAction>

/** Một bước. `step_id` ổn định trong một phiên bản (cũng dùng làm `option_id` của `POST /feedback`). Bất biến (Pydantic kiểm): `decided_at` có đúng khi `status` khác pending. */
export const RoadmapStep = z.object({
  step_id: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$")),
  kind: z.enum(["set_aside", "adjust_split", "pay_obligation", "cut_spending", "review_goal", "remind"]),
  title: z.string().min(1).max(80),
  reason: z.string().min(1).max(240),
  ai_generated: z.boolean().optional(),
  amount_vnd: VndPositive.optional(),
  jar_code: JarCode.optional(),
  to_jar_code: JarCode.optional(),
  due_date: IsoDate.optional(),
  metrics: z.array(ActionChange).max(4).optional(),
  checked_rules: z.array(z.string().max(64).regex(new RegExp("^[a-z][a-z0-9_]{0,63}$"))).max(8).optional(),
  action: RoadmapStepAction.optional(),
  status: RoadmapStepStatus,
  decided_at: IsoDateTime.optional(),
  edited: z.boolean().optional(),
})
export type RoadmapStep = z.infer<typeof RoadmapStep>

export const RoadmapPhase = z.object({
  phase_id: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$")),
  title: z.string().min(1).max(60),
  summary: z.string().min(1).max(160).optional(),
  start_date: IsoDate,
  end_date: IsoDate,
  steps: z.array(RoadmapStep).min(1).max(8),
})
export type RoadmapPhase = z.infer<typeof RoadmapPhase>

/** Một trong hai lựa chọn nói thẳng khi mục tiêu chưa khả thi (`feasibility` là infeasible). Chọn nó thì gửi `alternative_id` ở `POST /roadmap/regenerate`. */
export const RoadmapAlternative = z.object({
  option_id: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$")),
  kind: z.enum(["delay_goal", "reduce_goal", "cut_discretionary"]),
  label: z.string().min(1).max(60),
  summary: z.string().min(1).max(200),
  jar_code: JarCode.optional(),
  metrics: z.array(ActionChange).max(4).optional(),
})
export type RoadmapAlternative = z.infer<typeof RoadmapAlternative>

/** Số bước theo trạng thái (phải bằng đếm từ `phases`). */
export const RoadmapCounts = z.object({
  pending: z.int().min(0),
  accepted: z.int().min(0),
  rejected: z.int().min(0),
})
export type RoadmapCounts = z.infer<typeof RoadmapCounts>

/** Một phiên bản lộ trình. Bất biến (Pydantic và test kiểm): `step_id` và `phase_id` duy nhất; `counts` đúng; `based_on_version` nhỏ hơn `version`; giai đoạn xếp theo `start_date`; `infeasible` đi với đúng hai `alternatives` và ít nhất một mục tiêu không kịp, `on_track` thì mọi mục tiêu kịp, các trường hợp khác không có `alternatives`. */
export const RoadmapData = z.object({
  roadmap_id: Uuid,
  version: RoadmapVersion,
  status: RoadmapVersionStatus,
  reason: RoadmapReason,
  based_on_version: RoadmapVersion.optional(),
  created_at: IsoDateTime,
  app_date: IsoDate,
  headline: z.string().min(1).max(160),
  feasibility: z.enum(["on_track", "relaxed", "infeasible"]),
  horizon: RoadmapHorizon,
  goals: z.array(GoalProjection).max(8),
  phases: z.array(RoadmapPhase).min(1).max(5),
  alternatives: z.array(RoadmapAlternative).max(2),
  counts: RoadmapCounts,
  rules_version: z.string().min(1).max(40),
  basis: ForecastBasis,
})
export type RoadmapData = z.infer<typeof RoadmapData>

/** Lộ trình theo giai đoạn (F5): mỗi giai đoạn có các bước, mỗi bước có lý do và trạng thái chờ, đã chấp nhận hay đã từ chối. Có phiên bản tăng dần theo người dùng, kèm lý do sinh lại (`reason`). Số trong bước do bộ tối ưu (`planner___optimize_allocation`) tính, không do LLM viết; câu `reason` của bước do Roadmap agent viết và phải qua NumericGrounding và `check_suitability` (vi phạm mức block thì bước bị bỏ). Đọc bằng `planner___get_roadmap` (chat) và `GET /roadmap` (màn Lộ trình) cùng một khối. Lưu lộ trình là thao tác ghi KHÔNG đổi số dư nên không qua token; hành động đổi tiền gắn trong bước (`action`) vẫn qua `POST /confirmations` rồi `POST /actions`. Id khối `roadmap:{trace_id}:v{version}`. */
export const RoadmapBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("roadmap"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: RoadmapData,
})
export type RoadmapBlock = z.infer<typeof RoadmapBlock>

/** Một thay đổi của một bước giữa hai phiên bản. `fields` liệt kê trường đổi (số tiền, ngày, hũ) trước và sau; `reason_after` là 'Vì sao' mới của bước. */
export const RoadmapChange = z.object({
  kind: z.enum(["added", "removed", "changed"]),
  step_id: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$")),
  phase_id: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$")).optional(),
  title: z.string().min(1).max(80),
  fields: z.array(ActionChange).max(6).optional(),
  reason_after: z.string().min(1).max(240).optional(),
})
export type RoadmapChange = z.infer<typeof RoadmapChange>

/** Số bước theo loại thay đổi; `unchanged` là bước giữ nguyên (không liệt kê trong `changes`). */
export const RoadmapDiffCounts = z.object({
  added: z.int().min(0),
  removed: z.int().min(0),
  changed: z.int().min(0),
  unchanged: z.int().min(0),
})
export type RoadmapDiffCounts = z.infer<typeof RoadmapDiffCounts>

/** Bất biến (Pydantic và test kiểm): hai phiên bản khác nhau; `counts.added`, `removed`, `changed` bằng số phần tử cùng loại trong `changes`; mỗi bước tối đa một thay đổi; `can_adopt` đúng khi `to_status` là proposed. */
export const RoadmapDiffData = z.object({
  from_version: RoadmapVersion,
  to_version: RoadmapVersion,
  from_roadmap_id: Uuid,
  to_roadmap_id: Uuid,
  to_status: RoadmapVersionStatus,
  reason: RoadmapReason,
  headline: z.string().min(1).max(160),
  changes: z.array(RoadmapChange).max(30),
  counts: RoadmapDiffCounts,
  can_adopt: z.boolean(),
})
export type RoadmapDiffData = z.infer<typeof RoadmapDiffData>

/** So hai phiên bản lộ trình (frame L3: 'so với bản cũ'): bước thêm, bỏ, đổi, kèm lý do sinh lại của bản mới. Do code dựng từ hai bản đã lưu (so theo `step_id`), không qua LLM. `GET /roadmap/diff` trả khối này. `can_adopt` đúng khi bản mới đang chờ chọn (`proposed`): giao diện hiện 'Dùng bản mới' và 'Giữ bản cũ' (`POST /roadmap/versions/{version}/decision`). Id khối `roadmap_diff:{trace_id}:v{from}-v{to}`. */
export const RoadmapDiffBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("roadmap_diff"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: RoadmapDiffData,
})
export type RoadmapDiffBlock = z.infer<typeof RoadmapDiffBlock>

/** Hũ hiện tại của giao dịch (tên rút gọn). */
export const ReviewJarRef = z.object({
  code: JarCode,
  name: z.string().min(1).max(40),
})
export type ReviewJarRef = z.infer<typeof ReviewJarRef>

/** Một hũ gợi ý. `reason` do code dựng từ tín hiệu đã dùng (ví dụ 'Giống 4 giao dịch trước gửi cho cùng người'), không do LLM viết. */
export const ReviewSuggestion = z.object({
  jar: ForecastJar,
  confidence: Ratio.optional(),
  reason: z.string().min(1).max(80),
})
export type ReviewSuggestion = z.infer<typeof ReviewSuggestion>

/** Một giao dịch cần quyết định. `can_remember` đúng khi có người nhận đã lưu hoặc đối tác để lưu luật 'luôn luôn cho người này' (`assign_jar` với `remember` always). Số tiền dương; hướng nằm ở `kind`. Tên người nhận là dữ liệu của chính người dùng, không đi vào model. */
export const ReviewItem = z.object({
  transaction_id: Uuid,
  occurred_at: IsoDateTime,
  app_date: IsoDate,
  kind: z.enum(["expense", "income"]),
  amount_vnd: VndPositive,
  counterparty: z.string().min(1).max(120).optional(),
  note: z.string().min(1).max(200).optional(),
  tier: z.enum(["auto", "review", "ask"]),
  current_jar: ReviewJarRef.optional(),
  classified_by: z.enum(["user", "type_map", "rule", "embedding", "llm", "seed"]).optional(),
  confidence: Ratio.optional(),
  suggestions: z.array(ReviewSuggestion).max(2),
  can_remember: z.boolean(),
})
export type ReviewItem = z.infer<typeof ReviewItem>

/** Trạng thái câu hỏi gộp của ngày (một câu mỗi ngày mô phỏng): open (đã hỏi, chưa xong), answered (đã xếp hết), skipped (người dùng chọn để sau). */
export const ReviewAsk = z.object({
  ask_date: IsoDate,
  status: z.enum(["open", "answered", "skipped"]),
})
export type ReviewAsk = z.infer<typeof ReviewAsk>

/** Bất biến (Pydantic và test kiểm): `review` chỉ có mục mức review, `daily_ask` chỉ có mức ask và kèm `ask`; `count` không nhỏ hơn số mục đang hiện (danh sách bị cắt ở 50); mỗi giao dịch một lần. */
export const ReviewListData = z.object({
  mode: z.enum(["review", "daily_ask"]),
  headline: z.string().min(1).max(160),
  count: z.int().min(0),
  pending_total_vnd: Vnd,
  items: z.array(ReviewItem).max(50),
  jars: z.array(ForecastJar).max(20),
  ask: ReviewAsk.optional(),
})
export type ReviewListData = z.infer<typeof ReviewListData>

/** Danh sách giao dịch người dùng cần quyết định về hũ (F2 phân hũ tự động), một khối cho hai màn: A1 'Xem lại' (`mode` review: giao dịch đã được tự gán hũ ở mức tin cậy vừa, người dùng soát và sửa bằng một chạm) và A2 hỏi gộp (`mode` daily_ask: giao dịch chưa xếp được hũ, hỏi MỘT lần mỗi ngày kèm tối đa 2 gợi ý). Ba mức tin cậy (`tier`): auto (tự gán, không cần hỏi, không vào danh sách), review (tự gán và vào 'Xem lại'), ask (vào hũ Chưa phân loại và hỏi gộp); ngưỡng nằm ở cấu hình, hiệu chỉnh trên dữ liệu. Số tiền là số của sổ cái (không phải ước lượng) nên khối không có `basis`. Sửa hũ dùng lại đường `assign_jar` qua `POST /confirmations` và `POST /actions` (`remember` once hoặc always); xác nhận 'đúng rồi' cho mục mức review là `assign_jar` với chính hũ hiện tại (xóa cờ cần xem lại, không chuyển tiền). Id khối `review_list:{trace_id}:{mode}`. */
export const ReviewListBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("review_list"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: ReviewListData,
})
export type ReviewListBlock = z.infer<typeof ReviewListBlock>

/** Loại nhận xét: payday_cycle (chi dồn theo nhịp lương), weekday_pattern (ngày trong tuần), time_of_day (giờ trong ngày, chỉ tính giao dịch trong ví vì dòng nạp ngoài ví không có giờ), bnpl_usage (mức dùng Trả sau), category_trend (một hũ tăng hoặc giảm rõ), spending_cluster (nhóm hành vi của phân cụm đơn giản). */
export const BehaviorInsightKind = z.enum(["payday_cycle", "weekday_pattern", "time_of_day", "bnpl_usage", "category_trend", "spending_cluster"])
export type BehaviorInsightKind = z.infer<typeof BehaviorInsightKind>

/** Một con số làm bằng chứng, lấy thẳng từ sổ cái trong cửa sổ `period`. Đơn vị: vnd (số nguyên VND), percent (0..100), ratio (0..1), days, count (số nguyên không âm), hour (giờ 0..23 theo múi giờ của ứng dụng), weekday (thứ theo ISO, 1 là thứ Hai, 7 là Chủ nhật). Ràng buộc theo đơn vị do Pydantic kiểm (JSON Schema chỉ biết `number`). */
export const BehaviorEvidence = z.object({
  key: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$")),
  label: z.string().min(1).max(80),
  value: z.number().min(-99999999999999).max(99999999999999),
  unit: z.enum(["vnd", "percent", "ratio", "days", "count", "hour", "weekday"]),
  period_from: IsoDate.optional(),
  period_to: IsoDate.optional(),
})
export type BehaviorEvidence = z.infer<typeof BehaviorEvidence>

/** Một nhận xét. `headline` là câu tiếng Việt do model nhỏ tóm tắt (khi `ai_generated` đúng) hoặc do mẫu câu của code điền, và mọi số trong đó có trong `evidence`. `jar_code` khi nhận xét gắn với một hũ. */
export const BehaviorInsight = z.object({
  insight_id: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$")),
  kind: BehaviorInsightKind,
  headline: z.string().min(1).max(160),
  detail: z.string().min(1).max(280).optional(),
  jar_code: JarCode.optional(),
  evidence: z.array(BehaviorEvidence).min(1).max(6),
  confidence: ConfidenceBand,
  ai_generated: z.boolean(),
})
export type BehaviorInsight = z.infer<typeof BehaviorInsight>

/** MỘT việc cần làm đi kèm nhận xét. `action` (tùy chọn) dùng đúng hình dạng hành động của bước lộ trình: người dùng thực hiện bằng `POST /confirmations` rồi `POST /actions` (ADR-0002); bấm vào không tự ghi gì. */
export const BehaviorNextStep = z.object({
  label: z.string().min(1).max(80),
  reason: z.string().min(1).max(200),
  action: RoadmapStepAction.optional(),
})
export type BehaviorNextStep = z.infer<typeof BehaviorNextStep>

/** Đặc trưng đã tính (đầu vào của nhận xét, để truy vết). `history_days` là số ngày lịch sử đã dùng. Tỷ lệ là phần chi tiêu (0..1) trong cửa sổ. */
export const BehaviorFeatures = z.object({
  history_days: z.int().min(0),
  avg_daily_spend_vnd: Vnd.optional(),
  first_week_after_payday_share: Ratio.optional(),
  weekend_share: Ratio.optional(),
  evening_share: Ratio.optional(),
  top_weekday: z.int().min(1).max(7).optional(),
  bnpl_purchases_per_month: z.number().min(0).max(1000).optional(),
  bnpl_share: Ratio.optional(),
})
export type BehaviorFeatures = z.infer<typeof BehaviorFeatures>

/** Nhóm hành vi của phân cụm đơn giản (k-means trên đặc trưng chuẩn hóa hoặc luật ngưỡng; luồng p5-behavior chọn). */
export const BehaviorSegment = z.object({
  segment_id: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$")),
  label: z.string().min(1).max(60),
})
export type BehaviorSegment = z.infer<typeof BehaviorSegment>

/** Hồ sơ hành vi của người dùng ở ngày mô phỏng `app_date` (một dòng `behavior_profiles`). `ready` sai khi chưa đủ lịch sử hoặc batch đêm chưa chạy: khi đó không có nhận xét và `headline` nói cần thêm bao nhiêu ngày (`min_history_days`). Đây không phải lỗi. `ready` đúng thì có `computed_at`, `config_version`, `features`, `next_step` (MỘT việc cần làm của cả hồ sơ) và ít nhất một nhận xét (Pydantic kiểm). Cùng `data` cho tool `forecast___get_behavior_profile` và `GET /profile/behavior`. */
export const BehaviorProfileData = z.object({
  ready: z.boolean(),
  app_date: IsoDate,
  computed_at: IsoDateTime.optional(),
  config_version: z.string().min(1).max(40).optional(),
  headline: z.string().min(1).max(160),
  history_days: z.int().min(0),
  min_history_days: z.int().min(1).optional(),
  features: BehaviorFeatures.optional(),
  segment: BehaviorSegment.optional(),
  insights: z.array(BehaviorInsight).max(6),
  next_step: BehaviorNextStep.optional(),
})
export type BehaviorProfileData = z.infer<typeof BehaviorProfileData>

export const BehaviorInsightData = z.object({
  insight: BehaviorInsight,
  next_step: BehaviorNextStep,
  app_date: IsoDate,
  computed_at: IsoDateTime,
  history_days: z.int().min(0),
  config_version: z.string().min(1).max(40).optional(),
})
export type BehaviorInsightData = z.infer<typeof BehaviorInsightData>

/** MỘT nhận xét hành vi chi tiêu (F7) kèm bằng chứng số và MỘT việc cần làm, trong chat và ở màn Hồ sơ. Nhận xét lấy từ hồ sơ hành vi do batch đêm tính (bảng `behavior_profiles`, migration 0053; tool `forecast___get_behavior_profile`, `GET /profile/behavior`). Mỗi số trong câu nhận xét có trong `evidence` (đã qua NumericGrounding lúc batch đêm tóm tắt); số trong khối do code dựng, LLM không viết. Id khối `behavior_insight:{trace_id}:{insight_id}`. `$defs` ở đây cũng là hình dạng của hồ sơ hành vi (`BehaviorProfileData`) cho tool và REST. */
export const BehaviorInsightBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("behavior_insight"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: BehaviorInsightData,
})
export type BehaviorInsightBlock = z.infer<typeof BehaviorInsightBlock>

/** Một nguồn của biểu phí: `source_name`, `source_url`, `effective_from` chép nguyên từ các `FeeLine` có cùng ba giá trị đó; `fee_types` là loại phí của các dòng ấy, theo thứ tự trong kết quả tool. `excerpt` (tùy chọn) là câu ngắn chép nguyên từ dữ liệu bảng phí (`condition_note` của dòng khi nguồn chỉ có một loại phí), không do model viết. */
export const CitationItem = z.object({
  fee_types: z.array(z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,39}$"))).min(1).max(20),
  source_name: z.string().min(1).max(200),
  source_url: z.string().max(500).regex(new RegExp("^https://")),
  effective_from: IsoDate,
  excerpt: z.string().min(1).max(200).optional(),
})
export type CitationItem = z.infer<typeof CitationItem>

/** Sản phẩm của biểu phí (`product_code`, `product_label` của `FeeScheduleData`) và 1 đến 5 nguồn. Mỗi loại phí thuộc đúng một nguồn; mỗi bộ (tên nguồn, đường dẫn, ngày hiệu lực) một mục. */
export const CitationData = z.object({
  product_code: z.string().regex(new RegExp("^[a-z][a-z0-9_]{0,31}$")),
  product_label: z.string().min(1).max(60),
  items: z.array(CitationItem).min(1).max(5),
})
export type CitationData = z.infer<typeof CitationData>

/** Trích dẫn nguồn của biểu phí Trả sau (mô phỏng) cho một câu trả lời về phí. Dựng TỪ CHÍNH kết quả `knowledge___get_fee_schedule` (bảng có cấu trúc `fee_schedules`): mỗi mục là một nguồn (tên nguồn, đường dẫn nguồn, ngày hiệu lực) kèm các loại phí lấy từ nguồn đó. Không có tìm kiếm tài liệu (chủ dự án cắt luồng RAG ngày 24/11). Số tiền KHÔNG nằm trong khối này: số để tính và để nói vẫn là `amount_vnd` của `FeeLine`. Agent dựng bằng `build_citation(result=...)` (LLM không viết tên nguồn, đường dẫn hay câu trích). Id khối `citation:{trace_id}`. */
export const CitationBlock = z.object({
  v: SchemaVersion,
  id: BlockId,
  type: z.literal("citation"),
  trace_id: TraceId,
  fallback_text: FallbackText,
  source: Source,
  data: CitationData,
})
export type CitationBlock = z.infer<typeof CitationBlock>

/** Hợp của các khối đã biết (hai mươi ba), phân biệt theo `type`. Frontend không parse cả mảng bằng schema này: nó parse từng khối theo registry và hiện fallback_text khi type lạ hoặc sai schema. */
export const Block = z.discriminatedUnion('type', [JarSummaryBlock, ConfirmBlock, ReceiptBlock, NoticeBlock, ForecastTimelineBlock, ProactiveCardBlock, ConfirmActionBlock, ReceiptActionBlock, AffordabilityCardBlock, ObligationImpactBlock, OptionsBlock, ExplainBlock, ClarifyBlock, SuggestionsBlock, IngestReviewBlock, CoverageChangeBlock, ResilienceScoreBlock, StressResultBlock, RoadmapBlock, RoadmapDiffBlock, ReviewListBlock, BehaviorInsightBlock, CitationBlock])
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
  resilience_score: ResilienceScoreBlock,
  stress_result: StressResultBlock,
  roadmap: RoadmapBlock,
  roadmap_diff: RoadmapDiffBlock,
  review_list: ReviewListBlock,
  behavior_insight: BehaviorInsightBlock,
  citation: CitationBlock,
} as const

export type AnyBlockType = keyof typeof blockSchemas
export const ALL_BLOCK_TYPES = ["jar_summary", "confirm", "receipt", "notice", "forecast_timeline", "proactive_card", "confirm_action", "receipt_action", "affordability_card", "obligation_impact", "options", "explain", "clarify", "suggestions", "ingest_review", "coverage_change", "resilience_score", "stress_result", "roadmap", "roadmap_diff", "review_list", "behavior_insight", "citation"] as const

/** Khối mà registry frontend đã đăng ký (xem scripts/gen_contracts.mjs, REGISTERED_BY_FRONTEND). */
export const BLOCK_TYPES = ["jar_summary", "confirm", "receipt", "notice", "forecast_timeline", "proactive_card", "confirm_action", "receipt_action", "affordability_card", "obligation_impact", "options", "explain", "clarify", "suggestions", "ingest_review", "coverage_change", "resilience_score", "stress_result", "roadmap", "roadmap_diff", "review_list"] as const
export type BlockType = (typeof BLOCK_TYPES)[number]
