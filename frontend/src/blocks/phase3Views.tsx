import { useState } from 'react'
import { Check, CircleHelp } from 'lucide-react'
import { useApi } from '@/api/ApiProvider'
import { useOptionalChatActions } from '@/chat/actions'
import { AiChip, StatusChip } from '@/components/StatusChip'
import { Disclosure } from '@/components/ui/Disclosure'
import { SuggestionChips } from '@/components/SuggestionChips'
import { Button } from '@/components/ui/button'
import { AffordCard } from '@/features/affordability/AffordCard'
import { ObligationImpactBody } from '@/features/affordability/ObligationImpactBody'
import { ExplainBody } from '@/features/explain/ExplainBody'
import { readableChipText } from '@/features/clarify/chipText'
import { useExplain } from '@/features/explain/context'
import { statusShortChip } from '@/lib/jar'
import type { AffordabilityCardBlock, ClarifyBlock, ExplainBlock, ObligationImpactBlock, OptionItem, OptionsBlock, SuggestionsBlock } from '@/contracts/blocks'
import type { BlockViewProps } from './views'

// Sáu khối của phase 3: affordability_card, obligation_impact, options, explain, clarify, suggestions.
// Chỉ vẽ số và chữ do code dựng; nút "Vì sao" chỉ có trong chat (nơi có bản ghi lượt của agent để giải thích).

/** Nút "Vì sao": mở bảng H4 cho lượt của khối này. Ẩn ngoài chat. */
export function WhyButton({ traceId, className }: { traceId: string; className?: string }) {
  const explain = useExplain()
  if (!explain) return null
  return (
    <button
      type="button"
      onClick={() => explain.open(traceId)}
      className={`inline-flex min-h-11 items-center gap-1.5 px-2 text-small font-semibold text-brand-text ${className ?? ''}`}
    >
      <CircleHelp className="size-4" aria-hidden />
      Vì sao
    </button>
  )
}

// ---------------------------------------------------------------- affordability_card

export function AffordabilityCardView({ block }: BlockViewProps<AffordabilityCardBlock>) {
  const explain = useExplain()
  return <AffordCard block={block} onAskWhy={explain ? () => explain.open(block.trace_id) : undefined} />
}

// ---------------------------------------------------------------- obligation_impact

export function ObligationImpactView({ block }: BlockViewProps<ObligationImpactBlock>) {
  return (
    <section data-block="obligation_impact" data-status={block.data.status} className="rounded-card bg-surface p-4 shadow-card">
      <header className="flex items-center justify-between gap-2">
        <h3 className="text-subtitle font-semibold text-ink">Tác động tới nghĩa vụ</h3>
        <AiChip />
      </header>
      <div className="mt-2">
        <ObligationImpactBody data={block.data} appDate={block.source.app_date} />
      </div>
      <div className="mt-1 flex justify-end">
        <WhyButton traceId={block.trace_id} />
      </div>
    </section>
  )
}

// ---------------------------------------------------------------- options

type Decision = 'accepted' | 'rejected'

