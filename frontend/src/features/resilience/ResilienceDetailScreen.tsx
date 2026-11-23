import { ScreenHeader } from '@/components/ScreenHeader'
import { SimNote } from '@/components/SimNote'
import { ErrorState, ListSkeleton } from '@/components/StateViews'
import { ResilienceScore } from './ResilienceScore'
import { useResilience } from './useResilience'

export function ResilienceDetailScreen() {
  const score = useResilience()

  return (
    <>
      <ScreenHeader title="Chi tiết điểm chống chịu" backTo="/foresight" />
      {score.status === 'loading' && <ListSkeleton rows={1} rowClass="h-96" label="Đang tải chi tiết điểm chống chịu" />}
      {score.status === 'error' && (
        <ErrorState className="px-4" error={score.error} title="Chưa tải được chi tiết điểm chống chịu" onRetry={() => void score.reload()} />
      )}
      {score.data && (
        <>
          <div className="px-4"><ResilienceScore data={score.data.data} heading="h2" /></div>
          <SimNote />
        </>
      )}
    </>
  )
}
