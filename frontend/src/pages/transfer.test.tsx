import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { restFixture, validBlock } from '@/test/fixtures'
import { backend, bodyOf, callsTo, json, mountApp, type Call } from '@/test/mountApp'
import { transferParams } from '@/features/transfer/params'

// Luồng chuyển tiền T1 → T2 → T4 → T5 với REST giả: chọn người nhận, bàn phím số, nguồn tiền (hũ hoặc Trả sau mô phỏng),
// xem lại, xác nhận qua /confirmations → /actions, biên nhận do server trả.

type Json = Record<string, any>
const TRANSFER_TX_TYPE = 'transfer_person' // mã do server đặt; giao diện tìm theo is_person_transfer, test dùng mã này làm dữ liệu
const HUY = '6f1e2d3c-4b5a-4968-8777-665544332211'

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

const receipt = (over: (d: Json) => void = () => {}): Json => {
  const r = restFixture('ActionResponse.receipt_action') as Json
  r.data.summary = 'Đã chuyển 250.000 ₫ cho Trần Quang Huy'
  r.data.amount_vnd = 250000
  r.data.jars_after = [{ code: 'hoa_don', name: 'Hóa đơn', balance_after_vnd: 200000 }]
  r.data.details = [{ label: 'Phí', value: '0 ₫' }]
  delete r.data.follow_up
  over(r.data)
  return r
}

async function pickPayee(user: ReturnType<typeof userEvent.setup>) {
  const book = await screen.findByRole('region', { name: 'Danh bạ' }, { timeout: 3000 })
  await user.click(within(book).getByRole('button', { name: /Trần Quang Huy/ }))
}

async function typeAmount(user: ReturnType<typeof userEvent.setup>, digits: string[]) {
  // Trang T2 tải theo route (chunk riêng): chờ nút đầu tiên hiện.
  for (const d of digits) await user.click(await screen.findByRole('button', { name: d }))
}

async function chooseSource(user: ReturnType<typeof userEvent.setup>, name: RegExp) {
  await user.click(await screen.findByRole('radio', { name }))
}

describe('T1 chọn người nhận', () => {
  it('danh bạ từ GET /payees, tìm kiếm lọc theo tên; Quét QR và nhập số mới vô hiệu có nhãn "Sắp có"', async () => {
    mountApp(backend(), '/transfer')
    const book = await screen.findByRole('region', { name: 'Danh bạ' })
    expect(within(book).getAllByRole('button')).toHaveLength(2)
    expect(within(book).getByText('xxxx 4821')).toBeInTheDocument() // chỉ phần đã che, không số đầy đủ
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Tìm người nhận'), 'mai')
    expect(within(book).getAllByRole('button')).toHaveLength(1)
    expect(within(book).getByText('Lê Thị Mai')).toBeInTheDocument()
    await user.clear(screen.getByLabelText('Tìm người nhận'))
    await user.type(screen.getByLabelText('Tìm người nhận'), 'zzz')
    expect(screen.getByText('Không tìm thấy')).toBeInTheDocument()
    for (const b of screen.getAllByRole('button', { name: /Quét QR|Nhập số điện thoại mới/ })) {
      expect(b).toBeDisabled()
      expect(b).toHaveTextContent('Sắp có')
    }
    expect(screen.getByText(/không chuyển tiền thật/)).toBeInTheDocument()
  })

  it('danh bạ rỗng: nói thật', async () => {
    mountApp(backend({ 'GET /payees': { payees: [] } }), '/transfer')
    expect(await screen.findByText('Chưa có người nhận nào')).toBeInTheDocument()
  })

  it('lỗi tải: thông báo và Thử lại', async () => {
    let n = 0
    mountApp(backend({ 'GET /payees': () => (++n === 1 ? json(500, { error: { code: 'INTERNAL_ERROR', message: 'x' } }) : restFixture('PayeesResponse.default')) }), '/transfer')
    const alert = await screen.findByRole('alert')
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByRole('region', { name: 'Danh bạ' })).toBeInTheDocument()
  })
})

