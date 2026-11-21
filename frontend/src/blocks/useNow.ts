import { useEffect, useState } from 'react'

/** Giờ hiện tại, cập nhật mỗi `intervalMs` khi `active`. */
export function useNow(intervalMs: number, active = true): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    setNow(Date.now())
    const t = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(t)
  }, [intervalMs, active])
  return now
}
