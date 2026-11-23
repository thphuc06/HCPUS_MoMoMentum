import { useRef, useState } from 'react'
import { useApi } from '@/api/ApiProvider'
import { ApiError } from '@/api/errors'
import type { RoadmapResponse, RoadmapStepDecisionRequest, RoadmapStepEditRequest } from '@/api/roadmapSchemas'

export function useRoadmapMutation(onConflict: () => Promise<unknown>) {
  const busy = useRef(false)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  async function run<T>(request: () => Promise<T>, onSuccess: (data: T) => void) {
    if (busy.current) return
    busy.current = true
    setWorking(true)
    setError(null)
    try {
      onSuccess(await request())
    } catch (e) {
      const error = e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0)
      setError(error)
      if (error.code === 'ROADMAP_VERSION_CONFLICT') await onConflict()
    } finally {
      busy.current = false
      setWorking(false)
    }
  }

  return { run, working, error, clearError: () => setError(null) }
}

export function useStepDecision(onUpdated: (block: RoadmapResponse) => void, onConflict: () => Promise<unknown>) {
  const api = useApi()
  const { run, working, error, clearError } = useRoadmapMutation(onConflict)
  return {
    decide: (stepId: string, req: RoadmapStepDecisionRequest) => run(() => api.decideRoadmapStep(stepId, req), onUpdated),
    edit: (stepId: string, req: RoadmapStepEditRequest) => run(() => api.editRoadmapStep(stepId, req), onUpdated),
    working,
    error,
    clearError,
  }
}
