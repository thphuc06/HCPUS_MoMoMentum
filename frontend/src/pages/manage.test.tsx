import { cleanup, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { restFixture } from '@/test/fixtures'
import { backend, bodyOf, callsTo, json, mountApp } from '@/test/mountApp'

// Nghĩa vụ, Tiền vào, Lương về, Giữa hũ, Hồ sơ, Hoạt động, Thêm/sửa hũ: bình thường, rỗng, lỗi; mọi thao tác ghi đi qua
// /confirmations → /actions và làm mới dữ liệu.

type Json = Record<string, any>
const TIEN_DIEN = '9a4d0e11-6b2c-4f3a-8d5e-1c7b9a3f5e20'
const BNPL = '2b6e8f40-3d1a-4c5b-9e7f-0a1b2c3d4e5f'
const SALARY_EVENT = '7e1f3a90-2c4b-4d6e-8f01-a3b5c7d9e0f2'

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

const receiptAction = (over: (d: Json) => void = () => {}): Json => {
  const r = restFixture('ActionResponse.receipt_action') as Json
  delete r.data.follow_up
  over(r.data)
  return r
}

describe('Nghĩa vụ', () => {
  it('hạn mức Trả sau có nguồn biểu phí; khoản khai theo khoảng; khoản Trả sau tự sinh không sửa được, hiện gốc + phí của server', async () => {
    mountApp(backend(), '/obligations')
    const credit = await screen.findByTestId('credit-line')
    expect(credit).toHaveTextContent('Trả sau (mô phỏng)')
    expect(credit).toHaveTextContent('5.000.000 ₫')
    expect(credit).toHaveTextContent('4.700.000 ₫')
    expect(credit).toHaveTextContent('Nguồn: Biểu phí công khai')
    const list = await screen.findByTestId('obligation-list')
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Tiền điện')
    expect(rows[0]).toHaveTextContent('300.000 ₫ đến 450.000 ₫')
    expect(within(rows[0]!).getByRole('link', { name: 'Sửa Tiền điện' })).toHaveAttribute('href', `/obligations/${TIEN_DIEN}`)
    expect(rows[1]).toHaveTextContent('Gốc 300.000 ₫ + phí 33.000 ₫')
    expect(rows[1]).toHaveTextContent('333.000 ₫')
    expect(within(rows[1]!).queryByRole('link')).toBeNull()
    expect(screen.getByTestId('obligations-total')).toHaveTextContent('708.000 ₫')
  })

  it('B6: thanh hạn mức đã dùng trên tổng; khoản Trả sau đến hạn gần nhất so với số dư hũ trả (từ Tổng quan)', async () => {
    mountApp(backend(), '/obligations')
    const credit = await screen.findByTestId('credit-line')
    expect(within(credit).getByRole('heading', { name: 'Đã dùng Trả sau bao nhiêu' })).toBeInTheDocument()
    expect(within(credit).getByRole('img', { name: /^Đã dùng 300\.000\s₫ trên hạn mức 5\.000\.000\s₫, còn 4\.700\.000\s₫$/ })).toBeInTheDocument()
    expect(credit).toHaveTextContent('Đã dùng 300.000 ₫ (6%)')
    const due = await within(credit).findByTestId('credit-due')
    expect(due).toHaveTextContent('Đến hạn 05/12')
    expect(due).toHaveTextContent('Phải trả: gốc 300.000 ₫ + phí 33.000 ₫')
    expect(await within(due).findByTestId('credit-due-status')).toHaveTextContent('Đủ trả')
    expect(due).toHaveTextContent(/Hũ Nghĩa vụ đang có\s*1\.000\.000 ₫/)
    // Màn Nghĩa vụ không có lối quay về chính nó
    expect(within(credit).queryByRole('link', { name: /Xem các khoản Trả sau/ })).toBeNull()
  })

  it('B6: chưa dùng Trả sau thì thanh rỗng và nói rõ; không có hạn mức thì không có thẻ', async () => {
    const none = { ...(restFixture('CreditLineResponse.default') as Json) }
    none.credit_line = { ...none.credit_line, outstanding_vnd: 0, available_vnd: 5000000 }
    mountApp(backend({ 'GET /credit-line': none, 'GET /obligations': { app_date: '2026-11-21', obligations: [], total_due_vnd: 0 } }), '/obligations')
    const credit = await screen.findByTestId('credit-line')
    expect(credit).toHaveTextContent('Chưa dùng Trả sau. Hạn mức 5.000.000 ₫.')
    expect(within(credit).queryByTestId('credit-due')).toBeNull()
    cleanup()
    mountApp(backend({ 'GET /credit-line': restFixture('CreditLineResponse.none') }), '/obligations')
    expect(await screen.findByTestId('obligation-list')).toBeInTheDocument()
    expect(screen.queryByTestId('credit-line')).toBeNull()
  })

  it('rỗng: trạng thái rỗng có nút thêm; lỗi: Thử lại', async () => {
    let n = 0
    mountApp(backend({ 'GET /obligations': () => (++n === 1 ? json(503, { error: { code: 'DATABASE_UNAVAILABLE', message: 'x' } }) : { app_date: '2026-11-21', obligations: [], total_due_vnd: 0 }) }), '/obligations')
    const alert = await screen.findByRole('alert')
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByText('Chưa có khoản nghĩa vụ nào')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /Thêm khoản/ }).length).toBeGreaterThan(0)
  })

  it('thêm khoản: tiền trọ cố định hằng tháng → update_profile; làm mới; quay về danh sách', async () => {
    const { calls, router } = mountApp(backend({ 'POST /actions': () => receiptAction() }), '/obligations/new')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Tên khoản'), 'Tiền trọ')
    await user.type(screen.getByLabelText('Số tiền mỗi kỳ'), '2500000')
    await user.type(screen.getByLabelText('Ngày đến hạn trong tháng'), '1')
    await user.selectOptions(screen.getByLabelText('Hũ dùng để trả'), 'hoa_don')
    await user.click(screen.getByRole('button', { name: 'Lưu khoản này' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/obligations'))
    const conf = bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)
    expect(conf).toEqual({
      tool: 'update_profile',
      params: { obligation: { op: 'upsert', kind: 'rent', name: 'Tiền trọ', cycle: 'monthly', is_essential: true, amount_vnd: 2500000, due_day: 1, pay_jar: 'hoa_don' } },
    })
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(1)
    await waitFor(() => expect(callsTo(calls, 'GET', '/overview').length).toBeGreaterThanOrEqual(2))
  })

  it('khai theo khoảng, chu kỳ không phải hằng tháng thì cần ngày đến hạn đầy đủ; kiểm khoảng hợp lệ', async () => {
    const { calls } = mountApp(backend({ 'POST /actions': () => receiptAction() }), '/obligations/new')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('radio', { name: 'Hóa đơn' }))
    await user.type(screen.getByLabelText('Tên khoản'), 'Tiền điện')
    await user.click(screen.getByRole('radio', { name: 'Dao động theo tháng' }))
    await user.type(screen.getByLabelText('Thấp nhất'), '450000')
    await user.type(screen.getByLabelText('Cao nhất'), '300000')
    await user.selectOptions(screen.getByLabelText('Chu kỳ'), 'yearly')
    await user.click(screen.getByRole('button', { name: 'Lưu khoản này' }))
    expect(screen.getByText('Số cao nhất phải không nhỏ hơn số thấp nhất')).toBeInTheDocument()
    expect(screen.getByText('Chọn ngày đến hạn')).toBeInTheDocument()
    expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(0)
    await user.clear(screen.getByLabelText('Cao nhất'))
    await user.type(screen.getByLabelText('Cao nhất'), '600000')
    await user.type(screen.getByLabelText(/Ngày đến hạn \(ngày mô phỏng\)/), '2026-12-26')
    await user.click(screen.getByRole('button', { name: 'Lưu khoản này' }))
    await waitFor(() => expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(1))
    expect(bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!).params.obligation).toMatchObject({
      kind: 'bill', cycle: 'yearly', amount_min_vnd: 450000, amount_max_vnd: 600000, due_date: '2026-12-26',
    })
  })

  it('sửa khoản: điền sẵn từ server, gửi obligation_id', async () => {
    const { calls } = mountApp(backend({ 'POST /actions': () => receiptAction() }), `/obligations/${TIEN_DIEN}`)
    const user = userEvent.setup()
    const name = await screen.findByDisplayValue('Tiền điện')
    expect(screen.getByLabelText('Thấp nhất')).toHaveValue('300.000')
    expect(screen.getByLabelText('Cao nhất')).toHaveValue('450.000')
    await user.clear(name)
    await user.type(name, 'Tiền điện nhà')
    await user.click(screen.getByRole('button', { name: 'Lưu khoản này' }))
    await waitFor(() => expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(1))
    expect(bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!).params.obligation).toMatchObject({ op: 'upsert', obligation_id: TIEN_DIEN, name: 'Tiền điện nhà', amount_min_vnd: 300000, amount_max_vnd: 450000 })
  })

  it('xóa khoản: có hộp xác nhận, chỉ ghi sau khi xác nhận; xong về danh sách', async () => {
    const { calls, router } = mountApp(backend({ 'POST /actions': () => receiptAction() }), `/obligations/${TIEN_DIEN}`)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Xóa khoản này' }))
    expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(0)
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Hủy' }))
    expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Xóa khoản này' }))
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Xóa' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/obligations'))
    expect(bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)).toEqual({ tool: 'update_profile', params: { obligation: { op: 'delete', obligation_id: TIEN_DIEN } } })
  })

  it('khoản Trả sau tự sinh không sửa hay xóa tay; id lạ thì báo không tìm thấy', async () => {
    const a = mountApp(backend(), `/obligations/${BNPL}`)
    expect(await screen.findByText(/không sửa hay xóa tay được/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Xóa khoản này' })).toBeNull()
    a.router.navigate('/obligations/00000000-0000-4000-8000-000000000000')
    expect(await screen.findByText(/Không tìm thấy khoản này/)).toBeInTheDocument()
  })
})

