import { useCallback, useEffect, useRef, useState } from 'react'
import { useApi, useDataVersion } from './ApiProvider'
import type { ApiClient } from './client'
import { ApiError } from './errors'

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
 */
export function useApiResource<T>(fetcher: (api: ApiClient) => Promise<T>, deps: readonly unknown[], enabled = true): Resource<T> {
  const api = useApi()
  const version = useDataVersion()
  const [state, setState] = useState<State<T>>({ status: 'loading', data: null, error: null, refreshing: false })
  const seq = useRef(0)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher
  const depsKey = JSON.stringify(deps)
  const lastDepsKey = useRef(depsKey)

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
    void run(!depsChanged)
  }, [run, version, depsKey, enabled])

  const reload = useCallback(() => run(true), [run])
  return { ...state, reload } as Resource<T>
}
