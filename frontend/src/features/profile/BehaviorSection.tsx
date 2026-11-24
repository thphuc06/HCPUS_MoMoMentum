import { useState } from 'react'
import { useApiResource } from '@/api/resource'
import { ErrorState, ListSkeleton } from '@/components/StateViews'
import { StatusChip } from '@/components/StatusChip'
import { Button } from '@/components/ui/button'
import { BehaviorInsightCard, NextStep } from '@/features/behavior/BehaviorInsightCard'
import { BEHAVIOR_SECTION_ID } from '@/features/behavior/format'
import { ExecuteStepDrawer } from '@/features/roadmap/RoadmapStepDialogs'
import { formatDateTime } from '@/lib/format'

/**
 * Nhận xét hành vi ở màn Hồ sơ (`GET /profile/behavior`, batch đêm tính). Mỗi nhận xét vẽ như khối `behavior_insight` (cùng
 * component với chat); việc cần làm của cả hồ sơ ở cuối, có hành động thì "Thực hiện" đi luồng xác nhận của màn hình
 * (`POST /confirmations` rồi `POST /actions`), không tự ghi. Chưa đủ lịch sử thì nói cần thêm bao nhiêu ngày (không phải lỗi).
 */
export function BehaviorSection() {
  const profile = useApiResource((api) => api.getBehaviorProfile(), [])
  const [executing, setExecuting] = useState(false)
  const data = profile.data

  return (
    <section id={BEHAVIOR_SECTION_ID} aria-labelledby="behavior-heading" className="scroll-mt-4 space-y-3">
      <h2 id="behavior-heading" className="text-section font-bold text-ink">Nhận xét hành vi</h2>
      {profile.status === 'loading' && <ListSkeleton rows={1} rowClass="h-32" label="Đang tải nhận xét hành vi" />}
      {profile.status === 'error' && !data && (
        profile.error.code === 'PROFILE_INCOMPLETE' ? (
          <p className="rounded-card bg-surface p-4 text-small text-ink-2 shadow-card">{profile.error.message}</p>
        ) : (
          <ErrorState error={profile.error} title="Chưa tải được nhận xét hành vi" onRetry={() => void profile.reload()} />
        )
      )}
      {data && !data.ready && (
        <div className="rounded-card bg-surface p-4 shadow-card" data-testid="behavior-not-ready">
          <p className="text-small text-ink">{data.headline}</p>
          <p className="num mt-1 text-note text-ink-2">
            Đã có {data.history_days} ngày dữ liệu{data.min_history_days ? `, cần ít nhất ${data.min_history_days} ngày` : ''}.
          </p>
        </div>
      )}
      {data?.ready && (
        <>
          <div className="rounded-card bg-surface p-4 shadow-card">
            <p className="text-subtitle font-semibold text-ink">{data.headline}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-note text-ink-2">
              {data.segment && <StatusChip kind="info">{data.segment.label}</StatusChip>}
              <span className="num">Từ {data.history_days} ngày dữ liệu{data.computed_at ? ` · cập nhật ${formatDateTime(data.computed_at)}` : ''}</span>
            </div>
          </div>
          <ul className="space-y-3" aria-label="Các nhận xét">
            {data.insights.map((insight) => (
              <li key={insight.insight_id}><BehaviorInsightCard as="article" insight={insight} /></li>
            ))}
          </ul>
          {data.next_step && (
            <NextStep step={data.next_step}>
              {data.next_step.action && (
                <Button type="button" size="sm" className="mt-2" onClick={() => setExecuting(true)}>Thực hiện</Button>
              )}
            </NextStep>
          )}
          {executing && data.next_step?.action && (
            <ExecuteStepDrawer
              title={data.next_step.label}
              action={data.next_step.action}
              available={profile.status === 'ready' && !profile.refreshing}
              onClose={() => setExecuting(false)}
            />
          )}
        </>
      )}
    </section>
  )
}
