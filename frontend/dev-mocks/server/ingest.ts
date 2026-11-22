// CHỈ cho `npm run dev:mock`: REST giả của `/ingest/*` (phase 5, F6) và nơi nhận tệp thay cho S3, có trạng thái trong bộ nhớ
// theo email. KHÔNG phải server thật, KHÔNG vào bundle production. Số liệu lấy từ contracts/fixtures (bảng duyệt, độ phủ).
// Thử lỗi: tệp nhỏ hơn 2 KB thành `rejected` với INGEST_NOT_FINANCIAL; nạp lại đúng kích thước + loại của một lần còn sống
// thành `rejected` với INGEST_DUPLICATE_FILE. Lần đầu mỗi nguồn (ảnh, CSV) đòi `consent: true`.
import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import type { Ctx, Reply } from './wallet.ts'

const FIX = path.resolve(import.meta.dirname, '../../../contracts/fixtures')
const fixture = (rel: string) => JSON.parse(readFileSync(path.join(FIX, rel), 'utf8')) as any
const nowIso = () => new Date().toISOString().replace(/\.\d+Z$/, 'Z')

const LIMITS: Record<'image' | 'csv', { max: number; mimes: string[] }> = {
  image: { max: 3_750_000, mimes: ['image/png', 'image/jpeg', 'image/webp'] },
  csv: { max: 2_000_000, mimes: ['text/csv', 'application/vnd.ms-excel'] },
}

/** Đường nhận tệp thay S3 (cùng nguồn với dev server, không cần Bearer như S3 thật). */
export const MOCK_S3_PREFIX = '/mock-s3/'

type Job = {
  id: string
  email: string
  kind: 'image' | 'csv'
  mime: string
  size: number
  status: string
  uploadedAt: number | null
  createdAt: string
  error?: { code: string; message: string }
  review: any | null
  coverage: any | null
}

const jobs = new Map<string, Job>()
const consents = new Map<string, Set<string>>()
const tokens = new Map<string, { jobId: string; params: any; used: boolean }>()

const ok = (body: unknown): Reply => ({ status: 200, body })
const fail = (status: number, code: string, message: string): Reply => ({ status, body: { error: { code, message } } })

function reviewFor(job: Job): any {
  const b = fixture('blocks/valid/ingest_review.review.json')
  b.id = `ingest_review:${job.id}`
  b.data.job_id = job.id
  b.data.source_kind = job.kind
  b.source = { tool: 'rest:GET /ingest/jobs/{job_id}', as_of: nowIso(), app_date: b.source.app_date }
  // id dòng riêng cho từng lần nạp (fixture dùng chung một bộ id)
  for (const r of b.data.rows) r.row_id = randomUUID()
  return b
}

function view(job: Job) {
  // Tiến độ giả theo thời gian kể từ lúc "S3" nhận tệp: queued ~1 s, processing tới ~4 s, rồi review.
  if (job.uploadedAt !== null && (job.status === 'queued' || job.status === 'processing')) {
    const t = Date.now() - job.uploadedAt
    if (job.size < 2_000) {
      job.status = 'rejected'
      job.error = { code: 'INGEST_NOT_FINANCIAL', message: 'Ảnh này không phải sao kê hay hóa đơn nên không đọc được dòng nào.' }
    } else if (t > 4_000) {
      job.status = 'review'
      job.review = reviewFor(job)
    } else if (t > 1_000) job.status = 'processing'
  }
  const progress = job.status === 'awaiting_upload' ? 0 : job.status === 'queued' ? 5 : job.status === 'processing' ? Math.min(95, Math.round(((Date.now() - job.uploadedAt!) / 4_000) * 100)) : 100
  const finished = ['done', 'failed', 'rejected'].includes(job.status)
  return {
    job_id: job.id,
    status: job.status,
    source_kind: job.kind,
    progress,
    rows_total: job.review?.data.rows_total ?? 0,
    ...(job.error ? { error_code: job.error.code, error_message: job.error.message } : {}),
    created_at: job.createdAt,
    updated_at: nowIso(),
    ...(finished ? { finished_at: nowIso() } : {}),
    ...(job.review ? { review: job.review } : {}),
    ...(job.coverage ? { coverage_change: job.coverage } : {}),
  }
}

