import { useCallback, useEffect, useRef, useState } from 'react'
import { useApi } from '@/api/ApiProvider'
import { ApiError } from '@/api/errors'
import { INGEST_STOP_STATUSES, type IngestJobResponse } from '@/api/ingestSchemas'
import { DEFAULT_POLL, type PollTiming } from './config'

export type IngestJobState = {
  job: IngestJobResponse | null
  /** Lỗi không tạm thời (job không có, phiên hết hạn...): đã dừng hỏi. Lỗi tạm thời (mạng) thì vẫn hỏi tiếp. */
  error: ApiError | null
  /** Đã quá `timeoutMs` mà job chưa tới trạng thái dừng: đã dừng hỏi, chờ người dùng bấm Thử lại. */
  slow: boolean
  polling: boolean
  /** Hỏi lại từ đầu (sau khi "lâu hơn thường lệ", lỗi, hoặc để lấy trạng thái mới sau khi chốt). */
  retry: () => void
}

/**
 * Theo dõi một lần nạp bằng `GET /ingest/jobs/{job_id}`: lần đầu sau `firstDelayMs`, rồi `delayMs` (1,5 s), lùi dần theo
 * `backoff` tới `maxDelayMs`. Dừng khi job tới `review`, `done`, `failed`, `rejected`; khi component rời trang (unmount) hoặc
 * `jobId` đổi; khi gặp lỗi không tạm thời; hoặc khi quá `timeoutMs` (đặt `slow`). Không chạy hai vòng hỏi cùng lúc.
 */
export function useIngestJob(jobId: string | null, timing: PollTiming = DEFAULT_POLL): IngestJobState {
  const api = useApi()
  const [job, setJob] = useState<IngestJobResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [slow, setSlow] = useState(false)
  const [polling, setPolling] = useState(false)
  const [round, setRound] = useState(0)
  const timingRef = useRef(timing)
  timingRef.current = timing

  useEffect(() => {
    setJob(null)
  }, [jobId])

  useEffect(() => {
    if (!jobId) return
    const t = timingRef.current
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const startedAt = Date.now()
    let delay = t.delayMs
    setError(null)
    setSlow(false)
    setPolling(true)

    const next = (ms: number) => {
      if (stopped) return
      if (Date.now() - startedAt + ms > t.timeoutMs) {
        setSlow(true)
        setPolling(false)
        return
      }
      timer = setTimeout(tick, ms)
    }

    async function tick() {
      try {
        const j = await api.getIngestJob(jobId!)
        if (stopped) return
        setJob(j)
        setError(null)
        if (INGEST_STOP_STATUSES.has(j.status)) {
          setPolling(false)
          return
        }
      } catch (e) {
        if (stopped) return
        const err = e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0)
        setError(err)
        if (!err.retryable) {
          setPolling(false)
          return
        }
      }
      const ms = delay
      delay = Math.min(t.maxDelayMs, Math.round(delay * t.backoff))
      next(ms)
    }

    next(t.firstDelayMs)
    return () => {
      stopped = true
      if (timer) clearTimeout(timer)
    }
  }, [api, jobId, round])

  const retry = useCallback(() => setRound((r) => r + 1), [])
  return { job, error, slow, polling, retry }
}
