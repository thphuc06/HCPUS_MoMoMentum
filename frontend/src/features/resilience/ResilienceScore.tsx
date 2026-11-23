import type { ResilienceScoreData } from '@/contracts/blocks'
import { ResilienceGauge } from './ResilienceGauge'
import { ScoreRow } from './ScoreRow'

export function ResilienceScore({ data }: { data: ResilienceScoreData }) {
  return (
    <section data-block="resilience_score" className="rounded-card bg-surface p-4 shadow-card">
      <h3 className="text-subtitle font-semibold text-ink">Điểm chống chịu</h3>
      <div className="mt-3 text-center">
        <ResilienceGauge score={data.score} band={data.band} />
        {data.previous_score !== undefined && <p className="text-note text-ink-2">Điểm lần trước {data.previous_score}/100</p>}
      </div>
      <p className="mt-2 text-small text-ink">{data.headline}</p>
      <ul className="mt-2 divide-y divide-line">
        {data.components.map((component) => (
          <ScoreRow key={component.key} component={component} weakest={component.key === data.weakest} />
        ))}
      </ul>
      <p className="border-t border-line pt-2 text-note text-ink-2">{data.disclaimer}</p>
    </section>
  )
}
