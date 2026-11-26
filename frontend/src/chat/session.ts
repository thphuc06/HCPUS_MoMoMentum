import type { AgentSubscriber, HttpAgent } from '@ag-ui/client'
import { newTraceparent, newUuid } from '@/lib/ids'
import { AuthError } from '@/auth/types'
import { blockSchemas } from '@/contracts/blocks'
import { chatErrorForCode, chatErrorForHttp, CHAT_MESSAGES, type ChatNoticeSpec } from './errors'
import { receiptNote } from './receiptNote'
import type { Resolution, StoredTurnInput } from './repository'
import type { AgentContext } from './walletContext'

/** Khóa activityType của khối UI trong ACTIVITY_SNAPSHOT (hợp đồng với agent). */
export const BLOCK_ACTIVITY_TYPE = 'yofina.block'
/** Header session của AgentCore Runtime: UUID ổn định theo cuộc hội thoại (33 đến 256 ký tự). */
export const SESSION_HEADER = 'X-Amzn-Bedrock-AgentCore-Runtime-Session-Id'
/**
 * Trần thời gian một lượt chat chờ lượt làm nóng của cùng phiên (ms). Runtime chỉ nhận một lượt mỗi session id: gửi khi
 * lượt làm nóng còn chạy thì bị 409 SESSION_BUSY. Quá trần thì gửi luôn để không treo nếu làm nóng kẹt.
 */
export const WARMUP_WAIT_MS = 15_000
/** Thời gian lùi trước mỗi lần thử lại khi Runtime trả 409 SESSION_BUSY (ms); hết danh sách thì hiện lỗi bận. */
export const SESSION_BUSY_RETRY_DELAYS_MS: readonly number[] = [1_000, 2_000, 4_000]

/**
 * Trạng thái hiển thị gắn thêm cho một khối `confirm` (ngoài nội dung khối): `cancelled` (người dùng bấm "Không",
 * chỉ ở phiên đang mở), `expired` (server báo quá hạn đề nghị), `done` (server báo đã thực hiện nhưng không
 * dựng được biên nhận: hiện "đã thực hiện", không nút).
 */
export type BlockUi = 'cancelled' | 'expired' | 'done' | 'undone'

export type ChatItem =
  | { kind: 'user'; id: string; text: string }
  | { kind: 'assistant'; id: string; text: string; done: boolean }
  | { kind: 'tool'; id: string; name: string; status: 'running' | 'done' }
  /**
   * `resolved`: khối này là kết quả của một đề nghị đã thực hiện (biên nhận thay chỗ `confirm`). `doneAt`: thời điểm (đồng hồ
   * máy) đề nghị vừa được thực hiện trong phiên này, để đếm ngược Hoàn tác; không có khi dựng lại từ server sau khi tải trang.
   */
  | { kind: 'block'; id: string; raw: unknown; ui?: BlockUi; resolved?: boolean; doneAt?: number }
  | { kind: 'notice'; id: string; title: string; message: string; code?: string; retry: boolean }

export type HistoryMessage = { id: string; role: 'user' | 'assistant' | 'system'; content: string }

export type ChatSnapshot = {
  conversationId: string
  items: readonly ChatItem[]
  running: boolean
  /** Id các khối xác nhận đã được "Chọn" từ một phương án (khối tham chiếu bởi `options.action` chỉ hiện sau khi chọn). */
  revealed: ReadonlySet<string>
}

export type ChatDeps = {
  agentUrl: string
  conversationId: string
  /** Access token còn hạn; `force` ép làm mới (gặp 401). */
  getAccessToken: (opts?: { force?: boolean }) => Promise<string>
  fetchImpl?: typeof fetch
  /** Gọi sau mỗi lượt kết thúc (tùy chọn). */
  onTurnEnd?: () => void
  /**
   * Các mục `context` AG-UI gửi kèm mỗi lượt chat (tùy chọn), đọc lúc gửi: danh sách hũ của ví từ REST (`walletContext`) để agent không
   * phải đọc ví trước router. Không có thì gửi `context` rỗng như trước.
   */
  getContext?: () => readonly AgentContext[]
}

