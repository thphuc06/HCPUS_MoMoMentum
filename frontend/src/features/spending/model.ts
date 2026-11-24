import type { CashflowDay, CashflowJar, CashflowResponse } from '@/api/cashflowSchemas'
import { formatDayMonth } from '@/lib/dates'
import { formatVnd } from '@/lib/format'

// Hàm thuần dựng dữ liệu VẼ cho ba biểu đồ chi tiêu (B1, B5, B7) từ `GET /cashflow`. Mọi số tiền, chênh lệch, lũy kế là số server
// trả; ở đây chỉ đổi thành tỷ lệ chiều dài, tọa độ và câu chữ (spending-visualization.md §2.1 quy tắc 1).

/** "05/11–21/11" (khoảng ngày mô phỏng của kỳ). */
export function rangeLabel(from: string, to: string): string {
  return from === to ? formatDayMonth(from) : `${formatDayMonth(from)}–${formatDayMonth(to)}`
}

export function periodNoun(data: CashflowResponse): string {
  return data.period.kind === 'pay_period' ? 'Kỳ lương' : 'Tháng'
}

/** "tăng 1.713.000 ₫" / "giảm 90.000 ₫" / "bằng kỳ trước" từ chênh lệch server trả. */
export function changeText(change: number): string {
  if (change > 0) return `tăng ${formatVnd(change)}`
  if (change < 0) return `giảm ${formatVnd(-change)}`
  return 'bằng kỳ trước'
}

// ---------------------------------------------------------------- B1: chi theo hũ

export type JarBar = {
  jar: CashflowJar
  /** Tỷ lệ 0..1 trên cùng thang của mọi hũ (lớn nhất trong cả chi kỳ này lẫn kỳ trước). */
  regular: number
  credit: number
  fixed: number
  /** Vị trí vạch kỳ trước 0..1 (vắng khi không có kỳ trước). */
  prev?: number
}

/** Thanh của từng hũ, sắp theo mức chi kỳ này (giảm dần; bằng nhau thì theo kỳ trước). Phần tách chỉ có khi server trả. */
export function jarBars(data: CashflowResponse): JarBar[] {
  const jars = [...data.by_jar].sort((a, b) => b.spent_vnd - a.spent_vnd || (b.previous_spent_vnd ?? 0) - (a.previous_spent_vnd ?? 0))
  const scale = Math.max(0, ...jars.map((j) => Math.max(j.spent_vnd, j.previous_spent_vnd ?? 0)))
  const r = (n: number) => (scale > 0 ? Math.min(1, Math.max(0, n / scale)) : 0)
  return jars.map((jar) => {
    const credit = jar.credit_vnd ?? 0
    const fixed = jar.obligation_vnd ?? 0
    return {
      jar,
      regular: r(Math.max(0, jar.spent_vnd - credit - fixed)),
      credit: r(credit),
      fixed: r(fixed),
      ...(jar.previous_spent_vnd !== undefined ? { prev: r(jar.previous_spent_vnd) } : {}),
    }
  })
}

/** Phần "gồm" của một hũ: "gồm Trả sau 967.000 ₫, cố định 180.000 ₫" (rỗng khi không có phần tách nào). */
export function jarParts(jar: CashflowJar): string {
  const parts: string[] = []
  if (jar.credit_vnd) parts.push(`Trả sau ${formatVnd(jar.credit_vnd)}`)
  if (jar.obligation_vnd) parts.push(`cố định ${formatVnd(jar.obligation_vnd)}`)
  return parts.length ? `gồm ${parts.join(', ')}` : ''
}

/** Câu đầy đủ của một hàng cho trình đọc màn hình (nhãn của liên kết mở chi tiết hũ). */
export function jarRowLabel(jar: CashflowJar): string {
  const bits = [`${jar.name}: ${formatVnd(jar.spent_vnd)}`]
  const parts = jarParts(jar)
  if (parts) bits.push(parts)
  if (jar.previous_spent_vnd !== undefined && jar.change_vnd !== undefined) {
    bits.push(`kỳ trước ${formatVnd(jar.previous_spent_vnd)}, ${changeText(jar.change_vnd)}`)
  }
  return `${bits.join(', ')}. Mở chi tiết hũ.`
}

/** Câu tóm tắt của B1 (figcaption, chỉ cho trình đọc màn hình: tổng đã hiện ở B7). */
export function byJarCaption(data: CashflowResponse): string {
  const from = formatDayMonth(data.period.from_date)
  const top = jarBars(data)[0]?.jar
  const head = `${periodNoun(data)} ${from} đến nay bạn đã chi ${formatVnd(data.current.spent_vnd)}`
  if (!top || top.spent_vnd === 0) return `${head}.`
  return `${head}, nhiều nhất ở ${top.name} ${formatVnd(top.spent_vnd)}.`
}

