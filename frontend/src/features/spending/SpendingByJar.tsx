import type { CSSProperties } from 'react'
import { Link } from 'react-router'
import { ArrowDown, ArrowUp, ChevronRight } from 'lucide-react'
import type { CashflowResponse } from '@/api/cashflowSchemas'
import type { JarFull } from '@/api/schemas'
import { jarColor } from '@/components/jarTheme'
import { cn } from '@/lib/cn'
import { formatVnd } from '@/lib/format'
import { byJarCaption, jarBars, jarRowLabel, type JarBar } from './model'

// B1 "Kỳ lương này tiêu vào đâu" (spending-visualization.md §3): thanh ngang theo hũ, sắp theo mức chi kỳ này. Mỗi thanh có ba phần
// khác nhau cả về hoa văn (không chỉ màu): chi thường (màu hũ, đặc), Trả sau (chấm), khoản cố định từ nghĩa vụ (gạch chéo). Vạch đứng
// là mức của kỳ trước TÍNH TỚI CÙNG NGÀY của kỳ. Chạm một hũ mở Chi tiết hũ. Mọi số là của GET /cashflow; tỷ lệ chiều dài là cách vẽ.
// Mỗi hũ là một mục danh sách, chữ đầy đủ là nhãn của liên kết; thanh `aria-hidden`.

/** Trả sau: chấm của màu hũ trên nền nhạt (như B6). */
const creditDots = (color: string): CSSProperties => ({
  backgroundColor: `color-mix(in srgb, ${color} 28%, var(--bg-surface))`,
  backgroundImage: `radial-gradient(${color} 1.4px, transparent 1.6px)`,
  backgroundSize: '5px 5px',
})
/** Khoản cố định (nghĩa vụ): gạch chéo xám, nét đậm để đạt 3:1 trên nền thẻ. */
const FIXED_HATCH: CSSProperties = {
  backgroundImage: 'repeating-linear-gradient(135deg, var(--text-secondary) 0 2px, var(--bg-surface-2) 2px 6px)',
}
// Viền 1 px cho mọi phần thanh: màu hũ nhạt (Đi lại, Du lịch) dưới 3:1 trên nền sáng (spending-visualization.md §2.1 quy tắc 7).
const EDGE = 'shadow-[inset_0_0_0_1px_var(--border-strong)]'

function Track({ bar, color, animate, index }: { bar: JarBar; color: string; animate: boolean; index: number }) {
  return (
    <div className="relative mt-1.5 h-3.5 rounded-md bg-surface-2" aria-hidden data-testid="jar-track">
      <div
        className={cn('flex h-full overflow-hidden rounded-md', animate && 'motion-grow-x')}
        style={animate ? ({ '--motion-delay': `${Math.min(index, 6) * 35}ms` } as CSSProperties) : undefined}
      >
        {bar.regular > 0 && <span className={cn('h-full', EDGE)} style={{ width: `${bar.regular * 100}%`, background: color }} data-part="regular" />}
        {bar.credit > 0 && <span className={cn('h-full', EDGE)} style={{ width: `${bar.credit * 100}%`, ...creditDots(color) }} data-part="credit" />}
        {bar.fixed > 0 && <span className={cn('h-full', EDGE)} style={{ width: `${bar.fixed * 100}%`, ...FIXED_HATCH }} data-part="fixed" />}
      </div>
      {bar.prev !== undefined && (
        <span
          className="absolute -top-1 -bottom-1 w-[3px] -translate-x-1/2 rounded-full bg-ink shadow-[0_0_0_1.5px_var(--bg-surface)]"
          style={{ left: `${Math.min(99.5, bar.prev * 100)}%` }}
          data-part="previous"
        />
      )}
    </div>
  )
}

