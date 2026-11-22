import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { Camera, FileSpreadsheet, ImageUp, Loader2, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScreenHeader } from '@/components/ScreenHeader'
import { SimNote } from '@/components/SimNote'
import { ErrorState } from '@/components/StateViews'
import { PreviewPanel } from '@/components/PreviewPanel'
import { useApi } from '@/api/ApiProvider'
import { ApiError, ERROR_CODES, ERROR_MESSAGES, type ErrorCode } from '@/api/errors'
import type { ConfirmRowsParams, IngestJobResponse, IngestSourceKind } from '@/api/ingestSchemas'
import { CoverageChangeBlock, IngestReviewBlock, type IngestJar, type IngestReviewData, type IngestRow as Row } from '@/contracts/blocks'
import { ACCEPT_CAMERA, ACCEPT_CSV, ACCEPT_IMAGE, DEFAULT_LIMITS, RETENTION_DAYS, useIngestPollTiming } from '@/features/ingest/config'
import { checkFile, mimeOf, uploadToS3 } from '@/features/ingest/upload'
import { useIngestJob } from '@/features/ingest/useIngestJob'
import { useIngestConfirm } from '@/features/ingest/useIngestConfirm'
import { IngestReviewList } from '@/features/ingest/IngestReview'
import { isOpenRow, rowTitle } from '@/features/ingest/IngestRow'
import { JarPickerSheet } from '@/features/ingest/JarPickerSheet'
import { CoverageChange, mostAffectedJar } from '@/features/ingest/CoverageChange'

// Nạp chi tiêu và thu nhập NGOÀI ví từ ảnh hoặc CSV (phase 5, F6), theo Figma cảnh 5: I1 chọn ảnh (24:2165), I2 đang xử lý
// (24:2210), I3 duyệt dòng (24:2269), I4 độ phủ tăng (24:2347). Trạng thái lần nạp đang xem nằm ở `?job=<id>` để tải lại
// trang hay mở từ chat vẫn về đúng chỗ. Không gì được ghi vào sổ cái cho tới khi người dùng xác nhận `confirm_rows`.

const SOURCE_LABEL: Record<IngestSourceKind, string> = { image: 'ảnh', csv: 'tệp CSV' }
const KNOWN = new Set<string>(ERROR_CODES)

/** Câu hiển thị cho job lỗi: câu tiếng Việt của mã hợp đồng, không có thì câu server gửi, không nữa thì câu chung. */
function jobErrorMessage(job: IngestJobResponse): string {
  if (job.error_code && KNOWN.has(job.error_code)) return ERROR_MESSAGES[job.error_code as ErrorCode]
  return job.error_message ?? 'Chưa đọc được tệp này. Bạn thử lại với tệp khác nhé.'
}

type Pending = { kind: IngestSourceKind; file: File }

// ---------------------------------------------------------------- I1: chọn tệp

function FilePick({ kind, label, accept, capture, Icon, disabled, onFile }: { kind: IngestSourceKind; label: string; accept: string; capture?: boolean; Icon: typeof Camera; disabled: boolean; onFile: (kind: IngestSourceKind, f: File) => void }) {
  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    e.target.value = '' // chọn lại đúng tệp đó vẫn kích hoạt
    if (f) onFile(kind, f)
  }
  return (
    <label
      className={`flex min-h-14 w-full cursor-pointer items-center gap-3 rounded-2xl border border-line bg-surface px-4 text-body font-semibold text-ink focus-within:ring-3 focus-within:ring-ring/50 active:bg-surface-2 ${disabled ? 'pointer-events-none opacity-50' : ''}`}
    >
      <span className="grid size-10 shrink-0 place-items-center rounded-full bg-tint text-brand-text">
        <Icon className="size-5" aria-hidden />
      </span>
      <span className="flex-1">{label}</span>
      <input type="file" className="sr-only" accept={accept} capture={capture ? 'environment' : undefined} disabled={disabled} onChange={onChange} />
    </label>
  )
}

