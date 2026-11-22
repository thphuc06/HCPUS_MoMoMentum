import { createContext, useContext } from 'react'

/** Thao tác khối UI được phép làm lên hội thoại (cung cấp bởi ChatProvider). */
export type ChatActions = {
  /**
   * Thay khối `id` bằng khối mới ở đúng vị trí (confirm -> receipt). `fresh`: vừa thực hiện xong trong phiên này nên còn
   * trong cửa sổ Hoàn tác (biên nhận dựng lại từ server sau khi tải trang thì không còn Hoàn tác).
   */
  replaceBlock: (id: string, raw: unknown, newId?: string, opts?: { fresh?: boolean; undone?: boolean }) => void
  markBlock: (id: string, ui: 'cancelled') => void
  /** Thêm dòng hệ thống vào lịch sử gửi agent ở lượt sau (không hiện cho người dùng). Cùng `key` thì chỉ thêm một lần. */
  addSystemNote: (text: string, key?: string) => void
  /** Id cuộc hội thoại hiện tại: gửi kèm khi xác nhận để server gắn biên nhận vào đúng đề nghị. */
  getConversationId: () => string
  /** Đồng bộ lại trạng thái các đề nghị từ server (khi gặp ALREADY_APPLIED). Không làm gì nếu đang chạy lượt. */
  reloadConversation: () => Promise<void>
  /** Gửi một tin nhắn như người dùng gõ (chip gợi ý, chip trả lời `clarify`). Không làm gì nếu đang chạy lượt. */
  ask: (text: string) => void
  /** "Thử lại" của `notice` có `retryable`: chạy lại lượt vừa rồi với cùng lịch sử. */
  retryLast: () => void
  /** Hỏi lại đúng câu cuối của người dùng (đề nghị hết hạn: hỏi lại để có đề nghị mới). */
  askAgain: () => void
  /** "Chọn" một phương án: hiện khối xác nhận mà phương án tham chiếu (khối đã phát sẵn trong lượt, đang ẩn). */
  revealBlock: (id: string) => void
  /** Cửa sổ Hoàn tác, tính bằng mili giây (cấu hình `undoWindowSeconds`). */
  undoWindowMs: number
}

export const ChatActionsContext = createContext<ChatActions | null>(null)

export function useChatActions(): ChatActions {
  const c = useContext(ChatActionsContext)
  if (!c) throw new Error('useChatActions phải nằm trong ChatProvider')
  return c
}

/** Như `useChatActions` nhưng trả `null` ngoài ChatProvider (khối vẽ ở màn hình, không có hội thoại). */
export function useOptionalChatActions(): ChatActions | null {
  return useContext(ChatActionsContext)
}
