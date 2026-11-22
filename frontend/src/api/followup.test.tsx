import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiProvider, FORECAST_FOLLOW_UP_MS, useForecastFollowUp, useRefreshAfterWrite } from './ApiProvider'
import type { ApiClient } from './client'
import { ApiError } from './errors'
import { useApiResource } from './resource'
import { usePreview } from './useConfirmPreview'

// Cơ chế theo dõi dự báo sau một lần ghi: số dư làm mới ngay, dự báo đọc lại cho tới khi `computed_at` theo kịp thời điểm
// server của lần ghi (có giới hạn), và hỏi lại khi dự báo báo `stale`. Dùng client giả ở mức ApiClient; mọi mốc thời gian
// do test dựng.

afterEach(() => vi.useRealTimers())

const stub = (over: Partial<ApiClient>): ApiClient => over as ApiClient

type Fc = { computed_at: string; stale?: boolean }

function Harness({ fetchForecast, delayMs = 10 }: { fetchForecast: () => Promise<Fc>; delayMs?: number }) {
  const pending = useForecastFollowUp()
  const bump = useRefreshAfterWrite()
  const res = useApiResource(
    () => fetchForecast(),
    [],
    true,
    (d) => {
      if (pending(d.computed_at)) return { delayMs, maxMs: FORECAST_FOLLOW_UP_MS }
      if (d.stale) return { delayMs, maxMs: 100 }
      return null
    },
  )
  return (
    <div>
      <p data-testid="computed">{res.data?.computed_at ?? 'chưa có'}</p>
      <p data-testid="pending">{res.data && pending(res.data.computed_at) ? 'đang chờ' : 'xong'}</p>
      <button onClick={() => bump('2026-11-22T05:59:26Z')}>ghi</button>
      <button onClick={() => bump()}>ghi không mốc</button>
    </div>
  )
}

describe('theo dõi dự báo sau khi ghi', () => {
  it('đọc lại dự báo cho tới khi computed_at theo kịp thời điểm server của lần ghi, rồi dừng', async () => {
    // dự báo cũ trong 3 lần đầu sau lần ghi, rồi mới
    let calls = 0
    let afterWrite = 0
    const fetchForecast = vi.fn(async (): Promise<Fc> => {
      calls++
      if (afterWrite === 0) return { computed_at: '2026-11-22T05:00:00Z' }
      afterWrite++
      return { computed_at: afterWrite > 3 ? '2026-11-22T05:59:29Z' : '2026-11-22T05:00:00Z' }
    })
    render(
      <ApiProvider client={stub({})}>
        <Harness fetchForecast={fetchForecast} />
      </ApiProvider>,
    )
    expect(await screen.findByTestId('computed')).toHaveTextContent('2026-11-22T05:00:00Z')
    expect(screen.getByTestId('pending')).toHaveTextContent('xong') // chưa có lần ghi nào: không đọc lại
    await new Promise((r) => setTimeout(r, 60))
    expect(calls).toBe(1)

    afterWrite = 1
    await userEvent.setup().click(screen.getByRole('button', { name: /^ghi$/ }))
    await waitFor(() => expect(screen.getByTestId('computed')).toHaveTextContent('2026-11-22T05:59:29Z'), { timeout: 3000 })
    await waitFor(() => expect(screen.getByTestId('pending')).toHaveTextContent('xong'))
    const settled = calls
    expect(settled).toBeGreaterThanOrEqual(4)
    await new Promise((r) => setTimeout(r, 80))
    expect(calls).toBe(settled) // đã theo kịp thì không hỏi nữa
  })

  it('ghi không kèm mốc server (đặt lại demo, làm mới sau lỗi) thì chỉ tải lại một lần, không chờ dự báo', async () => {
    const fetchForecast = vi.fn(async (): Promise<Fc> => ({ computed_at: '2026-11-22T05:00:00Z' }))
    render(
      <ApiProvider client={stub({})}>
        <Harness fetchForecast={fetchForecast} />
      </ApiProvider>,
    )
    await screen.findByText('2026-11-22T05:00:00Z')
    await userEvent.setup().click(screen.getByRole('button', { name: 'ghi không mốc' }))
    await waitFor(() => expect(fetchForecast).toHaveBeenCalledTimes(2))
    await new Promise((r) => setTimeout(r, 80))
    expect(fetchForecast).toHaveBeenCalledTimes(2)
  })

  it('có giới hạn: dự báo mãi không đổi thì dừng sau cửa sổ chờ (không hỏi vô hạn)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
    const fetchForecast = vi.fn(async (): Promise<Fc> => ({ computed_at: '2026-11-22T05:00:00Z' }))
    render(
      <ApiProvider client={stub({})}>
        <Harness fetchForecast={fetchForecast} delayMs={3000} />
      </ApiProvider>,
    )
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10)
    })
    expect(fetchForecast).toHaveBeenCalledTimes(1)
    vi.setSystemTime(new Date('2026-11-22T06:00:00Z'))
    act(() => screen.getByRole('button', { name: /^ghi$/ }).click())
    // từng bước 3 giây, mỗi bước một lần act để React kịp vẽ lại (và chạy effect hẹn lần hỏi kế tiếp)
    for (let t = 0; t < FORECAST_FOLLOW_UP_MS + 10_000; t += 3000) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000)
      })
    }
    const n = fetchForecast.mock.calls.length
    expect(n).toBeGreaterThan(5)
    expect(n).toBeLessThanOrEqual(1 + 1 + FORECAST_FOLLOW_UP_MS / 3000 + 1)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000)
    })
    expect(fetchForecast.mock.calls.length).toBe(n)
  })

  it('báo stale: thử lại vài lần trong cửa sổ ngắn rồi thôi', async () => {
    let n = 0
    const fetchForecast = vi.fn(async (): Promise<Fc> => ({ computed_at: '2026-11-22T05:00:00Z', stale: ++n < 3 }))
    render(
      <ApiProvider client={stub({})}>
        <Harness fetchForecast={fetchForecast} />
      </ApiProvider>,
    )
    await waitFor(() => expect(fetchForecast).toHaveBeenCalledTimes(3))
    await new Promise((r) => setTimeout(r, 80))
    expect(fetchForecast).toHaveBeenCalledTimes(3)
  })
})

