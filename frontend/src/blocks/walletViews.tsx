import { CheckCircle2, ChevronRight, Clock } from 'lucide-react'
import { useInRouterContext, useNavigate } from 'react-router'
import { AiChip, StatusChip } from '@/components/StatusChip'
import { useOptionalChatActions } from '@/chat/actions'
import { useExplain } from '@/features/explain/context'
import { ProactiveCard } from '@/components/ProactiveCard'
import { Button } from '@/components/ui/button'
import { ForecastBlock } from '@/features/forecast/ForecastBlock'
import { useProactiveActions } from '@/features/overview/useProactiveActions'
import { useChatLauncher } from '@/chat/launcher'
import { formatCountdown, formatSimMoment, formatVnd } from '@/lib/format'
import type { ConfirmActionBlock, ForecastTimelineBlock, ProactiveCardBlock, ReceiptActionBlock } from '@/contracts/blocks'
import { UndoBar } from './UndoBar'
import { useConfirmFlow } from './useConfirmFlow'
import { useNow } from './useNow'
import type { BlockViewProps } from './views'

// Bốn khối của phase 2: forecast_timeline, proactive_card, confirm_action, receipt_action.

// ---------------------------------------------------------------- forecast_timeline

/** Cùng ForecastBlock với màn Chi tiết hũ, nên chat và màn hình luôn cùng số. */
export function ForecastTimelineView({ block }: BlockViewProps<ForecastTimelineBlock>) {
  // "Vì sao" chỉ có trong chat: khối do agent phát mang `trace_id` của lượt (có bản ghi để giải thích). Khối do REST dựng
  // (Chi tiết hũ) không có bản ghi lượt, nên màn đó tự hỏi Yofina (xem JarDetailPage).
  const explain = useExplain()
  return <ForecastBlock data={block.data} onAskWhy={explain ? () => explain.open(block.trace_id) : undefined} />
}

// ---------------------------------------------------------------- proactive_card

function ProactiveCardInRouter({ block }: { block: ProactiveCardBlock }) {
  const d = block.data
  const onAction = useProactiveActions(d, block.source.app_date)
  // Trong chat không có chỗ lưu "Để sau" / "Ít nhắc loại này": chỉ giữ các nút làm được việc.
  const doable = d.actions.filter((a) => a.kind !== 'snooze' && a.kind !== 'mute_kind')
  return <ProactiveCard data={doable.length > 0 ? { ...d, actions: doable } : d} onAction={onAction} />
}

export function ProactiveCardView({ block }: BlockViewProps<ProactiveCardBlock>) {
  const inRouter = useInRouterContext()
  if (!inRouter) return <ProactiveCard data={block.data} onAction={() => {}} />
  return <ProactiveCardInRouter block={block} />
}

// ---------------------------------------------------------------- confirm_action

export function ConfirmActionView({ block, blockId, ui }: BlockViewProps<ConfirmActionBlock>) {
  const d = block.data
  const actions = useOptionalChatActions()
  const flow = useConfirmFlow({ block, blockId })
  const expiresAt = Date.parse(d.expires_at)
  const cancelled = ui === 'cancelled'
  const applied = ui === 'done'
  const settled = cancelled || applied
  const now = useNow(1000, !settled && flow.phase !== 'working' && flow.phase !== 'done')
  const remaining = expiresAt - now
  const expired = !settled && (ui === 'expired' || remaining <= 0 || flow.offerExpired) && flow.phase !== 'done'
  const canAct = !settled && !expired && !flow.cancelling && flow.phase !== 'working' && flow.phase !== 'done' && flow.phase !== 'blocked'

  return (
    <section
      data-block="confirm_action"
      data-phase={cancelled ? 'cancelled' : applied ? 'applied' : expired ? 'expired' : flow.phase}
      className="rounded-card border-2 border-brand bg-surface p-4"
    >
      <header className="flex items-center justify-between gap-2">
        <h3 className="text-subtitle font-semibold text-ink">Xác nhận trước khi thực hiện</h3>
        <AiChip />
      </header>
      <p className="mt-3 text-subtitle font-bold text-ink">{d.summary}</p>

      <ul className="mt-3 space-y-2">
        {d.changes.map((c, i) => (
          <li key={`${c.label}-${i}`} className="flex items-center justify-between gap-2 rounded-2xl bg-surface-2 px-4 py-3">
            <span className="text-body font-bold text-ink">{c.label}</span>
            <span className="num flex items-center gap-1.5 text-right text-small text-ink-2">
              {c.before && (
                <>
                  <span>{c.before}</span>
                  <ChevronRight className="size-4 shrink-0" aria-hidden />
                </>
              )}
              <span className="text-body font-extrabold text-ink">{c.after}</span>
            </span>
          </li>
        ))}
      </ul>

      {d.warnings && d.warnings.length > 0 && (
        <ul className="mt-3 space-y-1.5" aria-label="Lưu ý">
          {d.warnings.map((w) => (
            <li key={w} className="rounded-2xl bg-warn-bg px-3 py-2 text-small font-medium text-warn-fg">
              {w}
            </li>
          ))}
        </ul>
      )}

      {cancelled ? (
        <p className="mt-3 text-small font-semibold text-ink-2" role="status">
          Đã hủy. Chưa có gì được ghi.
        </p>
      ) : applied ? (
        <p className="mt-3 text-small font-semibold text-ink-2" role="status">
          Đề nghị này đã được thực hiện rồi. Bạn kiểm tra số dư ở Tổng quan nhé.
        </p>
      ) : expired ? (
        <div role="status" className="mt-3">
          <p className="text-small font-semibold text-warn-fg">
            Đề nghị này đã hết hạn nên số liệu xem trước có thể đã cũ.
          </p>
          {actions && (
            <Button type="button" variant="soft" size="sm" className="mt-2" onClick={actions.askAgain}>
              Hỏi lại để có đề nghị mới
            </Button>
          )}
        </div>
      ) : (
        <p className="mt-3 flex items-center gap-2 text-small text-ink-2">
          <Clock className="size-4 shrink-0" aria-hidden />
          <span>
            Đề nghị còn <span className="num font-semibold">{formatCountdown(remaining)}</span> · cần bạn xác nhận mới ghi
          </span>
        </p>
      )}

      {flow.error && (
        <p role="alert" className="mt-3 rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
          {flow.error.message}
        </p>
      )}

      {!settled && (
        <div className="mt-4 flex flex-col gap-3">
          <Button type="button" disabled={!canAct} onClick={() => void flow.confirm()} aria-busy={flow.phase === 'working'}>
            {flow.phase === 'working' ? 'Đang xác nhận…' : 'Xác nhận'}
          </Button>
          <Button type="button" variant="outline" disabled={flow.phase === 'working' || flow.phase === 'done' || flow.cancelling} onClick={() => void flow.cancel()}>
            Không
          </Button>
        </div>
      )}
    </section>
  )
}

