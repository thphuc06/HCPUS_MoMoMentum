import { Link } from 'react-router'
import { ScreenHeader } from '@/components/ScreenHeader'
import { SimNote } from '@/components/SimNote'
import { ErrorState, ListSkeleton } from '@/components/StateViews'
import { buttonVariants } from '@/components/ui/button'
import { StressResult } from './StressResult'
import { useStress } from './useResilience'

export function StressResultScreen({ shockId }: { shockId: string }) {
  const result = useStress(shockId)

  return (
    <>
      <ScreenHeader title="Mô phỏng cú sốc" backTo="/foresight" />
      {result.status === 'loading' && <ListSkeleton rows={1} rowClass="h-72" label="Đang mô phỏng cú sốc" />}
      {result.status === 'error' && (
        <ErrorState
          className="px-4"
          error={result.error}
          title="Chưa mô phỏng được cú sốc"
          onRetry={result.error.retryable ? () => void result.reload() : undefined}
        />
      )}
      {result.data && (
        <>
          <div className="space-y-3 px-4">
            <StressResult data={result.data.data} heading="h2" animateScore />
            <Link to="/roadmap" className={buttonVariants({ className: 'w-full' })}>Xem lộ trình thích ứng</Link>
          </div>
          <SimNote />
        </>
      )}
    </>
  )
}
