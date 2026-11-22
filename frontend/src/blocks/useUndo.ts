import { useCallback, useRef, useState } from 'react'
import { useApi, useRefreshAfterWrite } from '@/api/ApiProvider'
import { ApiError } from '@/api/errors'
import type { ToolName, ToolParams } from '@/api/schemas'
import { useOptionalChatActions } from '@/chat/actions'
import { undoNote } from '@/chat/receiptNote'
import type { ReceiptActionBlock, ReceiptBlock } from '@/contracts/blocks'
import { useNow } from './useNow'

/**
 * Thao tác ngược của một biên nhận, đi qua CÙNG luồng token như mọi thao tác ghi (POST /confirmations rồi POST /actions):
 * - chuyển hũ: chuyển ngược cùng số tiền (hũ đích về hũ nguồn);
 * - lời nhắc (`schedule_nudge`): `op` `cancel` với `nudge_id` = `reference_id` của biên nhận (hợp đồng phase 3).
 * Thao tác khác (ghi giao dịch, cập nhật hồ sơ...) không có thao tác ngược hợp đồng quy định nên không có Hoàn tác.
 */
export function undoRequestFor(r: ReceiptBlock | ReceiptActionBlock): { tool: ToolName; params: ToolParams } | null {
  if (r.type === 'receipt') {
    const d = r.data
    return { tool: 'move_between_jars', params: { from_jar: d.to_jar.code, to_jar: d.from_jar.code, amount_vnd: d.amount_vnd } }
  }
  if (r.data.tool === 'schedule_nudge' && r.data.reference_id) return { tool: 'schedule_nudge', params: { op: 'cancel', nudge_id: r.data.reference_id } }
  return null
}

export type UndoState = {
  /** Có nút Hoàn tác (còn trong cửa sổ, chưa đang làm). */
  available: boolean
  /** Mili giây còn lại của cửa sổ; 0 khi hết. */
  remainingMs: number
  working: boolean
  error: ApiError | null
  undo: () => Promise<void>
}

/**
 * Hoàn tác có đếm ngược (H6b). Cửa sổ tính từ `doneAt` (lúc đề nghị vừa thực hiện trong phiên này) với độ dài lấy từ cấu hình
 * (`undoWindowMs`). Biên nhận dựng lại từ server sau khi tải trang không có `doneAt` nên không có Hoàn tác. Xong thì biên
 * nhận được thay bằng biên nhận của thao tác ngược (không còn Hoàn tác tiếp) và agent được báo bằng một dòng hệ thống.
 */
export function useUndo(receipt: ReceiptBlock | ReceiptActionBlock, blockId: string, doneAt: number | undefined): UndoState {
  const api = useApi()
  const refresh = useRefreshAfterWrite()
  const actions = useOptionalChatActions()
  const req = undoRequestFor(receipt)
  const windowMs = actions?.undoWindowMs ?? 0
  const eligible = actions !== null && doneAt !== undefined && req !== null
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const now = useNow(1000, eligible && !working)
  const remainingMs = eligible ? Math.max(0, doneAt + windowMs - now) : 0
  const busy = useRef(false)

  const undo = useCallback(async () => {
    if (!actions || !req || busy.current) return
    busy.current = true
    setWorking(true)
    setError(null)
    try {
      const issued = await api.createConfirmation({ tool: req.tool, params: req.params })
      const res = await api.applyAction({ tool: issued.tool, params: issued.params, confirm_token: issued.confirm_token })
      actions.replaceBlock(blockId, res, res.id, { undone: true })
      actions.addSystemNote(undoNote(receipt, res), res.id)
      refresh(res.source.as_of)
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0))
      setWorking(false)
    } finally {
      busy.current = false
    }
  }, [api, actions, req, blockId, receipt, refresh])

  return { available: eligible && remainingMs > 0 && !working, remainingMs, working, error, undo }
}
