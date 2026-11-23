import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ReviewListResponse } from '@/api/reviewSchemas'
import { restFixture, validBlock } from '@/test/fixtures'
import { backend, bodyOf, callsTo, json, mountApp } from '@/test/mountApp'

describe('Xem lại', () => {
  const review = ReviewListResponse.parse(restFixture('ReviewListResponse.review'))
  const first = review.data.items[0]!
  const empty = validBlock('review_list.empty')

  it('tải mục và gợi ý từ fixture, xác nhận Luôn luôn rồi cập nhật danh sách từ server', async () => {
    const user = userEvent.setup()
    let applied = false
    const suggestion = first.suggestions[0]!
    const confirmation = restFixture('ConfirmationRequest.assign_jar')
    const actionFixture = restFixture('ActionRequest.assign_jar')
    const params = { ...(actionFixture.params as Record<string, unknown>), jar: suggestion.jar.code }
    const action = { tool: actionFixture.tool, params, confirm_token: actionFixture.confirm_token }
    const receipt = restFixture('ActionResponse.receipt_action')
    const { calls } = mountApp(backend({
      'GET /review': () => applied ? { ...review, data: { ...review.data, items: review.data.items.slice(1) } } : review,
      'POST /confirmations': () => ({
        tool: action.tool,
        params: action.params,
        confirm_token: action.confirm_token,
        expires_at: '2026-12-10T03:02:00Z',
        ttl_seconds: 120,
        params_hash: 'a'.repeat(64),
      }),
      'POST /actions': () => {
        applied = true
        return { ...receipt, data: { ...(receipt.data as object), tool: action.tool } }
      },
    }), '/review')

    const list = await screen.findByRole('region', { name: 'Xem lại giao dịch' })
    expect(screen.getByRole('heading', { name: 'Xem lại' })).toBeInTheDocument()
    const row = within(list).getByText(first.counterparty!).closest('li')!
    expect(row).toHaveTextContent('65.000 ₫')
    expect(row).toHaveTextContent('Tin cậy vừa')
    expect(row).toHaveTextContent('Hũ hiện tại · Ăn uống')
    expect(screen.getByText('gửi xe tháng', { exact: false })).toBeInTheDocument()
    const suggestionButton = within(row).getByRole('button', { name: `${suggestion.jar.name} ${suggestion.reason}` })
    await user.click(suggestionButton)
    expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(0)
    const scope = await screen.findByRole('dialog', { name: 'Áp dụng cho giao dịch nào?' })
    expect(scope).toHaveTextContent(suggestion.jar.name)
    await user.click(within(scope).getByRole('button', { name: 'Luôn luôn cho người này' }))

    await waitFor(() => expect(screen.queryByText(first.counterparty!)).toBeNull())
    expect(screen.getByText(review.data.items[1]!.counterparty!)).toBeInTheDocument()
    expect(callsTo(calls, 'POST', '/confirmations').map(bodyOf)).toEqual([
      { ...confirmation, params },
    ])
    expect(callsTo(calls, 'POST', '/actions').map(bodyOf)).toEqual([action])
    expect(callsTo(calls, 'GET', '/review').map(({ url }) => new URL(url).search)).toEqual(['?mode=review', '?mode=review'])
  })

  it('Đúng rồi giữ chính hũ hiện tại khi chọn Chỉ lần này', async () => {
    const user = userEvent.setup()
    const { calls } = mountApp(backend({ 'GET /review': review }), '/review')
    const row = (await screen.findByText(first.counterparty!)).closest('li')!
    await user.click(within(row).getByRole('button', { name: 'Đúng rồi' }))
    await user.click(await screen.findByRole('button', { name: 'Chỉ lần này' }))
    await waitFor(() => expect(callsTo(calls, 'POST', '/actions')).toHaveLength(1))
    expect(callsTo(calls, 'POST', '/confirmations').map(bodyOf)).toEqual([
      { tool: 'assign_jar', params: { transaction_id: first.transaction_id, jar: first.current_jar!.code, remember: 'once' } },
    ])
  })

  it('hiện EmptyState từ review_list.empty', async () => {
    mountApp(backend({ 'GET /review': empty }), '/review')
    const title = await screen.findByRole('heading', { name: 'Đã xem lại xong' })
    expect(title.closest('[data-state="empty"]')).toHaveTextContent(empty.fallback_text as string)
    expect(screen.queryByRole('button', { name: 'Đúng rồi' })).toBeNull()
  })

  it('hiện lỗi và có thể tải lại danh sách', async () => {
    const user = userEvent.setup()
    let attempts = 0
    mountApp(backend({ 'GET /review': () => ++attempts === 1 ? json(500, { error: { code: 'INTERNAL_ERROR' } }) : empty }), '/review')
    const error = await screen.findByRole('alert')
    expect(error).toHaveTextContent('Chưa tải được giao dịch cần xem lại')
    await user.click(within(error).getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByRole('heading', { name: 'Đã xem lại xong' })).toBeInTheDocument()
  })
})
