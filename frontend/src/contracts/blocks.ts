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

export const NoticeData = z.object({
  kind: z.enum(["out_of_scope", "degraded", "low_data", "error"]),
  title: z.string().min(1).max(80),
  message: z.string().min(1).max(280),
  code: z.string().regex(new RegExp("^[A-Z][A-Z0-9_]*$")).optional(),
})
export type NoticeData = z.infer<typeof NoticeData>

/** Thông báo trạng thái: ngoài phạm vi, chế độ rút gọn khi hệ thống chạm giới hạn, dữ liệu ít, lỗi. Không chứa số liệu tài chính. */
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
})
export type ForecastTimelineData = z.infer<typeof ForecastTimelineData>

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

/** Tool ghi dùng khối này (tên ngắn, không có tiền tố target). */
export const ConfirmActionTool = z.enum(["record_transaction", "assign_jar", "update_profile", "save_jars", "confirm_salary"])
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
})
export type ReceiptActionData = z.infer<typeof ReceiptActionData>

/** Biên nhận của thao tác ghi KHÔNG phải chuyển hũ (record_transaction, assign_jar, update_profile, save_jars, confirm_salary). Trả bởi POST /actions (cùng với `receipt` của chuyển hũ) và dựng lại từ kết quả tool. Id khối `receipt:{tool}:{reference_id}`, hoặc `receipt:{tool}:{trace_id}` khi thao tác không có reference_id (kèm tool vì assign_jar và record_transaction dùng chung id giao dịch). */
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

/** Hợp của các khối đã biết, phân biệt theo `type`. Frontend không parse cả mảng bằng schema này: nó parse từng khối theo registry và hiện fallback_text khi type lạ hoặc sai schema. */
export const Block = z.discriminatedUnion('type', [JarSummaryBlock, ConfirmBlock, ReceiptBlock, NoticeBlock, ForecastTimelineBlock, ProactiveCardBlock, ConfirmActionBlock, ReceiptActionBlock])
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
} as const

export type AnyBlockType = keyof typeof blockSchemas
export const ALL_BLOCK_TYPES = ["jar_summary", "confirm", "receipt", "notice", "forecast_timeline", "proactive_card", "confirm_action", "receipt_action"] as const

/** Khối mà registry frontend đã đăng ký (xem scripts/gen_contracts.mjs, REGISTERED_BY_FRONTEND). */
export const BLOCK_TYPES = ["jar_summary", "confirm", "receipt", "notice", "forecast_timeline", "proactive_card", "confirm_action", "receipt_action"] as const
export type BlockType = (typeof BLOCK_TYPES)[number]
