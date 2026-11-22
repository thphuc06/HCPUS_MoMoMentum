// Định dạng tiền và ngày theo figma-ui-design.md §3, dựa vào Intl (không gắn cứng số).
// Quy ước hợp đồng: tiền là số nguyên VND (contracts/README.md). Thẻ: "1.200.000 ₫"; câu hỏi và lời giải thích: "1,2 triệu".

const NBSP = ' '
const MINUS = '−'
const LOCALE = 'vi-VN'

const integerFmt = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0, useGrouping: true })
const oneDecimalFmt = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1, useGrouping: true })

function sign(n: number): string {
  return Math.round(n) < 0 ? MINUS : ''
}

/** 1200000 -> "1.200.000 ₫" (NBSP trước ₫); số âm dùng dấu trừ Unicode. */
export function formatVnd(n: number): string {
  return `${sign(n)}${integerFmt.format(Math.abs(Math.round(n)))}${NBSP}₫`
}

/** Chỉ phần số có chấm nhóm nghìn, không có ký hiệu tiền. */
export function formatVndNumber(n: number): string {
  return `${sign(n)}${integerFmt.format(Math.abs(Math.round(n)))}`
}

/** 1200000 -> "1,2 triệu"; 950000 -> "950 nghìn"; 1500000000 -> "1,5 tỷ"; dưới 1.000 giữ nguyên số. */
export function formatVndShort(n: number): string {
  const a = Math.abs(n)
  const s = sign(n)
  if (a >= 1e9) return `${s}${oneDecimalFmt.format(a / 1e9)} tỷ`
  if (a >= 1e6) return `${s}${oneDecimalFmt.format(a / 1e6)} triệu`
  if (a >= 1e3) return `${s}${integerFmt.format(Math.round(a / 1e3))} nghìn`
  return `${s}${integerFmt.format(Math.round(a))}`
}

const TZ = 'Asia/Ho_Chi_Minh'

/** "2026-11-21" (ngày mô phỏng) -> "21/11/2026". Không đi qua múi giờ để khỏi lệch ngày. */
export function formatAppDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!m) return iso
  return `${m[3]}/${m[2]}/${m[1]}`
}

const dateTimeFmt = new Intl.DateTimeFormat(LOCALE, {
  timeZone: TZ,
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

/** Thời điểm thật (RFC 3339) -> "21/11 09:14" theo giờ Việt Nam. */
export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = Object.fromEntries(dateTimeFmt.formatToParts(d).map((x) => [x.type, x.value]))
  return `${p.day}/${p.month} ${p.hour}:${p.minute}`
}

/** Đếm ngược mm:ss từ số mili giây còn lại (không âm). */
export function formatCountdown(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000))
  const mm = String(Math.floor(total / 60)).padStart(2, '0')
  const ss = String(total % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

/**
 * Lời chào theo giờ (0 đến 23). Khuya (0 đến 4 giờ) vẫn là "buổi tối": chưa ai chào "buổi sáng" lúc 1 giờ đêm.
 */
export function greetingForHour(hour: number): string {
  if (hour < 5) return 'Chào buổi tối'
  if (hour < 11) return 'Chào buổi sáng'
  if (hour < 14) return 'Chào buổi trưa'
  if (hour < 18) return 'Chào buổi chiều'
  return 'Chào buổi tối'
}

/** Lời chào theo giờ của thiết bị người dùng (không theo múi giờ cố định). */
export function greetingNow(now: Date = new Date()): string {
  return greetingForHour(now.getHours())
}

export { formatDayMonth } from './dates'

/** Nhãn trục tiền gọn: 1500000 -> "1,5tr", -500000 -> "−500k", 0 -> "0". */
export function formatVndAxis(n: number): string {
  if (Math.round(n) === 0) return '0'
  const a = Math.abs(n)
  const s = sign(n)
  if (a >= 1e9) return `${s}${oneDecimalFmt.format(a / 1e9)}tỷ`
  if (a >= 1e6) return `${s}${oneDecimalFmt.format(a / 1e6)}tr`
  if (a >= 1e3) return `${s}${integerFmt.format(Math.round(a / 1e3))}k`
  return `${s}${integerFmt.format(Math.round(a))}`
}

/** Tiền có dấu rõ ràng cho danh sách giao dịch: "−65.000 ₫" hoặc "+9.000.000 ₫". */
export function formatSignedVnd(n: number): string {
  return `${n > 0 ? '+' : ''}${formatVnd(n)}`
}

/** Tỷ lệ 0..1 -> "71%" (làm tròn đến số nguyên; chỉ để hiển thị số server trả). */
export function formatRatioPercent(r: number): string {
  return `${Math.round(r * 100)}%`
}

/** Phần trăm 0..100 (ví dụ tỷ lệ chia lương): bỏ phần thập phân thừa, "31%" hoặc "12,5%". */
export function formatPercent(p: number): string {
  return `${oneDecimalFmt.format(p)}%`
}

const UNITS = ['không', 'một', 'hai', 'ba', 'bốn', 'năm', 'sáu', 'bảy', 'tám', 'chín']

function readTriple(n: number, full: boolean): string {
  const h = Math.floor(n / 100)
  const t = Math.floor((n % 100) / 10)
  const u = n % 10
  const parts: string[] = []
  if (h > 0 || full) parts.push(`${UNITS[h]} trăm`)
  if (t > 1) parts.push(`${UNITS[t]} mươi`)
  else if (t === 1) parts.push('mười')
  else if (u > 0 && (h > 0 || full)) parts.push('lẻ')
  if (u > 0) {
    if (t > 1 && u === 1) parts.push('mốt')
    else if (t > 0 && u === 5) parts.push('lăm')
    else if (t > 1 && u === 4) parts.push('tư')
    else parts.push(UNITS[u]!)
  }
  return parts.join(' ')
}

function readInt(n: number): string {
  if (n === 0) return 'không'
  const billions = Math.floor(n / 1e9)
  const rest = n % 1e9
  const parts: string[] = []
  if (billions > 0) parts.push(`${readInt(billions)} tỷ`)
  const groups: Array<[number, string]> = [
    [Math.floor(rest / 1e6), 'triệu'],
    [Math.floor((rest % 1e6) / 1e3), 'nghìn'],
    [rest % 1e3, ''],
  ]
  let started = billions > 0
  for (const [g, name] of groups) {
    if (g === 0) continue
    parts.push(`${readTriple(g, started)}${name ? ` ${name}` : ''}`)
    started = true
  }
  return parts.join(' ')
}

/** 250000 -> "hai trăm năm mươi nghìn đồng" (để người dùng soát lại số tiền đã gõ). */
export function vndInWords(n: number): string {
  const v = Math.max(0, Math.round(n))
  return `${readInt(v)} đồng`
}
