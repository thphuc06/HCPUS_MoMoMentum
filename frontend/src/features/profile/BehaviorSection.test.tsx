import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'
import { ApiProvider } from '@/api/ApiProvider'
import { BehaviorProfileResponse } from '@/api/phase5Schemas'
import { restFixture } from '@/test/fixtures'
import { fakeApi } from '@/test/helpers'
import { BehaviorSection } from './BehaviorSection'

it('hiện ngày mô phỏng, giờ cập nhật và mục giải thích lịch tính lại khi hồ sơ sẵn sàng', async () => {
  const user = userEvent.setup()
  const profile = BehaviorProfileResponse.parse({
    ...restFixture('BehaviorProfileResponse.minh'),
    app_date: '2026-11-22',
    computed_at: '2026-12-02T19:03:00Z',
  })
  render(<ApiProvider client={fakeApi({ getBehaviorProfile: async () => profile })}><BehaviorSection /></ApiProvider>)

  const meta = await screen.findByText(/Từ \d+ ngày dữ liệu · cập nhật/)
  expect(meta).toHaveTextContent('22/11/2026 · 02:03')
  expect(meta).not.toHaveTextContent('03/12')
  const disclosure = screen.getByRole('button', { name: 'Khi nào cập nhật?' })
  expect(disclosure).toHaveAttribute('aria-expanded', 'false')
  await user.click(disclosure)
  expect(disclosure).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByText(/tính lại dự báo, điểm chống chịu và nhận xét mỗi đêm/i)).toBeVisible()
  expect(screen.getByText(/đặt lại dữ liệu cũng tính lại ngay.*ngày mô phỏng/i)).toBeVisible()
})

it('không hiện dòng cập nhật khi hồ sơ chưa sẵn sàng', async () => {
  const profile = BehaviorProfileResponse.parse(restFixture('BehaviorProfileResponse.chua_san_sang'))
  render(<ApiProvider client={fakeApi({ getBehaviorProfile: async () => profile })}><BehaviorSection /></ApiProvider>)

  expect(await screen.findByText(profile.headline)).toBeInTheDocument()
  expect(screen.queryByText(/Từ \d+ ngày dữ liệu|cập nhật/)).not.toBeInTheDocument()
})
