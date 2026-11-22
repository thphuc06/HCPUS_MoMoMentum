import type { ReactNode } from 'react'
import { ArrowRight, TrendingUp } from 'lucide-react'
import type { CoverageChangeData } from '@/contracts/blocks'
import { formatRatioPercent, formatVnd } from '@/lib/format'

const REFRESH: Record<CoverageChangeData['forecast_refresh'], string> = {
  done: 'Dự báo đã được tính lại với dữ liệu mới.',
  queued: 'Dự báo đang được tính lại, vài giây nữa sẽ có số mới.',
  skipped: 'Không có dòng nào được thêm nên dự báo giữ nguyên.',
}

/**
 * Figma I4 (24:2347): độ phủ dữ liệu trước → sau một lần nạp, số dòng đã thêm, tổng chi ngoài ví vừa thêm. Mọi số do server
 * tính (khối `coverage_change`); giao diện chỉ đổi tỷ lệ 0..1 thành phần trăm. Dùng chung cho màn Nạp dữ liệu và chat.
 */
export function CoverageChange({ data, actions }: { data: CoverageChangeData; actions?: ReactNode }) {
  const hasRatios = data.before !== undefined && data.after !== undefined
  return (
    <section data-block="coverage_change" aria-labelledby={`cov-${data.job_id}`} className="rounded-card bg-surface p-4 shadow-card">
      <header className="flex items-center gap-3">
        <span className="grid size-12 shrink-0 place-items-center rounded-full bg-ok-bg text-ok-fg">
          <TrendingUp className="size-6" aria-hidden />
        </span>
        <h2 id={`cov-${data.job_id}`} className="text-section font-bold text-ink">
          {hasRatios ? 'Độ phủ dữ liệu tăng' : 'Đã cập nhật dữ liệu'}
        </h2>
      </header>

      {hasRatios ? (
        <p className="mt-4 flex items-center justify-center gap-3" data-testid="coverage-ratios" aria-label={`Độ phủ dữ liệu từ ${formatRatioPercent(data.before!)} lên ${formatRatioPercent(data.after!)}`}>
          <span className="num text-title font-bold text-ink-2">{formatRatioPercent(data.before!)}</span>
          <ArrowRight className="size-6 text-ink-2" aria-hidden />
          <span className="num text-display font-extrabold text-ok-fg">{formatRatioPercent(data.after!)}</span>
        </p>
      ) : (
        <p className="mt-3 text-small text-ink-2">Chưa tính được độ phủ dữ liệu (chưa có thu nhập trong khoảng dự báo).</p>
      )}

      <dl className="mt-4 space-y-1.5 text-body">
        <div className="flex justify-between gap-3">
          <dt className="text-ink-2">Số dòng đã thêm</dt>
          <dd className="num font-semibold text-ink" data-testid="rows-added">
            {data.rows_added}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-ink-2">Chi ngoài ví vừa thêm</dt>
          <dd className="num font-semibold text-ink">{formatVnd(data.external_spend_added_vnd)}</dd>
        </div>
        {data.external_income_added_vnd !== undefined && (
          <div className="flex justify-between gap-3">
            <dt className="text-ink-2">Thu nhập ngoài ví vừa thêm</dt>
            <dd className="num font-semibold text-ink">{formatVnd(data.external_income_added_vnd)}</dd>
          </div>
        )}
        {data.jars_affected.length > 0 && (
          <div className="flex justify-between gap-3">
            <dt className="text-ink-2">Hũ có thêm lịch sử chi</dt>
            <dd className="text-right font-semibold text-ink">{data.jars_affected.map((j) => j.name).join(', ')}</dd>
          </div>
        )}
      </dl>

      <p className="mt-3 rounded-2xl bg-surface-2 px-3 py-2 text-small font-semibold text-ink">Số dư hũ không đổi — đây là chi tiêu ngoài ví.</p>
      <p className="mt-2 text-note text-ink-2">{REFRESH[data.forecast_refresh]}</p>
      {actions && <div className="mt-4 flex flex-col gap-2.5">{actions}</div>}
    </section>
  )
}

/**
 * Hũ bị ảnh hưởng nhiều nhất để mở "Xem dự báo cập nhật": trong `jars_affected`, hũ có tổng chi ngoài ví lớn nhất trong các
 * dòng ĐÃ THÊM của bảng duyệt (chỉ để chọn đích điều hướng, không phải số nghiệp vụ hiển thị). Không có bảng duyệt thì lấy
 * hũ đầu tiên server liệt kê. Không có hũ nào (chỉ có thu nhập) thì null.
 */
export function mostAffectedJar(data: CoverageChangeData, rows?: ReadonlyArray<{ kind: string; review_status: string; amount_vnd: number; suggested_jar?: { code: string } }>): string | null {
  const affected = new Set(data.jars_affected.map((j) => j.code))
  if (affected.size === 0) return null
  const sums = new Map<string, number>()
  for (const r of rows ?? []) {
    const code = r.suggested_jar?.code
    if (r.kind !== 'expense' || r.review_status !== 'approved' || !code || !affected.has(code)) continue
    sums.set(code, (sums.get(code) ?? 0) + r.amount_vnd)
  }
  let best: string | null = null
  for (const [code, sum] of sums) if (best === null || sum > sums.get(best)!) best = code
  return best ?? data.jars_affected[0]!.code
}
