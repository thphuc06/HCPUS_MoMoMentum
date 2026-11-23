import { createElement, type ReactNode } from 'react'
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiProvider } from '@/api/ApiProvider'
import type { ApiClient } from '@/api/client'
import { ApiError } from '@/api/errors'
import { RoadmapJob } from '@/api/roadmapSchemas'
import { restFixture } from '@/test/fixtures'
import { fakeApi } from '@/test/helpers'
import { useRoadmapJob } from './useRoadmapJob'

const timing = { delayMs: 100, timeoutMs: 1_000 }
const queued = RoadmapJob.parse(restFixture('RoadmapJob.queued'))
const running = RoadmapJob.parse(restFixture('RoadmapJob.running'))
const done = RoadmapJob.parse(restFixture('RoadmapJob.done'))
const failed = RoadmapJob.parse(restFixture('RoadmapJob.failed'))

function mount(getRoadmapJob: ApiClient['getRoadmapJob']) {
  const client = fakeApi({ getRoadmapJob })
  const wrapper = ({ children }: { children: ReactNode }) => createElement(ApiProvider, { client, children })
  return renderHook(() => useRoadmapJob(queued, timing), { wrapper })
}

async function advance(ms = timing.delayMs) {
  await act(async () => vi.advanceTimersByTimeAsync(ms))
}

describe('polling job lộ trình', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it.each([done, failed])('dừng khi job ở trạng thái $status', async (terminal) => {
    const get = vi.fn<ApiClient['getRoadmapJob']>().mockResolvedValueOnce(running).mockResolvedValueOnce(terminal)
    const { result } = mount(get)
    expect(result.current.job).toEqual(queued)
    await advance()
    expect(result.current.job).toEqual(running)
    await advance()
    expect(result.current.job).toEqual(terminal)
    expect(result.current.polling).toBe(false)
    await advance(timing.timeoutMs)
    expect(get.mock.calls).toEqual([[queued.job_id], [queued.job_id]])
  })

  it('dừng khi rời trang dù đang có yêu cầu chưa trả về', async () => {
    let resolve!: (job: RoadmapJob) => void
    const get = vi.fn(() => new Promise<RoadmapJob>((r) => { resolve = r }))
    const { unmount } = mount(get)
    await advance()
    unmount()
    await act(async () => { resolve(running) })
    await advance(timing.timeoutMs)
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('dừng đúng trần chờ và cho phép hỏi lại', async () => {
    const get = vi.fn<ApiClient['getRoadmapJob']>()
      .mockRejectedValueOnce(new ApiError('NETWORK', 0))
      .mockImplementationOnce(() => new Promise(() => {}))
      .mockResolvedValueOnce(done)
    const { result } = mount(get)
    await advance(timing.timeoutMs)
    expect(result.current.timedOut).toBe(true)
    expect(result.current.polling).toBe(false)
    expect(get).toHaveBeenCalledTimes(2)
    act(() => result.current.retry())
    await advance()
    expect(result.current.job).toEqual(done)
  })
})
