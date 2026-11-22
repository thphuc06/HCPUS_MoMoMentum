import { lazy, Suspense, useMemo, useState } from 'react'
import { AlertTriangle, Info } from 'lucide-react'
import { JarIcon } from '@/components/JarIcon'
import { StatusChip } from '@/components/StatusChip'
import { Skeleton } from '@/components/ui/skeleton'
import { CONFIDENCE_LABEL, jarStatusChip } from '@/lib/jar'
import { formatDateTime, formatRatioPercent, formatVnd, formatVndShort } from '@/lib/format'
import { formatDayMonth } from '@/lib/dates'
import type { ForecastTimelineData } from '@/contracts/blocks'
import { buildChartModel, rowAt } from './model'

// Recharts (~118 KB gzip) tải riêng, không nằm trong phần tải đầu.
const ForecastChart = lazy(() => import('./ForecastChart'))

/** Câu tóm tắt dựng từ số server trả (ngày cạn, ngày lương, số ngày tới lương); không tính lại gì. */
export function forecastSummary(d: ForecastTimelineData): string {
  const name = d.jar.name
  const payday = formatDayMonth(d.payday.date)
  if (d.runout_date) {
    if (d.runout_date < d.payday.date) {
      return `Hũ ${name} dự kiến cạn ngày ${formatDayMonth(d.runout_date)}, còn ${d.payday.days_until} ngày nữa mới tới kỳ lương ${payday}.`
    }
    return `Hũ ${name} dự kiến cạn ngày ${formatDayMonth(d.runout_date)}, sau kỳ lương ${payday}.`
  }
  if (d.status === 'short') return `Hũ ${name} có khả năng hụt trước kỳ lương ${payday} (còn ${d.payday.days_until} ngày).`
  return `Hũ ${name} dự kiến đủ tới kỳ lương ${payday} (còn ${d.payday.days_until} ngày).`
}

/**
 * ForecastBlock (Figma 7:248): dùng CHUNG cho màn Chi tiết hũ và khối `forecast_timeline` trong chat (qua registry), nên
 * hai nơi cùng số. Hiện ngày cạn, xác suất hụt HOẶC nhóm tin cậy (theo trường nào có), độ phủ dữ liệu, thời điểm tính,
 * "ước lượng ban đầu" và "số liệu cũ" khi cờ bật. Chạm vào biểu đồ (hoặc kéo thanh chọn ngày) để đọc số từng ngày.
 */
