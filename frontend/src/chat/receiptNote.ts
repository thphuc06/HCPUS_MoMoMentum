import { formatVnd } from '@/lib/format'
import type { ReceiptActionBlock, ReceiptBlock } from '@/contracts/blocks'

const HEAD = 'Hệ thống ghi nhận: người dùng đã xác nhận trên giao diện và thao tác đã được thực hiện.'

function body(r: ReceiptBlock | ReceiptActionBlock): string {
  if (r.type === 'receipt') {
    const d = r.data
    return (
      `${d.summary}. ` +
      `Số dư sau: ${d.from_jar.name} ${formatVnd(d.from_jar.balance_after_vnd)}, ${d.to_jar.name} ${formatVnd(d.to_jar.balance_after_vnd)}. ` +
      `Mã giao dịch ${d.transaction_id}.`
    )
  }
  const d = r.data
  const after = d.jars_after.length > 0 ? ` Số dư sau: ${d.jars_after.map((j) => `${j.name} ${formatVnd(j.balance_after_vnd)}`).join(', ')}.` : ''
  const ref = d.reference_id ? ` Mã tham chiếu ${d.reference_id}.` : ''
  return `${d.summary}.${after}${ref}`
}

/**
 * Dòng hệ thống cho agent biết việc đã làm; số liệu lấy từ biên nhận của server.
 * Dùng cả lúc bấm xác nhận (useConfirmFlow) lẫn lúc dựng lại hội thoại từ server (session.hydrate),
 * để agent không nói "chưa có khoản nào được chuyển" sau khi tải lại trang.
 * Nhận cả `receipt` (chuyển hũ) và `receipt_action` (mọi thao tác ghi khác).
 */
export function receiptNote(r: ReceiptBlock | ReceiptActionBlock): string {
  return `${HEAD} ${body(r)}`
}

/** Dòng hệ thống khi người dùng bấm Hoàn tác: nói rõ thao tác trước đã bị đảo ngược để agent không coi nó còn hiệu lực. */
export function undoNote(original: ReceiptBlock | ReceiptActionBlock, undone: ReceiptBlock | ReceiptActionBlock): string {
  return `Hệ thống ghi nhận: người dùng đã bấm Hoàn tác trên giao diện, nên thao tác "${original.data.summary}" không còn hiệu lực. Thao tác ngược đã được thực hiện: ${body(undone)}`
}
