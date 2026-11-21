import { useMemo, useState } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts'
import { addDays, diffDays, formatDayMonth, formatVND, formatVNDAxis, formatVNDShort } from '@/lib/format'
import type { ForecastData } from '@/lib/forecast-data'

type Props = {
  data: ForecastData
  /** true = hiện dải "sau what-if" (dải xám "trước" vẫn giữ để so sánh) */
  showScenario?: boolean
  height?: number
  ariaLabel?: string
}

type Row = {
  day: number
  base: [number, number]
  baseP50: number
  scn: [number, number]
  scnP50: number
}

const ANIM = 700
const HALO = { paintOrder: 'stroke', stroke: 'var(--card)', strokeWidth: 3, strokeLinejoin: 'round' } as const

export function ForecastChart({ data, showScenario = false, height = 230, ariaLabel }: Props) {
  const [active, setActive] = useState<number | null>(null)
  const scn = data.scenario

  const rows = useMemo<Row[]>(() => {
    return data.series.map((b, i) => {
      const s = scn && showScenario ? scn.series[i] : b
      return {
        day: diffDays(data.today, b.date),
        base: [b.p10, b.p90],
        baseP50: b.p50,
        scn: [s.p10, s.p90],
        scnP50: s.p50,
      }
    })
  }, [data, scn, showScenario])

  // miền Y cố định theo cả hai kịch bản để nền không "nhảy" khi bật tắt what-if
  const { yMin, yMax, yTicks } = useMemo(() => {
    const all = [...data.series, ...(scn ? scn.series : [])]
    const lo = Math.min(...all.map((b) => b.p10), 0)
    const hi = Math.max(...all.map((b) => b.p90))
    const span = hi - lo
    const step = span <= 3_000_000 ? 500_000 : span <= 6_000_000 ? 1_000_000 : 2_000_000
    const a = Math.floor(lo / step) * step
    const b = Math.ceil(hi / step) * step
    const t: number[] = []
    for (let v = a; v <= b; v += step) t.push(v)
    return { yMin: a, yMax: b, yTicks: t }
  }, [data, scn])

  const runout = (showScenario && scn ? scn.runout : data.runout).date_p50
  const runoutDay = runout ? diffDays(data.today, runout) : null
  // điểm P50 cắt y=0: nội suy tuyến tính giữa ngày trước và ngày cạn để chấm đỏ nằm đúng trên đường
  const runoutX = (() => {
    if (runoutDay === null || runoutDay === 0) return runoutDay
    const cur = rows[runoutDay]
    const prev = rows[runoutDay - 1]
    if (!cur || !prev || prev.scnP50 <= 0) return runoutDay
    return runoutDay - 1 + prev.scnP50 / (prev.scnP50 - cur.scnP50)
  })()
  const paydayDay = diffDays(data.today, data.payday)
  const lastDay = rows[rows.length - 1].day
  const ticks = [0, 5, 10, 15, 20, 25, 30].filter((t) => t <= lastDay)
  const readout = rows.find((r) => r.day === active) ?? null

  return (
    <div>
      <div
        className="mb-1 min-h-10 text-[13px] leading-snug text-muted-foreground"
        aria-live="polite"
        data-testid="chart-readout"
      >
        {readout ? (
          <>
            <span className="font-semibold text-foreground">{formatDayMonth(addDays(data.today, readout.day))}</span>
            {' · giữa '}
            <span className="num font-semibold text-foreground">{formatVNDShort(readout.scnP50)}</span>
            {' · khoảng 80% khả năng từ '}
            <span className="num">{formatVNDShort(readout.scn[0])}</span>
            {' đến '}
            <span className="num">{formatVNDShort(readout.scn[1])}</span>
          </>
        ) : (
          <>Chạm vào biểu đồ để xem số dư từng ngày. Dải màu = khoảng 80% khả năng số dư nằm trong vùng này.</>
        )}
      </div>
      <div role="img" aria-label={ariaLabel ?? `Biểu đồ dự báo số dư hũ ${data.jar_name} 30 ngày`} style={{ height }}>
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <ComposedChart
            data={rows}
            margin={{ top: 24, right: 18, bottom: 0, left: 0 }}
            onMouseMove={(s) => {
              const i = typeof s.activeTooltipIndex === 'number' ? s.activeTooltipIndex : Number(s.activeTooltipIndex)
              setActive(Number.isFinite(i) && rows[i] ? rows[i].day : null)
            }}
            onMouseLeave={() => setActive(null)}
          >
            <defs>
              <pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="7" height="7" fill="var(--short-soft)" />
                <line x1="0" y1="0" x2="0" y2="7" stroke="var(--short)" strokeWidth="1.6" strokeOpacity="0.55" />
              </pattern>
            </defs>
            <CartesianGrid vertical={false} stroke="var(--grid)" strokeDasharray="3 4" />
            <XAxis
              dataKey="day"
              type="number"
              domain={[0, lastDay]}
              ticks={ticks}
              tickFormatter={(d: number) => formatDayMonth(addDays(data.today, d))}
              tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
              tickLine={false}
              axisLine={false}
              tickMargin={6}
              interval={0}
            />
            <YAxis
              domain={[yMin, yMax]}
              ticks={yTicks}
              tickFormatter={(v: number) => formatVNDAxis(v)}
              tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
              tickLine={false}
              axisLine={false}
              width={44}
            />

            {runoutDay !== null && (
              <ReferenceArea x1={runoutDay} x2={paydayDay} y1={yMin} y2={0} fill="url(#hatch)" fillOpacity={1} stroke="none" ifOverflow="hidden" />
            )}

            {/* dải "trước" (xám) và dải "sau" (chàm); khi tắt what-if hai dải trùng nhau */}
            <Area
              type="monotone"
              dataKey="base"
              stroke="var(--band-before)"
              strokeWidth={1}
              strokeDasharray="3 3"
              fill="var(--band-before)"
              fillOpacity={0.14}
              isAnimationActive={false}
              activeDot={false}
            />
            <Area
              type="monotone"
              dataKey="scn"
              stroke="none"
              fill="var(--band)"
              fillOpacity={0.22}
              isAnimationActive
              animationDuration={ANIM}
              animationEasing="ease-in-out"
              activeDot={false}
            />
            <Line
              type="monotone"
              dataKey="baseP50"
              stroke="var(--band-before)"
              strokeWidth={1.5}
              strokeDasharray="5 4"
              dot={false}
              activeDot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="scnP50"
              stroke="var(--band)"
              strokeWidth={2.5}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--card)', fill: 'var(--band)' }}
              isAnimationActive
              animationDuration={ANIM}
              animationEasing="ease-in-out"
            />

            <ReferenceLine y={0} stroke="var(--muted-foreground)" strokeOpacity={0.6} />
            {data.events.map((e) => {
              const d = diffDays(data.today, e.date)
              const isPay = e.kind === 'payday'
              return (
                <ReferenceLine
                  key={e.date + e.label}
                  x={d}
                  stroke={isPay ? 'var(--ok)' : 'var(--warn)'}
                  strokeWidth={1.5}
                  strokeDasharray={isPay ? '4 3' : '2 3'}
                  label={{
                    value: `${e.label} ${formatDayMonth(e.date)}`,
                    position: 'top',
                    fontSize: 10.5,
                    fontWeight: 700,
                    fill: isPay ? 'var(--ok-ink)' : 'var(--warn-ink)',
                    style: HALO,
                  }}
                />
              )
            })}
            {runoutDay !== null && runoutX !== null && (
              <ReferenceDot
                x={runoutX}
                y={0}
                r={5.5}
                fill="var(--short)"
                stroke="var(--card)"
                strokeWidth={2}
                label={{ value: `Cạn ~${formatDayMonth(runout!)}`, position: 'bottom', fontSize: 11, fontWeight: 700, fill: 'var(--short-ink)', dy: 4, style: HALO }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-4 rounded-sm bg-[var(--band)] opacity-40" /> Dải 80%
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 bg-[var(--band)]" /> Số dư giữa
        </span>
        {scn && showScenario && (
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-0 w-4 border-t-2 border-dashed border-[var(--band-before)]" /> Trước {scn.label.toLowerCase()}
          </span>
        )}
        <span className="num ml-auto">Số dư hôm nay {formatVND(data.series[0].p50)}</span>
      </div>
    </div>
  )
}