function PickStep({ busy, error, pending, onFile, onConsent, onCancelConsent }: { busy: boolean; error: ApiError | null; pending: Pending | null; onFile: (k: IngestSourceKind, f: File) => void; onConsent: () => void; onCancelConsent: () => void }) {
  const [agree, setAgree] = useState(false)
  useEffect(() => setAgree(false), [pending])
  return (
    <div className="space-y-4" data-step="pick">
      <section className="rounded-card bg-surface p-4 shadow-card" aria-labelledby="ingest-pick-title">
        <h2 id="ingest-pick-title" className="text-subtitle font-semibold text-ink">
          Thêm chi tiêu ngoài ví
        </h2>
        <p className="mt-1 text-small text-ink-2">
          Chụp thông báo chuyển khoản, hóa đơn, hoặc tải sao kê ngân hàng. Yofina đọc các dòng chi tiêu và thu nhập để dự báo sát hơn; số dư hũ không đổi.
        </p>
        <div className="mt-4 flex flex-col gap-2.5">
          {/* Ô chụp dùng `image/*`: Chrome Android chỉ mở thẳng camera khi accept là image/*; máy ảnh luôn ra JPEG, loại vẫn được checkFile kiểm. */}
          <FilePick kind="image" label="Chụp ảnh" accept={ACCEPT_CAMERA} capture Icon={Camera} disabled={busy} onFile={onFile} />
          <FilePick kind="image" label="Chọn ảnh có sẵn" accept={ACCEPT_IMAGE} Icon={ImageUp} disabled={busy} onFile={onFile} />
          <FilePick kind="csv" label="Tải sao kê CSV" accept={ACCEPT_CSV} Icon={FileSpreadsheet} disabled={busy} onFile={onFile} />
        </div>
        <p className="mt-3 text-note text-ink-2">
          Ảnh PNG, JPEG, WEBP tối đa {(DEFAULT_LIMITS.image.maxBytes / 1_000_000).toLocaleString('vi-VN')} MB; CSV tối đa {(DEFAULT_LIMITS.csv.maxBytes / 1_000_000).toLocaleString('vi-VN')} MB.
        </p>
      </section>

      {busy && (
        <p role="status" aria-live="polite" className="flex items-center gap-2 rounded-2xl bg-surface px-4 py-3 text-small font-semibold text-ink shadow-card">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Đang tải tệp lên…
        </p>
      )}

      {error && (
        <p role="alert" data-testid="ingest-error" className="rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
          {error.message}
        </p>
      )}

      {pending && (
        <section className="rounded-card border-2 border-brand bg-surface p-4" aria-labelledby="ingest-consent-title" data-testid="consent">
          <h2 id="ingest-consent-title" className="flex items-center gap-2 text-subtitle font-semibold text-ink">
            <ShieldCheck className="size-5 text-brand-text" aria-hidden />
            Cho phép đọc {SOURCE_LABEL[pending.kind]}
          </h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-small text-ink">
            <li>Tệp gốc được giữ tối đa {RETENTION_DAYS} ngày rồi tự xóa.</li>
            <li>Số tài khoản, số điện thoại và tên người khác được che trước khi lưu.</li>
            <li>Chỉ các dòng bạn xác nhận mới vào lịch sử chi tiêu; số dư hũ không đổi.</li>
          </ul>
          <label className="mt-3 flex min-h-11 items-start gap-3 text-small text-ink">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-0.5 size-5 accent-[var(--brand-primary)]" />
            <span>Tôi đồng ý cho Yofina đọc {SOURCE_LABEL[pending.kind]} này</span>
          </label>
          <div className="mt-3 flex flex-col gap-2.5">
            <Button type="button" disabled={!agree || busy} onClick={onConsent}>
              Đồng ý và tải lên
            </Button>
            <Button type="button" variant="outline" disabled={busy} onClick={onCancelConsent}>
              Không, chọn lại
            </Button>
          </div>
        </section>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- I2: đang xử lý

const STAGE: Partial<Record<IngestJobResponse['status'], string>> = {
  awaiting_upload: 'Đang nhận tệp…',
  queued: 'Đang xếp hàng đọc tệp…',
  processing: 'Đang đọc các dòng và che thông tin cá nhân…',
}

function ProcessingStep({ job, slow, error, onRetry, onCancel }: { job: IngestJobResponse | null; slow: boolean; error: ApiError | null; onRetry: () => void; onCancel: () => void }) {
  const progress = job?.progress ?? 0
  const label = (job && STAGE[job.status]) ?? 'Đang đọc tệp…'
  return (
    <section className="rounded-card bg-surface p-5 shadow-card" data-step="processing" aria-labelledby="ingest-proc-title">
      <h2 id="ingest-proc-title" className="text-subtitle font-semibold text-ink">
        Đang xử lý
      </h2>
      <div className="mt-4 h-2.5 w-full overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-label="Tiến độ đọc tệp" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
        <div className="h-full rounded-full bg-brand transition-[width] duration-500" style={{ width: `${Math.max(4, progress)}%` }} />
      </div>
      <p className="mt-2 text-small text-ink-2" role="status" aria-live="polite" data-testid="ingest-progress">
        {slow ? 'Đang lâu hơn thường lệ. Bạn có thể thử hỏi lại hoặc quay lại sau.' : `${label} ${progress}%`}
      </p>
      {error && !slow && (
        <p className="mt-2 text-small text-warn-fg" role="status">
          {error.retryable ? 'Mạng chập chờn, đang thử lại…' : error.message}
        </p>
      )}
      <div className="mt-4 flex flex-col gap-2.5">
        {(slow || (error && !error.retryable)) && (
          <Button type="button" onClick={onRetry}>
            Thử lại
          </Button>
        )}
        <Button type="button" variant="outline" onClick={onCancel} aria-label="Hủy, dừng theo dõi và chọn tệp khác">
          Hủy
        </Button>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------- I3: duyệt dòng

function buildParams(data: IngestReviewData, selected: Record<string, boolean>, jars: Record<string, IngestJar>): ConfirmRowsParams {
  const open = data.rows.filter(isOpenRow)
  const rows = open.filter((r) => selected[r.row_id]).map((r) => (jars[r.row_id] ? { row_id: r.row_id, jar: jars[r.row_id]!.code } : { row_id: r.row_id }))
  const reject_row_ids = open.filter((r) => !selected[r.row_id]).map((r) => r.row_id)
  return { job_id: data.job_id, rows, reject_row_ids }
}

function ReviewStep({ data, onDone, onPickOther }: { data: IngestReviewData; onDone: (coverage: unknown, review: IngestReviewData) => void; onPickOther: () => void }) {
  const api = useApi()
  const flow = useIngestConfirm()
  const [selected, setSelected] = useState<Record<string, boolean>>(() => Object.fromEntries(data.rows.filter(isOpenRow).map((r) => [r.row_id, r.review_status === 'auto_added'])))
  const [jars, setJars] = useState<Record<string, IngestJar>>({})
  const [busyRow, setBusyRow] = useState<string | null>(null)
  const [rowError, setRowError] = useState<{ rowId: string; error: ApiError } | null>(null)
  const [picking, setPicking] = useState<Row | null>(null)

  const open = data.rows.filter(isOpenRow)
  const chosen = open.filter((r) => selected[r.row_id])
  const missingJar = chosen.filter((r) => r.kind === 'expense' && !(jars[r.row_id] ?? r.suggested_jar))
  const confirming = flow.phase === 'previewing' || flow.phase === 'ready' || flow.phase === 'working' || flow.phase === 'blocked'
  const locked = confirming || flow.phase === 'done'

  const pickJar = async (row: Row, jar: IngestJar) => {
    setPicking(null)
    if ((jars[row.row_id] ?? row.suggested_jar)?.code === jar.code) return
    setBusyRow(row.row_id)
    setRowError(null)
    try {
      const res = await api.setIngestRowJar(row.row_id, { jar: jar.code })
      setJars((m) => ({ ...m, [row.row_id]: res.suggested_jar }))
    } catch (e) {
      setRowError({ rowId: row.row_id, error: e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0) })
    } finally {
      setBusyRow(null)
    }
  }

  const start = () => void flow.requestPreview(buildParams(data, selected, jars))
  const confirm = async () => {
    const res = await flow.confirm()
    if (!res) return
    const reviewed: IngestReviewData = {
      ...data,
      rows: data.rows.map((r) => {
        if (!isOpenRow(r)) return r
        const jar = jars[r.row_id] ?? r.suggested_jar
        return { ...r, review_status: selected[r.row_id] ? 'approved' : 'rejected', ...(jar ? { suggested_jar: jar } : {}) }
      }),
    }
    onDone(res.type === 'receipt_action' ? res.data.coverage_change : undefined, reviewed)
  }

  if (open.length === 0) {
    return (
      <div className="space-y-4" data-step="review">
        <IngestReviewList data={data} />
        <section className="rounded-card bg-surface p-4 text-center shadow-card">
          <p className="text-subtitle font-semibold text-ink">Không có dòng mới để thêm</p>
          <p className="mt-1 text-small text-ink-2">Mọi dòng trong tệp đã có trong ví hoặc đã được xử lý.</p>
          <Button type="button" variant="soft" className="mt-3" onClick={onPickOther}>
            Nạp ảnh khác
          </Button>
        </section>
      </div>
    )
  }

  return (
    <div className="space-y-4" data-step="review">
      <IngestReviewList
        data={data}
        rowProps={(r) => ({
          jar: jars[r.row_id] ?? r.suggested_jar,
          selected: !!selected[r.row_id],
          onToggle: (v) => setSelected((s) => ({ ...s, [r.row_id]: v })),
          onPickJar: () => setPicking(r),
          jarBusy: busyRow === r.row_id,
          disabled: locked,
        })}
      />
      {rowError && (
        <p role="alert" className="rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
          Chưa đổi được hũ: {rowError.error.message}
        </p>
      )}

      {!confirming && flow.phase !== 'done' && (
        <section className="space-y-2.5">
          {missingJar.length > 0 && (
            <p role="status" className="rounded-2xl bg-warn-bg px-3 py-2 text-small font-medium text-warn-fg">
              Chọn hũ cho {missingJar.map(rowTitle).join(', ')} trước khi thêm.
            </p>
          )}
          {flow.error && (
            <p role="alert" className="rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
              {flow.error.message}
            </p>
          )}
          <Button type="button" className="w-full" disabled={missingJar.length > 0 || busyRow !== null} onClick={start}>
            Xong, cập nhật dự báo
          </Button>
          <p className="text-center text-note text-ink-2">
            {chosen.length} dòng sẽ được thêm, {open.length - chosen.length} dòng bỏ qua. Chưa có gì được ghi cho tới khi bạn xác nhận.
          </p>
        </section>
      )}

      {confirming && (
        <section className="space-y-3" aria-label="Xác nhận thêm dòng" data-testid="ingest-confirm">
          <PreviewPanel state={flow.phase === 'previewing' ? { status: 'loading', preview: null, error: null } : { status: 'ready', preview: flow.preview, error: null }} />
          {flow.phase !== 'previewing' && !flow.preview && !flow.error && (
            <p className="rounded-card bg-surface p-4 text-small text-ink shadow-card">
              Thêm {chosen.length} dòng ngoài ví vào lịch sử chi tiêu, bỏ {open.length - chosen.length} dòng. Số dư hũ không đổi.
            </p>
          )}
          {flow.error && (
            <p role="alert" className="rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
              {flow.error.message}
            </p>
          )}
          <Button type="button" className="w-full" disabled={flow.phase !== 'ready'} aria-busy={flow.phase === 'working'} onClick={() => void confirm()}>
            {flow.phase === 'working' ? 'Đang thêm…' : `Xác nhận thêm ${chosen.length} dòng`}
          </Button>
          <Button type="button" variant="outline" className="w-full" disabled={flow.phase === 'working'} onClick={flow.reset}>
            Quay lại sửa
          </Button>
        </section>
      )}

      <JarPickerSheet
        open={picking !== null}
        onOpenChange={(o) => !o && setPicking(null)}
        jars={data.jars}
        current={picking ? (jars[picking.row_id] ?? picking.suggested_jar)?.code : undefined}
        rowLabel={picking ? rowTitle(picking) : ''}
        onPick={(j) => picking && void pickJar(picking, j)}
      />
    </div>
  )
}

// ---------------------------------------------------------------- I4: xong

function DoneStep({ coverage, review, onMore }: { coverage: unknown; review: IngestReviewData | null; onMore: () => void }) {
  const navigate = useNavigate()
  const parsed = CoverageChangeBlock.safeParse(coverage)
  const more = (
    <Button type="button" variant="outline" onClick={onMore}>
      Nạp thêm ảnh khác
    </Button>
  )
  if (!parsed.success) {
    const fb = coverage && typeof coverage === 'object' ? (coverage as { fallback_text?: unknown }).fallback_text : undefined
    return (
      <section className="rounded-card bg-surface p-4 shadow-card" data-step="done">
        <h2 className="text-section font-bold text-ink">Đã thêm các dòng ngoài ví</h2>
        <p className="mt-1 text-small text-ink-2">{typeof fb === 'string' ? fb : 'Dự báo sẽ được tính lại với dữ liệu mới.'}</p>
        <p className="mt-3 rounded-2xl bg-surface-2 px-3 py-2 text-small font-semibold text-ink">Số dư hũ không đổi — đây là chi tiêu ngoài ví.</p>
        <div className="mt-4 flex flex-col gap-2.5">
          <Button type="button" onClick={() => navigate('/')}>
            Về Tổng quan
          </Button>
          {more}
        </div>
      </section>
    )
  }
  const code = mostAffectedJar(parsed.data.data, review?.rows)
  return (
    <div data-step="done">
      <CoverageChange
        data={parsed.data.data}
        actions={
          <>
            {code ? (
              <Button type="button" onClick={() => navigate(`/jars/${encodeURIComponent(code)}`)}>
                Xem dự báo cập nhật
              </Button>
            ) : (
              <Button type="button" onClick={() => navigate('/')}>
                Về Tổng quan
              </Button>
            )}
            {more}
          </>
        }
      />
    </div>
  )
}

// ---------------------------------------------------------------- trang

export function IngestPage() {
  const api = useApi()
  const timing = useIngestPollTiming()
  const [search, setSearch] = useSearchParams()
  const jobId = search.get('job')
  const poll = useIngestJob(jobId, timing)
  const [uploading, setUploading] = useState(false)
  const [pickError, setPickError] = useState<ApiError | null>(null)
  const [pending, setPending] = useState<Pending | null>(null)
  const [finished, setFinished] = useState<{ coverage: unknown; review: IngestReviewData } | null>(null)
  const abort = useRef<AbortController | null>(null)

  useEffect(() => () => abort.current?.abort(), [])

  const goPick = useCallback(() => {
    abort.current?.abort()
    setFinished(null)
    setPending(null)
    setPickError(null)
    setSearch({}, { replace: true })
  }, [setSearch])

  const upload = useCallback(
    async (kind: IngestSourceKind, file: File, consent: boolean) => {
      setPickError(null)
      const early = checkFile(file, kind, DEFAULT_LIMITS[kind])
      if (early) {
        setPending(null)
        setPickError(new ApiError(early, 0))
        return
      }
      abort.current?.abort()
      const ctrl = new AbortController()
      abort.current = ctrl
      setUploading(true)
      try {
        const target = await api.createIngestUpload({ source_kind: kind, mime: mimeOf(file, kind), size_bytes: file.size, ...(consent ? { consent: true } : {}) })
        if (ctrl.signal.aborted) return
        // Server là nơi quyết: kiểm lại theo giới hạn nó vừa trả.
        const late = checkFile(file, kind, { maxBytes: target.max_bytes, mimeTypes: target.mime_types })
        if (late) throw new ApiError(late, 0)
        await uploadToS3(target, file, { signal: ctrl.signal })
        if (ctrl.signal.aborted) return
        setPending(null)
        setFinished(null)
        setSearch({ job: target.job_id }, { replace: true })
      } catch (e) {
        if (ctrl.signal.aborted) return
        const err = e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0)
        if (err.code === 'CONSENT_REQUIRED') {
          setPending({ kind, file })
          return
        }
        setPending(null)
        setPickError(err)
      } finally {
        if (!ctrl.signal.aborted) setUploading(false)
      }
    },
    [api, setSearch],
  )

  const job = poll.job && poll.job.job_id === jobId ? poll.job : null
  const review = useMemo(() => {
    if (!job?.review) return null
    const r = IngestReviewBlock.safeParse(job.review)
    return r.success ? r.data.data : { invalid: job.review }
  }, [job])

  let body
  if (finished) {
    body = <DoneStep coverage={finished.coverage} review={finished.review} onMore={goPick} />
  } else if (!jobId) {
    body = <PickStep busy={uploading} error={pickError} pending={pending} onFile={(k, f) => void upload(k, f, false)} onConsent={() => pending && void upload(pending.kind, pending.file, true)} onCancelConsent={() => setPending(null)} />
  } else if (job && (job.status === 'failed' || job.status === 'rejected')) {
    body = (
      <section className="space-y-3" data-step="failed">
        <p role="alert" data-testid="ingest-error" className="rounded-card bg-bad-bg p-4 text-small font-semibold text-bad-fg">
          {jobErrorMessage(job)}
        </p>
        <Button type="button" className="w-full" onClick={goPick}>
          Chọn tệp khác
        </Button>
      </section>
    )
  } else if (job && (job.status === 'review' || job.status === 'done') && review) {
    if ('invalid' in review) {
      const fb = review.invalid && typeof review.invalid === 'object' ? (review.invalid as { fallback_text?: unknown }).fallback_text : undefined
      body = (
        <section className="space-y-3" data-step="failed">
          <p role="alert" className="rounded-card bg-surface-2 p-4 text-small text-ink">
            {typeof fb === 'string' ? fb : 'Chưa hiển thị được bảng duyệt.'} Cập nhật ứng dụng để duyệt các dòng này.
          </p>
          <Button type="button" variant="outline" className="w-full" onClick={goPick}>
            Chọn tệp khác
          </Button>
        </section>
      )
    } else if (job.status === 'done') {
      body = <DoneStep coverage={job.coverage_change} review={review} onMore={goPick} />
    } else {
      body = <ReviewStep key={job.job_id} data={review} onDone={(coverage, reviewed) => setFinished({ coverage, review: reviewed })} onPickOther={goPick} />
    }
  } else if (poll.error && !poll.error.retryable && !job) {
    body = <ErrorState error={poll.error} title="Chưa xem được lần nạp này" onRetry={poll.retry} />
  } else {
    body = <ProcessingStep job={job} slow={poll.slow} error={poll.error} onRetry={poll.retry} onCancel={goPick} />
  }

  return (
    <>
      <ScreenHeader title="Nạp ảnh / sao kê" backTo="/income" />
      <div className="space-y-4 px-4 pb-10">
        {body}
        {!jobId && !finished && (
          <p className="text-center text-small">
            <Link to="/activity" className="inline-flex min-h-11 items-center font-semibold text-brand-text">
              Xem lịch sử chi tiêu ở Hoạt động
            </Link>
          </p>
        )}
        <SimNote />
      </div>
    </>
  )
}
