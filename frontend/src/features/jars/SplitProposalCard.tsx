import { useState } from 'react'
import { useNavigate } from 'react-router'
import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useWriteFlow } from '@/api/useWrite'
import type { ActionResponse, JarFull, SplitProposalCheck, SplitProposalResponse } from '@/api/schemas'
import { formatAppDate, formatPercent, formatVnd } from '@/lib/format'
import { JarSplitEditor } from './JarSplitEditor'
import { rowsFromParams } from './params'
import { SaveJarsReview } from './SaveJarsReview'

const shortfallText = (c: SplitProposalCheck) =>
  c.shortfall ? `${c.jar_name}: thiếu ${formatVnd(c.shortfall.shortfall_vnd)} cho ${c.shortfall.label} (${formatAppDate(c.shortfall.date)}), trước lương ${formatAppDate(c.payday)}` : ''

/** Kiểm tra theo ngày của kỳ lương hiện tại và kỳ kế tiếp (số do server tính): khoản đến hạn trước ngày lương so với tiền có. */
function ChecksDetail({ checks }: { checks: SplitProposalCheck[] }) {
  if (checks.length === 0) return null
  return (
    <ul className="mt-2 space-y-2" aria-label="Kiểm tra theo ngày">
      {checks.map((c) => (
        <li key={`${c.jar_code}-${c.payday}`}>
          <p className="font-semibold text-ink">
            {c.jar_name}, trước lương {formatAppDate(c.payday)}: cần {formatVnd(c.due_vnd)}, có {formatVnd(c.available_vnd)}
          </p>
          {c.items.length > 0 && (
            <ul className="mt-0.5">
              {c.items.map((i) => (
                <li key={`${i.label}-${i.date}`} className="num">
                  {formatAppDate(i.date)} · {i.label} · {formatVnd(i.amount_vnd)}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  )
}

function Shortfalls({ checks }: { checks: SplitProposalCheck[] }) {
  const short = checks.filter((c) => c.shortfall)
  if (short.length === 0) return null
  return (
    <ul className="mt-3 space-y-1.5" aria-label="Khoản có thể thiếu">
      {short.map((c) => (
        <li key={`${c.jar_code}-${c.payday}`} data-testid="proposal-shortfall" className="flex items-start gap-2 rounded-2xl bg-warn-bg px-3 py-2 text-small font-medium text-warn-fg">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          {shortfallText(c)}
        </li>
      ))}
    </ul>
  )
}

/**
 * Thẻ đề xuất tỷ lệ theo số đã khai (bước 3 onboarding). Mọi số do `POST /jars/split-proposal` và bản xem trước `save_jars`
 * của server tính; thẻ chỉ vẽ lại và cho chọn Đồng ý, Sửa số hoặc Không đổi. Nghĩa vụ vượt số chia được thì không lưu gì,
 * liệt kê nghĩa vụ theo thứ tự ưu tiên và mở lộ trình (không gợi ý cắt khoản thiết yếu). Lương nhận lệch số khai quá ngưỡng thì
 * hỏi cập nhật lương trước.
 */
export function SplitProposalCard({
  proposal,
  jars,
  onSaved,
}: {
  proposal: SplitProposalResponse
  jars: JarFull[]
  onSaved: (r: ActionResponse) => void
}) {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'card' | 'edit' | 'kept'>('card')
  const update = useWriteFlow()
  const p = proposal

  if (p.status === 'no_declarations') {
    return (
      <section aria-label="Tỷ lệ chia lương" data-testid="split-proposal" data-status={p.status} className="mt-4 rounded-card bg-surface p-4 shadow-card">
        <h2 className="text-subtitle font-semibold text-ink">Tỷ lệ chia lương</h2>
        <ul className="mt-2 space-y-1.5">
          {p.jars.map((j) => (
            <li key={j.code} data-jar-code={j.code} className="flex items-center justify-between gap-3 text-small">
              <span className="font-semibold text-ink">
                {j.name}
                {j.kind === 'obligation' && p.obligation_basis === 'template' && (
                  <span className="ml-2 rounded-full bg-surface-2 px-2 py-0.5 text-note font-medium text-ink-2">chưa có số khai</span>
                )}
              </span>
              <span className="num font-bold text-ink">{formatPercent(j.split_after)}</span>
            </li>
          ))}
        </ul>
      </section>
    )
  }

  if (p.status === 'salary_mismatch' && p.salary_check) {
    const s = p.salary_check
    return (
      <section aria-label="Cập nhật lương trước" data-testid="split-proposal" data-status={p.status} className="mt-4 rounded-card bg-warn-bg p-4">
        <p className="text-small font-semibold text-ink">
          Lương nhận {formatVnd(s.received_vnd)} lệch {formatPercent(Math.abs(s.deviation_percent))} so với lương đã khai {formatVnd(s.declared_vnd)}.
        </p>
        <p className="mt-1 text-small text-ink-2">Cập nhật lương trước để tỷ lệ đề xuất đúng.</p>
        {update.error && (
          <p role="alert" className="mt-2 rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
            {update.error.message}
          </p>
        )}
        <Button
          type="button"
          className="mt-3 w-full"
          disabled={update.working || update.phase === 'blocked'}
          aria-busy={update.working}
          onClick={() => void update.submit('update_profile', { monthly_salary_vnd: s.received_vnd })}
        >
          {update.working ? 'Đang lưu…' : `Cập nhật lương thành ${formatVnd(s.received_vnd)}`}
        </Button>
      </section>
    )
  }

  if (p.status === 'infeasible') {
    return (
      <section aria-label="Nghĩa vụ vượt số chia được" data-testid="split-proposal" data-status={p.status} className="mt-4 rounded-card bg-surface p-4 shadow-card">
        <p className="flex items-start gap-2 text-small font-semibold text-ink">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn-fg" aria-hidden />
          {p.required_percent !== undefined
            ? `Nghĩa vụ, Quỹ dồn và sàn Dự phòng cần ${formatPercent(p.required_percent)} lương. Chưa lưu tỷ lệ mới.`
            : 'Nghĩa vụ vượt số tiền chia được. Chưa lưu tỷ lệ mới.'}
        </p>
        {p.priority_obligations && p.priority_obligations.length > 0 && (
          <ol className="mt-3 space-y-1.5" aria-label="Nghĩa vụ theo thứ tự ưu tiên">
            {p.priority_obligations.map((o) => (
              <li key={o.id} className="flex items-center justify-between gap-3 text-small">
                <span className="text-ink">{o.name}</span>
                <span className="num font-semibold text-ink">{formatVnd(o.monthly_vnd)}/tháng</span>
              </li>
            ))}
          </ol>
        )}
        <details className="mt-3 rounded-2xl bg-surface-2 px-3 py-2 text-small text-ink-2">
          <summary className="cursor-pointer font-semibold text-ink">Vì sao</summary>
          {(p.reasons ?? []).map((r) => (
            <p key={r.text} className="mt-1">{r.text}</p>
          ))}
          <p className="mt-1">Khoản thiết yếu được giữ nguyên. Lộ trình giúp xếp thứ tự trả theo ưu tiên.</p>
        </details>
        <Button type="button" className="mt-3 w-full" onClick={() => navigate('/roadmap')}>
          Mở lộ trình
        </Button>
      </section>
    )
  }

  if (p.status === 'aligned') {
    return (
      <section aria-label="Tỷ lệ chia lương" data-testid="split-proposal" data-status={p.status} className="mt-4 rounded-card bg-surface p-4 shadow-card">
        <p className="text-small font-semibold text-ink">Tỷ lệ đang khớp số đã khai.</p>
        <Shortfalls checks={p.checks ?? []} />
        {(p.checks?.length ?? 0) > 0 && (
          <details className="mt-3 rounded-2xl bg-surface-2 px-3 py-2 text-small text-ink-2">
            <summary className="cursor-pointer font-semibold text-ink">Vì sao</summary>
            {(p.reasons ?? []).map((r) => (
              <p key={r.text} className="mt-1">{r.text}</p>
            ))}
            <ChecksDetail checks={p.checks ?? []} />
          </details>
        )}
      </section>
    )
  }

  if (p.status !== 'proposed' || !p.params) return null

  if (mode === 'kept') {
    return (
      <p role="status" data-testid="split-proposal" data-status="kept" className="mt-4 rounded-2xl bg-surface-2 px-4 py-3 text-small text-ink-2">
        Giữ tỷ lệ đang đặt.
      </p>
    )
  }
  if (mode === 'edit') {
    return (
      <div className="mt-4" data-testid="split-proposal" data-status="edit">
        <JarSplitEditor
          jars={jars}
          templates={[]}
          initialRows={rowsFromParams(p.params.jars, jars)}
          submitLabel="Xem trước tỷ lệ này"
          onSaved={onSaved}
          onUnchanged={() => setMode('kept')}
        />
      </div>
    )
  }
  return (
    <div className="mt-4" data-testid="split-proposal" data-status={p.status}>
      <h2 className="mb-2 text-subtitle font-semibold text-ink">Đề xuất theo số đã khai</h2>
      <Shortfalls checks={p.checks ?? []} />
      <div className="mt-3">
        <SaveJarsReview params={p.params} onSaved={onSaved} onEdit={() => setMode('edit')} onKeep={() => setMode('kept')}>
          <ChecksDetail checks={p.checks ?? []} />
        </SaveJarsReview>
      </div>
    </div>
  )
}
