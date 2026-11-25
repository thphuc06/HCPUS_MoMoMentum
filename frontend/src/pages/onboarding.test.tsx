import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { restFixture } from '@/test/fixtures'
import { backend, bodyOf, callsTo, json, mountApp } from '@/test/mountApp'

// Onboarding O1–O3 cho tài khoản chưa khai: chỉ lương và ngày nhận là bắt buộc; ghi qua /confirmations → /actions
// (update_profile, save_jars).

type Json = Record<string, any>
beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

/** Backend giả có trạng thái: tài khoản trắng cho tới khi `update_profile` đầu tiên được áp dụng. */
function onboardingBackend(extra: Parameters<typeof backend>[0] = {}) {
  const state = { onboarded: false }
  const routes = {
    'GET /overview': () => (state.onboarded ? restFixture('OverviewResponse.minh') : restFixture('OverviewResponse.blank')),
    'POST /actions': (init: RequestInit) => {
      const b = JSON.parse(String(init.body)) as Json
      if (b.tool === 'update_profile' && !b.params.obligation) state.onboarded = true
      return { ...(restFixture('ActionResponse.receipt_action') as Json), data: { ...(restFixture('ActionResponse.receipt_action') as Json).data, follow_up: undefined } }
    },
    ...extra,
  }
  return { state, handler: backend(routes) }
}

const salaryInput = () => screen.getByLabelText('Lương thực nhận mỗi tháng (bắt buộc)')