describe('Tiền vào và ô Tiền vào khác', () => {
  it('ghi lương: record_transaction income + loại do server liệt kê; biên nhận dẫn tới xác nhận lương', async () => {
    const { calls } = mountApp(
      backend({
        'POST /actions': () => restFixture('ActionResponse.receipt_action'), // fixture có follow_up confirm_salary
      }),
      '/income',
    )
    const user = userEvent.setup()
    await waitFor(() => expect(screen.getByTestId('other-income-amount')).toHaveTextContent('350.000 ₫'))
    expect(screen.getByRole('link', { name: 'Gán vào hũ' })).toHaveAttribute('href', '/move?from=tien_vao_khac')
    const submit = screen.getByRole('button', { name: 'Ghi nhận tiền vào' })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText('Số tiền'), '9000000')
    await user.click(await screen.findByRole('radio', { name: 'Lương' }))
    expect(screen.queryByRole('radio', { name: 'Ăn uống' })).toBeNull() // chỉ loại chiều "vào"
    await user.click(submit)
    const rcpt = await screen.findByTestId('income-receipt')
    const conf = bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)
    expect(conf.tool).toBe('record_transaction')
    expect(conf.params).toMatchObject({ kind: 'income', amount_vnd: 9000000, tx_type: 'salary' })
    expect(conf.params.client_ref).toMatch(/^ui-/)
    expect(within(rcpt).getByRole('link', { name: 'Xác nhận chia lương vào các hũ' })).toHaveAttribute('href', '/salary')
    await waitFor(() => expect(callsTo(calls, 'GET', '/overview').length).toBeGreaterThanOrEqual(2))
    await user.click(within(rcpt).getByRole('button', { name: 'Ghi tiếp một khoản' }))
    expect(screen.getByRole('button', { name: 'Ghi nhận tiền vào' })).toBeDisabled()
  })

  it('không có Tiền vào khác thì không có nút gán; lỗi server hiện tiếng Việt', async () => {
    mountApp(
      backend({
        'GET /overview': (() => { const o = restFixture('OverviewResponse.minh') as Json; o.balance.other_income_vnd = 0; return o })(),
        'POST /confirmations': json(400, { error: { code: 'PARAMS_INVALID', message: 'x' } }),
      }),
      '/income',
    )
    const user = userEvent.setup()
    await screen.findByTestId('other-income-amount')
    expect(screen.queryByRole('link', { name: 'Gán vào hũ' })).toBeNull()
    await user.type(screen.getByLabelText('Số tiền'), '1000')
    await user.click(await screen.findByRole('radio', { name: 'Lương' }))
    await user.click(screen.getByRole('button', { name: 'Ghi nhận tiền vào' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Thông tin gửi đi chưa hợp lệ')
  })
})

describe('Lương về (xác nhận một chạm)', () => {
  it('chia vào hũ: confirm_salary decision split; biên nhận giữ trên màn dù danh sách chờ đã làm mới', async () => {
    let applied = false
    const { calls } = mountApp(
      backend({
        'GET /salary-events': () => (applied ? { salary_events: [] } : restFixture('SalaryEventsResponse.pending')),
        'POST /actions': () => {
          applied = true
          return receiptAction((d) => { d.summary = 'Đã chia lương 9.500.000 ₫ vào 7 hũ'; d.jars_after = [{ code: 'an_uong', name: 'Ăn uống', balance_after_vnd: 3230000 }] })
        },
      }),
      '/salary',
    )
    const user = userEvent.setup()
    const card = await screen.findByRole('region', { name: /Lương về ngày/ })
    expect(card).toHaveTextContent('9.500.000 ₫')
    expect(screen.getByTestId('deviation')).toHaveTextContent('+5,56%')
    expect(within(card).queryByRole('checkbox')).toBeNull() // lệch ít thì không hỏi cập nhật lương
    await user.click(within(card).getByRole('button', { name: 'Chia vào các hũ' }))
    expect(await screen.findByTestId('salary-done')).toHaveTextContent('Đã chia lương 9.500.000 ₫ vào 7 hũ')
    expect(bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)).toEqual({ tool: 'confirm_salary', params: { salary_event_id: SALARY_EVENT, decision: 'split' } })
    await waitFor(() => expect(callsTo(calls, 'GET', '/salary-events').length).toBeGreaterThanOrEqual(2))
    expect(screen.getByTestId('salary-done')).toBeInTheDocument()
    expect(screen.getByTestId('salary-done')).toHaveTextContent('3.230.000 ₫')
  })

  it('lệch nhiều: hỏi có cập nhật lương đã khai không; giữ ở Tiền vào khác', async () => {
    const ev = restFixture('SalaryEventsResponse.pending') as Json
    ev.salary_events[0].ask_update_salary = true
    ev.salary_events[0].deviation_percent = -25
    const { calls } = mountApp(backend({ 'GET /salary-events': ev, 'POST /actions': () => receiptAction() }), '/salary')
    const user = userEvent.setup()
    const box = await screen.findByRole('checkbox')
    expect(screen.getByTestId('deviation')).toHaveTextContent('−25%')
    expect(box).not.toBeChecked() // mặc định không tự đổi lương
    await user.click(box)
    await user.click(screen.getByRole('button', { name: 'Chia vào các hũ' }))
    await waitFor(() => expect(callsTo(calls, 'POST', '/actions')).toHaveLength(1))
    // lời gọi đầu là xem trước (không kèm cờ cập nhật lương); lời gọi xin token để ghi là lời gọi cuối
    expect(bodyOf(callsTo(calls, 'POST', '/confirmations').at(-1)!).params).toEqual({ salary_event_id: SALARY_EVENT, decision: 'split', update_declared_salary: true })
  })

  it('giữ ở Tiền vào khác; không có lương chờ thì trạng thái rỗng; lỗi thì Thử lại', async () => {
    const { calls } = mountApp(backend({ 'POST /actions': () => receiptAction() }), '/salary')
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Giữ ở Tiền vào khác' }))
    await waitFor(() => expect(callsTo(calls, 'POST', '/actions')).toHaveLength(1))
    expect(bodyOf(callsTo(calls, 'POST', '/confirmations').at(-1)!).params).toEqual({ salary_event_id: SALARY_EVENT, decision: 'keep_as_other' })
  })

  it('rỗng và lỗi', async () => {
    let n = 0
    mountApp(backend({ 'GET /salary-events': () => (++n === 1 ? json(500, { error: { code: 'INTERNAL_ERROR', message: 'x' } }) : { salary_events: [] }) }), '/salary')
    const alert = await screen.findByRole('alert')
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByText('Không có lương nào chờ xác nhận')).toBeInTheDocument()
  })
})

