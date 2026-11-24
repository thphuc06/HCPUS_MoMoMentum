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

/** Bước là một lần gọi tool khi tên có dạng `<target>___<tool>` (hợp đồng `TraceStep`). */
export function splitToolStep(step: string): { target: string; tool: string } | null {
  const i = step.indexOf('___')
  return i > 0 ? { target: step.slice(0, i), tool: step.slice(i + 3) } : null
}
