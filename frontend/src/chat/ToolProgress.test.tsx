import { act, render, screen, within } from '@testing-library/react'
import { useSyncExternalStore } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { MessageList } from './MessageList'
import { ChatSession } from './session'
import { Providers, fakeApi } from '@/test/helpers'
import { runFinished, runStarted, sseBody, sseResponse, textMessage, toolCall, type Ev } from '@/test/sse'

// Thẻ tiến độ trong lúc bước model (Analyst, người viết) chạy sau các công cụ: chưa được ghi "đã làm" trước RUN_FINISHED (#12).
// Đi qua đúng đường thật: luồng AG-UI -> ChatSession -> MessageList.

const CONVERSATION = '11111111-2222-4333-8444-555555555555'
const URL = 'https://runtime.example.invalid/invocations?qualifier=DEFAULT'

/** Luồng SSE mở, đẩy event từng đợt rồi đóng: mô phỏng khoảng chờ giữa công cụ cuối và RUN_FINISHED. */
function liveStream() {
  let ctrl!: ReadableStreamDefaultController<Uint8Array>
  const stream = new ReadableStream<Uint8Array>({ start: (c) => void (ctrl = c) })
  const enc = new TextEncoder()
  return {
    response: () => new Response(stream, { status: 200, headers: { 'content-type': 'text/event-stream' } }),
    push: (...evs: Ev[]) => act(async () => ctrl.enqueue(enc.encode(sseBody(evs)))),
    end: () => ctrl.close(),
  }
}

function setup(responses: Array<() => Response>) {
  const fetchImpl = vi.fn(async () => responses.shift()!()) as unknown as typeof fetch
  const session = new ChatSession({ agentUrl: URL, conversationId: CONVERSATION, getAccessToken: async () => 'tok', fetchImpl })
  function View() {
    const s = useSyncExternalStore(session.subscribe, session.getSnapshot)
    return <MessageList items={s.items} running={s.running} onRetry={vi.fn()} />
  }
  render(
    <Providers api={fakeApi()}>
      <View />
    </Providers>,
  )
  return session
}

describe('thẻ tiến độ khi công cụ đã xong mà lượt chưa kết thúc', () => {
  it('what-if: hiện bước "Đang cân các phương án…" tới RUN_FINISHED, rồi mới ghi "Yofina đã làm" (không đổi số dòng)', async () => {
    const live = liveStream()
    const session = setup([live.response])
    let done!: Promise<void>
    act(() => void (done = session.send('nếu mua tai nghe 1,2 triệu thì sao')))

    await live.push(runStarted(), ...toolCall('t1', 'ledger___get_jar_balances'), ...toolCall('t2', 'forecast___run_scenario'))
    const step = await screen.findByText('Đang cân các phương án…')
    const card = screen.getByTestId('tool-progress')
    expect(within(card).getByText('Yofina đang làm')).toBeInTheDocument()
    expect(within(card).queryByText('Yofina đã làm')).toBeNull()
    expect(within(card).getByText('Đã chạy kịch bản "nếu"')).toBeInTheDocument()
    expect(step.closest('li')).toHaveAttribute('data-status', 'running')
    const rowsWhileRunning = within(card).getAllByRole('listitem').length

    await live.push(...textMessage('m1', 'Mua được, nhưng hũ Thiết yếu sẽ sát.'), runFinished())
    await act(async () => {
      live.end()
      await done
    })

    expect(within(card).getByText('Yofina đã làm')).toBeInTheDocument()
    expect(within(card).queryByText('Đang cân các phương án…')).toBeNull()
    expect(within(card).getByText('Đã cân các phương án').closest('li')).toHaveAttribute('data-status', 'done')
    expect(within(card).getAllByRole('listitem')).toHaveLength(rowsWhileRunning) // không nhảy bố cục
  })

  it('lượt khác: thẻ của lượt trước vẫn "Yofina đã làm"; câu hỏi không phải what-if thì bước là "Đang soạn câu trả lời…"', async () => {
    const live = liveStream()
    const session = setup([
      () => sseResponse([runStarted(), ...toolCall('t1', 'forecast___run_scenario'), ...textMessage('m1', 'Mua được.'), runFinished()]),
      live.response,
    ])
    await act(() => session.send('nếu mua tai nghe thì sao'))
    let done!: Promise<void>
    act(() => void (done = session.send('số dư các hũ thế nào')))

    await live.push(runStarted(), ...toolCall('t1', 'ledger___get_jar_balances'))
    await screen.findByText('Đang soạn câu trả lời…')
    const [previous, current] = screen.getAllByTestId('tool-progress')
    expect(within(previous!).getByText('Yofina đã làm')).toBeInTheDocument()
    expect(within(previous!).getByText('Đã chạy kịch bản "nếu"')).toBeInTheDocument()
    expect(within(previous!).queryByText(/Đang /)).toBeNull()
    expect(within(current!).getByText('Yofina đang làm')).toBeInTheDocument()
    expect(within(current!).queryByText('Đang cân các phương án…')).toBeNull()

    await live.push(...textMessage('m2', 'Hũ Thiết yếu còn 1.200.000 ₫.'), runFinished())
    await act(async () => {
      live.end()
      await done
    })
    expect(within(current!).getByText('Yofina đã làm')).toBeInTheDocument()
    expect(within(current!).getByText('Đã soạn câu trả lời')).toBeInTheDocument()
  })
})