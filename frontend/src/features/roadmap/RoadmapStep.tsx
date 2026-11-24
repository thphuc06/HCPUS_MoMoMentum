import { useEffect, useRef, useState } from 'react'
import { ChevronDown, X } from 'lucide-react'
import { StatusChip } from '@/components/StatusChip'
import { Button } from '@/components/ui/button'
import { Drawer, DrawerContent, DrawerDescription, DrawerHeader, DrawerTitle } from '@/components/ui/drawer'
import type { RoadmapStep as RoadmapStepData } from '@/contracts/blocks'
import { usePhoneFrame } from '@/layout/FrameContext'
import { cn } from '@/lib/cn'
import { formatDayMonth } from '@/lib/dates'
import { formatVnd } from '@/lib/format'

// "Chờ" là thông tin, không phải mức "sát": dùng chip xanh thông tin để màu vàng chỉ còn nghĩa "sát" (ui-design-review.md §5, cảnh 4).
export const STEP_STATUS = {
  pending: { kind: 'info', label: 'Chờ' },
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

type Props = StepActions & {
  step: RoadmapStepData
  /** Số thứ tự của bước trên cả lộ trình (bắt đầu từ 1), vẽ trong nút tròn khi bước đang chờ. */
  index: number
  /** Bước cuối của lộ trình: không vẽ đoạn trục nối xuống. */
  last?: boolean
  jarNames?: ReadonlyMap<string, string>
}

/** Nút tròn trên trục theo trạng thái: số thứ tự (chờ), dấu tích trên nền "đủ" (đã chấp nhận), dấu X mờ (đã từ chối). */
function StepNode({ index, status, justAccepted }: { index: number; status: RoadmapStepData['status']; justAccepted: boolean }) {
  return (
    <span
      aria-hidden
      data-node={status}
      className={cn(
        'absolute top-0 left-0 grid size-8 place-items-center rounded-full',
        status === 'pending' && 'bg-surface text-small font-bold text-ink ring-2 ring-line-strong ring-inset',
        status === 'accepted' && 'bg-ok-line text-surface',
        status === 'rejected' && 'bg-surface-2 text-ink-2 ring-2 ring-line ring-inset',
        justAccepted && 'motion-pop',
      )}
    >
      {status === 'pending' && <span className="num">{index}</span>}
      {status === 'accepted' && (
        <svg viewBox="0 0 24 24" className="size-[18px]" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          {/* Dấu tích tự vẽ khi vừa chấp nhận (stroke-dashoffset, --dur-3). */}
          <path d="M5 12.5l4.5 4.5L19 7.5" pathLength="1" strokeDasharray="1" className={justAccepted ? 'motion-draw [--motion-delay:120ms]' : undefined} />
        </svg>
      )}
      {status === 'rejected' && <X className="size-4" strokeWidth={2.5} />}
    </span>
  )
}

type MenuEntry = { key: string; label: string; onSelect: () => void }

/**
 * Thao tác phụ của bước (Sửa, Từ chối) gom vào một bảng thao tác dưới đáy (action sheet), để mỗi bước chỉ còn một nút chính.
 * Dùng lại Drawer đã có của màn này nên không thêm thư viện hay chunk định vị popover.
 */
function StepMenu({ entries, disabled, title }: { entries: MenuEntry[]; disabled?: boolean; title: string }) {
  const frame = usePhoneFrame()
  const [open, setOpen] = useState(false)
  const label = `${entries.map((e, i) => (i === 0 ? e.label : e.label.toLowerCase())).join(', ')}…`
  return (
    <>
      <button
        type="button"
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`${label} (bước ${title})`}
        onClick={() => setOpen(true)}
        className="inline-flex h-11 items-center gap-1 rounded-full px-3 text-small font-bold text-brand-text outline-none hover:bg-tint focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50"
      >
        {label}
        <ChevronDown className="size-4" aria-hidden />
      </button>
      {open && (
        <Drawer open onOpenChange={(next) => { if (!next) setOpen(false) }}>
          <DrawerContent container={frame} className="rounded-t-sheet bg-background pb-[max(16px,env(safe-area-inset-bottom))] shadow-sheet">
            <DrawerHeader>
              <DrawerTitle className="text-section font-bold">Thao tác với bước</DrawerTitle>
              <DrawerDescription>{title}</DrawerDescription>
            </DrawerHeader>
            <div className="space-y-2 px-4 pt-3">
              {entries.map((e) => (
                <Button
                  key={e.key}
                  type="button"
                  variant={e.key === 'reject' ? 'destructive' : 'soft'}
                  className="w-full"
                  onClick={() => {
                    setOpen(false)
                    e.onSelect()
                  }}
                >
                  {e.label}
                </Button>
              ))}
              <Button type="button" variant="ghost" className="w-full" onClick={() => setOpen(false)}>
                Hủy
              </Button>
            </div>
          </DrawerContent>
        </Drawer>
      )}
    </>
  )
}
export function RoadmapStep({ step, index, last = false, jarNames, onAccept, onReject, onEdit, onExecute, disabled }: Props) {
  const status = STEP_STATUS[step.status]
  // Chỉ hiện tên hũ; chưa có tên (danh sách hũ chưa tải) thì ẩn dòng hũ thay vì lộ mã thô như "giai_tri".
  const codes = [step.jar_code, step.to_jar_code].filter((code): code is string => !!code)
  const names = codes.map((code) => jarNames?.get(code))
  const jars = names.every((name): name is string => !!name) ? names : []

  // Vừa chuyển sang "đã chấp nhận" ngay trên màn này (không phải lúc tải): nút tròn đổ màu và dấu tích tự vẽ một lần.
  const previous = useRef(step.status)
  const [justAccepted, setJustAccepted] = useState(false)
  useEffect(() => {
    if (previous.current !== 'accepted' && step.status === 'accepted') setJustAccepted(true)
    previous.current = step.status
  }, [step.status])

  // Một nút chính theo trạng thái: chờ hoặc đã từ chối thì "Chấp nhận"; đã chấp nhận và có việc đổi tiền thì "Thực hiện".
  const primary =
    onAccept && step.status !== 'accepted'
      ? { label: 'Chấp nhận', run: () => onAccept(step) }
      : onExecute && step.status === 'accepted' && step.action
        ? { label: 'Thực hiện', run: () => onExecute(step) }
        : null
  const entries: MenuEntry[] = []
  if (onEdit) entries.push({ key: 'edit', label: 'Sửa', onSelect: () => onEdit(step) })
  if (onReject && step.status !== 'rejected') entries.push({ key: 'reject', label: 'Từ chối', onSelect: () => onReject(step) })

  return (
    <li className="relative pb-5 pl-11" data-step-status={step.status}>
      <StepNode index={index} status={step.status} justAccepted={justAccepted} />
      {!last && (
        <span
          aria-hidden
          data-axis={step.status === 'accepted' ? 'done' : 'todo'}
          className={cn(
            'absolute top-9 bottom-0 left-[15px] w-0.5',
            step.status === 'accepted' ? 'bg-ok-line' : 'bg-line',
          )}
        />
      )}
      <div className="space-y-1">
        <div className="flex flex-wrap items-start justify-between gap-x-2 gap-y-1 pt-1">
          <p className={cn('min-w-0 flex-1 text-body font-semibold', step.status === 'rejected' ? 'text-ink-2' : 'text-ink')}>{step.title}</p>
          <StatusChip kind={status.kind}>{status.label}</StatusChip>
        </div>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-small text-ink-2">
          {step.amount_vnd !== undefined && <span className="num text-subtitle font-bold text-ink">{formatVnd(step.amount_vnd)}</span>}
          {jars.length > 0 && <span>Hũ {jars.join(' → ')}</span>}
          {step.due_date && <span>Hạn {formatDayMonth(step.due_date)}</span>}
        </div>
        {/* Một hàng: nút chính, thao tác phụ, "Vì sao". Mở "Vì sao" thì lý do xuống dòng riêng, rộng hết bước. */}
        <div className="flex flex-wrap items-center gap-x-2">
          {primary && (
            <Button type="button" size="sm" disabled={disabled} onClick={primary.run}>
              {primary.label}
            </Button>
          )}
          {entries.length > 0 && <StepMenu entries={entries} disabled={disabled} title={step.title} />}
          <details className="open:basis-full">
            <summary className="min-h-11 w-fit min-w-11 cursor-pointer px-1 py-3 text-small font-semibold text-brand-text">Vì sao</summary>
            <p className="pb-1 text-small text-ink-2">{step.reason}</p>
          </details>
        </div>
      </div>
    </li>
  )
}
