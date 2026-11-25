import { describe, expect, it } from 'vitest'
import type { ForecastTimelineData } from '@/contracts/blocks'
import { validBlock } from '@/test/fixtures'
import { buildChartModel, jarReference, LABEL_SPAN, lowestP50BeforePayday, niceTicks, rowAt, stackLevels, xToLabel } from './model'

const data = (name: string): ForecastTimelineData => (validBlock(name) as unknown as { data: ForecastTimelineData }).data

describe('buildChartModel (fixture forecast_timeline.short)', () => {
  const d = data('forecast_timeline.short')
  const m = buildChartModel(d)

  it('dựng đúng số điểm: một điểm gốc (số dư lúc chạy) cộng mỗi ngày dự báo', () => {
    expect(m.rows).toHaveLength(d.days.length + 1)
    expect(m.rows[0]).toMatchObject({ x: 0, date: d.origin_date, p10: d.start_balance_vnd, p50: d.start_balance_vnd, p90: d.start_balance_vnd })
    expect(m.rows[1]!.x).toBe(1) // ngày dự báo đầu tiên là origin + 1
    expect(m.lastX).toBe(d.days.length)
    expect(m.rows.every((r, i) => i === 0 || r.x === i)).toBe(true)
  })

  it('dải và đường lấy nguyên số của server', () => {
    const last = m.rows[m.rows.length - 1]!
    const lastDay = d.days[d.days.length - 1]!
    expect([last.p10, last.p50, last.p90]).toEqual([lastDay.p10_vnd, lastDay.p50_vnd, lastDay.p90_vnd])
    expect(last.band).toEqual([lastDay.p10_vnd, lastDay.p90_vnd])
  })

  it('mốc nghĩa vụ và lương nằm đúng ngày, trong khung', () => {
    expect(m.events).toHaveLength(d.events.length)
    for (const e of m.events) {
      expect(e.x).toBeGreaterThanOrEqual(0)
      expect(e.x).toBeLessThanOrEqual(m.lastX)
    }
    const salary = m.events.find((e) => e.kind === 'salary')!
    expect(salary.date).toBe(d.payday.date)
    expect(m.paydayX).toBe(salary.x)
  })

  it('điểm cạn: nội suy trên đoạn P50 cắt 0; vùng hụt chạy tới ngày lương', () => {
    expect(m.runout).not.toBeNull()
    const rx = m.rows.find((r) => r.date === d.runout_date)!.x
    expect(m.runout!.date).toBe(d.runout_date)
    expect(m.runout!.x).toBeGreaterThan(rx - 1)
    expect(m.runout!.x).toBeLessThanOrEqual(rx)
    expect(m.shortfallRange).toEqual({ x1: m.runout!.x, x2: m.paydayX! })
  })

  it('miền Y phủ cả dải hụt và số dương, có mốc 0', () => {
    expect(m.yMin).toBeLessThanOrEqual(Math.min(...m.rows.map((r) => r.p10)))
    expect(m.yMax).toBeGreaterThanOrEqual(Math.max(...m.rows.map((r) => r.p90)))
    expect(m.yTicks).toContain(0)
  })

  it('nhãn trục ngày là dd/mm của ngày gốc cộng x', () => {
    expect(xToLabel(d.origin_date, 0)).toBe('21/11')
    expect(xToLabel(d.origin_date, 14)).toBe('05/12')
    expect(rowAt(m, 3)?.date).toBe('2026-11-24')
    expect(rowAt(m, null)).toBeNull()
    expect(rowAt(m, 999)).toBeNull()
  })

  it('vạch dự báo của hũ: số P50 thấp nhất trước kỳ lương và mức tham chiếu theo dự báo', () => {
    const min = lowestP50BeforePayday(d)
    expect(min).toBeLessThan(0) // hũ hụt trước kỳ lương
    expect(jarReference(d)).toBeGreaterThanOrEqual(d.start_balance_vnd)
    expect(jarReference(d, 6_000_000)).toBe(6_000_000)
  })
})

