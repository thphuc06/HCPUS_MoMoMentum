import type { ToolParams, TxType } from '@/api/schemas'

/** Loại giao dịch "chuyển cho người khác" trong bảng tra tx_type_map (fixtures/rest/ConfirmationRequest.record_transaction_transfer). */
export const TRANSFER_TX_TYPE = 'transfer_person'

export type TransferSource = { kind: 'jar'; code: string } | { kind: 'credit' }

/**
 * Tham số `record_transaction` của một lần chuyển tiền cho người nhận. Màn hình chỉ gửi những gì người dùng đã chọn;
 * server chuẩn hóa (điền mặc định, kiểm hạn mức và số dư) và chỉ ký bản chuẩn hóa. Không có phí hay tổng ở đây: phí do
 * server tính khi ghi nghĩa vụ trả sau và trả về trong biên nhận.
 * `tx_type` chỉ gửi khi bảng tra của server có loại này (không gắn cứng danh sách).
 */
export function transferParams(args: {
  amountVnd: number
  source: TransferSource
  payeeId: string
  note: string
  clientRef: string
  txTypes: readonly TxType[]
  /** Hũ tính chi tiêu khi trả bằng hạn mức (tùy chọn; không chọn thì server tự xếp). */
  creditJar?: string
}): ToolParams {
  const note = args.note.trim()
  const p: ToolParams = {
    kind: 'expense',
    amount_vnd: args.amountVnd,
    funding: args.source.kind === 'jar' ? 'jar' : 'credit',
    payee_id: args.payeeId,
    client_ref: args.clientRef,
  }
  if (args.source.kind === 'jar') p.jar = args.source.code
  else if (args.creditJar) p.jar = args.creditJar
  if (note) p.note = note
  if (args.txTypes.some((t) => t.tx_type === TRANSFER_TX_TYPE && t.direction === 'out')) p.tx_type = TRANSFER_TX_TYPE
  return p
}
