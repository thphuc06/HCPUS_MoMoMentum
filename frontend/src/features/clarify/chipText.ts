import { formatVnd, formatVndShort } from '@/lib/format'

const RAW_AMOUNT = /^\s*\d{4,}\s*$/

/** Đọc lại số tiền từ chữ dạng `formatVndShort` ("250 nghìn", "1,2 triệu") để biết chữ gọn có giữ đúng số không. */
function parseShort(text: string): number | null {
  const m = /^(\d+(?:[.,]\d+)?)\s*(nghìn|triệu|tỷ)$/.exec(text.trim())
  if (!m) return null
  const unit = m[2] === 'tỷ' ? 1e9 : m[2] === 'triệu' ? 1e6 : 1e3
  return Math.round(Number(m[1]!.replace(/\./g, '').replace(',', '.')) * unit)
}

/**
 * Chữ người đọc được cho chip số tiền của khối `clarify`: "250000" -> "250 nghìn"; số làm tròn gọn bị đổi giá trị thì dùng dạng đầy đủ
 * ("1250000" -> "1.250.000 ₫"). Chữ khác (đã là "1 triệu", "Hũ Hóa đơn"...) giữ nguyên. Chip gửi chữ này như người dùng gõ; router
 * (phần đọc số tiền bằng mã) hiểu cả hai dạng.
 */
export function readableChipText(text: string, slot: string): string {
  if (slot !== 'amount' || !RAW_AMOUNT.test(text)) return text
  const n = Number(text.trim())
  const short = formatVndShort(n)
  return parseShort(short) === n ? short : formatVnd(n)
}
