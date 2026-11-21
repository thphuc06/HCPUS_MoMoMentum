import { formatVND, formatVNDShort, formatVNDAxis, formatDayMonth } from '../src/lib/format.ts'
import { makeForecast, jarIds } from '../src/lib/forecast-data.ts'
console.log(JSON.stringify([formatVND(1200000), formatVND(-120000), formatVNDShort(1200000), formatVNDShort(950000), formatVNDShort(1250000), formatVNDShort(1500000000), formatVNDAxis(500000), formatVNDAxis(-1200000), formatDayMonth('2026-11-28')]))
for (const j of jarIds()) { const f = makeForecast(j, true); console.log(j, f.runout, f.scenario?.runout, f.series[0].p50, f.series[30].p50, Math.min(...f.series.map(b=>b.p10))) }
