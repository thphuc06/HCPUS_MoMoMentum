import type { CSSProperties } from 'react'
import { cn } from '@/lib/cn'
import { diffDays } from '@/lib/dates'
import { formatShortfallChance } from '@/lib/format'

/**
 * Số ngày hũ trống trước kỳ lương của thẻ cảnh báo cạn: hiệu hai ngày server trả (`runout_date` của hũ và `next_payday.date`),
 * giống cách ForecastBlock tính khoảng trống. Không cạn trước kỳ lương thì không có số (null).
 */
export function emptyDaysBeforePayday(runoutDate: string | undefined, paydayDate: string | undefined, today: string): number | null {
  if (!runoutDate || !paydayDate) return null
  const from = diffDays(today, runoutDate) < 0 ? today : runoutDate
  const n = diffDays(from, paydayDate)
  return n > 0 ? n : null
}

/**
 * Số lớn của thẻ cảnh báo cạn (cảnh 1): "12 ngày · hũ trống trước kỳ lương", hiện sau dải ngày khi được phép chuyển động. Hũ thưa
 * (#25, server không nêu ngày cạn) không có số ngày: một dòng "Khả năng hụt 60%" (cùng chữ với Nhìn trước); tiêu đề thẻ của server đã
 * nói "có thể cạn trước ngày lương" nên dòng này không nhắc lại.
 */
export function RunoutHero(props: ({ days: number; chance?: undefined } | { chance: number; days?: undefined }) & { animate?: boolean }) {
  const { animate = false } = props
  const motion = animate ? 'motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 fill-mode-both duration-300 ease-out' : undefined
  const style = animate ? ({ '--tw-animation-delay': '560ms' } as CSSProperties) : undefined
  if (props.days === undefined) {
    return (
      <p data-testid="runout-hero" className={cn('mt-2 text-body font-semibold text-bad-fg', motion)} style={style}>
        Khả năng hụt {formatShortfallChance(props.chance).toLowerCase()}
      </p>
    )
  }
  return (
    <p data-testid="runout-hero" className={cn('mt-2 flex items-baseline gap-2.5', motion)} style={style}>
      <span className="num shrink-0 whitespace-nowrap text-[40px] leading-[44px] font-extrabold tracking-[-0.02em] text-bad-fg">{props.days} ngày</span>{' '}
      <span className="min-w-0 text-body font-semibold text-ink">hũ trống trước kỳ lương</span>
    </p>
  )
}
