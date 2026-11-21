import { useId } from 'react'
import { motion } from 'motion/react'

type Props = {
  /** 0..1: mức đầy so với kế hoạch tháng */
  level: number
  /** 0..1: "mực dự báo" tới ngày lương */
  forecast: number
  color: string
  size?: number
  label?: string
}

// Hũ thủy tinh tự vẽ SVG: thân hũ, mực nước (clipPath + sóng), vạch nét đứt "mực dự báo".
export function JarGlass({ level, forecast, color, size = 84, label }: Props) {
  const uid = useId().replace(/:/g, '')
  const top = 26 // y đỉnh thân hũ trong viewBox
  const bottom = 108
  const h = bottom - top
  const yWater = bottom - h * Math.max(0, Math.min(1, level))
  const yForecast = bottom - h * Math.max(0, Math.min(1, forecast))
  const body = 'M18 26 H82 C86 26 88 29 88 33 V96 C88 104 82 110 74 110 H26 C18 110 12 104 12 96 V33 C12 29 14 26 18 26 Z'
  const wave = (y: number) =>
    `M0 ${y} q 12.5 -5 25 0 t 25 0 t 25 0 t 25 0 V 120 H 0 Z`

  return (
    <svg
      viewBox="0 0 100 120"
      width={size}
      height={(size * 120) / 100}
      role="img"
      aria-label={label ?? `Hũ đầy ${Math.round(level * 100)}%, mực dự báo ${Math.round(forecast * 100)}%`}
      style={{ overflow: 'visible' }}
    >
      <defs>
        <clipPath id={`clip-${uid}`}>
          <path d={body} />
        </clipPath>
        <linearGradient id={`water-${uid}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.85" />
          <stop offset="1" stopColor={color} stopOpacity="0.55" />
        </linearGradient>
        <linearGradient id={`glass-${uid}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#fff" stopOpacity="0.3" />
          <stop offset="0.5" stopColor="#fff" stopOpacity="0.02" />
          <stop offset="1" stopColor="#fff" stopOpacity="0.14" />
        </linearGradient>
      </defs>
      {/* nắp hũ */}
      <rect x="22" y="12" width="56" height="12" rx="5" fill={color} opacity="0.9" />
      {/* thân hũ */}
      <path d={body} fill="var(--card)" stroke="var(--input)" strokeWidth="2" />
      <g clipPath={`url(#clip-${uid})`}>
        <motion.g
          initial={false}
          animate={{ y: yWater - top }}
          transition={{ type: 'spring', stiffness: 60, damping: 14 }}
        >
          <path d={wave(top)} fill={`url(#water-${uid})`} />
        </motion.g>
        <rect x="12" y="26" width="76" height="84" fill={`url(#glass-${uid})`} />
        {/* vạch mực dự báo */}
        <line x1="12" x2="88" y1={yForecast} y2={yForecast} stroke="var(--foreground)" strokeWidth="1.6" strokeDasharray="4 3" opacity="0.75" />
      </g>
      <path d={body} fill="none" stroke="var(--input)" strokeWidth="2" />
      <text x="92" y={yForecast + 3} fontSize="8.5" fontWeight="700" fill="var(--muted-foreground)">
        dự báo
      </text>
    </svg>
  )
}
