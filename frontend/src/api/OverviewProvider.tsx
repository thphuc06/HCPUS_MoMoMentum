import { createContext, useContext, type ReactNode } from 'react'
import { FORECAST_FOLLOW_UP_MS, useForecastFollowUp } from './ApiProvider'
import { useApiResource, type Resource } from './resource'
import type { OverviewResponse } from './schemas'

const OverviewContext = createContext<Resource<OverviewResponse> | null>(null)

/** Một lệnh GET /overview dùng chung cho Tổng quan, tab Hũ, Hoạt động, chuyển tiền... (tải lại sau mỗi lần ghi). */
export function OverviewProvider({ children }: { children: ReactNode }) {
  const forecastPending = useForecastFollowUp()
  // Hỏi lại tự động (có giới hạn) khi dự báo chưa theo kịp: sau một lần ghi (dự báo mới có sau 3 đến 4 giây), khi Tổng quan
  // báo `forecast.stale` (server đã kích hoạt tính lại nền), hoặc khi đã khai hồ sơ mà chưa có dự báo nào.
  const res = useApiResource(
    (api) => api.getOverview(),
    [],
    true,
    (d) => {
      if (forecastPending(d.forecast?.computed_at)) return { delayMs: 3_000, maxMs: FORECAST_FOLLOW_UP_MS }
      if (d.forecast?.stale || (d.forecast === null && d.profile.onboarded)) return { delayMs: 4_000, maxMs: 20_000 }
      return null
    },
  )
  return <OverviewContext.Provider value={res}>{children}</OverviewContext.Provider>
}

export function useOverview(): Resource<OverviewResponse> {
  const c = useContext(OverviewContext)
  if (!c) throw new Error('useOverview phải nằm trong <OverviewProvider>')
  return c
}
