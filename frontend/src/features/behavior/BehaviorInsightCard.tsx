import type { ReactNode } from 'react'
import { Lightbulb } from 'lucide-react'
import { AiChip, StatusChip, type ChipKind } from '@/components/StatusChip'
import type { BehaviorInsight, BehaviorNextStep } from '@/contracts/blocks'
import { CONFIDENCE_LABEL } from '@/lib/jar'
import { EvidenceBars } from './EvidenceBars'
import { formatEvidencePeriod, formatEvidenceValue, INSIGHT_KIND_LABEL } from './format'

const BAND_CHIP: Record<BehaviorInsight['confidence'], ChipKind> = { high: 'ok', medium: 'warn', low: 'bad' }

/**
 * MỘT nhận xét hành vi kèm bằng chứng số (khối `behavior_insight`, màn Hồ sơ). Câu nhận xét do batch đêm viết (model nhỏ hoặc mẫu
 * câu) và mọi số trong đó có trong `evidence`; giao diện chỉ vẽ.
 */
export function BehaviorInsightCard({ insight, nextStep, footer, as: Tag = 'section' }: {
  insight: BehaviorInsight
  nextStep?: BehaviorNextStep
  /** Phần cuối (nút thực hiện việc cần làm, lối sang Hồ sơ...). */
  footer?: ReactNode
  as?: 'section' | 'article'
}) {
  return (
    <Tag data-block="behavior_insight" data-insight={insight.insight_id} aria-label={`Nhận xét: ${insight.headline}`} className="space-y-3 rounded-card bg-surface p-4 shadow-card">
      <header className="flex flex-wrap items-center gap-2">
        <span className="text-note font-semibold text-ink-2">{INSIGHT_KIND_LABEL[insight.kind]}</span>
        <StatusChip kind={BAND_CHIP[insight.confidence]}>Tin cậy {CONFIDENCE_LABEL[insight.confidence].toLowerCase()}</StatusChip>
        {insight.ai_generated && <AiChip>AI tóm tắt</AiChip>}
      </header>
      <p className="text-subtitle font-semibold text-ink">{insight.headline}</p>
      {insight.detail && <p className="text-small text-ink-2">{insight.detail}</p>}
      <EvidenceBars evidence={insight.evidence} />
      <dl aria-label="Bằng chứng" className="divide-y divide-line rounded-xl bg-surface-2 px-3">
        {insight.evidence.map((e) => {
          const period = formatEvidencePeriod(e)
          return (
            <div key={e.key} data-evidence={e.key} className="flex items-start justify-between gap-3 py-2">
              <dt className="min-w-0 text-small text-ink">
                {e.label}
                {period && <span className="block text-note text-ink-2">{period}</span>}
              </dt>
              <dd className="num shrink-0 text-small font-semibold text-ink">{formatEvidenceValue(e)}</dd>
            </div>
          )
        })}
      </dl>
      {nextStep && <NextStep step={nextStep} />}
      {footer}
    </Tag>
  )
}

/** Việc cần làm đi kèm hồ sơ hành vi. Bấm thực hiện (nếu có) đi luồng xác nhận sẵn có, không tự ghi gì. */
export function NextStep({ step, children }: { step: BehaviorNextStep; children?: ReactNode }) {
  return (
    <div data-testid="behavior-next-step" className="flex items-start gap-2.5 rounded-xl bg-tint p-3">
      <Lightbulb className="mt-0.5 size-5 shrink-0 text-brand-text" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-note font-semibold text-brand-text">Việc nên làm</p>
        <p className="text-small font-semibold text-ink">{step.label}</p>
        <p className="text-small text-ink-2">{step.reason}</p>
        {children}
      </div>
    </div>
  )
}
