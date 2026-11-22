import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { newUuid } from '@/lib/ids'
import type { ActionResponse, Payee } from '@/api/schemas'
import type { TransferSource } from './params'

// Trạng thái của luồng chuyển tiền T1 → T2 → T4 → T5. Chỉ là bản nháp trong bộ nhớ của phiên (không localStorage):
// tải lại trang thì bắt đầu lại từ T1. Số tiền giữ dạng chuỗi chữ số để bàn phím số thao tác đơn giản.

export type TransferState = {
  payee: Payee | null
  /** Chuỗi chữ số của số tiền (không dấu chấm). */
  amountDigits: string
  source: TransferSource | null
  /** Hũ tính chi tiêu khi trả bằng hạn mức (tùy chọn). */
  creditJar: string
  note: string
  /** Mã chống ghi trùng: một mã cho mỗi lần chuyển, đổi sau khi thành công. */
  clientRef: string
  /** Biên nhận của server sau khi ghi (T5). */
  receipt: ActionResponse | null
}

type Ctx = {
  state: TransferState
  patch: (p: Partial<TransferState>) => void
  reset: () => void
}

const fresh = (): TransferState => ({ payee: null, amountDigits: '', source: null, creditJar: '', note: '', clientRef: `ui-${newUuid()}`, receipt: null })

const TransferContext = createContext<Ctx | null>(null)

export function TransferFlowProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<TransferState>(fresh)
  const patch = useCallback((p: Partial<TransferState>) => setState((s) => ({ ...s, ...p })), [])
  const reset = useCallback(() => setState(fresh()), [])
  const value = useMemo(() => ({ state, patch, reset }), [state, patch, reset])
  return <TransferContext.Provider value={value}>{children}</TransferContext.Provider>
}

export function useTransferFlow(): Ctx {
  const c = useContext(TransferContext)
  if (!c) throw new Error('useTransferFlow phải nằm trong <TransferFlowProvider>')
  return c
}

export const amountOf = (s: TransferState): number => (s.amountDigits ? Number(s.amountDigits) : 0)
