import { CheckCircle2, ChevronRight, Clock } from 'lucide-react'
import { useOptionalChatActions } from '@/chat/actions'
import { AiChip, StatusChip } from '@/components/StatusChip'
import { SuggestionChips } from '@/components/SuggestionChips'
import { JarIcon } from '@/components/JarIcon'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { formatCountdown, formatSimMoment, formatVnd } from '@/lib/format'
import type { ConfirmBlock, JarSummaryBlock, NoticeBlock, ReceiptBlock } from '@/contracts/blocks'
import { useConfirmFlow } from './useConfirmFlow'
import type { BlockUi } from '@/chat/session'
import { useNow } from './useNow'
import { UndoBar } from './UndoBar'

export type BlockViewProps<T> = {
  block: T
  blockId: string
  ui?: BlockUi
  /** Thời điểm (đồng hồ máy) đề nghị vừa được thực hiện trong phiên này: còn trong cửa sổ Hoàn tác thì biên nhận có nút Hoàn tác. */
  doneAt?: number
  /** Đã có tin nhắn mới của người dùng sau khối này (khối hỏi lại không còn bấm được). */
  stale?: boolean
}

// ---------------------------------------------------------------- jar_summary

export function JarSummaryView({ block }: BlockViewProps<JarSummaryBlock>) {
  const { jars, jars_total_vnd } = block.data
  return (
    <section data-block="jar_summary" className="rounded-card bg-surface p-4 shadow-card">
      <header className="flex items-center justify-between gap-2">
        <h3 className="text-subtitle font-semibold text-ink">Số dư các hũ</h3>
        <AiChip />
      </header>
      {jars.length === 0 ? (
        <p className="mt-3 text-small text-ink-2">Chưa có hũ nào trong tài khoản này.</p>
      ) : (
        <ul className="mt-2 divide-y divide-line">
          {jars.map((j) => (
            <li key={j.code} className="flex items-center gap-3 py-2.5" data-jar={j.code}>
              <JarIcon colorKey={j.color_key} iconKey={j.icon_key} size={36} />
              <span className="min-w-0 flex-1 truncate text-body font-semibold text-ink">{j.name}</span>
              <span className="num text-body font-bold text-ink">{formatVnd(j.balance_vnd)}</span>
            </li>
          ))}
        </ul>
      )}
      <footer className="mt-1 flex items-center justify-between border-t border-line pt-3 text-body">
        <span className="font-semibold text-ink-2">Tổng các hũ</span>
        <span className="num text-amount font-extrabold text-ink">{formatVnd(jars_total_vnd)}</span>
      </footer>
    </section>
  )
}

// ---------------------------------------------------------------- notice

/**
 * Thông báo trạng thái (H7 ngoài phạm vi, H8a suy giảm, H8b dữ liệu ít, lỗi). Phase 3 thêm: `retryable` (nút "Thử lại" chạy lại
 * lượt vừa rồi), `missing` (phần còn thiếu khi trả một phần), `suggestions` (việc làm được, bấm để hỏi).
 */
