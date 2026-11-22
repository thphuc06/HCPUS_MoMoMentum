import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ApiClient } from '@/api/client'
import { ApiError } from '@/api/errors'
import type { ActionResponse } from '@/api/schemas'
import { ExplainContext } from '@/features/explain/context'
import { Providers, fakeApi, fakeChatActions } from '@/test/helpers'
import { validBlock } from '@/test/fixtures'
import { BlockRenderer } from './registry'

type Json = Record<string, any>

function setup(raw: unknown, opts: { api?: Partial<ApiClient>; ui?: 'cancelled' | 'undone'; doneAt?: number; stale?: boolean; explain?: boolean } = {}) {
  const actions = fakeChatActions()
  const api = fakeApi(opts.api)
  const open = vi.fn()
  const tree = (
    <Providers api={api} actions={actions}>
      <BlockRenderer raw={raw} blockId="b1" ui={opts.ui} doneAt={opts.doneAt} stale={opts.stale} />
    </Providers>
  )
  const r = render(opts.explain ? <ExplainContext.Provider value={{ open }}>{tree}</ExplainContext.Provider> : tree)
  return { ...r, actions, api, open, user: userEvent.setup() }
}

describe('affordability_card (AffordCard)', () => {
  it('xanh: chữ "Đủ" kèm biểu tượng (không chỉ màu), tiêu đề do server dựng, từng hũ kèm trạng thái', () => {
    const { container } = setup(validBlock('affordability_card.transfer_250k'))
    const card = container.querySelector('[data-block="affordability_card"]')!
    expect(card).toHaveAttribute('data-verdict', 'ok')
    const chip = within(card as HTMLElement).getAllByText('Đủ')[0]!.closest('[data-chip]')!
    expect(chip.querySelector('svg')).not.toBeNull()
    expect(screen.getByTestId('afford-headline')).toHaveTextContent('Có thể chuyển 250.000 ₫ từ hũ Đi lại')
    // ba hũ: Hóa đơn sát (vàng), Đi lại đủ (xanh), Ăn uống hụt (đỏ), mỗi hũ có chữ
    const rows = container.querySelectorAll('[data-jar][data-status]')
    expect([...rows].map((r) => [r.getAttribute('data-jar'), r.querySelector('[data-chip]')?.textContent])).toEqual(
      expect.arrayContaining([
        ['hoa_don', 'Sát'],
        ['di_lai', 'Đủ'],
        ['an_uong', 'Hụt'],
      ]),
    )
    expect(screen.getByText('Cạn sớm hơn 1 ngày (23/11 → 22/11)')).toBeInTheDocument()
    expect(screen.getByText(/Hụt 480\.000 ₫ trước kỳ lương/)).toBeInTheDocument()
  })

  it('Trả sau: "món này tốn" TÁCH khỏi "đến hạn phải trả"; tổng gồm nghĩa vụ đã có; không tự cộng', () => {
    setup(validBlock('affordability_card.credit_only'))
    expect(screen.getByTestId('item-cost')).toHaveTextContent('Món này tốn')
    expect(screen.getByTestId('item-cost')).toHaveTextContent('250.000 ₫')
    expect(screen.getByTestId('item-cost')).toHaveTextContent('không phát sinh thêm phí')
    expect(screen.getByTestId('total-due')).toHaveTextContent('Đến hạn 05/12 phải trả')
    expect(screen.getByTestId('total-due')).toHaveTextContent('1.250.000 ₫')
    expect(screen.getByTestId('total-due')).toHaveTextContent('gồm 1.000.000 ₫ nghĩa vụ Trả sau đã có')
    expect(screen.getByTestId('credit-limit')).toHaveTextContent('4.033.000 ₫ → 3.783.000 ₫')
    expect(screen.getByTestId('obligation-ratio')).toHaveTextContent('47%')
    expect(screen.getByTestId('obligation-ratio')).toHaveTextContent('vượt ngưỡng')
    expect(screen.getByText('Hụt 250.000 ₫')).toBeInTheDocument()
    expect(screen.getByTestId('basis')).toHaveTextContent('nhóm tin cậy Vừa')
  })

  it('phí phát sinh thêm > 0: hiện rõ gốc và phí trong "món này tốn" (tài khoản chưa có nghĩa vụ)', () => {
    const b = validBlock('obligation_impact.first_of_month') as Json
    setup(b)
    const c = b.data.cost
    expect(c.fee_added_vnd).toBeGreaterThan(0)
    expect(screen.getByTestId('item-cost')).toHaveTextContent('gồm gốc')
    expect(screen.getByTestId('item-cost')).toHaveTextContent('phí')
    expect(screen.getByTestId('item-cost')).toHaveTextContent((c.item_cost_vnd as number).toLocaleString('vi-VN'))
    expect(screen.getByTestId('total-due')).toHaveTextContent((c.total_due_vnd as number).toLocaleString('vi-VN'))
  })

  it('"Vì sao" chỉ có khi ở trong chat (có ExplainContext) và mở đúng trace của khối', async () => {
    const block = validBlock('affordability_card.transfer_250k') as Json
    const a = setup(block)
    expect(screen.queryByRole('button', { name: 'Vì sao' })).toBeNull()
    a.unmount()
    const b = setup(block, { explain: true })
    await b.user.click(screen.getByRole('button', { name: 'Vì sao' }))
    expect(b.open).toHaveBeenCalledWith(block.trace_id)
  })
})

