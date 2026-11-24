import { Link } from 'react-router'
import { ChevronRight, Route } from 'lucide-react'
import type { RoadmapVersionsResponse } from '@/api/roadmapSchemas'
import { useChatLauncher } from '@/chat/launcher'
import { StatusChip } from '@/components/StatusChip'
import { ErrorState, ListSkeleton } from '@/components/StateViews'
import { Button } from '@/components/ui/button'
import { FEASIBILITY } from './Roadmap'
import { useRoadmapVersions } from './useRoadmapVersions'

// Lối vào trang Lộ trình từ tab Nhìn trước (nhà của lộ trình, ui-design-review.md §10). Tổng quan chỉ có một dòng "Việc cần làm" khi
// lộ trình có việc (features/overview/TodoList.tsx). Chỉ đọc `GET /roadmap/versions` (danh sách gọn đã có trạng thái, mức khả thi và
// số bước theo trạng thái), không tính gì thêm.

export const ROADMAP_PATH = '/roadmap'
/** Câu gửi vào chat khi chưa có lộ trình (người dùng bấm "Lập lộ trình"). */
export const ROADMAP_PROMPT = 'Lập giúp mình lộ trình tiết kiệm cho các mục tiêu hiện tại'

export type RoadmapEntrySummary = {
  /** Phiên bản hiện trên lối vào: bản đang dùng; chưa có bản đang dùng thì bản đề xuất, rồi bản mới nhất. */
  version: number
  active: boolean
  feasibility: keyof typeof FEASIBILITY
  pending: number
  /** Có bản đề xuất mới đang chờ người dùng chọn. */
  hasProposed: boolean
  regenerating: boolean
}

export function summarizeRoadmap(data: RoadmapVersionsResponse): RoadmapEntrySummary | null {
  const { versions } = data
  if (versions.length === 0) return null
  const byVersion = (v?: number) => (v === undefined ? undefined : versions.find((x) => x.version === v))
  const active = byVersion(data.active_version) ?? versions.find((x) => x.status === 'active')
  const shown = active ?? byVersion(data.proposed_version) ?? versions[0]!
  const job = data.current_job
  return {
    version: shown.version,
    active: shown.status === 'active',
    feasibility: shown.feasibility,
    pending: shown.counts.pending,
    hasProposed: data.proposed_version !== undefined,
    regenerating: !!job && (job.status === 'queued' || job.status === 'running'),
  }
}

function versionLine(s: RoadmapEntrySummary) {
  return s.active ? `Đang dùng phiên bản ${s.version}` : `Phiên bản ${s.version} chờ bạn chọn`
}

function Chips({ s }: { s: RoadmapEntrySummary }) {
  const f = FEASIBILITY[s.feasibility]
  return (
    <span className="flex flex-wrap gap-1.5">
      <StatusChip kind={f.kind}>{f.label}</StatusChip>
      {s.hasProposed && s.active && <StatusChip kind="info">Có phiên bản mới</StatusChip>}
    </span>
  )
}

function useStartRoadmapChat() {
  const launcher = useChatLauncher()
  return () => launcher.open(ROADMAP_PROMPT)
}

/** Thẻ "Lộ trình thích ứng" trên tab Nhìn trước (sau khối Điểm chống chịu, trước "Thử cú sốc tài chính"). */
export function RoadmapEntryCard() {
  const versions = useRoadmapVersions()
  const start = useStartRoadmapChat()
  const summary = versions.data ? summarizeRoadmap(versions.data) : null

  return (
    <section aria-labelledby="roadmap-entry-heading" className="space-y-2">
      <h2 id="roadmap-entry-heading" className="px-4 text-section font-bold text-ink">Lộ trình thích ứng</h2>
      {versions.status === 'loading' && <ListSkeleton rows={1} label="Đang tải lộ trình" />}
      {versions.status === 'error' && !versions.data && (
        <ErrorState className="px-4" error={versions.error} title="Chưa tải được lộ trình" onRetry={() => void versions.reload()} />
      )}
      {versions.data && !summary && (
        <div className="mx-4 rounded-card bg-surface p-4 shadow-card" data-testid="roadmap-entry-empty">
          <p className="text-small text-ink">Chưa có lộ trình. Yofina có thể lập các bước theo mục tiêu và thu chi của bạn.</p>
          <Button type="button" size="sm" className="mt-3" onClick={start}>Lập lộ trình</Button>
        </div>
      )}
      {summary && (
        <Link
          to={ROADMAP_PATH}
          data-testid="roadmap-entry"
          className="mx-4 flex min-h-16 items-center gap-3 rounded-card bg-surface p-4 shadow-card"
        >
          <span className="grid size-11 shrink-0 place-items-center rounded-full bg-tint text-brand-text">
            <Route className="size-5" aria-hidden />
          </span>
          <span className="min-w-0 flex-1 space-y-1">
            <span className="block text-subtitle font-semibold text-ink">{versionLine(summary)}</span>
            <Chips s={summary} />
            <span className="num block text-small text-ink-2">
              {summary.pending} bước chờ{summary.regenerating ? ' · Đang lập lại lộ trình' : ''}
            </span>
          </span>
          <ChevronRight className="size-5 shrink-0 text-ink-2" aria-hidden />
        </Link>
      )}
    </section>
  )
}
