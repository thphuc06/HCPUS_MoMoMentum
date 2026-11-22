import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ForecastTimelineData } from '@/contracts/blocks'
import { validBlock } from '@/test/fixtures'
import { ForecastBlock, forecastSummary } from './ForecastBlock'
import { buildChartModel } from './model'

const data = (name: string): ForecastTimelineData => structuredClone((validBlock(name) as unknown as { data: ForecastTimelineData }).data)
const SIZE = { width: 360, height: 240 }

async function mount(d: ForecastTimelineData) {
  const r = render(<ForecastBlock data={d} chartSize={SIZE} />)
  // Recharts tải lười (chunk riêng): chờ biểu đồ hiện.
  await waitFor(() => expect(r.container.querySelector('svg.recharts-surface')).not.toBeNull(), { timeout: 4000 })
  return r
}

describe('ForecastBlock: biểu đồ', () => {
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
    expect(screen.getByText('Cạn ngày 29/11')).toBeInTheDocument() // chip trạng thái có chữ
    expect(screen.getByTestId('p-shortfall')).toHaveTextContent('71%')
    expect(screen.getByTestId('confidence-band')).toHaveTextContent('Vừa')
    expect(screen.queryByText(/Chưa đủ cơ sở để nêu xác suất/)).toBeNull()
    expect(screen.getByTestId('coverage')).toHaveTextContent('62%')
    expect(screen.getByTestId('forecast-meta')).toHaveTextContent('47 ngày')
    expect(screen.getByText(/Cập nhật \d{2}\/\d{2} \d{2}:\d{2} · Ví mô phỏng/)).toBeInTheDocument()
    expect(screen.queryByText('Ước lượng ban đầu')).toBeNull()
    expect(screen.queryByText('Số liệu cũ')).toBeNull()
  })

  it('liệt kê mốc dưới biểu đồ (tương đương văn bản của biểu đồ)', async () => {
    const d = data('forecast_timeline.short')
    await mount(d)
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
    expect(forecastSummary({ ...d, runout_date: '2026-12-20' })).toContain('sau kỳ lương 05/12')
    expect(forecastSummary({ ...d, runout_date: undefined, status: 'ok' })).toContain('dự kiến đủ tới kỳ lương')
    expect(forecastSummary({ ...d, runout_date: undefined, status: 'short' })).toContain('có khả năng hụt')
  })
})
