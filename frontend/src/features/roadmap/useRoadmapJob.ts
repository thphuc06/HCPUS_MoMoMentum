import { useCallback, useEffect, useState } from 'react'
import { useApi } from '@/api/ApiProvider'
import { ApiError } from '@/api/errors'
import type { RoadmapJob } from '@/api/roadmapSchemas'
import { ROADMAP_JOB_POLL } from '@/lib/config'

export function isRoadmapJobPending(job: RoadmapJob) {
  return job.status === 'queued' || job.status === 'running'
}

type PollResult = {
  id: string
  round: number
  job?: RoadmapJob
  error?: ApiError
  timedOut?: boolean
}

export function useRoadmapJob(initial: RoadmapJob | null, timing = ROADMAP_JOB_POLL) {
  const api = useApi()
  const id = initial?.job_id
  const pending = initial !== null && isRoadmapJobPending(initial)
  const { delayMs, timeoutMs } = timing
  const [result, setResult] = useState<PollResult | null>(null)
  const [round, setRound] = useState(0)

  useEffect(() => {
    if (!id || !pending) return
    const key = { id, round }
    let stopped = false
    let next: ReturnType<typeof setTimeout>
    const deadline = setTimeout(() => {
      stop()
      setResult((previous) => ({ ...key, job: previous?.id === id ? previous.job : undefined, timedOut: true }))
    }, timeoutMs)

    function stop() {
      stopped = true
      clearTimeout(next)
      clearTimeout(deadline)
    }

    async function tick() {
      try {
        const job = await api.getRoadmapJob(key.id)
        if (stopped) return
        setResult({ ...key, job })
        if (!isRoadmapJobPending(job)) {
          stop()
          return
        }
      } catch (e) {
        if (stopped) return
        const error = e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0)
        if (!error.retryable) {
          setResult((previous) => ({ ...key, job: previous?.id === key.id ? previous.job : undefined, error }))
          stop()
          return
        }
      }
      next = setTimeout(tick, delayMs)
    }

    next = setTimeout(tick, delayMs)
    return stop
  }, [api, id, pending, round, delayMs, timeoutMs])

  const current = id === result?.id && round === result?.round ? result : null
  const job = current?.job ?? initial
  const retry = useCallback(() => setRound((r) => r + 1), [])
  return {
    job,
    error: current?.error,
    timedOut: current?.timedOut ?? false,
    polling: job !== null && isRoadmapJobPending(job) && !current?.error && !current?.timedOut,
    retry,
  }
}
