import { useId } from 'react'
import { motion } from 'motion/react'
import NumberFlow from '@number-flow/react'

type Parts = { save: number; spend: number; borrow: number; plan: number }

const PARTS: { key: keyof Parts; label: string; en: string }[] = [
  { key: 'save', label: 'Tiết kiệm', en: 'Save' },
  { key: 'spend', label: 'Chi tiêu', en: 'Spend' },
  { key: 'borrow', label: 'Vay nợ', en: 'Borrow' },
  { key: 'plan', label: 'Kế hoạch', en: 'Plan' },
]

function label(score: number) {
  if (score >= 75) return 'Vững vàng'
  if (score >= 55) return 'Tạm ổn'
  return 'Cần củng cố'
}

// Cung nửa vòng 0..100 tự vẽ SVG + bốn thanh thành phần (HTML/CSS).
export function ResilienceGauge({ score, parts }: { score: number; parts: Parts }) {
  const uid = useId().replace(/:/g, '')
  const R = 78
  const cx = 100
  const cy = 100
  const arc = Math.PI * R // chiều dài nửa vòng
  const pt = (t: number) => {
    const a = Math.PI * (1 - t)
    return [cx + R * Math.cos(a), cy - R * Math.sin(a)]
  }
  const seg = (t0: number, t1: number) => {
    const [x0, y0] = pt(t0)
    const [x1, y1] = pt(t1)
    return `M ${x0} ${y0} A ${R} ${R} 0 0 1 ${x1} ${y1}`
  }
  const full = seg(0, 1)
  const t = Math.max(0, Math.min(1, score / 100))
  const [kx, ky] = pt(t)

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-full max-w-[260px]">
        <svg viewBox="0 0 200 124" className="w-full" role="img" aria-label={`Điểm chống chịu ${score} trên 100, ${label(score)}`}>
          <defs>
            <linearGradient id={`g-${uid}`} x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="var(--short)" stopOpacity="0.75" />
              <stop offset="0.5" stopColor="var(--warn)" />
              <stop offset="1" stopColor="var(--ok)" />
            </linearGradient>
          </defs>
          {/* ba vùng nền nhạt, không tô đỏ chói */}
          <path d={full} fill="none" stroke="var(--muted)" strokeWidth="14" strokeLinecap="round" />
          <motion.path
            d={full}
            fill="none"
            stroke={`url(#g-${uid})`}
            strokeWidth="14"
            strokeLinecap="round"
            strokeDasharray={arc}
            initial={{ strokeDashoffset: arc }}
            animate={{ strokeDashoffset: arc * (1 - t) }}
            transition={{ duration: 1, ease: [0.32, 0.72, 0, 1] }}
          />
          <motion.circle
            r="9"
            fill="var(--card)"
            stroke="var(--foreground)"
            strokeWidth="3"
            initial={{ cx: pt(0)[0], cy: pt(0)[1] }}
            animate={{ cx: kx, cy: ky }}
            transition={{ duration: 1, ease: [0.32, 0.72, 0, 1] }}
          />
          <text x="22" y="121" fontSize="10" fill="var(--muted-foreground)" textAnchor="middle">0</text>
          <text x="178" y="121" fontSize="10" fill="var(--muted-foreground)" textAnchor="middle">100</text>
        </svg>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-col items-center leading-none">
          <NumberFlow value={score} className="num text-[40px] font-extrabold tracking-tight" />
          <span className="mt-1 text-[13px] font-semibold text-muted-foreground">{label(score)}</span>
        </div>
      </div>
      <ul className="mt-4 grid w-full grid-cols-2 gap-x-4 gap-y-3">
        {PARTS.map((p) => (
          <li key={p.key}>
            <div className="flex items-baseline justify-between text-[12.5px]">
              <span className="font-semibold">{p.label}</span>
              <span className="num text-muted-foreground">{parts[p.key]}</span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
              <motion.div
                className="h-full rounded-full bg-primary"
                initial={{ width: 0 }}
                animate={{ width: `${parts[p.key]}%` }}
                transition={{ duration: 0.8, ease: [0.32, 0.72, 0, 1] }}
              />
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-center text-[11.5px] text-muted-foreground">Điểm này không phải điểm tín dụng.</p>
    </div>
  )
}
