import { createContext, useContext, type ReactNode } from 'react'
import { useApiResource, type Resource } from './resource'
import type { OverviewResponse } from './schemas'

const OverviewContext = createContext<Resource<OverviewResponse> | null>(null)

/** Một lệnh GET /overview dùng chung cho Tổng quan, tab Hũ, Hoạt động, chuyển tiền... (tải lại sau mỗi lần ghi). */
export function OverviewProvider({ children }: { children: ReactNode }) {
  const res = useApiResource((api) => api.getOverview(), [])
  return <OverviewContext.Provider value={res}>{children}</OverviewContext.Provider>
}

export function useOverview(): Resource<OverviewResponse> {
  const c = useContext(OverviewContext)
  if (!c) throw new Error('useOverview phải nằm trong <OverviewProvider>')
  return c
}
