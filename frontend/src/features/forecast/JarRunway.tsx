import type { CSSProperties, ReactNode } from 'react'
import { Link } from 'react-router'
import { ChevronRight } from 'lucide-react'
import { JarStatusChip } from '@/components/JarStatusChip'
import { StatusChip } from '@/components/StatusChip'
import { Disclosure } from '@/components/ui/Disclosure'
import { jarColor } from '@/components/jarTheme'
import type { ForecastMeta, JarFull, NextPayday, Obligation } from '@/api/schemas'
import { cn } from '@/lib/cn'
import { diffDays, formatDayMonth } from '@/lib/dates'
import { formatRatioPercent, formatShortfallChance, formatSimMoment, formatVnd, formatVndNumber } from '@/lib/format'
import { CONFIDENCE_LABEL } from '@/lib/jar'
import { useAnimateOnce } from '@/lib/motion'

// B2 "Hũ nào sắp cạn" (spending-visualization.md §3), nay là khối dự báo duy nhất của tab Nhìn trước (ui-design-review.md §10
// "Mỗi thông tin một nhà"): gộp đường băng tới kỳ lương với danh sách hũ dự báo cũ (số dư, khả năng hụt, nhãn), kỳ lương kế tiếp
// và chất lượng dự báo. Hũ chi tiêu và hũ nghĩa vụ có đường băng; hũ tiết kiệm không "cạn" theo nghĩa này nên chỉ có một dòng.
// Đoạn còn tiền tô màu đủ, từ ngày cạn tới kỳ lương là đoạn hụt gạch chéo có chấm ở ngày cạn, hũ sát tô màu sát, mốc nghĩa vụ là
// vạch trên đúng hũ trả. Mọi số (trạng thái, ngày cạn, khả năng hụt, ngày lương, khoản đến hạn) lấy từ GET /overview; vị trí chỉ
// để vẽ. Luật chữ (§9): hiện ngay tên hũ, nhãn Đủ/Sát/Hụt, số dư; câu tóm tắt, mốc chi tiết, chất lượng dự báo vào "Chi tiết".
// Câu đầy đủ của từng hàng là nhãn của liên kết cho trình đọc màn hình.

const TRACK_KINDS = new Set<JarFull['kind']>(['spending', 'obligation'])

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

const chance = (j: JarFull) => (j.p_shortfall !== undefined ? `Khả năng hụt ${formatShortfallChance(j.p_shortfall).toLowerCase()}` : null)

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
  const p = chance(jar)
  const sentence = `${jar.name}: ${state}, số dư ${formatVnd(jar.balance_vnd)}${p ? `, ${p.toLowerCase()}` : ''}${marks.length ? `. Sắp đến hạn: ${marks.join('; ')}` : ''}.`
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

/** Dòng đầu của một hàng: chấm màu hũ, tên, nhãn Đủ/Sát/Hụt (kèm ngày cạn), số dư. */
function RowHead({ jar }: { jar: JarFull }) {
  return (
    <span className="flex items-center gap-2" aria-hidden>
      <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: jarColor(jar.color_key) }} />
      <span className="min-w-0 flex-1 truncate text-small font-semibold text-ink">{jar.name}</span>
      <JarStatusChip jar={jar} className="h-6 text-note" />
      <span className="num shrink-0 text-small font-bold text-ink">{formatVnd(jar.balance_vnd)}</span>
    </span>
  )
}

function Quality({ f }: { f: ForecastMeta }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-xl bg-surface-2 p-3" aria-label="Chất lượng dự báo" data-testid="forecast-quality">
      <div>
        <dt>Nhóm tin cậy</dt>
        <dd className="font-semibold text-ink">{CONFIDENCE_LABEL[f.confidence_band]}</dd>
      </div>
      <div>
        <dt>Độ phủ dữ liệu</dt>
        <dd className="num font-semibold text-ink">{f.coverage !== undefined ? formatRatioPercent(f.coverage) : 'Chưa tính được'}</dd>
      </div>
      <div>
        <dt>Dữ liệu lịch sử</dt>
        <dd className="num font-semibold text-ink">{f.history_days} ngày</dd>
      </div>
      <div>
        <dt>Cập nhật</dt>
        <dd className="font-semibold text-ink">{formatSimMoment(f.run_app_date, f.computed_at)}</dd>
      </div>
    </dl>
  )
}

/**
 * Khối dự báo của tab Nhìn trước. `jars` đã xếp theo mức cần chú ý (nơi dùng sắp); `notice` là một dòng nhỏ đặt dưới tiêu đề khi có
 * điều làm dự báo kém chính xác (giao dịch chưa xếp hũ).
 */
