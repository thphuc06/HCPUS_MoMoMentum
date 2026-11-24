import { JarIcon } from '@/components/JarIcon'
import { StatusChip } from '@/components/StatusChip'
import type { StressResultData } from '@/contracts/blocks'
import { formatAppDate, formatVnd } from '@/lib/format'
import { statusShortChip } from '@/lib/jar'
import { useEntranceMotion } from '@/lib/motion'
import { RESILIENCE_BANDS, ResilienceGauge } from './ResilienceGauge'
import { RunwayBar } from './RunwayBar'

/**
 * Kết quả một cú sốc (cảnh 3, Figma R3): đồng hồ điểm chạy từ điểm trước xuống điểm sau, rồi "trụ được N ngày" là số lớn và
 * thanh so với khoảng mô phỏng. Mọi số lấy từ khối `stress_result`.
 *
 * `animateScore` (màn Mô phỏng cú sốc): mỗi lần mở là một lần mô phỏng mới nên luôn chạy. Trong chat thì chạy một lần cho mỗi
 * khối trong phiên. Giảm chuyển động thì cả hai nơi hiện thẳng trạng thái cuối.
 */
export function StressResult({
  data,
  heading: Heading = 'h3',
  animateScore = false,
}: {
  data: StressResultData
  heading?: 'h2' | 'h3'
  animateScore?: boolean
}) {
  const status = statusShortChip(data.status)
  const emergencyJar = data.emergency_jar
  const animate = useEntranceMotion(animateScore ? undefined : `stress:${data.shock.shock_id}:${data.basis.computed_at}:${data.score_after}`)

  return (
    <section data-block="stress_result" className="space-y-4 rounded-card bg-surface p-4 shadow-card">
      <div className="space-y-2">
        <header className="flex flex-wrap items-start justify-between gap-2">
          <Heading className="text-subtitle font-semibold text-ink">{data.shock.label}</Heading>
          <StatusChip kind={status.kind}>{status.label}</StatusChip>
        </header>
        <p className="text-small text-ink-2">{data.headline}</p>
      </div>

      <div className="text-center" data-testid="stress-score">
        <ResilienceGauge score={data.score_after} band={data.band_after} from={data.score_before} fromBand={data.band_before} animate={animate} />
        <p className="flex flex-wrap items-baseline justify-center gap-x-2 text-small text-ink-2">
          <span className="sr-only">Điểm trước và sau</span>
          <strong className="num text-subtitle text-ink">{`${data.score_before} → ${data.score_after}`}</strong>
          <span className="num">{data.score_delta} điểm</span>
        </p>
        <p className="text-small text-ink-2">
          Nhóm điểm {RESILIENCE_BANDS[data.band_before].label} → {RESILIENCE_BANDS[data.band_after].label}
        </p>
      </div>

      <RunwayBar days={data.runway_days_total} horizonDays={data.horizon_days} status={data.status} animate={animate} />

      <dl className="space-y-2 border-t border-line pt-3 text-small">
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
