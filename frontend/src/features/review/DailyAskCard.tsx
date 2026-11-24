import { useState } from 'react'
import { useApi } from '@/api/ApiProvider'
import { ApiError } from '@/api/errors'
import { ErrorState } from '@/components/StateViews'
import { Button } from '@/components/ui/button'
import type { ReviewListData } from '@/contracts/blocks'
import { ReviewAssignments } from './ReviewAssignments'

/** `onSkipped`: người dùng vừa "Để sau" câu hỏi gộp (Tổng quan đổi sang một dòng "Việc cần làm" có lối sang Xem lại). */
export function DailyAskCard({ data, refreshing, onSkipped }: { data?: ReviewListData; refreshing?: boolean; onSkipped?: () => void }) {
  const api = useApi()
  const [dismissedDate, setDismissedDate] = useState<string | null>(null)
  const [skipping, setSkipping] = useState(false)
  const [failure, setFailure] = useState<{ date: string; error: ApiError } | null>(null)
  const ask = data?.ask

  if (!data || data.mode !== 'daily_ask' || ask?.status !== 'open' || ask.ask_date === dismissedDate) return null
  const date = ask.ask_date

  async function skip() {
    if (skipping || refreshing) return
    setSkipping(true)
    setFailure(null)
    try {
      const result = await api.skipReviewAsk({ ask_date: date })
      setDismissedDate(result.ask_date)
      onSkipped?.()
    } catch (e) {
      setFailure({ date, error: e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0) })
    } finally {
      setSkipping(false)
    }
  }

  return (
    <ReviewAssignments
      data={data}
      disabled={skipping || refreshing}
      footer={
        <div className="space-y-2 border-t border-line pt-2">
          {failure?.date === date && <ErrorState error={failure.error} title="Chưa để sau được câu hỏi" />}
          <Button type="button" variant="ghost" size="sm" disabled={skipping || refreshing} onClick={() => void skip()}>
            {skipping ? 'Đang lưu…' : 'Để sau'}
          </Button>
        </div>
      }
    />
  )
}
