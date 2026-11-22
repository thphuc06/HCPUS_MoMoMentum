import { useId, useMemo } from 'react'
import { Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceDot, ReferenceLine, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { formatDayMonth, formatVndAxis } from '@/lib/format'
import type { ForecastTimelineData } from '@/contracts/blocks'
import { buildChartModel, xToLabel, type ChartModel } from './model'

// Biểu đồ dự báo 30 ngày (Recharts 3): dải P10–P90, đường P50 màu accent/blue, mốc nghĩa vụ và lương, điểm cạn, vùng
// hụt gạch chéo. Tách chunk riêng (tải lười ở ForecastBlock) vì Recharts nặng. Cách dựng theo spike-frontend-stack §2.
// Chạm hoặc rê lên biểu đồ chọn một ngày (cha vẽ dòng đọc số); `activeX` là ngày đang chọn.

const HALO = { paintOrder: 'stroke', stroke: 'var(--bg-surface)', strokeWidth: 3, strokeLinejoin: 'round' } as const
const TICK = { fontSize: 11, fill: 'var(--text-secondary)' } as const

export type ForecastChartProps = {
  data: ForecastTimelineData
  activeX: number | null
  onActiveChange: (x: number | null) => void
  height?: number
  /** Chỉ cho test: vẽ với kích thước cố định thay vì đo khung (jsdom không có kích thước). */
  fixedSize?: { width: number; height: number }
  model?: ChartModel
}

export default function ForecastChart({ data, activeX, onActiveChange, height = 240, fixedSize, model }: ForecastChartProps) {
  const uid = useId().replace(/:/g, '')
  const m = useMemo(() => model ?? buildChartModel(data), [model, data])
  const hatchId = `hatch-${uid}`

  const pick = (s: { activeTooltipIndex?: unknown }) => {
    const i = typeof s.activeTooltipIndex === 'number' ? s.activeTooltipIndex : Number(s.activeTooltipIndex)
    const row = Number.isFinite(i) ? m.rows[i] : undefined
    onActiveChange(row ? row.x : null)
  }

  const chart = (
    <ComposedChart
      data={m.rows}
      margin={{ top: 28 + Math.max(0, ...m.eventLevels) * 13, right: 18, bottom: 0, left: 0 }}
      {...(fixedSize ? { width: fixedSize.width, height: fixedSize.height } : {})}
      onMouseMove={pick}
      onClick={pick}
      onTouchMove={pick}
      onMouseLeave={() => onActiveChange(null)}
    >
      <defs>
        <pattern id={hatchId} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="7" height="7" fill="var(--status-bad-bg)" />
          <line x1="0" y1="0" x2="0" y2="7" stroke="var(--status-bad-line)" strokeWidth="1.6" strokeOpacity="0.5" />
        </pattern>
      </defs>
      <CartesianGrid vertical={false} stroke="var(--border-default)" strokeDasharray="3 4" />
      <XAxis
        dataKey="x"
        type="number"
        domain={[0, m.lastX]}
        ticks={m.xTicks}
        tickFormatter={(x: number) => xToLabel(data.origin_date, x)}
        tick={TICK}
        tickLine={false}
        axisLine={false}
        tickMargin={6}
        interval={0}
      />
      <YAxis domain={[m.yMin, m.yMax]} ticks={m.yTicks} tickFormatter={(v: number) => formatVndAxis(v)} tick={TICK} tickLine={false} axisLine={false} width={46} />

      {m.shortfallRange && (
        <ReferenceArea x1={m.shortfallRange.x1} x2={m.shortfallRange.x2} y1={m.yMin} y2={0} fill={`url(#${hatchId})`} fillOpacity={1} stroke="none" ifOverflow="hidden" />
      )}

      <Area type="monotone" dataKey="band" stroke="none" fill="var(--accent-blue)" fillOpacity={0.18} isAnimationActive={false} activeDot={false} name="Dải 80%" />
      {m.hasCompare && (
        // Dải chênh lệch giữa TRƯỚC và SAU (màu thương hiệu): thấy ngay kịch bản kéo số dư xuống bao nhiêu.
        <Area type="monotone" dataKey="gap" stroke="none" fill="var(--brand-primary)" fillOpacity={0.22} isAnimationActive={false} activeDot={false} name="Chênh lệch" />
      )}
      <Line
        type="monotone"
        dataKey="p50"
        stroke="var(--accent-blue)"
        strokeWidth={2.5}
        strokeDasharray={m.hasCompare ? '6 4' : undefined}
        dot={false}
        activeDot={false}
        isAnimationActive={false}
        name={m.hasCompare ? 'Trước' : 'Số dư giữa'}
      />
      {m.hasCompare && (
        <Line type="monotone" dataKey="after" stroke="var(--brand-primary)" strokeWidth={2.5} dot={false} activeDot={false} isAnimationActive={false} name="Sau" />
      )}
      <ReferenceLine y={0} stroke="var(--text-secondary)" strokeOpacity={0.6} />

      {m.events.map((e, i) => (
        <ReferenceLine
          key={`${e.date}-${e.label}`}
          x={e.x}
          stroke={e.kind === 'salary' ? 'var(--status-ok-line)' : 'var(--status-warn-line)'}
          strokeWidth={1.5}
          strokeDasharray={e.kind === 'salary' ? '4 3' : '2 3'}
          label={{
            value: `${e.label} ${formatDayMonth(e.date)}`,
            position: 'top',
            // Mốc gần nhau xếp lên các tầng khác nhau để nhãn không chồng lên nhau.
            offset: 4 + (m.eventLevels[i] ?? 0) * 13,
            fontSize: 10.5,
            fontWeight: 700,
            fill: e.kind === 'salary' ? 'var(--status-ok-fg)' : 'var(--status-warn-fg)',
            style: HALO,
          }}
        />
      ))}

      {m.runout && (
        <ReferenceDot
          x={m.runout.x}
          y={0}
          r={5.5}
          fill="var(--status-bad-line)"
          stroke="var(--bg-surface)"
          strokeWidth={2}
          label={{ value: `Cạn ${formatDayMonth(m.runout.date)}`, position: 'bottom', fontSize: 11, fontWeight: 700, fill: 'var(--status-bad-fg)', dy: 4, style: HALO }}
        />
      )}

      {m.afterRunout && (
        <ReferenceDot
          x={m.afterRunout.x}
          y={0}
          r={5.5}
          fill="var(--brand-primary)"
          stroke="var(--bg-surface)"
          strokeWidth={2}
          label={{ value: `Sau: cạn ${formatDayMonth(m.afterRunout.date)}`, position: 'bottom', fontSize: 11, fontWeight: 700, fill: 'var(--text-brand)', dy: 18, style: HALO }}
        />
      )}

      {activeX !== null && <ReferenceLine x={activeX} stroke="var(--text-primary)" strokeOpacity={0.55} strokeWidth={1} />}
    </ComposedChart>
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