type AgentEvent = { type: string } & Record<string, unknown>
type TurnState = {
  n: number
  started: boolean
  finished: boolean
  errored: boolean
  produced: boolean
  /** `fallback_text` của các khối đã phát trong lượt, theo id khối (cùng id thì khối sau thay khối trước). */
  blockTexts: Map<string, string>
}

/** Chờ `ms` hoặc tới khi `signal` bị hủy (bấm Dừng), tùy cái nào đến trước. */
function pause(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve()
    const done = () => {
      clearTimeout(timer)
      signal.removeEventListener('abort', done)
      resolve()
    }
    const timer = setTimeout(done, ms)
    signal.addEventListener('abort', done)
  })
}

function str(v: unknown): string | undefined {
  return typeof v === 'string' ? v : undefined
}

/** `fallback_text` của một khối thô (mọi khối đều có, do engine dựng, không phải chữ của model). */
function blockFallback(raw: unknown): string | undefined {
  const t = str((raw as { fallback_text?: unknown } | null)?.fallback_text)
  return t?.trim() ? t.trim() : undefined
}

/**
 * Nội dung lượt của trợ lý trong lịch sử gửi agent: tóm tắt các khối (dòng thời gian, thẻ kiểm tra, câu hỏi lại...) rồi tới
 * phần chữ. Nhiều lượt chỉ có khối, không có chữ: thiếu phần này thì agent không biết lượt trước nó đã trả lời gì
 * (ví dụ đã mô phỏng khoản nào, vừa hỏi lại câu gì). Chỉ vào lịch sử, không đổi những gì người dùng thấy.
 */
export function assistantHistoryText(blockTexts: readonly string[], text: string): string {
  return [...blockTexts, text.trim()].filter(Boolean).join('\n')
}

type SettledBlock = { id: string; raw: unknown; ui?: BlockUi; resolved?: boolean; note?: { key: string; text: string } }

/**
 * Áp trạng thái do server giữ (`resolutions`) lên một khối đã lưu: `done` + biên nhận hợp lệ -> biên nhận thay chỗ
 * khối `confirm` (không còn nút bấm) và một ghi chú hệ thống cho agent; `done` mà biên nhận hỏng -> giữ khối
 * nhưng khóa; `expired` -> đánh dấu hết hạn; còn lại giữ nguyên.
 */
function settleBlock(raw: unknown, res: Resolution | undefined): SettledBlock {
  const rawId = (raw as { id?: unknown } | null)?.id
  const id = typeof rawId === 'string' ? rawId : `blk-${newUuid()}`
  if (!res) return { id, raw }
  if (res.status === 'done') {
    const receipt = blockSchemas.receipt.safeParse(res.receipt)
    const receiptAction = blockSchemas.receipt_action.safeParse(res.receipt)
    const parsed = receipt.success ? receipt : receiptAction.success ? receiptAction : null
    if (parsed) {
      return { id: parsed.data.id, raw: res.receipt, resolved: true, note: { key: parsed.data.id, text: receiptNote(parsed.data) } }
    }
    return { id, raw, ui: 'done', resolved: true }
  }
  if (res.status === 'cancelled') return { id, raw, ui: 'cancelled' }
  if (res.status === 'expired') return { id, raw, ui: 'expired' }
  return { id, raw }
}

