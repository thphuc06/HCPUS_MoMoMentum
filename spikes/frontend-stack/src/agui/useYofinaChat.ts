import { useCallback, useRef, useState } from 'react'
import { HttpAgent, type AgentSubscriber } from '@ag-ui/client'

export type ChatItem =
  | { kind: 'user'; id: string; text: string }
  | { kind: 'text'; id: string; text: string; done: boolean }
  | { kind: 'tool'; id: string; name: string; status: 'running' | 'done'; args?: unknown }
  | { kind: 'block'; id: string; raw: unknown; via: 'custom' | 'activity' }
  | { kind: 'error'; id: string; text: string }

declare global {
  interface Window {
    __aguiEvents?: string[]
  }
}

// Client mỏng trên @ag-ui/client: HttpAgent + AgentSubscriber đẩy event vào state React.
export function useYofinaChat(url: string) {
  const [items, setItems] = useState<ChatItem[]>([])
  const [running, setRunning] = useState(false)
  const agentRef = useRef<HttpAgent | null>(null)

  const upsert = useCallback((item: ChatItem, merge?: (old: ChatItem) => ChatItem) => {
    setItems((prev) => {
      const i = prev.findIndex((p) => p.id === item.id && p.kind === item.kind)
      if (i === -1) return [...prev, item]
      const next = prev.slice()
      next[i] = merge ? merge(prev[i]) : item
      return next
    })
  }, [])

  const send = useCallback(
    async (text: string) => {
      if (!agentRef.current) agentRef.current = new HttpAgent({ url, threadId: `thread-${Date.now()}` })
      const agent = agentRef.current
      const userId = `u-${Date.now()}`
      setItems((p) => [...p, { kind: 'user', id: userId, text }])
      agent.addMessage({ id: userId, role: 'user', content: text })
      setRunning(true)
      window.__aguiEvents = []

      const subscriber: AgentSubscriber = {
        onEvent: ({ event }) => {
          window.__aguiEvents?.push(String(event.type))
        },
        onTextMessageStartEvent: ({ event }) => {
          upsert({ kind: 'text', id: event.messageId, text: '', done: false })
        },
        onTextMessageContentEvent: ({ event, textMessageBuffer }) => {
          upsert({ kind: 'text', id: event.messageId, text: textMessageBuffer, done: false })
        },
        onTextMessageEndEvent: ({ event, textMessageBuffer }) => {
          upsert({ kind: 'text', id: event.messageId, text: textMessageBuffer, done: true })
        },
        onToolCallStartEvent: ({ event }) => {
          upsert({ kind: 'tool', id: event.toolCallId, name: event.toolCallName, status: 'running' })
        },
        onToolCallEndEvent: ({ event, toolCallName, toolCallArgs }) => {
          upsert({ kind: 'tool', id: event.toolCallId, name: toolCallName, status: 'running', args: toolCallArgs })
        },
        onToolCallResultEvent: ({ event }) => {
          setItems((p) => p.map((it) => (it.kind === 'tool' && it.id === event.toolCallId ? { ...it, status: 'done' } : it)))
        },
        // Cách 1: CUSTOM { name: 'yofina.block', value: <block> }
        onCustomEvent: ({ event }) => {
          if (event.name === 'yofina.block') {
            const raw = event.value as { id?: string } | undefined
            upsert({ kind: 'block', id: `custom:${raw?.id ?? Math.random()}`, raw: event.value, via: 'custom' })
          }
        },
        // Cách 2: ACTIVITY_SNAPSHOT { messageId, activityType: 'yofina.block', content: <block> }; cùng messageId = thay tại chỗ
        onActivitySnapshotEvent: ({ event }) => {
          if (event.activityType === 'yofina.block') {
            upsert({ kind: 'block', id: event.messageId, raw: event.content, via: 'activity' })
          }
        },
        onRunErrorEvent: ({ event }) => {
          setItems((p) => [...p, { kind: 'error', id: `e-${Date.now()}`, text: event.message }])
        },
        onRunFailed: ({ error }) => {
          setItems((p) => [...p, { kind: 'error', id: `e-${Date.now()}`, text: error.message }])
        },
      }

      try {
        await agent.runAgent({}, subscriber)
      } catch (e) {
        console.warn('[agui] run failed', e)
      } finally {
        setRunning(false)
      }
    },
    [url, upsert],
  )

  const abort = useCallback(() => agentRef.current?.abortRun(), [])
  return { items, running, send, abort }
}