function Change({ change }: { change: number }) {
  if (change === 0) return <span>bằng kỳ trước</span>
  const up = change > 0
  const Icon = up ? ArrowUp : ArrowDown
  return (
    <span className={cn('inline-flex items-center gap-0.5 font-semibold', up ? 'text-bad-fg' : 'text-ok-fg')}>
      <Icon className="size-3.5" aria-hidden />
      {up ? 'tăng' : 'giảm'} {formatVnd(Math.abs(change))}
    </span>
  )
}

export function SpendingByJar({ data, lookup, animate = false }: { data: CashflowResponse; lookup: Map<string, JarFull>; animate?: boolean }) {
  const bars = jarBars(data)
  const hasPrev = !!data.previous
  const seen = { credit: bars.some((b) => b.credit > 0), fixed: bars.some((b) => b.fixed > 0) }
  if (bars.every((b) => b.jar.spent_vnd === 0 && !b.jar.previous_spent_vnd)) {
    return (
      <p className="mt-3 rounded-xl bg-surface-2 p-3 text-small text-ink-2" data-testid="by-jar-empty">
        Kỳ này bạn chưa chi gì.
      </p>
    )
  }
  return (
    <figure className="mt-2" data-testid="spending-by-jar">
      <figcaption className="sr-only">{byJarCaption(data)}</figcaption>
      <ul className="divide-y divide-line" aria-label="Chi theo hũ kỳ này">
        {bars.map((bar, i) => {
          const { jar } = bar
          const color = jarColor(lookup.get(jar.jar)?.color_key ?? '')
          return (
            <li key={jar.jar} data-jar={jar.jar}>
              <Link to={`/jars/${encodeURIComponent(jar.jar)}`} aria-label={jarRowLabel(jar)} className="flex min-h-11 items-center gap-2 py-2.5">
                <span className="min-w-0 flex-1" aria-hidden>
                  <span className="flex items-center gap-2">
                    <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: color }} />
                    <span className="min-w-0 flex-1 truncate text-small font-semibold text-ink">{jar.name}</span>
                    <span className="num shrink-0 text-small font-bold text-ink">{formatVnd(jar.spent_vnd)}</span>
                  </span>
                  <Track bar={bar} color={color} animate={animate} index={i} />
                  {hasPrev && jar.previous_spent_vnd !== undefined && jar.change_vnd !== undefined && (
                    <span className="num mt-1 flex flex-wrap items-center gap-x-1 text-note text-ink-2">
                      Kỳ trước {formatVnd(jar.previous_spent_vnd)} · <Change change={jar.change_vnd} />
                    </span>
                  )}
                </span>
                <ChevronRight className="size-4 shrink-0 text-ink-3" aria-hidden />
              </Link>
            </li>
          )
        })}
      </ul>
      {!hasPrev && <p className="mt-1 text-note text-ink-2">Chưa có kỳ trước để so.</p>}
      <ul className="mt-2 flex flex-wrap items-center gap-x-3.5 gap-y-1 border-t border-line pt-2 text-note text-ink-2" aria-label="Chú giải">
        <li className="inline-flex items-center gap-1.5">
          <span className={cn('inline-block h-2.5 w-4 rounded-sm bg-ink-2', EDGE)} aria-hidden /> Chi thường
        </li>
        {seen.credit && (
          <li className="inline-flex items-center gap-1.5">
            <span className={cn('inline-block h-2.5 w-4 rounded-sm', EDGE)} style={creditDots('var(--text-secondary)')} aria-hidden /> Trả sau
          </li>
        )}
        {seen.fixed && (
          <li className="inline-flex items-center gap-1.5">
            <span className={cn('inline-block h-2.5 w-4 rounded-sm', EDGE)} style={FIXED_HATCH} aria-hidden /> Khoản cố định
          </li>
        )}
        {hasPrev && (
          <li className="inline-flex items-center gap-1.5">
            <span className="inline-block h-3.5 w-[3px] rounded-full bg-ink" aria-hidden /> Kỳ trước cùng ngày
          </li>
        )}
      </ul>
    </figure>
  )
}
