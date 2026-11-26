import type { ChipKind } from '@/components/StatusChip'
import type { JarStatus } from '@/contracts/blocks'
import { formatDayMonth } from './dates'
import { formatShortfallChance } from './format'

/**
 * Ngày cạn được phép nêu (#25): server đặt `runout_date_shown: false` ở hũ thưa (ngày cạn sai trung bình hơn 6 ngày) và bỏ
 * `runout_date`; dữ liệu cũ còn ngày thì cũng không nêu.
 */
export function shownRunoutDate(d: { runout_date?: string; runout_date_shown?: boolean }): string | undefined {
  return d.runout_date_shown === false ? undefined : d.runout_date
}

/** Hũ hụt mà server không nêu ngày cạn (#25): giao diện nói "Có thể cạn trước ngày lương" thay cho ngày. */
export function mayRunOutBeforePayday(d: { status?: string; runout_date_shown?: boolean }): boolean {
  return d.status === 'short' && d.runout_date_shown === false
}

export const MAY_RUN_OUT = 'Có thể cạn trước ngày lương'

/** Một dòng ngắn cho hũ hụt không nêu ngày cạn, kèm khả năng hụt khi server cho hiện ("…, khả năng 60%"). */
export function mayRunOutText(p?: number): string {
  return p === undefined ? MAY_RUN_OUT : `${MAY_RUN_OUT}, khả năng ${formatShortfallChance(p).toLowerCase()}`
}

/**
 * Mực nước hũ 0..1 chỉ để vẽ: số dư so với mục tiêu của hũ (nếu có), không thì so với hũ đầy nhất đang hiển thị
 * (hợp đồng chưa có mức đầu kỳ của hũ). Số âm vẽ như hũ cạn.
 */
export function jarLevel(jar: { balance_vnd: number; goal_vnd?: number }, peersMax: number): number {
  const ref = jar.goal_vnd && jar.goal_vnd > 0 ? jar.goal_vnd : peersMax
  if (jar.balance_vnd <= 0 || ref <= 0) return 0
  return Math.min(1, Math.max(0.08, jar.balance_vnd / ref))
}

/**
 * Mức vạch "dự báo" trên hũ 0..1 chỉ để vẽ: số dư P50 thấp nhất tới kỳ lương (`forecast_floor_vnd`, server tính, có thể âm
 * nên vẽ như cạn) so với cùng mức tham chiếu với `jarLevel`. Server chưa trả (hũ chưa có dự báo) thì chỉ vẽ vạch cạn cho
 * hũ báo hụt có ngày cạn; còn lại không vẽ vạch (không bịa).
 */
export function jarForecastLevel(
  jar: { balance_vnd: number; goal_vnd?: number; forecast_floor_vnd?: number; status?: string; runout_date?: string },
  peersMax: number,
): number | null {
  if (jar.forecast_floor_vnd !== undefined) {
    const ref = jar.goal_vnd && jar.goal_vnd > 0 ? jar.goal_vnd : peersMax
    if (jar.forecast_floor_vnd <= 0 || ref <= 0) return 0
    return Math.min(1, jar.forecast_floor_vnd / ref)
  }
  return jar.status === 'short' && jar.runout_date ? 0 : null
}

/** Hũ 0 ₫ chưa từng có tiền vào và chưa có giao dịch (#39): sự thật trung tính, không phải cảnh báo. */
export const NEVER_FUNDED_CHIP: { kind: ChipKind; label: string } = { kind: 'info', label: 'Chưa có tiền' }

/**
 * Chip trạng thái từ `status` của server: cùng bộ chữ Đủ / Sát / Hụt với B2 và thẻ kiểm tra (ui-design-review.md §3.2 #13),
 * hũ hụt kèm ngày cạn ("Hụt · cạn 27/11"). Luôn có biểu tượng + chữ (StatusChip). `neverFunded`: hũ 0 ₫ mà server cho biết chưa
 * từng có dòng sổ cái nào (`has_activity: false`, #39): nói "Chưa có tiền" thay cho "Đang hết tiền".
 */
export function jarStatusChip(status: JarStatus, runoutDate?: string, emptyNow = false, neverFunded = false): { kind: ChipKind; label: string } {
  if (status === 'ok') return { kind: 'ok', label: 'Đủ' }
  if (status === 'tight') return { kind: 'warn', label: 'Sát' }
  // Hũ đã không còn tiền (0 ₫): không nói "cạn ngày ..." như thể còn tiền để cạn; chưa từng có tiền thì cũng không nói "hết tiền".
  if (emptyNow) return neverFunded ? NEVER_FUNDED_CHIP : { kind: 'bad', label: 'Đang hết tiền' }
  return { kind: 'bad', label: runoutDate ? `Hụt · cạn ${formatDayMonth(runoutDate)}` : 'Hụt' }
}

/** Nhãn ngắn của ba trạng thái (Đủ, Sát, Hụt) cho thẻ kiểm tra: luôn đi cùng biểu tượng của StatusChip, không chỉ màu. */
export function statusShortChip(status: JarStatus): { kind: ChipKind; label: string } {
  return status === 'ok' ? { kind: 'ok', label: 'Đủ' } : status === 'tight' ? { kind: 'warn', label: 'Sát' } : { kind: 'bad', label: 'Hụt' }
}

export const CONFIDENCE_LABEL = { high: 'Cao', medium: 'Vừa', low: 'Thấp' } as const

/** Tỷ lệ 0..1 của một số so với mức tham chiếu (chỉ để vẽ). */
export function levelOf(value: number, ref: number): number {
  if (ref <= 0 || value <= 0) return 0
  return Math.min(1, value / ref)
}
