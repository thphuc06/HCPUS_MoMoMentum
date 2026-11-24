import { useEffect, useRef, useState, useSyncExternalStore } from 'react'

// Chuyển động gắn với dữ liệu (ui-design-review.md §4.6): tôn trọng `prefers-reduced-motion` và chỉ chạy một lần mỗi phiên
// cho cùng một khối, để quay lại màn cũ hay mở lại chat không phát lại hiệu ứng.

export const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

function query(): MediaQueryList | undefined {
  return typeof window === 'undefined' ? undefined : window.matchMedia?.(REDUCED_MOTION_QUERY)
}

export function prefersReducedMotion(): boolean {
  return !!query()?.matches
}

function subscribe(onChange: () => void) {
  const q = query()
  q?.addEventListener?.('change', onChange)
  return () => q?.removeEventListener?.('change', onChange)
}

/** true khi người dùng bật giảm chuyển động; đổi theo cài đặt máy mà không cần tải lại. */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, prefersReducedMotion, () => false)
}

const SEEN_PREFIX = 'yf-motion:'

function seen(key: string): boolean {
  try {
    return window.sessionStorage.getItem(SEEN_PREFIX + key) !== null
  } catch {
    return false
  }
}

/**
 * true nếu được phép chạy chuyển động cho khối `key` lần này: chưa thấy trong phiên và người dùng không giảm chuyển động.
 * Đọc cờ lúc mount (thuần), ghi cờ trong effect. `key` rỗng thì chỉ xét giảm chuyển động.
 */
export function useEntranceMotion(key?: string): boolean {
  const reduced = usePrefersReducedMotion()
  const [fresh] = useState(() => !key || !seen(key))
  useEffect(() => {
    if (!key) return
    try {
      window.sessionStorage.setItem(SEEN_PREFIX + key, '1')
    } catch {
      // Safari riêng tư hoặc bộ nhớ đầy: chỉ mất cờ "đã xem", không ảnh hưởng gì khác.
    }
  }, [key])
  return fresh && !reduced
}

// Các hook của Tổng quan (ui-b): cờ riêng; sessionStorage bị chặn thì coi như đã xem (không chạy).
const ONCE_PREFIX = 'yofina.motion.'

function seenOnce(key: string): boolean {
  try {
    return sessionStorage.getItem(ONCE_PREFIX + key) === '1'
  } catch {
    return true
  }
}

/**
 * Đúng khi phần `key` nên chạy chuyển động vào: chưa hiện trong phiên này và người dùng không tắt chuyển động. Giá trị giữ
 * nguyên suốt đời component (đọc một lần lúc mount); cờ ghi trong effect nên lần mount sau trong cùng phiên sẽ là `false`.
 */
export function useAnimateOnce(key: string): boolean {
  const [animate] = useState(() => !prefersReducedMotion() && !seenOnce(key))
  useEffect(() => {
    try {
      sessionStorage.setItem(ONCE_PREFIX + key, '1')
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
    const preference = window.matchMedia?.(REDUCED_MOTION_QUERY)
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
