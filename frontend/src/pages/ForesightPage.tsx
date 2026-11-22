import { Link } from 'react-router'
import { JarIcon } from '@/components/JarIcon'
import { JarStatusChip } from '@/components/JarStatusChip'
import { Notice } from '@/components/Notice'
import { SimNote } from '@/components/SimNote'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/StateViews'
import { useOverview } from '@/api/OverviewProvider'
import type { JarFull } from '@/api/schemas'
import { CONFIDENCE_LABEL } from '@/lib/jar'
import { formatDayMonth } from '@/lib/dates'
import { formatSimMoment, formatRatioPercent, formatShortfallChance, formatVnd } from '@/lib/format'

const SEVERITY: Record<string, number> = { short: 0, tight: 1, ok: 2 }

/** Hũ cần chú ý nhất lên đầu: hụt, sát, đủ, chưa có dự báo; cùng mức thì ngày cạn sớm hơn trước. Chỉ sắp xếp, không tính gì. */
export function sortByRisk(jars: readonly JarFull[]): JarFull[] {
  return [...jars].sort((a, b) => {
    const sa = a.status ? SEVERITY[a.status]! : 3
    const sb = b.status ? SEVERITY[b.status]! : 3
    if (sa !== sb) return sa - sb
    if (a.runout_date && b.runout_date) return a.runout_date < b.runout_date ? -1 : a.runout_date > b.runout_date ? 1 : 0
    return a.runout_date ? -1 : b.runout_date ? 1 : 0
  })
}

// Tab "Nhìn trước" (phase 2): hũ nào cạn trước, kèm chất lượng dự báo. Điểm chống chịu và kịch bản "nếu" là các phase sau.
export function ForesightPage() {
  const ov = useOverview()
  const data = ov.data
  const f = data?.forecast
  return (
    <>
      <header className="px-4 pt-[max(16px,env(safe-area-inset-top))] pb-3">
        <h1 className="text-title font-bold text-ink">Nhìn trước</h1>
        <p className="text-small text-ink-2">Hũ nào dự kiến cạn trước kỳ lương</p>
      </header>

      {ov.status === 'loading' && <ListSkeleton rows={4} label="Đang tải dự báo" />}
      {ov.status === 'error' && <ErrorState className="px-4" error={ov.error} title="Chưa tải được dự báo" onRetry={() => void ov.reload()} />}

      {data && (
        <div className="space-y-3 px-4 pb-8">
          {data.next_payday && (
            <section className="rounded-card bg-surface p-4 shadow-card" aria-label="Kỳ lương kế tiếp" data-testid="next-payday">
              <p className="text-small text-ink-2">Kỳ lương kế tiếp</p>
              <p className="text-subtitle font-bold text-ink">
                {formatDayMonth(data.next_payday.date)} · còn {data.next_payday.days_until} ngày
              </p>
              {data.next_payday.expected_vnd !== undefined && <p className="num text-small text-ink-2">Dự kiến {formatVnd(data.next_payday.expected_vnd)}</p>}
            </section>
          )}

          {data.jars.length > 0 && !f && (
            <Notice kind="low_data" title="Chưa có dự báo" message="Hệ thống chưa tính dự báo cho các hũ. Khi có, hũ sẽ được xếp theo mức cần chú ý." />
          )}
          {f && (
            <section className="rounded-card bg-surface p-4 text-small shadow-card" aria-label="Chất lượng dự báo" data-testid="forecast-quality">
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                <div>
                  <dt className="text-ink-2">Nhóm tin cậy</dt>
                  <dd className="font-semibold text-ink">{CONFIDENCE_LABEL[f.confidence_band]}</dd>
                </div>
                <div>
                  <dt className="text-ink-2">Độ phủ dữ liệu</dt>
                  <dd className="num font-semibold text-ink">{f.coverage !== undefined ? formatRatioPercent(f.coverage) : 'Chưa tính được'}</dd>
                </div>
                <div>
                  <dt className="text-ink-2">Dữ liệu lịch sử</dt>
                  <dd className="num font-semibold text-ink">{f.history_days} ngày</dd>
                </div>
                <div>
                  <dt className="text-ink-2">Cập nhật</dt>
                  <dd className="font-semibold text-ink">{formatSimMoment(f.run_app_date, f.computed_at)}</dd>
                </div>
              </dl>
              {f.is_initial_estimate && <p className="mt-2 font-semibold text-warn-fg">Ước lượng ban đầu: mới có ít ngày dữ liệu.</p>}
              {f.stale && <p className="mt-2 font-semibold text-warn-fg">Số liệu cũ: mở chi tiết một hũ để tính lại.</p>}
            </section>
          )}

          {data.jars.length === 0 ? (
            <EmptyState title="Chưa có hũ nào" message="Khai lương và chia hũ để Yofina dự báo ngày mỗi hũ cạn." />
          ) : (
            <ul className="space-y-3" aria-label="Hũ theo mức cần chú ý">
              {sortByRisk(data.jars).map((j) => (
                <li key={j.code}>
                  <Link to={`/jars/${j.code}`} className="flex min-h-[72px] items-center gap-3 rounded-card bg-surface p-4 shadow-card" aria-label={`Mở hũ ${j.name}`}>
                    <JarIcon colorKey={j.color_key} iconKey={j.icon_key} size={40} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-subtitle font-semibold text-ink">{j.name}</span>
                      <span className="num block text-small text-ink-2">
                        {formatVnd(j.balance_vnd)}
                      </span>
                      {j.p_shortfall !== undefined && <span className="num block text-small text-ink-2">Khả năng hụt {formatShortfallChance(j.p_shortfall).toLowerCase()}</span>}
                    </span>
                    <JarStatusChip jar={j} />
                  </Link>
                </li>
              ))}
            </ul>
          )}

          <p className="rounded-card bg-surface-2 px-4 py-3 text-small text-ink-2">Điểm chống chịu và kịch bản “nếu thì” sẽ có ở các phiên bản sau.</p>
      <SimNote />
        </div>
      )}
    </>
  )
}
