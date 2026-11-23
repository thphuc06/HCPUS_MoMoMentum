import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ERROR_MESSAGES } from '@/api/errors'
import { RoadmapJob, RoadmapResponse, RoadmapVersionsResponse } from '@/api/roadmapSchemas'
import { BlockRenderer } from '@/blocks/registry'
import { formatDayMonth } from '@/lib/dates'
import { formatVnd } from '@/lib/format'
import { ROADMAP_JOB_POLL } from '@/lib/config'
import { restFixture, validBlock } from '@/test/fixtures'
import { backend, bodyOf, callsTo, json, mountApp } from '@/test/mountApp'

const v3 = RoadmapResponse.parse(restFixture('RoadmapResponse.minh_v3'))
const v2 = RoadmapResponse.parse(validBlock('roadmap.active_edited'))
const versions = RoadmapVersionsResponse.parse(restFixture('RoadmapVersionsResponse.minh'))
const infeasible = RoadmapResponse.parse(restFixture('RoadmapResponse.infeasible'))
const queued = RoadmapJob.parse(restFixture('RoadmapJob.queued'))
const running = RoadmapJob.parse(restFixture('RoadmapJob.running'))
const done = RoadmapJob.parse(restFixture('RoadmapJob.done'))
const failed = RoadmapJob.parse(restFixture('RoadmapJob.failed'))
const executable = v3.data.phases.flatMap((phase) => phase.steps).find((step) => step.action)!

function withDecision(stepId: string, status: 'accepted' | 'rejected') {
  const block = structuredClone(v3)
  const step = block.data.phases.flatMap((phase) => phase.steps).find((step) => step.step_id === stepId)!
  step.status = status
  step.decided_at = block.source.as_of
  block.data.counts.pending--
  block.data.counts[status]++
  return block
}

async function stepCard(title: string) {
  return within((await screen.findByText(title)).closest('li')!)
}

async function pollOnce() {
  await act(async () => vi.advanceTimersByTimeAsync(ROADMAP_JOB_POLL.delayMs))
}

