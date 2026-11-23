import { JarIcon } from '@/components/JarIcon'
import { StatusChip } from '@/components/StatusChip'
import { Button } from '@/components/ui/button'
import type { ReviewItem, ReviewJarRef } from '@/contracts/blocks'
import { formatDayMonth } from '@/lib/dates'
import { formatVnd } from '@/lib/format'

const CONFIDENCE = {
  auto: { kind: 'ok', label: 'Tin cậy cao' },
  review: { kind: 'warn', label: 'Tin cậy vừa' },
  ask: { kind: 'bad', label: 'Tin cậy thấp' },
} as const

export type ReviewRowActions = {
  selectJar: (item: ReviewItem, jar: ReviewJarRef) => void
  pickOtherJar: (item: ReviewItem) => void
  disabled: boolean
  canPickOtherJar: boolean
}

export function reviewItemTitle(item: ReviewItem) {
  return item.counterparty ?? item.note ?? (item.kind === 'expense' ? 'Khoản chi' : 'Khoản thu')
}

export function ReviewItemRow({ item, actions, allowKeep }: { item: ReviewItem; actions?: ReviewRowActions; allowKeep?: boolean }) {
  const confidence = CONFIDENCE[item.tier]
  const kind = item.kind === 'expense' ? 'Khoản chi' : 'Khoản thu'
  const currentJar = item.current_jar

  return (
    <li className="space-y-2 rounded-xl bg-surface-2 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="min-w-0 wrap-anywhere text-small font-semibold text-ink">{reviewItemTitle(item)}</p>
        <strong className="num text-small text-ink">{formatVnd(item.amount_vnd)}</strong>
      </div>
      <p className="wrap-anywhere text-note text-ink-2">
        {kind} ngày {formatDayMonth(item.app_date)}{item.counterparty && item.note && ` · ${item.note}`}
      </p>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <StatusChip kind={confidence.kind}>{confidence.label}</StatusChip>
        <span className="text-small text-ink-2">{currentJar ? `Hũ hiện tại · ${currentJar.name}` : 'Chưa có hũ hiện tại'}</span>
      </div>
      {item.suggestions.length > 0 && (
        <ul aria-label="Hũ gợi ý" className="space-y-2 border-t border-line pt-2">
          {item.suggestions.map(({ jar, reason }) => (
            <li key={jar.code}>
              {actions ? (
                <button
                  type="button"
                  disabled={actions.disabled}
                  onClick={() => actions.selectJar(item, jar)}
                  className="flex min-h-11 w-full items-center gap-2 rounded-xl border border-line bg-surface px-2.5 py-1.5 text-left text-small focus-visible:ring-3 focus-visible:ring-ring/50 active:bg-tint disabled:opacity-50"
                >
                  <JarIcon colorKey={jar.color_key} iconKey={jar.icon_key} size={24} />
                  <span className="min-w-0 wrap-anywhere">
                    <span className="block font-semibold text-brand-text">{jar.name}</span>{' '}
                    <span className="block text-ink-2">{reason}</span>
                  </span>
                </button>
              ) : (
                <div className="flex items-start gap-2 text-small">
                  <JarIcon colorKey={jar.color_key} iconKey={jar.icon_key} size={24} />
                  <div className="min-w-0">
                    <p className="font-semibold text-ink">{jar.name}</p>
                    <p className="text-ink-2">{reason}</p>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {actions && (
        <div className="flex flex-wrap gap-2">
          {allowKeep && currentJar && (
            <Button type="button" variant="soft" size="sm" disabled={actions.disabled} onClick={() => actions.selectJar(item, currentJar)}>
              Đúng rồi
            </Button>
          )}
          <Button type="button" variant="ghost" size="sm" disabled={actions.disabled || !actions.canPickOtherJar} onClick={() => actions.pickOtherJar(item)}>
            Hũ khác
          </Button>
        </div>
      )}
    </li>
  )
}
