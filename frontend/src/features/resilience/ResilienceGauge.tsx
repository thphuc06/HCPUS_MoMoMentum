import type { ResilienceScoreData } from '@/contracts/blocks'

export const RESILIENCE_BANDS = {
  weak: { label: 'Yếu', color: 'text-bad-fg' },
  fair: { label: 'Vừa', color: 'text-warn-fg' },
  strong: { label: 'Tốt', color: 'text-ok-fg' },
} as const

const ARC = 'M 16 92 A 76 76 0 0 1 168 92'

export function ResilienceGauge({ score, band }: Pick<ResilienceScoreData, 'score' | 'band'>) {
  const { label, color } = RESILIENCE_BANDS[band]
  return (
    <svg
      role="img"
      aria-label={`Điểm chống chịu ${score}/100, nhóm ${label}`}
      viewBox="0 0 184 106"
      className="mx-auto w-full max-w-48"
    >
      <path d={ARC} fill="none" stroke="currentColor" strokeWidth="10" strokeLinecap="round" className="text-surface-2" />
      {score > 0 && (
        <path
          d={ARC}
          pathLength="100"
          fill="none"
          stroke="currentColor"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${score} 100`}
          className={color}
        />
      )}
      <text x="92" y="73" textAnchor="middle" className="num fill-ink text-section font-extrabold">{score}/100</text>
      <text x="92" y="94" textAnchor="middle" fill="currentColor" className={`text-small font-semibold ${color}`}>{label}</text>
    </svg>
  )
}
