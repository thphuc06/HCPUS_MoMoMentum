import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
import { useOptionalOverview } from '@/api/OverviewProvider'
import { useAuth } from '@/auth/AuthProvider'
import { newConversationId } from '@/lib/ids'
import { ChatActionsContext, type ChatActions } from './actions'
import {
  clearConversationId,
  loadConversationId,
  saveConversationId,
  type ConversationRepository,
} from './repository'
import { ChatSession, type ChatSnapshot } from './session'
import { walletContext, type AgentContext } from './walletContext'

export type ChatContextValue = {
  snapshot: ChatSnapshot
  hydrating: boolean
  /** Lỗi khi nạp lại hội thoại từ server (không chặn chat). */
  replayFailed: boolean
  send: (text: string) => Promise<void>
  retry: () => Promise<void>
  stop: () => void
  startNew: () => void
  /** Làm nóng phiên Runtime (gọi một lần khi mở sheet; không làm gì nếu chưa cấu hình URL). */
  warmUp: () => void
}

const ChatContext = createContext<ChatContextValue | null>(null)

export type ChatProviderProps = {
  agentUrl: string
  repository: ConversationRepository
  fetchImpl?: typeof fetch
  /** Làm nóng phiên khi mở sheet (mặc định bật; cấu hình `VITE_CHAT_WARMUP=0` để tắt). */
  warmupEnabled?: boolean
  /** Cửa sổ Hoàn tác (ms), mặc định 30 giây. */
  undoWindowMs?: number
  children: ReactNode
}

export function ChatProvider({ agentUrl, repository, fetchImpl, warmupEnabled = true, undoWindowMs = 30_000, children }: ChatProviderProps) {
  const { session: auth, getAccessToken } = useAuth()
  const userKey = auth?.email ?? 'anonymous'
  // Danh sách hũ của ví từ GET /overview (đã tải cho các màn hình) gửi kèm mỗi lượt chat: đọc lúc gửi qua ref, phiên chat không tạo lại.
  const overview = useOptionalOverview()
  const overviewRef = useRef(overview)
  overviewRef.current = overview
  const getContext = useCallback((): AgentContext[] => {
    const wallet = walletContext(overviewRef.current)
    return wallet ? [wallet] : []
  }, [])

  // Một ChatSession cho mỗi người dùng; id hội thoại (cũng là session id của Runtime) nhớ ở trình duyệt, khối thì không.
  const session = useMemo(() => {
    let id = loadConversationId(userKey)
    if (!id) {
      id = newConversationId()
      saveConversationId(userKey, id)
    }
    return new ChatSession({ agentUrl, conversationId: id, getAccessToken, fetchImpl, getContext })
  }, [agentUrl, userKey, getAccessToken, fetchImpl, getContext])

  const snapshot = useSyncExternalStore(session.subscribe, session.getSnapshot)
  const [hydrating, setHydrating] = useState(true)
  const [replayFailed, setReplayFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setHydrating(true)
    setReplayFailed(false)
    repository
      .load(session.getSnapshot().conversationId)
      .then((turns) => {
        // Chỉ nạp khi người dùng chưa kịp gõ gì (tránh ghi đè hội thoại đang chạy).
        if (!cancelled && turns.length > 0 && session.getSnapshot().items.length === 0) session.hydrate(turns)
      })
      .catch(() => {
        if (!cancelled) setReplayFailed(true)
      })
      .finally(() => {
        if (!cancelled) setHydrating(false)
      })
    return () => {
      cancelled = true
    }
  }, [session, repository])

  const warmed = useRef<string | null>(null)
  const warmUp = useCallback(() => {
    if (!warmupEnabled) return
    const id = session.getSnapshot().conversationId
    if (warmed.current === id) return
    warmed.current = id
    // ChatSession giữ promise của lượt làm nóng: tin gửi trong lúc đó chờ nó xong (tránh 409 SESSION_BUSY).
    void session.warmUp()
  }, [session, warmupEnabled])

  const startNew = useCallback(() => {
    clearConversationId(userKey)
    const id = newConversationId()
    saveConversationId(userKey, id)
    session.reset(id)
    warmed.current = null
  }, [session, userKey])

  const actions = useMemo<ChatActions>(
    () => ({
      replaceBlock: (id, raw, newId, opts) => session.replaceBlock(id, raw, newId, opts),
      markBlock: (id, ui) => session.markBlock(id, ui),
      addSystemNote: (text, key) => session.addSystemNote(text, key),
      getConversationId: () => session.getConversationId(),
      ask: (text) => void session.send(text),
      retryLast: () => void session.retry(),
      askAgain: () => void session.askAgain(),
      revealBlock: (id) => session.revealBlock(id),
      undoWindowMs,
      // Server là nguồn sự thật về việc một đề nghị đã thực hiện chưa: chỉ vá trạng thái, không dựng lại cả hội thoại.
      reloadConversation: async () => {
        const id = session.getConversationId()
        if (session.getSnapshot().running) return
        try {
          const turns = await repository.load(id)
          if (id === session.getConversationId() && !session.getSnapshot().running) session.applyResolutions(turns)
        } catch {
          // Không tải lại được thì giữ nguyên: thông báo lỗi của lần bấm vẫn hiện.
        }
      },
    }),
    [session, repository, undoWindowMs],
  )

  const value = useMemo<ChatContextValue>(
    () => ({
      snapshot,
      hydrating,
      replayFailed,
      send: (t) => session.send(t),
      retry: () => session.retry(),
      stop: () => session.stop(),
      startNew,
      warmUp,
    }),
    [snapshot, hydrating, replayFailed, session, startNew, warmUp],
  )

  return (
    <ChatActionsContext.Provider value={actions}>
      <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
    </ChatActionsContext.Provider>
  )
}

export function useChat(): ChatContextValue {
  const c = useContext(ChatContext)
  if (!c) throw new Error('useChat phải nằm trong <ChatProvider>')
  return c
}
