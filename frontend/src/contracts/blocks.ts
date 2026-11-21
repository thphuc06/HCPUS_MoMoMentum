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

/** Hợp của các khối đã biết, phân biệt theo `type`. Frontend không parse cả mảng bằng schema này: nó parse từng khối theo registry và hiện fallback_text khi type lạ hoặc sai schema. */
export const Block = z.discriminatedUnion('type', [JarSummaryBlock, ConfirmBlock, ReceiptBlock, NoticeBlock])
export type Block = z.infer<typeof Block>

/** type -> schema, thứ tự như contracts/blocks/block.schema.json. */
export const blockSchemas = {
  jar_summary: JarSummaryBlock,
  confirm: ConfirmBlock,
  receipt: ReceiptBlock,
  notice: NoticeBlock,
} as const

export type BlockType = keyof typeof blockSchemas
export const BLOCK_TYPES = ["jar_summary", "confirm", "receipt", "notice"] as const
