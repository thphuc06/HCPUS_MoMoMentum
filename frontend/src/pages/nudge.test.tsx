import { cleanup, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { NudgeTodayResponse } from '@/api/phase5Schemas'
import { ROADMAP_PROMPT, summarizeRoadmap } from '@/features/roadmap/RoadmapEntry'
import { RoadmapVersionsResponse } from '@/api/roadmapSchemas'
import { restFixture } from '@/test/fixtures'
import { backend, bodyOf, callsTo, json, mountApp, runCalls } from '@/test/mountApp'
import { runFinished, runStarted, sseResponse } from '@/test/sse'

// Thẻ chủ động hiện bản tin của cổng giá trị (`GET /nudges/today`) và lối vào trang Lộ trình ở Tổng quan và tab Nhìn trước.

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

const withNudge = NudgeTodayResponse.parse(restFixture('NudgeTodayResponse.co_ban_tin'))
const nudgeId = withNudge.nudge!.nudge_id
const feedbackPath = `/nudges/${nudgeId}/feedback`
const feedbackReply = (init: RequestInit) => ({ nudge_id: nudgeId, outcome: JSON.parse(String(init.body)).outcome, recorded_at: '2026-12-10T03:00:00Z' })
const card = () => screen.findByRole('region', { name: 'Việc cần làm hôm nay' })

describe('Tổng quan: bản tin chủ động', () => {
  it('có bản tin thì hiện bản tin thay thẻ tất định của /overview, đủ nút gồm "Ít nhắc loại này"', async () => {
    mountApp(backend({ 'GET /nudges/today': withNudge }))
    const c = await screen.findByText('Lộ trình mới chờ bạn chọn')
    const region = c.closest('section') as HTMLElement
    expect(region).toHaveAttribute('data-kind', 'roadmap_proposed')
    for (const name of ['Xem lộ trình mới', 'Để sau', 'Ít nhắc loại này']) expect(within(region).getByRole('button', { name })).toBeInTheDocument()
    expect(screen.queryByText('Hũ Ăn uống dự kiến cạn ngày 29/11')).toBeNull()
    expect(screen.getAllByRole('region', { name: 'Việc cần làm hôm nay' })).toHaveLength(1)
  })

  it('"Ít nhắc loại này" gửi less_like_this cho server (không lưu trên máy) rồi ẩn thẻ', async () => {
    const user = userEvent.setup()
    const { calls } = mountApp(backend({ 'GET /nudges/today': withNudge, [`POST ${feedbackPath}`]: feedbackReply }))
    await screen.findByText('Lộ trình mới chờ bạn chọn')
    await user.click(screen.getByRole('button', { name: 'Ít nhắc loại này' }))
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Việc cần làm hôm nay' })).toBeNull())
    expect(callsTo(calls, 'POST', feedbackPath).map(bodyOf)).toEqual([restFixture('NudgeFeedbackRequest.less_like_this')])
    expect(localStorage.getItem('yofina.nudge.muted')).toBeNull()
    // Không có thẻ tất định nào thế chỗ: người dùng vừa gạt việc hôm nay đi
    expect(screen.queryByText('Hũ Ăn uống dự kiến cạn ngày 29/11')).toBeNull()
  })

  it('nút chính ghi acted rồi mở trang Lộ trình', async () => {
    const user = userEvent.setup()
    const { calls, router } = mountApp(backend({ 'GET /nudges/today': withNudge, [`POST ${feedbackPath}`]: feedbackReply }))
    await screen.findByText('Lộ trình mới chờ bạn chọn')
    await user.click(screen.getByRole('button', { name: 'Xem lộ trình mới' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/roadmap'))
    await waitFor(() => expect(callsTo(calls, 'POST', feedbackPath).map((c) => bodyOf(c).outcome)).toEqual(['acted']))
  })

  it('"Để sau" gửi snoozed rồi ẩn thẻ', async () => {
    const user = userEvent.setup()
    const { calls } = mountApp(backend({ 'GET /nudges/today': withNudge, [`POST ${feedbackPath}`]: feedbackReply }))
    await screen.findByText('Lộ trình mới chờ bạn chọn')
    await user.click(screen.getByRole('button', { name: 'Để sau' }))
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Việc cần làm hôm nay' })).toBeNull())
    expect(callsTo(calls, 'POST', feedbackPath).map((c) => bodyOf(c).outcome)).toEqual(['snoozed'])
  })

  it('bản tin đã được gạt đi hôm nay (outcome snoozed): không hiện thẻ nào', async () => {
    const snoozed = structuredClone(withNudge)
    snoozed.nudge!.outcome = 'snoozed'
    mountApp(backend({ 'GET /nudges/today': snoozed }))
    await screen.findByTestId('balance-total')
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Việc cần làm hôm nay' })).toBeNull())
  })

  it('ghi phản hồi lỗi: báo lỗi, thẻ vẫn còn', async () => {
    const user = userEvent.setup()
    mountApp(backend({ 'GET /nudges/today': withNudge, [`POST ${feedbackPath}`]: json(503, { error: { code: 'DATABASE_UNAVAILABLE' } }) }))
    await screen.findByText('Lộ trình mới chờ bạn chọn')
    await user.click(screen.getByRole('button', { name: 'Để sau' }))
    expect(await screen.findByText(/Chưa ghi được lựa chọn của bạn/)).toBeInTheDocument()
    expect(await card()).toBeInTheDocument()
  })

  it('không có bản tin (hoặc lỗi đọc bản tin): dùng thẻ tất định của /overview như trước', async () => {
    mountApp(backend({ 'GET /nudges/today': json(503, { error: { code: 'DATABASE_UNAVAILABLE' } }) }))
    expect(await screen.findByText('Hũ Ăn uống dự kiến cạn ngày 29/11')).toBeInTheDocument()
  })
})

describe('lối vào Lộ trình', () => {
  const versions = RoadmapVersionsResponse.parse(restFixture('RoadmapVersionsResponse.minh'))

  it('tóm tắt từ danh sách phiên bản: bản đang dùng, mức khả thi, số bước chờ, có bản đề xuất', () => {
    expect(summarizeRoadmap(versions)).toEqual({ version: 2, active: true, feasibility: 'on_track', pending: 2, hasProposed: true, regenerating: false })
    expect(summarizeRoadmap({ versions: [] })).toBeNull()
    const onlyProposed = { versions: versions.versions.filter((v) => v.status === 'proposed'), proposed_version: 3 }
    expect(summarizeRoadmap(onlyProposed)).toMatchObject({ version: 3, active: false, feasibility: 'relaxed' })
  })

  it('tab Nhìn trước: thẻ sau Điểm chống chịu, trước "Thử cú sốc tài chính"; bấm mở /roadmap', async () => {
    const user = userEvent.setup()
    const { router } = mountApp(backend(), '/foresight')
    const entry = await screen.findByTestId('roadmap-entry')
    expect(entry).toHaveTextContent('Đang dùng phiên bản 2')
    expect(entry).toHaveTextContent('Kịp hạn')
    expect(entry).toHaveTextContent('2 bước chờ')
    expect(entry).toHaveTextContent('Có phiên bản mới')
    expect(entry).toHaveAttribute('href', '/roadmap')
    const gauge = await screen.findByRole('img', { name: /Điểm chống chịu/ })
    const shocks = await screen.findByRole('list', { name: 'Thử cú sốc tài chính' })
    expect(gauge.compareDocumentPosition(entry) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(entry.compareDocumentPosition(shocks) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    await user.click(entry)
    await waitFor(() => expect(router.state.location.pathname).toBe('/roadmap'))
  })

  it('bản đề xuất chưa khả thi và chưa có bản đang dùng: nói bản đó đang chờ chọn', async () => {
    const proposedOnly = { versions: [{ ...versions.versions[0]!, feasibility: 'infeasible' }], proposed_version: 3 }
    mountApp(backend({ 'GET /roadmap/versions': proposedOnly }), '/foresight')
    const entry = await screen.findByTestId('roadmap-entry')
    expect(entry).toHaveTextContent('Phiên bản 3 chờ bạn chọn')
    expect(entry).toHaveTextContent('Chưa khả thi')
    expect(entry).toHaveTextContent('5 bước chờ')
  })

  it('chưa có lộ trình: thẻ mời "Lập lộ trình" mở chat với câu gợi ý', async () => {
    const user = userEvent.setup()
    const { calls } = mountApp(backend({
      'GET /roadmap/versions': restFixture('RoadmapVersionsResponse.chua_co'),
      'POST /invocations': async () => sseResponse([runStarted(), runFinished()]),
    }), '/foresight')
    const empty = await screen.findByTestId('roadmap-entry-empty')
    await user.click(within(empty).getByRole('button', { name: 'Lập lộ trình' }))
    expect(await screen.findByTestId('chat-sheet', {}, { timeout: 10_000 })).toBeInTheDocument()
    await waitFor(() => expect(runCalls(calls)).toHaveLength(1))
    const msgs = bodyOf(runCalls(calls)[0]!).messages as Array<{ role: string; content: string }>
    expect(msgs.at(-1)).toMatchObject({ role: 'user', content: ROADMAP_PROMPT })
  })

  // Tổng quan không còn thẻ/dòng lộ trình cố định (nhà là Nhìn trước, ui-design-review.md §10): chỉ một dòng "Việc cần làm" khi có việc.
  const todoRoadmap = () => document.querySelector('[data-todo="roadmap"]')

  it('Tổng quan: có phiên bản mới chờ chọn thì một dòng Việc cần làm dẫn tới /roadmap', async () => {
    mountApp(backend())
    await waitFor(() => expect(todoRoadmap()).not.toBeNull())
    const row = within(todoRoadmap() as HTMLElement).getByRole('link')
    expect(row).toHaveTextContent('Lộ trình mới chờ bạn chọn Phiên bản 3')
    expect(row).toHaveAttribute('href', '/roadmap')
    expect(screen.queryByText('Lộ trình thích ứng')).toBeNull()
  })

  it('Tổng quan: chỉ còn bước chờ ở bản đang dùng thì dòng nói số bước; không có việc hay chưa có lộ trình thì không có dòng', async () => {
    const activeOnly = { versions: versions.versions.filter((v) => v.status !== 'proposed'), active_version: 2 }
    mountApp(backend({ 'GET /roadmap/versions': activeOnly }))
    await waitFor(() => expect(todoRoadmap()).not.toBeNull())
    expect(todoRoadmap()).toHaveTextContent('Lộ trình: 2 bước chờ bạn Phiên bản 2')
    cleanup()
    const done = { versions: activeOnly.versions.map((v) => ({ ...v, counts: { ...v.counts, pending: 0 } })), active_version: 2 }
    const { calls } = mountApp(backend({ 'GET /roadmap/versions': done }))
    await waitFor(() => expect(callsTo(calls, 'GET', '/roadmap/versions')).toHaveLength(1))
    await screen.findByTestId('balance-total')
    expect(todoRoadmap()).toBeNull()
    cleanup()
    const none = mountApp(backend({ 'GET /roadmap/versions': restFixture('RoadmapVersionsResponse.chua_co') }))
    await waitFor(() => expect(callsTo(none.calls, 'GET', '/roadmap/versions')).toHaveLength(1))
    expect(todoRoadmap()).toBeNull()
    expect(screen.queryByRole('button', { name: 'Lập lộ trình' })).toBeNull()
  })

  it('Tổng quan: thẻ chính hôm nay đã là "Lộ trình mới chờ bạn chọn" thì không lặp thành dòng', async () => {
    mountApp(backend({ 'GET /nudges/today': withNudge }))
    await waitFor(() => expect(screen.getByRole('region', { name: 'Việc cần làm hôm nay' })).toHaveTextContent('Lộ trình mới chờ bạn chọn'))
    await waitFor(() => expect(screen.getByTestId('todo-list')).toBeInTheDocument())
    expect(todoRoadmap()).toBeNull()
  })

  it('Tổng quan: lỗi đọc lộ trình thì không hiện dòng (không làm ồn Tổng quan)', async () => {
    mountApp(backend({ 'GET /roadmap/versions': json(500, { error: { code: 'INTERNAL_ERROR' } }) }))
    await screen.findByTestId('balance-total')
    await waitFor(() => expect(screen.getByTestId('todo-list')).toBeInTheDocument())
    expect(todoRoadmap()).toBeNull()
  })
})
