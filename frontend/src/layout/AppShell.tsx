import { lazy, Suspense, useMemo, useState } from 'react'
import { Outlet } from 'react-router'
import { useAuth } from '@/auth/AuthProvider'
import { ApiProvider, JarsProvider } from '@/api/ApiProvider'
import { createApiClient } from '@/api/client'
import { ChatProvider } from '@/chat/ChatProvider'
import { HttpConversationRepository, NullConversationRepository } from '@/chat/repository'
import { useConfig } from '@/AppContext'
import { TabBar } from './TabBar'

// Sheet chat (Drawer + registry khối) tách chunk riêng: tải ngay sau lần vẽ đầu, không chặn Tổng quan.
const ChatSheet = lazy(() => import('@/chat/ChatSheet').then((m) => ({ default: m.ChatSheet })))

/** Khung sau đăng nhập: nội dung tab cuộn được, tab bar 5 mục, sheet chat; các provider dùng chung dữ liệu. */
export function AppShell() {
  const config = useConfig()
  const { getAccessToken } = useAuth()
  const [chatOpen, setChatOpen] = useState(false)

  const apiClient = useMemo(() => createApiClient({ baseUrl: config.apiUrl, getAccessToken }), [config.apiUrl, getAccessToken])
  const repository = useMemo(
    () =>
      config.replayEnabled
        ? new HttpConversationRepository({ baseUrl: config.apiUrl, getAccessToken })
        : new NullConversationRepository(),
    [config.replayEnabled, config.apiUrl, getAccessToken],
  )

  return (
    <ApiProvider client={apiClient}>
      <JarsProvider>
        <ChatProvider agentUrl={config.agentUrl} repository={repository}>
          <main className="phone-scroll" id="main">
            <Outlet />
          </main>
          <TabBar onOpenChat={() => setChatOpen(true)} chatOpen={chatOpen} />
          <Suspense fallback={null}>
            <ChatSheet open={chatOpen} onOpenChange={setChatOpen} />
          </Suspense>
        </ChatProvider>
      </JarsProvider>
    </ApiProvider>
  )
}
