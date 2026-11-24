import { lazy, Suspense, useMemo, useState } from 'react'
import type { CashflowResponse } from '@/api/cashflowSchemas'
import { Disclosure } from '@/components/ui/Disclosure'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDayMonth } from '@/lib/dates'
import { formatVnd } from '@/lib/format'
import { rangeLabel, trendCaption, trendMeasure, trendRows, trendSummary, TREND_MIN_DAYS } from './model'

// B5 "So với kỳ trước": câu ngắn dựng từ chênh lệch server trả, dòng đọc số `aria-live`, biểu đồ Recharts tải lười, thanh kéo
// `range` cao 44 px để chọn ngày (đường chính cho bàn phím và trình đọc màn hình), bảng `sr-only` đủ từng ngày. Mặc định vẽ chi thường
// ngày (bỏ khoản trả nghĩa vụ) khi server có phần tách. Kỳ mới bắt đầu (ngày 1 đến 2) chỉ hiện số. Cách tính trong "Cách tính" (§9).

const SpendingTrendChart = lazy(() => import('./SpendingTrendChart'))

export function SpendingTrend({ data, animate = false, chartSize }: {
  data: CashflowResponse
  animate?: boolean
  /** Chỉ cho test: kích thước cố định của biểu đồ. */
  chartSize?: { width: number; height: number }
}) {
  const measure = trendMeasure(data)
  const rows = useMemo(() => trendRows(data, measure), [data, measure])
  const today = data.period.day_index
  const [active, setActive] = useState<number | null>(null)
  const row = active !== null ? rows.find((r) => r.day === active) : undefined
  const nothing = rows.every((r) => !r.current && !r.previous)
  const early = today < TREND_MIN_DAYS
  const what = measure === 'regular' ? 'Chi thường ngày' : 'Tổng chi'
  const readout = (r: (typeof rows)[number]) =>
    `Ngày ${r.day} của kỳ: kỳ này ${r.current !== undefined ? formatVnd(r.current) : 'chưa tới'}${data.previous ? `, kỳ trước ${r.previous !== undefined ? formatVnd(r.previous) : 'không có'}` : ''}`

  if (nothing) {
    return (
      <p className="mt-3 rounded-xl bg-surface-2 p-3 text-small text-ink-2" data-testid="trend-empty">
        Kỳ này bạn chưa chi gì.
      </p>
    )
  }

  return (
    <figure className="mt-2" data-testid="spending-trend" data-measure={measure}>
      <p className="text-body font-medium text-ink" data-testid="trend-summary">
        {trendSummary(data, measure)}
      </p>
      <figcaption className="sr-only">{trendCaption(data, measure)}</figcaption>

      {early ? (
        <p className="mt-2 text-small text-ink-2" data-testid="trend-early">
          Kỳ mới bắt đầu, đường lũy kế hiện từ ngày {TREND_MIN_DAYS}.
        </p>
      ) : (
        <>
          <div className="mt-2 min-h-10 text-small leading-snug text-ink-2" aria-live="polite" data-testid="trend-readout">
            {row ? (
              <>
                <span className="font-semibold text-ink">Ngày {row.day}</span>
                {' · kỳ này '}
                <span className="num font-semibold text-brand-text">{row.current !== undefined ? formatVnd(row.current) : 'chưa tới'}</span>
                {data.previous && (
                  <>
                    {' · kỳ trước '}
                    <span className="num font-semibold text-ink">{row.previous !== undefined ? formatVnd(row.previous) : 'không có'}</span>
                  </>
                )}
              </>
            ) : (
              <>Chạm vào biểu đồ để xem từng ngày.</>
            )}
          </div>
          <div role="img" aria-label={trendCaption(data, measure)} data-testid="trend-chart">
            <Suspense fallback={<Skeleton className="h-[200px] w-full rounded-2xl" />}>
              <SpendingTrendChart rows={rows} today={today} activeDay={active} onActiveChange={setActive} animate={animate} fixedSize={chartSize} />
            </Suspense>
          </div>
          <label className="mt-1 block">
            <span className="sr-only">Chọn ngày của kỳ để xem chi lũy kế</span>
            <input
              type="range"
              min={1}
              max={rows.length}
              step={1}
              value={active ?? today}
              onChange={(e) => setActive(Number(e.target.value))}
              aria-label="Chọn ngày của kỳ để xem chi lũy kế"
              aria-valuetext={readout(row ?? rows[today - 1] ?? rows[0]!)}
              className="h-11 w-full accent-[var(--brand-primary)]"
            />
          </label>
          <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-note text-ink-2" aria-label="Chú giải">
            <li className="inline-flex items-center gap-1.5">
              <span className="inline-block h-0.5 w-4 bg-brand" aria-hidden /> Kỳ này
            </li>
            {data.previous && (
              <li className="inline-flex items-center gap-1.5">
                <span className="inline-block w-4 border-t-2 border-dashed border-ink-2" aria-hidden /> Kỳ trước
              </li>
            )}
            <li>Trục ngang: ngày của kỳ</li>
          </ul>
        </>
      )}

      <table className="sr-only">
        <caption>{what} lũy kế theo ngày của kỳ</caption>
        <thead>
          <tr>
            <th scope="col">Ngày</th>
            <th scope="col">Kỳ này</th>
            {data.previous && <th scope="col">Kỳ trước</th>}
          </tr>
        </thead>
        <tbody>
          {rows
            .filter((r) => r.current !== undefined || r.previous !== undefined)
            .map((r) => (
              <tr key={r.day}>
                <th scope="row">{r.day}</th>
                <td>{r.current !== undefined ? formatVnd(r.current) : 'chưa tới'}</td>
                {data.previous && <td>{r.previous !== undefined ? formatVnd(r.previous) : 'không có'}</td>}
              </tr>
            ))}
        </tbody>
      </table>

      <Disclosure label="Cách tính" className="mt-1 border-t border-line pt-1" panelClassName="space-y-1 pb-1 text-small text-ink-2">
        <p>
          {measure === 'regular'
            ? 'Đường là chi thường ngày cộng dồn, không gồm khoản trả theo lịch nghĩa vụ (tiền nhà, hóa đơn cố định). Món mua bằng Trả sau vẫn tính.'
            : 'Đường là tổng chi cộng dồn, gồm cả khoản trả nghĩa vụ.'}
        </p>
        <p>Ngày 1 là ngày lương {formatDayMonth(data.period.from_date)}.</p>
        {data.previous && (
          <p>
            Kỳ trước {rangeLabel(data.previous.from_date, data.previous.end_date ?? data.previous.to_date)}; so tới cùng ngày {today} ({rangeLabel(data.previous.from_date, data.previous.to_date)}).
          </p>
        )}
      </Disclosure>
    </figure>
  )
}
