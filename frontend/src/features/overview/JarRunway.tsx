import type { CSSProperties } from 'react'
import { Link } from 'react-router'
import { StatusChip } from '@/components/StatusChip'
import { jarColor } from '@/components/jarTheme'
import type { ForecastMeta, JarFull, NextPayday, Obligation } from '@/api/schemas'
import { cn } from '@/lib/cn'
import { diffDays, formatDayMonth } from '@/lib/dates'
import { formatVnd } from '@/lib/format'
import { statusShortChip } from '@/lib/jar'
import { useAnimateOnce } from '@/lib/motion'

// B2 "Hũ nào sắp cạn" (spending-visualization.md §3): mỗi hũ chi tiêu và hũ nghĩa vụ một đường băng từ hôm nay tới kỳ lương.
// Đoạn còn tiền tô màu đủ, từ ngày cạn tới kỳ lương là đoạn hụt gạch chéo có chấm ở ngày cạn, hũ sát tô màu sát, mốc nghĩa vụ
// là vạch trên đúng hũ trả. Mọi số (trạng thái, ngày cạn, ngày lương, khoản đến hạn) lấy từ GET /overview; vị trí chỉ để vẽ.

const SHOWN_KINDS = new Set<JarFull['kind']>(['spending', 'obligation'])

const BAD_HATCH: CSSProperties = {
  backgroundImage: 'repeating-linear-gradient(45deg, var(--status-bad-line) 0 2px, var(--status-bad-bg) 2px 6px)',
}

function amountText(o: Obligation): string {
  return o.amount_min_vnd !== undefined && o.amount_max_vnd !== undefined ? `${formatVnd(o.amount_min_vnd)} đến ${formatVnd(o.amount_max_vnd)}` : formatVnd(o.amount_vnd)
}

type Row = { jar: JarFull; runoutPos: number | null; ticks: { o: Obligation; pos: number }[]; sentence: string; sub: string | null }

function rowFor(jar: JarFull, today: string, payday: string, span: number, obligations: Obligation[]): Row {
  const at = (iso: string) => Math.min(1, Math.max(0, diffDays(today, iso) / span))
  const mine = obligations.filter((o) => o.pay_jar === jar.code && diffDays(today, o.due_date) >= 0 && diffDays(o.due_date, payday) >= 0)
  const ticks = mine.map((o) => ({ o, pos: at(o.due_date) }))
  const runoutPos = jar.status === 'short' ? (jar.runout_date && diffDays(jar.runout_date, payday) > 0 ? at(jar.runout_date) : 0) : null
  const marks = mine.map((o) => `${o.name} ${formatDayMonth(o.due_date)} ${amountText(o)}`)
  let state: string
  if (!jar.status) state = 'chưa có dự báo'
  else if (jar.status === 'short') {
    const empty = jar.runout_date ? diffDays(diffDays(today, jar.runout_date) < 0 ? today : jar.runout_date, payday) : 0
    state = jar.runout_date ? `hụt, dự kiến cạn ${formatDayMonth(jar.runout_date)}${empty > 0 ? `, ${empty} ngày trước kỳ lương` : ''}` : 'hụt trước kỳ lương'
  } else state = jar.status === 'tight' ? 'sát' : 'đủ tới kỳ lương'
  const sentence = `${jar.name}: ${state}, số dư ${formatVnd(jar.balance_vnd)}${marks.length ? `. Sắp đến hạn: ${marks.join('; ')}` : ''}.`
  const subParts: string[] = []
  if (jar.status === 'short' && jar.runout_date) subParts.push(`Dự kiến cạn ${formatDayMonth(jar.runout_date)}`)
  if (marks.length) subParts.push(`Mốc: ${marks.join('; ')}`)
  return { jar, runoutPos, ticks, sentence, sub: subParts.length ? subParts.join('. ') : null }
}

function Track({ row }: { row: Row }) {
  const { jar, runoutPos, ticks } = row
  const base = !jar.status ? 'bg-surface-2' : jar.status === 'tight' ? 'bg-warn-line' : 'bg-ok-line'
  return (
    <div className={cn('relative mt-1.5 h-3 rounded-md shadow-[inset_0_0_0_1px_var(--border-default)]', base)} aria-hidden data-track={jar.status ?? 'none'}>
      {runoutPos !== null && (
        <>
          <span
            data-part="empty"
            className="absolute inset-y-0 right-0 rounded-r-md shadow-[inset_0_0_0_1px_var(--status-bad-line)]"
            style={{ ...BAD_HATCH, left: `${runoutPos * 100}%`, ...(runoutPos === 0 ? { borderRadius: 6 } : null) }}
          />
          <span className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-[2.5px] border-surface bg-bad-line" style={{ left: `${runoutPos * 100}%` }} />
        </>
      )}
      {ticks.map(({ o, pos }) => (
        <span key={o.id} data-tick={o.id} className="absolute -top-1 -bottom-1 w-0.5 -translate-x-1/2 rounded-full bg-ink" style={{ left: `${Math.min(99, pos * 100)}%` }} />
      ))}
    </div>
  )
}

