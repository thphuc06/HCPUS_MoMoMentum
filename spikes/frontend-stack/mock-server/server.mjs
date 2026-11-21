// Mock AG-UI server (SSE) để kiểm phía client. Không có LLM, không có AWS.
// Chạy: node mock-server/server.mjs   (cổng 8787, đổi bằng PORT=...)
// Node 24 chạy trực tiếp file .ts nên import được fixtures từ src/.
import http from 'node:http'
import { setTimeout as sleep } from 'node:timers/promises'
import { forecastBlock, jarSummaryBlock, affordabilityBlock, confirmBlock, unknownBlock, brokenBlock } from '../src/blocks/fixtures.ts'

const PORT = Number(process.env.PORT ?? 8787)
const FAST = process.env.FAST === '1' // bỏ độ trễ khi chạy kiểm thử

const cors = {
  'access-control-allow-origin': '*',
  'access-control-allow-headers': 'content-type, authorization, accept, x-amzn-bedrock-agentcore-runtime-session-id',
  'access-control-allow-methods': 'POST, OPTIONS',
}

const nowTs = () => Date.now()
const d = (ms) => (FAST ? Promise.resolve() : sleep(ms))

async function readBody(req) {
  const chunks = []
  for await (const c of req) chunks.push(c)
  return JSON.parse(Buffer.concat(chunks).toString() || '{}')
}

function textChunks(s) {
  // tách theo từ, giữ khoảng trắng
  return s.match(/\S+\s*/g) ?? [s]
}

http
  .createServer(async (req, res) => {
    if (req.method === 'OPTIONS') {
      res.writeHead(204, cors)
      return res.end()
    }
    if (req.method !== 'POST' || !req.url?.startsWith('/run')) {
      res.writeHead(404, cors)
      return res.end('not found')
    }
    const input = await readBody(req)
    const last = [...(input.messages ?? [])].reverse().find((m) => m.role === 'user')
    console.log('[mock] run', input.threadId, input.runId, 'user:', last?.content)

    res.writeHead(200, { ...cors, 'content-type': 'text/event-stream', 'cache-control': 'no-cache', connection: 'keep-alive' })
    const emit = (ev) => res.write(`data: ${JSON.stringify({ timestamp: nowTs(), ...ev })}\n\n`)
    let closed = false
    req.on('close', () => (closed = true))

    const say = async (messageId, text) => {
      emit({ type: 'TEXT_MESSAGE_START', messageId, role: 'assistant' })
      for (const piece of textChunks(text)) {
        if (closed) return
        emit({ type: 'TEXT_MESSAGE_CONTENT', messageId, delta: piece })
        await d(45)
      }
      emit({ type: 'TEXT_MESSAGE_END', messageId })
    }

    try {
      emit({ type: 'RUN_STARTED', threadId: input.threadId, runId: input.runId })
      await say('m1', 'Mình đọc dự báo hũ Ăn uống của bạn nhé. Mình sẽ gọi công cụ dự báo trước.')

      // tool call 1: dự báo -> khối đi bằng CUSTOM
      emit({ type: 'TOOL_CALL_START', toolCallId: 'tc1', toolCallName: 'forecast.get_forecast', parentMessageId: 'm1' })
      emit({ type: 'TOOL_CALL_ARGS', toolCallId: 'tc1', delta: '{"jar_id":"an_' })
      emit({ type: 'TOOL_CALL_ARGS', toolCallId: 'tc1', delta: 'uong","horizon_days":30}' })
      emit({ type: 'TOOL_CALL_END', toolCallId: 'tc1' })
      await d(1600) // thời gian "tool đang chạy" để thấy skeleton
      emit({ type: 'TOOL_CALL_RESULT', messageId: 'tr1', toolCallId: 'tc1', content: JSON.stringify({ ok: true }), role: 'tool' })
      emit({ type: 'CUSTOM', name: 'yofina.block', value: forecastBlock('an_uong', true) })
      await d(300)

      await say('m2', 'Hũ Ăn uống dự kiến cạn ngày 29/11, trước kỳ lương 5/12. Bạn thử xem nếu mua tai nghe thì sao.')

      // tool call 2: khả năng chi trả -> khối đi bằng ACTIVITY_SNAPSHOT
      emit({ type: 'TOOL_CALL_START', toolCallId: 'tc2', toolCallName: 'affordability.check', parentMessageId: 'm2' })
      emit({ type: 'TOOL_CALL_ARGS', toolCallId: 'tc2', delta: '{"amount_vnd":1200000}' })
      emit({ type: 'TOOL_CALL_END', toolCallId: 'tc2' })
      await d(900)
      emit({ type: 'TOOL_CALL_RESULT', messageId: 'tr2', toolCallId: 'tc2', content: JSON.stringify({ verdict: 'tight' }), role: 'tool' })
      emit({ type: 'ACTIVITY_SNAPSHOT', messageId: 'act:af', activityType: 'yofina.block', content: affordabilityBlock(), replace: true })
      emit({ type: 'ACTIVITY_SNAPSHOT', messageId: 'act:js', activityType: 'yofina.block', content: jarSummaryBlock('giai_tri'), replace: true })
      await d(200)
      // cùng messageId -> thay tại chỗ (khối jar_summary đổi sang hũ Ăn uống)
      emit({ type: 'ACTIVITY_SNAPSHOT', messageId: 'act:js', activityType: 'yofina.block', content: jarSummaryBlock('an_uong'), replace: true })

      // khối lạ và khối sai schema: client phải rơi về fallback
      emit({ type: 'CUSTOM', name: 'yofina.block', value: unknownBlock() })
      emit({ type: 'ACTIVITY_SNAPSHOT', messageId: 'act:broken', activityType: 'yofina.block', content: brokenBlock(), replace: true })
      await d(200)

      emit({ type: 'CUSTOM', name: 'yofina.block', value: confirmBlock() })
      await say('m3', 'Nếu muốn, mình đề xuất chuyển 300.000 ₫ từ hũ Giải trí sang. Bạn bấm xác nhận để thực hiện.')
      emit({ type: 'RUN_FINISHED', threadId: input.threadId, runId: input.runId })
    } catch (e) {
      console.error(e)
      if (!closed) emit({ type: 'RUN_ERROR', message: String(e) })
    }
    res.end()
  })
  .listen(PORT, () => console.log(`[mock] AG-UI SSE tại http://localhost:${PORT}/run`))