/** Nhận tệp ở `/mock-s3/<job_id>` (multipart, không đọc nội dung). */
export function receiveUpload(jobId: string): Reply {
  const job = jobs.get(jobId)
  if (!job || job.status !== 'awaiting_upload') return { status: 403, body: '<Error><Code>AccessDenied</Code></Error>' }
  const dup = [...jobs.values()].find((j) => j !== job && j.email === job.email && j.size === job.size && j.mime === job.mime && !['failed', 'rejected'].includes(j.status) && j.uploadedAt !== null)
  job.uploadedAt = Date.now()
  job.status = 'queued'
  if (dup) {
    job.status = 'rejected'
    job.error = { code: 'INGEST_DUPLICATE_FILE', message: 'Tệp này đã được nạp ở một lần khác.' }
  }
  return { status: 204, body: undefined }
}

export function handleIngest(c: Ctx): Reply | null {
  const { method, path: p } = c
  if (method === 'POST' && p === '/ingest/uploads') {
    const b = c.body ?? {}
    const lim = LIMITS[b.source_kind as 'image' | 'csv']
    if (!lim) return fail(400, 'PARAMS_INVALID', 'source_kind phải là image hoặc csv.')
    if (!lim.mimes.includes(b.mime)) return fail(415, 'INGEST_UNSUPPORTED_TYPE', `Hỗ trợ: ${lim.mimes.join(', ')}.`)
    if (!(b.size_bytes > 0) || b.size_bytes > lim.max) return fail(413, 'INGEST_TOO_LARGE', `Tối đa ${lim.max} byte.`)
    const given = consents.get(c.email) ?? new Set<string>()
    if (!given.has(b.source_kind) && b.consent !== true) return fail(403, 'CONSENT_REQUIRED', 'Cần đồng ý trước.')
    given.add(b.source_kind)
    consents.set(c.email, given)
    const id = randomUUID()
    jobs.set(id, { id, email: c.email, kind: b.source_kind, mime: b.mime, size: b.size_bytes, status: 'awaiting_upload', uploadedAt: null, createdAt: nowIso(), review: null, coverage: null })
    const f = fixture('rest/IngestUploadResponse.image.json')
    const key = `mock/${id}`
    return ok({
      ...f,
      job_id: id,
      key,
      url: `${MOCK_S3_PREFIX}${id}`,
      fields: { ...f.fields, key, 'Content-Type': b.mime },
      expires_at: new Date(Date.now() + 300_000).toISOString().replace(/\.\d+Z$/, 'Z'),
      max_bytes: lim.max,
      mime_types: [...lim.mimes],
    })
  }
  const jm = /^\/ingest\/jobs\/([0-9a-f-]{36})$/.exec(p)
  if (method === 'GET' && jm) {
    const job = jobs.get(jm[1]!)
    if (!job || job.email !== c.email) return fail(404, 'INGEST_JOB_NOT_FOUND', 'Không có lần nạp này.')
    return ok(view(job))
  }
  const rm = /^\/ingest\/rows\/([0-9a-f-]{36})\/jar$/.exec(p)
  if (method === 'POST' && rm) {
    for (const job of jobs.values()) {
      if (job.email !== c.email || !job.review) continue
      const row = job.review.data.rows.find((r: any) => r.row_id === rm[1])
      if (!row) continue
      if (job.status !== 'review' || row.kind !== 'expense' || !['auto_added', 'pending'].includes(row.review_status)) return fail(409, 'INGEST_JOB_NOT_READY', 'Dòng không còn mở.')
      const jar = job.review.data.jars.find((j: any) => j.code === c.body?.jar)
      if (!jar) return fail(404, 'JAR_NOT_FOUND', 'Không có hũ này.')
      row.suggested_jar = jar
      row.jar_source = 'user'
      row.jar_confidence = 1
      return ok({ row_id: row.row_id, suggested_jar: jar, jar_source: 'user' })
    }
    return fail(404, 'INGEST_JOB_NOT_FOUND', 'Không có dòng này.')
  }
  if (method === 'POST' && p === '/ingest/confirmations') {
    const params = c.body?.params ?? {}
    const job = jobs.get(params.job_id)
    if (c.body?.tool !== 'confirm_rows') return fail(400, 'PARAMS_INVALID', 'Chỉ nhận confirm_rows.')
    if (!job || job.email !== c.email) return fail(404, 'INGEST_JOB_NOT_FOUND', 'Không có lần nạp này.')
    if (job.status !== 'review') return fail(409, 'INGEST_JOB_NOT_READY', 'Lần nạp đã chốt hoặc chưa đọc xong.')
    const rows = (params.rows ?? []) as Array<{ row_id: string; jar?: string }>
    const norm = { job_id: job.id, rows: [...rows].sort((a, b) => (a.row_id < b.row_id ? -1 : 1)), reject_row_ids: [...(params.reject_row_ids ?? [])].sort() }
    const token = `${randomUUID().replace(/-/g, '')}.${randomUUID().slice(0, 8)}`
    tokens.set(token, { jobId: job.id, params: norm, used: false })
    const byId = new Map(job.review.data.rows.map((r: any) => [r.row_id, r]))
    const spend = rows.reduce((s, r) => s + ((byId.get(r.row_id) as any)?.kind === 'expense' ? (byId.get(r.row_id) as any).amount_vnd : 0), 0)
    return ok({
      confirm_token: token,
      expires_at: new Date(Date.now() + 120_000).toISOString().replace(/\.\d+Z$/, 'Z'),
      ttl_seconds: 120,
      tool: 'confirm_rows',
      params: norm,
      params_hash: 'a'.repeat(64),
      preview: {
        summary: `Thêm ${rows.length} dòng ngoài ví vào lịch sử chi tiêu`,
        changes: [
          { label: 'Dòng thêm', after: `${rows.length} dòng` },
          { label: 'Dòng bỏ', after: `${norm.reject_row_ids.length} dòng` },
          { label: 'Chi ngoài ví', after: `${spend.toLocaleString('vi-VN')} ₫` },
          { label: 'Số dư hũ', after: 'không đổi' },
        ],
      },
    })
  }
  if (method === 'POST' && p === '/ingest/actions') {
    const t = tokens.get(c.body?.confirm_token)
    if (!c.body?.confirm_token) return fail(428, 'NEEDS_CONFIRMATION', 'Cần xác nhận.')
    if (!t) return fail(403, 'TOKEN_INVALID', 'Token không hợp lệ.')
    if (t.used) return fail(409, 'TOKEN_REUSED', 'Token đã dùng.')
    if (JSON.stringify(t.params) !== JSON.stringify(c.body.params)) return fail(409, 'PARAMS_MISMATCH', 'Tham số lệch.')
    const job = jobs.get(t.jobId)!
    if (job.status !== 'review') return fail(409, 'INGEST_JOB_NOT_READY', 'Lần nạp đã chốt.')
    t.used = true
    const add = new Map((t.params.rows as Array<{ row_id: string; jar?: string }>).map((r) => [r.row_id, r]))
    const rej = new Set<string>(t.params.reject_row_ids)
    for (const r of job.review.data.rows) {
      if (add.has(r.row_id)) {
        const jar = job.review.data.jars.find((j: any) => j.code === add.get(r.row_id)!.jar)
        if (jar) r.suggested_jar = jar
        r.review_status = 'approved'
      } else if (rej.has(r.row_id)) r.review_status = 'rejected'
    }
    const counts = { auto_added: 0, pending: 0, approved: 0, rejected: 0, duplicate: 0 } as Record<string, number>
    for (const r of job.review.data.rows) counts[r.review_status]!++
    job.review.data.counts = counts
    job.review.data.status = 'done'
    job.status = 'done'
    const added = job.review.data.rows.filter((r: any) => r.review_status === 'approved')
    const spend = added.filter((r: any) => r.kind === 'expense').reduce((s: number, r: any) => s + r.amount_vnd, 0)
    const income = added.filter((r: any) => r.kind === 'income').reduce((s: number, r: any) => s + r.amount_vnd, 0)
    const jarsAffected = [...new Map(added.filter((r: any) => r.kind === 'expense' && r.suggested_jar).map((r: any) => [r.suggested_jar.code, { code: r.suggested_jar.code, name: r.suggested_jar.name }])).values()]
    const cov = fixture('blocks/valid/coverage_change.added.json')
    cov.id = `coverage_change:${job.id}`
    cov.source = { tool: 'rest:POST /ingest/actions', as_of: nowIso(), app_date: cov.source.app_date }
    cov.data = { ...cov.data, job_id: job.id, rows_added: added.length, external_spend_added_vnd: spend, jars_affected: jarsAffected, forecast_refresh: added.length ? 'queued' : 'skipped' }
    if (income > 0) cov.data.external_income_added_vnd = income
    else delete cov.data.external_income_added_vnd
    cov.fallback_text = `Đã thêm ${added.length} dòng ngoài ví.`
    job.coverage = cov
    const receipt = fixture('rest/ActionResponse.receipt_action_confirm_rows.json')
    receipt.id = `receipt:confirm_rows:${job.id}`
    receipt.source = cov.source
    receipt.data = { ...receipt.data, reference_id: job.id, occurred_at: nowIso(), amount_vnd: spend, summary: `Đã thêm ${added.length} dòng ngoài ví vào lịch sử chi tiêu`, coverage_change: cov }
    return ok(receipt)
  }
  return null
}