describe('obligation_impact', () => {
  it('minh mua 1,2 triệu: món 1.200.000 ₫ tách khỏi tổng phải trả 2.200.000 ₫; hũ Nghĩa vụ hụt', () => {
    setup(validBlock('obligation_impact.minh_headphones'))
    expect(screen.getByTestId('item-cost')).toHaveTextContent('1.200.000 ₫')
    expect(screen.getByTestId('total-due')).toHaveTextContent('2.200.000 ₫')
    expect(screen.getByText('Hụt 1.150.000 ₫')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Lưu ý' })).toHaveTextContent('Không khuyến khích')
  })
})

describe('options (phương án) và POST /feedback', () => {
  const block = () => validBlock('options.move_remind_skip') as Json

  it('"Chọn" phương án có action: ghi feedback accepted rồi hiện khối xác nhận đã phát (không gọi tool ghi, không tạo token)', async () => {
    const b = block()
    const { user, api, actions } = setup(b)
    expect(screen.getAllByText(/Cần bạn xác nhận mới thực hiện/)).toHaveLength(2)
    expect(screen.getByText(/Chỉ để cân nhắc/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Chọn: Bù 100.000 ₫ từ hũ Giải trí' }))
    expect(actions.revealBlock).toHaveBeenCalledWith(b.data.options[0].action.block_id)
    await waitFor(() => expect(api.submitFeedback).toHaveBeenCalledTimes(1))
    expect(api.submitFeedback).toHaveBeenCalledWith({
      trace_id: b.trace_id,
      block_id: b.id,
      option_id: 'move_from_giai_tri',
      decision: 'accepted',
      scenario_id: b.data.scenario_id,
    })
    expect(api.createConfirmation).not.toHaveBeenCalled()
    expect(api.applyAction).not.toHaveBeenCalled()
    expect(await screen.findByText('Đã chọn')).toBeInTheDocument()
    expect(screen.getByText('Bước xác nhận đã mở ngay bên dưới.')).toBeInTheDocument()
  })

  it('"Không chọn" ghi rejected và không mở khối xác nhận', async () => {
    const b = block()
    const { user, api, actions } = setup(b)
    await user.click(screen.getByRole('button', { name: 'Không chọn: Bù 100.000 ₫ từ hũ Giải trí' }))
    await waitFor(() => expect(api.submitFeedback).toHaveBeenCalledWith(expect.objectContaining({ option_id: 'move_from_giai_tri', decision: 'rejected' })))
    expect(actions.revealBlock).not.toHaveBeenCalled()
    expect(await screen.findByText('Đã bỏ qua')).toBeInTheDocument()
  })

  it('phương án chỉ để cân nhắc (không action): chọn thì chỉ ghi feedback', async () => {
    const { user, api, actions } = setup(block())
    await user.click(screen.getByRole('button', { name: 'Chọn: Bỏ qua khoản này' }))
    await waitFor(() => expect(api.submitFeedback).toHaveBeenCalledWith(expect.objectContaining({ option_id: 'skip_purchase', decision: 'accepted' })))
    expect(actions.revealBlock).not.toHaveBeenCalled()
  })

  it('ghi feedback lỗi: nói nhẹ nhàng, không chặn việc mở bước xác nhận', async () => {
    const { user, actions } = setup(block(), { api: { submitFeedback: vi.fn(async () => { throw new ApiError('TRACE_NOT_FOUND', 404) }) } })
    await user.click(screen.getByRole('button', { name: 'Chọn: Bù 100.000 ₫ từ hũ Giải trí' }))
    expect(actions.revealBlock).toHaveBeenCalled()
    expect(await screen.findByText(/Chưa ghi được lựa chọn của bạn/)).toBeInTheDocument()
  })
})

describe('explain (bảng "Vì sao")', () => {
  it('dữ liệu đã dùng, luật đã kiểm (có chữ kết quả), nhóm tin cậy kèm lý do, mã trace', () => {
    const b = validBlock('explain.what_if') as Json
    setup(b)
    const used = screen.getByTestId('explain-data-used')
    expect(within(used).getAllByRole('listitem')).toHaveLength(b.data.data_used.length)
    expect(used).toHaveTextContent('forecast___run_scenario')
    const rules = screen.getByTestId('explain-rules')
    expect(within(rules).getAllByRole('listitem')).toHaveLength(b.data.rules_checked.length)
    expect(rules.querySelector('[data-outcome="warn"]')).toHaveTextContent('Cảnh báo')
    expect(rules.querySelector('[data-outcome="skipped"]')).toHaveTextContent('Không áp dụng')
    expect(screen.getByRole('region', { name: 'Độ tin cậy' })).toHaveTextContent('Vừa')
    expect(screen.getByTestId('explain-reasons')).toHaveTextContent('Có 47 ngày dữ liệu.')
    expect(screen.getByTestId('explain-trace-id')).toHaveTextContent(b.data.subject_trace_id)
    expect(screen.queryByTestId('explain-low-invite')).toBeNull()
  })

  it('độ tin cậy Thấp (H8b): mời ghi thêm dữ liệu', () => {
    setup(validBlock('explain.low_confidence'))
    expect(screen.getByRole('region', { name: 'Độ tin cậy' })).toHaveTextContent('Thấp')
    expect(screen.getByTestId('explain-low-invite')).toHaveTextContent('Ghi thêm giao dịch')
  })
})

describe('clarify (hỏi lại đúng một câu)', () => {
  it('chip gửi value (hoặc nhãn) như tin nhắn kế tiếp', async () => {
    const b = validBlock('clarify.funding') as Json
    const { user, actions } = setup(b)
    expect(screen.getByTestId('clarify-question')).toHaveTextContent(b.data.question)
    const chip = b.data.chips[0]
    await user.click(screen.getByRole('button', { name: chip.label }))
    expect(actions.ask).toHaveBeenCalledWith(chip.value ?? chip.label)
    expect(screen.getByText(/gõ câu trả lời/)).toBeInTheDocument()
  })

  it('đã có tin nhắn sau khối: chip hết bấm được', () => {
    const b = validBlock('clarify.amount') as Json
    setup(b, { stale: true })
    for (const c of b.data.chips) expect(screen.getByRole('button', { name: c.label })).toBeDisabled()
  })
})

describe('suggestions và notice mở rộng', () => {
  it('mở đầu (H1): "mình làm được / chưa làm" và chip gợi ý bấm được', async () => {
    const b = validBlock('suggestions.welcome') as Json
    const { user, actions } = setup(b)
    expect(screen.getByText('Mình làm được')).toBeInTheDocument()
    expect(screen.getByText('Mình chưa làm')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: b.data.items[0].label }))
    expect(actions.ask).toHaveBeenCalledWith(b.data.items[0].prompt)
  })

  it('ngoài phạm vi (H7): lời từ chối kèm việc làm được; bấm chip để hỏi', async () => {
    const b = validBlock('notice.out_of_scope_suggestions') as Json
    const { user, actions } = setup(b)
    expect(screen.getByRole('status')).toHaveAttribute('data-notice', 'out_of_scope')
    const sg = screen.getByTestId('notice-suggestions')
    await user.click(within(sg).getAllByRole('button')[0]!)
    expect(actions.ask).toHaveBeenCalledWith(b.data.suggestions[0].prompt)
  })

  it('suy giảm (H8a) có retryable: "Thử lại" chạy lại lượt; hết quyền thử lại khi đã có tin mới (stale)', async () => {
    const b = validBlock('notice.error_retry') as Json
    expect(b.data.retryable).toBe(true)
    const a = setup(b)
    await a.user.click(screen.getByRole('button', { name: 'Thử lại' }))
    expect(a.actions.retryLast).toHaveBeenCalledTimes(1)
    a.unmount()
    setup(b, { stale: true })
    expect(screen.queryByRole('button', { name: 'Thử lại' })).toBeNull()
  })

  it('trả một phần: liệt kê phần còn thiếu', () => {
    const b = validBlock('notice.degraded_partial') as Json
    setup(b)
    const miss = screen.getByTestId('notice-missing')
    for (const m of b.data.missing) expect(miss).toHaveTextContent(m)
  })
})

describe('Hoàn tác có đếm ngược (H6b)', () => {
  const receipt = () => validBlock('receipt.move') as Json

  it('biên nhận vừa thực hiện: Hoàn tác gọi thao tác ngược qua /confirmations rồi /actions; biên nhận mới thay chỗ, agent được báo', async () => {
    const r = receipt()
    const undoReceipt = { ...validBlock('receipt.move'), id: 'receipt:undo' }
    const createConfirmation = vi.fn(async (req: any) => ({
      confirm_token: 'aaa.bbb',
      expires_at: '2026-12-10T03:02:00Z',
      ttl_seconds: 120,
      tool: req.tool,
      params: req.params,
      params_hash: 'a'.repeat(64),
    }))
    const applyAction = vi.fn(async () => undoReceipt as unknown as ActionResponse)
    const { user, actions } = setup(r, { doneAt: Date.now(), api: { createConfirmation, applyAction } })
    const btn = screen.getByRole('button', { name: /Hoàn tác · còn \d\d:\d\d/ })
    await user.click(btn)
    await waitFor(() => expect(applyAction).toHaveBeenCalledTimes(1))
    // chuyển ngược: hũ đích -> hũ nguồn, cùng số tiền; không kèm conversation/confirm_block (không phải khối đề nghị)
    expect(createConfirmation).toHaveBeenCalledWith({ tool: 'move_between_jars', params: { from_jar: r.data.to_jar.code, to_jar: r.data.from_jar.code, amount_vnd: r.data.amount_vnd } })
    expect(applyAction).toHaveBeenCalledWith({ tool: 'move_between_jars', params: expect.any(Object), confirm_token: 'aaa.bbb' })
    expect(actions.replaceBlock).toHaveBeenCalledWith('b1', undoReceipt, 'receipt:undo', { undone: true })
    expect(actions.addSystemNote).toHaveBeenCalledWith(expect.stringContaining('Hoàn tác'), 'receipt:undo')
  })

  it('không có doneAt (dựng lại sau khi tải trang) hoặc hết giờ: không có nút Hoàn tác', () => {
    const a = setup(receipt())
    expect(screen.queryByTestId('undo-bar')).toBeNull()
    a.unmount()
    setup(receipt(), { doneAt: Date.now() - 31_000 })
    expect(screen.queryByTestId('undo-bar')).toBeNull()
  })

  it('lỗi khi hoàn tác: báo bằng tiếng Việt, giữ nút để thử lại', async () => {
    const createConfirmation = vi.fn(async () => {
      throw new ApiError('INSUFFICIENT_FUNDS', 422)
    })
    const { user } = setup(receipt(), { doneAt: Date.now(), api: { createConfirmation } })
    await user.click(screen.getByRole('button', { name: /Hoàn tác/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('không đủ số dư')
    expect(screen.getByRole('button', { name: /Hoàn tác/ })).toBeEnabled()
  })

  it('lời nhắc đã đặt: Hoàn tác = schedule_nudge op cancel với nudge_id là reference_id của biên nhận', async () => {
    const r = validBlock('receipt_action.schedule_nudge') as Json
    const createConfirmation = vi.fn(async (req: any) => ({
      confirm_token: 'aaa.bbb', expires_at: '2026-12-10T03:02:00Z', ttl_seconds: 120, tool: req.tool, params: req.params, params_hash: 'a'.repeat(64),
    }))
    const applyAction = vi.fn(async () => ({ ...r, id: 'receipt:schedule_nudge:cancel', data: { ...r.data, summary: 'Đã hủy nhắc' } }) as unknown as ActionResponse)
    const { user } = setup(r, { doneAt: Date.now(), api: { createConfirmation, applyAction } })
    await user.click(screen.getByRole('button', { name: /Hoàn tác/ }))
    await waitFor(() => expect(applyAction).toHaveBeenCalled())
    expect(createConfirmation).toHaveBeenCalledWith({ tool: 'schedule_nudge', params: { op: 'cancel', nudge_id: r.data.reference_id } })
  })

  it('thao tác không có thao tác ngược trong hợp đồng (ghi giao dịch): không có Hoàn tác', () => {
    setup(validBlock('receipt_action.record_transaction'), { doneAt: Date.now() })
    expect(screen.queryByTestId('undo-bar')).toBeNull()
  })

  it('biên nhận của thao tác ngược: ghi rõ "Đã hoàn tác" và không còn Hoàn tác', () => {
    setup(validBlock('receipt.move'), { ui: 'undone', doneAt: Date.now() })
    expect(screen.getByTestId('undone-note')).toHaveTextContent('Đã hoàn tác')
  })
})

describe('OFFER_EXPIRED: đề nghị hết hạn', () => {
  it('xin token bị OFFER_EXPIRED: khóa nút, mời "Hỏi lại để có đề nghị mới" (gọi askAgain), không nói như token hết hạn', async () => {
    const block = validBlock('confirm.move') as Json
    block.data.expires_at = new Date(Date.now() + 5 * 60_000).toISOString().replace(/\.\d+Z$/, 'Z')
    const { user, actions, container } = setup(block, { api: { createConfirmation: vi.fn(async () => { throw new ApiError('OFFER_EXPIRED', 410) }) } })
    await user.click(screen.getByRole('button', { name: /Xác nhận chuyển/ }))
    await waitFor(() => expect(container.querySelector('[data-block="confirm"]')).toHaveAttribute('data-phase', 'expired'))
    expect(screen.getByRole('button', { name: /Xác nhận chuyển/ })).toBeDisabled()
    expect(screen.queryByRole('alert')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Hỏi lại để có đề nghị mới' }))
    expect(actions.askAgain).toHaveBeenCalledTimes(1)
  })

  it('TOKEN_EXPIRED lúc áp dụng (token quá 2 phút) vẫn là lỗi bấm lại được, KHÔNG phải đề nghị hết hạn', async () => {
    const block = validBlock('confirm.move') as Json
    block.data.expires_at = new Date(Date.now() + 5 * 60_000).toISOString().replace(/\.\d+Z$/, 'Z')
    const createConfirmation = vi.fn(async (req: any) => ({ confirm_token: 'a.b', expires_at: '2026-12-10T03:02:00Z', ttl_seconds: 120, tool: req.tool, params: req.params, params_hash: 'a'.repeat(64) }))
    const applyAction = vi.fn(async () => {
      throw new ApiError('TOKEN_EXPIRED', 403)
    })
    const { user, container } = setup(block, { api: { createConfirmation, applyAction } })
    await user.click(screen.getByRole('button', { name: /Xác nhận chuyển/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Phiên xác nhận đã hết hạn')
    expect(container.querySelector('[data-block="confirm"]')).toHaveAttribute('data-phase', 'idle')
    expect(screen.getByRole('button', { name: /Xác nhận chuyển/ })).toBeEnabled()
  })
})
