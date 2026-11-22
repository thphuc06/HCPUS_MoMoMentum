import { ApiError } from '@/api/errors'
import type { IngestSourceKind, IngestUploadResponse } from '@/api/ingestSchemas'
import { UPLOAD_TIMEOUT_MS, type SourceLimits } from './config'

/**
 * MIME khai báo cho server: lấy `file.type`; trình duyệt Windows có thể để trống (hoặc ghi `application/vnd.ms-excel`) với
 * tệp `.csv`, nên CSV không có loại thì đoán theo đuôi. Server so lại với danh sách cho phép và S3 ép đúng giá trị này.
 */
export function mimeOf(file: File, kind: IngestSourceKind): string {
  if (file.type) return file.type
  if (kind === 'csv' && /\.csv$/i.test(file.name)) return 'text/csv'
  return 'application/octet-stream'
}

/** Kiểm sớm ở máy người dùng (server vẫn kiểm lại): trả mã lỗi hợp đồng nếu sai loại hoặc quá lớn. */
export function checkFile(file: File, kind: IngestSourceKind, limits: SourceLimits): 'INGEST_UNSUPPORTED_TYPE' | 'INGEST_TOO_LARGE' | null {
  if (!limits.mimeTypes.includes(mimeOf(file, kind))) return 'INGEST_UNSUPPORTED_TYPE'
  if (file.size <= 0 || file.size > limits.maxBytes) return 'INGEST_TOO_LARGE'
  return null
}

/**
 * Tải tệp thẳng lên S3 bằng presigned POST: mọi trường `fields` đúng thứ tự server trả, rồi `file` CUỐI CÙNG (S3 bỏ qua
 * trường đứng sau `file`). Không gửi JWT hay header nào khác tới S3; `Content-Type` multipart do trình duyệt tự đặt.
 */
export async function uploadToS3(target: Pick<IngestUploadResponse, 'url' | 'fields'>, file: File, opts: { signal?: AbortSignal; fetchImpl?: typeof fetch } = {}): Promise<void> {
  const form = new FormData()
  for (const [k, v] of Object.entries(target.fields)) form.append(k, v)
  form.append('file', file)
  const ctrl = new AbortController()
  const onAbort = () => ctrl.abort()
  opts.signal?.addEventListener('abort', onAbort)
  const timer = setTimeout(() => ctrl.abort(), UPLOAD_TIMEOUT_MS)
  const doFetch = opts.fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a))
  let res: Response
  try {
    res = await doFetch(target.url, { method: 'POST', body: form, signal: ctrl.signal })
  } catch {
    throw new ApiError(ctrl.signal.aborted && !opts.signal?.aborted ? 'TIMEOUT' : 'UPLOAD_FAILED', 0)
  } finally {
    clearTimeout(timer)
    opts.signal?.removeEventListener('abort', onAbort)
  }
  // S3 trả 204 (mặc định) hoặc 201/200 tùy `success_action_status`. Lỗi là XML có <Code>: vượt content-length-range là
  // EntityTooLarge; còn lại (chữ ký hết hạn, sai policy) coi là tải lên thất bại, xin URL mới bằng cách thử lại.
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(/<Code>EntityTooLarge<\/Code>/.test(text) ? 'INGEST_TOO_LARGE' : 'UPLOAD_FAILED', res.status)
  }
}
