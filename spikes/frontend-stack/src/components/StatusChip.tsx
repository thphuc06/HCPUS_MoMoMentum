import { AlertTriangle, ArrowDownRight, CheckCircle2 } from 'lucide-react'
import { cn } from 'cn'

export type Verdict = 'enough' | 'tight' | 'short'

const STYLE: Record<Verdict, { cls: string; Icon: typeof CheckCircle2 }> = {
  enough: { cls: 'bg-ok-soft text-ok-ink', Icon: CheckCircle2 },
  tight: { cls: 'bg-warn-soft text-warn-ink', Icon: AlertTriangle },
  short: { cls: 'bg-short-soft text-short-ink', Icon: ArrowDownRight },
}

// Ba lớp mã hóa: màu + biểu tượng + chữ (WCAG 1.4.1).
export function StatusChip({ verdict, children, className }: { verdict: Verdict; children: React.ReactNode; className?: string }) {
  const { cls, Icon } = STYLE[verdict]
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[12px] font-semibold leading-tight', cls, className)}>
      <Icon className="size-3.5 shrink-0" aria-hidden />
      <span>{children}</span>
    </span>
  )
}
