import { lazy, Suspense, useCallback, useMemo, useState, type ReactNode } from 'react'
import { Outlet, useLocation } from 'react-router'
import { useAuth } from '@/auth/AuthProvider'
import { ApiProvider } from '@/api/ApiProvider'
import { OverviewProvider } from '@/api/OverviewProvider'
import { createApiClient } from '@/api/client'
import { ChatProvider, useChat } from '@/chat/ChatProvider'
import { ChatLauncherContext, type ChatLauncher } from '@/chat/launcher'
import { HttpConversationRepository, NullConversationRepository } from '@/chat/repository'
import { useConfig } from '@/AppContext'
import { TabBar } from './TabBar'

// Sheet chat (Drawer + registry khối) tách chunk riêng: tải ngay sau lần vẽ đầu, không chặn Tổng quan.
const ChatSheet = lazy(() => import('@/chat/ChatSheet').then((m) => ({ default: m.ChatSheet })))

// Màn toàn khung (luồng chuyển tiền, onboarding, form...) không có tab bar, theo Figma T1–T5, O1–O3.
const NO_TABBAR = /^\/(onboarding|transfer|activity|obligations|income|ingest|move|salary|jars\/edit)(\/|$)/

function Frame({ children }: { children: ReactNode }) {
  const chat = useChat()
  const location = useLocation()
  const [chatOpen, setChatOpen] = useState(false)
  const launcher = useMemo<ChatLauncher>(
    () => ({
      open: (prompt) => {
        setChatOpen(true)
        // "Hỏi vì sao" mở chat và gửi luôn câu hỏi về hũ đó (câu do server hoặc màn hình dựng, không phải đáp án dựng sẵn).
        if (prompt) void chat.send(prompt)
      },
      close: () => setChatOpen(false),
    }),
    [chat],
  )
  const close = useCallback((o: boolean) => setChatOpen(o), [])
  const showTabBar = !NO_TABBAR.test(location.pathname)

  return (
    <ChatLauncherContext.Provider value={launcher}>
      <main className="phone-scroll" id="main">
        {children}
      </main>
      {showTabBar && <TabBar onOpenChat={() => setChatOpen(true)} chatOpen={chatOpen} />}
      <Suspense fallback={null}>
        <ChatSheet open={chatOpen} onOpenChange={close} />
      </Suspense>
    </ChatLauncherContext.Provider>
  )
}

/** Khung sau đăng nhập: nội dung cuộn được, tab bar 5 mục (ẩn ở màn toàn khung), sheet chat; các provider dùng chung dữ liệu. */
export function AppShell() {
  const config = useConfig()
  const { getAccessToken } = useAuth()

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
      <OverviewProvider>
        <ChatProvider agentUrl={config.agentUrl} repository={repository}>
          <Frame>
            <Outlet />
          </Frame>
        </ChatProvider>
      </OverviewProvider>
    </ApiProvider>
  )
}
