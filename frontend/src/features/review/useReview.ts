import { useApiResource } from '@/api/resource'
import type { ReviewMode } from '@/api/reviewSchemas'

export function useReview(mode: ReviewMode) {
  return useApiResource((api) => api.getReview(mode), [mode])
}