function OptionRow({
  option,
  decision,
  pending,
  onDecide,
}: {
  option: OptionItem
  decision: Decision | undefined
  pending: boolean
  onDecide: (d: Decision) => void
}) {
  const chip = statusShortChip(option.status)
  const needsConfirm = option.action !== undefined
  return (
    <li
      data-option={option.option_id}
      data-decision={decision}
      className={`rounded-2xl p-3 ${option.recommended ? 'border-2 border-brand' : 'border border-line'} bg-surface`}
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-body font-bold text-ink">
            {option.label}
            {option.recommended && <span className="ml-2 text-note font-semibold text-brand-text">Gợi ý</span>}
          </p>
          <p className="mt-0.5 text-small text-ink-2">{option.summary}</p>
        </div>
        <StatusChip kind={chip.kind}>{chip.label}</StatusChip>
      </div>
      {option.metrics && option.metrics.length > 0 && (
        <ul className="mt-2 space-y-1">
          {option.metrics.map((m, i) => (
            <li key={`${m.label}-${i}`} className="flex items-center justify-between gap-2 rounded-xl bg-surface-2 px-3 py-2 text-small">
              <span className="font-semibold text-ink">{m.label}</span>
              <span className="num text-ink-2">
                {m.before ? `${m.before} → ` : ''}
                <span className="font-bold text-ink">{m.after}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-note text-ink-2">
        {needsConfirm ? 'Cần bạn xác nhận mới thực hiện.' : 'Chỉ để cân nhắc, không thay đổi số dư.'}
        {option.checked_rules && option.checked_rules.length > 0 ? ` Đã kiểm ${option.checked_rules.length} luật.` : ''}
      </p>
      <div className="mt-2 flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant={decision === 'accepted' ? 'soft' : 'default'}
          disabled={pending}
          aria-pressed={decision === 'accepted'}
          aria-label={`Chọn: ${option.label}`}
          onClick={() => onDecide('accepted')}
        >
          {decision === 'accepted' && <Check className="size-4" aria-hidden />}
          {decision === 'accepted' ? 'Đã chọn' : 'Chọn'}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={pending}
          aria-pressed={decision === 'rejected'}
          aria-label={`Không chọn: ${option.label}`}
          onClick={() => onDecide('rejected')}
        >
          {decision === 'rejected' ? 'Đã bỏ qua' : 'Không chọn'}
        </Button>
      </div>
      {decision === 'accepted' && needsConfirm && <p className="mt-1.5 text-small font-medium text-ok-fg" role="status">Bước xác nhận đã mở ngay bên dưới.</p>}
    </li>
  )
}

/**
 * Hai đến ba phương án (H3c). "Chọn" ghi `POST /feedback` (accepted) rồi, nếu phương án có `action`, hiện khối xác nhận mà
 * agent đã phát sẵn trong lượt (giao diện KHÔNG gọi tool ghi và KHÔNG tạo token ở đây: bước xác nhận chạy luồng token như
 * mọi thao tác ghi). "Không chọn" ghi `rejected`. Lỗi ghi phản hồi không chặn việc mở bước xác nhận.
 */
export function OptionsView({ block }: BlockViewProps<OptionsBlock>) {
  const api = useApi()
  const actions = useOptionalChatActions()
  const [decisions, setDecisions] = useState<Record<string, Decision>>({})
  const [pending, setPending] = useState<string | null>(null)
  const [feedbackFailed, setFeedbackFailed] = useState(false)

  const decide = async (o: OptionItem, d: Decision) => {
    setPending(o.option_id)
    setFeedbackFailed(false)
    if (d === 'accepted' && o.action) actions?.revealBlock(o.action.block_id)
    setDecisions((prev) => ({ ...prev, [o.option_id]: d }))
    try {
      await api.submitFeedback({
        trace_id: block.trace_id,
        block_id: block.id,
        option_id: o.option_id,
        decision: d,
        ...(block.data.scenario_id ? { scenario_id: block.data.scenario_id } : {}),
      })
    } catch {
      setFeedbackFailed(true)
    } finally {
      setPending(null)
    }
  }

  return (
    <section data-block="options" className="rounded-card bg-surface p-4 shadow-card">
      <header className="flex items-center justify-between gap-2">
        <h3 className="text-subtitle font-semibold text-ink">{block.data.title ?? 'Bạn có thể'}</h3>
        <AiChip />
      </header>
      <ul className="mt-3 space-y-3">
        {block.data.options.map((o) => (
          <OptionRow key={o.option_id} option={o} decision={decisions[o.option_id]} pending={pending === o.option_id} onDecide={(d) => void decide(o, d)} />
        ))}
      </ul>
      {feedbackFailed && (
        <p role="status" className="mt-2 text-note text-ink-2">
          Chưa ghi được lựa chọn của bạn để cải thiện gợi ý; việc bạn chọn vẫn có tác dụng.
        </p>
      )}
      <div className="mt-1 flex justify-end">
        <WhyButton traceId={block.trace_id} />
      </div>
    </section>
  )
}

// ---------------------------------------------------------------- explain

export function ExplainView({ block }: BlockViewProps<ExplainBlock>) {
  return (
    <section className="rounded-card bg-surface p-4 shadow-card">
      <ExplainBody block={block} />
    </section>
  )
}

// ---------------------------------------------------------------- clarify

/**
 * Hỏi lại đúng MỘT câu (H5) kèm chip trả lời: bấm chip thì gửi `value` (hoặc nhãn) như tin nhắn kế tiếp; cũng gõ tự do được ở ô
 * nhập của chat. Khi người dùng đã trả lời (có tin nhắn sau khối), chip không còn bấm được.
 */
export function ClarifyView({ block, stale }: BlockViewProps<ClarifyBlock>) {
  const actions = useOptionalChatActions()
  const d = block.data
  return (
    <section data-block="clarify" data-slot={d.slot} data-stale={stale ? 'true' : undefined} className="rounded-card bg-surface p-4 shadow-card">
      <header className="flex items-center justify-between gap-2">
        <h3 className="text-small font-semibold text-ink-2">Mình cần hỏi thêm một điều</h3>
        <AiChip />
      </header>
      <p className="mt-2 text-subtitle font-bold text-ink" data-testid="clarify-question">
        {d.question}
      </p>
      {d.chips.length > 0 && (
        <SuggestionChips
          label="Câu trả lời nhanh"
          className="mt-3"
          disabled={stale || !actions}
          items={d.chips.map((c) => ({
            id: c.id,
            label: readableChipText(c.label, d.slot),
            prompt: readableChipText(c.value ?? c.label, d.slot),
          }))}
          onPick={(prompt) => actions?.ask(prompt)}
        />
      )}
      {d.allow_free_text !== false && !stale && <p className="mt-3 text-note text-ink-2">Hoặc gõ câu trả lời của bạn vào ô bên dưới.</p>}
    </section>
  )
}

// ---------------------------------------------------------------- suggestions

/** Gợi ý bấm được (H1 mở đầu có "mình làm được / chưa làm"; sau câu trả lời; kèm từ chối ngoài phạm vi). */
export function SuggestionsView({ block }: BlockViewProps<SuggestionsBlock>) {
  const actions = useOptionalChatActions()
  const d = block.data
  return (
    <section data-block="suggestions" data-context={d.context} className="rounded-card bg-surface p-4 shadow-card">
      {d.title && <h3 className="text-subtitle font-semibold text-ink">{d.title}</h3>}
      <SuggestionChips className="mt-3" disabled={!actions} items={d.items} onPick={(prompt) => actions?.ask(prompt)} />
      {/* Gợi ý bấm được trước; "Mình làm được / chưa làm" là chữ phụ, thu gọn (Luật chữ, ui-design-review.md §9). */}
      {(!!d.can_do?.length || !!d.cannot_do?.length) && (
        <Disclosure label="Mình làm được gì?" className="mt-1" panelClassName="pb-1">
          {d.can_do && d.can_do.length > 0 && (
            <>
              <h4 className="mt-1 text-small font-semibold text-ok-fg">Mình làm được</h4>
              <ul className="mt-1 space-y-1.5">
                {d.can_do.map((t) => (
                  <li key={t} className="flex items-start gap-2 text-small text-ink">
                    <Check className="mt-0.5 size-4 shrink-0 text-ok-fg" aria-hidden />
                    {t}
                  </li>
                ))}
              </ul>
            </>
          )}
          {d.cannot_do && d.cannot_do.length > 0 && (
            <>
              <h4 className="mt-3 text-small font-semibold text-ink-2">Mình chưa làm</h4>
              <ul className="mt-1 space-y-1.5 text-small text-ink-2">
                {d.cannot_do.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </>
          )}
        </Disclosure>
      )}
    </section>
  )
}