/**
 * Phiên chat: giữ danh sách mục hiển thị và lịch sử gửi agent, chạy từng lượt qua @ag-ui/client
 * gọi thẳng Runtime. Tách khỏi React để test bằng chuỗi event mẫu. Quy tắc cốt lõi:
 * - gửi lại TOÀN BỘ lịch sử (user, assistant, ghi chú hệ thống) mỗi lượt; khối UI không vào lịch sử;
 * - luồng rỗng hoặc đứt giữa chừng (200 + thân rỗng, không RUN_FINISHED) là lỗi, có nút thử lại;
 * - 401: làm mới token và thử lại một lần; 403: thông báo riêng;
 * - lượt chat chờ lượt làm nóng của cùng phiên xong (tối đa `WARMUP_WAIT_MS`); 409 SESSION_BUSY: thử lại có lùi
 *   (`SESSION_BUSY_RETRY_DELAYS_MS`), hết lượt thử mới báo bận.
 */
export class ChatSession {
  private items: ChatItem[] = []
  private history: HistoryMessage[] = []
  private running = false
  private revealed: ReadonlySet<string> = new Set()
  private conversationId: string
  private listeners = new Set<() => void>()
  private snapshot: ChatSnapshot
  private agent: HttpAgent | null = null
  private aborted = false
  /** Hủy các lần chờ trong lượt đang chạy (chờ làm nóng, lùi trước khi thử lại) khi bấm Dừng. */
  private waitAbort: AbortController | null = null
  /** Lượt làm nóng đang chạy (theo session id); xong thì xóa. */
  private warming: { conversationId: string; done: Promise<void> } | null = null
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
    return { conversationId: this.conversationId, items: this.items, running: this.running, revealed: this.revealed }
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

  /**
   * Thay khối `confirm` có `id` bằng kết quả của nó (biên nhận) ở đúng vị trí; đánh dấu `resolved` để phần chữ
   * của lượt hiện là "trước khi xác nhận". Chưa có thì thêm cuối.
   */
  replaceBlock(id: string, raw: unknown, newId?: string, opts?: { fresh?: boolean; undone?: boolean }): void {
    const i = this.items.findIndex((p) => p.kind === 'block' && p.id === id)
    const item: ChatItem = { kind: 'block', id: newId ?? id, raw, resolved: true, ...(opts?.fresh ? { doneAt: Date.now() } : {}), ...(opts?.undone ? { ui: 'undone' as const } : {}) }
    if (i === -1) return this.setItems([...this.items, item])
    const next = this.items.slice()
    next[i] = item
    this.setItems(next)
  }

  /** "Chọn" một phương án: hiện khối xác nhận mà phương án tham chiếu (khối đã có sẵn trong lượt nhưng đang ẩn). */
  revealBlock(id: string): void {
    if (this.revealed.has(id)) return
    this.revealed = new Set([...this.revealed, id])
    this.emit()
  }

  /** Hỏi lại đúng câu cuối của người dùng (đề nghị hết hạn: hỏi lại để có đề nghị mới). */
  async askAgain(): Promise<void> {
    if (this.running) return
    let last: string | undefined
    for (const it of this.items) if (it.kind === 'user') last = it.text
    if (last) await this.send(last)
  }

  markBlock(id: string, ui: 'cancelled'): void {
    this.setItems(this.items.map((p) => (p.kind === 'block' && p.id === id ? { ...p, ui } : p)))
  }

  /**
   * Thêm một dòng hệ thống vào lịch sử gửi agent ở lượt sau; không hiện cho người dùng. Cùng `key` thì chỉ thêm
   * một lần (lúc bấm xác nhận và lúc đồng bộ lại từ server cùng cho ra một ghi chú).
   */
  addSystemNote(content: string, key?: string): void {
    const id = `sys-${key ?? newUuid()}`
    if (this.history.some((m) => m.id === id)) return
    this.history = [...this.history, { id, role: 'system', content }]
  }

  /** Id cuộc hội thoại hiện tại (cũng là session id của Runtime). */
  getConversationId(): string {
    return this.conversationId
  }

