import type { AgentSubscriber, HttpAgent } from '@ag-ui/client'
import { newTraceparent, newUuid } from '@/lib/ids'
import { AuthError } from '@/auth/types'
import { chatErrorForCode, chatErrorForHttp, CHAT_MESSAGES, type ChatNoticeSpec } from './errors'
import type { StoredTurn } from './repository'

/** Khóa activityType của khối UI trong ACTIVITY_SNAPSHOT (hợp đồng với agent). */
export const BLOCK_ACTIVITY_TYPE = 'yofina.block'
/** Header session của AgentCore Runtime: UUID ổn định theo cuộc hội thoại (33 đến 256 ký tự). */
export const SESSION_HEADER = 'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id'

export type ChatItem =
  | { kind: 'user'; id: string; text: string }
  | { kind: 'assistant'; id: string; text: string; done: boolean }
  | { kind: 'tool'; id: string; name: string; status: 'running' | 'done' }
  | { kind: 'block'; id: string; raw: unknown; ui?: 'cancelled' }
  | { kind: 'notice'; id: string; title: string; message: string; code?: string; retry: boolean }

export type HistoryMessage = { id: string; role: 'user' | 'assistant' | 'system'; content: string }

export type ChatSnapshot = {
  conversationId: string
  items: readonly ChatItem[]
  running: boolean
}

export type ChatDeps = {
  agentUrl: string
  conversationId: string
  /** Access token còn hạn; `force` ép làm mới (gặp 401). */
  getAccessToken: (opts?: { force?: boolean }) => Promise<string>
  fetchImpl?: typeof fetch
  /** Gọi sau mỗi lượt kết thúc (tùy chọn). */
  onTurnEnd?: () => void
}

type AgentEvent = { type: string } & Record<string, unknown>
type TurnState = { n: number; started: boolean; finished: boolean; errored: boolean; produced: boolean }

function str(v: unknown): string | undefined {
  return typeof v === 'string' ? v : undefined
}

/**
 * Phiên chat: giữ danh sách mục hiển thị và lịch sử gửi agent, chạy từng lượt qua @ag-ui/client
 * gọi thẳng Runtime. Tách khỏi React để test bằng chuỗi event mẫu. Quy tắc cốt lõi:
 * - gửi lại TOÀN BỘ lịch sử (user, assistant, ghi chú hệ thống) mỗi lượt; khối UI không vào lịch sử;
 * - luồng rỗng hoặc đứt giữa chừng (200 + thân rỗng, không RUN_FINISHED) là lỗi, có nút thử lại;
 * - 401: làm mới token và thử lại một lần; 403, 409 SESSION_BUSY: thông báo riêng.
 */
export class ChatSession {
  private items: ChatItem[] = []
  private history: HistoryMessage[] = []
  private running = false
  private conversationId: string
  private listeners = new Set<() => void>()
  private snapshot: ChatSnapshot
  private agent: HttpAgent | null = null
  private aborted = false
  private turnSeq = 0
  private readonly deps: ChatDeps

  constructor(deps: ChatDeps) {
    this.deps = deps
    this.conversationId = deps.conversationId
    this.snapshot = this.buildSnapshot()
  }

  // --- đăng ký theo kiểu useSyncExternalStore ---
  subscribe = (cb: () => void): (() => void) => {
    this.listeners.add(cb)
    return () => this.listeners.delete(cb)
  }
  getSnapshot = (): ChatSnapshot => this.snapshot

  private buildSnapshot(): ChatSnapshot {
    return { conversationId: this.conversationId, items: this.items, running: this.running }
  }
  private emit(): void {
    this.snapshot = this.buildSnapshot()
    for (const l of this.listeners) l()
  }
  private setItems(next: ChatItem[]): void {
    this.items = next
    this.emit()
  }

  /** Lịch sử sẽ gửi ở lượt sau (để test và gỡ lỗi). */
  getHistory(): readonly HistoryMessage[] {
    return this.history
  }

  // --- thao tác trên mục ---
  private upsert(item: ChatItem, merge?: (old: ChatItem) => ChatItem): void {
    const i = this.items.findIndex((p) => p.id === item.id && p.kind === item.kind)
    if (i === -1) return this.setItems([...this.items, item])
    const next = this.items.slice()
    next[i] = merge ? merge(this.items[i]!) : item
    this.setItems(next)
  }

  /** Thay khối có `id` bằng khối mới ở đúng vị trí (confirm -> receipt). Chưa có thì thêm cuối. */
  replaceBlock(id: string, raw: unknown, newId?: string): void {
    const i = this.items.findIndex((p) => p.kind === 'block' && p.id === id)
    const item: ChatItem = { kind: 'block', id: newId ?? id, raw }
    if (i === -1) return this.setItems([...this.items, item])
    const next = this.items.slice()
    next[i] = item
    this.setItems(next)
  }

