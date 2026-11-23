import { AlertTriangle, Info, RotateCw, XCircle } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'

// Figma Notice (10:196): ngoài phạm vi (xanh dương), chế độ rút gọn (hổ phách), dữ liệu ít (hồng nhạt), lỗi (san hô).
// `info` (phase 4): trạng thái trống hoặc chỉ mang thông tin, không phải lỗi, nên dùng màu trung tính (nền surface-2, chữ ink).
// Mỗi loại có biểu tượng + tiêu đề + nội dung, không chỉ dựa vào màu.
export type NoticeKind = 'out_of_scope' | 'degraded' | 'low_data' | 'error' | 'info'

const STYLE: Record<NoticeKind, { box: string; title: string; Icon: typeof Info }> = {
  out_of_scope: { box: 'bg-blue-tint', title: 'text-blue', Icon: Info },
  degraded: { box: 'bg-warn-bg', title: 'text-warn-fg', Icon: AlertTriangle },
  low_data: { box: 'bg-tint', title: 'text-brand-text', Icon: Info },
  error: { box: 'bg-bad-bg', title: 'text-bad-fg', Icon: XCircle },
  info: { box: 'bg-surface-2', title: 'text-ink', Icon: Info },
}

export function Notice({
  kind,
  title,
  message,
  code,
  onRetry,
  children,
}: {
  kind: NoticeKind
  title: string
  message: string
  code?: string
  onRetry?: () => void
  children?: ReactNode
}) {
  const { box, title: titleCls, Icon } = STYLE[kind]
  return (
    <section role={kind === 'error' ? 'alert' : 'status'} data-notice={kind} className={cn('rounded-card p-4', box)}>
      <h3 className={cn('flex items-center gap-2 text-subtitle font-semibold', titleCls)}>
        <Icon className="size-5 shrink-0" aria-hidden />
        <span>{title}</span>
      </h3>
      <p className="mt-1 text-small text-ink">{message}</p>
      {code && <p className="mt-1 text-note text-ink-2">Mã: {code}</p>}
      {children}
      {onRetry && (
        <Button type="button" variant="soft" size="sm" className="mt-3 bg-surface" onClick={onRetry}>
          <RotateCw className="size-4" aria-hidden />
          Thử lại
        </Button>
      )}
    </section>
  )
}
