import { addDays, diffDays, formatDayMonth } from '@/lib/dates'
import type { ForecastTimelineData } from '@/contracts/blocks'

// Dựng dữ liệu cho biểu đồ dự báo từ khối `forecast_timeline` (thuần hàm, test không cần DOM). Mọi số trên đồ thị là
// số server trả (phân vị số dư, mốc, ngày cạn); ở đây chỉ đổi ngày thành tọa độ x (số ngày kể từ ngày gốc) và chọn
// các mốc trục cho dễ đọc.

export type ChartRow = {
  /** Số ngày kể từ origin_date (0 là ngày gốc với số dư lúc chạy). */
  x: number
  date: string
  p10: number
  p50: number
  p90: number
  band: [number, number]
  /** Chỉ khi khối có `compare`: số dư giữa SAU kịch bản và dải chênh lệch giữa TRƯỚC và SAU (để tô). */
  after?: number
  after10?: number
  after90?: number
  gap?: [number, number]
}

export type ChartEvent = { x: number; date: string; kind: 'obligation' | 'salary'; label: string; amountVnd: number; amountMaxVnd?: number }

export type ChartModel = {
  rows: ChartRow[]
  lastX: number
  yMin: number
  yMax: number
  yTicks: number[]
  xTicks: number[]
  events: ChartEvent[]
  /** Vị trí x (có thể lẻ để chấm nằm đúng trên đường) của điểm cạn; null nếu không cạn. */
  runout: { x: number; date: string } | null
  /** x của ngày lương nếu nằm trong khung. */
  paydayX: number | null
  /** Vùng hụt: từ ngày cạn tới ngày lương (hoặc hết khung). */
  shortfallRange: { x1: number; x2: number } | null
  /** Có vẽ đường SAU (khối `forecast_timeline` biến thể trước-sau). */
  hasCompare: boolean
  /** Điểm cạn của đường SAU (khối trước-sau). */
  afterRunout: { x: number; date: string } | null
  /** Mức xếp lớp (0, 1, 2) của nhãn mốc theo thứ tự `events`: mốc gần nhau (trong 4 ngày) xếp lên các tầng khác nhau để nhãn không chồng. */
  eventLevels: number[]
}

/** Mốc trục "đẹp" theo bước 1-2-5 × 10^k, phủ [lo, hi]. */
export function niceTicks(lo: number, hi: number, target = 5): number[] {
  if (!(hi > lo)) {
    const v = Number.isFinite(lo) ? lo : 0
    return v === 0 ? [0, 1] : [Math.min(0, v), Math.max(0, v)]
  }
  const raw = (hi - lo) / Math.max(1, target)
  const pow = 10 ** Math.floor(Math.log10(raw))
  const f = raw / pow
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * pow
  const start = Math.floor(lo / step) * step
  const end = Math.ceil(hi / step) * step
  const ticks: number[] = []
  for (let v = start; v <= end + step / 2; v += step) ticks.push(Math.round(v))
  return ticks
}

function xTickList(lastX: number): number[] {
  const step = lastX <= 10 ? 2 : lastX <= 21 ? 5 : lastX <= 45 ? 7 : 14
  const out: number[] = []
  for (let x = 0; x <= lastX; x += step) out.push(x)
  return out
}

/** Phần bề ngang vùng vẽ mà một nhãn mốc chiếm (chữ 12 px, khung 390 px). */
export const LABEL_SPAN = 0.34

/** Tầng của nhãn mốc: mốc đứng gần mốc trước (cách dưới `minGap` ngày) lên tầng kế tiếp, tối đa 3 tầng; đủ xa thì về tầng 0. */
export function stackLevels(xs: readonly number[], minGap = 4, maxLevels = 3): number[] {
  const out: number[] = []
  let prevX = Number.NEGATIVE_INFINITY
  let level = 0
  for (const x of xs) {
    level = x - prevX < minGap ? (level + 1) % maxLevels : 0
    out.push(level)
    prevX = x
  }
  return out
}

