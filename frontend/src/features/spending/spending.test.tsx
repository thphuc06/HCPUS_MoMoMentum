import type { ReactNode } from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CashflowResponse } from '@/api/cashflowSchemas'
import { ApiError } from '@/api/errors'
import type { JarFull } from '@/api/schemas'
import { restFixture } from '@/test/fixtures'
import { formatVnd as vnd } from '@/lib/format'
import { fakeApi, Providers } from '@/test/helpers'
import { backend, callsTo, json, mountApp } from '@/test/mountApp'
import { CashflowSection, CashflowView } from './CashflowSection'
import { PeriodCashflow } from './PeriodCashflow'
import { SpendingByJar } from './SpendingByJar'
import { SpendingTrend } from './SpendingTrend'
import { jarBars, trendMeasure, trendRows, trendSummary } from './model'

// Ba biểu đồ chi tiêu của màn Hoạt động (B1, B5, B7) với fixture hợp đồng `CashflowResponse.*` (sinh bằng mã Lambda thật trên
// PostgreSQL cục bộ). Biến thể (rỗng, chưa có kỳ trước, chi bằng 0, chi vượt lương, chưa tách được) dựng từ fixture bằng cách đổi
// đúng trường liên quan, để không có số nào gắn cứng ngoài fixture.

const minh = () => CashflowResponse.parse(restFixture('CashflowResponse.minh'))
const khoa = () => CashflowResponse.parse(restFixture('CashflowResponse.khoa_chua_co_ky_truoc'))
const CHART = { width: 360, height: 200 }
const lookup = new Map<string, JarFull>()

function zeroSpend(d: CashflowResponse): CashflowResponse {
  const zero = (x: CashflowResponse['daily'][number]) => ({ ...x, spent_vnd: 0, cumulative_vnd: 0, obligation_vnd: 0, regular_cumulative_vnd: 0 })
  return {
    ...d,
    current: { ...d.current, spent_vnd: 0, net_vnd: d.current.salary_income_vnd, obligation_vnd: 0, credit_vnd: 0, regular_spent_vnd: 0 },
    by_jar: [],
    daily: d.daily.map(zero),
    ...(d.previous_daily ? { previous_daily: d.previous_daily.map(zero) } : {}),
    ...(d.previous ? { previous: { ...d.previous, spent_vnd: 0, obligation_vnd: 0, credit_vnd: 0, regular_spent_vnd: 0 } } : {}),
    ...(d.change ? { change: { spent_vnd: 0, regular_vnd: 0 } } : {}),
  }
}

function withoutSplit(d: CashflowResponse): CashflowResponse {
  const strip = <T extends Record<string, unknown>>(o: T, keys: string[]) => Object.fromEntries(Object.entries(o).filter(([k]) => !keys.includes(k))) as T
  const day = ['obligation_vnd', 'regular_cumulative_vnd']
  return {
    ...d,
    split_complete: false,
    current: strip(d.current, ['obligation_vnd', 'credit_vnd', 'regular_spent_vnd']),
    ...(d.previous ? { previous: strip(d.previous, ['obligation_vnd', 'credit_vnd', 'regular_spent_vnd']) } : {}),
    ...(d.change ? { change: { spent_vnd: d.change.spent_vnd } } : {}),
    by_jar: d.by_jar.map((j) => strip(j, ['obligation_vnd', 'credit_vnd'])),
    daily: d.daily.map((x) => strip(x, day)),
    ...(d.previous_daily ? { previous_daily: d.previous_daily.map((x) => strip(x, day)) } : {}),
  }
}

const inRouter = (ui: ReactNode) => render(<MemoryRouter>{ui}</MemoryRouter>)
/** toHaveTextContent chuẩn hóa khoảng trắng của phần tử (NBSP thành dấu cách) nhưng không chuẩn hóa chuỗi mong đợi. */
const sp = (s: string) => s.replace(/\u00a0/g, ' ')