  /** Dựng lại hội thoại từ dữ liệu server (phát lại sau khi tải trang), kèm trạng thái từng đề nghị. */
  hydrate(turns: readonly StoredTurnInput[]): void {
    const items: ChatItem[] = []
    const history: HistoryMessage[] = []
    for (const t of turns) {
      if (t.user_text) {
        const id = `u-${t.trace_id}`
        items.push({ kind: 'user', id, text: t.user_text })
        history.push({ id, role: 'user', content: t.user_text })
      }
      const byId = new Map((t.resolutions ?? []).map((r) => [r.block_id, r]))
      const notes: Array<{ key: string; text: string }> = []
      const blockTexts = new Map<string, string>()
      for (const raw of t.blocks) {
        const rawId = (raw as { id?: unknown } | null)?.id
        const s = settleBlock(raw, typeof rawId === 'string' ? byId.get(rawId) : undefined)
        items.push({ kind: 'block', id: s.id, raw: s.raw, ui: s.ui, resolved: s.resolved })
        if (s.note) notes.push(s.note)
        const fb = blockFallback(raw)
        if (fb) blockTexts.set(typeof rawId === 'string' ? rawId : s.id, fb)
      }
      if (t.assistant_text) {
        items.push({ kind: 'assistant', id: `a-${t.trace_id}`, text: t.assistant_text, done: true })
      }
      const content = assistantHistoryText([...blockTexts.values()], t.assistant_text)
      if (content) history.push({ id: `a-${t.trace_id}`, role: 'assistant', content })
      // Việc đã thực hiện xảy ra sau lượt này (lúc người dùng bấm): báo agent như lúc bấm.
      for (const n of notes) history.push({ id: `sys-${n.key}`, role: 'system', content: n.text })
    }
    this.history = history
    this.setItems(items)
  }

  /**
   * Đồng bộ trạng thái đề nghị từ server mà KHÔNG dựng lại cả hội thoại (không làm mất mục chưa lưu như thông báo
   * lỗi): khối `confirm` đang hiện mà server báo `done` thì đổi thành biên nhận. Dùng khi gặp ALREADY_APPLIED.
   */
  applyResolutions(turns: readonly StoredTurnInput[]): void {
    const all = new Map<string, Resolution>()
    for (const t of turns) for (const r of t.resolutions ?? []) all.set(r.block_id, r)
    let changed = false
    const next = this.items.map((it): ChatItem => {
      if (it.kind !== 'block') return it
      const res = all.get(it.id)
      if (!res || res.status === 'pending') return it
      const s = settleBlock(it.raw, res)
      if (s.note) this.addSystemNote(s.note.text, s.note.key)
      if (s.id === it.id && s.ui === it.ui && s.resolved === it.resolved) return it
      changed = true
      return { kind: 'block', id: s.id, raw: s.raw, ui: s.ui, resolved: s.resolved }
    })
    if (changed) this.setItems(next)
  }

  /** Bắt đầu cuộc hội thoại mới (id mới, danh sách trống). */
  reset(conversationId: string): void {
    this.stop()
    this.conversationId = conversationId
    this.history = []
    this.items = []
    this.revealed = new Set()
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
    this.waitAbort?.abort()
    this.agent?.abortRun()
  }

