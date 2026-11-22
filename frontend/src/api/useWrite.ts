import { useCallback, useRef, useState } from 'react'
import { useApi, useRefreshAfterWrite } from './ApiProvider'
import { ApiError, type ErrorCode } from './errors'
import type { ActionResponse, ToolName, ToolParams } from './schemas'

export type WritePhase = 'idle' | 'working' | 'done' | 'blocked'

/** Lỗi mà bấm lại cũng vô ích (số dư đổi, đã ghi rồi, vượt hạn mức...): khóa nút, người dùng sửa dữ liệu hoặc quay lại. */
const BLOCKING: ReadonlySet<string> = new Set<ErrorCode>([
  'TOKEN_REUSED',
  'ALREADY_APPLIED',
  'DUPLICATE_TRANSACTION',
  'PARAMS_MISMATCH',
  'INSUFFICIENT_FUNDS',
  'AMOUNT_LIMIT_EXCEEDED',
  'CREDIT_LIMIT_EXCEEDED',
  'JAR_NOT_FOUND',
  'JAR_PROTECTED',
  'PAYEE_NOT_FOUND',
  'OBLIGATION_NOT_FOUND',
  'SALARY_EVENT_NOT_FOUND',
  'PARAMS_INVALID',
])

/**
 * Luồng ghi của MÀN HÌNH (không có khối `confirm`): người dùng đã bấm nút xác nhận có nêu rõ việc sẽ làm, rồi
 * POST /confirmations (tool + params tự dựng) -> POST /actions với token và `params` đã được server chuẩn hóa
 * (đúng thứ token đã ký) -> làm mới mọi dữ liệu. LLM không nằm trên đường ghi (ADR-0002). Không gửi
 * `conversation_id`/`confirm_block_id` (hợp đồng: màn hình không có khối). Mỗi `submit` chạy một lần tại một thời điểm.
 */
export function useWriteFlow() {
  const api = useApi()
  const refresh = useRefreshAfterWrite()
  const [phase, setPhase] = useState<WritePhase>('idle')
  const [error, setError] = useState<ApiError | null>(null)
  const [receipt, setReceipt] = useState<ActionResponse | null>(null)
  const busy = useRef(false)

  const submit = useCallback(
    async (tool: ToolName, params: ToolParams): Promise<ActionResponse | null> => {
      if (busy.current) return null
      busy.current = true
      setPhase('working')
      setError(null)
      try {
        const issued = await api.createConfirmation({ tool, params })
        const res = await api.applyAction({ tool: issued.tool, params: issued.params, confirm_token: issued.confirm_token })
        setReceipt(res)
        setPhase('done')
        refresh()
        return res
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0)
        setError(err)
        setPhase(BLOCKING.has(err.code) ? 'blocked' : 'idle')
        // Token đã dùng hoặc đã áp dụng: thao tác có thể đã ghi, tải lại số liệu cho người dùng thấy sự thật.
        if (err.code === 'TOKEN_REUSED' || err.code === 'ALREADY_APPLIED' || err.code === 'DUPLICATE_TRANSACTION') refresh()
        return null
      } finally {
        busy.current = false
      }
    },
    [api, refresh],
  )

  const reset = useCallback(() => {
    setPhase('idle')
    setError(null)
    setReceipt(null)
  }, [])

  return { phase, error, receipt, submit, reset, working: phase === 'working' }
}