export function JarRunway({ jars, appDate, nextPayday, obligations, forecast, notice }: {
  jars: JarFull[]
  appDate: string
  nextPayday: NextPayday | null
  obligations: Obligation[]
  forecast: ForecastMeta | null
  notice?: ReactNode
}) {
  const animate = useAnimateOnce('jar-runway')
  if (jars.length === 0) return null
  const payday = nextPayday?.date
  const span = payday ? Math.max(1, diffDays(appDate, payday)) : 1
  const tracked = jars.filter((j) => TRACK_KINDS.has(j.kind))
  const others = jars.filter((j) => !TRACK_KINDS.has(j.kind))
  const rows = payday ? tracked.map((j) => rowFor(j, appDate, payday, span, obligations)) : []
  const attention = tracked.filter((j) => j.status === 'short' || j.status === 'tight')
  const until = payday ? ` trước kỳ lương ${formatDayMonth(payday)}` : ''
  const caption = tracked.every((j) => !j.status)
    ? `Chưa có dự báo cho các hũ${until}.`
    : attention.length === 0
      ? `Các hũ chi tiêu đủ${payday ? ` tới kỳ lương ${formatDayMonth(payday)}` : ''}.`
      : `${attention.length} hũ cần chú ý${until}: ${attention
          .map((j) => (j.status === 'short' ? `${j.name} ${j.runout_date ? `dự kiến cạn ${formatDayMonth(j.runout_date)}` : 'hụt'}` : `${j.name} sát`))
          .join(', ')}.`
  const marks = rows.flatMap((r) => r.mine.map((o) => ({ jar: r.jar.name, o })))
  const rowAnim = (i: number) =>
    animate
      ? { className: 'motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-left-2 fill-mode-both duration-300 ease-out', style: { '--tw-animation-delay': `${i * 40}ms` } as CSSProperties }
      : {}

  return (
    <figure className="rounded-card bg-surface p-4 shadow-card" data-testid="jar-runway" aria-labelledby="jar-runway-title" aria-describedby="jar-runway-caption">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="jar-runway-title" className="min-w-0 flex-1 text-subtitle font-semibold text-ink">Hũ nào sắp cạn</h2>
        {forecast?.stale && <StatusChip kind="warn">Số liệu cũ</StatusChip>}
        {forecast?.is_initial_estimate && <StatusChip kind="info">Ước lượng ban đầu</StatusChip>}
        {nextPayday && (
          <span className="num inline-flex h-7 items-center rounded-full bg-surface-2 px-2.5 text-note font-semibold text-ink-2" data-testid="next-payday">
            Lương {formatDayMonth(nextPayday.date)} · còn {nextPayday.days_until} ngày
          </span>
        )}
      </div>
      {/* Câu tóm tắt nhắc lại điều các hàng đã nói: chỉ cho trình đọc màn hình (bản nhìn thấy nằm trong "Chi tiết"). */}
      <figcaption id="jar-runway-caption" className="sr-only">{caption}</figcaption>
      {notice}
      {rows.length > 0 && (
        <>
          <div className="mt-3 flex justify-between text-note text-ink-2" aria-hidden>
            <span>Hôm nay {formatDayMonth(appDate)}</span>
            <span className="font-semibold text-ok-fg">Lương {formatDayMonth(payday!)}</span>
          </div>
          <ul className="mt-1 space-y-1" aria-label="Hũ theo mức cần chú ý">
            {rows.map((r, i) => {
              const p = r.jar.status === 'short' || r.jar.status === 'tight' ? chance(r.jar) : null
              return (
                <li key={r.jar.code} data-runway={r.jar.code} {...rowAnim(i)}>
                  <Link to={`/jars/${r.jar.code}`} aria-label={r.sentence} className="block min-h-11 rounded-xl py-1.5">
                    <RowHead jar={r.jar} />
                    <Track row={r} />
                    {p && <span className="num mt-0.5 block text-right text-note text-ink-2" aria-hidden>{p}</span>}
                  </Link>
                </li>
              )
            })}
          </ul>
        </>
      )}
      {(others.length > 0 || rows.length === 0) && (
        <>
          {rows.length > 0 && <h3 className="mt-3 text-note font-semibold text-ink-2">Hũ tiết kiệm</h3>}
          <ul className="mt-1 divide-y divide-line" aria-label={rows.length > 0 ? 'Hũ tiết kiệm' : 'Hũ theo mức cần chú ý'}>
            {(rows.length > 0 ? others : jars).map((j) => (
              <li key={j.code} data-runway={j.code}>
                <Link
                  to={`/jars/${j.code}`}
                  aria-label={`${j.name}: số dư ${formatVnd(j.balance_vnd)}${chance(j) ? `, ${chance(j)!.toLowerCase()}` : ''}.`}
                  className="flex min-h-11 items-center gap-1 py-1.5"
                >
                  <span className="min-w-0 flex-1"><RowHead jar={j} /></span>
                  <ChevronRight className="size-4 shrink-0 text-ink-2" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
      <Disclosure label="Chi tiết" className="mt-1" panelClassName="space-y-2 pb-1 text-small text-ink-2">
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
        {nextPayday?.expected_vnd !== undefined && <p className="num">Lương dự kiến {formatVnd(nextPayday.expected_vnd)}</p>}
        {forecast && <Quality f={forecast} />}
        {forecast?.stale && <p>Số liệu cũ: mở chi tiết một hũ để tính lại.</p>}
        <p className="text-note">Chạm một hũ để xem dự báo từng ngày.</p>
      </Disclosure>
    </figure>
  )
}
