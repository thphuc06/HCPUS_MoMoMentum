import { useEffect, useState } from 'react'
import { REDUCED_MOTION_QUERY } from '@/lib/motion'

const COUNTDOWN_DURATION_MS = 600

/**
 * Số chạy từ `from` tới `to` (lên hoặc xuống) trong `durationMs`, bắt đầu sau `delayMs`. Giảm chuyển động thì hiện thẳng số
 * cuối. Đây chỉ là phần nhìn: nơi dùng phải đặt số cuối (do server trả) vào chữ cho trình đọc màn hình.
 */
export function useCountdown(from: number, to: number, durationMs = COUNTDOWN_DURATION_MS, delayMs = 0) {
  const [value, setValue] = useState(() => window.matchMedia?.(REDUCED_MOTION_QUERY).matches ? to : from)

  useEffect(() => {
    const preference = window.matchMedia?.(REDUCED_MOTION_QUERY)
    if (preference?.matches || from === to) {
      setValue(to)
      return
    }

    let frame: number
    let startedAt: number | undefined
    function tick(now: number) {
      startedAt ??= now
      const progress = Math.min(Math.max(now - startedAt - delayMs, 0) / durationMs, 1)
      setValue(Math.round(from + (to - from) * progress))
      if (progress < 1) frame = requestAnimationFrame(tick)
    }

    function onPreferenceChange(event: MediaQueryListEvent) {
      if (event.matches) {
        cancelAnimationFrame(frame)
        setValue(to)
      }
    }

    frame = requestAnimationFrame(tick)
    preference?.addEventListener?.('change', onPreferenceChange)
    return () => {
      cancelAnimationFrame(frame)
      preference?.removeEventListener?.('change', onPreferenceChange)
    }
  }, [from, to, durationMs, delayMs])

  return value
}

export function AnimatedNumber({ from, to, durationMs }: { from: number; to: number; durationMs?: number }) {
  return <span>{useCountdown(from, to, durationMs)}</span>
}