describe('T2 số tiền và nguồn tiền', () => {
  it('bàn phím số: gõ, "000", xóa, chip chọn nhanh; hiển thị chấm nghìn và số tiền bằng chữ', async () => {
    mountApp(backend(), '/transfer')
    const user = userEvent.setup()
    await pickPayee(user)
    expect(await screen.findByTestId('amount-display')).toHaveTextContent('0')
    await typeAmount(user, ['2', '5', '0', '000'])
    expect(screen.getByTestId('amount-display')).toHaveTextContent('250.000')
    expect(screen.getByTestId('amount-words')).toHaveTextContent('Bằng chữ: hai trăm năm mươi nghìn đồng')
    await user.click(screen.getByRole('button', { name: 'Xóa chữ số cuối' }))
    expect(screen.getByTestId('amount-display')).toHaveTextContent('25.000')
    await user.click(screen.getByRole('button', { name: '200.000' }))
    expect(screen.getByTestId('amount-display')).toHaveTextContent('200.000')
    expect(screen.getByRole('button', { name: '200.000' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('"Kiểm tra trước khi chuyển" chỉ bật khi có số tiền và đã chọn nguồn tiền', async () => {
    mountApp(backend(), '/transfer')
    const user = userEvent.setup()
    await pickPayee(user)
    const next = await screen.findByRole('button', { name: 'Kiểm tra trước khi chuyển' })
    expect(next).toBeDisabled()
    await typeAmount(user, ['1', '000'])
    expect(next).toBeDisabled() // chưa có nguồn
    await chooseSource(user, /Hũ Hóa đơn/)
    expect(next).toBeEnabled()
    expect(screen.getByTestId('source-label')).toHaveTextContent('Trả từ hũ Hóa đơn')
  })

  it('nguồn Trả sau (mô phỏng): nhãn và hạn mức còn lại lấy từ GET /credit-line', async () => {
    mountApp(backend(), '/transfer')
    const user = userEvent.setup()
    await pickPayee(user)
    await chooseSource(user, /Trả sau \(mô phỏng\)/)
    expect(screen.getByTestId('source-label')).toHaveTextContent('Trả bằng Trả sau (mô phỏng)')
    expect(screen.getByText('Hạn mức còn 4.700.000 ₫')).toBeInTheDocument()
    expect(screen.getByLabelText(/Tính vào hũ/)).toBeInTheDocument()
  })

  it('chưa có hạn mức: lựa chọn Trả sau bị vô hiệu và nói thật', async () => {
    mountApp(backend({ 'GET /credit-line': restFixture('CreditLineResponse.none') }), '/transfer')
    const user = userEvent.setup()
    await pickPayee(user)
    const r = await screen.findByRole('radio', { name: /Trả sau/ })
    await waitFor(() => expect(r).toBeDisabled())
    expect(r).toHaveTextContent('Chưa có hạn mức')
  })

  it('số tiền lớn hơn số dư hũ: cảnh báo mềm (server mới là bên quyết định)', async () => {
    mountApp(backend(), '/transfer')
    const user = userEvent.setup()
    await pickPayee(user)
    await chooseSource(user, /Hũ Hóa đơn/)
    await typeAmount(user, ['9', '000', '000'])
    expect(screen.getByRole('status')).toHaveTextContent('Số tiền lớn hơn số dư của hũ này')
  })

  it('vào thẳng T2 hoặc T4 khi chưa chọn người nhận thì quay về T1', async () => {
    const a = mountApp(backend(), '/transfer/amount')
    await waitFor(() => expect(a.router.state.location.pathname).toBe('/transfer'))
  })
})

async function toReview(user: ReturnType<typeof userEvent.setup>, source: RegExp, digits = ['2', '5', '0', '000'], note?: string) {
  await pickPayee(user)
  await typeAmount(user, digits)
  await chooseSource(user, source)
  if (note) await user.type(screen.getByPlaceholderText('Lời nhắn (tùy chọn)'), note)
  await user.click(screen.getByRole('button', { name: 'Kiểm tra trước khi chuyển' }))
  // T3: thẻ kiểm tra của server; đi tiếp sang T4 bằng "Tiếp tục" (xanh) hoặc "Vẫn chuyển" (vàng, đỏ).
  await user.click(await screen.findByRole('button', { name: /^(Tiếp tục|Vẫn chuyển)/ }))
}

async function toCheck(user: ReturnType<typeof userEvent.setup>, source: RegExp, digits = ['2', '5', '0', '000']) {
  await pickPayee(user)
  await typeAmount(user, digits)
  await chooseSource(user, source)
  await user.click(screen.getByRole('button', { name: 'Kiểm tra trước khi chuyển' }))
  await screen.findByTestId('afford-headline')
}

describe('T3 kiểm tra trước khi chuyển (POST /affordability)', () => {
  it('gọi /affordability với số tiền, nguồn và hũ người dùng chọn; vẽ thẻ XANH: chữ "Đủ", từng hũ, nút "Tiếp tục" sang T4', async () => {
    const { calls, router } = mountApp(backend(), '/transfer')
    const user = userEvent.setup()
    await toCheck(user, /Hũ Hóa đơn/)
    const req = bodyOf(callsTo(calls, 'POST', '/affordability')[0]!)
    expect(req).toEqual({ amount_vnd: 250000, funding_source: 'jar', jar: 'hoa_don', label: 'Trần Quang Huy' })
    expect(screen.getByTestId('check-amount')).toHaveTextContent('250.000 ₫')
    const card = document.querySelector('[data-block="affordability_card"]')!
    expect(card).toHaveAttribute('data-verdict', 'ok')
    expect(within(card as HTMLElement).getAllByText('Đủ').length).toBeGreaterThan(0)
    expect(card.querySelectorAll('ul[aria-label="Kiểm tra từng hũ"] [data-jar]')).toHaveLength(3)
    expect(screen.queryByRole('button', { name: /Vì sao/ })).toBeNull() // màn hình không có bản ghi lượt agent để giải thích
    // chưa ghi gì
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Tiếp tục' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/transfer/review'))
  })

  it('thẻ ĐỎ/VÀNG: chữ "Hụt", "Vẫn chuyển 250.000 ₫", "Đổi nguồn", "Trả bằng Trả sau (mô phỏng)"; chi phí của món TÁCH khỏi tổng phải trả ngày đến hạn', async () => {
    const short = validBlock('affordability_card.transfer_an_uong_short')
    const { router } = mountApp(backend({ 'POST /affordability': short }), '/transfer')
    const user = userEvent.setup()
    await toCheck(user, /Hũ Ăn uống/)
    const card = document.querySelector('[data-block="affordability_card"]') as HTMLElement
    expect(card).toHaveAttribute('data-verdict', 'short')
    expect(within(card).getAllByText('Hụt').length).toBeGreaterThan(0)
    expect(screen.getByTestId('item-cost')).toHaveTextContent('250.000 ₫')
    expect(screen.getByTestId('total-due')).toHaveTextContent('1.250.000 ₫')
    expect(screen.getByRole('button', { name: /^Vẫn chuyển 250\.000/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Đổi nguồn' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Trả bằng Trả sau (mô phỏng)' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/transfer/review'))
    // nguồn đã đổi sang Trả sau: T4 nêu "Trả sau"
    expect(await screen.findByTestId('review-source')).toHaveTextContent('Trả sau (mô phỏng)')
  })

  it('"Vẫn chuyển" giữ nguồn và sang T4; "Đổi nguồn" bỏ nguồn đã chọn và về T2 để chọn lại', async () => {
    const short = validBlock('affordability_card.transfer_an_uong_short')
    const a = mountApp(backend({ 'POST /affordability': short }), '/transfer')
    const user = userEvent.setup()
    await toCheck(user, /Hũ Ăn uống/)
    await user.click(screen.getByRole('button', { name: 'Đổi nguồn' }))
    await waitFor(() => expect(a.router.state.location.pathname).toBe('/transfer/amount'))
    expect(await screen.findByTestId('source-label')).toHaveTextContent('Chọn nguồn tiền')
    expect(screen.getByTestId('amount-display')).toHaveTextContent('250.000') // giữ số tiền đã nhập
  })

  it('nguồn Trả sau: gửi funding_source credit (không gửi jar) và vẽ phần Trả sau là chính', async () => {
    const credit = validBlock('affordability_card.credit_only')
    const { calls } = mountApp(backend({ 'POST /affordability': credit }), '/transfer')
    const user = userEvent.setup()
    await toCheck(user, /Trả sau \(mô phỏng\)/)
    const req = bodyOf(callsTo(calls, 'POST', '/affordability')[0]!)
    expect(req).toEqual({ amount_vnd: 250000, funding_source: 'credit', label: 'Trần Quang Huy' })
    expect(screen.getByTestId('afford-credit')).toBeInTheDocument()
    expect(screen.getByTestId('total-due')).toHaveTextContent('1.250.000 ₫')
    expect(screen.queryByRole('button', { name: 'Trả bằng Trả sau (mô phỏng)' })).toBeNull() // đang chọn rồi
  })

  it('lỗi ở bước kiểm tra không chặn: báo bằng tiếng Việt, cho Thử lại hoặc bỏ qua để xem lại', async () => {
    let n = 0
    const { router } = mountApp(
      backend({ 'POST /affordability': () => (++n === 1 ? json(503, { error: { code: 'DATABASE_UNAVAILABLE', message: 'x' } }) : validBlock('affordability_card.transfer_250k')) }),
      '/transfer',
    )
    const user = userEvent.setup()
    await pickPayee(user)
    await typeAmount(user, ['2', '5', '0', '000'])
    await chooseSource(user, /Hũ Hóa đơn/)
    await user.click(screen.getByRole('button', { name: 'Kiểm tra trước khi chuyển' }))
    const err = await screen.findByTestId('check-error')
    expect(err).toHaveTextContent('Hệ thống đang khởi động')
    await user.click(within(err).getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByTestId('afford-headline')).toBeInTheDocument()
    expect(n).toBe(2)
    void router
  })

  it('bỏ qua kiểm tra khi lỗi: sang T4', async () => {
    const { router } = mountApp(backend({ 'POST /affordability': json(404, { error: { code: 'PARAMS_INVALID', message: 'x' } }) }), '/transfer')
    const user = userEvent.setup()
    await pickPayee(user)
    await typeAmount(user, ['2', '5', '0', '000'])
    await chooseSource(user, /Hũ Hóa đơn/)
    await user.click(screen.getByRole('button', { name: 'Kiểm tra trước khi chuyển' }))
    await user.click(await screen.findByRole('button', { name: 'Bỏ qua kiểm tra, xem lại' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/transfer/review'))
  })

  it('vào thẳng T3 khi chưa chọn nguồn thì về T2; chưa chọn người nhận thì về T1', async () => {
    const a = mountApp(backend(), '/transfer/check')
    await waitFor(() => expect(a.router.state.location.pathname).toBe('/transfer'))
  })
})

describe('T4 xem lại, xác nhận và T5 biên nhận', () => {
  it('trả từ hũ: /confirmations với tham số đúng thứ người dùng chọn → /actions kèm token → biên nhận của server; dữ liệu được làm mới', async () => {
    const { calls } = mountApp(backend({ 'POST /actions': () => receipt() }), '/transfer')
    const user = userEvent.setup()
    await toReview(user, /Hũ Hóa đơn/, ['2', '5', '0', '000'], 'Tiền điện nước chia đôi')

    expect(await screen.findByTestId('review-amount')).toHaveTextContent('250.000 ₫')
    expect(screen.getByTestId('review-source')).toHaveTextContent('Hũ Hóa đơn')
    expect(screen.getByTestId('review-source')).toHaveTextContent('Hiện còn 450.000 ₫')
    expect(screen.getByText('Tiền điện nước chia đôi')).toBeInTheDocument()
    expect(screen.queryByTestId('credit-fee-note')).toBeNull()
    // xem trước do server tính (POST /confirmations không ghi gì); chưa bấm xác nhận thì chưa ghi gì
    await waitFor(() => expect(screen.getByTestId('preview')).toHaveTextContent('180.000 ₫'))
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: /Xác nhận chuyển 250.000/ }))
    expect(await screen.findByTestId('transfer-receipt')).toBeInTheDocument()

    const conf = bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)
    expect(conf.tool).toBe('record_transaction')
    expect(conf.params).toMatchObject({ kind: 'expense', amount_vnd: 250000, funding: 'jar', jar: 'hoa_don', payee_id: HUY, note: 'Tiền điện nước chia đôi', tx_type: TRANSFER_TX_TYPE })
    expect(conf.params.client_ref).toMatch(/^ui-[0-9a-f-]{36}$/)
    expect(conf).not.toHaveProperty('conversation_id') // màn hình không có khối confirm
    expect(conf).not.toHaveProperty('confirm_block_id')
    const act = bodyOf(callsTo(calls, 'POST', '/actions')[0]!)
    expect(act).toMatchObject({ tool: 'record_transaction', confirm_token: 'aaa.bbb' })
    expect(act.params).toEqual(conf.params) // đúng thứ token đã ký (server trả lại bản chuẩn hóa)

    // biên nhận: mọi số từ server, giao diện không tự tính
    expect(screen.getByRole('heading', { name: 'Đã chuyển 250.000 ₫ cho Trần Quang Huy' })).toBeInTheDocument()
    expect(screen.getByText('Hũ Hóa đơn còn lại')).toBeInTheDocument()
    expect(screen.getByText('200.000 ₫')).toBeInTheDocument()
    expect(screen.getByTestId('receipt-ref')).toBeInTheDocument()
    // làm mới tổng quan sau khi ghi
    await waitFor(() => expect(callsTo(calls, 'GET', '/overview').length).toBeGreaterThanOrEqual(2))
  })

  it('trả bằng Trả sau: gửi funding credit (không có hũ nếu không chọn), nêu biểu phí có nguồn, KHÔNG tự cộng tổng', async () => {
    const { calls } = mountApp(
      backend({
        'POST /confirmations': (init) => {
          const b = JSON.parse(String(init.body))
          return {
            confirm_token: 'aaa.bbb',
            expires_at: '2026-12-10T03:02:00Z',
            ttl_seconds: 120,
            tool: b.tool,
            params: b.params,
            params_hash: 'a'.repeat(64),
            preview: {
              summary: 'Mua 300.000 ₫ bằng Trả sau (mô phỏng)',
              changes: [
                { label: 'Phải trả ngày 05/12', before: 'chưa có', after: '333.000 ₫' },
                { label: 'Hạn mức còn lại', before: '4.700.000 ₫', after: '4.400.000 ₫' },
              ],
              warnings: ['Phí dịch vụ 33.000 ₫ đã tính vào số phải trả'],
            },
          }
        },
        'POST /actions': () =>
          receipt((d) => {
            d.summary = 'Đã ghi chi 300.000 ₫ bằng Trả sau (mô phỏng)'
            d.jars_after = []
            d.details = [{ label: 'Nghĩa vụ mới', value: '333.000 ₫ đến hạn 05/12' }]
          }),
      }),
      '/transfer',
    )
    const user = userEvent.setup()
    await toReview(user, /Trả sau \(mô phỏng\)/, ['3', '0', '0', '0', '0', '0'])
    const note = await screen.findByTestId('credit-fee-note')
    await waitFor(() => expect(note).toHaveTextContent('Phí 33.000 ₫')) // biểu phí tải từ GET /credit-line
    expect(note).toHaveTextContent('Nguồn: Biểu phí công khai')
    // 300.000 + 33.000: giao diện không tự cộng, tổng gồm phí là dòng xem trước do server tính
    await waitFor(() => expect(screen.getByTestId('preview')).toHaveTextContent('Phải trả ngày 05/12'))
    expect(screen.getByTestId('preview')).toHaveTextContent('333.000 ₫')
    expect(note.textContent).not.toContain('333.000')

    await user.click(screen.getByRole('button', { name: /Xác nhận chuyển 300\.000/ }))
    expect(await screen.findByTestId('transfer-receipt')).toBeInTheDocument()
    const conf = bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)
    expect(conf.params).toMatchObject({ kind: 'expense', amount_vnd: 300000, funding: 'credit', payee_id: HUY })
    expect(conf.params).not.toHaveProperty('jar')
    // tổng phải trả gồm phí đến từ server, trong biên nhận
    expect(screen.getByText('333.000 ₫ đến hạn 05/12')).toBeInTheDocument()
  })

  it.each([
    ['INSUFFICIENT_FUNDS', 422, 'Hũ nguồn không đủ số dư'],
    ['CREDIT_LIMIT_EXCEEDED', 422, 'Vượt hạn mức Trả sau'],
    ['DUPLICATE_TRANSACTION', 409, 'Giao dịch này đã được ghi rồi'],
  ])('lỗi %s từ server: hiện sớm ở bản xem trước bằng tiếng Việt và khóa nút xác nhận (bấm lại vô ích)', async (code, status, text) => {
    const { calls } = mountApp(backend({ 'POST /confirmations': json(status, { error: { code, message: 'x' } }) }), '/transfer')
    const user = userEvent.setup()
    await toReview(user, /Hũ Hóa đơn/)
    expect(await screen.findByRole('alert')).toHaveTextContent(text)
    expect(screen.getByRole('button', { name: /Xác nhận chuyển/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Quay lại sửa' })).toBeEnabled()
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(0)
  })

  it('lỗi tạm thời (Aurora đang thức dậy) ngay ở bản xem trước: vẫn cho bấm xác nhận, chỉ ghi một lần khi thành công', async () => {
    let n = 0
    const { calls } = mountApp(
      backend({
        'POST /confirmations': (init) => {
          if (++n === 1) return json(503, { error: { code: 'DATABASE_UNAVAILABLE', message: 'x' } })
          const b = JSON.parse(String(init.body))
          return { confirm_token: 'aaa.bbb', expires_at: '2026-12-10T03:02:00Z', ttl_seconds: 120, tool: b.tool, params: b.params, params_hash: 'a'.repeat(64) }
        },
        'POST /actions': () => receipt(),
      }),
      '/transfer',
    )
    const user = userEvent.setup()
    await toReview(user, /Hũ Hóa đơn/)
    expect(await screen.findByRole('alert')).toHaveTextContent('Hệ thống đang khởi động')
    const retry = screen.getByRole('button', { name: /Xác nhận chuyển/ })
    expect(retry).toBeEnabled()
    await user.click(retry)
    expect(await screen.findByTestId('transfer-receipt')).toBeInTheDocument()
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(1)
    // cùng một mã chống ghi trùng cho mọi lần gọi (xem trước lẫn ghi)
    const refs = callsTo(calls, 'POST', '/confirmations').map((c: Call) => bodyOf(c).params.client_ref)
    expect(refs.length).toBeGreaterThanOrEqual(2)
    expect(new Set(refs).size).toBe(1)
  })

  it('"Quay lại sửa" giữ nguyên số đã nhập', async () => {
    mountApp(backend(), '/transfer')
    const user = userEvent.setup()
    await toReview(user, /Hũ Hóa đơn/)
    await user.click(await screen.findByRole('button', { name: 'Quay lại sửa' }))
    expect(await screen.findByTestId('amount-display')).toHaveTextContent('250.000')
    expect(screen.getByTestId('source-label')).toHaveTextContent('Trả từ hũ Hóa đơn')
  })
})

describe('transferParams (thuần hàm)', () => {
  const base = { amountVnd: 100000, payeeId: HUY, note: '  ', clientRef: 'ui-1', txTypes: [] as never[] }

  it('không gửi tx_type khi bảng tra của server không có loại chuyển cho người khác; lời nhắn trống thì bỏ', () => {
    expect(transferParams({ ...base, source: { kind: 'jar', code: 'an_uong' } })).toEqual({
      kind: 'expense',
      amount_vnd: 100000,
      funding: 'jar',
      payee_id: HUY,
      client_ref: 'ui-1',
      jar: 'an_uong',
    })
  })

  it('có loại is_person_transfer (chiều chi) thì gửi, không gõ cứng mã; Trả sau chỉ gửi hũ khi người dùng chọn', () => {
    const txTypes = [{ tx_type: TRANSFER_TX_TYPE, label: 'Chuyển', direction: 'out' as const, is_person_transfer: true }]
    expect(transferParams({ ...base, txTypes, source: { kind: 'credit' } })).toMatchObject({ funding: 'credit', tx_type: TRANSFER_TX_TYPE })
    expect(transferParams({ ...base, txTypes, source: { kind: 'credit' } })).not.toHaveProperty('jar')
    expect(transferParams({ ...base, txTypes, source: { kind: 'credit' }, creditJar: 'giai_tri', note: 'a' })).toMatchObject({ jar: 'giai_tri', note: 'a' })
    // không đánh dấu is_person_transfer thì không gửi tx_type, dù mã trùng tên
    expect(transferParams({ ...base, txTypes: [{ ...txTypes[0]!, is_person_transfer: undefined }], source: { kind: 'credit' } })).not.toHaveProperty('tx_type')
    // loại cùng tên nhưng chiều "in" thì không dùng
    expect(transferParams({ ...base, txTypes: [{ ...txTypes[0]!, direction: 'in' as const }], source: { kind: 'credit' } })).not.toHaveProperty('tx_type')
  })
})

describe('Trả sau: hũ trả khi đến hạn (ví không có hũ nghĩa vụ)', () => {
  // Tổng quan của fixture, bỏ loại "obligation" khỏi mọi hũ: server khi đó không có hũ trả mặc định và đòi pay_jar.
  const withoutObligationJar = (): Json => {
    const o = restFixture('OverviewResponse.minh') as Json
    for (const j of o.jars) if (j.kind === 'obligation') j.kind = 'spending'
    return o
  }
  const PAY_JAR = 'Hũ trả khi đến hạn'

  it('hiện ô chọn hũ trả (chỉ hũ người dùng), chưa chọn thì không đi tiếp; chọn rồi thì gửi pay_jar trong record_transaction', async () => {
    const o = withoutObligationJar()
    const { calls } = mountApp(backend({ 'GET /overview': o, 'POST /actions': () => receipt() }), '/transfer')
    const user = userEvent.setup()
    await pickPayee(user)
    await typeAmount(user, ['2', '5', '0', '000'])
    await chooseSource(user, /Trả sau \(mô phỏng\)/)
    const picker = await screen.findByLabelText(PAY_JAR)
    const options = within(picker).getAllByRole('option').filter((op) => (op as HTMLOptionElement).value !== '')
    expect(options.map((op) => (op as HTMLOptionElement).value)).toEqual(o.jars.map((j: Json) => j.code))
    for (const s of o.system_jars) expect(within(picker).queryByRole('option', { name: s.name })).toBeNull()
    const next = screen.getByRole('button', { name: 'Kiểm tra trước khi chuyển' })
    expect(next).toBeDisabled()

    const chosen = o.jars[0]
    await user.selectOptions(picker, chosen.code)
    expect(next).toBeEnabled()
    await user.click(next)
    await user.click(await screen.findByRole('button', { name: /^(Tiếp tục|Vẫn chuyển)/ }))
    const confirmBtn = await screen.findByRole('button', { name: /Xác nhận chuyển/ })
    await waitFor(() => expect(confirmBtn).toBeEnabled())
    await user.click(confirmBtn)
    expect(await screen.findByTestId('transfer-receipt')).toBeInTheDocument()
    const conf = bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)
    expect(conf.params).toMatchObject({ funding: 'credit', pay_jar: chosen.code })
    expect(bodyOf(callsTo(calls, 'POST', '/actions')[0]!).params).toEqual(conf.params)
  })

  it('"Trả bằng Trả sau" ở bước kiểm tra: chưa chọn hũ trả thì về bước nguồn tiền để chọn, không vào xem lại cụt đường', async () => {
    const short = validBlock('affordability_card.transfer_an_uong_short')
    const { router } = mountApp(backend({ 'GET /overview': withoutObligationJar(), 'POST /affordability': short }), '/transfer')
    const user = userEvent.setup()
    await toCheck(user, /Hũ Ăn uống/)
    await user.click(screen.getByRole('button', { name: 'Trả bằng Trả sau (mô phỏng)' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/transfer/amount'))
    expect(await screen.findByLabelText(PAY_JAR)).toBeInTheDocument()
  })

  it('kiểm tra trước khi chi bằng Trả sau gửi pay_jar đã chọn tới POST /affordability (không có thì server trả PARAMS_INVALID)', async () => {
    const o = withoutObligationJar()
    const { calls } = mountApp(backend({ 'GET /overview': o }), '/transfer')
    const user = userEvent.setup()
    await pickPayee(user)
    await typeAmount(user, ['2', '5', '0', '000'])
    await chooseSource(user, /Trả sau \(mô phỏng\)/)
    const chosen = o.jars[1]
    await user.selectOptions(await screen.findByLabelText(PAY_JAR), chosen.code)
    await user.click(screen.getByRole('button', { name: 'Kiểm tra trước khi chuyển' }))
    await screen.findByRole('button', { name: /^(Tiếp tục|Vẫn chuyển)/ })
    const req = bodyOf(callsTo(calls, 'POST', '/affordability')[0]!)
    expect(req).toMatchObject({ amount_vnd: 250000, funding_source: 'credit', pay_jar: chosen.code })
  })

  it('ví có hũ nghĩa vụ: kiểm tra Trả sau không gửi pay_jar (server tự chọn hũ nghĩa vụ)', async () => {
    const { calls } = mountApp(backend(), '/transfer')
    const user = userEvent.setup()
    await toReview(user, /Trả sau \(mô phỏng\)/)
    const req = bodyOf(callsTo(calls, 'POST', '/affordability')[0]!)
    expect(req).toMatchObject({ funding_source: 'credit' })
    expect(req).not.toHaveProperty('pay_jar')
  })

  it('ví có hũ nghĩa vụ: không hiện ô chọn và gửi đúng tham số như trước (không có pay_jar)', async () => {
    const { calls } = mountApp(backend({ 'POST /actions': () => receipt() }), '/transfer')
    const user = userEvent.setup()
    await toReview(user, /Trả sau \(mô phỏng\)/)
    const confirmBtn = await screen.findByRole('button', { name: /Xác nhận chuyển/ })
    await waitFor(() => expect(confirmBtn).toBeEnabled())
    await user.click(confirmBtn)
    await screen.findByTestId('transfer-receipt')
    const conf = bodyOf(callsTo(calls, 'POST', '/confirmations')[0]!)
    const txTypes = (restFixture('TxTypesResponse.default') as Json).tx_types
    const today = transferParams({ amountVnd: 250000, source: { kind: 'credit' }, payeeId: HUY, note: '', clientRef: conf.params.client_ref, txTypes })
    expect(conf.params).toEqual(today)
    expect(conf.params).not.toHaveProperty('pay_jar')
  })

  it('chọn hũ trên bước nguồn tiền chỉ hiện khi ví thiếu hũ nghĩa vụ', async () => {
    mountApp(backend(), '/transfer')
    const user = userEvent.setup()
    await pickPayee(user)
    await chooseSource(user, /Trả sau \(mô phỏng\)/)
    expect(screen.getByLabelText(/Tính vào hũ/)).toBeInTheDocument()
    expect(screen.queryByLabelText(PAY_JAR)).toBeNull()
  })
})
