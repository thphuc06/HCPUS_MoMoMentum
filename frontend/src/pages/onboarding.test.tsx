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

/** Bấm một nút của bản xem trước khi nó bật (nút chờ bản xem trước của server về mới bật). */
async function clickWhenEnabled(user: ReturnType<typeof userEvent.setup>, name: string, scope: HTMLElement = document.body) {
  const button = await within(scope).findByRole('button', { name })
  await waitFor(() => expect(button).toBeEnabled())
  await user.click(button)
}

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
    await clickWhenEnabled(user, 'Đồng ý')
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
    // Bước 4: bản xem trước của server hiện trước, chỉ Đồng ý mới ghi
    const review = await screen.findByTestId('save-jars-review')
    expect(await within(review).findByText('Xem trước thao tác')).toBeInTheDocument()
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(0)
    await clickWhenEnabled(user, 'Đồng ý', review)
    expect(await screen.findByRole('heading', { name: 'Chi phí cố định' })).toBeInTheDocument()
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(1)

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

describe('O3 đề xuất tỷ lệ theo số đã khai (bước 3, bước 4 của lộ trình)', () => {
  const SALARY_EVENT = '7e1f3a90-2c4b-4d6e-8f01-a3b5c7d9e0f2'
  const serverPreview = {
    summary: 'Lưu 4 hũ và tỷ lệ chia lương',
    changes: [
      { label: 'Lý do: hũ Nghĩa vụ', after: 'Nghĩa vụ đã khai 3.095.000 ₫/tháng = 34,4% lương 9.000.000 ₫' },
      { label: 'Hũ Nghĩa vụ', before: '33% · 2.970.000 ₫/kỳ', after: '35% · 3.150.000 ₫/kỳ (+180.000 ₫)' },
      { label: 'Hũ Chi hằng ngày', before: '42% · 3.780.000 ₫/kỳ', after: '28% · 2.520.000 ₫/kỳ (−1.260.000 ₫)' },
    ],
    warnings: ['Tỷ lệ mới áp từ lần chia lương đầu tiên sau khi lưu. Dự báo tính lại ngay sau khi lưu.'],
  }
  const confirmations = (init: RequestInit) => {
    const b = JSON.parse(String(init.body)) as Json
    return {
      confirm_token: 'aaa.bbb', expires_at: '2026-12-10T03:02:00Z', ttl_seconds: 120, tool: b.tool, params: b.params,
      params_hash: 'a'.repeat(64), preview: b.tool === 'save_jars' ? serverPreview : { summary: 'Xem trước', changes: [{ label: 'x', after: 'y' }] },
    }
  }
  const base = (over: Json): Json => ({ app_date: '2026-11-21', as_of: '2026-12-10T03:00:00Z', salary_vnd: 9000000, ...over })

  async function openO3(routes: Parameters<typeof backend>[0]) {
    const m = mountApp(backend({ 'GET /overview': restFixture('OverviewResponse.minh'), 'POST /confirmations': confirmations, ...routes }), '/onboarding')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Bỏ qua, dùng gợi ý này' }))
    await screen.findByRole('heading', { name: 'Chi phí cố định' })
    return { ...m, user }
  }

  it('lệch từ 1 điểm: thẻ nêu khoản thiếu, xem trước của server có lý do và tiền mỗi kỳ; Đồng ý gửi đúng tham số server dựng', async () => {
    const proposal = restFixture('SplitProposalResponse.proposed') as Json
    const { calls, user } = await openO3({ 'POST /jars/split-proposal': proposal })
    const card = await screen.findByTestId('split-proposal')
    expect(card).toHaveAttribute('data-status', 'proposed')
    expect(within(card).getByTestId('proposal-shortfall')).toHaveTextContent(/thiếu 375\.000\s₫ cho Tiền điện/)
    const review = within(card).getByTestId('save-jars-review')
    expect(await within(review).findByText('35% · 3.150.000 ₫/kỳ (+180.000 ₫)')).toBeInTheDocument()
    expect(within(review).getByText(/Nghĩa vụ đã khai 3\.095\.000 ₫\/tháng/)).toBeInTheDocument()
    expect(within(review).getByText(/Dự báo tính lại ngay/)).toBeInTheDocument() // trong phần mở rộng
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(0) // chưa ghi gì trước khi đồng ý
    await clickWhenEnabled(user, 'Đồng ý', review)
    await waitFor(() => expect(callsTo(calls, 'POST', '/actions')).toHaveLength(1))
    const sent = bodyOf(callsTo(calls, 'POST', '/actions')[0]!)
    expect(sent.tool).toBe('save_jars')
    expect(sent.params).toEqual(proposal.params)
    expect(await screen.findByTestId('split-saved')).toHaveTextContent('Dự báo đang tính lại')
  })

  it('Không đổi thì không ghi; Sửa số mở trình sửa với tỷ lệ server đề xuất', async () => {
    const proposal = restFixture('SplitProposalResponse.proposed')
    const { calls, user } = await openO3({ 'POST /jars/split-proposal': proposal })
    const card = await screen.findByTestId('split-proposal')
    await clickWhenEnabled(user, 'Sửa số', card)
    expect(await screen.findByLabelText('Tỷ lệ chia lương của Nghĩa vụ')).toHaveValue('35')
    expect(screen.getByLabelText('Tỷ lệ chia lương của Quỹ dồn')).toHaveValue('12')
    expect(screen.getByLabelText('Tỷ lệ chia lương của Chi hằng ngày')).toHaveValue('28')
    await user.click(screen.getByRole('button', { name: 'Xem trước tỷ lệ này' }))
    await clickWhenEnabled(user, 'Không đổi', screen.getByTestId('save-jars-review'))
    expect(await screen.findByText('Giữ tỷ lệ đang đặt.')).toBeInTheDocument()
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(0)
  })

  it('khoản biết trước: tên, số tiền, ngày cần gửi lên server để tính Quỹ dồn', async () => {
    const seen: Json[] = []
    const { user } = await openO3({
      'POST /jars/split-proposal': (init) => {
        seen.push(JSON.parse(String(init.body || '{}')) as Json)
        return restFixture('SplitProposalResponse.proposed')
      },
    })
    await user.click(screen.getByRole('button', { name: 'Thêm khoản biết trước' }))
    await user.click(screen.getByRole('button', { name: 'Thêm khoản này' }))
    expect(screen.getByText('Nhập tên khoản')).toBeInTheDocument()
    expect(screen.getByText('Chọn ngày sau hôm nay')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Tên khoản biết trước'), 'Tết')
    await user.type(screen.getByLabelText('Số tiền cần'), '3000000')
    await user.type(screen.getByLabelText('Ngày cần'), '2027-02-10')
    await user.click(screen.getByRole('button', { name: 'Thêm khoản này' }))
    await waitFor(() => expect(seen.at(-1)).toEqual({ sinking_items: [{ name: 'Tết', amount_vnd: 3000000, needed_date: '2027-02-10' }] }))
    expect(seen[0]).toEqual({}) // chưa khai khoản nào thì chỉ tính theo nghĩa vụ đã khai
    expect(within(screen.getByRole('list', { name: 'Khoản biết trước đã thêm' })).getByText('Tết')).toBeInTheDocument()
  })

  it('bỏ qua kê khai: giữ tỷ lệ mẫu, hũ Nghĩa vụ ghi "chưa có số khai"; không ghi gì', async () => {
    const jars = [
      { code: 'chi_hang_ngay', name: 'Chi hằng ngày', kind: 'spending', split_before: 42, split_after: 42 },
      { code: 'nghia_vu', name: 'Nghĩa vụ', kind: 'obligation', split_before: 33, split_after: 33 },
      { code: 'du_phong', name: 'Dự phòng', kind: 'saving', purpose: 'buffer', split_before: 25, split_after: 25 },
    ]
    const { calls } = await openO3({ 'POST /jars/split-proposal': base({ status: 'no_declarations', obligation_basis: 'template', jars }) })
    const card = await screen.findByTestId('split-proposal')
    expect(card).toHaveAttribute('data-status', 'no_declarations')
    expect(card.querySelector('[data-jar-code="nghia_vu"]')).toHaveTextContent('chưa có số khai')
    expect(card.querySelector('[data-jar-code="chi_hang_ngay"]')).not.toHaveTextContent('chưa có số khai')
    expect(within(card).queryByRole('button')).toBeNull()
    expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(0)
  })

  it('nghĩa vụ vượt số chia được: không lưu tỷ lệ, liệt kê theo ưu tiên, mở lộ trình', async () => {
    const infeasible = base({
      status: 'infeasible',
      required_percent: 112,
      obligation_basis: 'declared',
      reasons: [{ jar_code: 'nghia_vu', text: 'Nghĩa vụ đã khai 9.200.000 ₫/tháng = 102,2% lương 9.000.000 ₫' }],
      priority_obligations: [
        { id: '9a4d0e11-6b2c-4f3a-8d5e-1c7b9a3f5e21', name: 'Tiền trọ', kind: 'rent', cycle: 'monthly', amount_vnd: 4000000, monthly_vnd: 4000000, is_essential: true },
        { id: '9a4d0e11-6b2c-4f3a-8d5e-1c7b9a3f5e22', name: 'Tiền điện', kind: 'bill', cycle: 'monthly', amount_vnd: 700000, monthly_vnd: 700000, is_essential: true },
        { id: '9a4d0e11-6b2c-4f3a-8d5e-1c7b9a3f5e23', name: 'Khoản vay', kind: 'loan', cycle: 'monthly', amount_vnd: 4500000, monthly_vnd: 4500000, is_essential: false },
      ],
      jars: [{ code: 'nghia_vu', name: 'Nghĩa vụ', kind: 'obligation', split_before: 33, split_after: 33 }],
    })
    const { calls, router, user } = await openO3({ 'POST /jars/split-proposal': infeasible })
    const card = await screen.findByTestId('split-proposal')
    expect(card).toHaveTextContent('cần 112% lương')
    const items = within(within(card).getByRole('list', { name: 'Nghĩa vụ theo thứ tự ưu tiên' })).getAllByRole('listitem')
    expect(items.map((li) => li.textContent?.split(/\d/)[0])).toEqual(['Tiền trọ', 'Tiền điện', 'Khoản vay'])
    expect(within(card).queryByRole('button', { name: /Đồng ý/ })).toBeNull()
    await user.click(within(card).getByRole('button', { name: 'Mở lộ trình' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/roadmap'))
    expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(0)
  })

  it('lương nhận lệch quá ngưỡng: hỏi cập nhật lương trước khi đề xuất', async () => {
    const mismatch = base({
      status: 'salary_mismatch',
      salary_check: { salary_event_id: SALARY_EVENT, received_vnd: 7000000, declared_vnd: 9000000, deviation_percent: -22.22 },
      jars: [],
    })
    const { calls, user } = await openO3({ 'POST /jars/split-proposal': mismatch })
    const card = await screen.findByTestId('split-proposal')
    expect(card).toHaveTextContent(/Lương nhận 7\.000\.000\s₫ lệch 22,2%/)
    await user.click(within(card).getByRole('button', { name: /Cập nhật lương thành 7\.000\.000/ }))
    await waitFor(() => expect(callsTo(calls, 'POST', '/actions')).toHaveLength(1))
    expect(bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)).toEqual({ tool: 'update_profile', params: { monthly_salary_vnd: 7000000 } })
  })

  it('có lương chờ chia: hỏi áp cho kỳ này hay từ kỳ sau; từ kỳ sau chia lương chờ theo tỷ lệ cũ rồi mới lưu', async () => {
    const overview = restFixture('OverviewResponse.minh') as Json
    overview.next_payday = { ...overview.next_payday, state: 'pending_confirmation', salary_event_id: SALARY_EVENT }
    const proposal = restFixture('SplitProposalResponse.proposed') as Json
    const { calls, user } = await openO3({ 'GET /overview': overview, 'POST /jars/split-proposal': proposal })
    const review = await screen.findByTestId('save-jars-review')
    expect(await within(review).findByRole('button', { name: 'Đồng ý, áp cho kỳ này' })).toBeInTheDocument()
    await clickWhenEnabled(user, 'Đồng ý, từ kỳ sau', review)
    await waitFor(() => expect(callsTo(calls, 'POST', '/actions')).toHaveLength(2))
    const actions = callsTo(calls, 'POST', '/actions').map((c) => bodyOf(c))
    expect(actions.map((a) => a.tool)).toEqual(['confirm_salary', 'save_jars'])
    expect(actions[0]!.params).toEqual({ salary_event_id: SALARY_EVENT, decision: 'split' })
    expect(actions[1]!.params).toEqual(proposal.params)
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
