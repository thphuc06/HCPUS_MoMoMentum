import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { validBlock } from '@/test/fixtures'
import { BlockRenderer } from './registry'

function renderFixture(name: string) {
  const raw = validBlock(name)
  const { container } = render(<BlockRenderer raw={raw} blockId={String(raw.id)} />)
  expect(container.querySelector('[data-block="fallback"]')).toBeNull()
  expect(container.querySelector(`[data-block="${String(raw.type)}"]`)).toBeInTheDocument()
}

describe('điểm chống chịu', () => {
  it('hiện điểm, nhóm điểm, bốn thành phần, điểm lần trước và lưu ý', () => {
    renderFixture('resilience_score.minh')
    const gauge = screen.getByRole('img', { name: 'Điểm chống chịu 58/100, nhóm Vừa' })
    expect(within(gauge).getByText('58/100')).toBeInTheDocument()
    expect(within(gauge).getByText('Vừa')).toBeInTheDocument()
    const [save] = screen.getAllByRole('listitem')
    expect(screen.getAllByRole('listitem')).toHaveLength(4)
    expect(within(save!).getByText('Tiết kiệm')).toBeInTheDocument()
    expect(within(save!).getByText('15 điểm')).toBeInTheDocument()
    expect(within(save!).getByText('Yếu nhất')).toBeInTheDocument()
    expect(within(save!).getByText(/Số dư khả dụng đủ sống 27 ngày/)).toBeInTheDocument()
    expect(screen.getByText('Điểm lần trước 61/100')).toBeInTheDocument()
    expect(screen.getByText(/^Đây không phải điểm tín dụng/)).toBeInTheDocument()
  })

  it('hiện Kế hoạch không áp dụng khi chưa có mục tiêu', () => {
    renderFixture('resilience_score.no_goal')
    expect(screen.getByRole('img', { name: 'Điểm chống chịu 55/100, nhóm Vừa' })).toBeInTheDocument()
    expect(screen.getByText('Kế hoạch')).toBeInTheDocument()
    expect(screen.getByText('Không áp dụng')).toBeInTheDocument()
    expect(screen.getByText('Chưa có mục tiêu nên chưa tính thành phần Kế hoạch.')).toBeInTheDocument()
    expect(screen.queryByText(/^Điểm lần trước/)).toBeNull()
  })
})

describe('kết quả cú sốc', () => {
  it.each([
    ['mat_viec', 'Mất việc 2 tháng', '58 → 34', '-24 điểm', 'Hụt', 'Trụ được 27 ngày', '8.890.000 ₫', '9 ngày'],
    ['tien_tro_tang', 'Tiền trọ tăng', '58 → 52', '-6 điểm', 'Đủ', 'Trụ hết 90 ngày dự báo', '0 ₫', null],
    ['om_mot_tuan_khong_co_hu_du_phong', 'Ốm một tuần', '55 → 50', '-5 điểm', 'Sát', 'Trụ được 6 ngày', '100.000 ₫', null],
  ] as const)('%s hiện điểm, trạng thái và số ngày trụ được', (fixture, shock, score, delta, status, runway, shortfall, emergency) => {
    renderFixture(`stress_result.${fixture}`)
    expect(screen.getByRole('heading', { name: shock })).toBeInTheDocument()
    for (const label of [score, delta, status, runway, shortfall]) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    if (emergency) {
      expect(screen.getByText('Hũ Dự phòng')).toBeInTheDocument()
      expect(screen.getByText(emergency)).toBeInTheDocument()
      expect(screen.getByText('Khoản thiếu từ 18/12/2026')).toBeInTheDocument()
    } else {
      expect(screen.queryByText('Hũ Dự phòng')).toBeNull()
    }
  })
})

