import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { ApiClient } from './client'
import { ApiError } from './errors'
import type { JarsResponse } from './schemas'

const ApiContext = createContext<ApiClient | null>(null)

export function ApiProvider({ client, children }: { client: ApiClient; children: ReactNode }) {
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>
}

export function useApi(): ApiClient {
  const c = useContext(ApiContext)
  if (!c) throw new Error('useApi phải nằm trong <ApiProvider>')
  return c
}

// --- Số dư các hũ: một nguồn dùng chung cho Tổng quan, Hồ sơ (sau đặt lại) và khối confirm (sau ghi). ---

export type JarsState =
  | { status: 'loading'; data: null; error: null }
  | { status: 'ready'; data: JarsResponse; error: null; refreshing: boolean }
  | { status: 'error'; data: JarsResponse | null; error: ApiError }

export type JarsContextValue = { state: JarsState; reload: () => Promise<void> }

const JarsContext = createContext<JarsContextValue | null>(null)

export function JarsProvider({ children }: { children: ReactNode }) {
  const api = useApi()
  const [state, setState] = useState<JarsState>({ status: 'loading', data: null, error: null })
  const seq = useRef(0)

  const reload = useCallback(async () => {
    const mine = ++seq.current
    setState((prev) =>
      prev.data ? { status: 'ready', data: prev.data, error: null, refreshing: true } : { status: 'loading', data: null, error: null },
    )
    try {
      const data = await api.getJars()
      if (mine === seq.current) setState({ status: 'ready', data, error: null, refreshing: false })
    } catch (e) {
      if (mine !== seq.current) return
      const error = e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0)
      setState((prev) => ({ status: 'error', data: prev.data, error }))
    }
  }, [api])

  useEffect(() => {
    void reload()
  }, [reload])

  const value = useMemo(() => ({ state, reload }), [state, reload])
  return <JarsContext.Provider value={value}>{children}</JarsContext.Provider>
}

export function useJars(): JarsContextValue {
  const c = useContext(JarsContext)
  if (!c) throw new Error('useJars phải nằm trong <JarsProvider>')
  return c
}