function runoutPoint(d: { origin: string; runout?: string }, rows: ChartRow[], pick: (r: ChartRow) => number | undefined, lastX: number): { x: number; date: string } | null {
  if (!d.runout) return null
  const rx = diffDays(d.origin, d.runout)
  let x = rx
  const cur = rows.find((r) => r.x === rx)
  const prev = rows.find((r) => r.x === rx - 1)
  const cv = cur ? pick(cur) : undefined
  const pv = prev ? pick(prev) : undefined
  // Điểm P50 cắt y = 0: nội suy giữa ngày trước và ngày cạn để chấm nằm đúng trên đường.
  if (cv !== undefined && pv !== undefined && pv > 0 && cv <= 0) x = prev!.x + pv / (pv - cv)
  return rx >= 0 && rx <= lastX ? { x, date: d.runout } : null
}

export function buildChartModel(d: ForecastTimelineData): ChartModel {
  const first: ChartRow = {
    x: 0,
    date: d.origin_date,
    p10: d.start_balance_vnd,
    p50: d.start_balance_vnd,
    p90: d.start_balance_vnd,
    band: [d.start_balance_vnd, d.start_balance_vnd],
  }
  const rows: ChartRow[] = [
    first,
    ...d.days.map((day) => ({
      x: diffDays(d.origin_date, day.date),
      date: day.date,
      p10: day.p10_vnd,
      p50: day.p50_vnd,
      p90: day.p90_vnd,
      band: [day.p10_vnd, day.p90_vnd] as [number, number],
    })),
  ]
  const lastX = rows[rows.length - 1]!.x

  // Biến thể trước-sau: ghép đường SAU theo ngày (cùng ngày với baseline).
  const after = d.compare?.after
  if (after) {
    const byDate = new Map(after.days.map((a) => [a.date, a]))
    for (const r of rows) {
      const a = r.x === 0 ? { p10_vnd: d.start_balance_vnd, p50_vnd: d.start_balance_vnd, p90_vnd: d.start_balance_vnd } : byDate.get(r.date)
      if (!a) continue
      r.after = a.p50_vnd
      r.after10 = a.p10_vnd
      r.after90 = a.p90_vnd
      r.gap = [Math.min(r.p50, a.p50_vnd), Math.max(r.p50, a.p50_vnd)]
    }
  }

  const lo = Math.min(0, ...rows.map((r) => Math.min(r.p10, r.after10 ?? r.p10)))
  const hi = Math.max(0, ...rows.map((r) => Math.max(r.p90, r.after90 ?? r.p90)))
  const yTicks = niceTicks(lo, hi)

  const events: ChartEvent[] = d.events
    .map((e) => ({ x: diffDays(d.origin_date, e.date), date: e.date, kind: e.kind, label: e.label, amountVnd: e.amount_vnd, amountMaxVnd: e.amount_max_vnd }))
    .filter((e) => e.x >= 0 && e.x <= lastX)
    .sort((a, b) => a.x - b.x)

  // Hũ thưa (#25, `runout_date_shown: false`): không có điểm cạn, vùng hụt hay "Sau: cạn …" (không nêu ngày cạn cụ thể).
  const hidden = d.runout_date_shown === false
  const runout = hidden ? null : runoutPoint({ origin: d.origin_date, runout: d.runout_date }, rows, (r) => r.p50, lastX)
  const afterRunout = after && !hidden ? runoutPoint({ origin: d.origin_date, runout: after.runout_date }, rows, (r) => r.after, lastX) : null

  const px = diffDays(d.origin_date, d.payday.date)
  const paydayX = px >= 0 && px <= lastX ? px : null
  const shortfallRange = runout ? { x1: runout.x, x2: Math.max(runout.x, paydayX ?? lastX) } : null

  // Nhãn mốc 12 px rộng khoảng 1/3 vùng vẽ trên khung 390 px: hai mốc cách nhau dưới 1/3 khoảng ngày thì xếp tầng khác nhau.
  const eventLevels = stackLevels(events.map((e) => e.x), Math.max(4, lastX * LABEL_SPAN))
  return {
    rows,
    lastX,
    yMin: yTicks[0]!,
    yMax: yTicks[yTicks.length - 1]!,
    yTicks,
    xTicks: xTickList(lastX),
    events,
    runout,
    paydayX,
    shortfallRange,
    hasCompare: after !== undefined,
    afterRunout,
    eventLevels,
  }
}

