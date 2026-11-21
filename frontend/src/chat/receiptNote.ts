import { formatVnd } from '@/lib/format'
import type { ReceiptBlock } from '@/contracts/blocks'

/**
 * Dòng hệ thống cho agent biết việc đã làm; số liệu lấy từ biên nhận của server.
 * Dùng cả lúc bấm xác nhận (useConfirmFlow) lẫn lúc dựng lại hội thoại từ server (session.hydrate),
 * để agent không nói "chưa có khoản nào được chuyển" sau khi tải lại trang.
 */
export function receiptNote(r: ReceiptBlock): string {
  const d = r.data
  return (
    `Hệ thống ghi nhận: người dùng đã xác nhận trên giao diện và thao tác đã được thực hiện. ${d.summary}. ` +
    `Số dư sau: ${d.from_jar.name} ${formatVnd(d.from_jar.balance_after_vnd)}, ${d.to_jar.name} ${formatVnd(d.to_jar.balance_after_vnd)}. ` +
    `Mã giao dịch ${d.transaction_id}.`
  )
}