  /**
   * Làm nóng phiên Runtime: một lượt `forwardedProps.warmup` (agent chỉ nạp cấu hình và tạo client, không gọi model hay
   * tool) với cùng session id. Lượt chat gửi trong lúc này sẽ chờ nó xong (xem `runTurn`). Lỗi thì bỏ qua: làm nóng chỉ
   * là tối ưu độ trễ, lượt chat đầu sẽ chịu cold start. Promise trả về không bao giờ reject.
   */
  warmUp(): Promise<void> {
    const id = this.conversationId
    const fetchImpl = this.deps.fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a))
    const body = { threadId: id, runId: newUuid(), state: {}, messages: [], tools: [], context: [], forwardedProps: { warmup: true } }
    const done = this.deps
      .getAccessToken()
      .then(async (token) => {
        const res = await fetchImpl(this.deps.agentUrl, {
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
        // Đọc hết luồng: Runtime chỉ coi phiên rảnh khi lượt làm nóng kết thúc.
        await res.text()
      })
      .catch(() => {})
      .finally(() => {
        if (this.warming?.done === done) this.warming = null
      })
    this.warming = { conversationId: id, done }
    return done
  }

  /** Chờ lượt làm nóng của phiên hiện tại (nếu đang chạy), tối đa `WARMUP_WAIT_MS`; Dừng thì thôi chờ. */
  private async waitForWarmup(signal: AbortSignal): Promise<void> {
    const w = this.warming
    if (!w || w.conversationId !== this.conversationId) return
    // Bộ hẹn giờ riêng để dọn ngay khi làm nóng xong trước trần.
    const local = new AbortController()
    const onAbort = () => local.abort()
    signal.addEventListener('abort', onAbort)
    try {
      await Promise.race([w.done, pause(WARMUP_WAIT_MS, local.signal)])
    } finally {
      local.abort()
      signal.removeEventListener('abort', onAbort)
    }
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
    const waits = new AbortController()
    this.waitAbort = waits
    this.emit()
    try {
      // Giao diện vẫn ở trạng thái đang gửi trong lúc chờ.
      await this.waitForWarmup(waits.signal)
      let force = false
      let refreshed = false
      let busyRetries = 0
      while (!this.aborted) {
        const outcome = await this.attempt(force)
        force = false
        if (outcome === 'unauthorized') {
          if (refreshed) {
            this.notice(chatErrorForHttp(401))
            break
          }
          refreshed = true
          force = true
          continue
        }
        if (outcome === 'busy') {
          const delay = SESSION_BUSY_RETRY_DELAYS_MS[busyRetries++]
          if (delay === undefined) {
            this.notice(chatErrorForHttp(409))
            break
          }
          await pause(delay, waits.signal)
          continue
        }
        break
      }
    } finally {
      this.running = false
      this.agent = null
      this.waitAbort = null
      this.emit()
      this.deps.onTurnEnd?.()
    }
  }

  /**
   * Một lần gọi Runtime. Trả 'unauthorized' khi gặp 401 để lớp trên làm mới token rồi thử lại, 'busy' khi gặp 409
   * (phiên đang chạy lượt khác) để lớp trên lùi rồi thử lại.
   */
  private async attempt(forceRefresh: boolean): Promise<'done' | 'unauthorized' | 'busy'> {
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

    const turn: TurnState = {
      n: ++this.turnSeq,
      started: false,
      finished: false,
      errored: false,
      produced: false,
      blockTexts: new Map(),
    }
    const texts = new Map<string, string>()
    const subscriber: AgentSubscriber = {
      onEvent: ({ event }) => {
        this.onEvent(event as unknown as AgentEvent, turn, texts)
      },
    }

    try {
      const context = [...(this.deps.getContext?.() ?? [])]
      await agent.runAgent(context.length > 0 ? { context } : {}, subscriber)
    } catch (err) {
      if (this.aborted) {
        this.finishOpenItems()
        return 'done'
      }
      const status = (err as { status?: unknown } | null)?.status
      if (typeof status === 'number') {
        if (status === 401) return 'unauthorized'
        this.finishOpenItems()
        if (status === 409) return 'busy'
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
        const answer = assistantHistoryText(
          [...turn.blockTexts.values()],
          [...texts.values()].filter((t) => t.trim()).join('\n\n'),
        )
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
        // Người dùng bấm Dừng: @ag-ui/client báo RUN_ERROR (code "abort") nhưng đó không phải lỗi, nên không hiện thông báo.
        if (!this.aborted) this.notice(chatErrorForCode(str(e.code), str(e.message)))
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
        const fb = blockFallback(e.content)
        if (fb) turn.blockTexts.set(id, fb)
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
