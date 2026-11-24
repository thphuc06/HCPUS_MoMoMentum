import { act, render, renderHook, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MiniTimeline } from '@/components/MiniTimeline'
import { emptyDaysBeforePayday } from '@/features/overview/RunoutHero'
import { useAnimateOnce, useCountUp, useRisingLevels } from './motion'

// Chuyển động gắn với dữ liệu: một lần mỗi phiên, tôn trọng "giảm chuyển động", số cuối luôn là số server trả.

const reduceMotion = (on: boolean) =>
  vi.stubGlobal('matchMedia', vi.fn((q: string) => ({ matches: on && q === '(prefers-reduced-motion: reduce)', addEventListener: vi.fn(), removeEventListener: vi.fn() })))

beforeEach(() => sessionStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('useAnimateOnce', () => {
  it('lần đầu trong phiên thì chạy, lần mount sau thì không', () => {
    expect(renderHook(() => useAnimateOnce('k')).result.current).toBe(true)
    expect(renderHook(() => useAnimateOnce('k')).result.current).toBe(false)
    expect(renderHook(() => useAnimateOnce('khac')).result.current).toBe(true)
  })

  it('giảm chuyển động: không chạy', () => {
    reduceMotion(true)
    expect(renderHook(() => useAnimateOnce('k')).result.current).toBe(false)
  })
})

describe('useCountUp', () => {
  it('không chạy chuyển động: trả thẳng số cuối', () => {
    expect(renderHook(() => useCountUp(7_900_000, false)).result.current).toBe(7_900_000)
  })

  it('đếm từ 0 lên đúng số cuối; số đích đổi sau đó thì nhảy thẳng', async () => {
    vi.useFakeTimers({ toFake: ['requestAnimationFrame', 'cancelAnimationFrame', 'performance'] })
    const { result, rerender } = renderHook(({ to }) => useCountUp(to, true, 800), { initialProps: { to: 1_000_000 } })
    expect(result.current).toBe(0)
    await act(async () => { vi.advanceTimersByTime(400) })
    expect(result.current).toBeGreaterThan(0)
    expect(result.current).toBeLessThan(1_000_000)
    await act(async () => { vi.advanceTimersByTime(600) })
    expect(result.current).toBe(1_000_000)
    rerender({ to: 1_250_000 })
    expect(result.current).toBe(1_250_000)
  })

  it('giảm chuyển động: số cuối ngay', () => {
    reduceMotion(true)
    expect(renderHook(() => useCountUp(500_000, true)).result.current).toBe(500_000)
  })
})

describe('useRisingLevels', () => {
  it('lần vẽ đầu mọi hũ ở đáy, rồi từng hũ lên mức thật lệch nhịp', () => {
    vi.useFakeTimers()
    const { result } = renderHook(() => useRisingLevels([0.5, 0.8, 0.2], true, 40))
    expect(result.current).toEqual([0, 0, 0])
    act(() => { vi.advanceTimersByTime(16) })
    expect(result.current).toEqual([0.5, 0, 0])
    act(() => { vi.advanceTimersByTime(40) })
    expect(result.current).toEqual([0.5, 0.8, 0])
    act(() => { vi.advanceTimersByTime(40) })
    expect(result.current).toEqual([0.5, 0.8, 0.2])
  })

  it('không chạy chuyển động: mức thật ngay', () => {
    expect(renderHook(() => useRisingLevels([0.5, 0.8], false)).result.current).toEqual([0.5, 0.8])
  })
})

describe('MiniTimeline (dải ô ngày tới kỳ lương)', () => {
  const kinds = () => [...screen.getByTestId('mini-timeline').querySelectorAll('[data-day]')].map((c) => c.getAttribute('data-day'))

  it('không có ngày cạn: mọi ô còn tiền, ô cuối là ngày lương, không có nhãn cạn', () => {
    render(<MiniTimeline today="2026-11-21" paydayDate="2026-11-25" />)
    expect(kinds()).toEqual(['ok', 'ok', 'ok', 'ok', 'payday'])
    expect(screen.getByTestId('mini-timeline')).toHaveAttribute('aria-label', 'Từ hôm nay 21/11 đến kỳ lương 25/11')
  })

  it('đã cạn từ trước hôm nay: ô hôm nay là ô cạn, mọi ngày tới kỳ lương là hũ trống', () => {
    render(<MiniTimeline today="2026-11-21" paydayDate="2026-11-24" runoutDate="2026-11-19" />)
    expect(kinds()).toEqual(['runout', 'gap', 'gap', 'payday'])
    expect(screen.getByTestId('mini-timeline').getAttribute('aria-label')).toContain('3 ngày hũ trống trước kỳ lương')
    expect(emptyDaysBeforePayday('2026-11-19', '2026-11-24', '2026-11-21')).toBe(3)
  })

  it('cạn đúng ngày lương: không có ngày hũ trống, không có số lớn', () => {
    render(<MiniTimeline today="2026-11-21" paydayDate="2026-11-24" runoutDate="2026-11-24" />)
    expect(kinds()).toEqual(['ok', 'ok', 'ok', 'payday'])
    expect(emptyDaysBeforePayday('2026-11-24', '2026-11-24', '2026-11-21')).toBeNull()
    expect(emptyDaysBeforePayday(undefined, '2026-11-24', '2026-11-21')).toBeNull()
  })
})
