import { StatusChip } from '@/components/StatusChip'
import { Button } from '@/components/ui/button'
import type { RoadmapStep as RoadmapStepData } from '@/contracts/blocks'
import { formatDayMonth } from '@/lib/dates'
import { formatVnd } from '@/lib/format'

export const STEP_STATUS = {
  pending: { kind: 'warn', label: 'Chờ' },
  accepted: { kind: 'ok', label: 'Đã chấp nhận' },
  rejected: { kind: 'bad', label: 'Đã từ chối' },
} as const

export type StepActions = {
  onAccept?: (step: RoadmapStepData) => void
  onReject?: (step: RoadmapStepData) => void
  onEdit?: (step: RoadmapStepData) => void
  onExecute?: (step: RoadmapStepData) => void
  disabled?: boolean
}

type Props = StepActions & { step: RoadmapStepData; jarNames?: ReadonlyMap<string, string> }

export function RoadmapStep({ step, jarNames, onAccept, onReject, onEdit, onExecute, disabled }: Props) {
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
        <summary className="min-h-11 w-fit min-w-11 cursor-pointer py-3 text-small font-semibold text-brand-text">Vì sao</summary>
        <p className="pb-1 text-small text-ink-2">{step.reason}</p>
      </details>
      {(onAccept || onEdit || onReject || onExecute) && (
        <div className="flex flex-wrap gap-2">
          {onAccept && step.status !== 'accepted' && (
            <Button type="button" size="sm" variant="soft" disabled={disabled} onClick={() => onAccept(step)}>Chấp nhận</Button>
          )}
          {onEdit && (
            <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => onEdit(step)}>Sửa</Button>
          )}
          {onReject && step.status !== 'rejected' && (
            <Button type="button" size="sm" variant="destructive" disabled={disabled} onClick={() => onReject(step)}>Từ chối</Button>
          )}
          {onExecute && step.status === 'accepted' && step.action && (
            <Button type="button" size="sm" disabled={disabled} onClick={() => onExecute(step)}>Thực hiện</Button>
          )}
        </div>
      )}
    </li>
  )
}
