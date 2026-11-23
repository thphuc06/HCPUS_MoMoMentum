import { StatusChip } from '@/components/StatusChip'
import type { RoadmapStep as RoadmapStepData } from '@/contracts/blocks'
import { formatDayMonth } from '@/lib/dates'
import { formatVnd } from '@/lib/format'

export const STEP_STATUS = {
  pending: { kind: 'warn', label: 'Chờ' },
  accepted: { kind: 'ok', label: 'Đã chấp nhận' },
  rejected: { kind: 'bad', label: 'Đã từ chối' },
} as const

export function RoadmapStep({ step, jarNames }: { step: RoadmapStepData; jarNames?: ReadonlyMap<string, string> }) {
  const status = STEP_STATUS[step.status]
  const jars = [step.jar_code, step.to_jar_code].flatMap((code) => (code ? [jarNames?.get(code) ?? code] : []))

  return (
    <li className="space-y-1 rounded-xl bg-surface-2 px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="min-w-0 text-small font-semibold text-ink">{step.title}</p>
        <StatusChip kind={status.kind}>{status.label}</StatusChip>
      </div>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-small text-ink-2">
        {step.amount_vnd !== undefined && <span className="num font-semibold text-ink">{formatVnd(step.amount_vnd)}</span>}
        {jars.length > 0 && <span>Hũ {jars.join(' → ')}</span>}
        {step.due_date && <span>Hạn {formatDayMonth(step.due_date)}</span>}
      </div>
      <details>
        <summary className="w-fit cursor-pointer py-1.5 text-small font-semibold text-brand-text">Vì sao</summary>
        <p className="pb-1 text-small text-ink-2">{step.reason}</p>
      </details>
    </li>
  )
}
