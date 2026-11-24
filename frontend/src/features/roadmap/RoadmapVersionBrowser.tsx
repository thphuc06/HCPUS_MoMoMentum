import { useState } from 'react'
import { Link } from 'react-router'
import { useApiResource } from '@/api/resource'
import type { RoadmapVersionsResponse } from '@/api/roadmapSchemas'
import { ErrorState, ListSkeleton } from '@/components/StateViews'
import { Button, buttonVariants } from '@/components/ui/button'
import { Roadmap } from './Roadmap'
import { RoadmapVersionList } from './RoadmapChatLinks'

/**
 * Đường tới trang so sánh giữa `version` và bản đang dùng, theo thứ tự thời gian (bản cũ → bản mới) như khối `roadmap_diff`.
 * Không có bản đang dùng hoặc chính là bản đang dùng thì không có gì để so.
 */
export function compareWithActivePath(active: number | undefined, version: number): string | null {
  if (active === undefined || active === version) return null
  const [from, to] = active < version ? [active, version] : [version, active]
  return `/roadmap/compare?from=${from}&to=${to}`
}

function VersionView({ version, active, onClose }: { version: number; active?: number; onClose: () => void }) {
  const roadmap = useApiResource((api) => api.getRoadmap({ version }), [version])
  const compare = compareWithActivePath(active, version)
  return (
    <section aria-label={`Phiên bản ${version}`} data-testid="roadmap-version-view" className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {compare && <Link to={compare} className={buttonVariants({ size: 'sm' })}>So với bản đang dùng</Link>}
        <Button type="button" size="sm" variant="outline" onClick={onClose}>Đóng bản này</Button>
      </div>
      {roadmap.status === 'loading' && <ListSkeleton rows={2} label={`Đang tải phiên bản ${version}`} />}
      {roadmap.status === 'error' && <ErrorState error={roadmap.error} title={`Chưa tải được phiên bản ${version}`} onRetry={() => void roadmap.reload()} />}
      {/* Xem bản khác chỉ để đọc; quyết định từng bước làm trên bản đang hiện ở trên, chọn bản mới làm ở trang So với bản cũ. */}
      {roadmap.data && <Roadmap data={roadmap.data.data} />}
    </section>
  )
}

/** Danh sách phiên bản của trang Lộ trình: bấm một bản để xem riêng bản đó và so với bản đang dùng. */
export function RoadmapVersionBrowser({ versions, shownVersion }: { versions: RoadmapVersionsResponse; shownVersion?: number }) {
  const [selected, setSelected] = useState<number | null>(null)
  if (versions.versions.length === 0) return null
  const open = selected !== null && selected !== shownVersion ? selected : null
  return (
    <section aria-labelledby="roadmap-versions-heading" className="space-y-2">
      <h2 id="roadmap-versions-heading" className="text-subtitle font-semibold text-ink">Các phiên bản</h2>
      <RoadmapVersionList
        items={versions.versions}
        current={shownVersion}
        selected={open ?? shownVersion}
        onSelect={(v) => setSelected(v === shownVersion || v === open ? null : v)}
      />
      {open !== null && <VersionView key={open} version={open} active={versions.active_version} onClose={() => setSelected(null)} />}
    </section>
  )
}
