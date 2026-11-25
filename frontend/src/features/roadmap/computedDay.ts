import { addDays, diffDays } from '@/lib/dates'

// Múi giờ ứng dụng (ADR-0003), cùng giá trị với `TZ` của `lib/format.ts` (hằng đó chưa được export).
const APP_TIME_ZONE = 'Asia/Ho_Chi_Minh'
const dayParts = new Intl.DateTimeFormat('en-US', { timeZone: APP_TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit' })

/** Ngày `YYYY-MM-DD` theo múi giờ ứng dụng của một thời điểm thật (RFC 3339); null nếu không đọc được. */
function zoneDay(iso: string): string | null {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const p = Object.fromEntries(dayParts.formatToParts(d).map((x) => [x.type, x.value]))
  return `${p.year}-${p.month}-${p.day}`
}

/**
 * Ngày mô phỏng của thời điểm thật `instant`, theo ADR-0003: ngày mô phỏng = ngày theo múi giờ ứng dụng + offset. Offset lấy từ chính
 * phiên bản lộ trình: `createdAt` (giờ thật lúc lưu) và `appDate` (ngày mô phỏng lúc lưu), nên không cần đồng hồ của máy người dùng.
 * Dùng cho nhãn "Số tính ngày …" (`basis.computed_at`), để ngày này cùng hệ với các ngày khác trên màn lộ trình.
 */
export function simDayOf(instant: string, createdAt: string, appDate: string): string | null {
  const day = zoneDay(instant)
  const savedDay = zoneDay(createdAt)
  if (day === null || savedDay === null) return null
  return addDays(appDate, diffDays(savedDay, day))
}
