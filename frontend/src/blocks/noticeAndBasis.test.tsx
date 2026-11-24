import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Providers, fakeApi, fakeChatActions } from '@/test/helpers'
import { validBlock } from '@/test/fixtures'
import { BlockRenderer } from './registry'

// Đi cảnh 24/11: notice kind info hiện "Mã: ROADMAP_PROPOSAL_REPLACED" cho người dùng; thẻ tác động nghĩa vụ ghi "cập nhật 24/11 14:32"
// trong khi ngày mô phỏng là 21/11.

type Json = Record<string, any>

function show(raw: unknown) {
  return render(
    <Providers api={fakeApi()} actions={fakeChatActions()}>
      <BlockRenderer raw={raw} blockId="b1" />
    </Providers>,
  )
}

function notice(kind: string, code: string): Json {
  const b = structuredClone(validBlock('notice.info')) as Json
  b.data = { kind, title: 'Đã thay bản đề xuất đang chờ', message: 'Bản này thay bản đề xuất phiên bản 3 đang chờ bạn chọn.', code }
  return b
}

describe('khối notice: mã nội bộ', () => {
  it('notice info không hiện mã cho người dùng', () => {
    show(notice('info', 'ROADMAP_PROPOSAL_REPLACED'))
    expect(screen.getByText('Đã thay bản đề xuất đang chờ')).toBeInTheDocument()
    expect(screen.queryByText(/ROADMAP_PROPOSAL_REPLACED/)).toBeNull()
    expect(screen.queryByText(/Mã:/)).toBeNull()
  })

  it.each(['degraded', 'low_data', 'out_of_scope'])('notice %s cũng không hiện mã', (kind) => {
    show(notice(kind, 'MODEL_BUDGET_EXCEEDED'))
    expect(screen.queryByText(/Mã:/)).toBeNull()
  })

  it('notice lỗi vẫn hiện mã để báo lỗi', () => {
    show(validBlock('notice.error_retry'))
    expect(screen.getByText('Mã: FORECAST_UNAVAILABLE')).toBeInTheDocument()
  })
})

describe('chân thẻ số liệu: ngày mô phỏng', () => {
  it('obligation_impact ghi thời điểm tính theo ngày mô phỏng của khối, giờ thật', () => {
    const b = structuredClone(validBlock('obligation_impact.minh_headphones')) as Json
    b.source.app_date = '2026-11-21'
    b.data.basis.computed_at = '2026-11-24T07:32:00Z' // 14:32 giờ Việt Nam ngày thật 24/11
    show(b)
    const basis = screen.getByTestId('basis')
    expect(basis).toHaveTextContent('Dựa trên dự báo cập nhật 21/11/2026 · 14:32')
    expect(basis).not.toHaveTextContent('24/11')
  })

  it('affordability_card dùng cùng cách ghi', () => {
    const b = structuredClone(validBlock('affordability_card.credit_only')) as Json
    b.source.app_date = '2026-11-21'
    b.data.basis.computed_at = '2026-11-24T07:32:00Z'
    show(b)
    expect(screen.getByTestId('basis')).toHaveTextContent('21/11/2026 · 14:32')
    expect(screen.getByTestId('basis')).not.toHaveTextContent('24/11')
  })
})
