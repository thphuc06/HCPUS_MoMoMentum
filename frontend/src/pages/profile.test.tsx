import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ERROR_MESSAGES } from '@/api/errors'
import { BehaviorProfileResponse, MemoryListResponse } from '@/api/phase5Schemas'
import { MEMORY_KIND_LABEL } from '@/features/profile/MemorySection'
import {
  MEMORY_DELETE_GRACE_MS,
  hideMemoryCreatedBefore,
  hideMemoryRecords,
  isMemoryRecordHidden,
  resetHiddenMemory,
  unhideMemoryRecords,
} from '@/features/profile/hiddenMemory'
import { restFixture } from '@/test/fixtures'
import { backend, bodyOf, callsTo, config, json, mountApp, type Reply } from '@/test/mountApp'

// Màn Hồ sơ phase 5 (thay khung S1): nhận xét hành vi, bộ nhớ của tôi, đồng ý theo nguồn nạp, xóa dữ liệu của tôi, lối vào bảng vận hành.

beforeEach(() => {
  localStorage.clear()
  resetHiddenMemory() // trạng thái ẩn sống ở mức module: không để ca trước làm lệch ca sau
})
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

  it('câu tổng trùng đúng câu của một nhận xét (vd. câu Trả sau): chỉ hiện một lần, ở thẻ nhận xét', async () => {
    const dup = structuredClone(restFixture('BehaviorProfileResponse.minh')) as Record<string, any>
    dup.headline = `${dup.insights[2].headline}`
    mountApp(backend({ 'GET /profile/behavior': dup }), '/profile')
    const section = await screen.findByRole('region', { name: 'Nhận xét hành vi' })
    expect(await within(section).findByText(dup.segment.label)).toBeInTheDocument()
    expect(within(section).getAllByText(dup.insights[2].headline)).toHaveLength(1)
    expect(within(section).queryByTestId('behavior-headline')).toBeNull()
  })

  it('B3: nhận xét có cặp phần chi và phần số ngày thì thẻ ở Hồ sơ cũng có hai thanh (cùng component với chat)', async () => {
    const withPair = structuredClone(restFixture('BehaviorProfileResponse.minh')) as Record<string, any>
    withPair.insights[0].evidence.push({ key: 'first_week_day_share', label: 'Phần số ngày thuộc tuần đầu sau lương', value: 23, unit: 'percent' })
    mountApp(backend({ 'GET /profile/behavior': withPair }), '/profile')
    const section = await screen.findByRole('region', { name: 'Nhận xét hành vi' })
    const bars = await within(section).findByTestId('evidence-bars')
    expect(within(bars).getByRole('img')).toHaveAccessibleName(/46%.*23%.*Nhiều hơn mức chi đều 23 điểm phần trăm/)
    expect(within(section).getAllByTestId('evidence-bars')).toHaveLength(1)
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

describe('Hồ sơ: xóa bộ nhớ là optimistic, không hiện lại bản ghi đã xóa trong lúc dịch vụ còn trễ', () => {
  // Đo Runtime v25: ngay sau khi xóa, `GET /memory` còn liệt kê bản ghi cũ khoảng một phút. Backend giả ở đây cũng vậy: GET luôn trả đủ.
  afterEach(() => vi.restoreAllMocks())

  function deferred() {
    let release!: (r: Reply) => void
    const promise = new Promise<Reply>((res) => (release = res))
    return { promise, release }
  }

  async function revisitProfile(router: { navigate: (to: string) => Promise<void> }) {
    await act(() => router.navigate('/'))
    await act(() => router.navigate('/profile'))
    return within(await screen.findByRole('region', { name: 'Bộ nhớ của tôi' })).findByRole('list', { name: 'Các mục nhớ' })
  }

  it('xóa một mục: ẩn ngay khi bấm (trước khi API trả); quay lại Hồ sơ mà GET còn trả thì vẫn ẩn; quá MEMORY_DELETE_GRACE_MS thì hiện', async () => {
    const user = userEvent.setup()
    const gate = deferred()
    const { router, calls } = mountApp(backend({ 'DELETE /memory/*': () => gate.promise }), '/profile')
    const list = await screen.findByRole('list', { name: 'Các mục nhớ' })
    const first = memory.records[0]!
    await user.click(within(list).getByRole('button', { name: `Xóa mục nhớ: ${first.text}` }))
    expect(within(list).queryByText(first.text)).toBeNull()
    expect(within(list).getAllByRole('listitem')).toHaveLength(memory.records.length - 1)
    gate.release({ record_id: first.record_id, deleted: true })
    await waitFor(() => expect(callsTo(calls, 'DELETE', `/memory/${first.record_id}`)).toHaveLength(1))

    const again = await revisitProfile(router)
    expect(within(again).getAllByRole('listitem')).toHaveLength(memory.records.length - 1)
    expect(within(again).queryByText(first.text)).toBeNull()

    const now = Date.now()
    vi.spyOn(Date, 'now').mockReturnValue(now + MEMORY_DELETE_GRACE_MS + 1000)
    const later = await revisitProfile(router)
    expect(within(later).getByText(first.text)).toBeInTheDocument()
  })

  it('xóa một mục mà API báo lỗi: mục hiện lại và báo lỗi', async () => {
    const user = userEvent.setup()
    const gate = deferred()
    mountApp(backend({ 'DELETE /memory/*': () => gate.promise }), '/profile')
    const list = await screen.findByRole('list', { name: 'Các mục nhớ' })
    const first = memory.records[0]!
    await user.click(within(list).getByRole('button', { name: `Xóa mục nhớ: ${first.text}` }))
    expect(within(list).queryByText(first.text)).toBeNull()
    gate.release(json(503, { error: { code: 'MEMORY_UNAVAILABLE' } }))
    expect(await within(list).findByText(first.text)).toBeInTheDocument()
    const section = screen.getByRole('region', { name: 'Bộ nhớ của tôi' })
    expect(within(section).getByRole('alert')).toHaveTextContent(ERROR_MESSAGES.MEMORY_UNAVAILABLE)
    expect(within(list).getAllByRole('listitem')).toHaveLength(memory.records.length)
  })

  it('xóa hết: ẩn ngay khi xác nhận; GET sau đó còn trả bản ghi cũ thì vẫn trống', async () => {
    const user = userEvent.setup()
    const gate = deferred()
    const { router } = mountApp(backend({ 'DELETE /memory': () => gate.promise }), '/profile')
    const section = await screen.findByRole('region', { name: 'Bộ nhớ của tôi' })
    await within(section).findByRole('list', { name: 'Các mục nhớ' })
    await user.click(within(section).getByRole('button', { name: 'Xóa hết' }))
    await user.click(await screen.findByRole('button', { name: 'Xóa hết bộ nhớ' }))
    expect(within(section).queryByRole('list', { name: 'Các mục nhớ' })).toBeNull()
    expect(within(section).getByText('Đang xóa bộ nhớ…')).toBeInTheDocument()
    gate.release(restFixture('MemoryClearResponse.default'))
    expect(await within(section).findByText(/Đã xóa 6 mục nhớ/)).toBeInTheDocument()
    expect(within(section).getByTestId('memory-empty')).toBeInTheDocument()
    await act(() => router.navigate('/'))
    await act(() => router.navigate('/profile'))
    const back = await screen.findByRole('region', { name: 'Bộ nhớ của tôi' })
    expect(await within(back).findByTestId('memory-empty')).toBeInTheDocument()
  })

  it('xóa hết mà API báo lỗi: danh sách hiện lại và báo lỗi', async () => {
    const user = userEvent.setup()
    const gate = deferred()
    mountApp(backend({ 'DELETE /memory': () => gate.promise }), '/profile')
    const section = await screen.findByRole('region', { name: 'Bộ nhớ của tôi' })
    await within(section).findByRole('list', { name: 'Các mục nhớ' })
    await user.click(within(section).getByRole('button', { name: 'Xóa hết' }))
    await user.click(await screen.findByRole('button', { name: 'Xóa hết bộ nhớ' }))
    expect(within(section).queryByRole('list', { name: 'Các mục nhớ' })).toBeNull()
    gate.release(json(503, { error: { code: 'MEMORY_UNAVAILABLE' } }))
    const list = await within(section).findByRole('list', { name: 'Các mục nhớ' })
    expect(within(list).getAllByRole('listitem')).toHaveLength(memory.records.length)
    expect(within(section).getByRole('alert')).toHaveTextContent(ERROR_MESSAGES.MEMORY_UNAVAILABLE)
  })
})

describe('hiddenMemory: ẩn theo id và theo mốc "xóa hết", có hạn', () => {

  it('ẩn theo id đến hết hạn; bỏ ẩn được; "xóa hết" ẩn bản ghi tạo trước mốc, không ẩn bản ghi mới hơn', () => {
    const t0 = Date.parse('2026-11-25T10:00:00Z')
    const old = { record_id: 'mem-a', created_at: '2026-11-25T09:00:00Z' }
    const fresh = { record_id: 'mem-b', created_at: '2026-11-25T10:01:00Z' }
    hideMemoryRecords(['mem-a'], t0)
    expect(isMemoryRecordHidden(old, t0 + 1000)).toBe(true)
    expect(isMemoryRecordHidden(fresh, t0 + 1000)).toBe(false)
    expect(isMemoryRecordHidden(old, t0 + MEMORY_DELETE_GRACE_MS)).toBe(false)
    hideMemoryRecords(['mem-a'], t0)
    unhideMemoryRecords(['mem-a'])
    expect(isMemoryRecordHidden(old, t0 + 1000)).toBe(false)
    hideMemoryCreatedBefore(t0, t0)
    expect(isMemoryRecordHidden(old, t0 + 1000)).toBe(true)
    expect(isMemoryRecordHidden(fresh, t0 + 61_000)).toBe(false)
    expect(isMemoryRecordHidden(old, t0 + MEMORY_DELETE_GRACE_MS + 1)).toBe(false)
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
