import { JarIcon } from '@/components/JarIcon'
import { StatusChip } from '@/components/StatusChip'
import type { ReviewItem } from '@/contracts/blocks'
import { formatDayMonth } from '@/lib/dates'
import { formatVnd } from '@/lib/format'

const CONFIDENCE = {
  auto: { kind: 'ok', label: 'Tin cậy cao' },
  review: { kind: 'warn', label: 'Tin cậy vừa' },
  ask: { kind: 'bad', label: 'Tin cậy thấp' },
} as const

export function ReviewItemRow({ item }: { item: ReviewItem }) {
  const confidence = CONFIDENCE[item.tier]
  const kind = item.kind === 'expense' ? 'Khoản chi' : 'Khoản thu'

  return (
    <li className="space-y-2 rounded-xl bg-surface-2 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="min-w-0 wrap-anywhere text-small font-semibold text-ink">{item.counterparty ?? item.note ?? kind}</p>
        <strong className="num text-small text-ink">{formatVnd(item.amount_vnd)}</strong>
      </div>
      <p className="wrap-anywhere text-note text-ink-2">
        {kind} ngày {formatDayMonth(item.app_date)}{item.counterparty && item.note && ` · ${item.note}`}
      </p>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <StatusChip kind={confidence.kind}>{confidence.label}</StatusChip>
        <span className="text-small text-ink-2">{item.current_jar ? `Hũ hiện tại · ${item.current_jar.name}` : 'Chưa có hũ hiện tại'}</span>
      </div>
      {item.suggestions.length > 0 && (
        <ul aria-label="Hũ gợi ý" className="space-y-2 border-t border-line pt-2">
          {item.suggestions.map(({ jar, reason }) => (
            <li key={jar.code} className="flex items-start gap-2 text-small">
              <JarIcon colorKey={jar.color_key} iconKey={jar.icon_key} size={24} />
              <div className="min-w-0">
                <p className="font-semibold text-ink">{jar.name}</p>
                <p className="text-ink-2">{reason}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}
