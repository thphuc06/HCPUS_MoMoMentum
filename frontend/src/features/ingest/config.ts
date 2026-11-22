import { createContext, useContext } from 'react'
import type { IngestSourceKind } from '@/api/ingestSchemas'

// Cấu hình phía giao diện của màn Nạp dữ liệu. Giới hạn tệp ở đây chỉ để báo sớm cho người dùng, khớp mặc định của
// `yofina_core.ingest.IngestSettings` (contracts/README.md, mục "Cấu hình"). SERVER mới là nơi quyết: sau `POST /ingest/uploads`
// giao diện kiểm lại theo `max_bytes` và `mime_types` server trả, và S3 ép `content-length-range` cùng `Content-Type`.

export type SourceLimits = { maxBytes: number; mimeTypes: readonly string[] }

export const DEFAULT_LIMITS: Record<IngestSourceKind, SourceLimits> = {
  image: { maxBytes: 3_750_000, mimeTypes: ['image/png', 'image/jpeg', 'image/webp'] },
  csv: { maxBytes: 2_000_000, mimeTypes: ['text/csv', 'application/vnd.ms-excel'] },
}

/** `accept` của ô chọn tệp. */
export const ACCEPT_IMAGE = 'image/png,image/jpeg,image/webp'
export const ACCEPT_CSV = '.csv,text/csv'

/** Hỏi tiến độ: lần đầu ngay sau khi tải lên, rồi 1,5 s, lùi dần x1,5 tới 5 s; quá 90 s thì báo "lâu hơn thường lệ". */
export type PollTiming = { firstDelayMs: number; delayMs: number; maxDelayMs: number; backoff: number; timeoutMs: number }
export const DEFAULT_POLL: PollTiming = { firstDelayMs: 0, delayMs: 1_500, maxDelayMs: 5_000, backoff: 1.5, timeoutMs: 90_000 }

/** Nhịp hỏi tiến độ của màn Nạp dữ liệu; mặc định là DEFAULT_POLL (test thu ngắn bằng Provider). */
export const IngestPollContext = createContext<PollTiming>(DEFAULT_POLL)
export const useIngestPollTiming = () => useContext(IngestPollContext)

/** Thời gian chờ khi tải tệp thẳng lên S3. */
export const UPLOAD_TIMEOUT_MS = 60_000

/** Số ngày tệp gốc được giữ (bucket có lifecycle xóa sau thời gian này), hiện ở ô đồng ý. */
export const RETENTION_DAYS = 30
