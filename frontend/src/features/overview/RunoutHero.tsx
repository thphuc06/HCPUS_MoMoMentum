import type { CSSProperties } from 'react'
import { cn } from '@/lib/cn'
import { diffDays } from '@/lib/dates'

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

/** Dòng số lớn "12 ngày · hũ trống trước kỳ lương" (cảnh 1). Hiện sau dải ngày khi được phép chuyển động. */
export function RunoutHero({ days, animate = false }: { days: number; animate?: boolean }) {
  return (
    <p
      data-testid="runout-hero"
      className={cn('mt-2 flex items-baseline gap-2.5', animate && 'motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-1 fill-mode-both duration-300 ease-out')}
      style={animate ? ({ '--tw-animation-delay': '560ms' } as CSSProperties) : undefined}
    >
      <span className="num text-[40px] leading-[44px] font-extrabold tracking-[-0.02em] text-bad-fg">{days} ngày</span>{' '}
      <span className="text-body font-semibold text-ink">hũ trống trước kỳ lương</span>
    </p>
  )
}
