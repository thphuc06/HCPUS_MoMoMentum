import { createContext, useContext } from 'react'

/** Mở/đóng sheet chat từ màn hình khác (cung cấp bởi AppShell). `open(prompt)` mở chat và gửi câu hỏi ngay. */
export type ChatLauncher = {
  open: (prompt?: string) => void
  close: () => void
}

export const ChatLauncherContext = createContext<ChatLauncher>({ open: () => {}, close: () => {} })

export function useChatLauncher(): ChatLauncher {
  return useContext(ChatLauncherContext)
}
