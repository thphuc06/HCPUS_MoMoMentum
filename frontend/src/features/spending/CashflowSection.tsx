import { useId, useState } from 'react'
import type { CashflowResponse } from '@/api/cashflowSchemas'
import type { JarFull } from '@/api/schemas'
import { useApiResource } from '@/api/resource'
import { ErrorState } from '@/components/StateViews'
import { Skeleton } from '@/components/ui/skeleton'
import { useJarLookup } from '@/features/common/useJarLookup'
import { cn } from '@/lib/cn'
import { useAnimateOnce } from '@/lib/motion'
import { PeriodCashflow } from './PeriodCashflow'
import { SpendingByJar } from './SpendingByJar'
import { SpendingTrend } from './SpendingTrend'

// Phần "tiền đã đi đâu" ở đầu màn Hoạt động (nhà của thông tin này, ui-design-review.md §10): B7 thu và chi của kỳ, rồi một thẻ
// "Tiêu vào đâu" chuyển giữa B1 (theo hũ) và B5 (theo ngày) để màn không dài. Một lần gọi `GET /cashflow`, tải lại sau mỗi lần ghi
// như mọi tài nguyên khác. Route chưa có trên server (404, frontend deploy trước backend) thì không hiện gì; lỗi khác có Thử lại.

type View = 'jar' | 'day'

export function CashflowView({ data, lookup, animate = false, chartSize }: {
  data: CashflowResponse
  lookup: Map<string, JarFull>
  animate?: boolean
  /** Chỉ cho test: kích thước cố định của biểu đồ B5. */
  chartSize?: { width: number; height: number }
}) {
  const [view, setView] = useState<View>('jar')
  const titleId = useId()
  const tabs: Array<{ key: View; label: string }> = [
    { key: 'jar', label: 'Theo hũ' },
    { key: 'day', label: 'Theo ngày' },
  ]
  return (
    <div className="space-y-3" data-testid="cashflow-section">
      <PeriodCashflow data={data} animate={animate} />
      <section className="rounded-card bg-surface p-4 shadow-card" aria-labelledby={titleId}>
        <div className="flex flex-wrap items-center gap-2">
          <h2 id={titleId} className="min-w-0 flex-1 text-subtitle font-semibold text-ink">
            Tiêu vào đâu
          </h2>
          <div role="group" aria-label="Cách xem" className="flex gap-1 rounded-full bg-surface-2 p-1">
            {tabs.map((t) => (
              <button
                key={t.key}
                type="button"
                aria-pressed={view === t.key}
                onClick={() => setView(t.key)}
                className={cn(
                  'min-h-11 rounded-full px-3.5 text-small font-semibold outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
                  view === t.key ? 'bg-surface text-brand-text shadow-card' : 'text-ink-2',
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
        {view === 'jar' ? <SpendingByJar data={data} lookup={lookup} animate={animate} /> : <SpendingTrend data={data} animate={animate} chartSize={chartSize} />}
      </section>
    </div>
  )
}

export function CashflowSection({ className }: { className?: string }) {
  const res = useApiResource((api) => api.getCashflow(), [])
  const lookup = useJarLookup()
  const animate = useAnimateOnce('cashflow')
  if (res.status === 'loading') {
    return (
      <div role="status" aria-busy="true" aria-label="Đang tải chi tiêu kỳ này" data-state="loading" className={cn('space-y-3', className)}>
        <Skeleton className="h-[148px] w-full rounded-card" />
        <Skeleton className="h-[260px] w-full rounded-card" />
      </div>
    )
  }
  if (res.status === 'error' && !res.data) {
    if (res.error.status === 404) return null
    return <ErrorState className={className} error={res.error} title="Chưa tải được chi tiêu kỳ này" onRetry={() => void res.reload()} />
  }
  return (
    <div className={className}>
      <CashflowView data={res.data!} lookup={lookup} animate={animate} />
    </div>
  )
}
