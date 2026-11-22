import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import type { ApiClient } from './client'

const ApiContext = createContext<ApiClient | null>(null)

/** Cửa sổ chờ dự báo mới sau một lần ghi: pipeline sự kiện thường xong trong 3 đến 4 giây; chờ tối đa 60 giây rồi thôi. */
export const FORECAST_FOLLOW_UP_MS = 60_000

/**
 * "Phiên bản dữ liệu": tăng sau mỗi thao tác ghi thành công. Mọi tài nguyên đang hiện (tổng quan, hũ, dự báo, giao dịch,
 * nghĩa vụ...) nghe số này và tải lại, nên không màn nào hiện số cũ sau khi ghi (xem useApiResource).
 *
 * Số dư đổi ngay khi ghi, còn dự báo mới do pipeline sự kiện tính sau khoảng 3 đến 4 giây. Để màn hình biết dự báo đang
 * hiện đã kịp theo lần ghi chưa, `bump` nhận thời điểm SERVER của lần ghi (`as_of` của biên nhận) và `useForecastFollowUp`
 * so nó với `computed_at` của dự báo (cùng đồng hồ server, không phụ thuộc đồng hồ máy người dùng).
 */
type LastWrite = { serverAt: number; clientAt: number }
type DataVersion = { version: number; bump: (serverAt?: string) => void; lastWrite: LastWrite | null }
const DataVersionContext = createContext<DataVersion>({ version: 0, bump: () => {}, lastWrite: null })

export function ApiProvider({ client, children }: { client: ApiClient; children: ReactNode }) {
  const [state, setState] = useState<{ version: number; lastWrite: LastWrite | null }>({ version: 0, lastWrite: null })
  const bump = useCallback((serverAt?: string) => {
    const t = serverAt ? Date.parse(serverAt) : Number.NaN
    setState((s) => ({
      version: s.version + 1,
      // Không có thời điểm server (đặt lại demo, làm mới sau lỗi): không chờ dự báo, vì không có mốc để so.
      lastWrite: Number.isFinite(t) ? { serverAt: t, clientAt: Date.now() } : s.lastWrite,
    }))
  }, [])
  const dv = useMemo(() => ({ version: state.version, bump, lastWrite: state.lastWrite }), [state, bump])
  return (
    <ApiContext.Provider value={client}>
      <DataVersionContext.Provider value={dv}>{children}</DataVersionContext.Provider>
    </ApiContext.Provider>
  )
}

/** Số phiên bản dữ liệu hiện tại (đổi sau mỗi lần ghi). */
export function useDataVersion(): number {
  return useContext(DataVersionContext).version
}

/** Gọi sau khi một thao tác ghi thành công: làm mới mọi dữ liệu liên quan. Truyền `as_of` của biên nhận nếu có. */
export function useRefreshAfterWrite(): (serverAt?: string) => void {
  return useContext(DataVersionContext).bump
}

/**
 * Dự báo có đang chậm hơn lần ghi gần nhất không? `computedAt` là `computed_at` của dự báo đang hiện (null: chưa có dự báo).
 * Đúng khi lần ghi cách đây chưa quá 60 giây và dự báo được tính trước lúc ghi.
 */
export function useForecastFollowUp(): (computedAt: string | null | undefined) => boolean {
  const { lastWrite } = useContext(DataVersionContext)
  return useCallback(
    (computedAt) => {
      if (!lastWrite || Date.now() - lastWrite.clientAt > FORECAST_FOLLOW_UP_MS) return false
      if (!computedAt) return true
      const t = Date.parse(computedAt)
      return !Number.isFinite(t) || t < lastWrite.serverAt
    },
    [lastWrite],
  )
}

export function useApi(): ApiClient {
  const c = useContext(ApiContext)
  if (!c) throw new Error('useApi phải nằm trong <ApiProvider>')
  return c
}
