import { useEffect, useState } from 'react'

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)'
const COUNTDOWN_DURATION_MS = 600

function useCountdown(from: number, to: number) {
  const [value, setValue] = useState(() => window.matchMedia?.(REDUCED_MOTION).matches ? to : from)

  useEffect(() => {
    const preference = window.matchMedia?.(REDUCED_MOTION)
    if (preference?.matches || from === to) {
      setValue(to)
      return
    }

    let frame: number
    let startedAt: number | undefined
    function tick(now: number) {
      startedAt ??= now
      const progress = Math.min((now - startedAt) / COUNTDOWN_DURATION_MS, 1)
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
    preference?.addEventListener('change', onPreferenceChange)
    return () => {
      cancelAnimationFrame(frame)
      preference?.removeEventListener('change', onPreferenceChange)
    }
  }, [from, to])

  return value
}

export function AnimatedNumber({ from, to }: { from: number; to: number }) {
  return <span>{useCountdown(from, to)}</span>
}
