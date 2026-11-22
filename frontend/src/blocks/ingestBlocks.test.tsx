import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Providers, fakeApi } from '@/test/helpers'
import { invalidBlock, validBlock } from '@/test/fixtures'
import { mostAffectedJar } from '@/features/ingest/CoverageChange'
import type { CoverageChangeData } from '@/contracts/blocks'
import { BlockRenderer } from './registry'

// Hai khối phase 5 (F6) trong registry: parse fixture hợp lệ, fallback_text với fixture sai, chỉ xem (không chọn hay đổi hũ).

const draw = (raw: unknown) =>
  render(
    <Providers api={fakeApi()}>
      <BlockRenderer raw={raw} blockId="b1" />
    </Providers>,
  )

describe('ingest_review', () => {
  it('fixture review: đủ dòng, số tiền định dạng, trạng thái tự thêm / cần duyệt / đã có trong ví, chỉ xem', () => {
    const { container } = draw(validBlock('ingest_review.review'))
    expect(container.querySelector('[data-block="ingest_review"]')).not.toBeNull()
    const list = screen.getByRole('list', { name: 'Dòng đã đọc' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(5)
    expect(screen.getByText('−85.000 ₫')).toBeInTheDocument()
    expect(screen.getByText('+2.000.000 ₫')).toBeInTheDocument()
    expect(screen.getAllByText('Tự thêm')).toHaveLength(2)
    expect(screen.getAllByText('Cần duyệt')).toHaveLength(2)
    expect(screen.getByText('Đã có trong ví')).toBeInTheDocument()
    expect(screen.getByTestId('ingest-counts')).toHaveTextContent('Đọc được 5 dòng: 2 tự thêm, 2 cần duyệt, 1 đã có trong ví.')
    expect(screen.queryByRole('checkbox')).toBeNull()
    expect(screen.queryByRole('button', { name: /Đổi hũ/ })).toBeNull()
  })

  it('fixture done: trạng thái đã thêm / đã bỏ', () => {
    draw(validBlock('ingest_review.done'))
    expect(screen.getAllByText('Đã thêm')).toHaveLength(3)
    expect(screen.getByText('Đã bỏ')).toBeInTheDocument()
  })

  for (const name of ['ingest_review.bad_status', 'ingest_review.float_amount', 'ingest_review.transfer_row']) {
    it(`sai schema (${name}): hiện fallback_text`, () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const raw = invalidBlock(name)
      const { container } = draw(raw)
      expect(container.querySelector('[data-block="fallback"]')?.textContent).toContain(String(raw.fallback_text))
      warn.mockRestore()
    })
  }
})

describe('coverage_change', () => {
  it('độ phủ trước → sau, số dòng, chi ngoài ví, câu "số dư hũ không đổi"', () => {
    draw(validBlock('coverage_change.added'))
    expect(screen.getByTestId('coverage-ratios')).toHaveAccessibleName('Độ phủ dữ liệu từ 62% lên 81%')
    expect(screen.getByTestId('rows-added')).toHaveTextContent('3')
    expect(screen.getByText('205.000 ₫')).toBeInTheDocument()
    expect(screen.getByText('2.000.000 ₫')).toBeInTheDocument()
    expect(screen.getByText('Số dư hũ không đổi — đây là chi tiêu ngoài ví.')).toBeInTheDocument()
  })

  it('không có before/after: không bịa phần trăm', () => {
    draw(validBlock('coverage_change.no_income'))
    expect(screen.queryByTestId('coverage-ratios')).toBeNull()
    expect(screen.getByText(/Chưa tính được độ phủ/)).toBeInTheDocument()
  })

  for (const name of ['coverage_change.bad_refresh', 'coverage_change.ratio_percent']) {
    it(`sai schema (${name}): hiện fallback_text`, () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const raw = invalidBlock(name)
      const { container } = draw(raw)
      expect(container.querySelector('[data-block="fallback"]')?.textContent).toContain(String(raw.fallback_text))
      warn.mockRestore()
    })
  }

  it('hũ ảnh hưởng nhiều nhất: theo tổng chi các dòng đã thêm, không có bảng duyệt thì hũ đầu', () => {
    const cov = (validBlock('coverage_change.added') as { data: CoverageChangeData }).data
    const rows = (validBlock('ingest_review.done') as { data: { rows: Array<{ kind: string; review_status: string; amount_vnd: number; suggested_jar?: { code: string } }> } }).data.rows
    expect(mostAffectedJar(cov, rows)).toBe('giai_tri')
    expect(mostAffectedJar(cov)).toBe('an_uong')
    expect(mostAffectedJar({ ...cov, jars_affected: [] }, rows)).toBeNull()
  })
})
