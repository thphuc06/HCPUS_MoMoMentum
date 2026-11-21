// Định dạng tiền VND và ngày, tự viết (không dựa vào Intl compact giữa các trình duyệt).
// Chỉ dùng cú pháp erasable để Node 24 chạy trực tiếp được (scripts/check-format.ts).

export const NBSP = ' '
const MINUS = '−'

function group(n: number): string {
  return Math.round(Math.abs(n))
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}

/** 1200000 -> "1.200.000 ₫"; âm -> "−120.000 ₫" (dấu trừ Unicode) */
export function formatVND(n: number): string {
  const sign = Math.round(n) < 0 ? MINUS : ''
  return `${sign}${group(n)}${NBSP}₫`
}

/** Chỉ phần số có chấm nhóm nghìn, không có ký hiệu tiền. */
export function formatVNDNumber(n: number): string {
  return `${Math.round(n) < 0 ? MINUS : ''}${group(n)}`
}

function trimDecimal(x: number, digits: number): string {
  const f = Math.pow(10, digits)
  const r = Math.round(x * f) / f
  return r.toString().replace('.', ',')
}

/** 1200000 -> "1,2 triệu"; 950000 -> "950 nghìn"; 1500000000 -> "1,5 tỷ" */
export function formatVNDShort(n: number, digits = 1): string {
  const sign = Math.round(n) < 0 ? MINUS : ''
  const a = Math.abs(n)
  if (a >= 1e9) return `${sign}${trimDecimal(a / 1e9, digits)} tỷ`
  if (a >= 1e6) return `${sign}${trimDecimal(a / 1e6, digits)} triệu`
  if (a >= 1e3) return `${sign}${trimDecimal(a / 1e3, 0)} nghìn`
  return `${sign}${Math.round(a)}`
}

/** Dạng cực gọn cho trục biểu đồ: "1,2tr", "500k", "0" */
export function formatVNDAxis(n: number): string {
  const sign = Math.round(n) < 0 ? MINUS : ''
  const a = Math.abs(n)
  if (a >= 1e9) return `${sign}${trimDecimal(a / 1e9, 1)}tỷ`
  if (a >= 1e6) return `${sign}${trimDecimal(a / 1e6, 1)}tr`
  if (a >= 1e3) return `${sign}${trimDecimal(a / 1e3, 0)}k`
  return `${sign}${Math.round(a)}`
}

const TZ = 'Asia/Ho_Chi_Minh'
const dmFmt = new Intl.DateTimeFormat('vi-VN', { timeZone: TZ, day: 'numeric', month: 'numeric' })

/** "2026-11-28" -> "28/11" */
export function formatDayMonth(iso: string): string {
  return dmFmt.format(new Date(`${iso}T00:00:00+07:00`))
}

/** Cộng ngày cho một chuỗi ISO yyyy-mm-dd (tính theo UTC để không lệch múi giờ). */
export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export function diffDays(fromIso: string, toIso: string): number {
  return Math.round(
    (Date.parse(`${toIso}T00:00:00Z`) - Date.parse(`${fromIso}T00:00:00Z`)) / 86400000,
  )
}
