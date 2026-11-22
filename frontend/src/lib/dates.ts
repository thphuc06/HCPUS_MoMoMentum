// Số học ngày theo lịch cho ngày mô phỏng (YYYY-MM-DD). Chỉ dùng để dựng nhãn và vị trí trên biểu đồ, không phải số
// nghiệp vụ (ngày cạn, số ngày tới lương do server trả). Tính theo UTC để không lệch ngày do múi giờ hay giờ mùa hè.

const ISO = /^(\d{4})-(\d{2})-(\d{2})$/
const DAY_MS = 86_400_000

function toUtc(iso: string): number {
  const m = ISO.exec(iso)
  if (!m) return Number.NaN
  return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
}

export function isIsoDate(s: string): boolean {
  if (!ISO.test(s)) return false
  const t = toUtc(s)
  return !Number.isNaN(t) && new Date(t).toISOString().slice(0, 10) === s
}

/** Số ngày từ `from` đến `to` (dương nếu `to` sau `from`). */
export function diffDays(from: string, to: string): number {
  return Math.round((toUtc(to) - toUtc(from)) / DAY_MS)
}

export function addDays(iso: string, n: number): string {
  const d = new Date(toUtc(iso) + n * DAY_MS)
  return d.toISOString().slice(0, 10)
}

/** "2026-11-23" -> "23/11" */
export function formatDayMonth(iso: string): string {
  const m = ISO.exec(iso)
  return m ? `${m[3]}/${m[2]}` : iso
}
