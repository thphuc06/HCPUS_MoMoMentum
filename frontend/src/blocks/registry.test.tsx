import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { BLOCK_TYPES, blockSchemas } from '@/contracts/blocks'
import { BlockRenderer, REGISTERED_TYPES, registry } from './registry'
import { Providers, fakeApi } from '@/test/helpers'
import {
  invalidBlock,
  invalidBlockEntries,
  schemaOnlyInvalidBlock,
  validBlock,
  validBlockEntries,
} from '@/test/fixtures'

function renderBlock(raw: unknown, ui?: 'cancelled') {
  return render(
    <Providers api={fakeApi()}>
      <BlockRenderer raw={raw} blockId="b1" ui={ui} />
    </Providers>,
  )
}

describe('registry khối UI', () => {
  it('mỗi loại khối trong hợp đồng đều có schema và component', () => {
    expect([...REGISTERED_TYPES].sort()).toEqual([...BLOCK_TYPES].sort())
    for (const t of BLOCK_TYPES) {
      expect(registry[t]).toBeDefined()
      expect(blockSchemas[t]).toBeDefined()
    }
  })

  describe('fixture hợp lệ', () => {
    for (const [name, block] of validBlockEntries()) {
      it(`${name}: vẽ khối, không rơi về fallback`, () => {
        const { container } = renderBlock(block)
        expect(container.querySelector('[data-block="fallback"]')).toBeNull()
        expect(container.querySelector(`[data-block="${String(block.type)}"], [data-notice]`)).not.toBeNull()
      })
    }
  })

  it('jar_summary hiện đủ 7 hũ, số dư và tổng lấy từ khối (không số gắn cứng)', () => {
    const block = validBlock('jar_summary.seven_jars') as { data: { jars: Array<{ name: string }>; jars_total_vnd: number } }
    const { container } = renderBlock(block)
    expect(container.querySelectorAll('[data-jar]')).toHaveLength(block.data.jars.length)
    expect(screen.getByText('Ăn uống')).toBeInTheDocument()
    expect(screen.getByText('380.000 ₫')).toBeInTheDocument()
    expect(screen.getByText('7.730.000 ₫')).toBeInTheDocument()
  })

  it('notice: tiêu đề và nội dung, có biểu tượng theo loại', () => {
    renderBlock(validBlock('notice.degraded'))
    expect(screen.getByRole('status')).toHaveAttribute('data-notice', 'degraded')
    expect(screen.getByText('Đang ở chế độ rút gọn')).toBeInTheDocument()
  })

  it('receipt: số tiền, hai hũ và mã giao dịch rút gọn', () => {
    renderBlock(validBlock('receipt.move'))
    expect(screen.getByText('Đã chuyển 100.000 ₫')).toBeInTheDocument()
    expect(screen.getByText('660.000 ₫')).toBeInTheDocument()
    expect(screen.getByText('480.000 ₫')).toBeInTheDocument()
    expect(screen.getByText('3B9F6C1E')).toBeInTheDocument()
  })

  describe('fixture sai schema: hiện fallback_text, không vỡ trang', () => {
    for (const [name, block] of invalidBlockEntries()) {
      it(`${name}`, () => {
        const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
        const { container } = renderBlock(block)
        const fb = container.querySelector('[data-block="fallback"]')
        expect(fb).not.toBeNull()
        if (typeof block.fallback_text === 'string') expect(fb!.textContent).toContain(block.fallback_text)
        warn.mockRestore()
      })
    }
  })

  it('type lạ: fallback_text của chính khối và gợi ý cập nhật ứng dụng', () => {
    const block = invalidBlock('block.unknown_type')
    const { container } = renderBlock(block)
    const fb = container.querySelector('[data-block="fallback"]')!
    expect(fb).toHaveAttribute('data-reason', 'unknown_type')
    expect(fb.textContent).toContain(String(block.fallback_text))
    expect(fb.textContent).toContain('Cập nhật ứng dụng')
  })

  it('thiếu cả fallback_text thì dùng câu mặc định', () => {
    renderBlock({ type: 'khong_co', x: 1 })
    expect(screen.getByText('Mình chưa hiển thị được phần này.')).toBeInTheDocument()
  })

  it('không phải đối tượng: fallback mặc định', () => {
    renderBlock('chuỗi trơn')
    expect(screen.getByText('Mình chưa hiển thị được phần này.')).toBeInTheDocument()
    renderBlock(null)
  })

  it('phiên bản khối mới hơn (v = 2): gợi ý cập nhật ứng dụng', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { container } = renderBlock(invalidBlock('jar_summary.version_2'))
    const fb = container.querySelector('[data-block="fallback"]')!
    expect(fb).toHaveAttribute('data-reason', 'newer_version')
    warn.mockRestore()
  })

  it('trường thừa (producer thêm trường tùy chọn): vẫn vẽ bình thường, bỏ trường lạ', () => {
    const { container } = renderBlock(schemaOnlyInvalidBlock('jar_summary.extra_field'))
    expect(container.querySelector('[data-block="jar_summary"]')).not.toBeNull()
  })

  it('error boundary từng khối: khối ném lỗi lúc vẽ chỉ làm mình hiện fallback, các khối khác vẫn sống', () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    // Khối confirm cần ApiProvider/ChatActions; thiếu provider thì useConfirmFlow ném lỗi khi vẽ.
    const { container } = render(
      <>
        <BlockRenderer raw={validBlock('confirm.move')} blockId="c1" />
        <BlockRenderer raw={validBlock('notice.out_of_scope')} blockId="n1" />
      </>,
    )
    const fb = container.querySelector('[data-block="fallback"]')
    expect(fb).toHaveAttribute('data-reason', 'render_error')
    expect(fb!.textContent).toContain(String(validBlock('confirm.move').fallback_text))
    expect(container.querySelector('[data-notice="out_of_scope"]')).not.toBeNull()
    err.mockRestore()
    warn.mockRestore()
  })
})
