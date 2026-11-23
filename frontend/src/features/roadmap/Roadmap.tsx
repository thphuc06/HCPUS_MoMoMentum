import { StatusChip } from '@/components/StatusChip'
import { Button } from '@/components/ui/button'
import type { RoadmapAlternative, RoadmapData } from '@/contracts/blocks'
import { RoadmapStep, STEP_STATUS, type StepActions } from './RoadmapStep'

const VERSION_STATUS = {
  active: { kind: 'ok', label: 'Đang dùng' },
  proposed: { kind: 'info', label: 'Bản đề xuất' },
  superseded: { kind: 'info', label: 'Đã thay thế' },
  discarded: { kind: 'info', label: 'Đã bỏ' },
} as const

const FEASIBILITY = {
  on_track: { kind: 'ok', label: 'Kịp hạn' },
  relaxed: { kind: 'warn', label: 'Khả thi sau điều chỉnh' },
  infeasible: { kind: 'bad', label: 'Chưa khả thi' },
} as const

type Props = StepActions & {
  data: RoadmapData
  onAlternative?: (option: RoadmapAlternative) => void
}

export function Roadmap({ data, onAlternative, ...actions }: Props) {
  const version = VERSION_STATUS[data.status]
  const feasibility = FEASIBILITY[data.feasibility]
  const jarNames = new Map(data.goals.map(({ jar }) => [jar.code, jar.name]))

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
      <ol aria-label="Các giai đoạn" className="space-y-3">
        {data.phases.map((phase) => (
          <li key={phase.phase_id}>
            <h4 className="text-small font-semibold text-ink">{phase.title}</h4>
            {phase.summary && <p className="mt-1 text-small text-ink-2">{phase.summary}</p>}
            <ol className="mt-2 space-y-2">
              {phase.steps.map((step) => <RoadmapStep key={step.step_id} step={step} jarNames={jarNames} {...actions} />)}
            </ol>
          </li>
        ))}
      </ol>
    </section>
  )
}
