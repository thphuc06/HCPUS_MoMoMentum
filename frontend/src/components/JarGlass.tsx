import { useId } from 'react'
import { jarColor } from './jarTheme'

// Hũ thủy tinh vẽ SVG theo Figma JarCard/JarGlyph (7:130): nắp theo màu hũ, thân kính bo 20, mực nước,
// vệt sáng. `level` là mức nước 0..1. `forecastLevel` (tùy chọn, 0..1) là vạch đứt "dự báo": mức mà dự báo cho thấy
// hũ sẽ xuống tới; không truyền thì không vẽ vạch (không có số dự báo thì không bịa vạch).
const W = 148
const H = 112
const GLASS = { x: 24, y: 16, w: 76, h: 92, r: 20 }

export function JarGlass({
  colorKey,
  level,
  label,
  forecastLevel,
}: {
  colorKey: string
  level: number
  label: string
  forecastLevel?: number | null
}) {
  const uid = useId().replace(/:/g, '')
  const color = jarColor(colorKey)
  const clamped = Math.max(0, Math.min(1, level))
  const waterH = GLASS.h * clamped
  const shift = GLASS.h - waterH // dịch nước xuống: 0 là đầy, GLASS.h là cạn
  const fl = forecastLevel === null || forecastLevel === undefined ? null : Math.max(0, Math.min(1, forecastLevel))
  const flY = fl === null ? 0 : GLASS.y + GLASS.h * (1 - fl)

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={label} className="mx-auto block max-w-full">
      <defs>
        <clipPath id={`glass-${uid}`}>
          <rect x={GLASS.x} y={GLASS.y} width={GLASS.w} height={GLASS.h} rx={GLASS.r} />
        </clipPath>
      </defs>
      {/* nắp */}
      <rect x={38} y={0} width={48} height={12} rx={5} fill={color} />
      {/* kính */}
      <rect x={GLASS.x} y={GLASS.y} width={GLASS.w} height={GLASS.h} rx={GLASS.r} fill="var(--bg-surface-2)" />
      <g clipPath={`url(#glass-${uid})`}>
        <g style={{ transform: `translateY(${shift}px)`, transition: 'transform 700ms cubic-bezier(0.22, 1, 0.36, 1)' }}>
          {clamped > 0 && (
            <>
              <rect x={GLASS.x} y={GLASS.y} width={GLASS.w} height={GLASS.h} fill={color} opacity={0.88} />
              <rect x={GLASS.x} y={GLASS.y - 5} width={GLASS.w} height={10} rx={5} fill={color} opacity={0.55} />
            </>
          )}
        </g>
        <rect x={GLASS.x + 6} y={GLASS.y + 10} width={6} height={46} rx={3} fill="#fff" opacity={0.7} />
      </g>
      <rect x={GLASS.x} y={GLASS.y} width={GLASS.w} height={GLASS.h} rx={GLASS.r} fill="none" stroke="var(--border-default)" strokeWidth={2} />
      {fl !== null && (
        <g data-testid="forecast-mark">
          <line x1={GLASS.x + 4} x2={GLASS.x + GLASS.w + 6} y1={flY} y2={flY} stroke="var(--text-primary)" strokeWidth={1.5} strokeDasharray="4 3" />
          <text x={GLASS.x + GLASS.w + 9} y={flY + 4} fontSize={11} fontWeight={600} fill="var(--text-secondary)">
            dự báo
          </text>
        </g>
      )}
    </svg>
  )
}
