import { createContext, useContext } from 'react'

/**
 * Mở bảng "Vì sao" cho một lượt trả lời của agent (cung cấp bởi ChatSheet). Ngoài chat không có provider: khối nào cần
 * nút "Vì sao" thì hỏi `useExplain()` và ẩn nút khi trả `null` (màn hình không có bản ghi lượt agent để giải thích).
 */
export type ExplainLauncher = { open: (traceId: string) => void }

export const ExplainContext = createContext<ExplainLauncher | null>(null)

export function useExplain(): ExplainLauncher | null {
  return useContext(ExplainContext)
}