afterEach(() => {
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

describe('B1 chi theo hũ', () => {
  it('sắp theo mức chi, mỗi hũ là liên kết mở chi tiết hũ, nhãn đủ chữ, có vạch kỳ trước', () => {
    const d = minh()
    inRouter(<SpendingByJar data={d} lookup={lookup} />)
    const list = screen.getByRole('list', { name: 'Chi theo hũ kỳ này' })
    const links = within(list).getAllByRole('link')
    const spent = d.by_jar.map((j) => j.spent_vnd)
    expect([...spent].sort((a, b) => b - a)).toEqual(spent)
    expect(links).toHaveLength(d.by_jar.length)
    const top = d.by_jar[0]!
    expect(links[0]).toHaveAttribute('href', `/jars/${top.jar}`)
    expect(links[0]).toHaveAccessibleName(new RegExp(`^${top.name}: ${vnd(top.spent_vnd)}.*kỳ trước ${vnd(top.previous_spent_vnd!)}, tăng ${vnd(top.change_vnd!)}`))
    expect(list.querySelectorAll('[data-part="previous"]')).toHaveLength(d.by_jar.length)
    expect(screen.queryByText('Chưa có kỳ trước để so.')).toBeNull()
  })

  it('Trả sau (chấm) và khoản cố định (gạch chéo) là phần riêng của thanh, có chữ trong nhãn và chú giải', () => {
    const d = minh()
    const credit = d.by_jar.find((j) => (j.credit_vnd ?? 0) > 0)!
    inRouter(<SpendingByJar data={d} lookup={lookup} />)
    const row = document.querySelector(`li[data-jar="${credit.jar}"]`)!
    expect(row.querySelector('[data-part="credit"]')).not.toBeNull()
    expect(within(row as HTMLElement).getByRole('link')).toHaveAccessibleName(new RegExp(`gồm Trả sau ${vnd(credit.credit_vnd!)}`))
    const legend = screen.getByRole('list', { name: 'Chú giải' })
    for (const t of ['Chi thường', 'Trả sau', 'Khoản cố định', 'Kỳ trước cùng ngày']) expect(within(legend).getByText(t)).toBeInTheDocument()
    // tỷ lệ là cách vẽ: không phần nào vượt 1 và hũ lớn nhất chạm thang
    const bars = jarBars(d)
    for (const b of bars) expect(b.regular + b.credit + b.fixed).toBeLessThanOrEqual(1 + 1e-9)
    expect(Math.max(...bars.map((b) => Math.max(b.regular + b.credit + b.fixed, b.prev ?? 0)))).toBeCloseTo(1)
  })

  it('kỳ trước chưa có dữ liệu: không vạch, không chênh lệch, ghi rõ chưa có kỳ trước', () => {
    inRouter(<SpendingByJar data={khoa()} lookup={lookup} />)
    expect(document.querySelectorAll('[data-part="previous"]')).toHaveLength(0)
    expect(screen.getByText('Chưa có kỳ trước để so.')).toBeInTheDocument()
    expect(screen.queryByText(/Kỳ trước cùng ngày/)).toBeNull()
  })

  it('dữ liệu rỗng: trạng thái rỗng nói thật', () => {
    inRouter(<SpendingByJar data={{ ...khoa(), by_jar: [] }} lookup={lookup} />)
    expect(screen.getByTestId('by-jar-empty')).toHaveTextContent('Kỳ này bạn chưa chi gì.')
  })

  it('kỳ này chi bằng 0 nhưng kỳ trước có: hàng vẫn hiện, thanh rỗng, vạch kỳ trước, giảm đúng số server trả', () => {
    const d = minh()
    const data: CashflowResponse = {
      ...d,
      by_jar: d.by_jar.map((j) => ({ ...j, spent_vnd: 0, tx_count: 0, obligation_vnd: 0, credit_vnd: 0, change_vnd: -(j.previous_spent_vnd ?? 0) })),
    }
    inRouter(<SpendingByJar data={data} lookup={lookup} />)
    const withPrev = data.by_jar.find((j) => (j.previous_spent_vnd ?? 0) > 0)!
    const row = document.querySelector(`li[data-jar="${withPrev.jar}"]`) as HTMLElement
    expect(row.querySelector('[data-part="regular"]')).toBeNull()
    expect(row.querySelector('[data-part="previous"]')).not.toBeNull()
    expect(within(row).getByRole('link')).toHaveAccessibleName(new RegExp(`giảm ${vnd(withPrev.previous_spent_vnd!)}`))
  })
})

describe('B7 thu và chi của kỳ', () => {
  it('hàng số gọn: lương vào, đã chi, còn lại (số server trả), câu đủ cho trình đọc màn hình', () => {
    const d = minh()
    render(<PeriodCashflow data={d} />)
    expect(screen.getByRole('heading', { name: 'Kỳ lương này' })).toBeInTheDocument()
    expect(screen.getByTestId('cashflow-spent')).toHaveTextContent(sp(vnd(d.current.spent_vnd)))
    expect(screen.getByTestId('cashflow-net')).toHaveTextContent(sp(vnd(d.current.net_vnd)))
    expect(screen.getByText(new RegExp(sp(`lương vào ${vnd(d.current.salary_income_vnd)}, đã chi ${vnd(d.current.spent_vnd)}, còn ${vnd(d.current.net_vnd)}`)))).toHaveClass('sr-only')
    const bar = screen.getByTestId('cashflow-bar')
    expect(bar).toHaveAttribute('aria-hidden', 'true')
    expect(bar.querySelector('[data-part="over"]')).toBeNull()
    // tiền vào khác chỉ nằm trong "Cách tính"
    expect(screen.getByRole('button', { name: 'Cách tính' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('chi vượt lương: phần vượt gạch chéo, nhãn chữ "Chi quá lương"', () => {
    const d = minh()
    const spent = d.current.salary_income_vnd * 2
    render(<PeriodCashflow data={{ ...d, current: { ...d.current, spent_vnd: spent, net_vnd: d.current.salary_income_vnd - spent } }} />)
    expect(screen.getByText('Chi quá lương', { selector: 'dt' })).toBeInTheDocument()
    expect(screen.getByTestId('cashflow-bar').querySelector('[data-part="over"]')).not.toBeNull()
  })

  it('lương chưa về: không có "Còn lại", ghi rõ lương chưa về; chi bằng 0 thì thanh rỗng', () => {
    const d = zeroSpend(minh())
    render(<PeriodCashflow data={{ ...d, current: { ...d.current, salary_income_vnd: 0, net_vnd: 0 } }} />)
    expect(screen.getByText('Lương kỳ này chưa về.')).toBeInTheDocument()
    expect(screen.queryByTestId('cashflow-net')).toBeNull()
    expect(screen.getByTestId('cashflow-spent')).toHaveTextContent(sp(vnd(0)))
    expect((screen.getByTestId('cashflow-bar').querySelector('[data-part="spent"]') as HTMLElement).style.width).toBe('0%')
  })
})

describe('B5 lũy kế so với kỳ trước', () => {
  it('câu tóm tắt dựng từ chênh lệch chi thường ngày của server; bảng sr-only đủ từng ngày; thanh kéo đọc số', async () => {
    const d = minh()
    render(<SpendingTrend data={d} chartSize={CHART} />)
    expect(trendMeasure(d)).toBe('regular')
    expect(screen.getByTestId('trend-summary')).toHaveTextContent(sp(`Chi thường ngày nhanh hơn kỳ trước ${vnd(d.change!.regular_vnd!)} tính tới hôm nay.`))
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(1 + Math.max(d.daily.length, d.previous_daily!.length))
    const slider = screen.getByRole('slider', { name: 'Chọn ngày của kỳ để xem chi lũy kế' })
    const pick = d.period.day_index - 7
    fireEvent.change(slider, { target: { value: String(pick) } })
    const today = d.daily[pick - 1]!
    const prevSame = d.previous_daily![pick - 1]!
    expect(screen.getByTestId('trend-readout')).toHaveTextContent(
      sp(`Ngày ${pick} · kỳ này ${vnd(today.regular_cumulative_vnd!)} · kỳ trước ${vnd(prevSame.regular_cumulative_vnd!)}`),
    )
    expect(screen.getByTestId('trend-chart')).toHaveAccessibleName(
      `Đến ngày ${d.period.day_index} của kỳ bạn chi thường ngày ${vnd(d.current.regular_spent_vnd!)}, kỳ trước cùng thời điểm ${vnd(d.previous!.regular_spent_vnd!)}.`,
    )
    await waitFor(() => expect(screen.getByTestId('trend-chart').querySelector('svg')).not.toBeNull())
  })

  it('kỳ trước chưa có dữ liệu: một đường, câu "Chưa có kỳ trước để so.", bảng không có cột kỳ trước', () => {
    const d = khoa()
    render(<SpendingTrend data={d} chartSize={CHART} />)
    expect(screen.getByTestId('trend-summary')).toHaveTextContent('Chưa có kỳ trước để so.')
    expect(within(screen.getByRole('table')).getAllByRole('columnheader')).toHaveLength(2)
    expect(trendRows(d).every((r) => r.previous === undefined)).toBe(true)
    expect(screen.queryByText('Kỳ trước', { selector: 'li' })).toBeNull()
  })

  it('chi bằng 0 cả hai kỳ: trạng thái rỗng, không vẽ', () => {
    render(<SpendingTrend data={zeroSpend(minh())} chartSize={CHART} />)
    expect(screen.getByTestId('trend-empty')).toHaveTextContent('Kỳ này bạn chưa chi gì.')
    expect(screen.queryByTestId('trend-chart')).toBeNull()
  })

  it('kỳ mới bắt đầu (ngày 2): chỉ số, chưa vẽ đường', () => {
    const d = minh()
    render(<SpendingTrend data={{ ...d, period: { ...d.period, day_index: 2 }, daily: d.daily.slice(0, 2) }} chartSize={CHART} />)
    expect(screen.getByTestId('trend-early')).toBeInTheDocument()
    expect(screen.queryByTestId('trend-chart')).toBeNull()
  })

  it('server chưa tách được nghĩa vụ: vẽ tổng chi, câu dùng chênh lệch tổng', () => {
    const d = withoutSplit(minh())
    expect(CashflowResponse.safeParse(d).success).toBe(true)
    expect(trendMeasure(d)).toBe('total')
    expect(trendSummary(d)).toBe(`Chi nhanh hơn kỳ trước ${vnd(d.change!.spent_vnd)} tính tới hôm nay.`)
    expect(trendRows(d)[d.period.day_index - 1]!.current).toBe(d.current.spent_vnd)
  })
})

describe('phần chi tiêu ở màn Hoạt động', () => {
  it('tải GET /cashflow, chuyển giữa Theo hũ và Theo ngày', async () => {
    const api = fakeApi()
    render(
      <MemoryRouter>
        <Providers api={api}>
          <CashflowSection />
        </Providers>
      </MemoryRouter>,
    )
    expect(await screen.findByTestId('period-cashflow')).toBeInTheDocument()
    expect(api.getCashflow).toHaveBeenCalledTimes(1)
    const byJar = screen.getByRole('button', { name: 'Theo hũ' })
    expect(byJar).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('spending-by-jar')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Theo ngày' }))
    expect(screen.getByTestId('spending-trend')).toBeInTheDocument()
    expect(screen.queryByTestId('spending-by-jar')).toBeNull()
  })

  it('route chưa có trên server (404): không hiện gì; lỗi khác: báo lỗi và thử lại được', async () => {
    const missing = fakeApi({ getCashflow: vi.fn(async () => Promise.reject(new ApiError('INTERNAL_ERROR', 404))) })
    const { container, unmount } = render(
      <MemoryRouter>
        <Providers api={missing}>
          <CashflowSection />
        </Providers>
      </MemoryRouter>,
    )
    await waitFor(() => expect(missing.getCashflow).toHaveBeenCalled())
    await waitFor(() => expect(container.querySelector('[data-state="loading"]')).toBeNull())
    expect(screen.queryByTestId('cashflow-section')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    unmount()

    let fail = true
    const flaky = fakeApi({
      getCashflow: vi.fn(async () => {
        if (fail) throw new ApiError('DATABASE_UNAVAILABLE', 503)
        return minh()
      }),
    })
    render(
      <MemoryRouter>
        <Providers api={flaky}>
          <CashflowSection />
        </Providers>
      </MemoryRouter>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('Chưa tải được chi tiêu kỳ này')
    fail = false
    await userEvent.click(screen.getByRole('button', { name: /Thử lại/ }))
    expect(await screen.findByTestId('period-cashflow')).toBeInTheDocument()
  })

  it('giảm chuyển động: không có lớp chuyển động; bình thường thì thanh chạy một lần', () => {
    const d = minh()
    const { unmount } = inRouter(<CashflowView data={d} lookup={lookup} animate={false} />)
    expect(document.querySelector('.motion-grow-x')).toBeNull()
    unmount()
    inRouter(<CashflowView data={d} lookup={lookup} animate />)
    expect(document.querySelectorAll('.motion-grow-x').length).toBeGreaterThan(0)
  })

  it('CashflowSection đọc prefers-reduced-motion: bật giảm chuyển động thì không chạy', async () => {
    vi.stubGlobal('matchMedia', (q: string) => ({ matches: q.includes('reduce'), addEventListener() {}, removeEventListener() {} }))
    render(
      <MemoryRouter>
        <Providers api={fakeApi()}>
          <CashflowSection />
        </Providers>
      </MemoryRouter>,
    )
    expect(await screen.findByTestId('period-cashflow')).toBeInTheDocument()
    expect(document.querySelector('.motion-grow-x')).toBeNull()
  })
})

describe('màn Hoạt động (cả ứng dụng)', () => {
  it('đầu màn có thu chi kỳ này và chi theo hũ; chạm một hũ mở Chi tiết hũ; danh sách giao dịch vẫn ở dưới', async () => {
    const d = minh()
    const { calls, router } = mountApp(backend(), '/activity')
    expect(await screen.findByRole('heading', { name: 'Tiêu vào đâu' })).toBeInTheDocument()
    expect(callsTo(calls, 'GET', '/cashflow')).toHaveLength(1)
    expect(await screen.findByTestId('activity-list')).toBeInTheDocument()
    const top = d.by_jar[0]!
    await userEvent.click(within(screen.getByRole('list', { name: 'Chi theo hũ kỳ này' })).getAllByRole('link')[0]!)
    await waitFor(() => expect(router.state.location.pathname).toBe(`/jars/${top.jar}`))
  })

  it('server chưa có /cashflow (404): màn Hoạt động như cũ', async () => {
    mountApp(backend({ 'GET /cashflow': () => json(404, { message: 'Not Found' }) }), '/activity')
    expect(await screen.findByTestId('activity-list')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Tiêu vào đâu' })).toBeNull()
  })
})
