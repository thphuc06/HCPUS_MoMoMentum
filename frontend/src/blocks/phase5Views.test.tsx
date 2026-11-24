import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { ChatLauncherContext } from '@/chat/launcher'
import { BehaviorInsightBlock, CitationBlock } from '@/contracts/blocks'
import { formatEvidencePeriod, formatEvidenceValue, shareGapText, sharePairs, weekdayLabel } from '@/features/behavior/format'
import { Providers, fakeApi } from '@/test/helpers'
import { validBlock } from '@/test/fixtures'
import { BlockRenderer } from './registry'

// Hai khối phase 5: behavior_insight (nhận xét hành vi kèm bằng chứng số và một việc cần làm), citation (nguồn biểu phí).

function inRouter(block: Record<string, unknown>, launcher = { open: vi.fn(), close: vi.fn() }) {
  const router = createMemoryRouter([
    { path: '/', element: <BlockRenderer raw={block} blockId={String(block.id)} /> },
    { path: '/profile', element: <p>MÀN HỒ SƠ</p> },
    { path: '/roadmap', element: <p>MÀN LỘ TRÌNH</p> },
  ])
  render(
    <ChatLauncherContext.Provider value={launcher}>
      <Providers api={fakeApi()}>
        <RouterProvider router={router} />
      </Providers>
    </ChatLauncherContext.Provider>,
  )
  return { router, launcher }
}

describe('behavior_insight', () => {
  it('câu nhận xét, bằng chứng theo đơn vị (phần trăm, ngày, tiền, cửa sổ), nhãn AI, việc nên làm', () => {
    const block = BehaviorInsightBlock.parse(validBlock('behavior_insight.chi_don_sau_luong'))
    render(<Providers api={fakeApi()}><BlockRenderer raw={block} blockId={block.id} /></Providers>)
    const card = screen.getByRole('region', { name: `Nhận xét: ${block.data.insight.headline}` })
    expect(within(card).getByText(block.data.insight.headline)).toBeInTheDocument()
    expect(within(card).getByText(block.data.insight.detail!)).toBeInTheDocument()
    const row = (key: string) => card.querySelector(`[data-evidence="${key}"]`) as HTMLElement
    expect(row('first_week_share')).toHaveTextContent('46%')
    expect(row('first_week_share')).toHaveTextContent('22/09–21/11')
    expect(row('first_week_days')).toHaveTextContent('7 ngày')
    expect(row('first_week_spend_vnd')).toHaveTextContent('2.580.000 ₫')
    expect(within(card).getByText('AI tóm tắt')).toBeInTheDocument()
    expect(within(card).getByText('Tin cậy vừa')).toBeInTheDocument()
    expect(within(card).getByTestId('behavior-next-step')).toHaveTextContent(block.data.next_step.label)
    // Ngoài router (không có chỗ điều hướng): không có nút hành động (chỉ có nút mở/thu gọn), và khối không tự ghi gì
    expect(within(card).queryAllByRole('button').filter((b) => !b.hasAttribute('aria-expanded'))).toHaveLength(0)
    // Câu giải thích và bảng bằng chứng thu gọn sau "Xem căn cứ"; thanh B3 (nếu có) hiện ngay
    expect(within(card).getByRole('button', { name: 'Xem căn cứ' })).toHaveAttribute('aria-expanded', 'false')
    expect(row('first_week_share').closest('[data-disclosure-panel]')).toHaveAttribute('data-disclosure-panel', 'closed')
  })

  it('trong chat: việc có hành động thì "Thực hiện ở Hồ sơ" đóng chat rồi mở phần nhận xét của Hồ sơ (không ghi từ khối)', async () => {
    const block = validBlock('behavior_insight.thu_bay_chuyen_hu')
    const { router, launcher } = inRouter(block)
    expect(screen.getByText('Thứ Bảy', { selector: 'dd' })).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Thực hiện ở Hồ sơ' }))
    expect(launcher.close).toHaveBeenCalled()
    expect(await screen.findByText('MÀN HỒ SƠ')).toBeInTheDocument()
    expect(router.state.location.hash).toBe('#nhan-xet-hanh-vi')
  })

  it('việc không có hành động và nhận xét không do AI viết: không có nhãn AI, nút chỉ mở Hồ sơ để xem', () => {
    inRouter(validBlock('behavior_insight.tra_sau_khong_hanh_dong'))
    expect(screen.queryByText('AI tóm tắt')).toBeNull()
    expect(screen.getByRole('button', { name: 'Xem các nhận xét ở Hồ sơ' })).toBeInTheDocument()
    expect(screen.getByText('5 lần')).toBeInTheDocument()
    expect(screen.getByText('60 ngày')).toBeInTheDocument()
  })

  it('đọc số theo đơn vị hợp đồng', () => {
    expect(formatEvidenceValue({ value: 0.38, unit: 'ratio' })).toBe('38%')
    expect(formatEvidenceValue({ value: 12.5, unit: 'percent' })).toBe('12,5%')
    expect(formatEvidenceValue({ value: 21, unit: 'hour' })).toBe('21:00')
    expect(formatEvidenceValue({ value: 7, unit: 'weekday' })).toBe('Chủ nhật')
    expect(formatEvidenceValue({ value: 1, unit: 'weekday' })).toBe('Thứ Hai')
    expect(weekdayLabel(6)).toBe('Thứ Bảy')
    expect(formatEvidencePeriod({})).toBe('')
    expect(formatEvidencePeriod({ period_from: '2026-11-05' })).toBe('từ 05/11')
  })
})

