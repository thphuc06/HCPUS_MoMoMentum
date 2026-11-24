import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { blockSchemas, type ReasoningBlock } from '@/contracts/blocks'
import { validBlock } from '@/test/fixtures'
import { COLLAPSE_AFTER_MS, ReasoningView, STEP_INTERVAL_MS } from './ReasoningView'
import { ChatSession } from './session'
import { sseResponse } from '@/test/sse'

const reduceMotion = (on: boolean) =>
  vi.stubGlobal('matchMedia', vi.fn((q: string) => ({ matches: on && q === '(prefers-reduced-motion: reduce)', addEventListener: vi.fn(), removeEventListener: vi.fn() })))

function block(name: string, change?: (raw: Record<string, any>) => void): ReasoningBlock {
  const raw = validBlock(name) as Record<string, any>
  change?.(raw)
  return blockSchemas.reasoning.parse(raw)
}

let seq = 0
const freshId = () => `reasoning:test-${++seq}-${Math.random().toString(36).slice(2)}`

beforeEach(() => sessionStorage.clear())
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('ReasoningView (luồng K: người tư vấn)', () => {
  it('giảm chuyển động: hiện ngay câu kết luận, các bước thu vào "Xem cách mình cân nhắc" (vẫn trong DOM, mở được)', async () => {
    reduceMotion(true)
    const b = block('reasoning.what_if')
    render(<ReasoningView block={b} blockId={freshId()} />)
    expect(screen.getByTestId('reasoning-conclusion')).toHaveTextContent(b.data.conclusion!.text)
    expect(screen.getByText('Có tính tới thói quen chi tiêu của bạn.')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Xem cách mình cân nhắc' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    const panel = document.getElementById(button.getAttribute('aria-controls')!)!
    expect(panel).toHaveAttribute('inert')
    // mọi bước có sẵn trong vùng thu gọn, kèm căn cứ bằng chữ (không chỉ dựa vào màu)
    expect(panel.querySelectorAll('li')).toHaveLength(b.data.steps.length)
    expect(within(panel).getAllByTestId('reasoning-basis')[0]).toHaveTextContent('Căn cứ: Kết quả mô phỏng · Các khoản đến hạn')
    await userEvent.setup().click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(panel).not.toHaveAttribute('inert')
  })

  it('có chuyển động: các bước hiện từng dòng, xong thì thu gọn thành kết luận', () => {
    reduceMotion(false)
    vi.useFakeTimers()
    const b = block('reasoning.what_if')
    const { container } = render(<ReasoningView block={b} blockId={freshId()} />)
    const live = container.querySelector('[aria-live="polite"]')!
    expect(live).toHaveAttribute('data-state', 'thinking')
    expect(screen.getByText('Mình đang cân nhắc')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
    expect(screen.getByText(b.data.steps[0]!.seen)).toBeInTheDocument()
    expect(screen.queryByText(b.data.steps[1]!.seen)).toBeNull()
    act(() => void vi.advanceTimersByTime(STEP_INTERVAL_MS))
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    act(() => void vi.advanceTimersByTime(STEP_INTERVAL_MS))
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    expect(screen.queryByTestId('reasoning-conclusion')).toBeNull()
    act(() => void vi.advanceTimersByTime(COLLAPSE_AFTER_MS))
    // cùng vùng aria-live (trình đọc màn hình đọc câu kết luận khi nó thay chỗ các bước)
    expect(container.querySelector('[aria-live="polite"]')).toBe(live)
    expect(live).toHaveAttribute('data-state', 'concluded')
    expect(screen.getByTestId('reasoning-conclusion')).toHaveTextContent(b.data.conclusion!.text)
    expect(screen.getByRole('button', { name: 'Xem cách mình cân nhắc' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('bản chưa xong được thay bằng bản cuối (cùng id): tiếp tục hiện dần rồi mới thu gọn', () => {
    reduceMotion(false)
    vi.useFakeTimers()
    const id = freshId()
    const partial = block('reasoning.dang_can_nhac')
    const { rerender } = render(<ReasoningView block={partial} blockId={id} />)
    act(() => void vi.advanceTimersByTime(COLLAPSE_AFTER_MS * 2))
    expect(screen.getByText('Mình đang cân nhắc')).toBeInTheDocument() // chưa xong thì không thu gọn
    const final = block('reasoning.what_if')
    rerender(<ReasoningView block={final} blockId={id} />)
    act(() => void vi.advanceTimersByTime(STEP_INTERVAL_MS))
    act(() => void vi.advanceTimersByTime(STEP_INTERVAL_MS))
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    act(() => void vi.advanceTimersByTime(COLLAPSE_AFTER_MS))
    expect(screen.getByTestId('reasoning-conclusion')).toBeInTheDocument()
  })

  it('đã thấy khối trong phiên (mở lại chat, tải lại trang): không chạy lại, hiện ngay trạng thái cuối', () => {
    reduceMotion(false)
    const id = freshId()
    const b = block('reasoning.what_if')
    const first = render(<ReasoningView block={b} blockId={id} />)
    first.unmount()
    render(<ReasoningView block={b} blockId={id} />)
    expect(screen.getByTestId('reasoning-conclusion')).toBeInTheDocument()
  })

  it('không có kết luận: các bước giữ nguyên trên màn, không có mục thu gọn', () => {
    reduceMotion(true)
    const b = block('reasoning.roadmap')
    render(<ReasoningView block={b} blockId={freshId()} />)
    expect(screen.getByText('Mình đã cân nhắc')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(b.data.steps.length)
    expect(screen.queryByRole('button', { name: 'Xem cách mình cân nhắc' })).toBeNull()
    expect(screen.getByRole('region', { name: 'Cách Yofina cân nhắc' })).toBeInTheDocument()
  })

  it('chỉ có kết luận (mọi bước bị agent bỏ): hiện câu kết luận, không nút mở', () => {
    reduceMotion(false)
    const b = block('reasoning.what_if', (raw) => {
      raw.data.steps = []
    })
    render(<ReasoningView block={b} blockId={freshId()} />)
    expect(screen.getByRole('region', { name: 'Lời khuyên của Yofina' })).toBeInTheDocument()
    expect(screen.queryByRole('button')).toBeNull()
  })
})

describe('ChatSession: khối reasoning phát dần', () => {
  it('các bản cùng id thay nhau tại chỗ, cuối cùng chỉ còn một mục là bản đã xong', async () => {
    const partial = validBlock('reasoning.dang_can_nhac')
    const final = validBlock('reasoning.what_if')
    const snap = (content: unknown) => ({ type: 'ACTIVITY_SNAPSHOT', messageId: (content as { id: string }).id, activityType: 'yofina.block', content, replace: true })
    const fetchImpl = vi.fn(async () =>
      sseResponse([
        { type: 'RUN_STARTED', threadId: 't', runId: 'r' },
        snap(partial),
        snap(final),
        { type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'assistant' },
        { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'Xong.' },
        { type: 'TEXT_MESSAGE_END', messageId: 'm1' },
        { type: 'RUN_FINISHED', threadId: 't', runId: 'r' },
      ]),
    )
    const s = new ChatSession({ agentUrl: 'https://agent.invalid', conversationId: 'c'.repeat(36), getAccessToken: async () => 'tok', fetchImpl: fetchImpl as never })
    await s.send('Nếu mua tai nghe thì sao')
    const blocks = s.getSnapshot().items.filter((i) => i.kind === 'block')
    expect(blocks).toHaveLength(1)
    expect((blocks[0] as { raw: { data: { complete: boolean } } }).raw.data.complete).toBe(true)
  })
})
