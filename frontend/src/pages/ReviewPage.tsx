import { ScreenHeader } from '@/components/ScreenHeader'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/StateViews'
import { ReviewAssignments } from '@/features/review/ReviewAssignments'
import { useReview } from '@/features/review/useReview'

export function ReviewPage() {
  const review = useReview('review')
  return (
    <>
      <ScreenHeader title="Xem lại" backTo="/" />
      {review.status === 'loading' && <ListSkeleton label="Đang tải giao dịch cần xem lại" />}
      {review.status === 'error' && (
        <ErrorState className="px-4 [&_button]:min-h-11" error={review.error} title="Chưa tải được giao dịch cần xem lại" onRetry={() => void review.reload()} />
      )}
      {review.status === 'ready' && (
        <div className="px-4 pb-6">
          {review.data.data.items.length === 0 ? (
            <EmptyState title="Đã xem lại xong" message={review.data.data.headline} />
          ) : (
            <ReviewAssignments data={review.data.data} disabled={review.refreshing} />
          )}
        </div>
      )}
    </>
  )
}
