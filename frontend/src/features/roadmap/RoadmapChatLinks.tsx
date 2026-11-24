import { useState } from 'react'
import { useNavigate } from 'react-router'
import { useChatLauncher } from '@/chat/launcher'
import { StatusChip } from '@/components/StatusChip'
import { ErrorState, ListSkeleton } from '@/components/StateViews'
import { Button } from '@/components/ui/button'
import type { RoadmapData } from '@/contracts/blocks'
import { VERSION_STATUS } from './Roadmap'
import { useRoadmapVersions } from './useRoadmapVersions'

// Phần cuối của khối lộ trình trong chat: nói bản này đứng ở đâu so với các phiên bản khác và mở lối sang trang Lộ trình
// (so với bản đang dùng, xem các phiên bản). Chọn Dùng bản mới hay Giữ bản cũ làm ở trang So với bản cũ, không làm trong chat.

const STATUS_HINT: Record<RoadmapData['status'], string> = {
  proposed: 'Đây là bản đề xuất, chưa thay lộ trình bạn đang dùng. So với bản đang dùng rồi chọn Dùng bản mới hoặc Giữ bản cũ.',
  active: 'Đây là lộ trình bạn đang dùng.',
  superseded: 'Bản này đã được thay bằng một phiên bản mới hơn.',
  discarded: 'Bản đề xuất này đã bị bỏ, không còn để chọn.',
}

function VersionList({ current }: { current: number }) {
  const versions = useRoadmapVersions()
  if (versions.status === 'loading') return <ListSkeleton rows={2} rowClass="h-12" label="Đang tải các phiên bản" />
  if (versions.error) return <ErrorState error={versions.error} title="Chưa tải được các phiên bản" onRetry={() => void versions.reload()} />
  const items = versions.data?.versions ?? []
  return (
    <ol aria-label="Các phiên bản lộ trình" className="space-y-2">
      {items.map((item) => {
        const status = VERSION_STATUS[item.status]
        return (
          <li key={item.version} className="space-y-1 rounded-xl bg-surface-2 p-3" aria-current={item.version === current ? 'true' : undefined}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-small font-semibold text-ink">
                Phiên bản {item.version}{item.version === current ? ' (bản này)' : ''}
              </span>
              <StatusChip kind={status.kind}>{status.label}</StatusChip>
            </div>
            <p className="text-note text-ink-2">{item.reason_text}</p>
          </li>
        )
      })}
    </ol>
  )
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
