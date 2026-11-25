import { lazy, Suspense, useMemo, useState } from 'react'
import { AlertTriangle, Info } from 'lucide-react'
import { JarIcon } from '@/components/JarIcon'
import { StatusChip } from '@/components/StatusChip'
import { Disclosure } from '@/components/ui/Disclosure'
import { Skeleton } from '@/components/ui/skeleton'
import { CONFIDENCE_LABEL, jarStatusChip, MAY_RUN_OUT, mayRunOutBeforePayday, mayRunOutText, shownRunoutDate, statusShortChip } from '@/lib/jar'
import { formatSimMoment, formatRatioPercent, formatShortfallChance, formatVnd, formatVndShort } from '@/lib/format'
import { diffDays, formatDayMonth } from '@/lib/dates'
import { useEntranceMotion } from '@/lib/motion'
import type { ForecastCompare, ForecastTimelineData } from '@/contracts/blocks'
import { buildChartModel, idleSaving, noOutflowExpected, rowAt } from './model'

// Recharts (~118 KB gzip) tải riêng, không nằm trong phần tải đầu.
const ForecastChart = lazy(() => import('./ForecastChart'))

/** Câu tóm tắt dựng từ số server trả (ngày cạn, ngày lương, số ngày tới lương); không tính lại gì. */
export function forecastSummary(d: ForecastTimelineData): string {
  const name = d.jar.name
  const payday = formatDayMonth(d.payday.date)
  const runout = shownRunoutDate(d)
  // Hũ không có gì rút tiền (#39, hũ để dành chưa có tiền): không nói "hết tiền" hay "đủ tới kỳ lương" như thể có khoản để chi.
  if (noOutflowExpected(d)) {
    // Hũ để dành còn tiền (#39 lần hai): không nói "không có khoản chi"; cùng lời với `_no_outflow_sentence` của yofina_core.blocks.
    const saving = idleSaving(d)
    if (saving?.kind === 'salary') return `Hũ ${name} dự kiến nhận thêm ${formatVnd(saving.amountVnd)} khi lương về ${formatDayMonth(saving.date)}.`
    if (saving?.kind === 'flat') return `Hũ ${name} dự kiến giữ nguyên số dư trong ${d.horizon_days} ngày tới.`
    if (saving?.kind === 'steady') return `Số dư hũ ${name} dự kiến không xuống dưới mức hôm nay trong ${d.horizon_days} ngày tới.`
    return d.start_balance_vnd === 0
      ? `Hũ ${name} chưa có tiền và không có khoản chi nào dự kiến trong ${d.horizon_days} ngày tới.`
      : `Hũ ${name} không có khoản chi nào dự kiến trong ${d.horizon_days} ngày tới; số dư không giảm.`
  }
  // Hũ đã hết tiền (0 ₫): không nói "dự kiến cạn" như thể còn tiền để cạn.
  if (d.start_balance_vnd <= 0) {
    return `Hũ ${name} đang hết tiền (${formatVnd(d.start_balance_vnd)}). Kỳ lương kế tiếp ngày ${payday}, còn ${d.payday.days_until} ngày nữa.`
  }
  // Hũ thưa (#25): server không nêu ngày cạn cụ thể.
  if (mayRunOutBeforePayday(d)) return `Hũ ${name} có thể cạn trước ngày lương ${payday} (còn ${d.payday.days_until} ngày).`
  if (runout) {
    if (runout < d.payday.date) {
      // Hai con số khác nhau, nói rõ để khỏi lẫn: khoảng trống từ ngày cạn tới lương (hiệu hai ngày server trả) và số ngày từ hôm nay.
      const gap = diffDays(runout, d.payday.date)
      return `Hũ ${name} dự kiến cạn ngày ${formatDayMonth(runout)}, ${gap} ngày trước kỳ lương ${payday} (hôm nay còn ${d.payday.days_until} ngày tới lương).`
    }
    return `Hũ ${name} dự kiến cạn ngày ${formatDayMonth(runout)}, sau kỳ lương ${payday}.`
  }
  if (d.status === 'short') return `Hũ ${name} có khả năng hụt trước kỳ lương ${payday} (còn ${d.payday.days_until} ngày).`
  if (d.status === 'tight')
    return `Hũ ${name} sát: dự kiến còn rất ít tiền trước kỳ lương ${payday} (còn ${d.payday.days_until} ngày).`
  return `Hũ ${name} dự kiến đủ tới kỳ lương ${payday} (còn ${d.payday.days_until} ngày).`
}