  markBlock(id: string, ui: 'cancelled'): void {
    this.setItems(this.items.map((p) => (p.kind === 'block' && p.id === id ? { ...p, ui } : p)))
  }

  /** Thêm một dòng hệ thống vào lịch sử gửi agent ở lượt sau; không hiện cho người dùng. */
  addSystemNote(content: string): void {
    this.history = [...this.history, { id: `sys-${newUuid()}`, role: 'system', content }]
  }

  /** Dựng lại hội thoại từ dữ liệu server (phát lại sau khi tải trang). */
  hydrate(turns: readonly StoredTurn[]): void {
    const items: ChatItem[] = []
    const history: HistoryMessage[] = []
    for (const t of turns) {
      if (t.user_text) {
        const id = `u-${t.trace_id}`
        items.push({ kind: 'user', id, text: t.user_text })
        history.push({ id, role: 'user', content: t.user_text })
      }
      for (const raw of t.blocks) {
        const id = (raw as { id?: unknown } | null)?.id
        items.push({ kind: 'block', id: typeof id === 'string' ? id : `blk-${newUuid()}`, raw })
      }
      if (t.assistant_text) {
        const id = `a-${t.trace_id}`
        items.push({ kind: 'assistant', id, text: t.assistant_text, done: true })
        history.push({ id, role: 'assistant', content: t.assistant_text })
      }
    }
    this.history = history
    this.setItems(items)
  }

  /** Bắt đầu cuộc hội thoại mới (id mới, danh sách trống). */
  reset(conversationId: string): void {
    this.stop()
    this.conversationId = conversationId
    this.history = []
    this.items = []
    this.running = false
    this.emit()
  }

  // --- chạy lượt ---
  async send(text: string): Promise<void> {
    const content = text.trim()
    if (!content || this.running) return
    const id = `u-${newUuid()}`
    this.history = [...this.history, { id, role: 'user', content }]
    this.setItems([...this.items, { kind: 'user', id, text: content }])
    await this.runTurn()
  }

  /** Chạy lại lượt vừa lỗi: bỏ phần dở dang sau tin nhắn người dùng cuối rồi gửi lại cùng lịch sử. */
  async retry(): Promise<void> {
    if (this.running) return
    let lastUser = -1
    this.items.forEach((it, i) => {
      if (it.kind === 'user') lastUser = i
    })
    if (lastUser === -1) return
    this.setItems(this.items.slice(0, lastUser + 1))
    await this.runTurn()
  }

  stop(): void {
    if (!this.running) return
    this.aborted = true
    this.agent?.abortRun()
  }

  private notice(spec: ChatNoticeSpec): void {
    this.setItems([
      ...this.items,
      { kind: 'notice', id: `n-${newUuid()}`, title: spec.title, message: spec.message, code: spec.code, retry: spec.retry },
    ])
  }

  private async runTurn(): Promise<void> {
    this.running = true
    this.aborted = false
    this.emit()
    try {
      let outcome = await this.attempt(false)
      if (outcome === 'unauthorized') outcome = await this.attempt(true)
      if (outcome === 'unauthorized') this.notice(chatErrorForHttp(401))
    } finally {
      this.running = false
      this.agent = null
      this.emit()
      this.deps.onTurnEnd?.()
    }
  }

