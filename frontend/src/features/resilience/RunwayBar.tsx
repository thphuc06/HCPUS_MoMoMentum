import type { CSSProperties } from 'react'
import type { JarStatus } from '@/contracts/blocks'
import { useCountdown } from './AnimatedNumber'

const LINE: Record<JarStatus, string> = {
  ok: 'var(--status-ok-line)',
  tight: 'var(--status-warn-line)',
  short: 'var(--status-bad-line)',
}

/** Thanh và số chạy sau cung điểm một nhịp, cả chuỗi dưới 1,2 giây (ui-design-review.md §4.6). */
export const RUNWAY_DELAY_MS = 300
export const RUNWAY_MS = 800

/**
 * "Trụ được N ngày" so với khoảng mô phỏng (cảnh 3): số lớn đếm lên, thanh dài theo `days / horizonDays`, phần còn lại của
 * khoảng mô phỏng gạch chéo màu hụt khi ví cạn trước hết khoảng. `days` vắng nghĩa là trụ hết khoảng (số của server).
 */
export function RunwayBar({ days, horizonDays, status, animate }: { days?: number; horizonDays: number; status: JarStatus; animate: boolean }) {
  const full = days === undefined
  const value = full ? horizonDays : Math.min(days, horizonDays)
  const pct = horizonDays > 0 ? (value / horizonDays) * 100 : 0
  const shown = useCountdown(animate ? 0 : value, value, RUNWAY_MS, RUNWAY_DELAY_MS)
  const text = full ? `Trụ hết ${horizonDays} ngày dự báo` : `Trụ được ${days} ngày`
  const motion: CSSProperties = { ['--motion-delay' as string]: `${RUNWAY_DELAY_MS}ms` }

  return (
    <div data-testid="runway" className="space-y-2">
      <p className="text-small font-semibold text-ink-2">Toàn bộ ví</p>
      <p className="sr-only">{text}</p>
      <p aria-hidden className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-subtitle font-semibold text-ink">{full ? 'Trụ hết' : 'Trụ được'}</span>
        <span className="num text-[40px] leading-[44px] font-extrabold tracking-[-0.02em] text-ink" data-testid="runway-count">{shown}</span>
        <span className="text-subtitle font-semibold text-ink">{full ? 'ngày dự báo' : 'ngày'}</span>
      </p>
      <div role="img" aria-label={`Thanh số ngày trụ được: ${value} trên ${horizonDays} ngày mô phỏng`}>
        <div className="relative h-3.5 overflow-hidden rounded-full bg-surface-2 ring-1 ring-line-strong ring-inset">
          {!full && pct < 100 && (
            // Phần khoảng mô phỏng sau ngày cạn: gạch chéo như vùng hụt của biểu đồ dự báo (không chỉ dựa vào màu).
            <div
              aria-hidden
              data-testid="runway-gap"
              className="absolute inset-y-0 right-0"
              style={{
                left: `${pct}%`,
                background: 'repeating-linear-gradient(135deg, var(--status-bad-bg) 0 4px, color-mix(in srgb, var(--status-bad-line) 45%, transparent) 4px 6px)',
              }}
            />
          )}
          <div
            data-testid="runway-fill"
            className={`relative h-full rounded-full ${animate ? 'motion-grow-x' : ''}`}
            style={{ width: `${pct}%`, background: LINE[status], ...(animate ? motion : {}) }}
          />
        </div>
        <div aria-hidden className="mt-1 flex justify-between text-note text-ink-2">
          <span>Hôm nay</span>
          <span className="num">{horizonDays} ngày mô phỏng</span>
        </div>
      </div>
    </div>
  )
}