/**
 * Dòng chính hiện ngay (Luật chữ, ui-design-review.md §9: tối đa khoảng 12 từ). Câu đầy đủ của `forecastSummary` nằm trong
 * "Chi tiết dự báo". Số lấy từ khối; khoảng trống từ ngày cạn tới lương là hiệu hai ngày server trả.
 */
export function forecastHeadline(d: ForecastTimelineData): string {
  const payday = formatDayMonth(d.payday.date)
  const runout = shownRunoutDate(d)
  if (noOutflowExpected(d)) {
    const saving = idleSaving(d)
    if (saving?.kind === 'salary') return `Dự kiến thêm ${formatVnd(saving.amountVnd)} khi lương về ${formatDayMonth(saving.date)}.`
    if (saving?.kind === 'flat') return `Số dư giữ nguyên trong ${d.horizon_days} ngày tới.`
    if (saving?.kind === 'steady') return `Số dư không xuống dưới mức hôm nay trong ${d.horizon_days} ngày tới.`
    const days = `trong ${d.horizon_days} ngày.`
    return d.start_balance_vnd === 0 ? `Chưa có tiền, không có khoản chi dự kiến ${days}` : `Không có khoản chi dự kiến ${days}`
  }
  if (d.start_balance_vnd <= 0) return `Đang hết tiền, ${d.payday.days_until} ngày nữa tới lương ${payday}.`
  if (mayRunOutBeforePayday(d)) return `${mayRunOutText(d.p_shortfall)}.`
  if (runout) {
    if (runout < d.payday.date) return `Cạn ${formatDayMonth(runout)}, ${diffDays(runout, d.payday.date)} ngày trước lương ${payday}.`
    return `Cạn ${formatDayMonth(runout)}, sau lương ${payday}.`
  }
  if (d.status === 'short') return `Có khả năng hụt trước lương ${payday}.`
  if (d.status === 'tight') return `Còn rất ít tiền trước lương ${payday}.`
  return `Đủ tới lương ${payday}, còn ${d.payday.days_until} ngày.`
}

/**
 * Mô tả biểu đồ cho trình đọc màn hình: loại biểu đồ, khoảng ngày và điều chính cần đọc (ngày cạn, trước và sau). Số lấy từ khối,
 * không tự tính; chi tiết từng ngày đọc bằng thanh chọn ngày bên dưới.
 */
export function chartLabel(d: ForecastTimelineData): string {
  const base = `Biểu đồ dự báo số dư hũ ${d.jar.name} ${d.horizon_days} ngày`
  const hidden = d.runout_date_shown === false
  const runout = (p: { status: ForecastTimelineData['status']; runout_date?: string }) =>
    hidden
      ? p.status === 'short' ? MAY_RUN_OUT.toLowerCase() : p.status === 'tight' ? 'sát trước kỳ lương' : 'đủ tới kỳ lương'
      : p.runout_date ? `cạn ngày ${formatDayMonth(p.runout_date)}` : 'không cạn trong kỳ dự báo'
  if (d.compare) return `${base}: đường Trước nét đứt ${runout(d)}, đường Sau ${runout(d.compare.after)}.`
  return `${base}: ${runout(d)}, kỳ lương ${formatDayMonth(d.payday.date)}.`
}

type AfterPath = ForecastCompare['after']

function pathLine(path: { status: ForecastTimelineData['status']; runout_date?: string }, hidden: boolean): string {
  if (hidden && path.status === 'short') return MAY_RUN_OUT
  if (path.runout_date && !hidden) return `Dự kiến cạn ngày ${formatDayMonth(path.runout_date)}`
  return path.status === 'ok' ? 'Đủ tới kỳ lương' : path.status === 'tight' ? 'Sát, còn rất ít tiền' : 'Có khả năng hụt'
}

/**
 * Biến thể trước-sau (H3a): hai cột TRƯỚC và SAU với trạng thái đủ/sát/hụt (biểu tượng + chữ), ngày cạn và khả năng hụt, rồi
 * chênh lệch do engine tính sẵn (`delta`, cùng dãy số ngẫu nhiên cho hai bên). Chỉ vẽ số server trả.
 */
