import { useEffect, useRef, useState } from 'react'

// Chuyển động gắn với dữ liệu (ui-design-review.md §4.6): chạy MỘT lần khi phần đó hiện lần đầu trong phiên (cờ trong
// sessionStorage), không chạy lại mỗi lần quay về tab; người dùng bật "giảm chuyển động" thì hiện thẳng trạng thái cuối.
// Chỉ đổi cách hiện số server trả, không tính số nghiệp vụ nào.

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)'
const KEY_PREFIX = 'yofina.motion.'

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.(REDUCED_MOTION).matches === true
}

function seen(key: string): boolean {
  try {
    return sessionStorage.getItem(KEY_PREFIX + key) === '1'
  } catch {
    return true
  }
}

/**
 * Đúng khi phần `key` nên chạy chuyển động vào: chưa hiện trong phiên này và người dùng không tắt chuyển động. Giá trị giữ
 * nguyên suốt đời component (đọc một lần lúc mount); cờ ghi trong effect nên lần mount sau trong cùng phiên sẽ là `false`.
 */
export function useAnimateOnce(key: string): boolean {
  const [animate] = useState(() => !prefersReducedMotion() && !seen(key))
  useEffect(() => {
    try {
      sessionStorage.setItem(KEY_PREFIX + key, '1')
    } catch {
      // sessionStorage bị chặn (chế độ riêng tư): bỏ qua, chỉ mất tính năng "một lần mỗi phiên".
    }
  }, [key])
  return animate
}

const easeOut = (t: number) => 1 - (1 - t) ** 3

/**
 * Số đếm từ 0 lên `to` trong `durationMs` khi `animate` đúng; ngược lại trả thẳng `to`. Đổi sang "giảm chuyển động" giữa
 * chừng thì nhảy tới số cuối. Đây là số để VẼ: nơi dùng phải đặt số cuối cho trình đọc màn hình và ẩn phần đang chạy.
 */
export function useCountUp(to: number, animate: boolean, durationMs = 800): number {
  const [value, setValue] = useState(() => (animate ? 0 : to))
  // Số đích của lần đếm đầu. Số đích đổi sau đó (tải lại sau một lần ghi) thì nhảy thẳng tới số mới, không đếm lại từ 0.
  const firstTarget = useRef<number | null>(null)

  useEffect(() => {
    if (firstTarget.current !== null && firstTarget.current !== to) {
      firstTarget.current = Number.NaN // từ giờ mọi số mới đều nhảy thẳng
      setValue(to)
      return
    }
    firstTarget.current = to
    if (!animate || prefersReducedMotion()) {
      setValue(to)
      return
    }
    let frame = 0
    let startedAt: number | undefined
    const tick = (now: number) => {
      startedAt ??= now
      const p = Math.min((now - startedAt) / durationMs, 1)
      setValue(p >= 1 ? to : Math.round(to * easeOut(p)))
      if (p < 1) frame = requestAnimationFrame(tick)
    }
    const preference = window.matchMedia?.(REDUCED_MOTION)
    const onChange = (e: MediaQueryListEvent) => {
      if (e.matches) {
        cancelAnimationFrame(frame)
        setValue(to)
      }
    }
    frame = requestAnimationFrame(tick)
    preference?.addEventListener?.('change', onChange)
    return () => {
      cancelAnimationFrame(frame)
      preference?.removeEventListener?.('change', onChange)
    }
  }, [to])

  return value
}

/**
 * Mức nước các hũ "dâng" khi mở: lần vẽ đầu là 0, rồi từng hũ lên mức thật, lệch `staggerMs` mỗi hũ (transition của
 * JarGlass lo phần chuyển động). Không chạy chuyển động thì trả thẳng mức thật.
 */
export function useRisingLevels(levels: number[], animate: boolean, staggerMs = 40): number[] {
  const [risen, setRisen] = useState(() => (animate ? 0 : Number.POSITIVE_INFINITY))

  useEffect(() => {
    if (!animate || risen >= levels.length) return
    // Khung hình đầu vẽ mức 0; sau đó mỗi `staggerMs` thêm một hũ lên mức thật.
    const t = setTimeout(() => setRisen((n) => n + 1), risen === 0 ? 16 : staggerMs)
    return () => clearTimeout(t)
  }, [animate, risen, levels.length, staggerMs])

  return levels.map((l, i) => (i < risen ? l : 0))
}