describe('Chuyển giữa hũ và gán Tiền vào khác', () => {
  it('mở từ "Gán vào hũ": nguồn là Tiền vào khác, điền sẵn toàn bộ số đang có; ghi move_between_jars; biên nhận là khối receipt', async () => {
    const { calls } = mountApp(backend({ 'POST /actions': () => restFixture('ActionResponse.receipt') }), '/move?from=tien_vao_khac')
    const user = userEvent.setup()
    await waitFor(() => expect(screen.getByLabelText('Số tiền')).toHaveValue('350.000'))
    expect(screen.getByLabelText('Từ hũ')).toHaveValue('tien_vao_khac')
    const submit = screen.getByRole('button', { name: 'Chuyển tiền giữa hũ' })
    expect(submit).toBeDisabled() // chưa chọn hũ đích
    await user.selectOptions(screen.getByLabelText('Sang hũ'), 'an_uong')
    await user.click(submit)
    expect(await screen.findByTestId('move-receipt')).toHaveTextContent('Đã chuyển 100.000 ₫')
    expect(bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)).toEqual({ tool: 'move_between_jars', params: { from_jar: 'tien_vao_khac', to_jar: 'an_uong', amount_vnd: 350000 } })
  })

  it('mở từ Chi tiết hũ: hũ đích điền sẵn; số tiền lớn hơn số dư thì cảnh báo mềm', async () => {
    mountApp(backend(), '/move?to=an_uong')
    const user = userEvent.setup()
    await waitFor(() => expect(screen.getByLabelText('Sang hũ')).toHaveValue('an_uong'))
    await user.selectOptions(screen.getByLabelText('Từ hũ'), 'di_lai')
    await user.type(screen.getByLabelText('Số tiền'), '9000000')
    expect(screen.getByText(/lớn hơn số đang có ở hũ nguồn/)).toBeInTheDocument()
  })

  it('lỗi không đủ số dư từ server: hiện thông báo, khóa nút', async () => {
    mountApp(backend({ 'POST /confirmations': json(422, { error: { code: 'INSUFFICIENT_FUNDS', message: 'x' } }) }), '/move?to=an_uong')
    const user = userEvent.setup()
    await waitFor(() => expect(screen.getByLabelText('Sang hũ')).toHaveValue('an_uong'))
    await user.selectOptions(screen.getByLabelText('Từ hũ'), 'di_lai')
    await user.type(screen.getByLabelText('Số tiền'), '100000')
    // lỗi hiện sớm ở bản xem trước do server tính, trước khi bấm chuyển
    expect(await screen.findByRole('alert')).toHaveTextContent('không đủ số dư')
    expect(screen.getByRole('button', { name: 'Chuyển tiền giữa hũ' })).toBeDisabled()
  })
})

