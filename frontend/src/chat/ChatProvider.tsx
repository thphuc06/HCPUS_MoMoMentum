import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
import { useAuth } from '@/auth/AuthProvider'
import { newConversationId, newTraceparent, newUuid } from '@/lib/ids'
import { ChatActionsContext, type ChatActions } from './actions'
import {
  clearConversationId,
  loadConversationId,
  saveConversationId,
  type ConversationRepository,
} from './repository'
import { ChatSession, SESSION_HEADER, type ChatSnapshot } from './session'

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
  children: ReactNode
}

export function ChatProvider({ agentUrl, repository, fetchImpl, children }: ChatProviderProps) {
  const { session: auth, getAccessToken } = useAuth()
  const userKey = auth?.email ?? 'anonymous'

  // Một ChatSession cho mỗi người dùng; id hội thoại (cũng là session id của Runtime) nhớ ở trình duyệt, khối thì không.
  const session = useMemo(() => {
    let id = loadConversationId(userKey)
    if (!id) {
      id = newConversationId()
      saveConversationId(userKey, id)
    }
    return new ChatSession({ agentUrl, conversationId: id, getAccessToken, fetchImpl })
  }, [agentUrl, userKey, getAccessToken, fetchImpl])

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
    const id = session.getSnapshot().conversationId
    if (warmed.current === id) return
    warmed.current = id
    const doFetch = fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a))
    // Agent hỗ trợ forwardedProps.warmup: chỉ nạp cấu hình và tạo client, không gọi model hay tool.
    const body = { threadId: id, runId: newUuid(), state: {}, messages: [], tools: [], context: [], forwardedProps: { warmup: true } }
    void getAccessToken()
      .then(async (token) => {
        const res = await doFetch(agentUrl, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
            [SESSION_HEADER]: id,
            traceparent: newTraceparent().header,
          },
          body: JSON.stringify(body),
        })
        await res.text()
      })
      .catch(() => {
        // Làm nóng chỉ là tối ưu độ trễ: lỗi thì bỏ qua, lượt chat đầu sẽ chịu cold start.
      })
  }, [session, agentUrl, fetchImpl, getAccessToken])

  const startNew = useCallback(() => {
    clearConversationId(userKey)
    const id = newConversationId()
    saveConversationId(userKey, id)
    session.reset(id)
    warmed.current = null
  }, [session, userKey])

  const actions = useMemo<ChatActions>(
    () => ({
      replaceBlock: (id, raw, newId) => session.replaceBlock(id, raw, newId),
      markBlock: (id, ui) => session.markBlock(id, ui),
      addSystemNote: (text) => session.addSystemNote(text),
    }),
    [session],
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
