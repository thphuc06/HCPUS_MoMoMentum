import { useCallback, useRef, useState } from 'react'
import { useApi, useJars } from '@/api/ApiProvider'
import { ApiError, type ErrorCode } from '@/api/errors'
import { useChatActions } from '@/chat/actions'
import { receiptNote } from '@/chat/receiptNote'
import type { ConfirmBlock } from '@/contracts/blocks'

export { receiptNote }

export type ConfirmPhase = 'idle' | 'working' | 'done' | 'blocked'

/** Lỗi mà bấm lại cũng vô ích (số dư đổi, đã ghi rồi, tham số lệch): khóa nút, người dùng bấm "Không" hoặc hỏi lại. */
const BLOCKING: ReadonlySet<string> = new Set<ErrorCode>([
  'TOKEN_REUSED',
  'ALREADY_APPLIED',
  'PARAMS_MISMATCH',
  'INSUFFICIENT_FUNDS',
  'AMOUNT_LIMIT_EXCEEDED',
  'JAR_NOT_FOUND',
])

/**
 * Luồng bấm xác nhận (ADR-0002): POST /confirmations (tool + params lấy nguyên từ khối) -> POST /actions kèm token
 * -> thay khối confirm bằng khối receipt -> làm mới số dư -> báo agent bằng một dòng hệ thống ở lượt sau.
 * LLM không nằm trên đường ghi.
 *
 * Cả hai lời gọi kèm `conversation_id` + `confirm_block_id` (id của khối confirm): server chỉ cho một đề nghị được
 * thực hiện MỘT lần và lưu biên nhận gắn với nó. Gặp ALREADY_APPLIED (đã thực hiện ở đâu đó, ví dụ tab khác hoặc
 * trước khi tải lại trang) thì khóa nút và đồng bộ lại trạng thái từ server để khối đổi thành biên nhận.
 */
export function useConfirmFlow({ block, blockId }: { block: ConfirmBlock; blockId: string }) {
  const api = useApi()
  const jars = useJars()
  const actions = useChatActions()
  const [phase, setPhase] = useState<ConfirmPhase>('idle')
  const [error, setError] = useState<ApiError | null>(null)
  const busy = useRef(false)

  const confirm = useCallback(async () => {
    if (busy.current) return
    busy.current = true
    setPhase('working')
    setError(null)
    const { tool, params, params_hash } = block.data
    const ref = { conversation_id: actions.getConversationId(), confirm_block_id: block.id }
    try {
      const issued = await api.createConfirmation({ tool, params, params_hash, ...ref })
      const receipt = await api.applyAction({ tool: issued.tool, params: issued.params, confirm_token: issued.confirm_token, ...ref })
      actions.replaceBlock(blockId, receipt, receipt.id)
      actions.addSystemNote(receiptNote(receipt), receipt.id)
      setPhase('done')
      void jars.reload()
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0)
      setError(err)
      setPhase(BLOCKING.has(err.code) ? 'blocked' : 'idle')
      // Token đã dùng hoặc đề nghị đã thực hiện nghĩa là thao tác đã ghi: tải lại số dư và trạng thái đề nghị
      // từ server để người dùng thấy sự thật (khối confirm đổi thành biên nhận).
      if (err.code === 'TOKEN_REUSED' || err.code === 'ALREADY_APPLIED') {
        void jars.reload()
        void actions.reloadConversation()
      }
    } finally {
      busy.current = false
    }
  }, [api, actions, block, blockId, jars])

  const cancel = useCallback(() => {
    if (busy.current) return
    actions.markBlock(blockId, 'cancelled')
  }, [actions, blockId])

  return { phase, error, confirm, cancel }
}