/** Nhãn ngày dd/mm của tọa độ x. */
export function xToLabel(originDate: string, x: number): string {
  return formatDayMonth(addDays(originDate, Math.round(x)))
}


/** Điểm có ngày `x` (để dòng đọc số khi chạm); null nếu không có. */
export function rowAt(m: ChartModel, x: number | null): ChartRow | null {
  if (x === null) return null
  return m.rows.find((r) => r.x === x) ?? null
}

/** Số dư P50 thấp nhất từ ngày gốc tới trước ngày lương (hoặc hết khung): mức thấp nhất dự kiến, để vẽ vạch "dự báo" trên hũ. */
export function lowestP50BeforePayday(d: ForecastTimelineData): number {
  const upto = d.days.filter((day) => day.date < d.payday.date)
  const rows = upto.length > 0 ? upto : d.days
  return Math.min(d.start_balance_vnd, ...rows.map((r) => r.p50_vnd))
}

/**
 * Dự báo không thấy gì rút tiền khỏi hũ (#39): đủ, không ngày cạn, không khoản đến hạn, số dư hôm nay không âm và không ngày nào (kể
 * cả cận dưới P10) xuống dưới số dư hôm nay. Ví dụ hũ để dành chưa có tiền, hũ mục tiêu chỉ nhận lương. Chỉ đọc số server trả (không
 * theo mã hũ, không tính lại); cùng định nghĩa với `no_outflow_expected` của `yofina_core.blocks`.
 */
export function noOutflowExpected(d: ForecastTimelineData): boolean {
  const start = d.start_balance_vnd
  return (
    d.status === 'ok' &&
    !d.runout_date &&
    start >= 0 &&
    !d.events.some((e) => e.kind === 'obligation') &&
    d.days.every((day) => day.p10_vnd >= start)
  )
}

/**
 * Hũ để dành còn tiền mà dự báo không thấy gì rút (#39 lần hai): điều cần nói ở hũ này, theo số của khối. Hũ để dành là khối có
 * `jar.purpose` (chỉ hũ `saving` mới có, ràng buộc của migration 0057). Không nói "không có khoản chi" vì lịch sử có thể có khoản rút
 * tay mà dự báo không tính. Có mốc lương trong kỳ thì `salary` (số và ngày của mốc sớm nhất); không thì `flat` khi mọi ngày (P10, P50,
 * P90) bằng số dư hôm nay; còn lại `steady` (chỉ biết số dư không xuống dưới mức hôm nay). Khối không có số mục tiêu nên không nói tiến
 * độ mục tiêu. Null với hũ 0 ₫, hũ không phải hũ để dành, hoặc dự báo có rút tiền. Cùng định nghĩa với `_no_outflow_sentence` của
 * `yofina_core.blocks`.
 */
export type IdleSaving = { kind: 'salary'; date: string; amountVnd: number } | { kind: 'flat' } | { kind: 'steady' }

export function idleSaving(d: ForecastTimelineData): IdleSaving | null {
  const start = d.start_balance_vnd
  if (!d.jar.purpose || start <= 0 || !noOutflowExpected(d)) return null
  const salary = d.events.filter((e) => e.kind === 'salary').sort((a, b) => a.date.localeCompare(b.date))[0]
  if (salary) return { kind: 'salary', date: salary.date, amountVnd: salary.amount_vnd }
  if (d.days.every((day) => day.p10_vnd === start && day.p50_vnd === start && day.p90_vnd === start)) return { kind: 'flat' }
  return { kind: 'steady' }
}

/** Mức tham chiếu để vẽ hũ: mục tiêu nếu có, không thì số lớn nhất mà dự báo cho thấy (số dư, P90). */
export function jarReference(d: ForecastTimelineData, goalVnd?: number): number {
  if (goalVnd && goalVnd > 0) return goalVnd
  return Math.max(d.start_balance_vnd, ...d.days.map((r) => r.p90_vnd), 1)
}
