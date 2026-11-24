import { useMemo, type ReactNode } from 'react'
import { StatusChip } from '@/components/StatusChip'
import { Button } from '@/components/ui/button'
import type { RoadmapAlternative, RoadmapData } from '@/contracts/blocks'
import { useJarNames } from '@/features/common/useJarLookup'
import { RoadmapStep, STEP_STATUS, type StepActions } from './RoadmapStep'
import { formatDayMonth } from '@/lib/dates'

/** "21–30/11" khi cùng tháng, "28/11–05/12" khi khác tháng (ngày của server). */
function formatRange(start: string, end: string): string {
  if (start === end) return formatDayMonth(start)
  return start.slice(0, 7) === end.slice(0, 7) ? `${start.slice(8, 10)}–${formatDayMonth(end)}` : `${formatDayMonth(start)}–${formatDayMonth(end)}`
}

// Nhãn trạng thái phiên bản: nói rõ bản đề xuất CHƯA thay bản đang dùng và đang chờ người dùng chọn.
export const VERSION_STATUS = {
  active: { kind: 'ok', label: 'Đang dùng' },
  proposed: { kind: 'info', label: 'Đề xuất · chờ bạn chọn' },
  superseded: { kind: 'info', label: 'Bản cũ · đã thay' },
  discarded: { kind: 'info', label: 'Đã bỏ' },
} as const

export const FEASIBILITY = {
  on_track: { kind: 'ok', label: 'Kịp hạn' },
  relaxed: { kind: 'warn', label: 'Khả thi sau điều chỉnh' },
  infeasible: { kind: 'bad', label: 'Chưa khả thi' },
} as const

type Props = StepActions & {
  data: RoadmapData
  onAlternative?: (option: RoadmapAlternative) => void
  /** Phần cuối khối (ví dụ lối sang trang Lộ trình khi khối hiện trong chat). */
  footer?: ReactNode
}

export function Roadmap({ data, onAlternative, footer, ...actions }: Props) {
  const version = VERSION_STATUS[data.status]
  const feasibility = FEASIBILITY[data.feasibility]
  // Bước chỉ mang mã hũ: tên lấy từ mục tiêu của khối, còn lại từ danh sách hũ của người dùng (Tổng quan).
  const goalNames = useMemo(() => data.goals.map(({ jar }) => [jar.code, jar.name] as const), [data.goals])
  const jarNames = useJarNames(goalNames)
  // Số thứ tự liên tục trên cả lộ trình: nội dung là một trình tự thật nên đánh số.
  const { stepIndex, lastStepId } = useMemo(() => {
    const ids = data.phases.flatMap((phase) => phase.steps.map((step) => step.step_id))
    return { stepIndex: new Map(ids.map((id, i) => [id, i + 1])), lastStepId: ids.at(-1) }
  }, [data.phases])

  return (
    <section data-block="roadmap" className="space-y-3 rounded-card bg-surface p-4 shadow-card">
      <header className="space-y-2">
        <h3 className="text-subtitle font-semibold text-ink">Lộ trình · Phiên bản {data.version}</h3>
        <div className="flex flex-wrap gap-2">
          <StatusChip kind={version.kind}>{version.label}</StatusChip>
          <StatusChip kind={feasibility.kind}>{feasibility.label}</StatusChip>
        </div>
        <p className="text-small text-ink">{data.headline}</p>
        <p className="text-small text-ink-2">{data.reason.text}</p>
        {!!data.reason.detail?.length && (
          <dl className="space-y-1 text-small text-ink-2">
            {data.reason.detail.map((detail, i) => (
              <div key={i} className="flex flex-wrap justify-between gap-x-3">
                <dt>{detail.label}</dt>
                <dd className="num">{detail.before && `${detail.before} → `}{detail.after}</dd>
              </div>
            ))}
          </dl>
        )}
        <ul aria-label="Số bước theo trạng thái" className="flex flex-wrap gap-x-3 gap-y-1 text-note text-ink-2">
          {(['pending', 'accepted', 'rejected'] as const).map((status) => (
            <li key={status}>{STEP_STATUS[status].label} <strong className="num text-ink">{data.counts[status]}</strong></li>
          ))}
        </ul>
      </header>
      {data.feasibility === 'infeasible' && data.alternatives.length > 0 && (
        <div className="space-y-2 rounded-xl bg-warn-bg p-3">
          <h4 className="text-small font-semibold text-warn-fg">Lựa chọn điều chỉnh</h4>
          <ul className="space-y-2 text-small text-ink">
            {data.alternatives.map((option) => (
              <li key={option.option_id} className="space-y-1">
                {onAlternative ? (
                  <Button type="button" size="sm" variant="soft" className="h-auto min-h-11 max-w-full whitespace-normal text-left"
                    onClick={() => onAlternative(option)} disabled={actions.disabled}>
                    {option.label}
                  </Button>
                ) : <p className="font-semibold">{option.label}</p>}
                <p>{option.summary}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
      <ol aria-label="Các giai đoạn" className="pt-1">
        {data.phases.map((phase, phaseIndex) => (
          <li key={phase.phase_id} className="relative">
            {/* Dòng thời gian dọc: tiêu đề giai đoạn nằm trên trục, các bước là nút tròn nối bằng đoạn trục. */}
            <div className="relative pb-3 pl-11">
              <span aria-hidden className={`absolute bottom-0 left-[15px] w-0.5 bg-line ${phaseIndex > 0 ? 'top-0' : 'top-3'}`} />
              <span aria-hidden className="absolute top-1.5 left-[11px] size-2.5 rounded-full bg-surface ring-2 ring-line-strong" />
              <div className="flex flex-wrap items-baseline gap-x-2">
                <h4 className="text-small font-bold text-ink">{phase.title}</h4>
                <span className="num text-note text-ink-2">{formatRange(phase.start_date, phase.end_date)}</span>
              </div>
              {phase.summary && <p className="mt-0.5 text-small text-ink-2">{phase.summary}</p>}
            </div>
            <ol aria-label={`Các bước: ${phase.title}`}>
              {phase.steps.map((step) => (
                <RoadmapStep
                  key={step.step_id}
                  step={step}
                  index={stepIndex.get(step.step_id) ?? 0}
                  last={step.step_id === lastStepId}
                  jarNames={jarNames}
                  {...actions}
                />
              ))}
            </ol>
          </li>
        ))}
      </ol>
      {footer}
    </section>
  )
}
