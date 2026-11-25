import { useEffect, useRef, type ReactNode } from 'react'
import { BlockRenderer } from '@/blocks/registry'
import { blockSchemas } from '@/contracts/blocks'
import { Notice } from '@/components/Notice'
import { AiChip } from '@/components/StatusChip'
import { AIMessage, ToolProgress, UserBubble } from './parts'
import type { ChatItem } from './session'

type ToolItem = Extract<ChatItem, { kind: 'tool' }>

/** Gộp các mục công cụ liền nhau thành một thẻ ToolProgress. */
function groupItems(items: readonly ChatItem[]): Array<ChatItem | { kind: 'tools'; id: string; tools: ToolItem[] }> {
  const out: Array<ChatItem | { kind: 'tools'; id: string; tools: ToolItem[] }> = []
  for (const it of items) {
    if (it.kind === 'tool') {
      const last = out[out.length - 1]
      if (last && last.kind === 'tools') last.tools.push(it)
      else out.push({ kind: 'tools', id: `tools-${it.id}`, tools: [it] })
    } else out.push(it)
  }
  return out
}

/**
 * Mã các tin nhắn của agent thuộc một lượt có đề nghị đã thực hiện. Một "lượt" là đoạn từ một tin của người dùng
 * tới tin kế tiếp của người dùng. Xử lý ở tầng hiển thị, theo trạng thái của khối (`resolved`), không theo nội dung chữ.
 */
export function supersededAssistantIds(items: readonly ChatItem[]): Set<string> {
  const out = new Set<string>()
  let segment: ChatItem[] = []
  const flush = () => {
    if (segment.some((i) => i.kind === 'block' && i.resolved)) {
      for (const i of segment) if (i.kind === 'assistant') out.add(i.id)
    }
    segment = []
  }
  for (const it of items) {
    if (it.kind === 'user') flush()
    segment.push(it)
  }
  flush()
  return out
}

/**
 * Id các khối xác nhận mà một khối `options` tham chiếu (`options.action.block_id`). Khối xác nhận được agent phát sẵn trong
 * lượt nhưng chỉ hiện sau khi người dùng "Chọn" phương án tương ứng (hợp đồng phase 3, quyết định số 11).
 */
export function referencedConfirmIds(items: readonly ChatItem[]): Set<string> {
  const out = new Set<string>()
  for (const it of items) {
    if (it.kind !== 'block') continue
    const parsed = blockSchemas.options.safeParse(it.raw)
    if (!parsed.success) continue
    for (const o of parsed.data.data.options) if (o.action) out.add(o.action.block_id)
  }
  return out
}

/** Id các khối đã có tin nhắn mới của người dùng đứng sau (khối hỏi lại không còn bấm được). */
function staleBlockIds(items: readonly ChatItem[]): Set<string> {
  const out = new Set<string>()
  let lastUser = -1
  items.forEach((it, i) => {
    if (it.kind === 'user') lastUser = i
  })
  items.forEach((it, i) => {
    if (it.kind === 'block' && i < lastUser) out.add(it.id)
  })
  return out
}

export function MessageList({
  items,
  running,
  onRetry,
  revealed,
}: {
  items: readonly ChatItem[]
  running: boolean
  onRetry: () => void
  revealed?: ReadonlySet<string>
}) {
  const viewport = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  const shown = revealed ?? EMPTY
  const lastRevealed = useRef<number>(0)

  // "Chọn" một phương án: cuộn tới khối xác nhận vừa hiện.
  useEffect(() => {
    if (shown.size === lastRevealed.current) return
    lastRevealed.current = shown.size
    const id = [...shown].pop()
    if (!id) return
    const raf = requestAnimationFrame(() => {
      const el = viewport.current?.querySelector(`[data-block-id="${id.replace(/["\\]/g, '')}"]`)
      if (el && 'scrollIntoView' in el) (el as HTMLElement).scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    })
    return () => cancelAnimationFrame(raf)
  }, [shown])

  // Tự cuộn xuống đáy khi có nội dung mới, trừ khi người dùng đã cuộn lên xem.
  useEffect(() => {
    const el = viewport.current
    if (!el) return
    const last = items[items.length - 1]
    // Tin mới của người dùng và thông báo lỗi luôn được cuộn tới; còn lại chỉ khi người dùng đang ở gần đáy.
    if (last?.kind === 'user' || last?.kind === 'notice') stick.current = true
    if (!stick.current) return
    const toBottom = () => {
      el.scrollTop = el.scrollHeight
    }
    toBottom()
    const raf = requestAnimationFrame(toBottom) // sau khi bố cục (khối, ảnh) ổn định
    return () => cancelAnimationFrame(raf)
  }, [items])

  const grouped = groupItems(items)
  const superseded = supersededAssistantIds(items)
  const referenced = referencedConfirmIds(items)
  const stale = staleBlockIds(items)
  const modelStepGroup = running ? modelStepGroupId(grouped) : undefined
  const rows: ReactNode[] = grouped.map((g, idx) => {
    const next = grouped[idx + 1]
    switch (g.kind) {
      case 'user':
        return <UserBubble key={g.id} text={g.text} />
      case 'assistant': {
        const endOfAnswer = g.done && (!next || next.kind === 'user') && !running
        return (
          <div key={g.id} className="space-y-2">
            <AIMessage text={g.text} done={g.done} superseded={superseded.has(g.id)} />
            {endOfAnswer && <AiChip>Do AI tạo</AiChip>}
          </div>
        )
      }
      case 'tools':
        return <ToolProgress key={g.id} tools={g.tools} modelStepRunning={g.id === modelStepGroup} />
      case 'block':
        // Khối xác nhận do một phương án tham chiếu: ẩn cho tới khi chọn phương án (đã thực hiện, hủy hay hết hạn thì luôn hiện).
        if (referenced.has(g.id) && !shown.has(g.id) && !g.resolved && !g.ui) return null
        return (
          <div key={g.id} data-testid="block-item" data-block-id={g.id}>
            <BlockRenderer raw={g.raw} blockId={g.id} ui={g.ui} doneAt={g.doneAt} stale={stale.has(g.id)} />
          </div>
        )
      case 'notice':
        return (
          <Notice
            key={g.id}
            kind="error"
            title={g.title}
            message={g.message}
            code={g.code}
            onRetry={g.retry && g.id === lastNoticeId(items) && !running ? onRetry : undefined}
          />
        )
      default:
        return null
    }
  })

  return (
    <div
      ref={viewport}
      onScroll={(e) => {
        const el = e.currentTarget
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
      }}
      className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4"
      data-testid="message-viewport"
    >
      <div className="flex flex-col gap-4 pt-2 pb-4">{rows}</div>
    </div>
  )
}

const EMPTY: ReadonlySet<string> = new Set()

/**
 * Lượt đang chạy mà mọi công cụ của thẻ công cụ cuối (sau tin cuối của người dùng) đã xong: bước model (Analyst, người viết)
 * đang chạy, chưa có event riêng nào báo. Trả id của thẻ đó; gọi chỉ khi lượt đang chạy (chưa RUN_FINISHED).
 */
function modelStepGroupId(grouped: ReturnType<typeof groupItems>): string | undefined {
  for (let i = grouped.length - 1; i >= 0; i--) {
    const g = grouped[i]!
    if (g.kind === 'user') return undefined
    if (g.kind === 'tools') return g.tools.every((t) => t.status === 'done') ? g.id : undefined
  }
  return undefined
}

function lastNoticeId(items: readonly ChatItem[]): string | undefined {
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i]!
    if (it.kind === 'notice') return it.id
  }
  return undefined
}
