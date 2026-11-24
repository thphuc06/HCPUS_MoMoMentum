import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ReviewListResponse } from '@/api/reviewSchemas'
import { restFixture } from '@/test/fixtures'
import { backend, bodyOf, callsTo, json, mountApp } from '@/test/mountApp'

const CARD = 'Chọn hũ cho giao dịch hôm nay'
// Sau khi Để sau: một dòng Việc cần làm gộp hai hàng chờ (2 chưa xếp hũ ở daily_ask, 1 cần xem lại = needs_review_count 3 − 2).
const SUMMARY = /^Xếp hũ cho 3 giao dịch 2 chưa xếp hũ · 180\.000\s₫; 1 cần xem lại$/

describe('Hỏi gộp ở Tổng quan', () => {
  const daily = ReviewListResponse.parse(restFixture('ReviewListResponse.daily_ask'))

  it('hiện mục hỏi gộp và hai gợi ý, gửi ngày mô phỏng khi Để sau rồi giữ số chưa phân loại', async () => {
    const user = userEvent.setup()
    const { calls } = mountApp(backend({
      'GET /review': daily,
      'POST /review/daily-ask/skip': restFixture('ReviewAskResponse.skipped'),
    }))
    const card = await screen.findByRole('region', { name: CARD })
    const first = daily.data.items[0]!
    const row = within(card).getByText(first.counterparty!).closest('li')!
    expect(row).toHaveTextContent('Tin cậy thấp')
    expect(row).toHaveTextContent('Hũ hiện tại · Chưa phân loại')
    const suggestions = within(row).getByRole('list', { name: 'Hũ gợi ý' })
    expect(within(suggestions).getAllByRole('button')).toHaveLength(2)
    for (const suggestion of first.suggestions) {
      expect(within(suggestions).getByRole('button', { name: `${suggestion.jar.name} ${suggestion.reason}` })).toBeInTheDocument()
    }

    await user.click(within(card).getByRole('button', { name: 'Để sau' }))
    await waitFor(() => expect(screen.queryByRole('region', { name: CARD })).toBeNull())
    expect(callsTo(calls, 'POST', '/review/daily-ask/skip').map(bodyOf)).toEqual([restFixture('ReviewAskSkipRequest.default')])
    expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(0)
    expect(screen.getByRole('link', { name: SUMMARY })).toHaveAttribute('href', '/review')
  })

  it('mục không có gợi ý dùng Hũ khác rồi chỉ cho lưu lần này', async () => {
    const user = userEvent.setup()
    let applied = false
    const [first, second] = daily.data.items
    const jar = daily.data.jars[1]!
    const { calls } = mountApp(backend({
      'GET /review': () => applied ? { ...daily, data: { ...daily.data, items: [first!], count: 1, pending_total_vnd: first!.amount_vnd } } : daily,
      'POST /actions': () => {
        applied = true
        return restFixture('ActionResponse.receipt_action')
      },
    }))
    const card = await screen.findByRole('region', { name: CARD })
    const row = within(card).getByText('120.000 ₫').closest('li')!
    await user.click(within(row).getByRole('button', { name: 'Hũ khác' }))
    const picker = await screen.findByRole('dialog', { name: 'Chọn hũ' })
    await user.click(within(picker).getByRole('radio', { name: jar.name }))
    const scope = await screen.findByRole('dialog', { name: 'Áp dụng cho giao dịch nào?' })
    expect(within(scope).queryByRole('button', { name: 'Luôn luôn cho người này' })).toBeNull()
    expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(0)
    await user.click(within(scope).getByRole('button', { name: 'Chỉ lần này' }))

    await waitFor(() => expect(within(screen.getByRole('region', { name: CARD })).getByText(/^1 giao dịch · 60\.000\s₫$/)).toBeInTheDocument())
    expect(within(card).queryByText('120.000 ₫')).toBeNull()
    expect(callsTo(calls, 'POST', '/confirmations').map(bodyOf)).toEqual([
      { tool: 'assign_jar', params: { transaction_id: second!.transaction_id, jar: jar.code, remember: 'once' } },
    ])
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(1)
  })

  it('giữ thẻ và cho thử lại khi Để sau gặp lỗi', async () => {
    const user = userEvent.setup()
    let attempts = 0
    mountApp(backend({
      'GET /review': daily,
      'POST /review/daily-ask/skip': () => ++attempts === 1
        ? json(503, { error: { code: 'UNAVAILABLE' } })
        : restFixture('ReviewAskResponse.skipped'),
    }))
    const card = await screen.findByRole('region', { name: CARD })
    await user.click(within(card).getByRole('button', { name: 'Để sau' }))
    expect(await within(card).findByRole('alert')).toHaveTextContent('Chưa để sau được câu hỏi')
    await user.click(within(card).getByRole('button', { name: 'Để sau' }))
    await waitFor(() => expect(screen.queryByRole('region', { name: CARD })).toBeNull())
  })
})
