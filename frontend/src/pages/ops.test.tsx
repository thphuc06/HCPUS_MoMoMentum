import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { OpsTraceDetail, OpsTraceListResponse } from '@/api/phase5Schemas'
import { TraceResponse } from '@/api/schemas'
import { ChatLauncherContext } from '@/chat/launcher'
import { ExplainBody } from '@/features/explain/ExplainBody'
import { restFixture } from '@/test/fixtures'
import { Providers, fakeApi, fakeAuth, session } from '@/test/helpers'
import { backend, callsTo, config, json, mountApp } from '@/test/mountApp'

// Màn trace X1 và bảng vận hành: chỉ nhóm Cognito `ops` (đọc nhóm từ token); người khác không thấy lối vào và không gọi `/ops/*`.

afterEach(() => vi.unstubAllGlobals())

const OPS = { session: { groups: ['ops'] } }
const detail = OpsTraceDetail.parse(restFixture('OpsTraceDetail.what_if'))
const traces = OpsTraceListResponse.parse(restFixture('OpsTraceListResponse.default'))

describe('bảng vận hành /ops/summary', () => {
  it('số tổng hợp, lượt gọi model theo ngày so với trần, các lượt gần đây dẫn tới màn trace', async () => {
    const user = userEvent.setup()
    const { calls, router } = mountApp(backend(), '/ops', config, OPS)
    await waitFor(() => expect(router.state.location.pathname).toBe('/ops/summary'))
    const kpis = await screen.findByTestId('ops-kpis')
    expect(kpis).toHaveTextContent('42')
    expect(kpis).toHaveTextContent('3 bị từ chối · 1 lỗi')
    expect(kpis).toHaveTextContent('4,2 s / 9,8 s')
    expect(kpis).toHaveTextContent('2%')
    expect(kpis).toHaveTextContent('2 / 96 lần gọi')
    expect(kpis).toHaveTextContent('27.500 ₫')
    const days = screen.getByRole('list', { name: 'Lượt gọi model theo ngày' })
    expect(days.querySelectorAll(':scope > li')).toHaveLength(3)
    // tổng ngày không so với tổng trần mọi model (7.800); từng model so với trần của chính nó
    expect(days).not.toHaveTextContent('7.800')
    const first = days.querySelector<HTMLElement>('[data-day="2026-12-08"]')!
    expect(within(first).getByTestId('ops-day-total')).toHaveTextContent('61 lượt')
    const models = within(within(first).getByRole('list', { name: 'Theo model ngày 08/12' })).getAllByRole('listitem')
    expect(models.map((m) => m.textContent)).toEqual(['Nova 2 Lite46 / 2.000', 'Haiku 4.53 / 2.000', 'Sonnet 4.612 / 400'])
    expect(models.every((m) => m.getAttribute('data-level') === 'ok')).toBe(true)
    expect(within(first).getByText('Sonnet 4.6')).toHaveAttribute('title', 'global.anthropic.claude-sonnet-4-6')
    expect(within(first).getByRole('meter', { name: 'Sonnet 4.6: 12 trên trần 400' })).toHaveAttribute('aria-valuemax', '400')
    expect(screen.queryByText('Gần trần')).toBeNull()

    const table = await screen.findByRole('table')
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(traces.traces.length)
    expect(rows[1]).toHaveTextContent('FORECAST_UNAVAILABLE')
    expect(rows[1]).toHaveTextContent(traces.traces[1]!.user_ref)
    // tab bar ẩn ở màn vận hành, khung giãn thành desktop
    expect(screen.queryByRole('navigation', { name: 'Điều hướng chính' })).toBeNull()
    expect(document.querySelector('[data-layout="wide"]')).not.toBeNull()

    await user.selectOptions(screen.getByRole('combobox', { name: 'Kết quả' }), 'error')
    await waitFor(() => expect(callsTo(calls, 'GET', '/ops/traces').map((c) => new URL(c.url).searchParams.get('outcome'))).toEqual([null, 'error']))

    await user.click(within(await screen.findByRole('table')).getAllByRole('link')[0]!)
    await waitFor(() => expect(router.state.location.pathname).toBe(`/ops/traces/${traces.traces[0]!.trace_id}`))
  })

  it('không có lượt nào: nói thật, không vẽ số giả', async () => {
    mountApp(backend({ 'GET /ops/summary': restFixture('OpsSummaryResponse.khong_co_luot'), 'GET /ops/traces': { traces: [] } }), '/ops', config, OPS)
    expect(await screen.findByText('Chưa có lượt gọi model nào trong khoảng này.')).toBeInTheDocument()
    expect(screen.getByTestId('ops-kpis')).toHaveTextContent('Chưa có lượt')
    expect(await screen.findByText('Không có lượt nào.')).toBeInTheDocument()
  })

  it('model từ 80% trần của chính nó: cảnh báo "Gần trần"; chạm trần: "Chạm trần"; model ngoài cấu hình: chỉ số lượt', async () => {
    const body = structuredClone(restFixture('OpsSummaryResponse.default')) as Record<string, any>
    body.model_calls_by_day = [{
      day: '2026-12-08',
      model_calls: 4219,
      cap: 7800,
      by_model: [
        { model: 'global.amazon.nova-2-lite-v1:0', model_calls: 1599, cap: 2000 },
        { model: 'global.anthropic.claude-haiku-4-5-20251001-v1:0', model_calls: 2000, cap: 2000 },
        { model: 'global.anthropic.claude-sonnet-4-6', model_calls: 320, cap: 400 },
        { model: 'global.moonshotai.kimi-k3', model_calls: 300 },
      ],
    }]
    mountApp(backend({ 'GET /ops/summary': body }), '/ops', config, OPS)
    const list = await screen.findByRole('list', { name: 'Theo model ngày 08/12' })
    const rows = within(list).getAllByRole('listitem')
    expect(rows.map((r) => r.getAttribute('data-level'))).toEqual(['ok', 'over', 'near', null])
    expect(rows[0]).not.toHaveTextContent('Gần trần')
    expect(rows[1]).toHaveTextContent('Chạm trần')
    expect(rows[1]!.querySelector('[data-chip="bad"]')).not.toBeNull()
    expect(rows[2]).toHaveTextContent('Gần trần')
    expect(rows[2]).toHaveTextContent('320 / 400')
    expect(rows[2]!.querySelector('[data-chip="warn"]')).not.toBeNull()
    expect(rows[3]).toHaveTextContent('Kimi K3')
    expect(rows[3]).toHaveTextContent('300 lượt')
    expect(within(rows[3]!).queryByRole('meter')).toBeNull()
    expect(screen.getByTestId('ops-day-total')).toHaveTextContent('4.219 lượt')
  })

  it('không có by_model (số từ bản ghi lượt): hiện tổng so với trần như cũ', async () => {
    const body = structuredClone(restFixture('OpsSummaryResponse.default')) as Record<string, any>
    for (const d of body.model_calls_by_day) delete d.by_model
    mountApp(backend({ 'GET /ops/summary': body }), '/ops', config, OPS)
    const days = await screen.findByRole('list', { name: 'Lượt gọi model theo ngày' })
    expect(days.querySelectorAll(':scope > li')).toHaveLength(3)
    expect(within(days).getByText('61 / 7.800')).toBeInTheDocument()
    expect(within(days).queryByRole('list')).toBeNull()
    expect(screen.queryByTestId('ops-day-total')).toBeNull()
  })

  it('tài khoản không thuộc ops: không gọi /ops/*, hiện "Chỉ dành cho đội vận hành"', async () => {
    const { calls } = mountApp(backend(), '/ops')
    expect(await screen.findByRole('heading', { name: 'Chỉ dành cho đội vận hành' })).toBeInTheDocument()
    expect(calls.filter((c) => new URL(c.url).pathname.startsWith('/ops'))).toHaveLength(0)
  })

  it('token có nhóm ops nhưng server từ chối (403): cũng hiện màn không có quyền', async () => {
    mountApp(backend({ 'GET /ops/summary': json(403, { error: { code: 'FORBIDDEN' } }) }), '/ops', config, OPS)
    expect(await screen.findByRole('heading', { name: 'Chỉ dành cho đội vận hành' })).toBeInTheDocument()
  })
})

