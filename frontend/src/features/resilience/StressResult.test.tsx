import { render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { StressResultData } from '@/contracts/blocks'
import { validBlock } from '@/test/fixtures'
import { StressResult } from './StressResult'

const data = (name: string) => (validBlock(`stress_result.${name}`) as unknown as { data: StressResultData }).data

describe('kết quả cú sốc: đồng hồ điểm và thanh trụ được (cảnh 3)', () => {
  beforeEach(() => sessionStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('trong chat: chạy từ điểm trước xuống điểm sau một lần cho mỗi khối trong phiên', () => {
    const d = data('mat_viec')
    const first = render(<StressResult data={d} />)
    expect(screen.getByRole('img', { name: /^Điểm chống chịu/ })).toHaveAttribute('data-animate', 'score')
    // Lần vẽ đầu cung ở điểm trước (dashoffset 100 − điểm), số giữa cung bắt đầu từ điểm trước.
    expect(screen.getByTestId('gauge-arc')).toHaveAttribute('stroke-dashoffset', String(100 - d.score_before))
    expect(screen.getByText(`${d.score_before}/100`)).toBeInTheDocument()
    expect(screen.getByTestId('runway-count')).toHaveTextContent('0')
    first.unmount()

    render(<StressResult data={d} />)
    const gauge = screen.getByRole('img', { name: /^Điểm chống chịu/ })
    expect(gauge).not.toHaveAttribute('data-animate')
    expect(within(gauge).getByTestId('gauge-arc')).toHaveAttribute('stroke-dashoffset', String(100 - d.score_after))
    expect(screen.getByTestId('runway-count')).toHaveTextContent(String(d.runway_days_total))
  })

  it('vạch mốc điểm trước luôn có, kể cả khi giảm chuyển động', () => {
    vi.stubGlobal('matchMedia', vi.fn((q: string) => ({ matches: q === '(prefers-reduced-motion: reduce)' })))
    render(<StressResult data={data('mat_viec')} animateScore />)
    expect(screen.getByRole('img', { name: /^Điểm chống chịu/ })).not.toHaveAttribute('data-animate')
    expect(screen.getByTestId('gauge-from-mark')).toBeInTheDocument()
  })

  it('trụ hết khoảng dự báo: thanh đầy, không có phần gạch hụt, số là cả khoảng', () => {
    const d = data('tien_tro_tang')
    render(<StressResult data={d} />)
    expect(screen.getByText(`Trụ hết ${d.horizon_days} ngày dự báo`)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: `Thanh số ngày trụ được: ${d.horizon_days} trên ${d.horizon_days} ngày mô phỏng` })).toBeInTheDocument()
    expect(screen.getByTestId('runway-fill')).toHaveStyle({ width: '100%' })
    expect(screen.queryByTestId('runway-gap')).toBeNull()
  })

  it('thanh dài theo runway_days_total / horizon_days của server', () => {
    const d = data('om_mot_tuan_khong_co_hu_du_phong')
    render(<StressResult data={d} />)
    expect(screen.getByTestId('runway-fill')).toHaveStyle({ width: `${(d.runway_days_total! / d.horizon_days) * 100}%` })
    expect(screen.getByTestId('runway-gap')).toBeInTheDocument()
  })
})
