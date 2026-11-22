import { describe, expect, it } from 'vitest'
import type { ForecastTimelineData } from '@/contracts/blocks'
import { validBlock } from '@/test/fixtures'
import { buildChartModel, jarReference, lowestP50BeforePayday, niceTicks, rowAt, xToLabel } from './model'

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
