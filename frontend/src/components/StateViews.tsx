import type { ReactNode } from 'react'
import { RotateCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import type { ApiError } from '@/api/errors'

/** Trạng thái lỗi: thông báo tiếng Việt của mã lỗi + nút Thử lại (không ẩn lỗi, không số giả). */
export function ErrorState({ error, title = 'Chưa tải được dữ liệu', onRetry, className }: { error: ApiError; title?: string; onRetry?: () => void; className?: string }) {
  return (
    <div role="alert" data-state="error" className={className}>
      <div className="rounded-card bg-bad-bg p-4 text-bad-fg">
        <p className="text-subtitle font-semibold">{title}</p>
        <p className="mt-1 text-small text-ink">{error.message}</p>
        {error.traceId && <p className="mt-1 text-note text-ink-2">Mã theo dõi: {error.traceId}</p>}
        {onRetry && (
          <Button type="button" variant="soft" size="sm" className="mt-3 bg-surface" onClick={onRetry}>
            <RotateCw className="size-4" aria-hidden />
            Thử lại
          </Button>
        )}
      </div>
    </div>
  )
}

/** Trạng thái rỗng nói thật (không dữ liệu giả), có thể kèm hành động. */
export function EmptyState({ title, message, action, className }: { title: string; message: string; action?: ReactNode; className?: string }) {
  return (
    <div data-state="empty" className={`rounded-card bg-surface px-6 py-8 text-center shadow-card ${className ?? ''}`}>
      <h2 className="text-subtitle font-semibold text-ink">{title}</h2>
      <p className="mx-auto mt-1 max-w-[280px] text-small text-ink-2">{message}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  )
}

/** Khung chờ cho một danh sách thẻ (có aria-busy để đọc màn hình hiểu đang tải). */
export function ListSkeleton({ rows = 4, label = 'Đang tải', rowClass = 'h-[72px]' }: { rows?: number; label?: string; rowClass?: string }) {
  return (
    <div role="status" aria-busy="true" aria-label={label} data-state="loading" className="space-y-3 px-4">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={`${rowClass} w-full rounded-card`} />
      ))}
    </div>
  )
}
