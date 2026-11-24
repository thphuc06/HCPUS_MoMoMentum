import type { CSSProperties } from 'react'
import { Link } from 'react-router'
import { StatusChip } from '@/components/StatusChip'
import { Disclosure } from '@/components/ui/Disclosure'
import { jarColor } from '@/components/jarTheme'
import type { ForecastMeta, JarFull, NextPayday, Obligation } from '@/api/schemas'
import { cn } from '@/lib/cn'
import { diffDays, formatDayMonth } from '@/lib/dates'
import { formatVnd, formatVndNumber } from '@/lib/format'
import { statusShortChip } from '@/lib/jar'
import { useAnimateOnce } from '@/lib/motion'

// B2 "Hũ nào sắp cạn" (spending-visualization.md §3): mỗi hũ chi tiêu và hũ nghĩa vụ một đường băng từ hôm nay tới kỳ lương.
// Đoạn còn tiền tô màu đủ, từ ngày cạn tới kỳ lương là đoạn hụt gạch chéo có chấm ở ngày cạn, hũ sát tô màu sát, mốc nghĩa vụ
// là vạch trên đúng hũ trả. Mọi số (trạng thái, ngày cạn, ngày lương, khoản đến hạn) lấy từ GET /overview; vị trí chỉ để vẽ.
// Luật chữ (ui-design-review.md §9): hiện ngay tên hũ, nhãn Đủ/Sát/Hụt, số dư, ngày cạn; câu tóm tắt, mốc chi tiết và chú thích
// vào mục "Chi tiết". Câu đầy đủ của từng hàng vẫn là nhãn của liên kết cho trình đọc màn hình.

const SHOWN_KINDS = new Set<JarFull['kind']>(['spending', 'obligation'])

const BAD_HATCH: CSSProperties = {
  backgroundImage: 'repeating-linear-gradient(45deg, var(--status-bad-line) 0 2px, var(--status-bad-bg) 2px 6px)',
}

function amountText(o: Obligation): string {
  return o.amount_min_vnd !== undefined && o.amount_max_vnd !== undefined ? `${formatVnd(o.amount_min_vnd)} đến ${formatVnd(o.amount_max_vnd)}` : formatVnd(o.amount_vnd)
}

/** Mốc gọn cho phần thu gọn: "Tiền điện 26/11 · 300.000–450.000 ₫". */
export function markShort(o: Obligation): string {
  const amount = o.amount_min_vnd !== undefined && o.amount_max_vnd !== undefined ? `${formatVndNumber(o.amount_min_vnd)}–${formatVnd(o.amount_max_vnd)}` : formatVnd(o.amount_vnd)
  return `${o.name} ${formatDayMonth(o.due_date)} · ${amount}`
}

type Tick = { o: Obligation; pos: number; atRunout: boolean }
type Row = { jar: JarFull; runoutPos: number | null; ticks: Tick[]; sentence: string; mine: Obligation[] }

