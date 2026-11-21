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

/** Lời chào theo giờ Việt Nam. */
export function greetingForHour(hour: number): string {
  if (hour < 11) return 'Chào buổi sáng'
  if (hour < 14) return 'Chào buổi trưa'
  if (hour < 18) return 'Chào buổi chiều'
  return 'Chào buổi tối'
}

export function vietnamHour(now: Date = new Date()): number {
  return Number(
    new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', hour12: false }).format(now),
  ) % 24
}