// ---------------------------------------------------------------- receipt_action

function FollowUpButton({ followUp }: { followUp: NonNullable<ReceiptActionBlock['data']['follow_up']> }) {
  const navigate = useNavigate()
  const launcher = useChatLauncher()
  const go = () => {
    launcher.close()
    navigate(followUp.kind === 'confirm_salary' ? '/salary' : '/activity?review=1')
  }
  return (
    <Button type="button" variant="soft" className="mt-3 w-full" onClick={go}>
      {followUp.label}
    </Button>
  )
}

export function ReceiptActionView({ block, blockId, ui, doneAt }: BlockViewProps<ReceiptActionBlock>) {
  const d = block.data
  const inRouter = useInRouterContext()
  return (
    <section data-block="receipt_action" className="rounded-card bg-surface p-4 shadow-card">
      <header className="flex items-start gap-3">
        <span className="grid size-12 shrink-0 place-items-center rounded-full bg-ok-bg text-ok-fg">
          <CheckCircle2 className="size-6" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-section font-bold text-ink">{d.summary}</h3>
          <p className="text-small text-ink-2">{formatSimMoment(d.app_date, d.occurred_at)} · Ví mô phỏng</p>
        </div>
        <AiChip />
      </header>
      {ui === 'undone' && (
        <p role="status" data-testid="undone-note" className="mt-2 flex items-center gap-2 text-small font-semibold text-ink-2">
          <StatusChip kind="info">Đã hoàn tác</StatusChip>
          Đây là thao tác ngược của lần trước.
        </p>
      )}
      {(d.details.length > 0 || d.jars_after.length > 0 || d.reference_id) && (
        <dl className="mt-3 space-y-1.5 text-body">
          {d.details.map((x, i) => (
            <div key={`${x.label}-${i}`} className="flex items-center justify-between gap-3">
              <dt className="text-ink-2">{x.label}</dt>
              <dd className="num text-right font-semibold text-ink">{x.value}</dd>
            </div>
          ))}
          {d.jars_after.map((j) => (
            <div key={j.code} className="flex items-center justify-between gap-3">
              <dt className="text-ink-2">Số dư {j.name}</dt>
              <dd className="num font-bold text-ink">{formatVnd(j.balance_after_vnd)}</dd>
            </div>
          ))}
          {d.reference_id && (
            <div className="flex items-center justify-between text-small">
              <dt className="text-ink-2">Mã tham chiếu</dt>
              <dd className="num font-semibold text-ink">{d.reference_id.slice(0, 8).toUpperCase()}</dd>
            </div>
          )}
        </dl>
      )}
      {d.follow_up && inRouter && <FollowUpButton followUp={d.follow_up} />}
      {d.follow_up && !inRouter && <p className="mt-3 text-small font-semibold text-brand-text">{d.follow_up.label}</p>}
      <UndoBar receipt={block} blockId={blockId} doneAt={doneAt} />
    </section>
  )
}