  /** Một lần gọi Runtime. Trả 'unauthorized' khi gặp 401 để lớp trên làm mới token rồi thử lại. */
  private async attempt(forceRefresh: boolean): Promise<'done' | 'unauthorized'> {
    let token: string
    try {
      token = await this.deps.getAccessToken({ force: forceRefresh })
    } catch (e) {
      this.notice(e instanceof AuthError ? chatErrorForHttp(401) : { title: CHAT_MESSAGES.genericTitle, message: CHAT_MESSAGES.genericMessage, retry: true })
      return 'done'
    }

    const fetchImpl = this.deps.fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a))
    // @ag-ui/client (cùng rxjs, protobuf) chỉ tải khi có lượt chat đầu tiên: giữ bundle tải đầu nhẹ.
    const { HttpAgent } = await import('@ag-ui/client')
    const agent = new HttpAgent({
      url: this.deps.agentUrl,
      threadId: this.conversationId,
      headers: {
        Authorization: `Bearer ${token}`,
        [SESSION_HEADER]: this.conversationId,
        traceparent: newTraceparent().header,
      },
      initialMessages: this.history.map((m) => ({ id: m.id, role: m.role, content: m.content })) as never,
      // Không đặt credentials: 'include' (Runtime trả Access-Control-Allow-Origin: *).
      fetch: (url, init) => fetchImpl(url, init),
    })
    this.agent = agent

    const turn: TurnState = { n: ++this.turnSeq, started: false, finished: false, errored: false, produced: false }
    const texts = new Map<string, string>()
    const subscriber: AgentSubscriber = {
      onEvent: ({ event }) => {
        this.onEvent(event as unknown as AgentEvent, turn, texts)
      },
    }

    try {
      await agent.runAgent({}, subscriber)
    } catch (err) {
      if (this.aborted) {
        this.finishOpenItems()
        return 'done'
      }
      const status = (err as { status?: unknown } | null)?.status
      if (typeof status === 'number') {
        if (status === 401) return 'unauthorized'
        this.finishOpenItems()
        this.notice(chatErrorForHttp(status))
        return 'done'
      }
      // RUN_ERROR đã được báo qua onEvent; lỗi khác (đứt mạng, event sai thứ tự) rơi xuống phần kiểm tra bên dưới.
      if (!turn.errored) {
        this.finishOpenItems()
        this.notice({ title: CHAT_MESSAGES.interruptedTitle, message: CHAT_MESSAGES.interruptedMessage, retry: true })
        return 'done'
      }
    }

    this.finishOpenItems()
    if (this.aborted) return 'done'
    if (!turn.errored) {
      if (!turn.started && !turn.produced) {
        this.notice({ title: CHAT_MESSAGES.emptyTitle, message: CHAT_MESSAGES.emptyMessage, retry: true })
      } else if (!turn.finished) {
        this.notice({ title: CHAT_MESSAGES.interruptedTitle, message: CHAT_MESSAGES.interruptedMessage, retry: true })
      } else if (!turn.produced) {
        this.notice({ title: CHAT_MESSAGES.noAnswerTitle, message: CHAT_MESSAGES.noAnswerMessage, retry: true })
      } else {
        const answer = [...texts.values()].filter((t) => t.trim()).join('\n\n')
        if (answer) this.history = [...this.history, { id: `a-${newUuid()}`, role: 'assistant', content: answer }]
      }
    }
    return 'done'
  }

  /** Kết thúc các mục đang dở (chữ chưa đóng, công cụ chưa có kết quả) khi lượt dừng. */
  private finishOpenItems(): void {
    if (!this.items.some((i) => (i.kind === 'assistant' && !i.done) || (i.kind === 'tool' && i.status === 'running'))) return
    this.setItems(
      this.items.map((i) =>
        i.kind === 'assistant' && !i.done ? { ...i, done: true } : i.kind === 'tool' && i.status === 'running' ? { ...i, status: 'done' } : i,
      ),
    )
  }

  private onEvent(e: AgentEvent, turn: TurnState, texts: Map<string, string>): void {
    // Id tin nhắn và công cụ chỉ cần duy nhất trong một lượt: gắn số lượt để hai lượt không đè lên nhau.
    const scoped = (id: string) => `${turn.n}:${id}`
    switch (e.type) {
      case 'RUN_STARTED':
        turn.started = true
        break
      case 'RUN_FINISHED':
        turn.finished = true
        break
      case 'RUN_ERROR': {
        turn.errored = true
        this.finishOpenItems()
        this.notice(chatErrorForCode(str(e.code), str(e.message)))
        break
      }
      case 'TEXT_MESSAGE_START': {
        const raw = str(e.messageId)
        if (!raw) break
        const id = scoped(raw)
        texts.set(id, '')
        this.upsert({ kind: 'assistant', id, text: '', done: false })
        break
      }
      case 'TEXT_MESSAGE_CONTENT': {
        const raw = str(e.messageId)
        const delta = str(e.delta)
        if (!raw || delta === undefined) break
        const id = scoped(raw)
        const next = (texts.get(id) ?? '') + delta
        texts.set(id, next)
        if (delta) turn.produced = true
        this.upsert({ kind: 'assistant', id, text: next, done: false })
        break
      }
      case 'TEXT_MESSAGE_END': {
        const raw = str(e.messageId)
        if (!raw) break
        const id = scoped(raw)
        this.upsert({ kind: 'assistant', id, text: texts.get(id) ?? '', done: true })
        break
      }
      case 'TOOL_CALL_START': {
        const raw = str(e.toolCallId)
        if (!raw) break
        const id = scoped(raw)
        this.upsert({ kind: 'tool', id, name: str(e.toolCallName) ?? '', status: 'running' })
        break
      }
      case 'TOOL_CALL_RESULT': {
        const raw = str(e.toolCallId)
        if (!raw) break
        const id = scoped(raw)
        this.setItems(this.items.map((i) => (i.kind === 'tool' && i.id === id ? { ...i, status: 'done' } : i)))
        break
      }
      case 'ACTIVITY_SNAPSHOT': {
        // Cùng messageId thì thay khối tại chỗ (replace): khóa theo messageId.
        if (str(e.activityType) !== BLOCK_ACTIVITY_TYPE) break
        const id = str(e.messageId)
        if (!id) break
        turn.produced = true
        const i = this.items.findIndex((p) => p.kind === 'block' && p.id === id)
        if (i === -1) this.setItems([...this.items, { kind: 'block', id, raw: e.content }])
        else {
          const next = this.items.slice()
          next[i] = { kind: 'block', id, raw: e.content }
          this.setItems(next)
        }
        break
      }
      default:
        break
    }
  }
}