describe('lộ trình', () => {
  it('hiện phiên bản đề xuất, giai đoạn, số bước và lý do mở được', async () => {
    const user = userEvent.setup()
    renderFixture('roadmap.minh_v3_proposed')
    expect(screen.getByRole('heading', { name: 'Lộ trình · Phiên bản 3' })).toBeInTheDocument()
    expect(screen.getByText('Bản đề xuất')).toBeInTheDocument()
    expect(screen.getByText('Khả thi sau điều chỉnh')).toBeInTheDocument()
    expect(screen.getByText(/Chi Ăn uống mỗi tuần tăng.*giữ mức đó 2 tuần/)).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Số bước theo trạng thái' })).toHaveTextContent('Chờ 5')
    expect(screen.getByRole('heading', { name: 'Ổn định tháng này' })).toBeInTheDocument()
    // Đứng riêng (không có danh sách hũ của người dùng): không lộ mã hũ thô; tên lấy từ mục tiêu của khối vẫn hiện.
    expect(screen.queryByText(/giai_tri|nghia_vu|an_uong|du_phong/)).toBeNull()
    expect(screen.getAllByText('Hũ Du lịch')).toHaveLength(2)
    expect(screen.getByText('300.000 ₫')).toBeInTheDocument()

    const why = screen.getAllByText('Vì sao')[0]!
    const details = why.closest('details')!
    expect(details).not.toHaveAttribute('open')
    await user.click(why)
    expect(details).toHaveAttribute('open')
    expect(within(details).getByText(/^Khoản Trả sau/)).toBeVisible()
    await user.click(why)
    expect(details).not.toHaveAttribute('open')
  })

  it('hiện đủ trạng thái bước bằng chữ trên phiên bản đang dùng', () => {
    renderFixture('roadmap.active_edited')
    expect(screen.getByText('Đang dùng')).toBeInTheDocument()
    expect(screen.getByText('Kịp hạn')).toBeInTheDocument()
    expect(screen.getAllByText('Chờ', { selector: '[data-chip] span' })).toHaveLength(2)
    expect(screen.getAllByText('Đã chấp nhận', { selector: '[data-chip] span' })).toHaveLength(2)
    expect(screen.getByText('Đã từ chối', { selector: '[data-chip] span' })).toBeInTheDocument()
  })

  it('hiện cả hai lựa chọn khi chưa khả thi', () => {
    renderFixture('roadmap.infeasible_two_options')
    expect(screen.getByText('Chưa khả thi')).toBeInTheDocument()
    expect(screen.getByText('Lùi hạn Du lịch tới 31/05/2027')).toBeInTheDocument()
    expect(screen.getByText('Giảm mục tiêu còn 7.500.000 ₫')).toBeInTheDocument()
  })

  it('hiện các bước thêm, bỏ, đổi, lý do sinh lại và khả năng chọn bản mới', () => {
    renderFixture('roadmap_diff.v2_v3')
    expect(screen.getByRole('heading', { name: 'So sánh lộ trình · Bản 2 → 3' })).toBeInTheDocument()
    for (const label of ['Thêm', 'Bỏ', 'Đổi', '100.000 ₫ → 150.000 ₫', 'Có thể chọn dùng bản mới.']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    expect(screen.getByText(/Chi Ăn uống mỗi tuần tăng.*giữ mức đó 2 tuần/)).toBeInTheDocument()
  })
})

describe('xem lại giao dịch', () => {
  it('hiện giao dịch cần xem lại, hũ hiện tại, số tiền và lý do gợi ý', () => {
    renderFixture('review_list.review')
    expect(screen.getByRole('heading', { name: 'Xem lại giao dịch' })).toBeInTheDocument()
    expect(screen.getByText('2 giao dịch · 125.000 ₫')).toBeInTheDocument()
    expect(screen.getByText('Highlands Coffee')).toBeInTheDocument()
    expect(screen.getByText('65.000 ₫')).toBeInTheDocument()
    expect(screen.getAllByText('Tin cậy vừa')).toHaveLength(2)
    expect(screen.getByText('Hũ hiện tại · Ăn uống')).toBeInTheDocument()
    expect(screen.getByText('Giống 2 giao dịch trước ở Giải trí')).toBeInTheDocument()
  })

  it('hiện câu hỏi gộp, mức tin cậy thấp và hai gợi ý', () => {
    renderFixture('review_list.daily_ask')
    expect(screen.getByRole('heading', { name: 'Chọn hũ cho giao dịch hôm nay' })).toBeInTheDocument()
    expect(screen.getByText('2 giao dịch · 180.000 ₫')).toBeInTheDocument()
    expect(screen.getAllByText('Tin cậy thấp')).toHaveLength(2)
    const suggestions = within(screen.getByRole('list', { name: 'Hũ gợi ý' }))
    expect(suggestions.getAllByRole('listitem')).toHaveLength(2)
    expect(suggestions.getByText('Giờ ăn trưa, số tiền như một bữa ăn')).toBeInTheDocument()
    expect(suggestions.getByText('Giống 1 giao dịch trước gửi cho cùng người')).toBeInTheDocument()
  })

  it('hiện trạng thái rỗng và tổng từ khối', () => {
    renderFixture('review_list.empty')
    expect(screen.getByText('Không có giao dịch nào cần xem lại.')).toHaveAttribute('data-state', 'empty')
    expect(screen.getByText('0 giao dịch · 0 ₫')).toBeInTheDocument()
    expect(screen.queryByRole('list')).toBeNull()
  })
})