// ---------------------------------------------------------------- B7: thu và chi của kỳ

export type IncomeBar = {
  /** Phần đã chi trên thang max(lương, chi), 0..1. */
  spent: number
  /** Vị trí mốc lương 0..1 khi chi vượt lương (vắng khi chi không vượt lương hoặc chưa có lương). */
  salaryMark?: number
}

export function incomeBar(data: CashflowResponse): IncomeBar {
  const { salary_income_vnd: salary, spent_vnd: spent } = data.current
  const scale = Math.max(salary, spent)
  if (scale <= 0) return { spent: 0 }
  return { spent: spent / scale, ...(salary > 0 && spent > salary ? { salaryMark: salary / scale } : {}) }
}

export function cashflowCaption(data: CashflowResponse): string {
  const c = data.current
  const head = `${periodNoun(data)} ${rangeLabel(data.period.from_date, data.period.to_date)}`
  if (c.salary_income_vnd === 0) return `${head}: lương chưa về, đã chi ${formatVnd(c.spent_vnd)}.`
  const left = c.net_vnd >= 0 ? `còn ${formatVnd(c.net_vnd)}` : `chi quá lương ${formatVnd(-c.net_vnd)}`
  return `${head}: lương vào ${formatVnd(c.salary_income_vnd)}, đã chi ${formatVnd(c.spent_vnd)}, ${left}.`
}

// ---------------------------------------------------------------- B5: lũy kế so với kỳ trước

/** Đường B5 vẽ chi thường ngày (bỏ khoản trả nghĩa vụ) khi server có phần tách; không thì tổng chi. */
export type TrendMeasure = 'regular' | 'total'

export function trendMeasure(data: CashflowResponse): TrendMeasure {
  return data.split_complete && data.daily.every((d) => d.regular_cumulative_vnd !== undefined) ? 'regular' : 'total'
}

const valueOf = (d: CashflowDay, m: TrendMeasure) => (m === 'regular' ? (d.regular_cumulative_vnd ?? d.cumulative_vnd) : d.cumulative_vnd)

export type TrendRow = { day: number; current?: number; previous?: number; date?: string; previousDate?: string }

/** Một hàng mỗi ngày của kỳ (ngày 1 là ngày lương), tới hết kỳ dài hơn trong hai kỳ. */
export function trendRows(data: CashflowResponse, m: TrendMeasure = trendMeasure(data)): TrendRow[] {
  const prev = data.previous ? (data.previous_daily ?? []) : []
  const last = Math.max(data.period.days_total, data.daily.length, prev.length)
  const rows: TrendRow[] = []
  for (let day = 1; day <= last; day++) {
    const c = data.daily.find((d) => d.day_index === day)
    const p = prev.find((d) => d.day_index === day)
    rows.push({
      day,
      ...(c ? { current: valueOf(c, m), date: c.date } : {}),
      ...(p ? { previous: valueOf(p, m), previousDate: p.date } : {}),
    })
  }
  return rows
}

/** Kỳ mới bắt đầu (ngày 1 đến 2): chưa vẽ đường, chỉ hiện số. */
export const TREND_MIN_DAYS = 3

/** Câu ngắn hiện ngay của B5, dựng từ chênh lệch server trả. */
export function trendSummary(data: CashflowResponse, m: TrendMeasure = trendMeasure(data)): string {
  const what = m === 'regular' ? 'Chi thường ngày' : 'Chi'
  if (!data.previous || !data.change) return 'Chưa có kỳ trước để so.'
  const change = m === 'regular' ? (data.change.regular_vnd ?? data.change.spent_vnd) : data.change.spent_vnd
  if (change > 0) return `${what} nhanh hơn kỳ trước ${formatVnd(change)} tính tới hôm nay.`
  if (change < 0) return `${what} chậm hơn kỳ trước ${formatVnd(-change)} tính tới hôm nay.`
  return `${what} bằng kỳ trước tính tới hôm nay.`
}

/** Câu đầy đủ của B5 (nhãn của biểu đồ): ngày thứ mấy, kỳ này, kỳ trước cùng thời điểm. */
export function trendCaption(data: CashflowResponse, m: TrendMeasure = trendMeasure(data)): string {
  const what = m === 'regular' ? 'chi thường ngày' : 'chi'
  const n = data.period.day_index
  const now = m === 'regular' ? (data.current.regular_spent_vnd ?? data.current.spent_vnd) : data.current.spent_vnd
  const head = `Đến ngày ${n} của kỳ bạn ${what} ${formatVnd(now)}`
  if (!data.previous) return `${head}. Chưa có kỳ trước để so.`
  const before = m === 'regular' ? (data.previous.regular_spent_vnd ?? data.previous.spent_vnd) : data.previous.spent_vnd
  return `${head}, kỳ trước cùng thời điểm ${formatVnd(before)}.`
}
