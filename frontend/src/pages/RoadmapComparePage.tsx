import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useApi } from '@/api/ApiProvider'
import { useApiResource } from '@/api/resource'
import type { RoadmapResponse, RoadmapVersionDecisionRequest } from '@/api/roadmapSchemas'
import { ScreenHeader } from '@/components/ScreenHeader'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/StateViews'
import { Button, buttonVariants } from '@/components/ui/button'
import { Roadmap } from '@/features/roadmap/Roadmap'
import { RoadmapDiff } from '@/features/roadmap/RoadmapDiff'
import { useRoadmapMutation } from '@/features/roadmap/useStepDecision'
import { RoadmapVersion } from '@/contracts/blocks'

/** `?from=&to=` (mở từ danh sách phiên bản của trang Lộ trình); vắng hoặc sai thì để server chọn (bản đề xuất so với bản nó dựa vào). */
function versionParam(raw: string | null): number | undefined {
  const r = RoadmapVersion.safeParse(raw === null ? undefined : Number(raw))
  return r.success ? r.data : undefined
}

export function RoadmapComparePage() {
  const api = useApi()
  const [search] = useSearchParams()
  const from = versionParam(search.get('from'))
  const to = versionParam(search.get('to'))
  const diff = useApiResource((api) => api.getRoadmapDiff({ from_version: from, to_version: to }), [from, to])
  const [result, setResult] = useState<RoadmapResponse | null>(null)
  const mutation = useRoadmapMutation(diff.reload)
  const missing = diff.error?.code === 'ROADMAP_NOT_FOUND'
  const data = missing ? null : diff.data?.data
  const enabled = !!data?.can_adopt && diff.status === 'ready' && !diff.refreshing && !mutation.working

  const decide = (decision: RoadmapVersionDecisionRequest['decision']) => {
    if (!enabled || !data) return
    void mutation.run(() => api.decideRoadmapVersion(data.to_version, { decision }), setResult)
  }

  return (
    <>
      <ScreenHeader title="So với bản cũ" backTo="/roadmap" />
      <div className="space-y-3 px-4 pb-8">
        {result ? (
          <>
            <Roadmap data={result.data} />
            <Link to="/roadmap" className={buttonVariants({ className: 'w-full' })}>Về lộ trình đang dùng</Link>
          </>
        ) : (
          <>
            {diff.status === 'loading' && <ListSkeleton rows={2} label="Đang tải so sánh lộ trình" />}
            {missing && <EmptyState title="Chưa có bản để so sánh" message="Quay lại lộ trình để xem phiên bản hiện tại." />}
            {diff.error && !missing && <ErrorState error={diff.error} title="Chưa tải được so sánh" onRetry={() => void diff.reload()} />}
            {mutation.error && <ErrorState error={mutation.error} title="Chưa lưu được lựa chọn" />}
            {data && (
              <>
                <RoadmapDiff data={data} />
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" disabled={!enabled} onClick={() => decide('adopt')}>Dùng bản mới</Button>
                  <Button type="button" size="sm" variant="outline" disabled={!enabled} onClick={() => decide('keep_previous')}>Giữ bản cũ</Button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </>
  )
}
