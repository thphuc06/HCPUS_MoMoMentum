import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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

  it('hành động nhanh: Chuyển tiền, Tiền vào, Giữa hũ dẫn đi; Kiểm tra vô hiệu và ghi "Sắp có"', async () => {
    mountApp(backend())
    const nav = await screen.findByRole('navigation', { name: 'Hành động nhanh' })
    expect(within(nav).getByRole('link', { name: /Chuyển tiền/ })).toHaveAttribute('href', '/transfer')
    expect(within(nav).getByRole('link', { name: /Tiền vào/ })).toHaveAttribute('href', '/income')
    expect(within(nav).getByRole('link', { name: /Giữa hũ/ })).toHaveAttribute('href', '/move')
    const check = within(nav).getByRole('button', { name: /Kiểm tra/ })
    expect(check).toBeDisabled()
    expect(check).toHaveTextContent('Sắp có')
  })

  it('dải hũ: 7 thẻ, trạng thái đủ/sát/hụt có chữ; vạch dự báo chỉ ở hũ có số dự báo (hũ hụt)', async () => {
    mountApp(backend())
    const list = await screen.findByRole('list', { name: 'Danh sách hũ' })
    const cards = within(list).getAllByRole('article')
    expect(cards).toHaveLength(7)
    const an = list.querySelector('[data-jar="an_uong"]') as HTMLElement
    expect(an).toHaveAttribute('data-status', 'short')
    expect(within(an).getByText('Cạn ngày 29/11')).toBeInTheDocument()
    expect(within(an).getByTestId('forecast-mark')).toBeInTheDocument()
    expect(within(list.querySelector('[data-jar="di_lai"]') as HTMLElement).getByText('Đủ tới kỳ lương')).toBeInTheDocument()
    expect(within(list.querySelector('[data-jar="hoa_don"]') as HTMLElement).getByText('Sát, cần nhắc')).toBeInTheDocument()
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
    expect(await screen.findByTestId('chat-sheet')).toBeInTheDocument()
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

  it('Gần đây, nghĩa vụ sắp đến hạn và "Cần xem lại" lấy từ server', async () => {
    mountApp(backend())
    const recent = await screen.findByTestId('recent-transactions')
    expect(within(recent).getByText('Quán cơm')).toBeInTheDocument()
    expect(within(recent).getByText(/−45\.000/)).toBeInTheDocument()
    const due = screen.getByTestId('obligations-due')
    expect(within(due).getByText('Tiền điện')).toBeInTheDocument()
    expect(within(due).getByText('Trả sau (mô phỏng)')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Cần xem lại \(3\)/ })).toHaveAttribute('href', '/activity?review=1')
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
    expect(within(list).queryByText('Đủ tới kỳ lương')).toBeNull()
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
    expect(within(list).getByText('Cạn ngày 29/11')).toBeInTheDocument()
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