export function ForecastBlock({
  data,
  onAskWhy,
  chartSize,
  className,
}: {
  data: ForecastTimelineData
  onAskWhy?: () => void
  /** Chỉ cho test: kích thước cố định của biểu đồ. */
  chartSize?: { width: number; height: number }
  className?: string
}) {
  const model = useMemo(() => buildChartModel(data), [data])
  const [activeX, setActiveX] = useState<number | null>(null)
  const row = rowAt(model, activeX)
  const chip = jarStatusChip(data.status, data.runout_date)
  const events = model.events

  return (
    <section data-block="forecast_timeline" data-status={data.status} className={`rounded-card bg-surface p-4 shadow-card ${className ?? ''}`}>
      <header className="flex items-center gap-3">
        <JarIcon colorKey={data.jar.color_key} iconKey={data.jar.icon_key} size={36} />
        <h3 className="min-w-0 flex-1 text-subtitle leading-5 font-semibold text-ink">Dự báo hũ {data.jar.name}</h3>
        <StatusChip kind={chip.kind}>{chip.label}</StatusChip>
      </header>

      <p className="mt-3 text-body font-medium text-ink" data-testid="forecast-summary">
        {forecastSummary(data)}
      </p>

      {(data.is_initial_estimate || data.stale) && (
        <div className="mt-2 flex flex-wrap gap-2">
          {data.is_initial_estimate && <StatusChip kind="warn">Ước lượng ban đầu</StatusChip>}
          {data.stale && <StatusChip kind="warn">Số liệu cũ</StatusChip>}
        </div>
      )}
      {data.is_initial_estimate && (
        <p className="mt-1.5 flex items-start gap-1.5 text-small text-ink-2">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn-fg" aria-hidden />
          <span>Mới có {data.history_days} ngày dữ liệu nên đây mới là ước lượng sơ bộ; càng ghi nhiều, dự báo càng sát.</span>
        </p>
      )}
      {data.stale && (
        <p className="mt-1.5 flex items-start gap-1.5 text-small text-ink-2">
          <Info className="mt-0.5 size-4 shrink-0 text-warn-fg" aria-hidden />
          <span>Số liệu dự báo chưa được cập nhật theo ngày mô phỏng hôm nay. Mở lại màn này hoặc thử lại sau để tính lại.</span>
        </p>
      )}

      <div className="mt-3 min-h-10 text-small leading-snug text-ink-2" aria-live="polite" data-testid="chart-readout">
        {row ? (
          <>
            <span className="font-semibold text-ink">{formatDayMonth(row.date)}</span>
            {' · giữa '}
            <span className="num font-semibold text-ink">{formatVndShort(row.p50)}</span>
            {' · khoảng 80% khả năng từ '}
            <span className="num">{formatVndShort(row.p10)}</span>
            {' đến '}
            <span className="num">{formatVndShort(row.p90)}</span>
          </>
        ) : (
          <>Chạm vào biểu đồ hoặc kéo thanh bên dưới để xem số dư từng ngày. Dải màu là khoảng 80% khả năng.</>
        )}
      </div>

      <div role="img" aria-label={`Biểu đồ dự báo số dư hũ ${data.jar.name} ${data.horizon_days} ngày`} data-testid="forecast-chart">
        <Suspense fallback={<Skeleton className="h-[240px] w-full rounded-2xl" />}>
          <ForecastChart data={data} model={model} activeX={activeX} onActiveChange={setActiveX} fixedSize={chartSize} />
        </Suspense>
      </div>

      <label className="mt-1 block text-note text-ink-2">
        <span className="sr-only">Chọn ngày để xem số dư dự báo</span>
        <input
          type="range"
          min={0}
          max={model.rows.length - 1}
          step={1}
          value={Math.max(0, model.rows.findIndex((r) => r.x === activeX))}
          onChange={(e) => setActiveX(model.rows[Number(e.target.value)]?.x ?? null)}
          aria-label="Chọn ngày để xem số dư dự báo"
          aria-valuetext={row ? `${formatDayMonth(row.date)}, giữa ${formatVnd(row.p50)}` : undefined}
          className="h-11 w-full accent-[var(--accent-blue)]"
        />
      </label>

      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-note text-ink-2" aria-label="Chú giải">
        <li className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-4 rounded-sm bg-blue opacity-30" /> Dải 80%
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 bg-blue" /> Số dư giữa
        </li>
        {model.runout && (
          <li className="inline-flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-sm bg-bad-bg ring-1 ring-bad-line" /> Vùng hụt
          </li>
        )}
      </ul>

      {events.length > 0 && (
        <ul className="mt-3 space-y-1.5 border-t border-line pt-3 text-small" aria-label="Mốc tiền ra và tiền vào" data-testid="forecast-events">
          {events.map((e) => (
            <li key={`${e.date}-${e.label}`} className="flex items-center justify-between gap-3" data-event={e.kind}>
              <span className="text-ink">
                {e.label} · {formatDayMonth(e.date)}
              </span>
              <span className={`num font-semibold ${e.kind === 'salary' ? 'text-ok-fg' : 'text-warn-fg'}`}>
                {e.kind === 'salary' ? '+' : '−'}
                {formatVnd(e.amountVnd)}
                {e.amountMaxVnd ? ` đến ${formatVnd(e.amountMaxVnd)}` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-line pt-3 text-small" data-testid="forecast-meta">
        {data.p_shortfall !== undefined ? (
          <div>
            <dt className="text-ink-2">Khả năng hụt trước kỳ lương</dt>
            <dd className="num font-semibold text-ink" data-testid="p-shortfall">
              {formatRatioPercent(data.p_shortfall)}
            </dd>
          </div>
        ) : null}
        <div>
          <dt className="text-ink-2">Nhóm tin cậy</dt>
          <dd className="font-semibold text-ink" data-testid="confidence-band">
            {CONFIDENCE_LABEL[data.confidence_band]}
            {data.p_shortfall === undefined && <span className="block text-note font-normal text-ink-2">Chưa đủ cơ sở để nêu xác suất</span>}
          </dd>
        </div>
        <div>
          <dt className="text-ink-2">Độ phủ dữ liệu</dt>
          <dd className="num font-semibold text-ink" data-testid="coverage">
            {data.coverage !== undefined ? formatRatioPercent(data.coverage) : 'Chưa tính được'}
          </dd>
        </div>
        <div>
          <dt className="text-ink-2">Dữ liệu lịch sử</dt>
          <dd className="num font-semibold text-ink">{data.history_days} ngày</dd>
        </div>
      </dl>

      <footer className="mt-3 flex items-center justify-between gap-3 text-note text-ink-2">
        <span>Cập nhật {formatDateTime(data.computed_at)} · Ví mô phỏng</span>
        {onAskWhy && (
          <button type="button" onClick={onAskWhy} className="min-h-11 px-2 text-small font-semibold text-brand-text">
            Vì sao
          </button>
        )}
      </footer>
    </section>
  )
}
