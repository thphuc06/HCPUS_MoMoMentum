import { JarIcon } from '@/components/JarIcon'
import { StatusChip } from '@/components/StatusChip'
import type { StressResultData } from '@/contracts/blocks'
import { formatAppDate, formatVnd } from '@/lib/format'
import { statusShortChip } from '@/lib/jar'

export function StressResult({ data }: { data: StressResultData }) {
  const status = statusShortChip(data.status)
  const emergencyJar = data.emergency_jar

  return (
    <section data-block="stress_result" className="space-y-3 rounded-card bg-surface p-4 shadow-card">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-subtitle font-semibold text-ink">{data.shock.label}</h3>
        <StatusChip kind={status.kind}>{status.label}</StatusChip>
      </header>
      <p className="text-small text-ink-2">{data.headline}</p>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-xl bg-surface-2 px-3 py-2">
        <span className="text-small text-ink-2">Điểm trước và sau</span>
        <strong className="num text-section text-ink">{data.score_before} → {data.score_after}</strong>
        <span className="num text-small text-ink-2">{data.score_delta} điểm</span>
      </div>
      <dl className="space-y-2 text-small">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          <dt className="text-ink-2">Toàn bộ ví</dt>
          <dd className="num font-semibold text-ink">
            {data.runway_days_total === undefined
              ? `Trụ hết ${data.horizon_days} ngày dự báo`
              : `Trụ được ${data.runway_days_total} ngày`}
          </dd>
        </div>
        {emergencyJar && data.runway_days_emergency !== undefined && (
          <div className="flex flex-wrap items-center justify-between gap-x-3">
            <dt className="flex items-center gap-2 text-ink-2">
              <JarIcon colorKey={emergencyJar.color_key} iconKey={emergencyJar.icon_key} size={24} />
              Hũ {emergencyJar.name}
            </dt>
            <dd className="num font-semibold text-ink">{data.runway_days_emergency} ngày</dd>
          </div>
        )}
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          <dt className="text-ink-2">Khoản thiếu{data.shortfall_from && ` từ ${formatAppDate(data.shortfall_from)}`}</dt>
          <dd className="num font-semibold text-ink">{formatVnd(data.shortfall_vnd)}</dd>
        </div>
      </dl>
    </section>
  )
}
