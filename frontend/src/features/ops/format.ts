import type { ChipKind } from '@/components/StatusChip'

/** 480 -> "480 ms"; 5400 -> "5,4 s". */
export function formatMs(ms: number): string {
  if (ms < 1000) return `${ms.toLocaleString('vi-VN')} ms`
  return `${(ms / 1000).toLocaleString('vi-VN', { maximumFractionDigits: 1 })} s`
}

export const OUTCOME_CHIP: Record<'ok' | 'rejected' | 'error', { kind: ChipKind; label: string }> = {
  ok: { kind: 'ok', label: 'Thành công' },
  rejected: { kind: 'warn', label: 'Bị từ chối' },
  error: { kind: 'bad', label: 'Lỗi' },
}

export const TOOL_STATUS_CHIP: Record<'ok' | 'error' | 'denied', { kind: ChipKind; label: string }> = {
  ok: { kind: 'ok', label: 'OK' },
  error: { kind: 'bad', label: 'Lỗi' },
  denied: { kind: 'warn', label: 'Cedar từ chối' },
}

/**
 * Tên ngắn dễ đọc của một model id Bedrock, suy bằng luật chung (không có bảng tên):
 * bỏ tiền tố vùng và nhà cung cấp (phần trước dấu chấm cuối), bỏ hậu tố `-v1:0` (bản đầu, không mang thông tin; `-v2:0` giữ là
 * "v2"), bỏ ngày phát hành 8 chữ số; tên dạng `<họ>-<bậc>-<số>` bỏ từ họ (`claude-sonnet-4-6`); các số liền nhau nối bằng dấu chấm;
 * mỗi từ viết hoa chữ đầu, trừ số hiệu phiên bản `vN`.
 * `global.anthropic.claude-sonnet-4-6` -> "Sonnet 4.6"; `global.amazon.nova-2-lite-v1:0` -> "Nova 2 Lite";
 * `global.anthropic.claude-haiku-4-5-20251001-v1:0` -> "Haiku 4.5". Không suy được thì trả nguyên id.
 */
export function shortModelName(id: string): string {
  let s = id.trim().slice(id.trim().lastIndexOf('/') + 1).toLowerCase()
  s = s.replace(/-v1:\d+$/, '').replace(/-(v\d+):\d+$/, '-$1').replace(/:\d+$/, '')
  s = s.slice(s.lastIndexOf('.') + 1)
  let tokens = s.split('-').filter((t) => t && !/^\d{8}$/.test(t))
  if (tokens.length >= 3 && /^[a-z]+$/.test(tokens[0]!) && /^[a-z]+$/.test(tokens[1]!) && /^\d+$/.test(tokens[2]!)) tokens = tokens.slice(1)
  const words: string[] = []
  let prevNumber = false
  for (const t of tokens) {
    const isNumber = /^\d+$/.test(t)
    if (isNumber && prevNumber) words[words.length - 1] += `.${t}`
    else words.push(/^v\d+$/.test(t) ? t : t.charAt(0).toUpperCase() + t.slice(1))
    prevNumber = isNumber
  }
  return words.join(' ') || id
}

/** Tên ngắn cho cả danh sách model của một ngày: hai id khác nhau ra cùng tên ngắn thì hiện nguyên id cho khỏi lẫn. */
export function shortModelNames(ids: readonly string[]): string[] {
  const short = ids.map(shortModelName)
  return short.map((name, i) => (short.filter((x) => x === name).length > 1 ? ids[i]! : name))
}

/** Mức dùng so với trần ngày của một model: `near` từ 80% trần, `over` khi chạm hoặc vượt trần. Tính bằng số nguyên. */
export type CapLevel = 'ok' | 'near' | 'over'
export function capLevel(calls: number, cap: number): CapLevel {
  if (cap <= 0) return calls > 0 ? 'over' : 'ok'
  if (calls >= cap) return 'over'
  return calls * 5 >= cap * 4 ? 'near' : 'ok'
}

/** Bước là một lần gọi tool khi tên có dạng `<target>___<tool>` (hợp đồng `TraceStep`). */
export function splitToolStep(step: string): { target: string; tool: string } | null {
  const i = step.indexOf('___')
  return i > 0 ? { target: step.slice(0, i), tool: step.slice(i + 3) } : null
}
