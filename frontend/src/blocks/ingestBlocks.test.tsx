import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

  it('fixture fx: số VND ước tính hiện ngay, số gốc và tỷ giá ở mục thu gọn; dòng chưa có tỷ giá ghi rõ, chat không cho sửa số', async () => {
    const { container } = draw(validBlock('ingest_review.fx'))
    expect(screen.getByText('−2.865.527 ₫')).toBeInTheDocument()
    const fxButton = screen.getByRole('button', { name: /111,11 USD/ })
    expect(fxButton).toHaveAttribute('aria-expanded', 'false')
    const panel = container.querySelector(`#${CSS.escape(fxButton.getAttribute('aria-controls')!)}`)!
    expect(panel).toHaveAttribute('aria-hidden', 'true')
    expect(panel).toHaveTextContent('Tỷ giá bán Vietcombank 25.790 ₫ ngày 10/11/2026')
    await userEvent.setup().click(fxButton)
    expect(fxButton).toHaveAttribute('aria-expanded', 'true')
    expect(panel).not.toHaveAttribute('aria-hidden', 'true')
    // dòng tra tỷ giá lỗi: không đoán số VND
    expect(screen.getByText('Chưa có số VND')).toBeInTheDocument()
    expect(screen.getByText('48,5 EUR')).toBeInTheDocument()
    expect(screen.getByText(/Chưa lấy được tỷ giá/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Số VND sẽ ghi')).toBeNull()
  })

  it('fixture pii: chip "Đã che" ở dòng có PII (chỉ loại, không giá trị), câu tổng ở đầu danh sách; dòng không che gì không có chip', () => {
    draw(validBlock('ingest_review.pii'))
    expect(screen.getByTestId('ingest-pii-total')).toHaveTextContent('Đã che 3 thông tin cá nhân trước khi lưu')
    const chips = screen.getAllByTestId('ingest-pii')
    expect(chips).toHaveLength(1)
    expect(chips[0]).toHaveTextContent('Đã che: tên, SĐT, số TK')
    expect(chips[0]).toHaveAccessibleName('Đã che trước khi lưu: tên người, số điện thoại, số tài khoản')
    const plain = document.querySelector('[data-ingest-row="9a1b2c3d-4e5f-4a6b-8c7d-000000000022"]') as HTMLElement
    expect(within(plain).queryByTestId('ingest-pii')).toBeNull()
  })

  it('fixture không có pii_masked: không chip, không câu tổng', () => {
    draw(validBlock('ingest_review.review'))
    expect(screen.queryByTestId('ingest-pii')).toBeNull()
    expect(screen.queryByTestId('ingest-pii-total')).toBeNull()
  })
  for (const name of ['ingest_review.bad_status', 'ingest_review.float_amount', 'ingest_review.transfer_row', 'ingest_review.fx_float_original', 'ingest_review.pii_raw_value']) {
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
