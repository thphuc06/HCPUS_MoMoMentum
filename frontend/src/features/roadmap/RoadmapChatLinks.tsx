import { useState } from 'react'
import { useNavigate } from 'react-router'
import type { RoadmapVersionsResponse } from '@/api/roadmapSchemas'
import { useChatLauncher } from '@/chat/launcher'
import { StatusChip } from '@/components/StatusChip'
import { ErrorState, ListSkeleton } from '@/components/StateViews'
import { Button } from '@/components/ui/button'
import type { RoadmapData } from '@/contracts/blocks'
import { cn } from '@/lib/cn'
import { FEASIBILITY, VERSION_STATUS } from './Roadmap'
import { useRoadmapVersions } from './useRoadmapVersions'

// Phần cuối của khối lộ trình trong chat: nói bản này đứng ở đâu so với các phiên bản khác và mở lối sang trang Lộ trình
// (so với bản đang dùng, xem các phiên bản). Chọn Dùng bản mới hay Giữ bản cũ làm ở trang So với bản cũ, không làm trong chat.

const STATUS_HINT: Record<RoadmapData['status'], string> = {
  proposed: 'Đây là bản đề xuất, chưa thay lộ trình bạn đang dùng.',
  active: 'Đây là lộ trình bạn đang dùng.',
  superseded: 'Bản này đã được thay bằng một phiên bản mới hơn.',
  discarded: 'Bản đề xuất này đã bị bỏ, không còn để chọn.',
}

type VersionItem = RoadmapVersionsResponse['versions'][number]

/**
 * Danh sách phiên bản (đang dùng, đề xuất, đã thay, đã bỏ), mới nhất trước. `current` là bản đang hiện ở trên; có `onSelect`
 * (trang Lộ trình) thì mỗi bản là một nút để xem riêng bản đó, `selected` là bản đang mở.
 */
export function RoadmapVersionList({ items, current, selected, onSelect }: {
  items: readonly VersionItem[]
  current?: number
  selected?: number
  onSelect?: (version: number) => void
}) {
  return (
    <ol aria-label="Các phiên bản lộ trình" className="space-y-2">
      {items.map((item) => {
        const status = VERSION_STATUS[item.status]
        const feasibility = FEASIBILITY[item.feasibility]
        const body = (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-small font-semibold text-ink">
                Phiên bản {item.version}{item.version === current ? ' (bản này)' : ''}
              </span>
              <StatusChip kind={status.kind}>{status.label}</StatusChip>
              {onSelect && <StatusChip kind={feasibility.kind}>{feasibility.label}</StatusChip>}
            </div>
            <p className="text-note text-ink-2">{item.reason_text}</p>
            {onSelect && <p className="num text-note text-ink-2">{item.counts.pending} bước chờ</p>}
          </>
        )
        return (
          <li key={item.version} aria-current={item.version === current ? 'true' : undefined}>
            {onSelect ? (
              <button
                type="button"
                aria-pressed={item.version === selected}
                onClick={() => onSelect(item.version)}
                className={cn(
                  'w-full space-y-1 rounded-xl p-3 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
                  item.version === selected ? 'bg-tint ring-1 ring-brand' : 'bg-surface-2',
                )}
              >
                {body}
              </button>
            ) : (
              <div className="space-y-1 rounded-xl bg-surface-2 p-3">{body}</div>
            )}
          </li>
        )
      })}
    </ol>
  )
}

function VersionList({ current }: { current: number }) {
  const versions = useRoadmapVersions()
  if (versions.status === 'loading') return <ListSkeleton rows={2} rowClass="h-12" label="Đang tải các phiên bản" />
  if (versions.error) return <ErrorState error={versions.error} title="Chưa tải được các phiên bản" onRetry={() => void versions.reload()} />
  return <RoadmapVersionList items={versions.data?.versions ?? []} current={current} />
}

export function RoadmapChatLinks({ data }: { data: RoadmapData }) {
  const navigate = useNavigate()
  const launcher = useChatLauncher()
  const [showVersions, setShowVersions] = useState(false)
  const go = (to: string) => {
    launcher.close()
    navigate(to)
  }
  const proposed = data.status === 'proposed'

  return (
    <footer className="space-y-3 border-t border-line pt-3">
      <p className="text-small text-ink-2">{STATUS_HINT[data.status]}</p>
      <div className="flex flex-wrap gap-2">
        {proposed && (
          <Button type="button" size="sm" onClick={() => go('/roadmap/compare')}>So với bản đang dùng</Button>
        )}
        <Button type="button" size="sm" variant="outline" aria-expanded={showVersions} onClick={() => setShowVersions((open) => !open)}>
          Xem các phiên bản
        </Button>
        <Button type="button" size="sm" variant="soft" onClick={() => go('/roadmap')}>Mở trang Lộ trình</Button>
      </div>
      {showVersions && <VersionList current={data.version} />}
    </footer>
  )
}
