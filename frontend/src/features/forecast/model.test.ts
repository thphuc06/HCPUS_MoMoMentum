import { describe, expect, it } from 'vitest'
import type { ForecastTimelineData } from '@/contracts/blocks'
import { validBlock } from '@/test/fixtures'
import {
  buildChartModel,
  type EventLabel,
  jarReference,
  LABEL_CHAR_PX,
  LABEL_GAP_PX,
  LABEL_SPACE_PX,
  labelWidth,
  layoutEventLabels,
  lowestP50BeforePayday,
  MAX_LABEL_LEVELS,
  niceTicks,
  REF_PLOT_WIDTH_PX,
  rowAt,
  xToLabel,
} from './model'

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

describe('nhãn mốc không tràn khỏi vùng vẽ và không chồng nhau (#39, khung chat 390 px)', () => {
  /** Vùng vẽ của biểu đồ trong thẻ ở khổ 390 px: trục Y rộng 50, lề phải 18. */
  const PLOT = { left: 50, width: REF_PLOT_WIDTH_PX }
  const right = PLOT.left + PLOT.width
  const ev = (x: number, label: string, date: string) => ({ x, label, date })
  const overlaps = (a: EventLabel, b: EventLabel) => a.level === b.level && a.left < b.right + LABEL_GAP_PX && b.left < a.right + LABEL_GAP_PX

  it('bề rộng ước lượng của nhãn 12 px đậm: khoảng trắng hẹp hơn chữ, cộng dồn theo ký tự', () => {
    expect(labelWidth('Lương về 05/12')).toBeCloseTo(12 * LABEL_CHAR_PX + 2 * LABEL_SPACE_PX)
    expect(labelWidth('')).toBe(0)
  })

  it('mốc sát mép trái (ảnh h-c: "Tiền cơm văn phòng 23/11" ở ngày thứ 2): neo mép trái vùng vẽ, không còn tràn ra ngoài', () => {
    const [l] = layoutEventLabels([ev(2, 'Tiền cơm văn phòng', '2026-11-23')], 30, PLOT)
    expect(l).toMatchObject({ text: 'Tiền cơm văn phòng 23/11', anchor: 'start', x: PLOT.left, left: PLOT.left, level: 0 })
    expect(l!.right).toBeCloseTo(PLOT.left + labelWidth('Tiền cơm văn phòng 23/11'))
    expect(l!.right).toBeLessThanOrEqual(right)
  })

  it('mốc sát mép phải: neo mép phải vùng vẽ', () => {
    const [l] = layoutEventLabels([ev(29, 'Trả sau', '2026-12-20')], 30, PLOT)
    expect(l).toMatchObject({ text: 'Trả sau 20/12', anchor: 'end', x: right, right, level: 0 })
    expect(l!.left).toBeGreaterThanOrEqual(PLOT.left)
  })

  it('mốc ở giữa, đủ chỗ: căn giữa đúng vạch mốc', () => {
    const [l] = layoutEventLabels([ev(15, 'Lương về', '2026-12-06')], 30, PLOT)
    expect(l).toMatchObject({ anchor: 'middle', x: PLOT.left + PLOT.width / 2, level: 0 })
  })

  it('hai mốc gần nhau (ảnh h-c: "Tiền cơm văn phòng 23/11" và "Lương về 05/12"): nhãn thứ hai lên tầng trên, không đè nhau', () => {
    const out = layoutEventLabels([ev(2, 'Tiền cơm văn phòng', '2026-11-23'), ev(14, 'Lương về', '2026-12-05')], 30, PLOT)
    const [a, b] = out as [EventLabel, EventLabel]
    expect(a.level).toBe(0)
    expect(b.level).toBe(1)
    expect(b.text).toBe('Lương về 05/12')
    for (const l of [a, b]) expect(l.left >= PLOT.left && l.right <= right).toBe(true)
  })

  it('hai mốc đủ xa: cùng tầng 0', () => {
    const out = layoutEventLabels([ev(2, 'Tiền điện', '2026-11-23'), ev(27, 'Lương về', '2026-12-18')], 30, PLOT)
    expect(out.map((l) => l?.level)).toEqual([0, 0])
  })

  it('nhiều mốc cùng chỗ: tối đa 3 tầng; hết tầng mà bản rút gọn (chỉ ngày) cũng không có chỗ thì bỏ chữ (mốc vẫn có trong "Chi tiết dự báo")', () => {
    const many = [0, 1, 2, 3, 4].map((i) => ev(10, `Khoản ${i}`, `2026-12-0${i + 1}`))
    const out = layoutEventLabels(many, 30, PLOT)
    expect(out.map((l) => l?.level ?? null)).toEqual([0, 1, 2, null, null])
    const shown = out.filter((l): l is EventLabel => l !== null)
    expect(shown.every((l) => l.text.startsWith('Khoản'))).toBe(true)
    for (const [i, a] of shown.entries()) for (const b of shown.slice(i + 1)) expect(overlaps(a, b)).toBe(false)
  })

  it('hết tầng nhưng bản rút gọn có chỗ: nhãn chỉ còn ngày, không đè nhãn bên cạnh', () => {
    const out = layoutEventLabels([ev(5, 'Tiền điện', '2026-11-26'), ev(15, 'Lương về', '2026-12-06')], 30, PLOT, 1)
    const [a, b] = out as [EventLabel, EventLabel]
    expect(a.text).toBe('Tiền điện 26/11')
    expect(b).toMatchObject({ text: '06/12', level: 0, anchor: 'middle' })
    expect(overlaps(a, b)).toBe(false)
    expect(MAX_LABEL_LEVELS).toBe(3)
  })

  it('nhãn dài hơn cả vùng vẽ: rút gọn tên bằng dấu "…", giữ ngày, vừa trong vùng vẽ', () => {
    const [l] = layoutEventLabels([ev(15, 'Trả góp điện thoại kỳ thứ ba của hợp đồng mua máy mới', '2026-12-06')], 30, PLOT)
    expect(l!.text).toMatch(/^Trả góp.*… 06\/12$/)
    expect(l!.right - l!.left).toBeLessThanOrEqual(PLOT.width)
    expect(l!.left).toBeGreaterThanOrEqual(PLOT.left)
  })

  it('buildChartModel sắp mốc theo ngày và trả tầng cho từng mốc (ở bề ngang tham chiếu, để chừa lề trên)', () => {
    const d = structuredClone(data('forecast_timeline.short'))
    d.events = [
      { date: '2026-11-25', kind: 'obligation', label: 'A', amount_vnd: 1000 },
      { date: '2026-11-24', kind: 'obligation', label: 'B', amount_vnd: 1000 },
    ]
    const m = buildChartModel(d)
    expect(m.events.map((e) => e.label)).toEqual(['B', 'A'])
    expect(m.eventLevels).toEqual([0, 1])
  })

  it('fixture: "Tiền điện 26/11" và "Lương về 05/12" chạm nhau ở bề ngang tham chiếu nên xếp hai tầng', () => {
    const m = buildChartModel(structuredClone(data('forecast_timeline.short')))
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
