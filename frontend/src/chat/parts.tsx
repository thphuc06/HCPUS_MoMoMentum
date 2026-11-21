import { Check, Square, SendHorizontal } from 'lucide-react'
import { cn } from '@/lib/cn'
import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { toolLabel } from './errors'
import type { ChatItem } from './session'

// Figma UserBubble (10:238): bong bóng chủ đạo, bo 20, góc dưới phải nhỏ.
export function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p
        data-testid="user-bubble"
        className="max-w-[85%] rounded-[20px] rounded-br-md bg-brand px-4 py-2.5 text-body whitespace-pre-wrap text-white"
      >
        {text}
      </p>
    </div>
  )
}

// Figma AIMessage (10:242): chữ trực tiếp trên nền, không bong bóng. Con trỏ nhấp nháy khi còn chạy.
// `superseded`: lượt này có đề nghị đã được thực hiện, nên lời trước đó ("chưa chuyển gì, bấm xác nhận...") không còn
// đúng ở thời điểm hiện tại: làm mờ và ghi rõ đó là lời trước khi xác nhận (không sửa nội dung).
export function AIMessage({ text, done, superseded = false }: { text: string; done: boolean; superseded?: boolean }) {
  return (
    <div data-testid="assistant-message" data-superseded={superseded ? 'true' : undefined} className={cn(superseded && 'opacity-60')}>
      {superseded && <p className="mb-0.5 text-note font-semibold text-ink-2">Trước khi bạn xác nhận</p>}
      <p data-testid="assistant-text" className="text-body whitespace-pre-wrap text-ink">
        {text}
        {!done && <span aria-hidden className="ml-0.5 inline-block h-4 w-0.5 translate-y-0.5 animate-pulse bg-brand" />}
      </p>
    </div>
  )
}

type ToolItem = Extract<ChatItem, { kind: 'tool' }>

// Figma ToolProgress (10:75): thẻ "Yofina đang làm" với danh sách bước: xong (dấu tích), đang chạy (vòng quay).
export function ToolProgress({ tools }: { tools: readonly ToolItem[] }) {
  const running = tools.some((t) => t.status === 'running')
  return (
    <section aria-live="polite" data-testid="tool-progress" className="rounded-card bg-surface-2 p-4">
      <h3 className="text-small font-semibold text-ink-2">{running ? 'Yofina đang làm' : 'Yofina đã làm'}</h3>
      <ul className="mt-2 space-y-2">
        {tools.map((t) => (
          <li key={t.id} className="flex items-center gap-2.5 text-small text-ink" data-status={t.status}>
            {t.status === 'done' ? (
              <span className="grid size-5 shrink-0 place-items-center rounded-full bg-ok-bg text-ok-fg">
                <Check className="size-3.5" aria-hidden />
              </span>
            ) : (
              <span aria-hidden className="size-5 shrink-0 animate-spin rounded-full border-2 border-dashed border-brand" />
            )}
            <span>{toolLabel(t.name, t.status)}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

// Figma ChatInput (5:226): ô nhập dạng viên thuốc, nút gửi tròn chủ đạo; khi đang chạy thành nút Dừng.
export function ChatInput({
  running,
  onSend,
  onStop,
  disabled,
}: {
  running: boolean
  onSend: (text: string) => void
  onStop: () => void
  disabled?: boolean
}) {
  const [text, setText] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const v = text.trim()
    if (!v || running || disabled) return
    setText('')
    onSend(v)
  }
  return (
    <form
      onSubmit={submit}
      className="flex shrink-0 items-center gap-2 border-t border-line bg-background px-4 pt-3 pb-[max(12px,env(safe-area-inset-bottom))]"
    >
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Hỏi về các hũ của bạn…"
        aria-label="Tin nhắn"
        autoComplete="off"
        enterKeyHint="send"
        className={cn('h-13 flex-1 rounded-full px-5')}
      />
      {running ? (
        <Button type="button" size="icon-lg" variant="soft" aria-label="Dừng" onClick={onStop}>
          <Square className="size-5 fill-current" aria-hidden />
        </Button>
      ) : (
        <Button type="submit" size="icon-lg" aria-label="Gửi" disabled={!text.trim() || disabled}>
          <SendHorizontal className="size-5" aria-hidden />
        </Button>
      )}
    </form>
  )
}