export function JarRunway({ jars, appDate, nextPayday, obligations, forecast }: {
  jars: JarFull[]
  appDate: string
  nextPayday: NextPayday | null
  obligations: Obligation[]
  forecast: ForecastMeta | null
}) {
  const animate = useAnimateOnce('jar-runway')
  const shown = jars.filter((j) => SHOWN_KINDS.has(j.kind))
  if (!nextPayday || shown.length === 0) return null
  const payday = nextPayday.date
  const span = Math.max(1, diffDays(appDate, payday))
  const rows = shown.map((j) => rowFor(j, appDate, payday, span, obligations))
  const attention = rows.filter((r) => r.jar.status === 'short' || r.jar.status === 'tight')
  const noForecast = rows.every((r) => !r.jar.status)
  const caption = noForecast
    ? `Chưa có dự báo cho các hũ trước kỳ lương ${formatDayMonth(payday)}.`
    : attention.length === 0
      ? `Các hũ chi tiêu đủ tới kỳ lương ${formatDayMonth(payday)}.`
      : `${attention.length} hũ cần chú ý trước kỳ lương ${formatDayMonth(payday)}: ${attention
          .map((r) => (r.jar.status === 'short' ? `${r.jar.name} ${r.jar.runout_date ? `dự kiến cạn ${formatDayMonth(r.jar.runout_date)}` : 'hụt'}` : `${r.jar.name} sát`))
          .join(', ')}.`

  return (
    <figure className="mx-4 mt-3 rounded-card bg-surface p-4 shadow-card" data-testid="jar-runway" aria-labelledby="jar-runway-title">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="jar-runway-title" className="min-w-0 flex-1 text-subtitle font-semibold text-ink">Hũ nào sắp cạn</h2>
        {forecast?.stale && <StatusChip kind="warn">Số liệu cũ</StatusChip>}
        {forecast?.is_initial_estimate && <StatusChip kind="info">Ước lượng ban đầu</StatusChip>}
        <span className="num inline-flex h-7 items-center rounded-full bg-surface-2 px-2.5 text-note font-semibold text-ink-2">{nextPayday.days_until} ngày tới lương</span>
      </div>
      <figcaption className="mt-2 text-body text-ink">{caption}</figcaption>
      <div className="mt-3 flex justify-between text-note text-ink-2" aria-hidden>
        <span>Hôm nay {formatDayMonth(appDate)}</span>
        <span className="font-semibold text-ok-fg">Lương {formatDayMonth(payday)}</span>
      </div>
      <ul className="mt-1 space-y-1" aria-label="Các hũ từ hôm nay tới kỳ lương">
        {rows.map((r, i) => {
          const chip = r.jar.status ? statusShortChip(r.jar.status) : { kind: 'info' as const, label: 'Chưa có dự báo' }
          return (
            <li
              key={r.jar.code}
              data-runway={r.jar.code}
              className={cn(animate && 'motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-left-2 fill-mode-both duration-300 ease-out')}
              style={animate ? ({ '--tw-animation-delay': `${i * 40}ms` } as CSSProperties) : undefined}
            >
              <Link to={`/jars/${r.jar.code}`} aria-label={r.sentence} className="block min-h-11 rounded-xl py-1.5">
                <span className="flex items-center gap-2" aria-hidden>
                  <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: jarColor(r.jar.color_key) }} />
                  <span className="min-w-0 flex-1 truncate text-small font-semibold text-ink">{r.jar.name}</span>
                  <StatusChip kind={chip.kind} className="h-6 text-note">{chip.label}</StatusChip>
                  <span className="num shrink-0 text-small font-bold text-ink">{formatVnd(r.jar.balance_vnd)}</span>
                </span>
                <Track row={r} />
                {r.sub && <span className="mt-1 block text-note text-ink-2" aria-hidden>{r.sub}</span>}
              </Link>
            </li>
          )
        })}
      </ul>
      <p className="mt-2 text-note text-ink-2">Hũ tiết kiệm không hiện ở đây. Chạm một hũ để xem dự báo.</p>
    </figure>
  )
}
