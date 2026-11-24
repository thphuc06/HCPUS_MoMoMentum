import type { ReactNode } from 'react'
import { Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Disclosure } from '@/components/ui/Disclosure'
import { StatusChip } from './StatusChip'
import type { ProactiveCardData } from '@/contracts/blocks'

type Action = ProactiveCardData['actions'][number]

const STATUS_CHIP = {
  ok: { kind: 'info', label: 'Thông tin' },
  tight: { kind: 'warn', label: 'Sát' },
  short: { kind: 'bad', label: 'Hụt' },
} as const

// Figma ProactiveCard (14:176): MỘT việc, lý do ngắn, hành động chính ở đầu rồi các hành động phụ; "Để sau" ở góc,
// "Ít nhắc loại này" dạng chữ. Nút do server liệt kê (`actions`); ý nghĩa từng `kind` do nơi dùng xử lý (onAction).
export function ProactiveCard({ data, onAction, hero, children }: {
  data: ProactiveCardData
  onAction: (a: Action) => void
  /** Số chính của thẻ (vd. "12 ngày" hũ trống của cảnh báo cạn), đặt ngay dưới tiêu đề; có số chính thì lý do xuống sau phần vẽ. */
  hero?: ReactNode
  children?: ReactNode
}) {
  const snooze = data.actions.find((a) => a.kind === 'snooze')
  const mute = data.actions.find((a) => a.kind === 'mute_kind')
  const main = data.actions.filter((a) => a.kind !== 'snooze' && a.kind !== 'mute_kind')
  const chip = STATUS_CHIP[data.status]
  // Có số chính và dải ngày thì câu lý do ("Còn …, còn … ngày tới kỳ lương") nhắc lại điều phần vẽ đã nói: thu vào "Chi tiết".
  const reason = hero ? (
    <Disclosure label="Chi tiết" className="mt-1" panelClassName="pb-1 text-small text-ink-2">
      <p data-testid="proactive-reason">{data.reason}</p>
    </Disclosure>
  ) : (
    <p className="mt-1 text-body text-ink" data-testid="proactive-reason">{data.reason}</p>
  )
  return (
    <section aria-label="Việc cần làm hôm nay" data-block="proactive_card" data-kind={data.kind} data-status={data.status} className="rounded-card bg-surface p-5 shadow-card">
      <header className="flex items-center justify-between gap-2">
        <span className="inline-flex h-8 items-center gap-1.5 rounded-full bg-tint pr-3 pl-2.5 text-small font-semibold text-brand-text">
          <Sparkles className="size-4" aria-hidden />
          Việc cần làm hôm nay
        </span>
        {snooze && (
          <button type="button" onClick={() => onAction(snooze)} className="min-h-11 px-2 text-small font-semibold text-ink-2">
            {snooze.label}
          </button>
        )}
      </header>
      <div className="mt-2 flex items-start gap-2">
        <h2 className="min-w-0 flex-1 text-subtitle font-bold text-ink">{data.title}</h2>
        <StatusChip kind={chip.kind}>{chip.label}</StatusChip>
      </div>
      {hero}
      {!hero && reason}
      {children}
      {hero && reason}
      <div className="mt-4 flex flex-wrap items-center gap-2.5">
        {main.map((a, i) => (
          <Button key={`${a.kind}-${a.label}`} type="button" variant={i === 0 ? 'default' : 'soft'} onClick={() => onAction(a)}>
            {a.label}
          </Button>
        ))}
        {mute && (
          <button type="button" onClick={() => onAction(mute)} className="min-h-11 px-2 text-small font-medium text-ink-2">
            {mute.label}
          </button>
        )}
      </div>
    </section>
  )
}