describe('O1 lương và ngày nhận (bắt buộc)', () => {
  it('Tiếp tục chỉ bật khi có đủ lương và ngày nhận; ngày ngoài 1..31 không hợp lệ', async () => {
    const { handler } = onboardingBackend()
    mountApp(handler, '/onboarding')
    const user = userEvent.setup()
    const next = await screen.findByRole('button', { name: 'Tiếp tục' })
    expect(screen.getByText(/Chỉ cần lương và ngày nhận là bắt buộc/)).toBeInTheDocument()
    expect(next).toBeDisabled()
    await user.type(salaryInput(), '9000000')
    expect(salaryInput()).toHaveValue('9.000.000')
    expect(next).toBeDisabled() // thiếu ngày nhận
    await user.click(screen.getByRole('radio', { name: 'Ngày khác' }))
    await user.type(screen.getByLabelText('Ngày trong tháng (1 đến 31)'), '32')
    expect(next).toBeDisabled()
    await user.clear(screen.getByLabelText('Ngày trong tháng (1 đến 31)'))
    await user.type(screen.getByLabelText('Ngày trong tháng (1 đến 31)'), '28')
    expect(next).toBeEnabled()
  })

  it('chỉ khai lương và ngày nhận rồi vào được Tổng quan: update_profile qua /confirmations → /actions, các bước sau bỏ qua được', async () => {
    const { handler } = onboardingBackend()
    const { calls, router } = mountApp(handler, '/onboarding')
    const user = userEvent.setup()
    await screen.findByRole('button', { name: 'Tiếp tục' })
    await user.type(salaryInput(), '9000000')
    await user.click(screen.getByRole('radio', { name: '5' }))
    await user.click(screen.getByRole('button', { name: 'Tiếp tục' }))

    // O2 hiện các hũ do server tạo (đọc lại Tổng quan sau khi ghi)
    expect(await screen.findByRole('heading', { name: 'Chia lương vào các hũ' })).toBeInTheDocument()
    const conf = bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)
    expect(conf).toEqual({ tool: 'update_profile', params: { monthly_salary_vnd: 9000000, payday_day: 5 } })
    expect(bodyOf(callsTo(calls, 'POST', '/actions')[0]!)).toMatchObject({ tool: 'update_profile', confirm_token: 'aaa.bbb', params: { monthly_salary_vnd: 9000000, payday_day: 5 } })

    await user.click(await screen.findByRole('button', { name: 'Bỏ qua, dùng gợi ý này' }))
    expect(await screen.findByRole('heading', { name: 'Chi phí cố định' })).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: /^Xong/ }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/'))
    expect(await screen.findByTestId('balance-total')).toBeInTheDocument() // vào được Tổng quan
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(1) // O2, O3 bỏ qua thì không ghi thêm
  })

  it('lỗi từ server hiện bằng tiếng Việt, ở lại O1', async () => {
    const { handler } = onboardingBackend({ 'POST /confirmations': json(422, { error: { code: 'PROFILE_INCOMPLETE', message: 'x' } }) })
    mountApp(handler, '/onboarding')
    const user = userEvent.setup()
    await screen.findByRole('button', { name: 'Tiếp tục' })
    await user.type(salaryInput(), '9000000')
    await user.click(screen.getByRole('radio', { name: '5' }))
    await user.click(screen.getByRole('button', { name: 'Tiếp tục' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Bạn cần khai lương và ngày nhận lương')
    expect(screen.getByRole('heading', { name: /mình bắt đầu từ lương nhé/ })).toBeInTheDocument()
  })

  it('chào bằng tên hiển thị do server trả (không lấy từ email)', async () => {
    const { handler } = onboardingBackend()
    mountApp(handler, '/onboarding')
    expect(await screen.findByRole('heading', { name: /Chào giamkhao9/ })).toBeInTheDocument()
  })
})

describe('O2 hũ và tỷ lệ chia', () => {
  async function openO2() {
    const state = { onboarded: true }
    const handler = backend({ 'GET /overview': restFixture('OverviewResponse.minh') })
    void state
    const m = mountApp(handler, '/onboarding') // đã khai lương: mở lại giữa chừng thì bắt đầu từ O2
    await screen.findByRole('heading', { name: 'Chia lương vào các hũ' })
    await screen.findByLabelText('Tỷ lệ chia lương của Ăn uống')
    return m
  }

  it('hiện hũ và tỷ lệ của server, tổng 100% thì báo đủ', async () => {
    await openO2()
    const list = screen.getByRole('list', { name: 'Các hũ và tỷ lệ chia lương' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(7)
    expect(screen.getByLabelText('Tỷ lệ chia lương của Ăn uống')).toHaveValue('30')
    expect(screen.getByTestId('split-total')).toHaveTextContent('Tổng đủ 100%')
  })

  it('giữ vai trò và ngày đã cam kết khi sửa tỷ lệ bộ sáu hũ', async () => {
    const overview = restFixture('OverviewResponse.minh') as Json
    const defaults = [
      { code: 'chi_hang_ngay', name: 'Chi hằng ngày', kind: 'spending', split_percent: 35 },
      { code: 'nghia_vu', name: 'Nghĩa vụ', kind: 'obligation', split_percent: 35 },
      { code: 'du_phong', name: 'Dự phòng', kind: 'saving', purpose: 'buffer', split_percent: 15 },
      { code: 'quy_don', name: 'Quỹ dồn', kind: 'saving', purpose: 'sinking', split_percent: 5, goal_vnd: 920000, goal_date: '2027-01-03' },
      { code: 'muc_tieu', name: 'Mục tiêu', kind: 'saving', purpose: 'goal', split_percent: 5 },
      { code: 'tich_luy_dai_han', name: 'Tích lũy dài hạn', kind: 'saving', purpose: 'long_term', split_percent: 5, goal_date: '2029-01-01' },
    ].map((j) => ({ color_key: 'teal', icon_key: 'wallet', balance_vnd: 0, ...j }))
    const { calls } = mountApp(backend({ 'GET /overview': { ...overview, jars: defaults } }), '/onboarding')
    const user = userEvent.setup()
    const list = await screen.findByRole('list', { name: 'Các hũ và tỷ lệ chia lương' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(6)
    const sinking = list.querySelector('[data-jar-row="quy_don"]') as HTMLElement
    expect(within(sinking).getByLabelText('Ngày dự kiến')).toHaveAttribute('readonly')
    expect(within(sinking).getByLabelText('Mục đích của Quỹ dồn')).toHaveValue('sinking')
    const dailySplit = screen.getByLabelText('Tỷ lệ chia lương của Chi hằng ngày')
    const sinkingSplit = screen.getByLabelText('Tỷ lệ chia lương của Quỹ dồn')
    await user.clear(dailySplit)
    await user.type(dailySplit, '34')
    await user.clear(sinkingSplit)
    await user.type(sinkingSplit, '6')
    await user.click(screen.getByRole('button', { name: 'Tiếp tục' }))
    await screen.findByRole('heading', { name: 'Chi phí cố định' })
    const { params } = bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)
    expect(params.jars).toContainEqual(expect.objectContaining({
      code: 'quy_don', purpose: 'sinking', split_percent: 6, goal_vnd: 920000, goal_date: '2027-01-03',
    }))
    expect(params.jars).toContainEqual(expect.objectContaining({
      code: 'tich_luy_dai_han', purpose: 'long_term', goal_date: '2029-01-01',
    }))
  })

  it('tổng khác 100% thì không cho tiếp tục và nói rõ tổng hiện tại', async () => {
    await openO2()
    const user = userEvent.setup()
    const pct = screen.getByLabelText('Tỷ lệ chia lương của Ăn uống')
    await user.clear(pct)
    await user.type(pct, '35')
    expect(screen.getByTestId('split-total')).toHaveTextContent('Tổng đang là 105%, cần đúng 100%')
    expect(screen.getByRole('button', { name: 'Tiếp tục' })).toBeDisabled()
    await user.clear(pct)
    await user.type(pct, 'abc')
    expect(screen.getByTestId('split-total')).toHaveTextContent('chưa hợp lệ')
  })

  it('sửa tỷ lệ cho đủ 100% rồi Tiếp tục: save_jars thay cả danh sách theo thứ tự, giữ mã hũ và mục tiêu đã có', async () => {
    const { calls } = await openO2()
    const user = userEvent.setup()
    const a = screen.getByLabelText('Tỷ lệ chia lương của Ăn uống')
    await user.clear(a)
    await user.type(a, '35')
    const h = screen.getByLabelText('Tỷ lệ chia lương của Hóa đơn')
    await user.clear(h)
    await user.type(h, '26')
    expect(screen.getByTestId('split-total')).toHaveTextContent('Tổng đủ 100%')
    await user.click(screen.getByRole('button', { name: 'Tiếp tục' }))
    expect(await screen.findByRole('heading', { name: 'Chi phí cố định' })).toBeInTheDocument()

    const conf = bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)
    expect(conf.tool).toBe('save_jars')
    expect(conf.params.jars).toHaveLength(7)
    expect(conf.params.jars[0]).toMatchObject({ code: 'an_uong', name: 'Ăn uống', kind: 'spending', split_percent: 35 })
    expect(conf.params.jars[2]).toMatchObject({ code: 'hoa_don', split_percent: 26 })
    expect(conf.params.jars[4]).toMatchObject({ code: 'du_lich', goal_vnd: 6000000, goal_date: '2027-04-01' })
    expect(conf.params.jars.map((j: Json) => j.split_percent).reduce((s: number, v: number) => s + v, 0)).toBe(100)
  })

  it('thêm hũ từ mẫu (không có mã, server sinh) và bỏ hũ còn tiền thì bị khóa', async () => {
    await openO2()
    // hũ còn tiền không bỏ được
    expect(screen.getByRole('button', { name: 'Hũ Ăn uống còn tiền nên chưa bỏ được' })).toBeDisabled()
    // mẫu fixture chỉ có hai hũ đã có ở danh sách nên không còn gợi ý thêm
    expect(screen.queryByText('Thêm hũ')).toBeNull()
  })
})

describe('O3 chi phí cố định (tùy chọn)', () => {
  it('thêm một khoản: update_profile với nghĩa vụ; danh sách cập nhật; bỏ qua được', async () => {
    const { calls } = mountApp(backend({ 'GET /overview': restFixture('OverviewResponse.minh') }), '/onboarding')
    const user = userEvent.setup()
    await screen.findByRole('heading', { name: 'Chia lương vào các hũ' })
    await user.click(await screen.findByRole('button', { name: 'Bỏ qua, dùng gợi ý này' }))
    await screen.findByRole('heading', { name: 'Chi phí cố định' })
    await user.click(screen.getByRole('button', { name: 'Thêm khoản' }))
    await user.type(screen.getByLabelText('Tên khoản'), 'Tiền trọ')
    await user.type(screen.getByLabelText('Số tiền mỗi kỳ'), '2500000')
    await user.type(screen.getByLabelText('Ngày đến hạn trong tháng'), '1')
    await user.click(screen.getByRole('button', { name: 'Lưu khoản này' }))
    await waitFor(() => expect(callsTo(calls, 'POST', '/actions')).toHaveLength(1))
    const conf = bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)
    expect(conf).toEqual({
      tool: 'update_profile',
      params: { obligation: { op: 'upsert', kind: 'rent', name: 'Tiền trọ', cycle: 'monthly', is_essential: true, amount_vnd: 2500000, due_day: 1, pay_jar: 'nghia_vu' } },
    })
    expect(screen.getByText(/Khoản trả sau không cần khai/)).toBeInTheDocument()
  })

  it('form hiện lỗi từng trường khi bỏ trống, không gọi API', async () => {
    const { calls } = mountApp(backend({ 'GET /overview': restFixture('OverviewResponse.minh') }), '/onboarding')
    const user = userEvent.setup()
    await screen.findByRole('heading', { name: 'Chia lương vào các hũ' })
    await user.click(await screen.findByRole('button', { name: 'Bỏ qua, dùng gợi ý này' }))
    await user.click(await screen.findByRole('button', { name: 'Thêm khoản' }))
    await user.click(screen.getByRole('button', { name: 'Lưu khoản này' }))
    expect(screen.getByText('Nhập tên khoản')).toBeInTheDocument()
    expect(screen.getByText('Nhập số tiền lớn hơn 0')).toBeInTheDocument()
    expect(screen.getByText('Nhập ngày từ 1 đến 31')).toBeInTheDocument()
    expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(0)
  })
})