describe('behavior_insight: B3 thanh "phần chi" so với "phần số ngày"', () => {
  const withEvidence = (name: string, patch: (ev: Array<Record<string, unknown>>) => void) => {
    const raw = structuredClone(validBlock(name)) as { data: { insight: { evidence: Array<Record<string, unknown>> } } }
    patch(raw.data.insight.evidence)
    return BehaviorInsightBlock.parse(raw)
  }

  it('cặp phần chi tuần đầu sau lương và phần số ngày: hai thanh, nhãn đủ cho trình đọc màn hình, chênh lệch bằng chữ; bảng bằng chứng giữ nguyên', () => {
    const block = withEvidence('behavior_insight.chi_don_sau_luong', (ev) => {
      ev.push({ key: 'first_week_day_share', label: 'Phần số ngày thuộc tuần đầu sau lương', value: 23, unit: 'percent' })
    })
    render(<Providers api={fakeApi()}><BlockRenderer raw={block} blockId={block.id} /></Providers>)
    const card = screen.getByRole('region', { name: `Nhận xét: ${block.data.insight.headline}` })
    const bars = within(card).getByTestId('evidence-bars')
    expect(within(bars).getByRole('img', {
      name: 'Phần chi trong 7 ngày đầu sau lương 46%; Phần số ngày thuộc tuần đầu sau lương 23%. Nhiều hơn mức chi đều 23 điểm phần trăm.',
    })).toBeInTheDocument()
    const fills = bars.querySelectorAll<HTMLElement>('[style*="width"]')
    expect([...fills].map((f) => f.style.width)).toEqual(['46%', '23%'])
    // Bảng bằng chứng vẫn là bản tương đương đầy đủ
    expect(card.querySelector('[data-evidence="first_week_day_share"]')).toHaveTextContent('23%')
    expect(card.querySelector('[data-evidence="first_week_share"]')).toHaveTextContent('46%')
  })

  it('cuối tuần đơn vị tỷ lệ cũng vẽ; thiếu một vế hoặc khác đơn vị thì không vẽ thanh (giữ bảng như cũ)', () => {
    const weekend = [
      { key: 'weekend_share', label: 'Phần chi vào thứ Bảy, Chủ nhật', value: 0.37, unit: 'ratio' },
      { key: 'weekend_day_share', label: 'Phần số ngày là cuối tuần', value: 0.26, unit: 'ratio' },
    ] as const
    const pairs = sharePairs(weekend as never)
    expect(pairs.map((p) => [p.share.key, Math.round(p.sharePct), Math.round(p.basePct)])).toEqual([['weekend_share', 37, 26]])
    expect(shareGapText(pairs[0]!)).toBe('Nhiều hơn mức chi đều 11 điểm phần trăm.')
    expect(sharePairs([weekend[0]] as never)).toEqual([])
    expect(sharePairs([weekend[0], { ...weekend[1], unit: 'percent', value: 26 }] as never)).toEqual([])
    expect(shareGapText({ sharePct: 20, basePct: 30 })).toBe('Ít hơn mức chi đều 10 điểm phần trăm.')
    expect(shareGapText({ sharePct: 30, basePct: 30 })).toBe('Bằng mức chi đều.')

    const block = BehaviorInsightBlock.parse(validBlock('behavior_insight.chi_don_sau_luong'))
    render(<Providers api={fakeApi()}><BlockRenderer raw={block} blockId={block.id} /></Providers>)
    expect(screen.queryByTestId('evidence-bars')).toBeNull()
  })
})

describe('citation', () => {
  it('mỗi nguồn: tên là liên kết https mở trang mới, ngày hiệu lực, loại phí, câu trích; không có số tiền', () => {
    const block = CitationBlock.parse(validBlock('citation.nhieu_nguon'))
    const { container } = render(<BlockRenderer raw={block} blockId={block.id} />)
    const section = screen.getByRole('region', { name: 'Nguồn biểu phí Trả sau (mô phỏng)' })
    const links = within(section).getAllByRole('link')
    expect(links).toHaveLength(block.data.items.length)
    block.data.items.forEach((item, i) => {
      expect(links[i]).toHaveAttribute('href', item.source_url)
      expect(links[i]).toHaveAttribute('target', '_blank')
      expect(links[i]).toHaveAttribute('rel', 'noopener noreferrer')
      expect(links[i]).toHaveTextContent(item.source_name)
      expect(within(section).getByText(item.excerpt!)).toBeInTheDocument()
    })
    expect(within(section).getByText('Hiệu lực từ 31/03/2026')).toBeInTheDocument()
    expect(within(section).getByText('Hiệu lực từ 01/11/2026')).toBeInTheDocument()
    expect(within(section).getByText('Phí dịch vụ hằng tháng')).toBeInTheDocument()
    expect(within(section).getByText('Phí trả chậm')).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/₫/)
  })

  it('loại phí chưa có tên tiếng Việt: hiện mã gốc thay vì đoán', () => {
    const block = CitationBlock.parse(validBlock('citation.phi_tra_sau'))
    block.data.items[0]!.fee_types = ['annual_fee']
    render(<BlockRenderer raw={block} blockId={block.id} />)
    expect(screen.getByText('annual_fee')).toBeInTheDocument()
  })
})

describe('proactive_card bản tin (phase 5) trong chat', () => {
  it('nút "Xem lộ trình mới" (open_roadmap) đóng chat và mở trang Lộ trình; không có Để sau / Ít nhắc loại này trong chat', async () => {
    const { launcher } = inRouter(validBlock('proactive_card.ban_tin_lo_trinh'))
    expect(screen.queryByRole('button', { name: 'Ít nhắc loại này' })).toBeNull()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Xem lộ trình mới' }))
    expect(launcher.close).toHaveBeenCalled()
    expect(await screen.findByText('MÀN LỘ TRÌNH')).toBeInTheDocument()
  })
})
