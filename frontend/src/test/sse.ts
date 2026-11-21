// Dựng phản hồi SSE giả cho test từ chuỗi event AG-UI (dạng dây: `data: {json}\n\n`, không có `event:`).
// Dạng event lấy từ docs/research/spike-strands-agui-local.md §2.4, §3.1.

export type Ev = { type: string } & Record<string, unknown>

const enc = new TextEncoder()

export function sseBody(events: Ev[]): string {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('')
}

export type SseOptions = {
  status?: number
  /** Cắt luồng sau n event rồi đóng (mô phỏng đứt giữa chừng). */
  truncateAfter?: number
  /** Làm luồng lỗi sau khi gửi hết event (mô phỏng mất mạng). */
  errorAfter?: boolean
}

export function sseResponse(events: Ev[], opts: SseOptions = {}): Response {
  const list = opts.truncateAfter !== undefined ? events.slice(0, opts.truncateAfter) : events
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const e of list) controller.enqueue(enc.encode(`data: ${JSON.stringify(e)}\n\n`))
      if (opts.errorAfter) controller.error(new TypeError('network error'))
      else controller.close()
    },
  })
  return new Response(stream, {
    status: opts.status ?? 200,
    headers: { 'content-type': 'text/event-stream' },
  })
}

export function emptyResponse(): Response {
  return new Response(new ReadableStream({ start: (c) => c.close() }), {
    status: 200,
    headers: { 'content-type': 'text/event-stream' },
  })
}

export function runError(code: string, message = 'lỗi'): Ev {
  return { type: 'RUN_ERROR', message, code }
}

export const runStarted = (threadId = 't1', runId = 'r1'): Ev => ({ type: 'RUN_STARTED', threadId, runId })
export const runFinished = (threadId = 't1', runId = 'r1'): Ev => ({ type: 'RUN_FINISHED', threadId, runId })

export function textMessage(messageId: string, ...deltas: string[]): Ev[] {
  return [
    { type: 'TEXT_MESSAGE_START', messageId, role: 'assistant' },
    ...deltas.map((delta) => ({ type: 'TEXT_MESSAGE_CONTENT', messageId, delta })),
    { type: 'TEXT_MESSAGE_END', messageId },
  ]
}

export function toolCall(toolCallId: string, name: string, args = '{}'): Ev[] {
  return [
    { type: 'TOOL_CALL_START', toolCallId, toolCallName: name },
    { type: 'TOOL_CALL_ARGS', toolCallId, delta: args },
    { type: 'TOOL_CALL_END', toolCallId },
    { type: 'TOOL_CALL_RESULT', messageId: `res-${toolCallId}`, toolCallId, content: '{}', role: 'tool' },
  ]
}

export function blockSnapshot(messageId: string, content: unknown): Ev {
  return { type: 'ACTIVITY_SNAPSHOT', messageId, activityType: 'yofina.block', content, replace: true }
}
