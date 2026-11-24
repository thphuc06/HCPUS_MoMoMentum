import { useId, type CSSProperties } from 'react'
import type { CashflowResponse } from '@/api/cashflowSchemas'
import { Disclosure } from '@/components/ui/Disclosure'
import { cn } from '@/lib/cn'
import { formatVnd } from '@/lib/format'
import { cashflowCaption, incomeBar, periodNoun, rangeLabel } from './model'

// B7 "Thu và chi của kỳ" (spending-visualization.md §3): một hàng số gọn (lương vào, đã chi, còn lại) và một thanh so sánh trên
// thang max(lương, chi). `net_vnd` (lương trừ chi) do server trừ; tiền vào khác không tính là thu nhập nên chỉ nằm trong "Cách tính".
// Luật chữ (§9): số và nhãn ngắn hiện ngay; câu đầy đủ cho trình đọc màn hình; cách tính trong Disclosure.

const OVER_HATCH: CSSProperties = {
  backgroundImage: 'repeating-linear-gradient(45deg, var(--status-bad-line) 0 2px, var(--status-bad-bg) 2px 6px)',
}

export function PeriodCashflow({ data, animate = false }: { data: CashflowResponse; animate?: boolean }) {
  const titleId = useId()
  const c = data.current
  const bar = incomeBar(data)
  const noSalary = c.salary_income_vnd === 0
  const over = c.net_vnd < 0
  return (
    <section className="rounded-card bg-surface p-4 shadow-card" aria-labelledby={titleId} data-testid="period-cashflow">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id={titleId} className="min-w-0 flex-1 text-subtitle font-semibold text-ink">
          {periodNoun(data)} này
        </h2>
        <span className="num inline-flex h-7 items-center rounded-full bg-surface-2 px-2.5 text-note font-semibold text-ink-2">
          {rangeLabel(data.period.from_date, data.period.to_date)} · ngày {data.period.day_index}/{data.period.days_total}
        </span>
      </div>
      <p className="sr-only">{cashflowCaption(data)}</p>

      <dl className="mt-3 grid grid-cols-3 gap-2" aria-hidden>
        <div>
          <dt className="text-note text-ink-2">Lương vào</dt>
          <dd className="num text-small font-bold text-ink">{noSalary ? 'Chưa về' : formatVnd(c.salary_income_vnd)}</dd>
        </div>
        <div>
          <dt className="text-note text-ink-2">Đã chi</dt>
          <dd className="num text-small font-bold text-ink" data-testid="cashflow-spent">{formatVnd(c.spent_vnd)}</dd>
        </div>
        {!noSalary && (
          <div>
            <dt className="text-note text-ink-2">{over ? 'Chi quá lương' : 'Còn lại'}</dt>
            <dd className={cn('num text-small font-bold', over ? 'text-bad-fg' : 'text-ok-fg')} data-testid="cashflow-net">
              {formatVnd(Math.abs(c.net_vnd))}
            </dd>
          </div>
        )}
      </dl>

      {/* Thanh: cả thanh là lương (hoặc chi, khi chi vượt lương); phần tô là đã chi; phần vượt lương gạch chéo. */}
      <div className="relative mt-2 h-3 overflow-hidden rounded-md bg-surface-2 shadow-[inset_0_0_0_1px_var(--border-default)]" aria-hidden data-testid="cashflow-bar">
        <span
          className={cn('absolute inset-y-0 left-0 bg-blue', animate && 'motion-grow-x')}
          style={{ width: `${(bar.salaryMark ?? bar.spent) * 100}%` }}
          data-part="spent"
        />
        {bar.salaryMark !== undefined && (
          <span className="absolute inset-y-0 right-0" style={{ ...OVER_HATCH, left: `${bar.salaryMark * 100}%` }} data-part="over" />
        )}
      </div>
      {noSalary && <p className="mt-2 text-small text-ink-2">Lương kỳ này chưa về.</p>}

      <Disclosure label="Cách tính" className="mt-1" panelClassName="space-y-1 pb-1 text-small text-ink-2">
        <p>{over ? 'Chi quá lương' : 'Còn lại'} là lương vào trừ đã chi, chưa tính số dư từ trước.</p>
        {c.other_income_vnd > 0 && <p>Tiền vào khác {formatVnd(c.other_income_vnd)} không tính là thu nhập.</p>}
        <p>Đã chi gồm mọi khoản trả từ ví và bằng Trả sau, không gồm chuyển giữa hũ và chi ngoài ví.</p>
      </Disclosure>
    </section>
  )
}
