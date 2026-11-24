import type { BehaviorEvidence, BehaviorInsightKind } from '@/contracts/blocks'
import { formatDayMonth } from '@/lib/dates'
import { formatPercent, formatRatioPercent, formatVnd } from '@/lib/format'

// Đọc số bằng chứng của nhận xét hành vi theo đơn vị hợp đồng (`BehaviorEvidence.unit`). Chỉ đổi cách hiển thị số server trả,
// không tính lại gì.

/** Phần nhận xét hành vi ở màn Hồ sơ (id của section). */
export const BEHAVIOR_SECTION_ID = 'nhan-xet-hanh-vi'
export const PROFILE_BEHAVIOR_PATH = `/profile#${BEHAVIOR_SECTION_ID}`

const WEEKDAY = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ nhật'] as const
const count = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 })

/** Thứ theo ISO (1 là thứ Hai, 7 là Chủ nhật). */
export function weekdayLabel(isoWeekday: number): string {
  return WEEKDAY[isoWeekday - 1] ?? `Thứ ${isoWeekday}`
}

export function formatEvidenceValue(e: Pick<BehaviorEvidence, 'value' | 'unit'>): string {
  switch (e.unit) {
    case 'vnd':
      return formatVnd(e.value)
    case 'percent':
      return formatPercent(e.value)
    case 'ratio':
      return formatRatioPercent(e.value)
    case 'days':
      return `${count.format(e.value)} ngày`
    case 'count':
      return `${count.format(e.value)} lần`
    case 'hour':
      return `${String(Math.round(e.value)).padStart(2, '0')}:00`
    case 'weekday':
      return weekdayLabel(Math.round(e.value))
  }
}

/** Cửa sổ của bằng chứng: "22/09–21/11", "từ 22/09", "đến 21/11" hoặc rỗng. */
export function formatEvidencePeriod(e: Pick<BehaviorEvidence, 'period_from' | 'period_to'>): string {
  if (e.period_from && e.period_to) return `${formatDayMonth(e.period_from)}–${formatDayMonth(e.period_to)}`
  if (e.period_from) return `từ ${formatDayMonth(e.period_from)}`
  if (e.period_to) return `đến ${formatDayMonth(e.period_to)}`
  return ''
}

export const INSIGHT_KIND_LABEL: Record<BehaviorInsightKind, string> = {
  payday_cycle: 'Nhịp lương',
  weekday_pattern: 'Ngày trong tuần',
  time_of_day: 'Giờ trong ngày',
  bnpl_usage: 'Trả sau',
  category_trend: 'Xu hướng hũ',
  spending_cluster: 'Nhóm thói quen',
}

/**
 * Cặp bằng chứng "phần chi" so với "phần số ngày" (mốc nếu chi đều) mà batch hành vi phát trong CÙNG nhận xét
 * (`ml/yofina_ml/behavior.py`): khóa phần chi -> khóa phần số ngày. Hợp đồng chưa có `compare_key` (P1 của
 * spending-visualization.md §4.1) nên giao diện ghép theo bảng khóa cố định này; thiếu một vế thì không vẽ.
 */
export const SHARE_PAIRS: Readonly<Record<string, string>> = {
  weekend_share: 'weekend_day_share',
  first_week_share: 'first_week_day_share',
}

export type SharePair = { share: BehaviorEvidence; base: BehaviorEvidence; sharePct: number; basePct: number }

const toPct = (e: BehaviorEvidence) => (e.unit === 'ratio' ? e.value * 100 : e.value)

/** Các cặp vẽ được của một nhận xét: cả hai vế có mặt, cùng đơn vị phần trăm hoặc tỷ lệ, giá trị trong 0..100%. */
export function sharePairs(evidence: readonly BehaviorEvidence[]): SharePair[] {
  const byKey = new Map(evidence.map((e) => [e.key, e]))
  const out: SharePair[] = []
  for (const [shareKey, baseKey] of Object.entries(SHARE_PAIRS)) {
    const share = byKey.get(shareKey)
    const base = byKey.get(baseKey)
    if (!share || !base || share.unit !== base.unit || (share.unit !== 'percent' && share.unit !== 'ratio')) continue
    const sharePct = toPct(share)
    const basePct = toPct(base)
    if ([sharePct, basePct].some((v) => !Number.isFinite(v) || v < 0 || v > 100)) continue
    out.push({ share, base, sharePct, basePct })
  }
  return out
}

const points = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 })

/** "Nhiều hơn mức chi đều 11 điểm phần trăm" từ hai số của cặp (hiệu hai số server trả, không tính số mới nào khác). */
export function shareGapText(p: Pick<SharePair, 'sharePct' | 'basePct'>): string {
  const d = Math.round((p.sharePct - p.basePct) * 10) / 10
  if (d === 0) return 'Bằng mức chi đều.'
  return `${d > 0 ? 'Nhiều hơn' : 'Ít hơn'} mức chi đều ${points.format(Math.abs(d))} điểm phần trăm.`
}
