import { z } from 'zod'
import { IngestJar, IngestJobStatus, IsoDateTime, JarCode } from '@/contracts/blocks'

// Zod của REST `/ingest/*` (phase 5, F6) theo contracts/rest/openapi.yaml (IngestUploadRequest, IngestUploadResponse,
// IngestJobResponse, IngestRowJarRequest, IngestRowJarResponse, ConfirmRowsParams). Phía đọc dễ tính (z.object bỏ trường lạ).
// `review` và `coverage_change` của job giữ nguyên dạng thô: nơi vẽ parse bằng schema khối và hiện fallback_text khi sai,
// nên một khối hỏng không làm hỏng cả phản hồi tiến độ.

const Uuid = z.string().regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/)

export const IngestSourceKind = z.enum(['image', 'csv'])
export type IngestSourceKind = z.infer<typeof IngestSourceKind>

export const IngestUploadRequest = z.object({
  source_kind: IngestSourceKind,
  mime: z.string().min(3).max(100),
  size_bytes: z.int().min(1),
  consent: z.boolean().optional(),
})
export type IngestUploadRequest = z.infer<typeof IngestUploadRequest>

/**
 * URL tải lên: hợp đồng ép `https://`. Đường dẫn tương đối cùng nguồn (bắt đầu bằng một `/`) cũng nhận, để máy chủ giả của
 * `npm run dev:mock` dùng được; nó không thể trỏ ra máy chủ khác nên không mở thêm chỗ rò dữ liệu.
 */
const UploadUrl = z.string().max(2048).regex(/^(https:\/\/|\/(?!\/))/)

export const IngestUploadResponse = z.object({
  job_id: Uuid,
  key: z.string().min(1).max(512),
  url: UploadUrl,
  fields: z.record(z.string(), z.string()),
  expires_at: IsoDateTime,
  max_bytes: z.int().min(1),
  mime_types: z.array(z.string()).min(1).max(10),
})
export type IngestUploadResponse = z.infer<typeof IngestUploadResponse>

export const IngestJobResponse = z.object({
  job_id: Uuid,
  status: IngestJobStatus,
  source_kind: IngestSourceKind,
  progress: z.int().min(0).max(100),
  rows_total: z.int().min(0),
  /** Dễ tính: mã lạ (server mới hơn) vẫn đọc được, nơi hiển thị dùng `error_message` hoặc câu chung. */
  error_code: z.string().max(64).optional(),
  error_message: z.string().min(1).max(280).optional(),
  created_at: IsoDateTime,
  updated_at: IsoDateTime,
  finished_at: IsoDateTime.optional(),
  review: z.unknown().optional(),
  coverage_change: z.unknown().optional(),
})
export type IngestJobResponse = z.infer<typeof IngestJobResponse>

/** Một phần tử của `GET /ingest/jobs` (IngestJobSummary): như IngestJobResponse nhưng không có `review`, `coverage_change`. */
export const IngestJobSummary = IngestJobResponse.omit({ review: true, coverage_change: true })
export type IngestJobSummary = z.infer<typeof IngestJobSummary>

export const IngestJobListResponse = z.object({ jobs: z.array(IngestJobSummary).max(20) })
export type IngestJobListResponse = z.infer<typeof IngestJobListResponse>

export const IngestRowJarRequest = z.object({ jar: JarCode })
export type IngestRowJarRequest = z.infer<typeof IngestRowJarRequest>

export const IngestRowJarResponse = z.object({
  row_id: Uuid,
  suggested_jar: IngestJar,
  jar_source: z.literal('user'),
})
export type IngestRowJarResponse = z.infer<typeof IngestRowJarResponse>

/** Tham số của `confirm_rows` (server chuẩn hóa lại: sắp xếp, bỏ `jar` rỗng; xem ConfirmRowsParams). */
export type ConfirmRowsParams = {
  job_id: string
  rows: Array<{ row_id: string; jar?: string }>
  reject_row_ids: string[]
}

/** Trạng thái kết thúc của polling: tới đây thì không hỏi lại nữa (`review` chờ người dùng, không đổi nếu không ai làm gì). */
export const INGEST_STOP_STATUSES: ReadonlySet<IngestJobResponse['status']> = new Set(['review', 'done', 'failed', 'rejected'])