export function NoticeView({ block, stale }: BlockViewProps<NoticeBlock>) {
  const { kind, title, message, code, retryable, missing, suggestions } = block.data
  const actions = useOptionalChatActions()
  return (
    <Notice kind={kind} title={title} message={message} code={code} onRetry={retryable && actions && !stale ? actions.retryLast : undefined}>
      {missing && missing.length > 0 && (
        <div className="mt-2" data-testid="notice-missing">
          <p className="text-small font-semibold text-ink">Phần chưa có:</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-small text-ink">
            {missing.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
      {suggestions && suggestions.length > 0 && (
        <div className="mt-3" data-testid="notice-suggestions">
          <p className="text-small font-semibold text-ink">Bạn có thể hỏi mình:</p>
          <SuggestionChips className="mt-1.5" label="Việc mình làm được" disabled={!actions} items={suggestions} onPick={(prompt) => actions?.ask(prompt)} />
        </div>
      )}
    </Notice>
  )
}

// ---------------------------------------------------------------- receipt

export function ReceiptView({ block, blockId, ui, doneAt }: BlockViewProps<ReceiptBlock>) {
  const d = block.data
  return (
    <section data-block="receipt" className="rounded-card bg-surface p-4 shadow-card">
      <header className="flex items-start gap-3">
        <span className="grid size-12 shrink-0 place-items-center rounded-full bg-ok-bg text-ok-fg">
          <CheckCircle2 className="size-6" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-section font-bold text-ink">Đã chuyển {formatVnd(d.amount_vnd)}</h3>
          <p className="text-small text-ink-2">
            Từ hũ {d.from_jar.name} sang hũ {d.to_jar.name} · {formatSimMoment(d.app_date, d.occurred_at)}
          </p>
        </div>
        <AiChip />
      </header>
      {ui === 'undone' && (
        <p role="status" data-testid="undone-note" className="mt-2 flex items-center gap-2 text-small font-semibold text-ink-2">
          <StatusChip kind="info">Đã hoàn tác</StatusChip>
          Đây là thao tác ngược của lần chuyển trước.
        </p>
      )}
      <dl className="mt-3 space-y-1.5 text-body">
        {[d.from_jar, d.to_jar].map((j) => (
          <div key={j.code} className="flex items-center justify-between">
            <dt className="text-ink-2">{j.name}</dt>
            <dd className="num font-bold text-ink">{formatVnd(j.balance_after_vnd)}</dd>
          </div>
        ))}
        <div className="flex items-center justify-between text-small">
          <dt className="text-ink-2">Mã giao dịch</dt>
          <dd className="num font-semibold text-ink">{d.transaction_id.slice(0, 8).toUpperCase()}</dd>
        </div>
      </dl>
      <UndoBar receipt={block} blockId={blockId} doneAt={doneAt} />
    </section>
  )
}

// ---------------------------------------------------------------- confirm

export function ConfirmView({ block, blockId, ui }: BlockViewProps<ConfirmBlock>) {
  const d = block.data
  const actions = useOptionalChatActions()
  const flow = useConfirmFlow({ block, blockId })
  const expiresAt = Date.parse(d.expires_at)
  const cancelled = ui === 'cancelled'
  // Server báo đã thực hiện mà không dựng được biên nhận: không còn nút nào, kể cả khi hết hạn.
  const applied = ui === 'done'
  const settled = cancelled || applied
  const now = useNow(1000, !settled && flow.phase !== 'working' && flow.phase !== 'done')
  const remaining = expiresAt - now
  // `ui === 'expired'`: server đã báo quá hạn (nguồn sự thật); đồng hồ máy chỉ để đếm ngược và bắt kịp lúc quá hạn khi đang mở.
  const expired = !settled && (ui === 'expired' || remaining <= 0 || flow.offerExpired) && flow.phase !== 'done'
  const canAct = !settled && !expired && !flow.cancelling && flow.phase !== 'working' && flow.phase !== 'done' && flow.phase !== 'blocked'

  return (
    <section
      data-block="confirm"
      data-phase={cancelled ? 'cancelled' : applied ? 'applied' : expired ? 'expired' : flow.phase}
      className="rounded-card border-2 border-brand bg-surface p-4"
    >
      <header className="flex items-center justify-between gap-2">
        <h3 className="text-subtitle font-semibold text-ink">Xác nhận trước khi thực hiện</h3>
        <AiChip />
      </header>
      <p className="mt-3 text-subtitle font-bold text-ink">{d.summary}</p>

      <ul className="mt-3 space-y-2">
        {[d.preview.from, d.preview.to].map((j) => (
          <li key={j.code} className="flex items-center justify-between gap-2 rounded-2xl bg-surface-2 px-4 py-3">
            <span className="text-body font-bold text-ink">{j.name}</span>
            <span className="num flex items-center gap-1.5 text-small text-ink-2">
              <span>{formatVnd(j.before_vnd)}</span>
              <ChevronRight className="size-4" aria-hidden />
              <span className="text-body font-extrabold text-ink">{formatVnd(j.after_vnd)}</span>
            </span>
          </li>
        ))}
      </ul>

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
            Đề nghị này đã hết hạn nên số dư xem trước có thể đã cũ.
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
            {flow.phase === 'working' ? 'Đang xác nhận…' : `Xác nhận chuyển ${formatVnd(d.params.amount_vnd)}`}
          </Button>
          <Button type="button" variant="outline" disabled={flow.phase === 'working' || flow.phase === 'done' || flow.cancelling} onClick={() => void flow.cancel()}>
            Không
          </Button>
        </div>
      )}
    </section>
  )
}
