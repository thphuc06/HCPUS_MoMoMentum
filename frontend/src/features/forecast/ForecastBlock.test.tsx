import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ForecastTimelineData } from '@/contracts/blocks'
import { validBlock } from '@/test/fixtures'
import { chartLabel, ForecastBlock, forecastHeadline, forecastSummary } from './ForecastBlock'
import { buildChartModel } from './model'
import { formatVnd } from '@/lib/format'

const data = (name: string): ForecastTimelineData => structuredClone((validBlock(name) as unknown as { data: ForecastTimelineData }).data)
const SIZE = { width: 360, height: 240 }

async function mount(d: ForecastTimelineData) {
  const r = render(<ForecastBlock data={d} chartSize={SIZE} />)
  // Recharts tải lười (chunk riêng): chờ biểu đồ hiện.
  await waitFor(() => expect(r.container.querySelector('svg.recharts-surface')).not.toBeNull(), { timeout: 15_000 })
  return r
}

describe('ForecastBlock: biểu đồ', { timeout: 20_000 }, () => {
  it('dựng dải P10–P90, đường P50, mốc nghĩa vụ và lương, điểm cạn đúng số', async () => {
    const d = data('forecast_timeline.short')
    const { container } = await mount(d)
    const m = buildChartModel(d)
    expect(container.querySelectorAll('.recharts-area')).toHaveLength(1)
    expect(container.querySelectorAll('.recharts-line')).toHaveLength(1)
    // đường y = 0 + mỗi mốc một đường dọc
    expect(container.querySelectorAll('.recharts-reference-line')).toHaveLength(1 + m.events.length)
    expect(container.querySelectorAll('.recharts-reference-dot')).toHaveLength(1)
    expect(container.querySelectorAll('.recharts-reference-area')).toHaveLength(1)
    // nhãn trục ngày tiếng Việt dd/mm
    const ticks = Array.from(container.querySelectorAll('.recharts-xAxis-tick-labels .recharts-cartesian-axis-tick-value')).map((t) => t.textContent)
    expect(ticks[0]).toBe('21/11')
    expect(ticks).toContain('05/12')
    // nhãn mốc
    const text = container.textContent ?? ''
    expect(text).toContain('Lương về 05/12')
    expect(text).toContain('Tiền điện 26/11')
    expect(text).toContain(`Cạn ${d.runout_date!.slice(8, 10)}/${d.runout_date!.slice(5, 7)}`)
  })

  it('không cạn thì không có điểm cạn và vùng hụt', async () => {
    const d = data('forecast_timeline.short')
    delete d.runout_date
    d.status = 'ok'
    const { container } = await mount(d)
    expect(container.querySelectorAll('.recharts-reference-dot')).toHaveLength(0)
    expect(container.querySelectorAll('.recharts-reference-area')).toHaveLength(0)
  })
})

