import { z } from 'zod'
import { ApiError, apiErrorFromResponse } from '@/api/errors'

// Phát lại hội thoại sau khi tải lại trang. Nguồn sự thật nằm ở server (bảng turn_blocks do agent lưu qua
// `ledger___save_turn`): localStorage chỉ giữ conversation id, không giữ khối hay tin nhắn.
//
// Endpoint theo contracts/rest/openapi.yaml (operationId getConversation):
//   GET /conversations/{conversation_id}   (JWT Bearer)
//   200 -> { conversation_id, turns: [ { trace_id, created_at, user_text, assistant_text, blocks: [khối UI] } ] }
//   (cũ -> mới, tối đa 50 lượt). Hội thoại không có hoặc không thuộc người gọi: 200 với `turns` rỗng.
//   Khối `confirm` được lưu như lúc phát; việc đã bấm xác nhận hay chưa KHÔNG được lưu, nên sau khi tải lại
//   một khối confirm cũ hiện lại như chưa bấm (nút còn hạn thì bấm được; quá hạn thì hiện "hết hạn").
// Tắt phía frontend bằng VITE_CONVERSATION_REPLAY=0. Route chưa deploy (404) coi như chưa có gì.

export const StoredTurn = z.object({
  trace_id: z.string().min(1),
  created_at: z.string(),
  user_text: z.string(),
  assistant_text: z.string(),
  blocks: z.array(z.unknown()),
})
export type StoredTurn = z.infer<typeof StoredTurn>

export const ConversationResponse = z.object({
  conversation_id: z.string(),
  turns: z.array(StoredTurn),
})

export interface ConversationRepository {
  load(conversationId: string): Promise<StoredTurn[]>
}

/** Mặc định khi server chưa có endpoint: không phát lại được gì. */
export class NullConversationRepository implements ConversationRepository {
  async load(): Promise<StoredTurn[]> {
    return []
  }
}

type HttpRepositoryDeps = {
  baseUrl: string
  getAccessToken: (opts?: { force?: boolean }) => Promise<string>
  fetchImpl?: typeof fetch
}

export class HttpConversationRepository implements ConversationRepository {
  private readonly deps: HttpRepositoryDeps

  constructor(deps: HttpRepositoryDeps) {
    this.deps = deps
  }

  async load(conversationId: string): Promise<StoredTurn[]> {
    const doFetch = this.deps.fetchImpl ?? ((...a: Parameters<typeof fetch>) => fetch(...a))
    const token = await this.deps.getAccessToken()
    let res: Response
    try {
      res = await doFetch(`${this.deps.baseUrl}/conversations/${encodeURIComponent(conversationId)}`, {
        headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
      })
    } catch {
      throw new ApiError('NETWORK', 0)
    }
    if (res.status === 404) return []
    const text = await res.text()
    let body: unknown
    try {
      body = text ? JSON.parse(text) : undefined
    } catch {
      body = undefined
    }
    if (!res.ok) throw apiErrorFromResponse(res.status, body)
    const parsed = ConversationResponse.safeParse(body)
    if (!parsed.success) throw new ApiError('INVALID_RESPONSE', res.status)
    return parsed.data.turns
  }
}

// --- Chỉ conversation id được lưu ở trình duyệt (theo người dùng), không lưu khối hay tin nhắn. ---

const KEY_PREFIX = 'yofina.conversation.'

export function loadConversationId(userKey: string): string | null {
  try {
    return localStorage.getItem(KEY_PREFIX + userKey)
  } catch {
    return null
  }
}

export function saveConversationId(userKey: string, id: string): void {
  try {
    localStorage.setItem(KEY_PREFIX + userKey, id)
  } catch {
    /* trình duyệt chặn lưu trữ: chỉ mất khả năng phát lại */
  }
}

export function clearConversationId(userKey: string): void {
  try {
    localStorage.removeItem(KEY_PREFIX + userKey)
  } catch {
    /* bỏ qua */
  }
}
