import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ERROR_MESSAGES } from '@/api/errors'
import { ResilienceScoreResponse, ShocksResponse } from '@/api/resilienceSchemas'
import { ReviewListResponse } from '@/api/reviewSchemas'
import { restFixture } from '@/test/fixtures'
import { backend, callsTo, json, mountApp } from '@/test/mountApp'

describe('tab Nhìn trước', () => {
  const score = ResilienceScoreResponse.parse(restFixture('ResilienceScoreResponse.minh')).data
  const { shocks } = ShocksResponse.parse(restFixture('ShocksResponse.default'))

  it('dẫn đến Xem lại với số giao dịch và tiền chưa phân loại từ daily_ask', async () => {
    const daily = ReviewListResponse.parse(restFixture('ReviewListResponse.daily_ask'))
    const { calls } = mountApp(backend({ 'GET /review': daily }), '/foresight')
    expect(await screen.findByRole('link', { name: /^2 giao dịch chưa phân loại · 180\.000\s₫$/ })).toHaveAttribute('href', '/review')
    expect(callsTo(calls, 'GET', '/review').map(({ url }) => new URL(url).search)).toEqual(['?mode=daily_ask'])
    expect(screen.queryByRole('region', { name: 'Chọn hũ cho giao dịch hôm nay' })).toBeNull()
  })

  it('ẩn dòng chưa phân loại khi count bằng 0', async () => {
    const daily = ReviewListResponse.parse(restFixture('ReviewListResponse.daily_ask'))
    const empty = { ...daily, data: { ...daily.data, items: [], count: 0, pending_total_vnd: 0 } }
    const { calls } = mountApp(backend({ 'GET /review': empty }), '/foresight')
    await waitFor(() => expect(callsTo(calls, 'GET', '/review')).toHaveLength(1))
    expect(await screen.findByRole('list', { name: 'Hũ theo mức cần chú ý' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /giao dịch chưa phân loại/ })).toBeNull()
  })

  it('hiện điểm, nhãn nhóm và các cú sốc từ REST trước phần hũ', async () => {
    const user = userEvent.setup()
    const { router } = mountApp(backend(), '/foresight')
    const gauge = await screen.findByRole('img', { name: `Điểm chống chịu ${score.score}/100, nhóm Vừa` })
    expect(within(gauge).getByText(`${score.score}/100`)).toBeInTheDocument()
    expect(within(gauge).getByText('Vừa')).toBeInTheDocument()
    expect(screen.getByText(score.headline)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Xem chi tiết' })).toHaveAttribute('href', '/foresight/resilience')

    const list = await screen.findByRole('list', { name: 'Thử cú sốc tài chính' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(shocks.length)
    for (const shock of shocks) {
      const card = within(list).getByRole('link', { name: shock.label })
      expect(card).toHaveTextContent(shock.description)
      expect(card).toHaveAttribute('href', `/foresight/stress/${shock.shock_id}`)
    }
    const jarList = await screen.findByRole('list', { name: 'Hũ theo mức cần chú ý' })
    expect(list.compareDocumentPosition(jarList) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    await user.click(gauge)
    expect(await screen.findByRole('heading', { name: 'Chi tiết điểm chống chịu' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/foresight/resilience')
  })

  it('giữ dự báo hũ và danh sách cú sốc khi điểm lỗi, rồi tải lại được', async () => {
    const user = userEvent.setup()
    let attempts = 0
    mountApp(backend({
      'GET /resilience': () => ++attempts === 1
        ? json(500, { error: { code: 'INTERNAL_ERROR' } })
        : restFixture('ResilienceScoreResponse.minh'),
    }), '/foresight')

    const error = await screen.findByRole('alert')
    expect(error).toHaveTextContent(ERROR_MESSAGES.INTERNAL_ERROR)
    const jars = await screen.findByRole('list', { name: 'Hũ theo mức cần chú ý' })
    expect(within(jars).getAllByRole('listitem')[0]).toHaveTextContent('Ăn uống')
    expect(screen.getByTestId('forecast-quality')).toBeInTheDocument()
    expect(screen.getByTestId('next-payday')).toBeInTheDocument()
    expect(await screen.findByRole('list', { name: 'Thử cú sốc tài chính' })).toBeInTheDocument()

    await user.click(within(error).getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByRole('img', { name: /Điểm chống chịu/ })).toBeInTheDocument()
  })

  it('hiện trạng thái chưa có điểm khi chưa khai lương', async () => {
    mountApp(backend({
      'GET /resilience': json(422, { error: { code: 'PROFILE_INCOMPLETE' } }),
    }), '/foresight')

    expect(await screen.findByRole('heading', { name: 'Chưa có điểm chống chịu' })).toBeInTheDocument()
    expect(screen.getByText(ERROR_MESSAGES.PROFILE_INCOMPLETE)).toBeInTheDocument()
    expect(await screen.findByRole('list', { name: 'Hũ theo mức cần chú ý' })).toBeInTheDocument()
  })
})
