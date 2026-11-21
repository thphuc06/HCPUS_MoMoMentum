import { useState } from 'react'
import { Send, Sparkles, X } from 'lucide-react'
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerTitle,
} from '@/components/ui/drawer'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Message, MessageContent } from '@/components/ui/message'
import { Bubble, BubbleContent } from '@/components/ui/bubble'
import {
  MessageScroller,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from '@/components/ui/message-scroller'
import { Trace, TraceIcon, TraceLine, TraceTitle } from '@/components/ui/trace'
import { BlockRenderer } from '@/blocks/registry'
import { useYofinaChat, type ChatItem } from '@/agui/useYofinaChat'

const AGENT_URL = (import.meta.env.VITE_AGUI_URL as string | undefined) ?? 'http://localhost:8787/run'

const TOOL_LABEL: Record<string, string> = {
  'forecast.get_forecast': 'Đang đọc dự báo hũ Ăn uống…',
  'affordability.check': 'Đang kiểm tra khả năng chi trả…',
}

function Item({ it }: { it: ChatItem }) {
  switch (it.kind) {
    case 'user':
      return (
        <Message align="end">
          <MessageContent>
            <Bubble variant="default" align="end" className="max-w-[85%]">
              <BubbleContent className="rounded-3xl rounded-br-lg px-4 py-2.5 text-[15px]">{it.text}</BubbleContent>
            </Bubble>
          </MessageContent>
        </Message>
      )
    case 'text':
      return (
        <Message>
          <MessageContent>
            <Bubble variant="ghost" className="max-w-full">
              <BubbleContent className="text-[15px] leading-relaxed" data-testid="assistant-text">
                {it.text}
                {!it.done && <span className="ml-0.5 inline-block h-4 w-0.5 translate-y-0.5 animate-pulse bg-primary" aria-hidden />}
              </BubbleContent>
            </Bubble>
          </MessageContent>
        </Message>
      )
    case 'tool':
      return (
        <div className="space-y-2" data-testid="tool-item" data-status={it.status}>
          <Trace>
            <TraceLine status={it.status === 'running' ? 'running' : undefined}>
              <TraceIcon>
                <Sparkles />
              </TraceIcon>
              <TraceTitle>{it.status === 'running' ? (TOOL_LABEL[it.name] ?? `Đang chạy ${it.name}…`) : `Đã chạy ${it.name}`}</TraceTitle>
            </TraceLine>
          </Trace>
          {it.status === 'running' && it.name.startsWith('forecast') && (
            // khung skeleton đúng kích thước khối thật để không nhảy bố cục
            <Skeleton data-testid="block-skeleton" className="h-[318px] w-full rounded-3xl" />
          )}
        </div>
      )
    case 'block':
      return (
        <div data-testid="block-item" data-via={it.via}>
          <BlockRenderer raw={it.raw} />
        </div>
      )
    case 'error':
      return <p className="rounded-2xl bg-short-soft px-3 py-2 text-[13px] text-short-ink">Lỗi: {it.text}</p>
  }
}

const SUGGESTIONS = ['Hũ Ăn uống có đủ tới lương không?', 'Nếu mua tai nghe 1,2 triệu thì sao?']

export function ChatSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { items, running, send } = useYofinaChat(AGENT_URL)
  const [text, setText] = useState('')
  const [snap, setSnap] = useState<number | string | null>(0.6)

  const submit = (t: string) => {
    const v = t.trim()
    if (!v || running) return
    setText('')
    setSnap(1)
    void send(v)
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange} snapPoints={[0.6, 1]} snapPoint={snap} onSnapPointChange={setSnap}>
      <DrawerContent className="mx-auto max-w-[430px] rounded-t-[28px] bg-background pb-[var(--drawer-snap-point-offset,0px)]" data-testid="chat-sheet">
        {/* với snapPoints popup bị dịch xuống: chừa đáy bằng phần bị dịch (biến CSS chỉ có trên chính popup, không kế thừa xuống con) */}
        <div className="flex min-h-0 flex-1 flex-col" >
        <div className="mx-auto mt-2 h-1.5 w-10 shrink-0 rounded-full bg-border" aria-hidden />
        <div className="flex items-center justify-between px-5 pb-2 pt-3">
          <div>
            <DrawerTitle className="text-[17px] font-bold">Hỏi Yofina</DrawerTitle>
            <DrawerDescription className="text-[12px]">Trợ lý AI · số liệu lấy từ công cụ, không do mô hình tự nghĩ</DrawerDescription>
          </div>
          <DrawerClose render={<Button variant="ghost" size="icon" aria-label="Đóng" className="size-10 rounded-full" />}>
            <X className="size-5" />
          </DrawerClose>
        </div>
        <MessageScrollerProvider>
          <MessageScroller className="min-h-0 flex-1">
            <MessageScrollerViewport className="px-4" style={{ overscrollBehavior: 'contain' }}>
              <MessageScrollerContent className="gap-4 pb-4 pt-2">
                {items.length === 0 && (
                  <div className="space-y-2 pt-2">
                    <p className="text-[14px] text-muted-foreground">Bạn có thể hỏi:</p>
                    <div className="flex flex-col gap-2">
                      {SUGGESTIONS.map((s) => (
                        <button
                          key={s}
                          type="button"
                          onClick={() => submit(s)}
                          className="rounded-2xl bg-secondary px-4 py-3 text-left text-[14px] font-semibold text-secondary-foreground active:scale-[0.98]"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {items.map((it) => (
                  <MessageScrollerItem key={`${it.kind}:${it.id}`} messageId={`${it.kind}:${it.id}`} className="-mx-1 px-1 py-1 -my-1">
                    <Item it={it} />
                  </MessageScrollerItem>
                ))}
              </MessageScrollerContent>
            </MessageScrollerViewport>
          </MessageScroller>
        </MessageScrollerProvider>
        <form
          className="flex shrink-0 items-center gap-2 border-t border-border/70 bg-popover px-4 pb-[max(12px,env(safe-area-inset-bottom))] pt-3"
          onSubmit={(e) => {
            e.preventDefault()
            submit(text)
          }}
        >
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Hỏi về hũ, khoản chi, kịch bản…"
            aria-label="Tin nhắn"
            className="h-12 flex-1 rounded-full px-5 text-[16px]"
          />
          <Button type="submit" size="icon" disabled={running || !text.trim()} aria-label="Gửi" className="size-12 rounded-full">
            <Send className="size-5" />
          </Button>
        </form>
        </div>
      </DrawerContent>
    </Drawer>
  )
}
