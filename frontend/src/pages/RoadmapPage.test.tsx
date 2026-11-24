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
import { fakeApi, Providers } from '@/test/helpers'
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

/** Sửa và Từ chối nằm trong bảng thao tác phụ của bước (mỗi bước một nút chính). */
async function openStepMenu(user: ReturnType<typeof userEvent.setup>, card: ReturnType<typeof within>) {
  await user.click(card.getByRole('button', { name: /^Sửa/ }))
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
    // Danh sách phiên bản bên dưới cũng có lý do và mức khả thi của từng bản: kiểm trong khối lộ trình đang hiện.
    const shown = within(screen.getByRole('heading', { name: 'Lộ trình · Phiên bản 3' }).closest('[data-block="roadmap"]') as HTMLElement)
    expect(shown.getByText(v3.data.headline)).toBeVisible()
    expect(shown.getByText(v3.data.reason.text)).toBeVisible()
    expect(shown.getByText(v3.data.reason.detail![0]!.label)).toBeVisible()
    expect(shown.getByText('Khả thi sau điều chỉnh')).toBeVisible()
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

  it('hiện tên hũ của người dùng ở mọi bước, không hiện mã hũ thô', async () => {
    mountApp(backend({ 'GET /roadmap': v3, 'GET /roadmap/versions': versions }), '/roadmap')
    const overview = restFixture('OverviewResponse.minh') as { jars: Array<{ code: string; name: string }> }
    const name = (code: string) => overview.jars.find((j) => j.code === code)!.name
    const steps = v3.data.phases.flatMap((phase) => phase.steps).filter((s) => s.jar_code && s.to_jar_code)
    expect(steps.length).toBeGreaterThan(0)
    for (const s of steps) {
      const card = await stepCard(s.title)
      expect(await card.findByText(`Hũ ${name(s.jar_code!)} → ${name(s.to_jar_code!)}`)).toBeVisible()
    }
    expect(screen.queryByText(/\b(giai_tri|nghia_vu|an_uong|du_phong|du_lich)\b/)).toBeNull()
  })

  it('khối lộ trình trong chat lấy tên hũ từ danh sách hũ của người dùng', async () => {
    render(<Providers api={fakeApi()}><BlockRenderer raw={v3} blockId={v3.id} /></Providers>)
    expect(await screen.findByText('Hũ Giải trí → Ăn uống')).toBeVisible()
    expect(screen.getByText('Hũ Giải trí → Nghĩa vụ')).toBeVisible()
    expect(screen.queryByText(/giai_tri|an_uong|nghia_vu/)).toBeNull()
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
    await openStepMenu(user, card)
    await user.click(within(await screen.findByRole('dialog', { name: 'Thao tác với bước' })).getByRole('button', { name: 'Từ chối' }))
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
    await openStepMenu(user, await stepCard(target.title))
    await user.click(within(await screen.findByRole('dialog', { name: 'Thao tác với bước' })).getByRole('button', { name: 'Sửa' }))
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

describe('trang Lộ trình: danh sách phiên bản', () => {
  afterEach(() => vi.unstubAllGlobals())

  // Bản cũ (v1, đã thay) dựng từ khối v2 của fixture, đổi số phiên bản và trạng thái.
  const v1 = structuredClone(v2)
  v1.id = v1.id.replace(/v2$/, 'v1')
  v1.data.version = 1
  v1.data.status = 'superseded'
  delete v1.data.based_on_version

  it('liệt kê đủ phiên bản (đề xuất, đang dùng, đã thay) với trạng thái, mức khả thi và số bước chờ', async () => {
    mountApp(backend({ 'GET /roadmap': v2, 'GET /roadmap/versions': versions }), '/roadmap')
    const list = await screen.findByRole('list', { name: 'Các phiên bản lộ trình' })
    const items = within(list).getAllByRole('button')
    expect(items).toHaveLength(versions.versions.length)
    expect(items[0]).toHaveTextContent('Phiên bản 3')
    expect(items[0]).toHaveTextContent('Đề xuất · chờ bạn chọn')
    expect(items[0]).toHaveTextContent('5 bước chờ')
    expect(items[1]).toHaveTextContent('Phiên bản 2 (bản này)')
    expect(items[1]).toHaveTextContent('Đang dùng')
    expect(items[1]).toHaveAttribute('aria-pressed', 'true')
    expect(items[2]).toHaveTextContent('Bản cũ · đã thay')
    expect(items[2]).toHaveTextContent('Chưa khả thi')
  })

  it('bấm một bản: tải đúng phiên bản đó để xem (chỉ đọc) và có lối so với bản đang dùng', async () => {
    const user = userEvent.setup()
    const { calls } = mountApp(backend({
      'GET /roadmap': (_init, url) => (url.searchParams.get('version') === '1' ? v1 : v2),
      'GET /roadmap/versions': versions,
      'GET /roadmap/diff': restFixture('RoadmapDiffResponse.v2_v3'),
    }), '/roadmap')
    const list = await screen.findByRole('list', { name: 'Các phiên bản lộ trình' })
    await user.click(within(list).getByRole('button', { name: /Phiên bản 1/ }))
    const view = await screen.findByTestId('roadmap-version-view')
    expect(await within(view).findByRole('heading', { name: 'Lộ trình · Phiên bản 1' })).toBeVisible()
    expect(within(view).queryByRole('button', { name: /Chấp nhận|Từ chối|Sửa|Thực hiện/ })).toBeNull()
    expect(callsTo(calls, 'GET', '/roadmap').map(({ url }) => new URL(url).search)).toContain('?version=1')
    const compare = within(view).getByRole('link', { name: 'So với bản đang dùng' })
    expect(compare).toHaveAttribute('href', '/roadmap/compare?from=1&to=2')
    await user.click(compare)
    await screen.findByRole('heading', { name: 'So với bản cũ' })
    await vi.waitFor(() => expect(callsTo(calls, 'GET', '/roadmap/diff').map(({ url }) => new URL(url).search)).toEqual(['?from_version=1&to_version=2']))
  })

  it('bấm lại bản đang mở thì đóng; bấm bản đang hiện ở trên không mở thêm gì', async () => {
    const user = userEvent.setup()
    mountApp(backend({ 'GET /roadmap': (_init, url) => (url.searchParams.get('version') === '3' ? v3 : v2), 'GET /roadmap/versions': versions }), '/roadmap')
    const list = await screen.findByRole('list', { name: 'Các phiên bản lộ trình' })
    await user.click(within(list).getByRole('button', { name: /Phiên bản 2/ }))
    expect(screen.queryByTestId('roadmap-version-view')).toBeNull()
    await user.click(within(list).getByRole('button', { name: /Phiên bản 3/ }))
    const view = await screen.findByTestId('roadmap-version-view')
    expect(within(view).getByRole('link', { name: 'So với bản đang dùng' })).toHaveAttribute('href', '/roadmap/compare?from=2&to=3')
    await user.click(within(list).getByRole('button', { name: /Phiên bản 3/ }))
    expect(screen.queryByTestId('roadmap-version-view')).toBeNull()
  })
})

describe('lộ trình dạng dòng thời gian (cảnh 4)', () => {
  afterEach(() => vi.unstubAllGlobals())

  const steps = v2.data.phases.flatMap((phase) => phase.steps)

  it('mỗi bước một nút chính theo trạng thái; Sửa, Từ chối nằm trong menu phụ', async () => {
    const user = userEvent.setup()
    mountApp(backend({ 'GET /roadmap': v2, 'GET /roadmap/versions': versions }), '/roadmap')
    for (const s of steps) {
      const card = await stepCard(s.title)
      const primary = card.queryAllByRole('button', { name: /^(Chấp nhận|Thực hiện)$/ })
      expect(primary.length).toBeLessThanOrEqual(1)
      if (s.status === 'accepted') expect(primary.map((b) => b.textContent)).toEqual(s.action ? ['Thực hiện'] : [])
      else expect(primary.map((b) => b.textContent)).toEqual(['Chấp nhận'])
      // Không còn nút Sửa hay Từ chối đứng riêng trên bước.
      expect(card.queryByRole('button', { name: 'Sửa' })).toBeNull()
      expect(card.queryByRole('button', { name: 'Từ chối' })).toBeNull()
    }
    const rejected = steps.find((s) => s.status === 'rejected')!
    await user.click((await stepCard(rejected.title)).getByRole('button', { name: /^Sửa…/ }))
    const sheet = within(await screen.findByRole('dialog', { name: 'Thao tác với bước' }))
    expect(sheet.getByText(rejected.title)).toBeInTheDocument()
    expect(sheet.getAllByRole('button').map((b) => b.textContent)).toEqual(['Sửa', 'Hủy'])
    await user.click(sheet.getByRole('button', { name: 'Hủy' }))
    await vi.waitFor(() => expect(screen.queryByRole('dialog', { name: 'Thao tác với bước' })).toBeNull())
    const pending = steps.find((s) => s.status === 'pending')!
    const trigger = (await stepCard(pending.title)).getByRole('button', { name: /^Sửa, từ chối…/ })
    expect(trigger).toHaveAttribute('aria-haspopup', 'dialog')
    await user.click(trigger)
    const sheet2 = within(await screen.findByRole('dialog', { name: 'Thao tác với bước' }))
    expect(sheet2.getAllByRole('button').map((b) => b.textContent)).toEqual(['Sửa', 'Từ chối', 'Hủy'])
  })

  it('nút tròn trên trục theo trạng thái, đánh số liên tục; chip "Chờ" kiểu thông tin, không dùng màu "sát"', async () => {
    mountApp(backend({ 'GET /roadmap': v2, 'GET /roadmap/versions': versions }), '/roadmap')
    const block = (await screen.findByRole('heading', { name: `Lộ trình · Phiên bản ${v2.data.version}` })).closest('[data-block="roadmap"]') as HTMLElement
    const items = Array.from(block.querySelectorAll('li[data-step-status]'))
    expect(items.map((li) => li.getAttribute('data-step-status'))).toEqual(steps.map((s) => s.status))
    items.forEach((li, i) => {
      const node = li.querySelector('[data-node]')!
      expect(node.getAttribute('data-node')).toBe(steps[i]!.status)
      if (steps[i]!.status === 'pending') expect(node).toHaveTextContent(String(i + 1))
    })
    // Bước cuối không có đoạn trục nối xuống; đoạn sau bước đã chấp nhận tô màu "đủ".
    expect(items.at(-1)!.querySelector('[data-axis]')).toBeNull()
    items.slice(0, -1).forEach((li, i) => expect(li.querySelector('[data-axis]')).toHaveAttribute('data-axis', steps[i]!.status === 'accepted' ? 'done' : 'todo'))
    for (const chip of within(block).getAllByText('Chờ', { selector: '[data-chip] span' })) {
      expect(chip.closest('[data-chip]')).toHaveAttribute('data-chip', 'info')
    }
    // Giai đoạn có khoảng ngày của server.
    const phase = v2.data.phases[0]!
    expect(within(block).getByRole('heading', { name: phase.title }).parentElement).toHaveTextContent(formatDayMonth(phase.end_date))
  })

  it('vừa chấp nhận trên màn: nút tròn đổ màu và dấu tích tự vẽ (một lần)', async () => {
    const user = userEvent.setup()
    const target = v3.data.phases.flatMap((phase) => phase.steps).find((s) => s.status === 'pending')!
    mountApp(backend({
      'GET /roadmap': v3, 'GET /roadmap/versions': versions,
      [`POST /roadmap/steps/${target.step_id}/decision`]: withDecision(target.step_id, 'accepted'),
    }), '/roadmap')
    const card = await stepCard(target.title)
    // Lúc tải, bước đã chấp nhận sẵn không có hiệu ứng.
    expect(document.querySelector('.motion-draw')).toBeNull()
    await user.click(card.getByRole('button', { name: 'Chấp nhận' }))
    await card.findByText('Đã chấp nhận')
    const li = (await screen.findByText(target.title)).closest('li')!
    expect(li.querySelector('[data-node="accepted"]')).toHaveClass('motion-pop')
    expect(li.querySelector('.motion-draw')).not.toBeNull()
  })
})