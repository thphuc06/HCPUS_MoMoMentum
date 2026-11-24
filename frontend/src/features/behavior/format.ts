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
