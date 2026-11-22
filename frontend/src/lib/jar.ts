import type { ChipKind } from '@/components/StatusChip'
import type { JarStatus } from '@/contracts/blocks'
import { formatDayMonth } from './dates'

/**
 * Mực nước hũ 0..1 chỉ để vẽ: số dư so với mục tiêu của hũ (nếu có), không thì so với hũ đầy nhất đang hiển thị
 * (hợp đồng chưa có mức đầu kỳ của hũ). Số âm vẽ như hũ cạn.
 */
export function jarLevel(jar: { balance_vnd: number; goal_vnd?: number }, peersMax: number): number {
  const ref = jar.goal_vnd && jar.goal_vnd > 0 ? jar.goal_vnd : peersMax
  if (jar.balance_vnd <= 0 || ref <= 0) return 0
  return Math.min(1, Math.max(0.08, jar.balance_vnd / ref))
}

/** Chip trạng thái từ `status` của server (đủ/sát/hụt): luôn có biểu tượng + chữ (StatusChip). */
export function jarStatusChip(status: JarStatus, runoutDate?: string): { kind: ChipKind; label: string } {
  if (status === 'ok') return { kind: 'ok', label: 'Đủ tới kỳ lương' }
  if (status === 'tight') return { kind: 'warn', label: 'Sát, cần nhắc' }
  return { kind: 'bad', label: runoutDate ? `Cạn ngày ${formatDayMonth(runoutDate)}` : 'Hụt tiền' }
}

export const CONFIDENCE_LABEL = { high: 'Cao', medium: 'Vừa', low: 'Thấp' } as const

/** Tỷ lệ 0..1 của một số so với mức tham chiếu (chỉ để vẽ). */
export function levelOf(value: number, ref: number): number {
  if (ref <= 0 || value <= 0) return 0
  return Math.min(1, value / ref)
}