describe('Hồ sơ', () => {
  it('hiện tên hiển thị của server và thông tin khai báo', async () => {
    mountApp(backend(), '/profile')
    const declared = await screen.findByTestId('profile-declared')
    expect(screen.getByTestId('profile-name')).toHaveTextContent('Minh')
    expect(declared).toHaveTextContent('9.000.000 ₫')
    expect(declared).toHaveTextContent('Ngày 5 hằng tháng')
    expect(declared).toHaveTextContent('Vừa')
  })

  it('sửa lương và ngày nhận: chỉ gửi trường đã đổi; làm mới dữ liệu', async () => {
    const { calls } = mountApp(backend({ 'POST /actions': () => receiptAction() }), '/profile')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Sửa' }))
    const save = screen.getByRole('button', { name: 'Lưu thay đổi' })
    expect(save).toBeDisabled() // chưa đổi gì
    const salary = screen.getByLabelText('Lương thực nhận mỗi tháng')
    await user.clear(salary)
    await user.type(salary, '9500000')
    await user.click(save)
    await waitFor(() => expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(1))
    expect(bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)).toEqual({ tool: 'update_profile', params: { monthly_salary_vnd: 9500000 } })
    await waitFor(() => expect(callsTo(calls, 'GET', '/overview').length).toBeGreaterThanOrEqual(2))
  })

  it('ngày nhận ngoài 1..31 bị chặn', async () => {
    mountApp(backend(), '/profile')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Sửa' }))
    const day = screen.getByLabelText('Ngày nhận lương (1 đến 31)')
    await user.clear(day)
    await user.type(day, '45')
    expect(screen.getByText('Nhập ngày từ 1 đến 31')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Lưu thay đổi' })).toBeDisabled()
  })

  it('lối vào Nghĩa vụ, Thêm hoặc sửa hũ, Tiền vào, Hoạt động', async () => {
    mountApp(backend(), '/profile')
    const nav = await screen.findByRole('region', { name: 'Quản lý' })
    expect(within(nav).getByRole('link', { name: /Nghĩa vụ/ })).toHaveAttribute('href', '/obligations')
    expect(within(nav).getByRole('link', { name: /Thêm hoặc sửa hũ/ })).toHaveAttribute('href', '/jars/edit')
    expect(within(nav).getByRole('link', { name: /Hoạt động/ })).toHaveAttribute('href', '/activity')
  })
})

