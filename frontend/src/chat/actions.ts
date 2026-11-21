import { createContext, useContext } from 'react'

/** Thao tác khối UI được phép làm lên hội thoại (cung cấp bởi ChatProvider). */
export type ChatActions = {
  /** Thay khối `id` bằng khối mới ở đúng vị trí (confirm -> receipt). */
  replaceBlock: (id: string, raw: unknown, newId?: string) => void
  markBlock: (id: string, ui: 'cancelled') => void
  /** Thêm dòng hệ thống vào lịch sử gửi agent ở lượt sau (không hiện cho người dùng). */
  addSystemNote: (text: string) => void
}

export const ChatActionsContext = createContext<ChatActions | null>(null)

export function useChatActions(): ChatActions {
  const c = useContext(ChatActionsContext)
  if (!c) throw new Error('useChatActions phải nằm trong ChatProvider')
  return c
}
