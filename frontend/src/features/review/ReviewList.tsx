import type { ReactNode } from 'react'
import type { ReviewListData } from '@/contracts/blocks'
import { formatVnd } from '@/lib/format'
import { ReviewItemRow, type ReviewRowActions } from './ReviewItemRow'

export function ReviewList({ data, actions, footer, title: titleOverride }: { data: ReviewListData; actions?: ReviewRowActions; footer?: ReactNode; title?: string }) {
  const title = titleOverride ?? (data.mode === 'review' ? 'Xem lại giao dịch' : 'Chọn hũ cho giao dịch hôm nay')
  return (
    <section aria-label={title} data-block="review_list" className="space-y-3 rounded-card bg-surface p-4 shadow-card">
      <header className="space-y-1">
        <h3 className="text-subtitle font-semibold text-ink">{title}</h3>
        {/* Câu mở đầu của server nhắc lại đúng số giao dịch và tổng tiền của dòng dưới: chỉ cho trình đọc màn hình (§10). */}
        {data.items.length > 0 && <p className="sr-only">{data.headline}</p>}
        <p className="num text-small font-semibold text-ink">{data.count} giao dịch · {formatVnd(data.pending_total_vnd)}</p>
      </header>
      {data.items.length === 0 ? (
        <p data-state="empty" className="rounded-xl bg-surface-2 p-3 text-center text-small text-ink-2">{data.headline}</p>
      ) : (
        <ul className="space-y-2">
          {data.items.map((item) => <ReviewItemRow key={item.transaction_id} item={item} actions={actions} allowKeep={data.mode === 'review'} />)}
        </ul>
      )}
      {footer}
    </section>
  )
}
