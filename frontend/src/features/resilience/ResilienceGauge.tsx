import { useEffect, useState } from 'react'
import type { ResilienceBand, ResilienceScoreData } from '@/contracts/blocks'
import { useCountdown } from './AnimatedNumber'

export const RESILIENCE_BANDS = {
  weak: { label: 'Yếu', color: 'text-bad-fg' },
  fair: { label: 'Vừa', color: 'text-warn-fg' },
  strong: { label: 'Tốt', color: 'text-ok-fg' },
} as const

const ARC = 'M 16 92 A 76 76 0 0 1 168 92'
/** Thời gian cung chạy từ điểm trước tới điểm sau (cảnh 3); số giữa cung đếm cùng nhịp. */
export const GAUGE_MS = 800

type Props = Pick<ResilienceScoreData, 'score' | 'band'> & {
  /** Điểm và nhóm trước cú sốc: có thì cung và số chạy từ đây tới `score` (khi `animate`). */
  from?: number
  fromBand?: ResilienceBand
  /** Nơi dùng đã xét giảm chuyển động và "chỉ một lần"; false thì vẽ thẳng trạng thái cuối. */
  animate?: boolean
}

/** Phần cung đã tô (0 đến 100) theo `pathLength` 100: dashoffset = 100 − điểm. Chỉ đổi stroke-dashoffset và màu. */
function Arc({ value, color, moving }: { value: number; color: string; moving: boolean }) {
  return (
    <path
      d={ARC}
      pathLength="100"
      fill="none"
      stroke="currentColor"
      strokeWidth="10"
      strokeLinecap="round"
      strokeDasharray="100 100"
      strokeDashoffset={100 - value}
      // Điểm 0 thì đầu bo tròn vẫn vẽ một chấm: ẩn hẳn.
      opacity={value > 0 ? 1 : 0}
      className={color}
      style={moving ? { transition: `stroke-dashoffset ${GAUGE_MS}ms var(--ease-out), color ${GAUGE_MS}ms var(--ease-out)` } : undefined}
      data-testid="gauge-arc"
    />
  )
}

export function ResilienceGauge({ score, band, from, fromBand, animate = false }: Props) {
  const { label, color } = RESILIENCE_BANDS[band]
  const moving = animate && from !== undefined && from !== score
  // Lần vẽ đầu ở điểm trước, frame kế tiếp đặt điểm sau để CSS transition chạy cung.
  const [arcAt, setArcAt] = useState(moving ? from : score)
  useEffect(() => {
    if (!moving) {
      setArcAt(score)
      return
    }
    const frame = requestAnimationFrame(() => setArcAt(score))
    return () => cancelAnimationFrame(frame)
  }, [moving, score])
  const shown = useCountdown(moving ? from : score, score, GAUGE_MS)
  const arcColor = moving && arcAt !== score && fromBand ? RESILIENCE_BANDS[fromBand].color : color
  const before = from !== undefined && fromBand ? `, trước cú sốc ${from}/100 nhóm ${RESILIENCE_BANDS[fromBand].label}` : ''

  return (
    <svg
      role="img"
      aria-label={`Điểm chống chịu ${score}/100, nhóm ${label}${before}`}
      viewBox="0 0 184 106"
      className="mx-auto w-full max-w-48"
      data-animate={moving ? 'score' : undefined}
    >
      <path d={ARC} fill="none" stroke="currentColor" strokeWidth="10" strokeLinecap="round" className="text-surface-2" />
      {from !== undefined && from !== score && (
        // Vạch mốc điểm trước: thấy cung đã tụt bao nhiêu kể cả khi không có chuyển động.
        <path
          d={ARC}
          pathLength="100"
          fill="none"
          stroke="currentColor"
          strokeWidth="14"
          strokeDasharray={`0.6 ${100}`}
          strokeDashoffset={-(from - 0.3)}
          className="text-line-strong"
          data-testid="gauge-from-mark"
        />
      )}
      <Arc value={arcAt} color={arcColor} moving={moving} />
      <text x="92" y="73" textAnchor="middle" className="num fill-ink text-section font-extrabold">{`${shown}/100`}</text>
      <text x="92" y="94" textAnchor="middle" fill="currentColor" className={`text-small font-semibold ${color}`}>{label}</text>
    </svg>
  )
}
