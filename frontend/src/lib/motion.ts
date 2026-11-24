import { useEffect, useState, useSyncExternalStore } from 'react'

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
