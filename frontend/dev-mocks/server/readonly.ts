// CHỈ cho `npm run dev:mock`: các GET chỉ đọc của phase 4 và 5 (chống chịu, lộ trình, bản tin, bộ nhớ, "Vì sao", dòng tiền) trả thẳng
// fixture hợp đồng, để xem và chụp các màn này mà không cần backend. Không có trạng thái: ghi (chấp nhận bước, xóa bộ nhớ) trả 404.
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import type { Ctx, Reply } from './wallet.ts'

const FIXTURES = path.resolve(import.meta.dirname, '../../../contracts/fixtures')
const load = (dir: string, n: string) => JSON.parse(readFileSync(path.join(FIXTURES, dir, `${n}.json`), 'utf8')) as unknown
const ok = (body: unknown): Reply => ({ status: 200, body })

const GET: Record<string, string> = {
  '/resilience': 'ResilienceScoreResponse.minh',
  '/resilience/shocks': 'ShocksResponse.default',
  '/roadmap': 'RoadmapResponse.minh_v3',
  '/roadmap/versions': 'RoadmapVersionsResponse.minh',
  '/roadmap/diff': 'RoadmapDiffResponse.v2_v3',
  // Không có bản tin: Tổng quan dùng thẻ tất định của GET /overview (cảnh báo cạn của cảnh 1).
  '/nudges/today': 'NudgeTodayResponse.trong',
  '/memory': 'MemoryListResponse.minh',
  // Biểu đồ chi tiêu ở Hoạt động (B1, B5, B7): số của minh sinh bằng mã Lambda thật trên PostgreSQL cục bộ.
  '/cashflow': 'CashflowResponse.minh',
}

export function handleReadOnly(c: Ctx): Reply | null {
  if (c.method === 'GET') {
    const name = GET[c.path]
    if (name) return ok(load('rest', name))
    if (c.path === '/review') return ok(load('rest', c.query.get('mode') === 'daily_ask' ? 'ReviewListResponse.daily_ask' : 'ReviewListResponse.review'))
    if (/^\/traces\/[^/]+$/.test(c.path)) return ok(load('rest', 'TraceResponse.what_if'))
  }
  if (c.method === 'POST' && c.path === '/resilience/stress') return ok(load('rest', 'StressResultResponse.mat_viec'))
  return null
}

/** Khối mẫu hợp lệ theo tên fixture (`blocks/valid/<tên>.json`), cho câu chat "khoi <tên>" để xem từng khối trong chat. */
export function blockFixture(name: string): Record<string, unknown> | null {
  if (!/^[a-z_]+\.[a-z0-9_]+$/.test(name)) return null
  const file = path.join(FIXTURES, 'blocks', 'valid', `${name}.json`)
  return existsSync(file) ? (load('blocks/valid', name) as Record<string, unknown>) : null
}
