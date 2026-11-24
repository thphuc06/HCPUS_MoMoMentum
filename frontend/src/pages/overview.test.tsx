import { cleanup, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ReviewListResponse } from '@/api/reviewSchemas'
import { restFixture, validBlock } from '@/test/fixtures'
import { backend, bodyOf, callsTo, json, mountApp, runCalls } from '@/test/mountApp'
import { runFinished, runStarted, sseResponse, textMessage } from '@/test/sse'

// Màn Tổng quan, Hũ, Chi tiết hũ, Nhìn trước với fixture hợp đồng: bình thường, rỗng, lỗi, chưa có dự báo, hũ hệ thống âm.

type Json = Record<string, any>
const overview = (patch: (o: Json) => void = () => {}) => {
  const o = restFixture('OverviewResponse.minh') as Json
  patch(o)
  return o
}

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

describe('Tổng quan', () => {
  it('thẻ số dư: tổng gồm hũ + Tiền vào khác + Chưa phân loại; dòng chưa xếp hũ ghi theo giá trị tuyệt đối', async () => {
    mountApp(backend())
    expect(await screen.findByTestId('balance-total')).toHaveTextContent('7.900.000 ₫')
    expect(screen.getByTestId('balance-jars')).toHaveTextContent('7.730.000 ₫')
    expect(screen.getByTestId('balance-other')).toHaveTextContent('350.000 ₫')
    const un = screen.getByTestId('balance-parts')
    expect(within(un).getByText('Đã chi, chưa xếp hũ')).toBeInTheDocument()
    expect(screen.getByTestId('balance-unclassified')).toHaveTextContent('180.000 ₫')
    expect(screen.getByText(/Ví mô phỏng · ngày mô phỏng 21\/11\/2026/)).toBeInTheDocument()
  })

  it('Chưa phân loại dương: nhãn "Chưa phân loại"; bằng 0: không hiện dòng', async () => {
    mountApp(backend({ 'GET /overview': overview((o) => { o.balance.unclassified_vnd = 40000; o.balance.total_vnd = 8120000 }) }))
    expect(await screen.findByTestId('balance-unclassified')).toHaveTextContent('40.000 ₫')
    expect(within(screen.getByTestId('balance-parts')).getByText('Chưa phân loại')).toBeInTheDocument()
  })

  it('hành động nhanh: Chuyển tiền, Tiền vào, Giữa hũ dẫn đi; không còn nút bị tắt "Kiểm tra · Sắp có"', async () => {
    mountApp(backend())
    const nav = await screen.findByRole('navigation', { name: 'Hành động nhanh' })
    expect(within(nav).getByRole('link', { name: /Chuyển tiền/ })).toHaveAttribute('href', '/transfer')
    expect(within(nav).getByRole('link', { name: /Tiền vào/ })).toHaveAttribute('href', '/income')
    expect(within(nav).getByRole('link', { name: /Giữa hũ/ })).toHaveAttribute('href', '/move')
    expect(within(nav).getAllByRole('link')).toHaveLength(3)
    expect(within(nav).queryByRole('button')).toBeNull()
    expect(nav).not.toHaveTextContent('Sắp có')
  })

  it('dải hũ: 7 thẻ, trạng thái đủ/sát/hụt có chữ; vạch dự báo chỉ ở hũ có số dự báo (hũ hụt)', async () => {
    mountApp(backend())
    const list = await screen.findByRole('list', { name: 'Danh sách hũ' })
    const cards = within(list).getAllByRole('article')
    expect(cards).toHaveLength(7)
    const an = list.querySelector('[data-jar="an_uong"]') as HTMLElement
    expect(an).toHaveAttribute('data-status', 'short')
    expect(within(an).getByText('Hụt · cạn 29/11')).toBeInTheDocument()
    expect(within(an).getByTestId('forecast-mark')).toBeInTheDocument()
    expect(within(list.querySelector('[data-jar="di_lai"]') as HTMLElement).getByText('Đủ')).toBeInTheDocument()
    expect(within(list.querySelector('[data-jar="hoa_don"]') as HTMLElement).getByText('Sát')).toBeInTheDocument()
    expect(list.querySelectorAll('[data-testid="forecast-mark"]')).toHaveLength(1)
  })

  it('thẻ chủ động: một việc, MiniTimeline có ngày cạn và ngày lương, nút theo server', async () => {
    mountApp(backend())
    const card = await screen.findByRole('region', { name: 'Việc cần làm hôm nay' })
    expect(within(card).getByText('Hũ Ăn uống dự kiến cạn ngày 29/11')).toBeInTheDocument()
    expect(within(card).getByTestId('mini-timeline')).toHaveAttribute('aria-label', expect.stringContaining('dự kiến cạn 29/11'))
    for (const name of ['Xem dự báo', 'Hỏi vì sao', 'Để sau', 'Ít nhắc loại này']) expect(within(card).getByRole('button', { name })).toBeInTheDocument()
    expect(screen.getAllByRole('region', { name: 'Việc cần làm hôm nay' })).toHaveLength(1)
  })

  it('"Hỏi vì sao" mở chat và gửi câu hỏi về đúng hũ đó cho agent', async () => {
    const { calls } = mountApp(
      backend({
        'POST /invocations': async (init) =>
          JSON.parse(String(init.body)).forwardedProps?.warmup ? sseResponse([runStarted(), runFinished()]) : sseResponse([runStarted(), ...textMessage('m1', 'Vì thế đó.'), runFinished()]),
      }),
    )
    await screen.findByTestId('balance-total')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Hỏi vì sao' }))
    // ChatSheet tải lazy, lần đầu chạy Vitest runner có thể cần thêm thời gian để nạp module.
    expect(await screen.findByTestId('chat-sheet', {}, { timeout: 10_000 })).toBeInTheDocument()
    await waitFor(() => expect(runCalls(calls)).toHaveLength(1))
    const msgs = bodyOf(runCalls(calls)[0]!).messages as Array<{ role: string; content: string }>
    expect(msgs.at(-1)).toMatchObject({ role: 'user', content: 'Vì sao hũ Ăn uống sắp cạn?' })
    expect(await screen.findByText('Vì thế đó.')).toBeInTheDocument()
  })

  it('"Xem dự báo" mở Chi tiết hũ và gọi GET /forecasts/{hũ}', async () => {
    const { router, calls } = mountApp(backend())
    await screen.findByTestId('balance-total')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Xem dự báo' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/jars/an_uong'))
    await screen.findByTestId('forecast-summary')
    expect(callsTo(calls, 'GET', '/forecasts/an_uong')).toHaveLength(1)
    expect(callsTo(calls, 'GET', '/jars/an_uong')).toHaveLength(1)
  })

  it('"Để sau" ẩn thẻ và nhớ trong ngày mô phỏng; "Ít nhắc loại này" ẩn cả loại và Hồ sơ cho bật lại', async () => {
    const user = userEvent.setup()
    mountApp(backend())
    await screen.findByRole('region', { name: 'Việc cần làm hôm nay' })
    await user.click(screen.getByRole('button', { name: 'Để sau' }))
    expect(screen.queryByRole('region', { name: 'Việc cần làm hôm nay' })).toBeNull()
    expect(localStorage.getItem('yofina.nudge.snoozed')).toContain('runout_warning:an_uong|2026-11-21')
  })

  it('Ít nhắc loại này: ẩn thẻ; trang Hồ sơ cho bật lại', async () => {
    const user = userEvent.setup()
    mountApp(backend())
    await screen.findByRole('region', { name: 'Việc cần làm hôm nay' })
    await user.click(screen.getByRole('button', { name: 'Ít nhắc loại này' }))
    expect(screen.queryByRole('region', { name: 'Việc cần làm hôm nay' })).toBeNull()
    expect(localStorage.getItem('yofina.nudge.muted')).toContain('runout_warning')
    await user.click(screen.getByRole('link', { name: 'Hồ sơ' }))
    await user.click(await screen.findByRole('button', { name: 'Bật lại lời nhắc' }))
    expect(localStorage.getItem('yofina.nudge.muted')).toBe('[]')
  })

  it('thẻ sai schema bị bỏ qua, phần còn lại của Tổng quan vẫn hiện', async () => {
    mountApp(backend({ 'GET /overview': overview((o) => { o.proactive_card = { type: 'proactive_card', nonsense: true } }) }))
    expect(await screen.findByTestId('balance-total')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Việc cần làm hôm nay' })).toBeNull()
  })

  it('Gần đây, nghĩa vụ sắp đến hạn và việc xếp hũ lấy từ server', async () => {
    mountApp(backend())
    const recent = await screen.findByTestId('recent-transactions')
    expect(within(recent).getByText('Quán cơm')).toBeInTheDocument()
    expect(within(recent).getByText(/−45\.000/)).toBeInTheDocument()
    const due = screen.getByTestId('obligations-due')
    expect(within(due).getByText('Tiền điện')).toBeInTheDocument()
    expect(within(due).getByText('Trả sau (mô phỏng)')).toBeInTheDocument()
    // Không đọc được hàng chờ daily_ask: dòng Việc cần làm dùng số tổng needs_review_count của /overview
    expect(await screen.findByRole('link', { name: /^3 giao dịch cần xem lại hũ/ })).toHaveAttribute('href', '/review')
  })

  it('dòng xếp hũ hiện số N lấy từ needs_review_count của server; không còn thẻ "Cần xem lại" riêng', async () => {
    mountApp(backend({ 'GET /overview': overview((o) => { o.needs_review_count = 7 }) }))
    const row = await screen.findByRole('link', { name: /^7 giao dịch cần xem lại hũ/ })
    expect(row).toHaveAttribute('href', '/review')
    expect(row.closest('[data-todo]')).toHaveAttribute('data-todo', 'review')
    expect(screen.queryByText(/^Cần xem lại \(/)).toBeNull()
  })

  it('dòng xếp hũ ẩn khi needs_review_count bằng 0', async () => {
    mountApp(backend({ 'GET /overview': overview((o) => { o.needs_review_count = 0 }) }))
    expect(await screen.findByTestId('balance-total')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Cần xem lại|xem lại hũ|xếp hũ/ })).toBeNull()
  })

  it('đã để sau câu hỏi gộp: MỘT dòng việc cần làm với tổng chưa xếp hũ của cả tập (daily_ask), dẫn tới Xem lại', async () => {
    const daily = ReviewListResponse.parse(restFixture('ReviewListResponse.daily_ask'))
    daily.data.count += 1
    daily.data.pending_total_vnd += daily.data.items[0]!.amount_vnd
    daily.data.ask!.status = 'skipped'
    const { calls, router } = mountApp(backend({
      'GET /review': (_init, url) => url.searchParams.get('mode') === 'daily_ask' ? daily : restFixture('ReviewListResponse.review'),
    }))
    // needs_review_count 3 của /overview đều là giao dịch chưa xếp hũ: không có phần "cần xem lại"
    const summary = await screen.findByRole('link', { name: /^3 giao dịch chưa xếp hũ 240\.000\s₫$/ })
    expect(summary).toHaveAttribute('href', '/review')
    expect(screen.getAllByRole('link', { name: /xếp hũ|xem lại/i })).toHaveLength(1)
    expect(screen.queryByRole('region', { name: 'Chọn hũ cho giao dịch hôm nay' })).toBeNull()
    expect(callsTo(calls, 'GET', '/review').map(({ url }) => new URL(url).search)).toEqual(['?mode=daily_ask'])
    await userEvent.setup().click(summary)
    expect(await screen.findByRole('heading', { name: 'Xem lại' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/review')
    expect(await screen.findByRole('region', { name: 'Giao dịch chưa xếp hũ' })).toBeInTheDocument()
  })

  it('câu hỏi gộp đang mở: thẻ chọn hũ hiện ngay, không kèm dòng tóm tắt trùng; phần "cần xem lại" còn lại thành một dòng', async () => {
    const daily = ReviewListResponse.parse(restFixture('ReviewListResponse.daily_ask'))
    mountApp(backend({ 'GET /review': daily }))
    const ask = await screen.findByRole('region', { name: 'Chọn hũ cho giao dịch hôm nay' })
    expect(ask).toHaveTextContent(/2 giao dịch · 180\.000\s₫/)
    expect(screen.queryByRole('link', { name: /chưa xếp hũ|chưa phân loại/ })).toBeNull()
    // 3 (needs_review_count) − 2 (đang hỏi) = 1 giao dịch Yofina đã tự xếp
    expect(screen.getByRole('link', { name: /^Xem lại 1 giao dịch Yofina đã tự xếp hũ/ })).toHaveAttribute('href', '/review')
  })

  it.each(['zero', 'error'])('giữ Tổng quan và không có dòng "chưa xếp hũ" khi review trả %s', async (state) => {
    const daily = ReviewListResponse.parse(restFixture('ReviewListResponse.daily_ask'))
    daily.data.ask!.status = 'answered'
    const empty = { ...daily, data: { ...daily.data, items: [], count: 0, pending_total_vnd: 0 } }
    const { calls } = mountApp(backend({ 'GET /review': state === 'zero' ? empty : json(503, { error: { code: 'UNAVAILABLE' } }) }))
    await waitFor(() => expect(callsTo(calls, 'GET', '/review')).toHaveLength(1))
    expect(await screen.findByTestId('balance-total')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Danh sách hũ' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /chưa xếp hũ/ })).toBeNull()
    expect(screen.queryByRole('region', { name: 'Chọn hũ cho giao dịch hôm nay' })).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('lương về chờ xác nhận: lối vào xác nhận một chạm khi thẻ chủ động không phải thẻ lương', async () => {
    mountApp(
      backend({
        'GET /overview': overview((o) => {
          o.next_payday = { ...o.next_payday, state: 'pending_confirmation', salary_event_id: '7e1f3a90-2c4b-4d6e-8f01-a3b5c7d9e0f2' }
          o.proactive_card = null
        }),
      }),
    )
    expect(await screen.findByRole('link', { name: /Lương về, chờ bạn xác nhận/ })).toHaveAttribute('href', '/salary')
  })

  it('chưa có dự báo: nói thật, hũ ghi "Chưa có dự báo", không đủ/sát/hụt giả', async () => {
    mountApp(
      backend({
        'GET /overview': overview((o) => {
          o.forecast = null
          o.proactive_card = null
          o.jars = o.jars.map((j: Json) => ({ code: j.code, name: j.name, color_key: j.color_key, icon_key: j.icon_key, kind: j.kind, balance_vnd: j.balance_vnd, split_percent: j.split_percent }))
        }),
      }),
    )
    expect(await screen.findByText('Chưa có dự báo', { selector: 'h3 span' })).toBeInTheDocument()
    const list = screen.getByRole('list', { name: 'Danh sách hũ' })
    expect(within(list).getAllByText('Chưa có dự báo')).toHaveLength(7)
    expect(within(list).queryByText('Đủ')).toBeNull()
  })

  it('ước lượng ban đầu và số liệu cũ được báo rõ', async () => {
    mountApp(backend({ 'GET /overview': overview((o) => { o.forecast = { ...o.forecast, is_initial_estimate: true, history_days: 18, coverage: 0.38 } }) }))
    expect(await screen.findByText('Dự báo mới là ước lượng ban đầu')).toBeInTheDocument()
    expect(screen.getByText(/Mới có 18 ngày dữ liệu, độ phủ 38%/)).toBeInTheDocument()
  })

  it('skeleton khi tải; lỗi thì hiện thông báo tiếng Việt và Thử lại gọi lại', async () => {
    let n = 0
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    const { calls } = mountApp(
      backend({
        'GET /overview': async () => {
          if (++n === 1) {
            await gate
            return json(503, { error: { code: 'DATABASE_UNAVAILABLE', message: 'x' } })
          }
          return restFixture('OverviewResponse.minh')
        },
      }),
    )
    expect(await screen.findByTestId('overview-skeleton')).toBeInTheDocument()
    release()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Chưa tải được tổng quan')
    expect(alert).toHaveTextContent('Hệ thống đang khởi động')
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByTestId('balance-total')).toBeInTheDocument()
    expect(callsTo(calls, 'GET', '/overview')).toHaveLength(2)
  })

  it('tài khoản trắng (chưa khai): chuyển sang onboarding O1', async () => {
    const { router } = mountApp(backend({ 'GET /overview': restFixture('OverviewResponse.blank') }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/onboarding'))
    expect(await screen.findByRole('heading', { name: /mình bắt đầu từ lương nhé/ })).toBeInTheDocument()
  })

  it('có 0 hũ nhưng đã khai: thông báo rõ, không vỡ', async () => {
    mountApp(backend({ 'GET /overview': overview((o) => { o.jars = []; o.proactive_card = null; o.forecast = null }) }))
    expect(await screen.findByText('Chưa có hũ nào trong tài khoản này.')).toBeInTheDocument()
  })
})

describe('Tổng quan: cảnh 1 (thẻ cạn có số lớn và dải ngày), B2 (nay ở Nhìn trước), Trả sau và nghĩa vụ', () => {
  beforeEach(() => sessionStorage.clear())

  it('thẻ cảnh báo cạn: số lớn "6 ngày" (cạn 29/11, lương 05/12), dải 15 ô từ hôm nay 21/11, ô cạn và ô hũ trống khác nhau', async () => {
    mountApp(backend())
    const card = await screen.findByRole('region', { name: 'Việc cần làm hôm nay' })
    expect(within(card).getByTestId('runout-hero')).toHaveTextContent('6 ngày hũ trống trước kỳ lương')
    const strip = within(card).getByTestId('mini-timeline')
    expect(strip).toHaveAttribute('aria-label', 'Từ hôm nay 21/11 đến kỳ lương 05/12, dự kiến cạn 29/11, 6 ngày hũ trống trước kỳ lương')
    const kinds = [...strip.querySelectorAll('[data-day]')].map((c) => c.getAttribute('data-day'))
    expect(kinds).toEqual([...Array(8).fill('ok'), 'runout', ...Array(5).fill('gap'), 'payday'])
    // Lần mở đầu trong phiên: ô hiện lần lượt (độ trễ tăng 32 ms mỗi ô), chỉ khi người dùng không tắt chuyển động.
    const cells = strip.querySelectorAll<HTMLElement>('[data-day]')
    expect(cells[0]!.className).toContain('motion-safe:animate-in')
    expect(cells[3]!.style.getPropertyValue('--tw-animation-delay')).toBe('96ms')
    // Lý do của server ("Còn …, còn … ngày tới kỳ lương") nhắc lại dải ngày: không mất, nằm trong "Chi tiết" đang đóng
    const reason = within(card).getByText(/Còn 380\.000 ₫, còn 6 ngày tới kỳ lương 05\/12/)
    expect(reason.closest('[data-disclosure-panel]')).toHaveAttribute('data-disclosure-panel', 'closed')
    const more = within(card).getByRole('button', { name: 'Chi tiết' })
    await userEvent.setup().click(more)
    expect(reason.closest('[data-disclosure-panel]')).toHaveAttribute('data-disclosure-panel', 'open')
  })

  it('thẻ chủ động không có số lớn (không phải cảnh báo cạn): lý do hiện ngay, không thu gọn', async () => {
    mountApp(backend({ 'GET /overview': overview((o) => { o.proactive_card.data.kind = 'low_data'; o.proactive_card.data.status = 'ok' }) }))
    const card = await screen.findByRole('region', { name: 'Việc cần làm hôm nay' })
    expect(within(card).getByTestId('proactive-reason').closest('[data-disclosure-panel]')).toBeNull()
    expect(within(card).queryByRole('button', { name: 'Chi tiết' })).toBeNull()
  })

  it('số dư: bảng ba dòng thu gọn sau "Chi tiết số dư"; nền thẻ dùng --gradient-hero', async () => {
    mountApp(backend())
    const parts = await screen.findByTestId('balance-parts')
    expect(parts.closest('[data-disclosure-panel]')).toHaveAttribute('data-disclosure-panel', 'closed')
    expect(screen.getByRole('button', { name: 'Chi tiết số dư' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('region', { name: 'Tổng số dư' }).getAttribute('style')).toContain('var(--gradient-hero)')
  })

  it('số dư: trình đọc màn hình nhận ngay số cuối của server; số đang đếm chỉ để nhìn', async () => {
    mountApp(backend())
    const total = await screen.findByTestId('balance-total')
    expect(total).toHaveTextContent('7.900.000 ₫')
    expect(total).toHaveClass('sr-only')
    const visual = total.nextElementSibling as HTMLElement
    expect(visual).toHaveAttribute('aria-hidden', 'true')
    await waitFor(() => expect(visual).toHaveTextContent('7.900.000 ₫'))
  })

  it('giảm chuyển động: số dư, dải ngày, nước trong hũ hiện thẳng trạng thái cuối, không có lớp chuyển động', async () => {
    vi.stubGlobal('matchMedia', vi.fn((q: string) => ({ matches: q === '(prefers-reduced-motion: reduce)', addEventListener: vi.fn(), removeEventListener: vi.fn() })))
    mountApp(backend())
    const total = await screen.findByTestId('balance-total')
    expect(total.nextElementSibling).toHaveTextContent('7.900.000 ₫')
    const strip = screen.getByTestId('mini-timeline')
    expect(strip.innerHTML).not.toContain('animate-in')
  })

  it('không có ngày cạn trước kỳ lương (thẻ không phải cảnh báo cạn): không có số lớn, không có dải', async () => {
    mountApp(backend({ 'GET /overview': overview((o) => { o.proactive_card.data.kind = 'low_data'; o.proactive_card.data.status = 'ok' }) }))
    const card = await screen.findByRole('region', { name: 'Việc cần làm hôm nay' })
    expect(within(card).queryByTestId('runout-hero')).toBeNull()
    expect(within(card).queryByTestId('mini-timeline')).toBeNull()
  })

  it('Tổng quan không còn B2, B6, lối vào lộ trình cố định (mỗi thông tin một nhà, ui-design-review.md §10)', async () => {
    mountApp(backend())
    await screen.findByRole('region', { name: 'Việc cần làm hôm nay' })
    await waitFor(() => expect(screen.getByTestId('todo-list')).toBeInTheDocument())
    expect(screen.queryByTestId('jar-runway')).toBeNull()
    expect(screen.queryByTestId('credit-usage')).toBeNull()
    expect(screen.queryByText('Lộ trình thích ứng')).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Hũ nào sắp cạn' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Đã dùng Trả sau bao nhiêu' })).toBeNull()
  })

  it('B2 ở tab Nhìn trước: đường băng tới kỳ lương cho hũ chi tiêu và nghĩa vụ, xếp theo mức cần chú ý; hũ tiết kiệm một dòng; câu tóm tắt từ server', async () => {
    mountApp(backend(), '/foresight')
    const fig = await screen.findByTestId('jar-runway')
    expect(within(fig).getByRole('heading', { name: 'Hũ nào sắp cạn' })).toBeInTheDocument()
    // Kỳ lương kế tiếp gộp vào đầu khối (không còn thẻ "Kỳ lương kế tiếp" riêng)
    expect(within(fig).getByTestId('next-payday')).toHaveTextContent('Lương 05/12 · còn 14 ngày')
    expect(screen.queryByText('Kỳ lương kế tiếp')).toBeNull()
    const caption = '2 hũ cần chú ý trước kỳ lương 05/12: Ăn uống dự kiến cạn 29/11, Hóa đơn sát.'
    // Câu tóm tắt: trình đọc màn hình đọc ngay (figcaption sr-only là mô tả của hình), bản nhìn thấy nằm trong "Chi tiết" đang đóng.
    expect(fig.querySelector('figcaption')).toHaveTextContent(caption)
    expect(fig).toHaveAccessibleDescription(caption)
    const more = within(fig).getByRole('button', { name: 'Chi tiết' })
    expect(more).toHaveAttribute('aria-expanded', 'false')
    const panel = document.getElementById(more.getAttribute('aria-controls')!)!
    // Chất lượng dự báo và lương dự kiến nằm trong "Chi tiết"; mốc nghĩa vụ viết gọn
    expect(within(panel).getByTestId('forecast-quality')).toHaveTextContent('62%')
    expect(panel).toHaveTextContent('Lương dự kiến 9.000.000 ₫')
    expect(within(fig).getByTestId('jar-runway-marks')).toHaveTextContent('Hóa đơn: Tiền điện 26/11 · 300.000–450.000 ₫')
    const rows = within(fig).getByRole('list', { name: 'Hũ theo mức cần chú ý' })
    expect([...rows.querySelectorAll('[data-runway]')].map((r) => r.getAttribute('data-runway'))).toEqual(['an_uong', 'hoa_don', 'di_lai', 'giai_tri', 'nghia_vu'])
    // Hũ hụt: đoạn hũ trống bắt đầu ở ngày cạn (29/11 là ngày 8 trên 14), chữ đầy đủ cho trình đọc màn hình, mở Chi tiết hũ
    const an = within(rows).getByRole('link', { name: /^Ăn uống: hụt, dự kiến cạn 29\/11, 6 ngày trước kỳ lương, số dư 380\.000\s₫, khả năng hụt 71%\.$/ })
    expect(an).toHaveAttribute('href', '/jars/an_uong')
    expect(parseFloat((an.querySelector('[data-part="empty"]') as HTMLElement).style.left)).toBeCloseTo((8 / 14) * 100, 2)
    expect(within(an).getByText('Hụt · cạn 29/11')).toBeInTheDocument()
    expect(an).toHaveTextContent('Khả năng hụt 71%')
    // Hũ sát có mốc nghĩa vụ (tiền điện 26/11) bằng vạch và bằng chữ
    const hd = within(rows).getByRole('link', { name: /^Hóa đơn: sát, số dư 450\.000\s₫\. Sắp đến hạn: Tiền điện 26\/11 300\.000\s₫ đến 450\.000\s₫\.$/ })
    expect(hd.querySelectorAll('[data-tick]')).toHaveLength(1)
    expect(hd.querySelector('[data-track]')).toHaveAttribute('data-track', 'tight')
    // Hũ nghĩa vụ: mốc Trả sau 05/12
    const nv = within(rows).getByRole('link', { name: /^Nghĩa vụ: đủ tới kỳ lương, số dư 1\.000\.000\s₫\. Sắp đến hạn: Trả sau \(mô phỏng\) 05\/12 333\.000\s₫\.$/ })
    expect(nv.querySelectorAll('[data-tick]')).toHaveLength(1)
    expect(within(rows).queryByRole('link', { name: /^Du lịch/ })).toBeNull()
    // Hũ tiết kiệm không "cạn" theo nghĩa này: một dòng (tên, nhãn, số dư), không có đường băng
    const savings = within(fig).getByRole('list', { name: 'Hũ tiết kiệm' })
    const dl = within(savings).getByRole('link', { name: /^Du lịch: số dư 1\.800\.000\s₫\.$/ })
    expect(dl).toHaveAttribute('href', '/jars/du_lich')
    expect(dl.querySelector('[data-track]')).toBeNull()
  })

  it('B2 ở Nhìn trước, giảm chuyển động: không có lớp chuyển động', async () => {
    vi.stubGlobal('matchMedia', vi.fn((q: string) => ({ matches: q === '(prefers-reduced-motion: reduce)', addEventListener: vi.fn(), removeEventListener: vi.fn() })))
    mountApp(backend(), '/foresight')
    expect((await screen.findByTestId('jar-runway')).innerHTML).not.toContain('animate-in')
  })

  it('B2: hũ cạn đúng ngày có mốc nghĩa vụ: vạch mốc vẽ dài hơn và nằm trên chấm cạn (không bị che)', async () => {
    mountApp(backend({ 'GET /overview': overview((o) => { o.jars = o.jars.map((j: Json) => (j.code === 'hoa_don' ? { ...j, status: 'short', runout_date: '2026-11-26' } : j)) }) }), '/foresight')
    const fig = await screen.findByTestId('jar-runway')
    const hd = within(fig).getByRole('link', { name: /^Hóa đơn: hụt, dự kiến cạn 26\/11/ })
    const tick = hd.querySelector('[data-tick]') as HTMLElement
    const dot = hd.querySelector('[data-part="runout"]') as HTMLElement
    expect(tick).toHaveAttribute('data-at-runout')
    expect(tick.style.left).toBe(dot.style.left)
    expect(tick.className).toMatch(/\bz-10\b/)
    expect(tick.className).toMatch(/-top-2\b/)
    // Hũ khác không trùng ngày: vạch thường
    const nv = within(fig).getByRole('link', { name: /^Nghĩa vụ:/ })
    expect(nv.querySelector('[data-tick]')).not.toHaveAttribute('data-at-runout')
  })

  it('B2: hũ chưa có dự báo ghi rõ; không có kỳ lương thì không vẽ đường băng, vẫn có danh sách hũ', async () => {
    mountApp(backend({ 'GET /overview': overview((o) => { o.jars = o.jars.map((j: Json) => (j.code === 'di_lai' ? { ...j, status: undefined } : j)) }) }), '/foresight')
    const fig = await screen.findByTestId('jar-runway')
    expect(within(fig).getByRole('link', { name: /^Đi lại: chưa có dự báo/ })).toBeInTheDocument()
    cleanup()
    mountApp(backend({ 'GET /overview': overview((o) => { o.next_payday = null; o.proactive_card = null }) }), '/foresight')
    const plain = await screen.findByTestId('jar-runway')
    expect(plain.querySelector('[data-track]')).toBeNull()
    expect(within(plain).getAllByRole('link', { name: /số dư/ })).toHaveLength(7)
  })

  it('Trả sau ở Tổng quan: hũ trả đủ thì không có gì (B6 đầy đủ ở Nghĩa vụ)', async () => {
    mountApp(backend())
    await screen.findByRole('region', { name: 'Việc cần làm hôm nay' })
    await waitFor(() => expect(screen.getByTestId('todo-list')).toBeInTheDocument())
    expect(document.querySelector('[data-todo="credit"]')).toBeNull()
    expect(screen.queryByTestId('credit-usage')).toBeNull()
  })

  it('Trả sau ở Tổng quan: hũ trả có ít hơn số phải trả thì một dòng Việc cần làm dẫn tới Nghĩa vụ', async () => {
    mountApp(backend({ 'GET /overview': overview((o) => { o.jars = o.jars.map((j: Json) => (j.code === 'nghia_vu' ? { ...j, balance_vnd: 200000 } : j)) }) }))
    const row = await screen.findByRole('link', { name: /^Hũ Nghĩa vụ chưa đủ trả Trả sau \(mô phỏng\)/ })
    expect(row).toHaveAttribute('href', '/obligations')
    expect(row).toHaveTextContent(/Đến hạn 05\/12 · hũ đang có 200\.000\s₫/)
    // Số phải trả chỉ ở danh sách nghĩa vụ sắp đến hạn, không lặp ở dòng việc cần làm
    expect(row).not.toHaveTextContent('333.000')
    expect(within(screen.getByTestId('obligations-due')).getByText('333.000 ₫')).toBeInTheDocument()
  })

  it('nghĩa vụ sắp đến hạn: tối đa 3 dòng, "Xem tất cả" mở màn Nghĩa vụ', async () => {
    mountApp(backend({
      'GET /overview': overview((o) => {
        const base = o.obligations_due[0]
        o.obligations_due = [0, 1, 2, 3].map((i) => ({ ...base, id: `${base.id.slice(0, -1)}${i}`, name: `Khoản ${i}` }))
      }),
    }))
    const due = await screen.findByTestId('obligations-due')
    expect(within(due).getAllByRole('listitem')).toHaveLength(3)
    expect(within(due).queryByText('Khoản 3')).toBeNull()
    const title = screen.getByRole('heading', { name: 'Nghĩa vụ sắp đến hạn' }).parentElement!
    expect(within(title).getByRole('link', { name: 'Xem tất cả' })).toHaveAttribute('href', '/obligations')
  })

  it('số dư: "Trong 7 hũ" cộng trừ các phần ra đúng tổng (có dấu, đọc được cho trình đọc màn hình)', async () => {
    mountApp(backend())
    const parts = await screen.findByTestId('balance-parts')
    expect(parts).toHaveTextContent('Trong 7 hũ')
    expect(within(parts).getByText('Tiền vào khác (chưa gán hũ)').parentElement).toHaveTextContent(/^\+cộng Tiền vào khác/)
    expect(within(parts).getByText('Đã chi, chưa xếp hũ').parentElement).toHaveTextContent(/^−trừ Đã chi, chưa xếp hũ/)
  })
})

describe('tab Hũ', () => {
  it('tổng trong 7 hũ, hai ô hũ hệ thống, các dòng hũ có chip đủ/sát/hụt; chạm dòng mở Chi tiết hũ', async () => {
    const { router } = mountApp(backend(), '/jars')
    expect(await screen.findByTestId('jars-total')).toHaveTextContent('7.730.000 ₫')
    expect(screen.getByText('Tổng trong 7 hũ')).toBeInTheDocument()
    expect(screen.getByTestId('other-income-tile')).toHaveTextContent('350.000 ₫')
    expect(screen.getByTestId('unclassified-tile')).toHaveTextContent('Đã chi, chưa xếp hũ')
    expect(screen.getByTestId('unclassified-tile')).toHaveTextContent('180.000 ₫')
    const list = screen.getByRole('list', { name: 'Các hũ' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(7)
    expect(within(list).getByText('Hụt · cạn 29/11')).toBeInTheDocument()
    await userEvent.setup().click(within(list).getByRole('link', { name: 'Mở hũ Ăn uống' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/jars/an_uong'))
  })

  it('chưa có hũ: trạng thái rỗng có nút thêm hũ', async () => {
    mountApp(backend({ 'GET /overview': overview((o) => { o.jars = []; o.system_jars = []; o.balance = { total_vnd: 0, jars_total_vnd: 0, other_income_vnd: 0, unclassified_vnd: 0 } }) }), '/jars')
    expect(await screen.findByText('Chưa có hũ nào')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Thêm hũ' })).toBeInTheDocument()
  })

  it('lỗi tải: Thử lại', async () => {
    let n = 0
    mountApp(backend({ 'GET /overview': () => (++n === 1 ? json(500, { error: { code: 'INTERNAL_ERROR', message: 'x' } }) : restFixture('OverviewResponse.minh')) }), '/jars')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Chưa tải được danh sách hũ')
    await userEvent.setup().click(within(alert).getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByTestId('jars-total')).toBeInTheDocument()
  })
})

describe('Chi tiết hũ', () => {
  it('số dư, khối dự báo (cùng ForecastBlock với chat), giao dịch gần đây, luật chia, nút hành động', async () => {
    mountApp(backend(), '/jars/an_uong')
    expect(await screen.findByTestId('jar-balance')).toHaveTextContent('380.000 ₫')
    expect(await screen.findByTestId('forecast-summary')).toHaveTextContent('Ăn uống dự kiến cạn ngày 29/11')
    expect(screen.getByTestId('p-shortfall')).toHaveTextContent('71%')
    expect(screen.getByTestId('forecast-chart')).toBeInTheDocument() // vẽ biểu đồ được kiểm ở ForecastBlock.test (jsdom không đo được khung)
    const txs = screen.getByTestId('jar-transactions')
    expect(within(txs).getAllByRole('listitem').length).toBeGreaterThan(0)
    expect(screen.getByRole('region', { name: 'Luật chia và mục tiêu' })).toHaveTextContent('30%')
    expect(screen.getByRole('link', { name: 'Chuyển tiền vào hũ này' })).toHaveAttribute('href', '/move?to=an_uong')
    expect(screen.getByRole('button', { name: 'Hỏi Yofina về hũ này' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Vì sao hũ này cạn?' })).toBeInTheDocument()
  })

  it('nhãn Đủ/Sát/Hụt chỉ một lần: có khối dự báo thì đầu màn không có chip; payday chỉ trong khối dự báo', async () => {
    mountApp(backend(), '/jars/an_uong')
    const block = (await screen.findByTestId('forecast-summary')).closest('[data-block="forecast_timeline"]') as HTMLElement
    expect(within(block).getByText('Hụt · cạn 29/11')).toBeInTheDocument()
    expect(screen.getAllByText('Hụt · cạn 29/11')).toHaveLength(1)
    expect(screen.getByRole('region', { name: 'Luật chia và mục tiêu' })).not.toHaveTextContent('Kỳ lương kế tiếp')
  })

  it('dự báo lỗi: chip trạng thái của hũ và kỳ lương vẫn có (từ /jars và /overview)', async () => {
    mountApp(backend({ 'GET /forecasts/*': json(503, { error: { code: 'FORECAST_UNAVAILABLE', message: 'x' } }) }), '/jars/an_uong')
    await screen.findByTestId('forecast-error')
    expect(screen.getByText('Hụt · cạn 29/11')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Luật chia và mục tiêu' })).toHaveTextContent('Kỳ lương kế tiếp')
  })

  it('"Hỏi Yofina về hũ này" mở chat và gửi câu hỏi về đúng hũ', async () => {
    const { calls } = mountApp(
      backend({
        'POST /invocations': async (init) =>
          JSON.parse(String(init.body)).forwardedProps?.warmup ? sseResponse([runStarted(), runFinished()]) : sseResponse([runStarted(), ...textMessage('m1', 'OK'), runFinished()]),
      }),
      '/jars/an_uong',
    )
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Hỏi Yofina về hũ này' }))
    await waitFor(() => expect(runCalls(calls)).toHaveLength(1))
    expect((bodyOf(runCalls(calls)[0]!).messages as Array<{ content: string }>).at(-1)!.content).toBe('Cho mình biết tình hình hũ Ăn uống.')
  })

  it('dự báo chưa có (503 FORECAST_UNAVAILABLE): chỉ phần dự báo báo lỗi và có Thử lại; số dư và giao dịch vẫn hiện', async () => {
    let n = 0
    mountApp(
      backend({
        'GET /forecasts/*': () => (++n === 1 ? json(503, { error: { code: 'FORECAST_UNAVAILABLE', message: 'x' } }) : validBlock('forecast_timeline.short')),
      }),
      '/jars/an_uong',
    )
    const err = await screen.findByTestId('forecast-error')
    expect(err).toHaveTextContent('Chưa có dự báo cho hũ này')
    expect(err).toHaveTextContent('chưa tính được ngay')
    expect(screen.getByTestId('jar-balance')).toHaveTextContent('380.000 ₫')
    expect(screen.getByTestId('jar-transactions')).toBeInTheDocument()
    await userEvent.setup().click(within(err).getByRole('button', { name: 'Thử lại' }))
    expect(await screen.findByTestId('forecast-summary')).toBeInTheDocument()
  })

  it('hũ Chưa phân loại (âm): không gọi dự báo, nói rõ "đã chi mà chưa xếp hũ"', async () => {
    const { calls } = mountApp(backend({ 'GET /jars/*': restFixture('JarDetailResponse.unclassified') }), '/jars/chua_phan_loai')
    expect(await screen.findByTestId('jar-balance')).toHaveTextContent('−180.000 ₫')
    expect(screen.getByText(/Đã chi 180\.000 ₫ mà chưa xếp vào hũ nào/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Xếp hũ cho các giao dịch này' })).toHaveAttribute('href', '/review')
    expect(screen.getByText('Hũ hệ thống không có dự báo')).toBeInTheDocument()
    expect(callsTo(calls, 'GET', '/forecasts/chua_phan_loai')).toHaveLength(0)
    expect(screen.queryByRole('link', { name: 'Chuyển tiền vào hũ này' })).toBeNull()
  })

  it('hũ không tồn tại (404): thông báo tiếng Việt và Thử lại', async () => {
    mountApp(backend({ 'GET /jars/*': json(404, { error: { code: 'JAR_NOT_FOUND', message: 'x' } }) }), '/jars/khong_co')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Không tìm thấy hũ này')
  })

  it('ước lượng ban đầu của hũ hiện nhãn và chỉ nhóm tin cậy', async () => {
    mountApp(backend({ 'GET /forecasts/*': validBlock('forecast_timeline.initial_estimate') }), '/jars/an_uong')
    expect(await screen.findByText('Ước lượng ban đầu')).toBeInTheDocument()
    expect(screen.queryByTestId('p-shortfall')).toBeNull()
  })
})

describe('tab Nhìn trước', () => {
  it('hũ cần chú ý nhất lên đầu, kèm chất lượng dự báo và kỳ lương', async () => {
    mountApp(backend(), '/foresight')
    const list = await screen.findByRole('list', { name: 'Hũ theo mức cần chú ý' })
    const items = within(list).getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Ăn uống')
    expect(items[1]).toHaveTextContent('Hóa đơn')
    expect(screen.getByTestId('next-payday')).toHaveTextContent('05/12 · còn 14 ngày')
    expect(screen.getByTestId('forecast-quality')).toHaveTextContent('62%')
    expect(items[0]).toHaveTextContent('Khả năng hụt 71%')
  })
})
