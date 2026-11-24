import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ERROR_MESSAGES } from '@/api/errors'
import { BehaviorProfileResponse, MemoryListResponse } from '@/api/phase5Schemas'
import { MEMORY_KIND_LABEL } from '@/features/profile/MemorySection'
import { restFixture } from '@/test/fixtures'
import { backend, bodyOf, callsTo, config, json, mountApp } from '@/test/mountApp'

// Màn Hồ sơ phase 5 (thay khung S1): nhận xét hành vi, bộ nhớ của tôi, đồng ý theo nguồn nạp, xóa dữ liệu của tôi, lối vào bảng vận hành.

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

const behavior = BehaviorProfileResponse.parse(restFixture('BehaviorProfileResponse.minh'))
const memory = MemoryListResponse.parse(restFixture('MemoryListResponse.minh'))

describe('Hồ sơ: nhận xét hành vi', () => {
  it('hiện câu tóm tắt, nhóm hành vi, mỗi nhận xét kèm bằng chứng và MỘT việc nên làm', async () => {
    mountApp(backend(), '/profile')
    const section = await screen.findByRole('region', { name: 'Nhận xét hành vi' })
    expect(await within(section).findByText(behavior.headline)).toBeInTheDocument()
    expect(within(section).getByText(behavior.segment!.label)).toBeInTheDocument()
    const list = within(section).getByRole('list', { name: 'Các nhận xét' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(behavior.insights.length)
    for (const i of behavior.insights) expect(within(list).getByText(i.headline)).toBeInTheDocument()
    expect(within(section).getAllByTestId('behavior-next-step')).toHaveLength(1)
    expect(within(section).getByText(behavior.next_step!.label)).toBeInTheDocument()
  })

  it('"Thực hiện" việc nên làm: xem trước do server tính, chỉ ghi khi bấm xác nhận (token)', async () => {
    const user = userEvent.setup()
    const { calls } = mountApp(backend(), '/profile')
    const section = await screen.findByRole('region', { name: 'Nhận xét hành vi' })
    await user.click(await within(section).findByRole('button', { name: 'Thực hiện' }))
    expect(await screen.findByText('Xem trước thao tác')).toBeInTheDocument()
    const action = behavior.next_step!.action!
    expect(callsTo(calls, 'POST', '/confirmations').map(bodyOf)).toEqual([{ tool: action.tool, params: action.params }])
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Xác nhận thực hiện' }))
    expect(await screen.findByRole('heading', { name: 'Kết quả thực hiện' })).toBeInTheDocument()
    expect(callsTo(calls, 'POST', '/actions').map(bodyOf)).toEqual([{ tool: action.tool, params: action.params, confirm_token: 'aaa.bbb' }])
  })

  it('chưa đủ lịch sử: nói cần thêm bao nhiêu ngày, không phải lỗi', async () => {
    mountApp(backend({ 'GET /profile/behavior': restFixture('BehaviorProfileResponse.chua_san_sang') }), '/profile')
    const box = await screen.findByTestId('behavior-not-ready')
    expect(box).toHaveTextContent('Cần thêm 9 ngày giao dịch')
    expect(box).toHaveTextContent('Đã có 12 ngày dữ liệu, cần ít nhất 21 ngày')
    expect(within(screen.getByRole('region', { name: 'Nhận xét hành vi' })).queryByRole('alert')).toBeNull()
  })
})

describe('Hồ sơ: bộ nhớ của tôi', () => {
  it('liệt kê bản ghi theo loại; xóa từng mục gọi DELETE /memory/{id} và bỏ mục đó', async () => {
    const user = userEvent.setup()
    const { calls } = mountApp(backend({ 'DELETE /memory/*': (_init, url) => ({ record_id: url.pathname.split('/').pop(), deleted: true }) }), '/profile')
    const list = await screen.findByRole('list', { name: 'Các mục nhớ' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(memory.records.length)
    expect(within(list).getAllByText(MEMORY_KIND_LABEL.preference)).toHaveLength(2)
    expect(within(list).getByText(MEMORY_KIND_LABEL.lesson)).toBeInTheDocument()
    const first = memory.records[0]!
    await user.click(within(list).getByRole('button', { name: `Xóa mục nhớ: ${first.text}` }))
    await waitFor(() => expect(within(list).queryByText(first.text)).toBeNull())
    expect(callsTo(calls, 'DELETE', `/memory/${first.record_id}`)).toHaveLength(1)
    expect(within(list).getAllByRole('listitem')).toHaveLength(memory.records.length - 1)
    // Thao tác bộ nhớ không đi qua token
    expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(0)
  })

  it('"Xóa hết": hỏi lại; Hủy không gọi gì; xác nhận thì DELETE /memory, báo số đã xóa, danh sách trống', async () => {
    const user = userEvent.setup()
    let cleared = false
    const { calls } = mountApp(backend({
      'GET /memory': () => (cleared ? { records: [] } : memory),
      'DELETE /memory': () => {
        cleared = true
        return restFixture('MemoryClearResponse.default')
      },
    }), '/profile')
    const section = await screen.findByRole('region', { name: 'Bộ nhớ của tôi' })
    await within(section).findByRole('list', { name: 'Các mục nhớ' })
    await user.click(within(section).getByRole('button', { name: 'Xóa hết' }))
    await user.click(await screen.findByRole('button', { name: 'Hủy' }))
    expect(callsTo(calls, 'DELETE', '/memory')).toHaveLength(0)
    await user.click(within(section).getByRole('button', { name: 'Xóa hết' }))
    await user.click(await screen.findByRole('button', { name: 'Xóa hết bộ nhớ' }))
    expect(await within(section).findByText(/Đã xóa 6 mục nhớ/)).toBeInTheDocument()
    expect(await within(section).findByTestId('memory-empty')).toBeInTheDocument()
    expect(callsTo(calls, 'DELETE', '/memory')).toHaveLength(1)
  })

  it('xóa hết còn sót: nói còn bao nhiêu mục và mời bấm lại', async () => {
    const user = userEvent.setup()
    mountApp(backend({ 'DELETE /memory': { deleted_records: 4, deleted_events: 10, failed: 2 } }), '/profile')
    const section = await screen.findByRole('region', { name: 'Bộ nhớ của tôi' })
    await within(section).findByRole('list', { name: 'Các mục nhớ' })
    await user.click(within(section).getByRole('button', { name: 'Xóa hết' }))
    await user.click(await screen.findByRole('button', { name: 'Xóa hết bộ nhớ' }))
    expect(await within(section).findByText(/còn 2 mục chưa xóa được/)).toBeInTheDocument()
  })

  it('Memory không trả lời: thông báo tiếng Việt và thử lại được; phần khác của Hồ sơ vẫn hiện', async () => {
    const user = userEvent.setup()
    let n = 0
    mountApp(backend({ 'GET /memory': () => (n++ === 0 ? json(503, { error: { code: 'MEMORY_UNAVAILABLE' } }) : memory) }), '/profile')
    const section = await screen.findByRole('region', { name: 'Bộ nhớ của tôi' })
    const alert = await within(section).findByRole('alert')
    expect(alert).toHaveTextContent(ERROR_MESSAGES.MEMORY_UNAVAILABLE)
    expect(screen.getByTestId('profile-declared')).toBeInTheDocument()
    await user.click(within(alert).getByRole('button', { name: 'Thử lại' }))
    expect(await within(section).findByRole('list', { name: 'Các mục nhớ' })).toBeInTheDocument()
  })
})

describe('Hồ sơ: đồng ý theo nguồn nạp', () => {
  it('nguồn đã có lần nạp là đã đồng ý; nguồn chưa nạp nói sẽ hỏi ở lần đầu', async () => {
    mountApp(backend({ 'GET /ingest/jobs': restFixture('IngestJobListResponse.recent') }), '/profile')
    const list = await screen.findByRole('list', { name: 'Các nguồn nạp' })
    const image = list.querySelector('[data-source="image"]') as HTMLElement
    const csv = list.querySelector('[data-source="csv"]') as HTMLElement
    expect(within(image).getByText('Đã đồng ý')).toBeInTheDocument()
    expect(within(csv).getByText('Chưa nạp')).toBeInTheDocument()
    expect(csv).toHaveTextContent('Yofina sẽ hỏi bạn ở lần nạp đầu tiên')
  })
})

describe('Hồ sơ: xóa dữ liệu của tôi', () => {
  it('xem trước do server tính, phải tích ô hiểu rõ; xác nhận thì xin token mới rồi POST /me/delete-data kèm token', async () => {
    const user = userEvent.setup()
    const { calls } = mountApp(backend({
      'POST /me/delete-data/confirmations': restFixture('ConfirmationResponse.delete_my_data'),
      'POST /me/delete-data': restFixture('DataDeletion.done'),
    }), '/profile')
    const section = await screen.findByRole('region', { name: 'Xóa dữ liệu của tôi' })
    await user.click(within(section).getByRole('button', { name: 'Xóa dữ liệu của tôi' }))
    expect(await screen.findByTestId('preview-summary')).toHaveTextContent('Xóa toàn bộ dữ liệu của bạn trong Yofina')
    expect(screen.getByText('Bộ nhớ của trợ lý')).toBeInTheDocument()
    const go = screen.getByRole('button', { name: 'Xóa vĩnh viễn' })
    expect(go).toBeDisabled()
    expect(callsTo(calls, 'POST', '/me/delete-data')).toHaveLength(0)
    await user.click(screen.getByRole('checkbox', { name: 'Tôi hiểu dữ liệu sẽ bị xóa vĩnh viễn' }))
    await user.click(go)
    expect(await within(section).findByTestId('delete-result')).toHaveTextContent('Đã xóa toàn bộ dữ liệu của bạn')
    const confirms = callsTo(calls, 'POST', '/me/delete-data/confirmations')
    expect(confirms).toHaveLength(2) // bản xem trước + token mới lúc xác nhận
    expect(bodyOf(confirms[1]!)).toEqual(restFixture('DeleteDataConfirmationRequest.all'))
    expect(callsTo(calls, 'POST', '/me/delete-data').map(bodyOf)).toEqual([restFixture('DeleteDataRequest.co_token')])
    // Dữ liệu đã đổi: Tổng quan được tải lại
    await waitFor(() => expect(callsTo(calls, 'GET', '/overview').length).toBeGreaterThanOrEqual(2))
  })

  it('xóa dở (partial): báo phần chưa xóa được và đổi nút thành "Xóa tiếp"', async () => {
    const user = userEvent.setup()
    mountApp(backend({
      'POST /me/delete-data/confirmations': restFixture('ConfirmationResponse.delete_my_data'),
      'POST /me/delete-data': restFixture('DataDeletion.partial'),
    }), '/profile')
    const section = await screen.findByRole('region', { name: 'Xóa dữ liệu của tôi' })
    await user.click(within(section).getByRole('button', { name: 'Xóa dữ liệu của tôi' }))
    await screen.findByTestId('preview-summary')
    await user.click(screen.getByRole('checkbox', { name: 'Tôi hiểu dữ liệu sẽ bị xóa vĩnh viễn' }))
    await user.click(screen.getByRole('button', { name: 'Xóa vĩnh viễn' }))
    const result = await within(section).findByTestId('delete-result')
    expect(result).toHaveTextContent('còn một phần chưa xóa được')
    expect(result).toHaveTextContent('Bộ nhớ của trợ lýChưa xóa được')
    expect(within(section).getByRole('button', { name: 'Xóa tiếp' })).toBeInTheDocument()
  })

  it('token bị từ chối: hiện lỗi tiếng Việt trong hộp xác nhận, không báo đã xóa', async () => {
    const user = userEvent.setup()
    mountApp(backend({
      'POST /me/delete-data/confirmations': restFixture('ConfirmationResponse.delete_my_data'),
      'POST /me/delete-data': json(409, { error: { code: 'TOKEN_REUSED' } }),
    }), '/profile')
    const section = await screen.findByRole('region', { name: 'Xóa dữ liệu của tôi' })
    await user.click(within(section).getByRole('button', { name: 'Xóa dữ liệu của tôi' }))
    await screen.findByTestId('preview-summary')
    await user.click(screen.getByRole('checkbox', { name: 'Tôi hiểu dữ liệu sẽ bị xóa vĩnh viễn' }))
    await user.click(screen.getByRole('button', { name: 'Xóa vĩnh viễn' }))
    expect(await screen.findByText(ERROR_MESSAGES.TOKEN_REUSED)).toBeInTheDocument()
    expect(within(section).queryByTestId('delete-result')).toBeNull()
  })
})

describe('Hồ sơ: lối vào bảng vận hành', () => {
  it('tài khoản nhóm ops thấy "Bảng vận hành"; tài khoản thường không thấy', async () => {
    mountApp(backend(), '/profile', config, { session: { groups: ['ops'] } })
    const nav = await screen.findByRole('region', { name: 'Quản lý' })
    expect(within(nav).getByRole('link', { name: /Bảng vận hành/ })).toHaveAttribute('href', '/ops/summary')
  })

  it('tài khoản không thuộc ops: không có lối vào', async () => {
    mountApp(backend(), '/profile')
    const nav = await screen.findByRole('region', { name: 'Quản lý' })
    expect(within(nav).queryByRole('link', { name: /Bảng vận hành/ })).toBeNull()
    expect(screen.getByRole('button', { name: 'Đăng xuất' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Đặt lại dữ liệu' })).toBeInTheDocument()
  })
})
