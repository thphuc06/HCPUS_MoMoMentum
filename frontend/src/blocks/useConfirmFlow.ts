import { useCallback, useRef, useState } from 'react'
import { useApi, useJars } from '@/api/ApiProvider'
import { ApiError, type ErrorCode } from '@/api/errors'
import { useChatActions } from '@/chat/actions'
import { formatVnd } from '@/lib/format'
import type { ConfirmBlock, ReceiptBlock } from '@/contracts/blocks'

export type ConfirmPhase = 'idle' | 'working' | 'done' | 'blocked'

/** Lỗi mà bấm lại cũng vô ích (số dư đổi, đã ghi rồi, tham số lệch): khóa nút, người dùng bấm "Không" hoặc hỏi lại. */
const BLOCKING: ReadonlySet<string> = new Set<ErrorCode>([
  'TOKEN_REUSED',
  'PARAMS_MISMATCH',
  'INSUFFICIENT_FUNDS',
  'AMOUNT_LIMIT_EXCEEDED',
  'JAR_NOT_FOUND',
])

/** Dòng hệ thống cho agent biết việc đã làm; số liệu lấy từ biên nhận của server. */
export function receiptNote(r: ReceiptBlock): string {
  const d = r.data
  return (
    `Hệ thống ghi nhận: người dùng đã xác nhận trên giao diện và thao tác đã được thực hiện. ${d.summary}. ` +
    `Số dư sau: ${d.from_jar.name} ${formatVnd(d.from_jar.balance_after_vnd)}, ${d.to_jar.name} ${formatVnd(d.to_jar.balance_after_vnd)}. ` +
    `Mã giao dịch ${d.transaction_id}.`
  )
}

/**
 * Luồng bấm xác nhận (ADR-0002): POST /confirmations (tool + params lấy nguyên từ khối) -> POST /actions kèm token
 * -> thay khối confirm bằng khối receipt -> làm mới số dư -> báo agent bằng một dòng hệ thống ở lượt sau.
 * LLM không nằm trên đường ghi.
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
    try {
      const issued = await api.createConfirmation({ tool, params, params_hash })
      const receipt = await api.applyAction({ tool: issued.tool, params: issued.params, confirm_token: issued.confirm_token })
      actions.replaceBlock(blockId, receipt, receipt.id)
      actions.addSystemNote(receiptNote(receipt))
      setPhase('done')
      void jars.reload()
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0)
      setError(err)
      setPhase(BLOCKING.has(err.code) ? 'blocked' : 'idle')
      // Token đã dùng nghĩa là thao tác nhiều khả năng đã ghi: tải lại số dư để người dùng thấy sự thật.
      if (err.code === 'TOKEN_REUSED') void jars.reload()
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
