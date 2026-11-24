import type { CSSProperties } from 'react'
import { cn } from '@/lib/cn'
import { diffDays, formatDayMonth } from '@/lib/dates'

// Figma MiniTimeline (7:146), vẽ lại thành dải ô ngày theo ui-design-review.md §5 cảnh 1: mỗi ô là một ngày từ hôm nay tới
// kỳ lương. Ô trước ngày cạn là "còn tiền", ô ngày cạn tô đặc có chấm, các ô sau đó tới trước kỳ lương là "hũ trống" (gạch chéo,
// không chỉ dựa vào màu), ô cuối là ngày lương. Ngày cạn và ngày lương là số server trả; vị trí ô chỉ là cách vẽ.

type CellKind = 'ok' | 'runout' | 'gap' | 'payday'

const GAP_STYLE: CSSProperties = {
  backgroundImage:
    'repeating-linear-gradient(135deg, var(--status-bad-bg) 0 4px, color-mix(in srgb, var(--status-bad-line) 38%, var(--status-bad-bg)) 4px 6px)',
}

const CELL_CLASS: Record<CellKind, string> = {
  ok: 'bg-ok-bg',
  runout: 'bg-bad-line',
  gap: 'shadow-[inset_0_0_0_1px_var(--status-bad-line)]',
  payday: 'bg-ok-line',
}

/** Chỉ số ô của ngày cạn trong dải (0 là hôm nay), hoặc null nếu không cạn trước kỳ lương. */
function runoutIndex(today: string, runoutDate: string | undefined, last: number): number | null {
  if (!runoutDate) return null
  const i = diffDays(today, runoutDate)
  if (i >= last) return null // cạn đúng hoặc sau ngày lương: không có ngày hũ trống trước kỳ lương
  return Math.max(0, i)
}

function cellKind(i: number, last: number, runIdx: number | null): CellKind {
  if (i === last) return 'payday'
  if (runIdx === null || i < runIdx) return 'ok'
  return i === runIdx ? 'runout' : 'gap'
}

export function MiniTimeline({ today, paydayDate, runoutDate, animate = false }: {
  today: string
  paydayDate: string
  runoutDate?: string
  /** Ô hiện lần lượt từ trái sang và chấm ngày cạn bật ra (chỉ khi được phép chuyển động). */
  animate?: boolean
}) {
  const last = Math.max(1, diffDays(today, paydayDate))
  const n = last + 1
  const runIdx = runoutIndex(today, runoutDate, last)
  const emptyDays = runIdx === null ? 0 : last - runIdx
  const label =
    `Từ hôm nay ${formatDayMonth(today)} đến kỳ lương ${formatDayMonth(paydayDate)}` +
    (runoutDate ? `, dự kiến cạn ${formatDayMonth(runoutDate)}` : '') +
    (emptyDays > 0 ? `, ${emptyDays} ngày hũ trống trước kỳ lương` : '')
  const gap = n > 40 ? 1 : n > 20 ? 2 : 3
  const pos = runIdx === null ? 0 : (runIdx + 0.5) / n
  // Nhãn ngày cạn nằm trên đúng ô; sát mép thì canh theo mép để không tràn khỏi thẻ.
  const runLabelStyle: CSSProperties =
    pos < 0.18 ? { left: `${(runIdx! / n) * 100}%` } : pos > 0.82 ? { right: `${((n - runIdx! - 1) / n) * 100}%` } : { left: `${pos * 100}%`, transform: 'translateX(-50%)' }
  const enter = animate ? 'motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-2 fill-mode-both duration-300 ease-out' : ''

  return (
    <div role="img" aria-label={label} data-testid="mini-timeline" className="mt-3">
      {runIdx !== null && runoutDate && (
        <div className="relative h-5" aria-hidden>
          <span className="absolute top-0 text-small font-semibold whitespace-nowrap text-bad-fg" style={runLabelStyle}>
            Cạn {formatDayMonth(runoutDate)}
          </span>
        </div>
      )}
      <div className="mt-1 grid" style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))`, gap }} aria-hidden>
        {Array.from({ length: n }, (_, i) => {
          const kind = cellKind(i, last, runIdx)
          return (
            <span
              key={i}
              data-day={kind}
              className={cn('relative h-[30px] rounded-[7px]', CELL_CLASS[kind], i === 0 && 'outline-2 -outline-offset-2 outline-brand', enter)}
              style={{ ...(kind === 'gap' ? GAP_STYLE : null), ...(animate ? { '--tw-animation-delay': `${i * 32}ms` } : null) } as CSSProperties}
            >
              {kind === 'runout' && (
                <span
                  className={cn(
                    'absolute -top-[7px] left-1/2 -ml-[6px] size-3 rounded-full border-2 border-surface bg-bad-line',
                    animate && 'motion-safe:animate-in motion-safe:zoom-in-0 fill-mode-both duration-300 ease-out',
                  )}
                  style={animate ? ({ '--tw-animation-delay': `${i * 32 + 200}ms` } as CSSProperties) : undefined}
                />
              )}
            </span>
          )
        })}
      </div>
      <div className="mt-2 flex justify-between gap-3 text-small" aria-hidden>
        <span className="text-ink-2">Hôm nay {formatDayMonth(today)}</span>
        <span className="font-semibold text-ok-fg">Lương {formatDayMonth(paydayDate)}</span>
      </div>
    </div>
  )
}
