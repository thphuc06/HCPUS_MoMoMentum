import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ERROR_MESSAGES } from '@/api/errors'
import { StressRequest, StressResultResponse } from '@/api/resilienceSchemas'
import { formatAppDate, formatVnd } from '@/lib/format'
import { restFixture, validBlock } from '@/test/fixtures'
import { backend, bodyOf, callsTo, json, mountApp } from '@/test/mountApp'

describe('mô phỏng cú sốc', () => {
  const result = StressResultResponse.parse(restFixture('StressResultResponse.mat_viec'))
  const data = result.data
  const request = StressRequest.parse(restFixture('StressRequest.mat_viec'))

  afterEach(() => vi.unstubAllGlobals())

  it('mở từ thẻ, gửi đúng shock_id và hiện điểm, khoản thiếu, số ngày trụ được', async () => {
    const user = userEvent.setup()
    const { calls, router } = mountApp(backend({ 'POST /resilience/stress': result }), '/foresight')

    await user.click(await screen.findByRole('link', { name: data.shock.label }))
    expect(await screen.findByRole('heading', { name: data.shock.label })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(`/foresight/stress/${request.shock_id}`)
    const posts = callsTo(calls, 'POST', '/resilience/stress')
    expect(posts).toHaveLength(1)
    expect(bodyOf(posts[0]!)).toEqual(request)
    // Đồng hồ: mô tả có điểm sau và điểm trước; số giữa cung dừng ở điểm sau sau khi chạy.
    const gauge = screen.getByRole('img', { name: `Điểm chống chịu ${data.score_after}/100, nhóm Yếu, trước cú sốc ${data.score_before}/100 nhóm Vừa` })
    expect(gauge).toHaveAttribute('data-animate', 'score')
    expect(await within(gauge).findByText(`${data.score_after}/100`)).toBeInTheDocument()
    expect(screen.getByText(`${data.score_before} → ${data.score_after}`)).toBeVisible()
    // Thanh trụ được: dài theo runway / horizon, số lớn đếm tới số của server.
    expect(screen.getByRole('img', { name: `Thanh số ngày trụ được: ${data.runway_days_total} trên ${data.horizon_days} ngày mô phỏng` })).toBeInTheDocument()
    expect(screen.getByTestId('runway-fill')).toHaveStyle({ width: `${(data.runway_days_total! / data.horizon_days) * 100}%` })
    expect(screen.getByTestId('runway-fill')).toHaveClass('motion-grow-x')
    expect(screen.getByTestId('runway-gap')).toBeInTheDocument()
    expect(await screen.findByText(String(data.runway_days_total), { selector: '[data-testid="runway-count"]' })).toBeInTheDocument()
    expect(screen.getByText(data.headline)).toBeInTheDocument()
    expect(screen.getByText('Hụt')).toBeInTheDocument()
    expect(screen.getByText(`Trụ được ${data.runway_days_total} ngày`)).toBeInTheDocument()
    const emergency = screen.getByText(`Hũ ${data.emergency_jar!.name}`).parentElement!
    expect(within(emergency).getByText(`${data.runway_days_emergency} ngày`)).toBeInTheDocument()
    expect(screen.getByText(`Khoản thiếu từ ${formatAppDate(data.shortfall_from!)}`)).toBeInTheDocument()
    expect(screen.getByText(formatVnd(data.shortfall_vnd).replace('\u00a0', ' '))).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Xem lộ trình thích ứng' })).toHaveAttribute('href', '/roadmap')
    await user.click(screen.getByRole('button', { name: 'Quay lại' }))
    expect(await screen.findByRole('heading', { name: 'Nhìn trước' })).toBeInTheDocument()
  })

  it('ẩn dòng hũ Dự phòng khi kết quả không có hũ này', async () => {
    const block = StressResultResponse.parse(validBlock('stress_result.om_mot_tuan_khong_co_hu_du_phong'))
    mountApp(backend({ 'POST /resilience/stress': block }), `/foresight/stress/${block.data.shock.shock_id}`)

    expect(await screen.findByText(`Trụ được ${block.data.runway_days_total} ngày`)).toBeInTheDocument()
    expect(screen.queryByText('Hũ Dự phòng')).not.toBeInTheDocument()
  })

  it('hiện cả khoảng dự báo khi kết quả chưa cạn ví', async () => {
    const block = StressResultResponse.parse(validBlock('stress_result.tien_tro_tang'))
    mountApp(backend({ 'POST /resilience/stress': block }), `/foresight/stress/${block.data.shock.shock_id}`)

    expect(await screen.findByText(`Trụ hết ${block.data.horizon_days} ngày dự báo`)).toBeInTheDocument()
  })

  it('hiện ngay điểm sau cú sốc khi người dùng giảm chuyển động', async () => {
    vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: query === '(prefers-reduced-motion: reduce)' })))
    mountApp(backend({ 'POST /resilience/stress': result }), `/foresight/stress/${request.shock_id}`)

    await screen.findByRole('heading', { name: data.shock.label })
    const gauge = screen.getByRole('img', { name: /^Điểm chống chịu/ })
    expect(gauge).not.toHaveAttribute('data-animate')
    expect(within(gauge).getByText(`${data.score_after}/100`)).toBeInTheDocument()
    expect(within(gauge).queryByText(`${data.score_before}/100`)).not.toBeInTheDocument()
    expect(screen.getByTestId('runway-count')).toHaveTextContent(String(data.runway_days_total))
    expect(screen.getByTestId('runway-fill')).not.toHaveClass('motion-grow-x')
  })

  it('hiện thông báo SHOCK_NOT_FOUND cho mã cú sốc không tồn tại', async () => {
    mountApp(backend({
      'POST /resilience/stress': json(404, { error: { code: 'SHOCK_NOT_FOUND' } }),
    }), '/foresight/stress/khong_co')

    expect(await screen.findByRole('alert')).toHaveTextContent(ERROR_MESSAGES.SHOCK_NOT_FOUND)
  })
})
