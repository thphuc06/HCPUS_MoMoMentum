import { useCallback, useState } from 'react'
import { useApi } from '@/api/ApiProvider'
import { ApiError } from '@/api/errors'
import { parseNudgeCard, type NudgeOutcome } from '@/api/phase5Schemas'
import { useApiResource } from '@/api/resource'

/** Người dùng đã gạt bản tin này đi (để sau, bỏ qua, ít nhắc loại này): không hiện lại trong ngày. "Đã làm" thì vẫn hiện. */
const HIDES: ReadonlySet<NudgeOutcome> = new Set(['snoozed', 'dismissed', 'less_like_this'])

/**
 * Bản tin chủ động của hôm nay (`GET /nudges/today`, tối đa một việc do cổng giá trị của batch đêm chọn) và phản hồi của người dùng
 * (`POST /nudges/{id}/feedback`, không qua token vì không đụng tiền).
 *
 * `state`: `loading` (chưa biết), `none` (không có bản tin hoặc không đọc được: Tổng quan dùng thẻ tất định của `GET /overview`),
 * `hidden` (có bản tin nhưng người dùng đã gạt đi: không hiện thẻ nào), `show` (hiện `card`).
 */
export function useTodayNudge() {
  const api = useApi()
  const res = useApiResource((a) => a.getTodayNudge(), [])
  const [local, setLocal] = useState<Record<string, NudgeOutcome>>({})
  const [error, setError] = useState<ApiError | null>(null)
  const [sending, setSending] = useState(false)

  const card = parseNudgeCard(res.data)
  const nudgeId = card?.data.nudge_id
  const outcome = nudgeId ? local[nudgeId] ?? res.data?.nudge?.outcome : undefined
  const state: 'loading' | 'none' | 'hidden' | 'show' =
    res.status === 'loading' ? 'loading' : !card ? 'none' : outcome && HIDES.has(outcome) ? 'hidden' : 'show'

  const feedback = useCallback(
    async (next: NudgeOutcome) => {
      if (!nudgeId) return
      setSending(true)
      setError(null)
      try {
        const r = await api.submitNudgeFeedback(nudgeId, { outcome: next })
        setLocal((m) => ({ ...m, [r.nudge_id]: r.outcome }))
      } catch (e) {
        setError(e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0))
      } finally {
        setSending(false)
      }
    },
    [api, nudgeId],
  )

  return { state, card, appDate: res.data?.app_date, feedback, error, sending }
}
