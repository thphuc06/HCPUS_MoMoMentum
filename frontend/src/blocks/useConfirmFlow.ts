import { useCallback, useRef, useState } from 'react'
import { useApi, useRefreshAfterWrite } from '@/api/ApiProvider'
import { ApiError, type ErrorCode } from '@/api/errors'
import { useChatActions } from '@/chat/actions'
import { receiptNote } from '@/chat/receiptNote'
import type { ConfirmActionBlock, ConfirmBlock } from '@/contracts/blocks'

export { receiptNote }

export type ConfirmPhase = 'idle' | 'working' | 'done' | 'blocked'

/** Mã lỗi khi xin token cho đề nghị đã quá hạn (server ép hạn của đề nghị, không chỉ giao diện). */
const OFFER_EXPIRED = 'TOKEN_EXPIRED'

/** Lỗi mà bấm lại cũng vô ích (số dư đổi, đã ghi rồi, tham số lệch): khóa nút, người dùng bấm "Không" hoặc hỏi lại. */
const BLOCKING: ReadonlySet<string> = new Set<ErrorCode>([
  'TOKEN_REUSED',
  'ALREADY_APPLIED',
  'PARAMS_MISMATCH',
  'INSUFFICIENT_FUNDS',
  'AMOUNT_LIMIT_EXCEEDED',
  'JAR_NOT_FOUND',
  'CREDIT_LIMIT_EXCEEDED',
  'DUPLICATE_TRANSACTION',
  'JAR_PROTECTED',
  'PAYEE_NOT_FOUND',
  'OBLIGATION_NOT_FOUND',
  'SALARY_EVENT_NOT_FOUND',
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
export function useConfirmFlow({ block, blockId }: { block: ConfirmBlock | ConfirmActionBlock; blockId: string }) {
  const api = useApi()
  const refresh = useRefreshAfterWrite()
  const actions = useChatActions()
  const [phase, setPhase] = useState<ConfirmPhase>('idle')
  const [error, setError] = useState<ApiError | null>(null)
  const [offerExpired, setOfferExpired] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const busy = useRef(false)

  const confirm = useCallback(async () => {
    if (busy.current) return
    busy.current = true
    setPhase('working')
    setError(null)
    const { tool, params, params_hash } = block.data
    const ref = { conversation_id: actions.getConversationId(), confirm_block_id: block.id }
    let stage: 'issue' | 'apply' = 'issue'
    try {
      const issued = await api.createConfirmation({ tool, params, params_hash, ...ref })
      stage = 'apply'
      const receipt = await api.applyAction({ tool: issued.tool, params: issued.params, confirm_token: issued.confirm_token, ...ref })
      actions.replaceBlock(blockId, receipt, receipt.id)
      actions.addSystemNote(receiptNote(receipt), receipt.id)
      setPhase('done')
      refresh() // làm mới mọi dữ liệu đang hiện (tổng quan, hũ, dự báo, giao dịch...)
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0)
      // Xin token mà bị TOKEN_EXPIRED: là ĐỀ NGHỊ quá hạn (không phải token), bấm lại vô ích: hiện như hết hạn, hỏi lại Yofina.
      if (stage === 'issue' && err.code === OFFER_EXPIRED) {
        setOfferExpired(true)
        setPhase('blocked')
        return
      }
      setError(err)
      setPhase(BLOCKING.has(err.code) ? 'blocked' : 'idle')
      // Token đã dùng hoặc đề nghị đã thực hiện nghĩa là thao tác đã ghi: tải lại số dư và trạng thái đề nghị
      // từ server để người dùng thấy sự thật (khối confirm đổi thành biên nhận).
      if (err.code === 'TOKEN_REUSED' || err.code === 'ALREADY_APPLIED') {
        refresh()
        void actions.reloadConversation()
      }
    } finally {
      busy.current = false
    }
  }, [api, actions, block, blockId, refresh])

  /**
   * "Không": ghi việc hủy ở server (POST /confirmations/cancel) rồi đánh dấu khối. Hủy là hành động an toàn nên nếu server
   * chưa trả lời được vẫn đánh dấu tại chỗ (không có gì được ghi). Gặp ALREADY_APPLIED nghĩa là đề nghị đã thực hiện ở
   * nơi khác: đồng bộ lại từ server để khối đổi thành biên nhận thay vì "đã hủy".
   */
  const cancel = useCallback(async () => {
    if (busy.current) return
    busy.current = true
    setCancelling(true)
    try {
      await api.cancelConfirmation({ conversation_id: actions.getConversationId(), confirm_block_id: block.id })
      actions.markBlock(blockId, 'cancelled')
    } catch (e) {
      if (e instanceof ApiError && (e.code === 'ALREADY_APPLIED' || e.code === 'TOKEN_REUSED')) {
        setError(e)
        refresh()
        void actions.reloadConversation()
      } else {
        actions.markBlock(blockId, 'cancelled')
      }
    } finally {
      busy.current = false
      setCancelling(false)
    }
  }, [api, actions, block.id, blockId, refresh])

  return { phase, error, confirm, cancel, cancelling, offerExpired }
}