describe('ForecastBlock: nội dung hiển thị', () => {
  it('hũ hụt: tóm tắt, chip, xác suất hụt, nhóm tin cậy, độ phủ, thời điểm tính', async () => {
    const d = data('forecast_timeline.short')
    await mount(d)
    expect(screen.getByTestId('forecast-summary')).toHaveTextContent(forecastSummary(d))
    expect(screen.getByTestId('forecast-summary')).toHaveTextContent('Ăn uống dự kiến cạn ngày 29/11')
    expect(screen.getByText('Hụt · cạn 29/11')).toBeInTheDocument() // chip trạng thái có chữ
    expect(screen.getByTestId('p-shortfall')).toHaveTextContent('70%')
    expect(screen.getByTestId('confidence-band')).toHaveTextContent('Vừa')
    expect(screen.queryByText(/Chưa đủ cơ sở để nêu xác suất/)).toBeNull()
    expect(screen.getByTestId('coverage')).toHaveTextContent('62%')
    expect(screen.getByTestId('forecast-meta')).toHaveTextContent('47 ngày')
    expect(screen.getByText(/Cập nhật \d{2}\/\d{2}\/\d{4} · \d{2}:\d{2} · Ví mô phỏng/)).toBeInTheDocument()
    expect(screen.queryByText('Ước lượng ban đầu')).toBeNull()
    expect(screen.queryByText('Số liệu cũ')).toBeNull()
  })

  it('liệt kê mốc dưới biểu đồ (tương đương văn bản của biểu đồ), thu gọn trong "Chi tiết dự báo"', async () => {
    const d = data('forecast_timeline.short')
    await mount(d)
    const toggle = screen.getByRole('button', { name: 'Chi tiết dự báo' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    // Đang đóng: mốc vẫn nằm trong DOM nhưng ẩn khỏi cây trợ năng; dòng chính ngắn hiện ngay.
    expect(screen.queryAllByRole('listitem', { name: undefined }).filter((li) => li.closest('[data-testid="forecast-events"]'))).toHaveLength(0)
    expect(screen.getByTestId('forecast-headline')).toHaveTextContent('Cạn 29/11, 6 ngày trước lương 05/12.')
    fireEvent.click(toggle)
    const list = screen.getByTestId('forecast-events')
    expect(within(list).getAllByRole('listitem')).toHaveLength(d.events.length)
    expect(list).toHaveTextContent('Lương về · 05/12')
    expect(list).toHaveTextContent('Tiền điện · 26/11')
  })

  it('ước lượng ban đầu: chip, giải thích số ngày, chỉ nhóm tin cậy (không xác suất)', async () => {
    const d = data('forecast_timeline.initial_estimate')
    await mount(d)
    expect(screen.getByText('Ước lượng ban đầu')).toBeInTheDocument()
    expect(screen.getByText(new RegExp(`Mới có ${d.history_days} ngày dữ liệu`))).toBeInTheDocument()
    expect(screen.queryByTestId('p-shortfall')).toBeNull()
    expect(screen.getByTestId('confidence-band')).toHaveTextContent('Thấp')
    expect(screen.getByText(/Chưa đủ cơ sở để nêu xác suất/)).toBeInTheDocument()
  })

  it('không có độ phủ: nói thật "Chưa tính được", không số giả', async () => {
    const d = data('forecast_timeline.initial_estimate')
    delete d.coverage
    await mount(d)
    expect(screen.getByTestId('coverage')).toHaveTextContent('Chưa tính được')
  })

  it('số liệu cũ (stale): chip và lời giải thích', async () => {
    const d = data('forecast_timeline.short')
    d.stale = true
    await mount(d)
    expect(screen.getByText('Số liệu cũ')).toBeInTheDocument()
    expect(screen.getByText(/chưa được cập nhật theo ngày mô phỏng/)).toBeInTheDocument()
  })

  it('đọc số từng ngày bằng thanh chọn ngày (dùng được bằng chạm và bàn phím)', async () => {
    const d = data('forecast_timeline.short')
    await mount(d)
    const readout = screen.getByTestId('chart-readout')
    expect(readout).toHaveTextContent('Chạm vào biểu đồ')
    const slider = screen.getByRole('slider', { name: 'Chọn ngày để xem số dư dự báo' })
    fireEvent.change(slider, { target: { value: '3' } })
    const day = d.days[2]!
    expect(readout).toHaveTextContent('24/11')
    expect(readout.textContent).toContain('khoảng 80% khả năng')
    expect(day.date).toBe('2026-11-24')
  })

  it('nút "Vì sao" chỉ có khi nơi dùng truyền onAskWhy', async () => {
    const d = data('forecast_timeline.short')
    let asked = 0
    const { rerender } = render(<ForecastBlock data={d} chartSize={SIZE} onAskWhy={() => asked++} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Vì sao' }))
    expect(asked).toBe(1)
    rerender(<ForecastBlock data={d} chartSize={SIZE} />)
    expect(screen.queryByRole('button', { name: 'Vì sao' })).toBeNull()
  })
})

describe('forecastSummary', () => {
  it('ngày cạn sau kỳ lương, không cạn, hụt không có ngày cạn', () => {
    const d = data('forecast_timeline.short')
    // cạn trước lương: nói khoảng trống (ngày cạn -> lương) và số ngày từ hôm nay, hai con số khác nhau
    const before = forecastSummary({ ...d, runout_date: '2026-11-23', payday: { date: '2026-12-05', days_until: 14 } })
    expect(before).toContain('cạn ngày 23/11, 12 ngày trước kỳ lương 05/12 (hôm nay còn 14 ngày tới lương)')
    expect(forecastSummary({ ...d, runout_date: '2026-12-20' })).toContain('sau kỳ lương 05/12')
    expect(forecastSummary({ ...d, runout_date: undefined, status: 'ok' })).toContain('dự kiến đủ tới kỳ lương')
    expect(forecastSummary({ ...d, runout_date: undefined, status: 'short' })).toContain('có khả năng hụt')
    // Huy hiệu "Sát" thì câu tóm tắt không được nói "đủ" (lệch thấy trên tài khoản khoa).
    const tight = forecastSummary({ ...d, runout_date: undefined, status: 'tight' })
    expect(tight).toContain('còn rất ít tiền trước kỳ lương')
    expect(tight).not.toContain('đủ tới')
  })
})

describe('ForecastBlock: trước-sau (what-if)', { timeout: 20_000 }, () => {
  it('vẽ hai đường (trước nét đứt, sau) cùng dải chênh lệch; tóm tắt nêu trước, sau và chênh lệch của engine', async () => {
    const d = data('forecast_timeline.what_if')
    const { container } = await mount(d)
    expect(container.querySelectorAll('.recharts-line')).toHaveLength(2)
    expect(container.querySelectorAll('.recharts-area')).toHaveLength(2) // dải 80% và dải chênh lệch
    const cmp = screen.getByTestId('forecast-compare')
    expect(screen.getByTestId('compare-label')).toHaveTextContent(`Nếu ${d.compare!.label}`)
    const before = cmp.querySelector('[data-col="before"]')!
    const after = cmp.querySelector('[data-col="after"]')!
    // mỗi cột có biểu tượng + chữ trạng thái (Đủ, Sát, Hụt), không chỉ màu
    expect(before.querySelector('[data-chip] svg')).not.toBeNull()
    expect(within(after as HTMLElement).getByText('Sát')).toBeInTheDocument()
    expect(within(before as HTMLElement).getByText('Đủ')).toBeInTheDocument()
    expect(within(cmp).getByLabelText('Chênh lệch trước và sau')).toHaveTextContent('giảm 500.000 ₫')
    expect(within(cmp).getByLabelText('Chênh lệch trước và sau')).toHaveTextContent('Khả năng hụt tăng 16 điểm phần trăm')
    expect(cmp).toHaveTextContent('cùng dãy số ngẫu nhiên')
    expect(screen.queryByTestId('forecast-summary')).toBeNull()
  })

  it('khối không có compare: vẽ như cũ (một đường, không có phần so sánh)', async () => {
    const { container } = await mount(data('forecast_timeline.short'))
    expect(container.querySelectorAll('.recharts-line')).toHaveLength(1)
    expect(screen.queryByTestId('forecast-compare')).toBeNull()
  })
})

// "Cạn 29/11", "cạn ngày 29/11", "Hụt · cạn 29/11": mọi cách nêu một ngày cạn cụ thể
const RUNOUT_DATE = /cạn (ngày )?\d{2}\/\d{2}/i

describe('ForecastBlock: hũ thưa không nêu ngày cạn (#25)', { timeout: 20_000 }, () => {
  it('cờ runout_date_shown sai: một dòng "Có thể cạn trước ngày lương" kèm %, không ngày cạn, không điểm và vùng hụt', async () => {
    const d = data('forecast_timeline.sparse_no_date')
    const { container } = await mount(d)
    expect(screen.getByTestId('forecast-headline')).toHaveTextContent(/^Có thể cạn trước ngày lương, khả năng 60%\.$/)
    expect(container.querySelector('header')).toHaveTextContent(/Hụt$/) // chip không kèm ngày
    expect(container.querySelectorAll('.recharts-reference-dot')).toHaveLength(0)
    expect(container.querySelectorAll('.recharts-reference-area')).toHaveLength(0)
    expect(screen.getByTestId('forecast-summary')).toHaveTextContent('Hũ Giải trí có thể cạn trước ngày lương 05/12 (còn 14 ngày).')
    expect(screen.getByTestId('forecast-chart')).toHaveAttribute('aria-label', expect.stringContaining('có thể cạn trước ngày lương'))
    expect(container.textContent).not.toMatch(RUNOUT_DATE)
    expect(screen.getByTestId('p-shortfall')).toHaveTextContent('60%')
  })

  it('không được hiện % thì chỉ còn câu ngắn', () => {
    const d = data('forecast_timeline.sparse_no_date')
    delete d.p_shortfall
    delete d.p_shortfall_se
    expect(forecastHeadline(d)).toBe('Có thể cạn trước ngày lương.')
  })

  it('cờ sai mà dữ liệu vẫn còn ngày cạn (bản cũ): vẫn không hiện ngày', async () => {
    const d = { ...data('forecast_timeline.sparse_no_date'), runout_date: '2026-12-03' }
    const { container } = await mount(d)
    expect(container.textContent).not.toMatch(RUNOUT_DATE)
    expect(container.textContent).not.toContain('Cạn 03/12')
    expect(container.querySelectorAll('.recharts-reference-dot')).toHaveLength(0)
  })

  it('cờ đúng hoặc vắng: như cũ', () => {
    const d = data('forecast_timeline.short')
    expect(forecastHeadline({ ...d, runout_date_shown: true })).toBe('Cạn 29/11, 6 ngày trước lương 05/12.')
    expect(forecastHeadline(d)).toBe('Cạn 29/11, 6 ngày trước lương 05/12.')
  })

  it('what-if của hũ thưa: cột hụt nói "Có thể cạn trước ngày lương", không có "Ngày cạn sớm hơn"', async () => {
    const d = data('forecast_timeline.what_if')
    d.runout_date_shown = false
    d.compare!.after.status = 'short'
    d.compare!.after.runout_date = '2026-11-28' // bản cũ còn ngày: vẫn không hiện
    d.compare!.delta.runout_shift_days = -3
    const { container } = await mount(d)
    const after = screen.getByTestId('forecast-compare').querySelector('[data-col="after"]') as HTMLElement
    expect(after).toHaveTextContent('Có thể cạn trước ngày lương')
    expect(screen.getByLabelText('Chênh lệch trước và sau')).not.toHaveTextContent('Ngày cạn')
    expect(container.textContent).not.toMatch(RUNOUT_DATE)
  })
})

describe('ForecastBlock: cách nói số của server (lỗi nhỏ phase 2)', () => {
  it('xác suất hụt tròn 100% nói "gần như chắc chắn", không nói "100%"', async () => {
    const d = data('forecast_timeline.short')
    d.p_shortfall = 1
    await mount(d)
    expect(screen.getByTestId('p-shortfall')).toHaveTextContent('Gần như chắc chắn')
    expect(screen.getByTestId('p-shortfall')).not.toHaveTextContent('100%')
  })

  it('hũ đang 0 ₫: nói "đang hết tiền", không nói "dự kiến cạn"; chip "Đang hết tiền"', async () => {
    const d = data('forecast_timeline.short')
    d.start_balance_vnd = 0
    expect(forecastSummary(d)).toBe(`Hũ ${d.jar.name} đang hết tiền (${formatVnd(0)}). Kỳ lương kế tiếp ngày ${d.payday.date.slice(8, 10)}/${d.payday.date.slice(5, 7)}, còn ${d.payday.days_until} ngày nữa.`)
    await mount(d)
    expect(screen.getByTestId('forecast-summary')).not.toHaveTextContent('dự kiến cạn')
    expect(screen.getByText('Đang hết tiền')).toBeInTheDocument()
  })
})

describe('ForecastBlock: cảnh 2, đường "Sau" vẽ dần và nhãn đọc được', { timeout: 20_000 }, () => {
  beforeEach(() => sessionStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  const reducedMotion = (on: boolean) =>
    vi.stubGlobal('matchMedia', vi.fn((q: string) => ({ matches: on && q === '(prefers-reduced-motion: reduce)', addEventListener: vi.fn(), removeEventListener: vi.fn() })))

  it('khối what-if: bật vẽ dần cho đường Sau một lần; mở lại cùng khối trong phiên thì hiện thẳng', async () => {
    const d = data('forecast_timeline.what_if')
    const first = await mount(d)
    expect(first.getByTestId('forecast-chart')).toHaveAttribute('data-animate', 'after')
    first.unmount()
    const again = await mount(d)
    expect(again.getByTestId('forecast-chart')).not.toHaveAttribute('data-animate')
  })

  it('giảm chuyển động: không vẽ dần, chấm "Sau: cạn" không có hiệu ứng bật', async () => {
    reducedMotion(true)
    const d = data('forecast_timeline.what_if')
    const { container, getByTestId } = await mount(d)
    expect(getByTestId('forecast-chart')).not.toHaveAttribute('data-animate')
    expect(container.querySelector('.motion-pop')).toBeNull()
  })

  it('khối không có so sánh: không có gì chuyển động', async () => {
    reducedMotion(false)
    const { getByTestId } = await mount(data('forecast_timeline.short'))
    expect(getByTestId('forecast-chart')).not.toHaveAttribute('data-animate')
  })

  it('nhãn trục và nhãn mốc 12 px; nét mốc nghĩa vụ dùng màu nét "sát" dày 2 px', async () => {
    const d = data('forecast_timeline.short')
    const { container } = await mount(d)
    const ticks = Array.from(container.querySelectorAll('.recharts-cartesian-axis-tick-value'))
    expect(ticks.length).toBeGreaterThan(0)
    for (const t of ticks) expect(t.getAttribute('font-size')).toBe('12')
    const names = [...buildChartModel(d).events.map((e) => e.label), 'Cạn']
    const labels = Array.from(container.querySelectorAll('svg text')).filter((t) => names.some((n) => t.textContent?.startsWith(n)))
    expect(labels.length).toBeGreaterThan(0)
    for (const l of labels) expect(l.getAttribute('font-size')).toBe('12')
    const obligation = buildChartModel(d).events.find((e) => e.kind !== 'salary')!
    const line = Array.from(container.querySelectorAll('.recharts-reference-line-line')).find((l) => l.getAttribute('stroke') === 'var(--status-warn-line)')
    expect(obligation).toBeDefined()
    expect(line).toBeDefined()
    expect(line!.getAttribute('stroke-width')).toBe('2')
  })

  it('mô tả biểu đồ cho trình đọc màn hình nêu ngày cạn của Trước và Sau (số của khối)', async () => {
    const d = data('forecast_timeline.what_if')
    const { getByRole } = await mount(d)
    const label = chartLabel(d)
    expect(getByRole('img', { name: label })).toBeInTheDocument()
    expect(label).toContain('đường Trước nét đứt')
    expect(label).toContain(d.compare!.after.runout_date ? `Sau cạn ngày ${d.compare!.after.runout_date.slice(8, 10)}/${d.compare!.after.runout_date.slice(5, 7)}` : 'Sau không cạn trong kỳ dự báo')
  })
})