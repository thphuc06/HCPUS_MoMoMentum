import { ScreenHeader } from '@/components/ScreenHeader'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/StateViews'
import { ReviewAssignments } from '@/features/review/ReviewAssignments'
import { useReview } from '@/features/review/useReview'

// Nhà của "giao dịch chờ xếp hũ" (ui-design-review.md §10): hai hàng chờ khác bản chất nhưng cùng một việc. Giao dịch đang ở hũ Chưa
// phân loại (`daily_ask`, tiền đã chi mà chưa vào hũ nào) lên trước; rồi giao dịch Yofina đã tự xếp ở mức tin cậy vừa (`review`).
// Mục "Việc cần làm" ở Tổng quan và dòng nhỏ ở Nhìn trước đều dẫn về đây. Mỗi danh sách tải và báo lỗi riêng.
export function ReviewPage() {
  const unclassified = useReview('daily_ask')
  const review = useReview('review')
  const pending = unclassified.status === 'ready' && unclassified.data.data.items.length > 0 ? unclassified.data.data : null
  const allDone = review.status === 'ready' && review.data.data.items.length === 0 && unclassified.status !== 'loading' && !pending
  return (
    <>
      <ScreenHeader title="Xem lại" backTo="/" />
      <div className="space-y-3 px-4 pb-6">
        {(review.status === 'loading' || unclassified.status === 'loading') && <ListSkeleton label="Đang tải giao dịch cần xem lại" />}
        {unclassified.status === 'error' && (
          <ErrorState className="[&_button]:min-h-11" error={unclassified.error} title="Chưa tải được giao dịch chưa xếp hũ" onRetry={() => void unclassified.reload()} />
        )}
        {pending && <ReviewAssignments data={pending} disabled={unclassified.status === 'ready' && unclassified.refreshing} title="Giao dịch chưa xếp hũ" />}
        {review.status === 'error' && (
          <ErrorState className="[&_button]:min-h-11" error={review.error} title="Chưa tải được giao dịch cần xem lại" onRetry={() => void review.reload()} />
        )}
        {review.status === 'ready' && review.data.data.items.length > 0 && <ReviewAssignments data={review.data.data} disabled={review.refreshing} />}
        {allDone && review.status === 'ready' && <EmptyState title="Đã xem lại xong" message={review.data.data.headline} />}
      </div>
    </>
  )
}
