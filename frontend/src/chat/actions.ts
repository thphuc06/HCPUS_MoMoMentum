import { createContext, useContext } from 'react'

/** Thao tác khối UI được phép làm lên hội thoại (cung cấp bởi ChatProvider). */
export type ChatActions = {
  /** Thay khối `id` bằng khối mới ở đúng vị trí (confirm -> receipt). */
  replaceBlock: (id: string, raw: unknown, newId?: string) => void
  markBlock: (id: string, ui: 'cancelled') => void
  /** Thêm dòng hệ thống vào lịch sử gửi agent ở lượt sau (không hiện cho người dùng). Cùng `key` thì chỉ thêm một lần. */
  addSystemNote: (text: string, key?: string) => void
  /** Id cuộc hội thoại hiện tại: gửi kèm khi xác nhận để server gắn biên nhận vào đúng đề nghị. */
  getConversationId: () => string
  /** Đồng bộ lại trạng thái các đề nghị từ server (khi gặp ALREADY_APPLIED). Không làm gì nếu đang chạy lượt. */
  reloadConversation: () => Promise<void>
}

export const ChatActionsContext = createContext<ChatActions | null>(null)

export function useChatActions(): ChatActions {
  const c = useContext(ChatActionsContext)
  if (!c) throw new Error('useChatActions phải nằm trong ChatProvider')
  return c
}
