// Dữ liệu dự báo GIẢ sinh trong code (không phải kết quả ML). Hình dạng khớp ForecastTimelineData
// trong docs/research/agentic-ui-generative-ui.md §9.4 (date ISO, p10/p50/p90 số nguyên VND).
// Không import alias để mock server Node chạy trực tiếp được.

export type Band = { date: string; p10: number; p50: number; p90: number }
export type FEvent = { date: string; kind: 'payday' | 'obligation' | 'scenario'; label: string; amount_vnd: number }
export type Runout = { date_p50: string | null; p_shortfall_before_payday: number }
export type ForecastData = {
  jar_id: string
  jar_name: string
  today: string
  payday: string
  series: Band[]
  events: FEvent[]
  runout: Runout
  scenario: null | { label: string; series: Band[]; runout: Runout }
  data_quality: 'high' | 'medium' | 'low'
  data_quality_reasons: string[]
}

export const TODAY = '2026-11-21'

function iso(base: string, add: number): string {
  const d = new Date(`${base}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + add)
  return d.toISOString().slice(0, 10)
}

type JarCfg = { name: string; start: number; daily: number; sigma: number; payday: number; salary: number; obligations: { day: number; label: string; amount: number }[] }

const CFG: Record<string, JarCfg> = {
  an_uong: {
    name: 'Ăn uống',
    start: 1_900_000,
    daily: 190_000,
    sigma: 70_000,
    payday: 14,
    salary: 4_500_000,
    obligations: [{ day: 5, label: 'Tiền điện', amount: 450_000 }],
  },
  di_lai: {
    name: 'Đi lại',
    start: 1_300_000,
    daily: 55_000,
    sigma: 30_000,
    payday: 14,
    salary: 1_000_000,
    obligations: [{ day: 9, label: 'Phí gửi xe', amount: 120_000 }],
  },
  giai_tri: {
    name: 'Giải trí',
    start: 900_000,
    daily: 62_000,
    sigma: 55_000,
    payday: 14,
    salary: 1_200_000,
    obligations: [{ day: 12, label: 'Gói phim', amount: 180_000 }],
  },
}

export function jarIds(): string[] {
  return Object.keys(CFG)
}

function simulate(c: JarCfg, extraOutflows: { day: number; amount: number }[] = []): Band[] {
  const out: Band[] = []
  let p50 = c.start
  for (let d = 0; d <= 30; d++) {
    if (d > 0) {
      p50 -= c.daily
      for (const o of c.obligations) if (o.day === d) p50 -= o.amount
      if (d === c.payday) p50 += c.salary
    }
    for (const o of extraOutflows) if (o.day === d) p50 -= o.amount
    const s = c.sigma * Math.sqrt(d) * 1.28155
    out.push({ date: iso(TODAY, d), p10: Math.round(p50 - s), p50: Math.round(p50), p90: Math.round(p50 + s) })
  }
  return out
}

function runoutOf(series: Band[], paydayIso: string): Runout {
  const hit = series.find((b) => b.date <= paydayIso && b.p50 <= 0)
  const hitP10 = series.find((b) => b.date <= paydayIso && b.p10 <= 0)
  return {
    date_p50: hit ? hit.date : null,
    p_shortfall_before_payday: hit ? 0.7 : hitP10 ? 0.25 : 0.05,
  }
}

export function makeForecast(jarId = 'an_uong', withScenario = false): ForecastData {
  const c = CFG[jarId] ?? CFG.an_uong
  const paydayIso = iso(TODAY, c.payday)
  const series = simulate(c)
  const events: FEvent[] = [
    ...c.obligations.map((o) => ({ date: iso(TODAY, o.day), kind: 'obligation' as const, label: o.label, amount_vnd: -o.amount })),
    { date: paydayIso, kind: 'payday', label: 'Lương', amount_vnd: c.salary },
  ]
  let scenario: ForecastData['scenario'] = null
  if (withScenario) {
    const s = simulate(c, [{ day: 2, amount: 1_200_000 }])
    scenario = { label: 'Mua tai nghe 1,2 triệu', series: s, runout: runoutOf(s, paydayIso) }
  }
  return {
    jar_id: jarId,
    jar_name: c.name,
    today: TODAY,
    payday: paydayIso,
    series,
    events,
    runout: runoutOf(series, paydayIso),
    scenario,
    data_quality: 'medium',
    data_quality_reasons: ['Dựa trên 4/6 mục đã khai'],
  }
}

export function jarBalance(jarId: string): number {
  return (CFG[jarId] ?? CFG.an_uong).start
}