describe('màn trace X1 /ops/traces/:id', () => {
  it('tóm tắt lượt, mọi bước theo thứ tự (lần gọi tool có trạng thái), luật, dữ liệu đã dùng, khối đã phát', async () => {
    const { calls } = mountApp(backend(), `/ops/traces/${detail.trace_id}`, config, OPS)
    expect(await screen.findByTestId('ops-trace-id')).toHaveTextContent(detail.trace_id)
    expect(callsTo(calls, 'GET', `/ops/traces/${detail.trace_id}`)).toHaveLength(1)
    expect(screen.getByTestId('ops-duration')).toHaveTextContent('5,4 s')
    expect(screen.getByTestId('ops-tokens')).toHaveTextContent('5.200 / 640')
    expect(screen.getByTestId('ops-cost')).toHaveTextContent('655 ₫')
    const steps = within(screen.getByRole('list', { name: 'Các bước của lượt' })).getAllByRole('listitem')
    expect(steps.map((s) => s.getAttribute('data-step'))).toEqual(detail.steps.map((s) => s.step))
    expect(steps[1]).toHaveTextContent('ledger · get_jar_balances')
    expect(steps[1]).toHaveTextContent('OK')
    expect(steps[0]).toHaveTextContent('router')
    expect(steps[0]).toHaveTextContent('480 ms')
    const rules = screen.getByRole('region', { name: 'Luật đã kiểm' })
    expect(rules.querySelector('[data-rule="obligation_to_income"]')).toHaveAttribute('data-outcome', 'warn')
    expect(within(screen.getByRole('region', { name: 'Dữ liệu đã dùng' })).getByText('760.000 ₫')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Khối đã phát' })).getByText('options')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: `Lần gọi tool (${detail.tool_calls.length})` })).toBeInTheDocument()
    // logo "Yofina · Trace" về Tổng quan
    expect(screen.getByRole('link', { name: 'Yofina · Trace, về Tổng quan' })).toHaveAttribute('href', '/')
  })

  it('lần gọi tool lỗi hoặc bị Cedar từ chối: có mã lỗi', async () => {
    const failing = structuredClone(restFixture('OpsTraceDetail.what_if')) as Record<string, any>
    failing.steps[2] = { step: 'forecast___get_forecast', ms: 310, status: 'error', code: 'FORECAST_UNAVAILABLE' }
    failing.tool_calls[1] = { target: 'forecast', tool: 'get_forecast', ms: 310, status: 'denied' }
    mountApp(backend({ [`GET /ops/traces/${detail.trace_id}`]: failing }), `/ops/traces/${detail.trace_id}`, config, OPS)
    const steps = within(await screen.findByRole('list', { name: 'Các bước của lượt' })).getAllByRole('listitem')
    expect(steps[2]).toHaveTextContent('Lỗi · FORECAST_UNAVAILABLE')
    expect(screen.getByText('Cedar từ chối')).toBeInTheDocument()
  })

  it('bước tool lặp lại là các dòng riêng, giữ thứ tự, mỗi dòng có ms, trạng thái và mã', async () => {
    const repeated = structuredClone(restFixture('OpsTraceDetail.what_if')) as Record<string, any>
    repeated.steps = [
      { step: 'router', ms: 480 },
      { step: 'forecast___run_scenario', ms: 1500, status: 'ok' },
      { step: 'forecast___run_scenario', ms: 1200, status: 'error', code: 'PARAMS_INVALID' },
      { step: 'ledger___get_jar_balances', ms: 90, status: 'denied' },
      { step: 'forecast___run_scenario', ms: 980, status: 'ok' },
      { step: 'analyst', ms: 2600 },
    ]
    mountApp(backend({ [`GET /ops/traces/${detail.trace_id}`]: repeated }), `/ops/traces/${detail.trace_id}`, config, OPS)
    const steps = within(await screen.findByRole('list', { name: 'Các bước của lượt' })).getAllByRole('listitem')
    expect(steps.map((s) => s.getAttribute('data-step'))).toEqual(repeated.steps.map((s: { step: string }) => s.step))
    expect(steps[1]).toHaveTextContent('forecast · run_scenario')
    expect(steps[1]).toHaveTextContent('OK')
    expect(steps[1]).toHaveTextContent('1,5 s')
    expect(steps[2]).toHaveTextContent('Lỗi · PARAMS_INVALID')
    expect(steps[2]).toHaveTextContent('1,2 s')
    expect(steps[3]).toHaveTextContent('ledger · get_jar_balances')
    expect(steps[3]).toHaveTextContent('Cedar từ chối')
    expect(steps[3]).toHaveTextContent('90 ms')
    expect(steps[4]).toHaveTextContent('980 ms')
    expect(steps[5]).not.toHaveTextContent('OK')
  })

  it('không có trace: báo lỗi tiếng Việt; người không thuộc ops không gọi API', async () => {
    mountApp(backend({ [`GET /ops/traces/${detail.trace_id}`]: json(404, { error: { code: 'TRACE_NOT_FOUND' } }) }), `/ops/traces/${detail.trace_id}`, config, OPS)
    expect(await screen.findByText('Chưa mở được trace')).toBeInTheDocument()
  })

  it('người không thuộc ops mở thẳng đường dẫn: không gọi API', async () => {
    const { calls } = mountApp(backend(), `/ops/traces/${detail.trace_id}`)
    expect(await screen.findByRole('heading', { name: 'Chỉ dành cho đội vận hành' })).toBeInTheDocument()
    expect(callsTo(calls, 'GET', `/ops/traces/${detail.trace_id}`)).toHaveLength(0)
  })
})

describe('hàng "Mã trace" của bảng "Vì sao"', () => {
  const trace = TraceResponse.parse(restFixture('TraceResponse.what_if'))

  function renderExplain(groups: string[]) {
    const launcher = { open: vi.fn(), close: vi.fn() }
    const router = createMemoryRouter([
      { path: '/', element: <ExplainBody block={trace.explain} detail={trace.detail} /> },
      { path: '/ops/traces/:traceId', element: <p>MÀN TRACE</p> },
    ])
    render(
      <ChatLauncherContext.Provider value={launcher}>
        <Providers api={fakeApi()} auth={fakeAuth(session({ groups }))}>
          <RouterProvider router={router} />
        </Providers>
      </ChatLauncherContext.Provider>,
    )
    return { router, launcher }
  }

  it('nhóm ops: bấm hàng Mã trace thì đóng chat và mở màn trace của đúng lượt', async () => {
    const { router, launcher } = renderExplain(['ops'])
    const open = await screen.findByRole('button', { name: `Mở màn trace của lượt ${trace.explain.data.subject_trace_id}` })
    await userEvent.setup().click(open)
    expect(launcher.close).toHaveBeenCalled()
    expect(await screen.findByText('MÀN TRACE')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe(`/ops/traces/${trace.explain.data.subject_trace_id}`)
  })

  it('không thuộc ops: chỉ thấy mã, không có lối vào', async () => {
    renderExplain([])
    expect(await screen.findByTestId('explain-trace-id')).toHaveTextContent(trace.explain.data.subject_trace_id)
    expect(screen.queryByRole('button', { name: /Mở màn trace/ })).toBeNull()
  })
})
