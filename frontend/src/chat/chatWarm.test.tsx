import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { config, isWarmup, mountApp, restDefault, runCalls, type Call } from '@/test/mountApp'
import { runError, runFinished, runStarted, sseBody, sseResponse, textMessage } from '@/test/sse'

// Lỗi 409 SESSION_BUSY ở tin đầu tiên sau khi mở chat (#11): mở sheet làm nóng phiên; tin gửi ngay sau đó phải đợi lượt làm
// nóng xong rồi mới đi. Runtime giả ở mức fetch: như Runtime thật, nó trả 409 nếu nhận lượt chat khi lượt làm nóng còn chạy.

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

describe('chat: tin đầu tiên khi lượt làm nóng còn chạy', () => {
  it('mở chat rồi gửi ngay: yêu cầu gửi tin chỉ đi sau khi làm nóng xong, câu trả lời hiện, không có lỗi', async () => {
    let releaseWarmup!: () => void
    const warmupGate = new Promise<void>((r) => (releaseWarmup = r))
    let warming = false
    const order: string[] = []
    const { calls } = mountApp(async (url, init) => {
      if (url === config.agentUrl && JSON.parse(String(init.body)).forwardedProps?.warmup) {
        warming = true
        order.push('warmup:start')
        await warmupGate
        warming = false
        order.push('warmup:end')
        return sseResponse([runStarted(), runFinished()])
      }
      if (url === config.agentUrl) {
        order.push('chat')
        if (warming) return new Response(sseBody([runError('SESSION_BUSY')]), { status: 409, headers: { 'content-type': 'text/event-stream' } })
        return sseResponse([runStarted(), ...textMessage('m1', 'Chào Minh.'), runFinished()])
      }
      return restDefault(url)
    })
    const user = userEvent.setup()
    await screen.findByTestId('balance-total')
    await user.click(screen.getByRole('button', { name: /Hỏi Yofina/ }))
    const sheet = await screen.findByTestId('chat-sheet')
    await waitFor(() => expect(calls.some(isWarmup)).toBe(true))
    await user.type(within(sheet).getByLabelText('Tin nhắn'), 'xin chào')
    await user.click(within(sheet).getByRole('button', { name: 'Gửi' }))

    await new Promise((r) => setTimeout(r, 100))
    expect(runCalls(calls)).toHaveLength(0) // còn chờ làm nóng
    expect(within(sheet).getByRole('button', { name: 'Dừng' })).toBeInTheDocument() // trạng thái đang gửi như thường
    expect(within(sheet).queryByRole('alert')).toBeNull()

    releaseWarmup()
    await within(sheet).findByText('Chào Minh.')
    expect(order).toEqual(['warmup:start', 'warmup:end', 'chat'])
    expect(runCalls(calls)).toHaveLength(1)
    expect(calls.filter((c: Call) => isWarmup(c))).toHaveLength(1)
    expect(within(sheet).queryByText('Yofina đang bận')).toBeNull()
  })
})
