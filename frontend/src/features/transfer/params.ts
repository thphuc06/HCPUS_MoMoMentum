import type { ToolParams, TxType } from '@/api/schemas'

export type TransferSource = { kind: 'jar'; code: string } | { kind: 'credit' }

/**
 * Hũ người dùng chọn được làm hũ trả khoản Trả sau, khi ví KHÔNG có hũ loại nghĩa vụ (server khi đó không có hũ trả mặc định
 * và trả PARAMS_INVALID nếu thiếu `pay_jar`). Ví có hũ nghĩa vụ thì trả mảng rỗng: không hỏi, server tự chọn như trước.
 * Không gồm hũ hệ thống.
 */
export function payJarChoices<J extends { kind: string }>(jars: readonly J[]): J[] {
  if (jars.some((j) => j.kind === 'obligation')) return []
  return jars.filter((j) => j.kind !== 'system')
}

/**
 * Tham số `record_transaction` của một lần chuyển tiền cho người nhận. Màn hình chỉ gửi những gì người dùng đã chọn;
 * server chuẩn hóa (điền mặc định, kiểm hạn mức và số dư) và chỉ ký bản chuẩn hóa. Không có phí hay tổng ở đây: phí do
 * server tính khi ghi nghĩa vụ trả sau và trả về trong biên nhận.
 * `tx_type` là loại chi mà server đánh dấu `is_person_transfer` trong GET /tx-types (không gắn cứng mã); bảng tra chưa có
 * loại như vậy thì bỏ trống để server tự suy.
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
  /** Hũ trả khoản Trả sau khi đến hạn; chỉ gửi khi ví không có hũ nghĩa vụ (xem `payJarChoices`). */
  payJar?: string
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
  else {
    if (args.creditJar) p.jar = args.creditJar
    if (args.payJar) p.pay_jar = args.payJar
  }
  if (note) p.note = note
  const person = args.txTypes.find((t) => t.is_person_transfer === true && t.direction === 'out')
  if (person) p.tx_type = person.tx_type
  return p
}
