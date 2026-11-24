import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/StateViews'
import { buttonVariants } from '@/components/ui/button'
import { ResilienceGauge } from './ResilienceGauge'
import { ShockCard } from './ShockCard'
import { useResilience, useShocks } from './useResilience'

const DETAIL_PATH = '/foresight/resilience'

/** children nằm giữa khối Điểm chống chịu và "Thử cú sốc tài chính" (ví dụ lối vào Lộ trình của tab Nhìn trước). */
export function ResilienceSection({ children }: { children?: ReactNode }) {
  const score = useResilience()
  const shocks = useShocks()
  const data = score.data?.data

  return (
    <div className="space-y-4 pb-4">
      <section aria-labelledby="resilience-heading" className="space-y-2">
        <h2 id="resilience-heading" className="px-4 text-section font-bold text-ink">Điểm chống chịu</h2>
        {score.status === 'loading' && <ListSkeleton rows={1} rowClass="h-48" label="Đang tải điểm chống chịu" />}
        {score.status === 'error' && (
          score.error.code === 'PROFILE_INCOMPLETE' && !data ? (
            <EmptyState className="mx-4" title="Chưa có điểm chống chịu" message={score.error.message} />
          ) : (
            <ErrorState className="px-4" error={score.error} title="Chưa tải được điểm chống chịu" onRetry={() => void score.reload()} />
          )
        )}
        {data && (
          <div className="mx-4 rounded-card bg-surface p-4 text-center shadow-card">
            <Link
              to={DETAIL_PATH}
              className="mx-auto block min-h-11 w-full max-w-48 rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <ResilienceGauge score={data.score} band={data.band} />
            </Link>
            <p className="mt-2 text-small text-ink">{data.headline}</p>
            <Link to={DETAIL_PATH} className={buttonVariants({ variant: 'soft', size: 'sm', className: 'mt-3' })}>
              Xem chi tiết
            </Link>
          </div>
        )}
      </section>

      {children}

      <section aria-labelledby="shocks-heading" className="space-y-2">
        <h2 id="shocks-heading" className="px-4 text-section font-bold text-ink">Thử cú sốc tài chính</h2>
        {shocks.status === 'loading' && <ListSkeleton rows={1} label="Đang tải cú sốc" />}
        {shocks.status === 'error' && (
          <ErrorState className="px-4" error={shocks.error} title="Chưa tải được danh sách cú sốc" onRetry={() => void shocks.reload()} />
        )}
        {shocks.data && (
          <ul aria-labelledby="shocks-heading" className="space-y-2 px-4">
            {shocks.data.shocks.map((shock) => <li key={shock.shock_id}><ShockCard shock={shock} /></li>)}
          </ul>
        )}
      </section>
    </div>
  )
}
