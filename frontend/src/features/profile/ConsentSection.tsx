import { Link } from 'react-router'
import type { IngestSourceKind } from '@/api/ingestSchemas'
import { useApiResource } from '@/api/resource'
import { ErrorState, ListSkeleton } from '@/components/StateViews'
import { StatusChip } from '@/components/StatusChip'
import { Disclosure } from '@/components/ui/Disclosure'
import { RETENTION_DAYS } from '@/features/ingest/config'
import { formatDateTime } from '@/lib/format'

// "Đồng ý theo nguồn nạp" ở màn Hồ sơ. Hợp đồng REST chưa có endpoint đọc hay rút bảng `consents`; server chỉ nhận đồng ý lúc
// tải tệp (`POST /ingest/uploads` với `consent: true`, thiếu thì 403 CONSENT_REQUIRED). Nên màn này suy trạng thái từ các lần nạp
// gần đây (`GET /ingest/jobs`): đã có lần nạp của nguồn nào thì nguồn đó đã được đồng ý (server không tạo lần nạp khi chưa đồng ý).

const SOURCES: Array<{ kind: IngestSourceKind; label: string }> = [
  { kind: 'image', label: 'Ảnh chụp thông báo, hóa đơn' },
  { kind: 'csv', label: 'Tệp CSV sao kê' },
]

export function ConsentSection() {
  const jobs = useApiResource((api) => api.listIngestJobs(20), [])
  const list = jobs.data?.jobs
  return (
    <section aria-labelledby="consent-heading" className="space-y-3">
      <h2 id="consent-heading" className="text-section font-bold text-ink">Đồng ý theo nguồn nạp</h2>
      {jobs.status === 'loading' && <ListSkeleton rows={1} rowClass="h-24" label="Đang tải các lần nạp" />}
      {jobs.status === 'error' && !jobs.data && <ErrorState error={jobs.error} title="Chưa tải được các lần nạp" onRetry={() => void jobs.reload()} />}
      {list && (
        <div className="rounded-card bg-surface px-4 shadow-card">
          <ul className="divide-y divide-line" aria-label="Các nguồn nạp">
            {SOURCES.map((s) => {
              const latest = list.filter((j) => j.source_kind === s.kind).sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
              return (
                <li key={s.kind} data-source={s.kind} className="flex items-start justify-between gap-3 py-3">
                  <span className="min-w-0">
                    <span className="block text-body font-semibold text-ink">{s.label}</span>
                    <span className="block text-small text-ink-2">
                      {latest ? `Lần nạp gần nhất ${formatDateTime(latest.created_at)}` : 'Yofina sẽ hỏi bạn ở lần nạp đầu tiên'}
                    </span>
                  </span>
                  {latest ? <StatusChip kind="ok">Đã đồng ý</StatusChip> : <StatusChip kind="info">Chưa nạp</StatusChip>}
                </li>
              )
            })}
          </ul>
            <Disclosure label="Tệp được giữ thế nào?" className="border-t border-line pt-1" panelClassName="pb-2 text-note text-ink-2">
              <p>
                Tệp gốc được giữ tối đa {RETENTION_DAYS} ngày; số tài khoản, số điện thoại và tên người khác được che trước khi lưu.
                Muốn bỏ hết đồng ý và tệp đã nạp, dùng “Xóa dữ liệu của tôi” bên dưới.
              </p>
            </Disclosure>
          <Link to="/ingest" className="-mt-1 mb-1 flex min-h-11 items-center text-small font-semibold text-brand-text">Nạp dữ liệu</Link>
        </div>
      )}
    </section>
  )
}
