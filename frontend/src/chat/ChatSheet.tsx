import { useEffect, useState } from 'react'
import { Check, SquarePen, X } from 'lucide-react'
import { Drawer, DrawerClose, DrawerContent, DrawerDescription, DrawerTitle } from '@/components/ui/drawer'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { AiChip } from '@/components/StatusChip'
import { useAuth } from '@/auth/AuthProvider'
import { greetingNow } from '@/lib/format'
import { displayName } from '@/lib/user'
import { usePhoneFrame } from '@/layout/FrameContext'
import { useChat } from './ChatProvider'
import { MessageList } from './MessageList'
import { ChatInput } from './parts'

// Gợi ý là câu mẫu để bấm, không phải dữ liệu; phase 2: xem số dư, dự báo 30 ngày của hũ, chuyển giữa hai hũ.
const SUGGESTIONS = ['Số dư các hũ của mình', 'Hũ của mình còn trụ được bao lâu?', 'Chuyển tiền giữa hai hũ giúp mình']
const CAN_DO = ['Cho bạn xem số dư các hũ', 'Cho bạn xem dự báo 30 ngày của từng hũ', 'Chuyển tiền giữa hai hũ khi bạn xác nhận']
const CANNOT_DO = ['Tự chuyển tiền: mọi thay đổi số dư luôn cần bạn xác nhận', 'Tư vấn chọn cổ phiếu hay quỹ cụ thể']

function EmptyState({ onPick }: { onPick: (t: string) => void }) {
  const { session } = useAuth()
  const name = displayName(session?.email, session?.displayName)
  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 pb-4" data-testid="chat-empty">
      <h2 className="pt-2 text-section font-bold text-ink">
        {greetingNow()}
        {name ? `, ${name}` : ''}. Bạn muốn xem gì hôm nay?
      </h2>
      <section className="rounded-card bg-surface p-4 shadow-card">
        <h3 className="text-small font-semibold text-ok-fg">Mình làm được</h3>
        <ul className="mt-2 space-y-2">
          {CAN_DO.map((t) => (
            <li key={t} className="flex items-start gap-2.5 text-small text-ink">
              <Check className="mt-0.5 size-4 shrink-0 text-ok-fg" aria-hidden />
              {t}
            </li>
          ))}
        </ul>
        <h3 className="mt-4 text-small font-semibold text-ink-2">Mình chưa làm</h3>
        <ul className="mt-2 space-y-2">
          {CANNOT_DO.map((t) => (
            <li key={t} className="flex items-start gap-2.5 text-small text-ink-2">
              <X className="mt-0.5 size-4 shrink-0" aria-hidden />
              {t}
            </li>
          ))}
        </ul>
      </section>
      <p className="text-small font-semibold text-ink-2">Gợi ý</p>
      <div className="flex flex-col gap-2.5">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onPick(s)}
            className="min-h-12 rounded-card border border-line bg-surface px-4 py-3 text-left text-body font-semibold text-ink active:scale-[0.99]"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}

export function ChatSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const chat = useChat()
  const frame = usePhoneFrame()
  const [snap, setSnap] = useState<number | string | null>(0.6)
  const { items, running } = chat.snapshot

  // Làm nóng phiên Runtime ngay khi mở sheet để lượt đầu đỡ chịu cold start.
  useEffect(() => {
    if (open) chat.warmUp()
  }, [open, chat])

  const send = (text: string) => {
    setSnap(1) // sheet nở hết cỡ khi bắt đầu trò chuyện (vá của spike: snap points)
    void chat.send(text)
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange} snapPoints={[0.6, 1]} snapPoint={snap} onSnapPointChange={setSnap}>
      {/* Với snapPoints popup bị dịch xuống: chừa đáy bằng phần bị dịch. Biến CSS chỉ nằm trên popup, không kế thừa xuống con. */}
      <DrawerContent
        container={frame}
        data-testid="chat-sheet"
        className="rounded-t-sheet bg-background pb-[var(--drawer-snap-point-offset,0px)] shadow-sheet"
      >
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="mx-auto mt-2 h-1.5 w-10 shrink-0 rounded-full bg-line" aria-hidden />
          <header className="flex items-start justify-between gap-2 px-4 pt-2 pb-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <DrawerTitle className="text-section font-bold">Hỏi Yofina</DrawerTitle>
                <AiChip>Do AI tạo</AiChip>
              </div>
              <DrawerDescription className="mt-1 text-note text-ink-2">Số liệu lấy từ công cụ, không do mô hình tự nghĩ</DrawerDescription>
            </div>
            <div className="flex shrink-0 items-center">
              {items.length > 0 && !running && (
                <Button type="button" variant="ghost" size="icon" aria-label="Cuộc trò chuyện mới" onClick={chat.startNew}>
                  <SquarePen className="size-5" aria-hidden />
                </Button>
              )}
              <DrawerClose render={<Button variant="soft" size="icon" aria-label="Đóng" className="bg-surface-2 text-ink" />}>
                <X className="size-5" aria-hidden />
              </DrawerClose>
            </div>
          </header>

          {chat.hydrating ? (
            <div className="space-y-3 px-4 pt-2" aria-label="Đang tải hội thoại" role="status">
              <Skeleton className="h-10 w-2/3 rounded-2xl" />
              <Skeleton className="h-32 w-full rounded-card" />
            </div>
          ) : items.length === 0 ? (
            <EmptyState onPick={send} />
          ) : (
            <MessageList items={items} running={running} onRetry={() => void chat.retry()} />
          )}
          <ChatInput running={running} onSend={send} onStop={chat.stop} disabled={chat.hydrating} />
        </div>
      </DrawerContent>
    </Drawer>
  )
}
