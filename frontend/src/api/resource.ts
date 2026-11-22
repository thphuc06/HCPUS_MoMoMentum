import { useCallback, useEffect, useRef, useState } from 'react'
import { useApi, useDataVersion } from './ApiProvider'
import type { ApiClient } from './client'
import { ApiError } from './errors'

/** Hỏi lại định kỳ: sau `delayMs` gọi lại, tối đa `maxMs` kể từ lúc bắt đầu chờ (`null` = không cần hỏi lại nữa). */
export type PollPlan = { delayMs: number; maxMs: number } | null

export type Resource<T> =
  | { status: 'loading'; data: null; error: null; refreshing: false; reload: () => Promise<void> }
  | { status: 'ready'; data: T; error: null; refreshing: boolean; reload: () => Promise<void> }
  | { status: 'error'; data: T | null; error: ApiError; refreshing: false; reload: () => Promise<void> }

type State<T> = { status: 'loading' | 'ready' | 'error'; data: T | null; error: ApiError | null; refreshing: boolean }

/**
 * Tải một tài nguyên REST: loading -> ready | error, có `reload` (nút Thử lại) và tự tải lại khi:
 *  - `deps` đổi (ví dụ mã hũ khác): quay về loading;
 *  - có thao tác ghi thành công (số phiên bản dữ liệu đổi): giữ số cũ trong lúc tải (`refreshing`), lỗi thì hiện lỗi
 *    nhưng không xóa số cũ. `enabled = false` thì không gọi gì.
 * Kết quả cũ về muộn bị bỏ (chống đua).
 * `poll` (tùy chọn): sau mỗi lần tải xong, hỏi xem có cần tải lại sau một lúc không (ví dụ dự báo chưa kịp theo lần ghi,
 * hoặc `stale`). Có giới hạn thời gian cho mỗi đợt chờ; đợt chờ tính lại từ đầu khi `deps` đổi hoặc sau một lần ghi.
 */
export function useApiResource<T>(
  fetcher: (api: ApiClient) => Promise<T>,
  deps: readonly unknown[],
  enabled = true,
  poll?: (data: T) => PollPlan,
): Resource<T> {
  const api = useApi()
  const version = useDataVersion()
  const [state, setState] = useState<State<T>>({ status: 'loading', data: null, error: null, refreshing: false })
  const seq = useRef(0)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher
  const depsKey = JSON.stringify(deps)
  const lastDepsKey = useRef(depsKey)
  const pollRef = useRef(poll)
  pollRef.current = poll
  const pollSince = useRef<number | null>(null)

  const run = useCallback(
    async (keepData: boolean) => {
      const mine = ++seq.current
      setState((prev) =>
        keepData && prev.data !== null ? { status: 'ready', data: prev.data, error: null, refreshing: true } : { status: 'loading', data: null, error: null, refreshing: false },
      )
      try {
        const data = await fetcherRef.current(api)
        if (mine === seq.current) setState({ status: 'ready', data, error: null, refreshing: false })
      } catch (e) {
        if (mine !== seq.current) return
        const error = e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0)
        setState((prev) => ({ status: 'error', data: prev.data, error, refreshing: false }))
      }
    },
    [api],
  )

  useEffect(() => {
    if (!enabled) return
    const depsChanged = lastDepsKey.current !== depsKey
    lastDepsKey.current = depsKey
    pollSince.current = null
    void run(!depsChanged)
  }, [run, version, depsKey, enabled])

  // Hỏi lại định kỳ khi nơi dùng cho biết dữ liệu chưa theo kịp (xem `poll`).
  useEffect(() => {
    if (!enabled || state.status !== 'ready' || state.refreshing || state.data === null || !pollRef.current) return
    const plan = pollRef.current(state.data)
    if (!plan) {
      pollSince.current = null
      return
    }
    const now = Date.now()
    pollSince.current ??= now
    if (now - pollSince.current + plan.delayMs > plan.maxMs) return
    const timer = setTimeout(() => void run(true), plan.delayMs)
    return () => clearTimeout(timer)
  }, [state, enabled, run])

  const reload = useCallback(() => run(true), [run])
  return { ...state, reload } as Resource<T>
}
