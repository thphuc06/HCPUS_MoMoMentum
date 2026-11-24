import { Link } from 'react-router'
import { Notice } from '@/components/Notice'
import { SimNote } from '@/components/SimNote'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/StateViews'
import { useOverview } from '@/api/OverviewProvider'
import type { JarFull } from '@/api/schemas'
import type { ReviewListData } from '@/contracts/blocks'
import { JarRunway } from '@/features/forecast/JarRunway'
import { ResilienceSection } from '@/features/resilience/ResilienceSection'
import { RoadmapEntryCard } from '@/features/roadmap/RoadmapEntry'
import { useReview } from '@/features/review/useReview'
import { formatVnd } from '@/lib/format'

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

/**
 * Giao dịch chưa xếp hũ chưa thuộc lịch sử của hũ chi tiêu nào nên dự báo từng hũ chưa tính chúng: một dòng nhỏ có lối sang Xem lại.
 * Việc xếp hũ nằm ở Tổng quan ("Việc cần làm"), ở đây chỉ nói ảnh hưởng tới dự báo (ui-design-review.md §10).
 */
function UnclassifiedNote({ data }: { data?: ReviewListData }) {
  if (!data || data.count === 0) return null
  return (
    <p className="mt-2 flex flex-wrap items-center gap-x-2 rounded-xl bg-warn-bg px-3 py-1.5 text-note text-warn-fg" data-testid="forecast-unclassified">
      <span className="num">{data.count} giao dịch ({formatVnd(data.pending_total_vnd)}) chưa xếp hũ, dự báo chưa tính.</span>
      <Link to="/review" className="inline-flex min-h-11 items-center font-semibold underline underline-offset-2">Xếp hũ</Link>
    </p>
  )
}

// Tab Nhìn trước là nhà của dự báo, chống chịu, cú sốc và lộ trình (ui-design-review.md §10). Thứ tự giữ như cảnh 3 và 4: điểm
// chống chịu, lối vào Lộ trình, thử cú sốc, rồi khối dự báo hũ (B2 gộp danh sách hũ dự báo, kỳ lương, chất lượng dự báo).
export function ForesightPage() {
  const ov = useOverview()
  const review = useReview('daily_ask')
  const data = ov.data
  const f = data?.forecast
  return (
    <>
      <header className="px-4 pt-[max(16px,env(safe-area-inset-top))] pb-3">
        <h1 className="text-title font-bold text-ink">Nhìn trước</h1>
        <p className="text-small text-ink-2">Chống chịu, lộ trình và dự báo từng hũ</p>
      </header>

      <ResilienceSection>
        <RoadmapEntryCard />
      </ResilienceSection>

      {ov.status === 'loading' && <ListSkeleton rows={4} label="Đang tải dự báo" />}
      {ov.status === 'error' && <ErrorState className="px-4" error={ov.error} title="Chưa tải được dự báo" onRetry={() => void ov.reload()} />}

      {data && (
        <div className="space-y-3 px-4 pb-8">
          {data.jars.length > 0 && !f && (
            <Notice kind="low_data" title="Chưa có dự báo" message="Hệ thống chưa tính dự báo cho các hũ. Khi có, hũ sẽ được xếp theo mức cần chú ý." />
          )}
          {data.jars.length === 0 ? (
            <EmptyState title="Chưa có hũ nào" message="Khai lương và chia hũ để Yofina dự báo ngày mỗi hũ cạn." />
          ) : (
            <JarRunway
              jars={sortByRisk(data.jars)}
              appDate={data.app_date}
              nextPayday={data.next_payday}
              obligations={data.obligations_due}
              forecast={f ?? null}
              notice={review.status === 'ready' ? <UnclassifiedNote data={review.data.data} /> : undefined}
            />
          )}
          <SimNote />
        </div>
      )}
    </>
  )
}
