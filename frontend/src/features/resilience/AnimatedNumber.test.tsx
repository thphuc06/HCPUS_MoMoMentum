import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { StressResultResponse } from '@/api/resilienceSchemas'
import { restFixture } from '@/test/fixtures'
import { AnimatedNumber } from './AnimatedNumber'

describe('điểm đếm lùi', () => {
  const { score_before: from, score_after: to } = StressResultResponse.parse(
    restFixture('StressResultResponse.mat_viec'),
  ).data

  afterEach(() => vi.unstubAllGlobals())

  it('đi qua điểm trung gian rồi dừng ở điểm kết quả', () => {
    let nextFrame!: FrameRequestCallback
    const requestFrame = vi.fn((callback: FrameRequestCallback) => {
      nextFrame = callback
      return 1
    })
    vi.stubGlobal('requestAnimationFrame', requestFrame)

    const { container } = render(<AnimatedNumber from={from} to={to} />)
    expect(screen.getByText(String(from))).toBeVisible()
    act(() => nextFrame(0))
    act(() => nextFrame(100))
    const intermediate = Number(container.textContent)
    expect(intermediate).toBeLessThan(from)
    expect(intermediate).toBeGreaterThan(to)
    act(() => nextFrame(10_000))
    expect(screen.getByText(String(to))).toBeVisible()
    expect(requestFrame).toHaveBeenCalledTimes(3)
  })

  it('bỏ qua các frame khi giảm chuyển động', () => {
    const requestFrame = vi.fn()
    vi.stubGlobal('requestAnimationFrame', requestFrame)
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))

    render(<AnimatedNumber from={from} to={to} />)
    expect(screen.getByText(String(to))).toBeVisible()
    expect(requestFrame).not.toHaveBeenCalled()
  })
})