function rowFor(jar: JarFull, today: string, payday: string, span: number, obligations: Obligation[]): Row {
  const at = (iso: string) => Math.min(1, Math.max(0, diffDays(today, iso) / span))
  const mine = obligations.filter((o) => o.pay_jar === jar.code && diffDays(today, o.due_date) >= 0 && diffDays(o.due_date, payday) >= 0)
  const runoutPos = jar.status === 'short' ? (jar.runout_date && diffDays(jar.runout_date, payday) > 0 ? at(jar.runout_date) : 0) : null
  // Mốc trùng (hoặc sát) ngày cạn: vạch vẽ dài hơn chấm và nằm trên chấm, để chấm không che mất mốc (hũ Hóa đơn cạn đúng ngày tiền điện).
  const ticks = mine.map((o) => {
    const pos = at(o.due_date)
    return { o, pos, atRunout: runoutPos !== null && Math.abs(pos - runoutPos) < 0.04 }
  })
  const marks = mine.map((o) => `${o.name} ${formatDayMonth(o.due_date)} ${amountText(o)}`)
  let state: string
  if (!jar.status) state = 'chưa có dự báo'
  else if (jar.status === 'short') {
    const empty = jar.runout_date ? diffDays(diffDays(today, jar.runout_date) < 0 ? today : jar.runout_date, payday) : 0
    state = jar.runout_date ? `hụt, dự kiến cạn ${formatDayMonth(jar.runout_date)}${empty > 0 ? `, ${empty} ngày trước kỳ lương` : ''}` : 'hụt trước kỳ lương'
  } else state = jar.status === 'tight' ? 'sát' : 'đủ tới kỳ lương'
  const sentence = `${jar.name}: ${state}, số dư ${formatVnd(jar.balance_vnd)}${marks.length ? `. Sắp đến hạn: ${marks.join('; ')}` : ''}.`
  return { jar, runoutPos, ticks, sentence, mine }
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
          <span data-part="runout" className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-[2.5px] border-surface bg-bad-line" style={{ left: `${runoutPos * 100}%` }} />
        </>
      )}
      {ticks.map(({ o, pos, atRunout }) => (
        <span
          key={o.id}
          data-tick={o.id}
          data-at-runout={atRunout ? '' : undefined}
          className={cn('absolute w-0.5 -translate-x-1/2 rounded-full bg-ink', atRunout ? '-top-2 -bottom-2 z-10 outline-2 outline-surface' : '-top-1 -bottom-1')}
          style={{ left: `${Math.min(99, pos * 100)}%` }}
        />
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
  const marks = rows.flatMap((r) => r.mine.map((o) => ({ jar: r.jar.name, o })))

  return (
    <figure className="mx-4 mt-3 rounded-card bg-surface p-4 shadow-card" data-testid="jar-runway" aria-labelledby="jar-runway-title" aria-describedby="jar-runway-caption">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="jar-runway-title" className="min-w-0 flex-1 text-subtitle font-semibold text-ink">Hũ nào sắp cạn</h2>
        {forecast?.stale && <StatusChip kind="warn">Số liệu cũ</StatusChip>}
        {forecast?.is_initial_estimate && <StatusChip kind="info">Ước lượng ban đầu</StatusChip>}
        <span className="num inline-flex h-7 items-center rounded-full bg-surface-2 px-2.5 text-note font-semibold text-ink-2">{nextPayday.days_until} ngày tới lương</span>
      </div>
      {/* Câu tóm tắt nhắc lại điều các hàng đã nói: chỉ cho trình đọc màn hình (bản nhìn thấy nằm trong "Chi tiết"). */}
      <figcaption id="jar-runway-caption" className="sr-only">{caption}</figcaption>
      <div className="mt-3 flex justify-between text-note text-ink-2" aria-hidden>
        <span>Hôm nay {formatDayMonth(appDate)}</span>
        <span className="font-semibold text-ok-fg">Lương {formatDayMonth(payday)}</span>
      </div>
      <ul className="mt-1 space-y-1" aria-label="Các hũ từ hôm nay tới kỳ lương">
        {rows.map((r, i) => {
          const chip = r.jar.status ? statusShortChip(r.jar.status) : { kind: 'info' as const, label: 'Chưa có dự báo' }
          const runout = r.jar.status === 'short' && r.jar.runout_date ? formatDayMonth(r.jar.runout_date) : null
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
                  <StatusChip kind={chip.kind} className="h-6 text-note">{runout ? `${chip.label} · cạn ${runout}` : chip.label}</StatusChip>
                  <span className="num shrink-0 text-small font-bold text-ink">{formatVnd(r.jar.balance_vnd)}</span>
                </span>
                <Track row={r} />
              </Link>
            </li>
          )
        })}
      </ul>
      <Disclosure label="Chi tiết" className="mt-1" panelClassName="space-y-1.5 pb-1 text-small text-ink-2">
        <p className="text-ink">{caption}</p>
        {marks.length > 0 && (
          <ul aria-label="Mốc nghĩa vụ trước kỳ lương" className="space-y-0.5" data-testid="jar-runway-marks">
            {marks.map(({ jar, o }) => (
              <li key={o.id} className="num">
                <span className="font-semibold text-ink">{jar}:</span> {markShort(o)}
              </li>
            ))}
          </ul>
        )}
        <p className="text-note">Hũ tiết kiệm không hiện ở đây. Chạm một hũ để xem dự báo.</p>
      </Disclosure>
    </figure>
  )
}