describe('lộ trình thích ứng', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('hiện phiên bản, lý do, thay đổi trước sau và counts từ server', async () => {
    const { calls } = mountApp(backend({ 'GET /roadmap': v3, 'GET /roadmap/versions': versions }), '/roadmap')
    expect(await screen.findByRole('heading', { name: 'Lộ trình · Phiên bản 3' })).toBeVisible()
    expect(screen.getByText(v3.data.headline)).toBeVisible()
    expect(screen.getByText(v3.data.reason.text)).toBeVisible()
    expect(screen.getByText(v3.data.reason.detail![0]!.label)).toBeVisible()
    expect(screen.getByText('Khả thi sau điều chỉnh')).toBeVisible()
    const counts = within(screen.getByRole('list', { name: 'Số bước theo trạng thái' })).getAllByRole('listitem')
    expect(counts.map((item) => item.textContent)).toEqual([
      `Chờ ${v3.data.counts.pending}`,
      `Đã chấp nhận ${v3.data.counts.accepted}`,
      `Đã từ chối ${v3.data.counts.rejected}`,
    ])
    expect(await screen.findByRole('link', { name: 'Có phiên bản mới' })).toHaveAttribute('href', '/roadmap/compare')
    expect(new URL(callsTo(calls, 'GET', '/roadmap')[0]!.url).search).toBe('')
    const step = await stepCard(executable.title)
    await userEvent.click(step.getByText('Vì sao'))
    expect(step.getByText(executable.reason)).toBeVisible()
  })

  it('giữ khối lộ trình trong chat ở chế độ chỉ xem', () => {
    const block = withDecision(executable.step_id, 'accepted')
    render(<BlockRenderer raw={block} blockId={block.id} />)
    expect(screen.getByRole('heading', { name: 'Lộ trình · Phiên bản 3' })).toBeVisible()
    expect(screen.queryByRole('button', { name: /Chấp nhận|Từ chối|Sửa|Thực hiện/ })).toBeNull()
  })

  it('chấp nhận bước và chỉ ghi tiền sau khi người dùng xác nhận xem trước', async () => {
    const user = userEvent.setup()
    const path = `/roadmap/steps/${executable.step_id}/decision`
    const { calls } = mountApp(backend({
      'GET /roadmap': v3, 'GET /roadmap/versions': versions,
      [`POST ${path}`]: withDecision(executable.step_id, 'accepted'),
    }), '/roadmap')
    const card = await stepCard(executable.title)
    expect(card.queryByRole('button', { name: 'Thực hiện' })).toBeNull()
    await user.click(card.getByRole('button', { name: 'Chấp nhận' }))
    expect(await card.findByText('Đã chấp nhận')).toBeVisible()
    expect(callsTo(calls, 'POST', path).map(bodyOf)).toEqual([restFixture('RoadmapStepDecisionRequest.accept')])
    expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(0)
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(0)

    await user.click(card.getByRole('button', { name: 'Thực hiện' }))
    expect(await screen.findByText('Xem trước thao tác')).toBeVisible()
    expect(callsTo(calls, 'POST', '/confirmations').map(bodyOf)).toEqual([executable.action])
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Xác nhận thực hiện' }))
    expect(await screen.findByRole('heading', { name: 'Kết quả thực hiện' })).toBeVisible()
    expect(callsTo(calls, 'POST', '/actions').map(bodyOf)).toEqual([{ ...executable.action, confirm_token: 'aaa.bbb' }])
  })

  it('gửi lý do khi từ chối', async () => {
    const user = userEvent.setup()
    const target = v3.data.phases.flatMap((phase) => phase.steps).find((step) => step.step_id === 'bu_an_uong')!
    const path = `/roadmap/steps/${target.step_id}/decision`
    const request = restFixture('RoadmapStepDecisionRequest.reject')
    const { calls } = mountApp(backend({
      'GET /roadmap': v3, 'GET /roadmap/versions': versions,
      [`POST ${path}`]: withDecision(target.step_id, 'rejected'),
    }), '/roadmap')
    const card = await stepCard(target.title)
    await user.click(card.getByRole('button', { name: 'Từ chối' }))
    const dialog = within(await screen.findByRole('alertdialog'))
    await user.type(dialog.getByRole('textbox', { name: /Vì sao bạn muốn từ chối/ }), String(request.reason))
    await user.click(dialog.getByRole('button', { name: 'Từ chối' }))
    expect(await card.findByText('Đã từ chối')).toBeVisible()
    expect(callsTo(calls, 'POST', path).map(bodyOf)).toEqual([request])
  })

  it.each(['amount', 'due_date'] as const)('sửa %s và hiển thị phiên bản do server trả về', async (field) => {
    const user = userEvent.setup()
    const target = v2.data.phases[0]!.steps[0]!
    const path = `/roadmap/steps/${target.step_id}/edit`
    const request = restFixture(`RoadmapStepEditRequest.${field}`)
    const edited = structuredClone(v2)
    edited.id = edited.id.replace(/v2$/, 'v3')
    edited.data.version = 3
    edited.data.based_on_version = 2
    if (field === 'amount') edited.data.phases[0]!.steps[0]!.amount_vnd = Number(request.amount_vnd)
    else edited.data.phases[0]!.steps[0]!.due_date = String(request.due_date)
    const { calls } = mountApp(backend({
      'GET /roadmap': v2, 'GET /roadmap/versions': versions,
      [`POST ${path}`]: edited,
    }), '/roadmap')
    await user.click((await stepCard(target.title)).getByRole('button', { name: 'Sửa' }))
    const drawer = within(await screen.findByRole('dialog', { name: 'Sửa bước' }))
    expect(drawer.getByRole('button', { name: 'Lưu thay đổi' })).toBeDisabled()
    if (field === 'amount') fireEvent.change(drawer.getByLabelText('Số tiền'), { target: { value: request.amount_vnd } })
    else fireEvent.change(drawer.getByLabelText('Ngày đến hạn'), { target: { value: request.due_date } })
    await user.click(drawer.getByRole('button', { name: 'Lưu thay đổi' }))

    expect(await screen.findByRole('heading', { name: 'Lộ trình · Phiên bản 3' })).toBeVisible()
    expect(callsTo(calls, 'POST', path).map(bodyOf)).toEqual([request])
    const display = field === 'amount' ? formatVnd(Number(request.amount_vnd)).replace('\u00a0', ' ') : `Hạn ${formatDayMonth(String(request.due_date))}`
    expect((await stepCard(target.title)).getByText(display)).toBeVisible()
  })

  it('báo xung đột và tải lại lộ trình cùng danh sách phiên bản', async () => {
    const target = v2.data.phases.flatMap((phase) => phase.steps).find((step) => step.status === 'pending')!
    let current = v2
    const { calls } = mountApp(backend({
      'GET /roadmap': () => current, 'GET /roadmap/versions': versions,
      [`POST /roadmap/steps/${target.step_id}/decision`]: () => {
        current = v3
        return json(409, { error: { code: 'ROADMAP_VERSION_CONFLICT' } })
      },
    }), '/roadmap')
    await userEvent.click((await stepCard(target.title)).getByRole('button', { name: 'Chấp nhận' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(ERROR_MESSAGES.ROADMAP_VERSION_CONFLICT)
    expect(await screen.findByRole('heading', { name: 'Lộ trình · Phiên bản 3' })).toBeVisible()
    expect(callsTo(calls, 'GET', '/roadmap')).toHaveLength(2)
    expect(callsTo(calls, 'GET', '/roadmap/versions')).toHaveLength(2)
  })

  it('hiện EmptyState và lập lộ trình đầu tiên khi cả hai API báo chưa có', async () => {
    const { calls } = mountApp(backend({
      'GET /roadmap': json(404, { error: { code: 'ROADMAP_NOT_FOUND' } }),
      'GET /roadmap/versions': restFixture('RoadmapVersionsResponse.chua_co'),
      'POST /roadmap/regenerate': queued,
    }), '/roadmap')
    expect(await screen.findByRole('heading', { name: 'Chưa có lộ trình' })).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Lập lộ trình' }))
    expect(await screen.findByText('Đang chờ lập lộ trình')).toBeVisible()
    expect(callsTo(calls, 'POST', '/roadmap/regenerate').map(bodyOf)).toEqual([restFixture('RegenerateRoadmapRequest.empty')])
  })

  it('hiện hai lựa chọn khi chưa khả thi và gửi lựa chọn được bấm', async () => {
    const request = restFixture('RegenerateRoadmapRequest.alternative')
    const { calls } = mountApp(backend({
      'GET /roadmap': infeasible, 'GET /roadmap/versions': { versions: [], active_version: infeasible.data.version },
      'POST /roadmap/regenerate': queued,
    }), '/roadmap')
    for (const option of infeasible.data.alternatives) {
      expect(await screen.findByRole('button', { name: option.label })).toBeVisible()
      expect(screen.getByText(option.summary)).toBeVisible()
    }
    const option = infeasible.data.alternatives.find((alternative) => alternative.option_id === request.alternative_id)!
    await userEvent.click(screen.getByRole('button', { name: option.label }))
    expect(await screen.findByText('Đang chờ lập lộ trình')).toBeVisible()
    expect(callsTo(calls, 'POST', '/roadmap/regenerate').map(bodyOf)).toEqual([{
      alternative_id: request.alternative_id, based_on_version: request.based_on_version,
    }])
  })

  it('poll queued → running → done rồi tải lại cả hai tài nguyên', async () => {
    const path = `/roadmap/jobs/${queued.job_id}`
    const jobResponses = [queued, running, done]
    let current = v2
    const { calls } = mountApp(backend({
      'GET /roadmap': () => current,
      'GET /roadmap/versions': () => current === v3 ? versions : {
        versions: versions.versions.filter((summary) => summary.status === 'active'),
        active_version: versions.active_version,
      },
      'POST /roadmap/regenerate': queued,
      [`GET ${path}`]: () => {
        const job = jobResponses.shift()!
        if (job.status === 'done') current = v3
        return job
      },
    }), '/roadmap')
    const regenerate = await screen.findByRole('button', { name: 'Lập lại lộ trình' })
    expect(regenerate).toBeEnabled()
    vi.useFakeTimers()
    await act(async () => { fireEvent.click(regenerate) })
    expect(screen.getByText('Đang chờ lập lộ trình')).toBeVisible()
    await pollOnce()
    expect(screen.getByRole('progressbar')).toHaveValue(queued.progress)
    await pollOnce()
    expect(screen.getByText('Đang tính cách phân bổ')).toBeVisible()
    expect(screen.getByRole('progressbar')).toHaveValue(running.progress)
    await pollOnce()
    expect(screen.getByRole('heading', { name: 'Lộ trình · Phiên bản 3' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Có phiên bản mới' })).toBeVisible()
    expect(callsTo(calls, 'GET', '/roadmap')).toHaveLength(2)
    expect(callsTo(calls, 'GET', '/roadmap/versions')).toHaveLength(2)
    await pollOnce()
    expect(callsTo(calls, 'GET', path)).toHaveLength(3)
  })

  it('tiếp tục current_job sau tải trang và hiện thông báo lỗi của server', async () => {
    vi.useFakeTimers()
    const path = `/roadmap/jobs/${queued.job_id}`
    const { calls } = mountApp(backend({
      'GET /roadmap': v2,
      'GET /roadmap/versions': restFixture('RoadmapVersionsResponse.dang_sinh_lai'),
      [`GET ${path}`]: failed,
    }), '/roadmap')
    await vi.waitFor(() => expect(screen.getByRole('progressbar')).toBeVisible())
    await pollOnce()
    expect(screen.getByRole('alert')).toHaveTextContent(failed.error_message!)
    expect(screen.getByRole('button', { name: 'Lập lại lộ trình' })).toBeEnabled()
    await pollOnce()
    expect(callsTo(calls, 'GET', path)).toHaveLength(1)
    expect(callsTo(calls, 'POST', '/roadmap/regenerate')).toHaveLength(0)
  })
})
