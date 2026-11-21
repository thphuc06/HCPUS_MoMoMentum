import { AlertTriangle, ArrowDownRight, CheckCircle2, Info, Sparkles } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { ReactNode } from 'react'

// Figma StatusChip (5:60): Đủ, Sát, Hụt, AI, Thông tin. Ba trạng thái luôn có biểu tượng + chữ (không chỉ màu).
export type ChipKind = 'ok' | 'warn' | 'bad' | 'info' | 'ai'

const STYLE: Record<ChipKind, { cls: string; Icon: typeof CheckCircle2 }> = {
  ok: { cls: 'bg-ok-bg text-ok-fg', Icon: CheckCircle2 },
  warn: { cls: 'bg-warn-bg text-warn-fg', Icon: AlertTriangle },
  bad: { cls: 'bg-bad-bg text-bad-fg', Icon: ArrowDownRight },
  info: { cls: 'bg-blue-tint text-blue', Icon: Info },
  ai: { cls: 'bg-tint text-brand-text', Icon: Sparkles },
}

export function StatusChip({ kind, children, className }: { kind: ChipKind; children: ReactNode; className?: string }) {
  const { cls, Icon } = STYLE[kind]
  return (
    <span
      data-chip={kind}
      className={cn('inline-flex h-7 items-center gap-1.5 rounded-full pr-2.5 pl-2 text-small font-semibold whitespace-nowrap', cls, className)}
    >
      <Icon className="size-4 shrink-0" aria-hidden />
      <span>{children}</span>
    </span>
  )
}

/** Nhãn "Do AI tạo" ở đầu sheet và trên từng khối do AI sinh. */
export function AiChip({ children = 'AI', className }: { children?: ReactNode; className?: string }) {
  return (
    <StatusChip kind="ai" className={className}>
      {children}
    </StatusChip>
  )
}
