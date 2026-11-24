import { CartesianGrid, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { formatVndAxis, formatVndShort } from '@/lib/format'
import type { TrendRow } from './model'

// B5 "So với kỳ trước" (spending-visualization.md §3): hai đường lũy kế theo ngày của kỳ lương (ngày 1 là ngày lương). Kỳ này nét
// liền màu thương hiệu, kỳ trước nét đứt xám kéo hết kỳ: khác nhau cả nét lẫn màu. Tách chunk riêng (tải lười ở SpendingTrend), cùng
// Recharts với ForecastChart nên Vite gom chung phần thư viện. Chạm hoặc rê chọn một ngày (cha vẽ dòng đọc số).

const TICK = { fontSize: 12, fill: 'var(--text-secondary)' } as const
const HALO = { paintOrder: 'stroke', stroke: 'var(--bg-surface)', strokeWidth: 3, strokeLinejoin: 'round' } as const

export type SpendingTrendChartProps = {
  rows: TrendRow[]
  today: number
  activeDay: number | null
  onActiveChange: (day: number | null) => void
  /** Vẽ dần đường kỳ này (nơi dùng đã xét giảm chuyển động và chỉ bật một lần mỗi phiên). */
  animate?: boolean
  height?: number
  /** Chỉ cho test: kích thước cố định (jsdom không đo được khung). */
  fixedSize?: { width: number; height: number }
}

function dayTicks(last: number): number[] {
  const out = [1]
  for (let d = 8; d < last - 2; d += 7) out.push(d)
  if (last > 1) out.push(last)
  return out
}

export default function SpendingTrendChart({ rows, today, activeDay, onActiveChange, animate = false, height = 200, fixedSize }: SpendingTrendChartProps) {
  const last = rows.length
  const max = Math.max(0, ...rows.map((r) => Math.max(r.current ?? 0, r.previous ?? 0)))
  const end = rows.find((r) => r.day === today)
  const pick = (s: { activeTooltipIndex?: unknown }) => {
    const i = typeof s.activeTooltipIndex === 'number' ? s.activeTooltipIndex : Number(s.activeTooltipIndex)
    const row = Number.isFinite(i) ? rows[i] : undefined
    onActiveChange(row ? row.day : null)
  }
  const draw = animate
    ? ({ isAnimationActive: true, animationBegin: 0, animationDuration: 700, animationEasing: 'ease-out' } as const)
    : ({ isAnimationActive: false } as const)

  const chart = (
    <LineChart
      data={rows}
      margin={{ top: 22, right: 18, bottom: 0, left: 0 }}
      {...(fixedSize ? { width: fixedSize.width, height: fixedSize.height } : {})}
      onMouseMove={pick}
      onClick={pick}
      onTouchMove={pick}
      onMouseLeave={() => onActiveChange(null)}
    >
      <CartesianGrid vertical={false} stroke="var(--border-default)" strokeDasharray="3 4" />
      <XAxis
        dataKey="day"
        type="number"
        domain={[1, last]}
        ticks={dayTicks(last)}
        tickFormatter={(d: number) => String(d)}
        tick={TICK}
        tickLine={false}
        axisLine={false}
        tickMargin={6}
        interval={0}
      />
      <YAxis domain={[0, max > 0 ? 'auto' : 1]} tickFormatter={(v: number) => formatVndAxis(v)} tick={TICK} tickLine={false} axisLine={false} width={50} />
      <Line type="monotone" dataKey="previous" stroke="var(--text-secondary)" strokeWidth={2} strokeDasharray="6 4" dot={false} activeDot={false} isAnimationActive={false} connectNulls={false} name="Kỳ trước" />
      <Line type="monotone" dataKey="current" stroke="var(--brand-primary)" strokeWidth={2.5} dot={false} activeDot={false} connectNulls={false} name="Kỳ này" {...draw} />
      {end?.current !== undefined && (
        <ReferenceDot
          x={today}
          y={end.current}
          r={5}
          fill="var(--brand-primary)"
          stroke="var(--bg-surface)"
          strokeWidth={2}
          label={{ value: formatVndShort(end.current), position: 'top', fontSize: 12, fontWeight: 700, fill: 'var(--text-brand)', style: HALO }}
          className={animate ? 'motion-pop [--motion-delay:700ms]' : undefined}
        />
      )}
      {activeDay !== null && <ReferenceLine x={activeDay} stroke="var(--text-primary)" strokeOpacity={0.55} strokeWidth={1} />}
    </LineChart>
  )

  if (fixedSize) return <div style={{ width: fixedSize.width, height: fixedSize.height }}>{chart}</div>
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0}>
        {chart}
      </ResponsiveContainer>
    </div>
  )
}
