import { useEffect, useRef, type ReactNode } from 'react'
import { BlockRenderer } from '@/blocks/registry'
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

export function MessageList({ items, running, onRetry }: { items: readonly ChatItem[]; running: boolean; onRetry: () => void }) {
  const viewport = useRef<HTMLDivElement>(null)
  const stick = useRef(true)

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
  const rows: ReactNode[] = grouped.map((g, idx) => {
    const next = grouped[idx + 1]
    switch (g.kind) {
      case 'user':
        return <UserBubble key={g.id} text={g.text} />
      case 'assistant': {
        const endOfAnswer = g.done && (!next || next.kind === 'user') && !running
        return (
          <div key={g.id} className="space-y-2">
            <AIMessage text={g.text} done={g.done} />
            {endOfAnswer && <AiChip>Do AI tạo</AiChip>}
          </div>
        )
      }
      case 'tools':
        return <ToolProgress key={g.id} tools={g.tools} />
      case 'block':
        return (
          <div key={g.id} data-testid="block-item">
            <BlockRenderer raw={g.raw} blockId={g.id} ui={g.ui} />
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

function lastNoticeId(items: readonly ChatItem[]): string | undefined {
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i]!
    if (it.kind === 'notice') return it.id
  }
  return undefined
}
