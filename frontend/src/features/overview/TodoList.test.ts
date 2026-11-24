import { describe, expect, it } from 'vitest'
import { OverviewResponse } from '@/api/schemas'
import { RoadmapVersionsResponse } from '@/api/roadmapSchemas'
import { ReviewListResponse } from '@/api/reviewSchemas'
import { repeatsInsight } from '@/features/profile/BehaviorSection'
import { restFixture } from '@/test/fixtures'
import { creditTodo, reviewTodo, roadmapTodo, salaryTodo } from './TodoList'

// Dòng "Việc cần làm" ở Tổng quan (ui-design-review.md §10): chỉ có khi người dùng cần làm gì, không lặp loại đã là thẻ chính.

const ov = OverviewResponse.parse(restFixture('OverviewResponse.minh'))
const daily = ReviewListResponse.parse(restFixture('ReviewListResponse.daily_ask')).data
const versions = RoadmapVersionsResponse.parse(restFixture('RoadmapVersionsResponse.minh'))

describe('reviewTodo: hai hàng chờ (chưa xếp hũ, cần xem lại), một dòng', () => {
  it('needs_review_count là tổng hai hàng chờ: phần còn lại sau daily_ask là "cần xem lại"', () => {
    expect(reviewTodo(3, daily, false, null)).toMatchObject({ title: 'Xếp hũ cho 3 giao dịch', subtitle: expect.stringMatching(/^2 chưa xếp hũ · 180\.000\s₫; 1 cần xem lại$/), to: '/review' })
    expect(reviewTodo(2, daily, false, null)).toMatchObject({ title: '2 giao dịch chưa xếp hũ' })
    expect(reviewTodo(2, { ...daily, count: 0, pending_total_vnd: 0, items: [] }, false, null)).toMatchObject({ title: 'Xem lại 2 giao dịch' })
  })

  it('câu hỏi gộp đang hiện trên Tổng quan: chỉ còn phần cần xem lại; không có thì không có dòng', () => {
    expect(reviewTodo(3, daily, true, null)).toMatchObject({ title: 'Xem lại 1 giao dịch' })
    expect(reviewTodo(2, daily, true, null)).toBeNull()
  })

  it('không đọc được daily_ask: dùng số tổng; 0 thì không có dòng; thẻ chính là review_needed thì không lặp', () => {
    expect(reviewTodo(4, undefined, false, null)).toMatchObject({ title: '4 giao dịch cần xem lại hũ' })
    expect(reviewTodo(0, undefined, false, null)).toBeNull()
    expect(reviewTodo(3, daily, false, 'review_needed')).toBeNull()
  })
})

describe('creditTodo, roadmapTodo, salaryTodo', () => {
  const short = { ...ov, jars: ov.jars.map((j) => (j.code === 'nghia_vu' ? { ...j, balance_vnd: 200000 } : j)) }

  it('Trả sau: chỉ khi hũ trả có ít hơn số phải trả', () => {
    expect(creditTodo(ov, null)).toBeNull()
    expect(creditTodo(short, null)).toMatchObject({ to: '/obligations', title: 'Hũ Nghĩa vụ chưa đủ trả Trả sau (mô phỏng)' })
    expect(creditTodo(short, 'obligation_due')).toBeNull()
  })

  it('lộ trình: bản mới chờ chọn, rồi bước chờ; thẻ chính là lộ trình thì không lặp', () => {
    expect(roadmapTodo(versions, null)).toMatchObject({ title: 'Lộ trình mới chờ bạn chọn', subtitle: 'Phiên bản 3', to: '/roadmap' })
    expect(roadmapTodo(versions, 'roadmap_proposed')).toBeNull()
    expect(roadmapTodo({ versions: [] }, null)).toBeNull()
    expect(roadmapTodo(undefined, null)).toBeNull()
  })

  it('lương: chỉ khi chờ xác nhận và thẻ chính không phải thẻ lương', () => {
    expect(salaryTodo(ov, null)).toBeNull()
    const pending = { ...ov, next_payday: { ...ov.next_payday!, state: 'pending_confirmation' as const } }
    expect(salaryTodo(pending, null)).toMatchObject({ to: '/salary' })
    expect(salaryTodo(pending, 'salary_pending')).toBeNull()
  })
})

describe('repeatsInsight (Hồ sơ)', () => {
  it('trùng sau khi bỏ dấu câu, hoa thường; chứa trọn cũng tính là trùng', () => {
    const insights = [{ headline: '60 ngày qua bạn dùng Trả sau 5 lần, chiếm 12% chi tiêu.' }]
    expect(repeatsInsight('60 ngày qua bạn dùng Trả sau 5 lần, chiếm 12% chi tiêu', insights)).toBe(true)
    expect(repeatsInsight('Bạn dùng Trả sau 5 lần', [{ headline: 'Bạn dùng Trả sau 5 lần.' }])).toBe(true)
    expect(repeatsInsight('Bạn hay chi dồn trong tuần đầu sau ngày lương.', insights)).toBe(false)
    expect(repeatsInsight('', insights)).toBe(false)
  })
})