describe('Thêm hoặc sửa hũ', () => {
  it('sửa tỷ lệ cho đủ 100% rồi lưu bằng save_jars; chưa đổi thì nút Lưu tắt', async () => {
    const { calls, router } = mountApp(backend({ 'POST /actions': () => receiptAction() }), '/jars/edit')
    const user = userEvent.setup()
    const save = await screen.findByRole('button', { name: 'Lưu các hũ' })
    await screen.findByLabelText('Tỷ lệ chia lương của Ăn uống')
    expect(save).toBeDisabled()
    const a = screen.getByLabelText('Tỷ lệ chia lương của Ăn uống')
    await user.clear(a)
    await user.type(a, '25')
    expect(save).toBeDisabled() // tổng 95%
    const d = screen.getByLabelText('Tỷ lệ chia lương của Dự phòng')
    await user.clear(d)
    await user.type(d, '15')
    expect(save).toBeEnabled()
    await user.click(save)
    await waitFor(() => expect(router.state.location.pathname).toBe('/jars'))
    const conf = bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)
    expect(conf.tool).toBe('save_jars')
    expect(conf.params.jars.find((j: Json) => j.code === 'an_uong').split_percent).toBe(25)
    expect(conf.params.jars.find((j: Json) => j.code === 'du_phong').split_percent).toBe(15)
  })

  it('hũ còn tiền bị server từ chối bỏ (JAR_PROTECTED): báo bằng tiếng Việt', async () => {
    mountApp(backend({ 'POST /confirmations': json(422, { error: { code: 'JAR_PROTECTED', message: 'x' } }) }), '/jars/edit')
    const user = userEvent.setup()
    const a = await screen.findByLabelText('Tỷ lệ chia lương của Ăn uống')
    await user.clear(a)
    await user.type(a, '25')
    const d = screen.getByLabelText('Tỷ lệ chia lương của Dự phòng')
    await user.clear(d)
    await user.type(d, '15')
    await user.click(screen.getByRole('button', { name: 'Lưu các hũ' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Hũ hệ thống, hũ còn tiền hoặc còn nghĩa vụ')
  })
})

describe('Hoạt động', () => {
  const tx = (id: string, merchant: string, extra: Json = {}): Json => ({
    id,
    occurred_at: '2026-12-09T11:20:00Z',
    app_date: '2026-11-20',
    kind: 'expense',
    jar: 'an_uong',
    amount_vnd: -45000,
    merchant,
    funding_source: 'jar',
    ...extra,
  })
  const page = (transactions: Json[], next?: string): Json => ({ app_date: '2026-11-21', as_of: '2026-12-10T03:00:00Z', transactions, ...(next ? { next_cursor: next } : {}) })

  it('danh sách có phân trang bằng con trỏ: Tải thêm truyền lại nguyên văn next_cursor, không trùng dòng', async () => {
    const { calls } = mountApp(
      backend({
        'GET /transactions': (_i, u) =>
          u.searchParams.get('cursor') === 'CUR2'
            ? page([tx('0a1b2c3d-1111-4222-8333-000000000002', 'Phở'), tx('0a1b2c3d-1111-4222-8333-000000000001', 'Cà phê')])
            : page([tx('0a1b2c3d-1111-4222-8333-000000000001', 'Cà phê')], 'CUR2'),
      }),
      '/activity',
    )
    const user = userEvent.setup()
    const list = await screen.findByTestId('activity-list')
    expect(within(list).getAllByRole('listitem')).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Tải thêm' }))
    await waitFor(() => expect(within(screen.getByTestId('activity-list')).getAllByRole('listitem')).toHaveLength(2))
    expect(screen.getByText('Đã hết giao dịch.')).toBeInTheDocument()
    const reqs = callsTo(calls, 'GET', '/transactions').map((c) => new URL(c.url).searchParams)
    expect(reqs[0]!.get('cursor')).toBeNull()
    expect(reqs[1]!.get('cursor')).toBe('CUR2')
    expect(reqs[1]!.get('limit')).toBe('20')
  })

  it('lọc theo hũ và theo "Cần xem lại" gọi lại với tham số; lọc từ đường dẫn sâu', async () => {
    const { calls } = mountApp(backend(), '/activity?review=1')
    await screen.findByTestId('activity-list')
    const first = new URL(callsTo(calls, 'GET', '/transactions')[0]!.url).searchParams
    expect(first.get('needs_review')).toBe('true')
    expect(screen.getByRole('button', { name: 'Cần xem lại' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Ăn uống' }))
    await waitFor(() => expect(callsTo(calls, 'GET', '/transactions').some((c) => new URL(c.url).searchParams.get('jar') === 'an_uong')).toBe(true))
    const last = new URL(callsTo(calls, 'GET', '/transactions').at(-1)!.url).searchParams
    expect(last.get('jar')).toBe('an_uong')
    expect(last.get('needs_review')).toBeNull()
  })

  it('nhãn nguồn Trả sau lấy từ hạn mức, "Cần xem lại" được đánh dấu', async () => {
    mountApp(
      backend({ 'GET /transactions': page([tx('0a1b2c3d-1111-4222-8333-000000000003', 'Cửa hàng', { funding_source: 'credit', needs_review: true })]) }),
      '/activity',
    )
    const list = await screen.findByTestId('activity-list')
    expect(list).toHaveTextContent('Trả sau (mô phỏng)')
    expect(list).toHaveTextContent('Cần xem lại')
  })

  it('rỗng, lỗi và tải thêm lỗi đều có trạng thái', async () => {
    let n = 0
    mountApp(backend({ 'GET /transactions': () => (++n === 1 ? json(500, { error: { code: 'INTERNAL_ERROR', message: 'x' } }) : page([])) }), '/activity')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Chưa tải được giao dịch')
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByText('Chưa có giao dịch')).toBeInTheDocument()
  })

  it('tải thêm lỗi: báo và cho thử lại, danh sách đã có giữ nguyên', async () => {
    let n = 0
    mountApp(
      backend({
        'GET /transactions': (_i, u) => (u.searchParams.get('cursor') && ++n === 1 ? json(503, { error: { code: 'DATABASE_UNAVAILABLE', message: 'x' } }) : page([tx('0a1b2c3d-1111-4222-8333-000000000004', 'Phở')], 'C')),
      }),
      '/activity',
    )
    const user = userEvent.setup()
    await screen.findByTestId('activity-list')
    await user.click(screen.getByRole('button', { name: 'Tải thêm' }))
    expect(await screen.findByText('Chưa tải thêm được. Thử lại nhé.')).toBeInTheDocument()
    expect(within(screen.getByTestId('activity-list')).getAllByRole('listitem')).toHaveLength(1)
  })
})
