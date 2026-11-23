import { z } from 'zod'
import { ReviewAsk, ReviewListBlock, ReviewListData } from '@/contracts/blocks'
import { isIsoDate } from '@/lib/dates'
import { ApiError } from './errors'

export const ReviewListResponse = ReviewListBlock
export type ReviewListResponse = z.infer<typeof ReviewListResponse>
export type ReviewMode = ReviewListData['mode']

export const ReviewAskSkipRequest = z.strictObject({ ask_date: ReviewAsk.shape.ask_date.refine(isIsoDate) })
export type ReviewAskSkipRequest = z.infer<typeof ReviewAskSkipRequest>

export const ReviewAskResponse = ReviewAsk.strict()
export type ReviewAskResponse = z.infer<typeof ReviewAskResponse>

type Call = <T>(method: string, path: string, schema: z.ZodType<T>, body?: unknown) => Promise<T>

export function createReviewApi(call: Call) {
  return {
    getReview: (mode: ReviewMode) =>
      call('GET', `/review?${new URLSearchParams({ mode })}`, ReviewListResponse.refine((block) => block.data.mode === mode)),
    skipReviewAsk: async (request: ReviewAskSkipRequest) => {
      const parsed = ReviewAskSkipRequest.safeParse(request)
      if (!parsed.success) throw new ApiError('PARAMS_INVALID', 0)
      const response = ReviewAskResponse.refine((ask) => ask.ask_date === parsed.data.ask_date && ask.status !== 'open')
      return call('POST', '/review/daily-ask/skip', response, parsed.data)
    },
  }
}