describe('buildChartModel: không cạn, ngày lương ngoài khung', () => {
  it('không có runout_date thì không có điểm cạn và vùng hụt', () => {
    const d = data('forecast_timeline.short')
    const m = buildChartModel({ ...d, runout_date: undefined })
    expect(m.runout).toBeNull()
    expect(m.shortfallRange).toBeNull()
  })

  it('cờ runout_date_shown sai (hũ thưa, #25): không có điểm cạn và vùng hụt dù dữ liệu còn ngày, cả đường Sau', () => {
    const d = data('forecast_timeline.short')
    const m = buildChartModel({ ...d, runout_date_shown: false })
    expect(m.runout).toBeNull()
    expect(m.shortfallRange).toBeNull()
    const w = data('forecast_timeline.what_if')
    const after = { ...w.compare!.after, runout_date: w.days[5]!.date }
    expect(buildChartModel({ ...w, compare: { ...w.compare!, after } }).afterRunout).not.toBeNull()
    expect(buildChartModel({ ...w, runout_date_shown: false, compare: { ...w.compare!, after } }).afterRunout).toBeNull()
  })

  it('ngày lương sau khung thì không vẽ đường lương', () => {
    const d = data('forecast_timeline.short')
    const m = buildChartModel({ ...d, payday: { date: '2027-03-01', days_until: 100 } })
    expect(m.paydayX).toBeNull()
  })

  it('fixture ước lượng ban đầu cũng dựng được', () => {
    const d = data('forecast_timeline.initial_estimate')
    const m = buildChartModel(d)
    expect(m.rows).toHaveLength(d.days.length + 1)
  })
})

describe('niceTicks', () => {
  it('mốc 1-2-5 phủ miền và bao gồm 0 khi miền cắt 0', () => {
    const t = niceTicks(-1_000_000, 2_700_000)
    expect(t[0]).toBeLessThanOrEqual(-1_000_000)
    expect(t[t.length - 1]).toBeGreaterThanOrEqual(2_700_000)
    expect(t).toContain(0)
    const steps = new Set(t.slice(1).map((v, i) => v - t[i]!))
    expect(steps.size).toBe(1)
  })

  it('miền suy biến không làm vỡ', () => {
    expect(niceTicks(0, 0)).toEqual([0, 1])
    expect(niceTicks(5, 5).length).toBeGreaterThanOrEqual(2)
  })
})

describe('nhãn mốc không chồng nhau (lỗi nhỏ phase 2)', () => {
  it('stackLevels: mốc gần nhau (dưới 4 ngày) lên tầng khác nhau, đủ xa thì về tầng 0', () => {
    expect(stackLevels([0, 2, 3, 20])).toEqual([0, 1, 2, 0])
    expect(stackLevels([5, 5, 5, 5])).toEqual([0, 1, 2, 0]) // tối đa 3 tầng rồi quay vòng
    expect(stackLevels([])).toEqual([])
    expect(stackLevels([1, 10, 20])).toEqual([0, 0, 0])
  })

  it('buildChartModel sắp mốc theo ngày và trả tầng cho từng mốc', () => {
    const d = structuredClone(data('forecast_timeline.short'))
    d.events = [
      { date: '2026-11-25', kind: 'obligation', label: 'A', amount_vnd: 1000 },
      { date: '2026-11-24', kind: 'obligation', label: 'B', amount_vnd: 1000 },
    ]
    const m = buildChartModel(d)
    expect(m.events.map((e) => e.label)).toEqual(['B', 'A'])
    expect(m.eventLevels).toEqual([0, 1])
  })

  it('nhãn 12 px: hai mốc cách nhau dưới khoảng một phần ba trục (Tiền điện 26/11, Lương về 05/12) xếp hai tầng', () => {
    const d = structuredClone(data('forecast_timeline.short'))
    const m = buildChartModel(d)
    const [first, second] = m.events
    expect(second!.x - first!.x).toBeLessThan(m.lastX * LABEL_SPAN)
    expect(m.eventLevels).toEqual([0, 1])
  })
})

describe('biến thể trước-sau (compare)', () => {
  const d = data('forecast_timeline.what_if')
  const m = buildChartModel(d)

  it('ghép đường SAU theo ngày, giữ nguyên số engine; dải chênh lệch là khoảng giữa hai đường P50', () => {
    expect(m.hasCompare).toBe(true)
    const after = d.compare!.after
    const row = m.rows.find((r) => r.date === after.days[2]!.date)!
    expect(row.after).toBe(after.days[2]!.p50_vnd)
    expect(row.gap).toEqual([Math.min(row.p50, row.after!), Math.max(row.p50, row.after!)])
    expect(m.rows[0]!.after).toBe(d.start_balance_vnd) // cùng điểm xuất phát
  })

  it('khối không có compare thì không có đường SAU', () => {
    const plain = buildChartModel(data('forecast_timeline.short'))
    expect(plain.hasCompare).toBe(false)
    expect(plain.rows.every((r) => r.after === undefined && r.gap === undefined)).toBe(true)
    expect(plain.afterRunout).toBeNull()
  })
})