export function CompareSummary({ data, compare }: { data: ForecastTimelineData; compare: ForecastCompare }) {
  const after: AfterPath = compare.after
  // Hũ thưa (#25): không nêu ngày cạn ở cột nào, không nói ngày cạn sớm hay muộn hơn bao nhiêu ngày.
  const hidden = data.runout_date_shown === false
  const cols = [
    { key: 'before', title: 'Trước', path: data },
    { key: 'after', title: 'Sau', path: after },
  ] as const
  const d = compare.delta
  return (
    <div data-testid="forecast-compare" className="mt-3">
      <p className="text-body font-semibold text-ink" data-testid="compare-label">
        Nếu {compare.label}
      </p>
      <div className="mt-2 grid grid-cols-2 gap-2">
        {cols.map(({ key, title, path }) => {
          const chip = statusShortChip(path.status)
          return (
            <div key={key} data-col={key} className="rounded-2xl bg-surface-2 p-3">
              <p className="text-small font-semibold text-ink-2">{title}</p>
              <StatusChip kind={chip.kind} className="mt-1">
                {chip.label}
              </StatusChip>
              <p className="mt-1.5 text-small text-ink">{pathLine(path, hidden)}</p>
              {path.p_shortfall !== undefined && <p className="num text-small text-ink-2">Khả năng hụt: {formatShortfallChance(path.p_shortfall).toLowerCase()}</p>}
            </div>
          )
        })}
      </div>
      <ul className="mt-2 space-y-1 text-small text-ink" aria-label="Chênh lệch trước và sau">
        <li>
          Số dư giữa thấp nhất {d.min_balance_delta_vnd < 0 ? 'giảm' : 'tăng'} <span className="num font-semibold">{formatVnd(Math.abs(d.min_balance_delta_vnd))}</span>
          {after.min_balance_p50_vnd !== undefined && (
            <span className="text-ink-2">
              {' '}
              (còn <span className="num">{formatVnd(after.min_balance_p50_vnd)}</span>)
            </span>
          )}
        </li>
        {!hidden && d.runout_shift_days !== undefined && d.runout_shift_days !== 0 && (
          <li>
            Ngày cạn {d.runout_shift_days < 0 ? 'sớm hơn' : 'muộn hơn'} <span className="num font-semibold">{Math.abs(d.runout_shift_days)} ngày</span>
          </li>
        )}
        {d.p_shortfall_delta !== undefined && d.p_shortfall_delta !== 0 && (
          <li>
            Khả năng hụt {d.p_shortfall_delta > 0 ? 'tăng' : 'giảm'} <span className="num font-semibold">{Math.round(Math.abs(d.p_shortfall_delta) * 100)} điểm phần trăm</span>
          </li>
        )}
      </ul>
      {compare.common_random_numbers && (
        <Disclosure label="Vì sao so được?" className="mt-1" panelClassName="pb-1 text-note text-ink-2">
          <p>Hai đường dùng cùng dãy số ngẫu nhiên ({compare.n_paths.toLocaleString('vi-VN')} đường mô phỏng) nên chênh lệch không do nhiễu.</p>
        </Disclosure>
      )}
    </div>
  )
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
  const chip = jarStatusChip(data.status, shownRunoutDate(data), data.start_balance_vnd <= 0)
  const events = model.events
  const compare = data.compare
  const extraEvents = compare?.after.events ?? []
  // Đường "Sau" vẽ dần một lần cho mỗi khối what-if trong phiên (mở lại chat không vẽ lại); giảm chuyển động thì hiện thẳng.
  const animateAfter = useEntranceMotion(compare ? `forecast:${data.jar.code}:${data.computed_at}:${compare.label}` : undefined) && !!compare

  return (
    <section data-block="forecast_timeline" data-status={data.status} className={`rounded-card bg-surface p-4 shadow-card ${className ?? ''}`}>
      <header className="flex items-center gap-3">
        <JarIcon colorKey={data.jar.color_key} iconKey={data.jar.icon_key} size={36} />
        <h3 className="min-w-0 flex-1 text-subtitle leading-5 font-semibold text-ink">Dự báo hũ {data.jar.name}</h3>
        <StatusChip kind={chip.kind}>{chip.label}</StatusChip>
      </header>

      {compare ? (
        <CompareSummary data={data} compare={compare} />
      ) : (
        <p className="mt-3 text-body font-medium text-ink" data-testid="forecast-headline">
          {forecastHeadline(data)}
        </p>
      )}

      {(data.is_initial_estimate || data.stale) && (
        <div className="mt-2 flex flex-wrap gap-2">
          {data.is_initial_estimate && <StatusChip kind="warn">Ước lượng ban đầu</StatusChip>}
          {data.stale && <StatusChip kind="warn">Số liệu cũ</StatusChip>}
        </div>
      )}
      {data.is_initial_estimate && (
        <p className="mt-1.5 flex items-start gap-1.5 text-small text-ink-2">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn-fg" aria-hidden />
          <span>Mới có {data.history_days} ngày dữ liệu.</span>
        </p>
      )}
      {data.stale && (
        <p className="mt-1.5 flex items-start gap-1.5 text-small text-ink-2">
          <Info className="mt-0.5 size-4 shrink-0 text-warn-fg" aria-hidden />
          <span>Số liệu dự báo chưa được cập nhật theo ngày mô phỏng hôm nay.</span>
        </p>
      )}

      <div className="mt-3 min-h-10 text-small leading-snug text-ink-2" aria-live="polite" data-testid="chart-readout">
        {row ? (
          <>
            <span className="font-semibold text-ink">{formatDayMonth(row.date)}</span>
            {compare ? ' · trước ' : ' · giữa '}
            <span className="num font-semibold text-ink">{formatVndShort(row.p50)}</span>
            {row.after !== undefined && (
              <>
                {' · sau '}
                <span className="num font-semibold text-brand-text">{formatVndShort(row.after)}</span>
              </>
            )}
            {' · khoảng 80% khả năng từ '}
            <span className="num">{formatVndShort(row.p10)}</span>
            {' đến '}
            <span className="num">{formatVndShort(row.p90)}</span>
          </>
        ) : (
          <>Chạm vào biểu đồ để xem từng ngày.</>
        )}
      </div>

      <div role="img" aria-label={chartLabel(data)} data-testid="forecast-chart" data-animate={animateAfter ? 'after' : undefined}>
        <Suspense fallback={<Skeleton className="h-[240px] w-full rounded-2xl" />}>
          <ForecastChart data={data} model={model} activeX={activeX} onActiveChange={setActiveX} fixedSize={chartSize} animateAfter={animateAfter} />
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
          <span className={`inline-block h-0.5 w-4 ${compare ? 'border-t-2 border-dashed border-blue' : 'bg-blue'}`} /> {compare ? 'Trước' : 'Số dư giữa'}
        </li>
        {compare && (
          <li className="inline-flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 bg-brand" /> Sau
          </li>
        )}
        {model.runout && (
          <li className="inline-flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-sm bg-bad-bg ring-1 ring-bad-line" /> Vùng hụt
          </li>
        )}
      </ul>

      {/* Câu tóm tắt đầy đủ, mốc tiền và chỉ số chất lượng: chữ phụ, thu gọn (ui-design-review.md §3.2 #10, §9). */}
      <Disclosure label="Chi tiết dự báo" className="mt-2 border-t border-line pt-1" panelClassName="pb-1">
      {!compare && (
        <p className="pt-1 text-small text-ink" data-testid="forecast-summary">
          {forecastSummary(data)}
        </p>
      )}
      {data.is_initial_estimate && <p className="mt-2 text-small text-ink-2">Đây mới là ước lượng sơ bộ; càng ghi nhiều giao dịch, dự báo càng sát.</p>}
      {data.stale && <p className="mt-2 text-small text-ink-2">Mở lại màn này hoặc thử lại sau để tính lại.</p>}
      {extraEvents.length > 0 && (
        <ul className="mt-3 space-y-1.5 border-t border-line pt-3 text-small" aria-label="Mốc phát sinh thêm do kịch bản" data-testid="forecast-extra-events">
          {extraEvents.map((e) => (
            <li key={`${e.date}-${e.label}`} className="flex items-center justify-between gap-3" data-event={e.kind}>
              <span className="text-ink">
                {e.label} · {formatDayMonth(e.date)} <span className="text-ink-2">(phát sinh thêm)</span>
              </span>
              <span className={`num font-semibold ${e.kind === 'salary' ? 'text-ok-fg' : 'text-warn-fg'}`}>
                {e.kind === 'salary' ? '+' : '−'}
                {formatVnd(e.amount_vnd)}
              </span>
            </li>
          ))}
        </ul>
      )}

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
            <dt className="text-ink-2">Khả năng hụt trước kỳ lương{compare ? ' (trước)' : ''}</dt>
            <dd className="num font-semibold text-ink" data-testid="p-shortfall">
              {formatShortfallChance(data.p_shortfall)}
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
      </Disclosure>

      <footer className="mt-3 flex items-center justify-between gap-3 text-note text-ink-2">
        <span>Cập nhật {formatSimMoment(data.origin_date, data.computed_at)} · Ví mô phỏng</span>
        {onAskWhy && (
          <button type="button" onClick={onAskWhy} className="min-h-11 px-2 text-small font-semibold text-brand-text">
            Vì sao
          </button>
        )}
      </footer>
    </section>
  )
}
