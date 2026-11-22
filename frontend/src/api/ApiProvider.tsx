import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import type { ApiClient } from './client'

const ApiContext = createContext<ApiClient | null>(null)

/**
 * "Phiên bản dữ liệu": tăng sau mỗi thao tác ghi thành công. Mọi tài nguyên đang hiện (tổng quan, hũ, dự báo, giao dịch,
 * nghĩa vụ...) nghe số này và tải lại, nên không màn nào hiện số cũ sau khi ghi (xem useApiResource).
 */
type DataVersion = { version: number; bump: () => void }
const DataVersionContext = createContext<DataVersion>({ version: 0, bump: () => {} })

export function ApiProvider({ client, children }: { client: ApiClient; children: ReactNode }) {
  const [version, setVersion] = useState(0)
  const bump = useCallback(() => setVersion((v) => v + 1), [])
  const dv = useMemo(() => ({ version, bump }), [version, bump])
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

/** Gọi sau khi một thao tác ghi thành công: làm mới mọi dữ liệu liên quan. */
export function useRefreshAfterWrite(): () => void {
  return useContext(DataVersionContext).bump
}

export function useApi(): ApiClient {
  const c = useContext(ApiContext)
  if (!c) throw new Error('useApi phải nằm trong <ApiProvider>')
  return c
}