describe('usePreview (POST /confirmations để xem trước)', () => {
  function PreviewHarness({ params }: { params: Record<string, unknown> | null }) {
    const p = usePreview('move_between_jars', params)
    return (
      <div>
        <p data-testid="status">{p.status}</p>
        <p data-testid="summary">{p.preview?.summary ?? ''}</p>
        <p data-testid="error">{p.error?.code ?? ''}</p>
      </div>
    )
  }
  const ok = (summary: string) => ({ confirm_token: 'a.b', expires_at: '2026-12-10T03:02:00Z', ttl_seconds: 120, tool: 'move_between_jars' as const, params: {}, params_hash: 'a'.repeat(64), preview: { summary, changes: [{ label: 'x', after: 'y' }] } })

  it('không gọi khi chưa đủ dữ liệu; gọi khi có tham số; gọi lại khi tham số đổi; lỗi nghiệp vụ trả về để báo sớm', async () => {
    const createConfirmation = vi.fn(async (req: { params: Record<string, unknown> }) => {
      if (req.params.amount_vnd === 999) throw new ApiError('INSUFFICIENT_FUNDS', 422)
      return ok(`chuyển ${String(req.params.amount_vnd)}`)
    })
    const client = stub({ createConfirmation: createConfirmation as unknown as ApiClient['createConfirmation'] })
    const { rerender } = render(
      <ApiProvider client={client}>
        <PreviewHarness params={null} />
      </ApiProvider>,
    )
    expect(screen.getByTestId('status')).toHaveTextContent('idle')
    expect(createConfirmation).not.toHaveBeenCalled()

    rerender(
      <ApiProvider client={client}>
        <PreviewHarness params={{ amount_vnd: 100 }} />
      </ApiProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('summary')).toHaveTextContent('chuyển 100'))
    rerender(
      <ApiProvider client={client}>
        <PreviewHarness params={{ amount_vnd: 200 }} />
      </ApiProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('summary')).toHaveTextContent('chuyển 200'))
    rerender(
      <ApiProvider client={client}>
        <PreviewHarness params={{ amount_vnd: 999 }} />
      </ApiProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('error')).toHaveTextContent('INSUFFICIENT_FUNDS'))
    expect(createConfirmation).toHaveBeenCalledTimes(3)
  })
})
