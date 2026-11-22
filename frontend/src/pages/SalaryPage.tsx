import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { CheckCircle2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScreenHeader } from '@/components/ScreenHeader'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/StateViews'
import { useApiResource } from '@/api/resource'
import { useWriteFlow } from '@/api/useWrite'
import { usePreview } from '@/api/useConfirmPreview'
import { PreviewPanel } from '@/components/PreviewPanel'
import type { SalaryEvent } from '@/api/schemas'
import { formatAppDate, formatVnd } from '@/lib/format'

function signedPercent(p: number): string {
  const v = Math.abs(p).toLocaleString('vi-VN', { maximumFractionDigits: 2 })
  return `${p > 0 ? '+' : p < 0 ? '−' : ''}${v}%`
}

function SalaryCard({ ev }: { ev: SalaryEvent }) {
  const write = useWriteFlow()
  const [update, setUpdate] = useState(false)
  const receipt = write.receipt?.type === 'receipt_action' ? write.receipt.data : null
  // Phần chia vào từng hũ do server tính (làm tròn xuống, dồn phần dư vào hũ tỷ lệ lớn nhất); không tính ở giao diện.
  const preview = usePreview('confirm_salary', receipt ? null : { salary_event_id: ev.id, decision: 'split' })

  const decide = (decision: 'split' | 'keep_as_other') => {
    const params: Record<string, unknown> = { salary_event_id: ev.id, decision }
    if (decision === 'split' && ev.ask_update_salary && update) params.update_declared_salary = true
    return write.submit('confirm_salary', params)
  }

  return (
    <section className="rounded-card bg-surface p-4 shadow-card" data-salary-event={ev.id} aria-label={`Lương về ngày ${formatAppDate(ev.received_on)}`}>
      <h2 className="text-subtitle font-semibold text-ink">Lương về ngày {formatAppDate(ev.received_on)}</h2>
      <p className="num mt-1 text-title font-extrabold text-ink">{formatVnd(ev.amount_vnd)}</p>
      <dl className="mt-2 space-y-1 text-small">
        {ev.expected_vnd !== undefined && (
          <div className="flex justify-between gap-3">
            <dt className="text-ink-2">Lương đã khai</dt>
            <dd className="num font-semibold text-ink">{formatVnd(ev.expected_vnd)}</dd>
          </div>
        )}
        <div className="flex justify-between gap-3">
          <dt className="text-ink-2">Chênh so với đã khai</dt>
          <dd className="num font-semibold text-ink" data-testid="deviation">
            {signedPercent(ev.deviation_percent)}
          </dd>
        </div>
      </dl>

      {receipt ? (
        <div role="status" className="mt-3 rounded-2xl bg-ok-bg p-3 text-small text-ok-fg" data-testid="salary-done">
          <p className="flex items-center gap-2 font-semibold">
            <CheckCircle2 className="size-4" aria-hidden />
            {receipt.summary}
          </p>
          <ul className="mt-1.5 space-y-0.5 text-ink">
            {receipt.jars_after.map((j) => (
              <li key={j.code} className="flex justify-between gap-3">
                <span>{j.name}</span>
                <span className="num font-semibold">{formatVnd(j.balance_after_vnd)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <>
          {ev.ask_update_salary && (
            <label className="mt-3 flex min-h-11 items-start gap-3 rounded-2xl bg-warn-bg p-3 text-small text-ink">
              <input type="checkbox" checked={update} onChange={(e) => setUpdate(e.target.checked)} className="mt-0.5 size-5 accent-[var(--brand-primary)]" />
              <span>
                Số nhận lệch nhiều so với lương đã khai. Cập nhật lương đã khai thành <span className="num font-semibold">{formatVnd(ev.amount_vnd)}</span>?
              </span>
            </label>
          )}
          {preview.status !== 'idle' && <PreviewPanel state={preview} className="mt-3 !bg-surface-2 !shadow-none" />}
          {write.error && (
            <p role="alert" className="mt-3 rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
              {write.error.message}
            </p>
          )}
          <div className="mt-3 flex flex-col gap-2.5">
            <Button type="button" disabled={write.working || write.phase === 'blocked'} onClick={() => void decide('split')} aria-busy={write.working}>
              {write.working ? 'Đang chia…' : 'Chia vào các hũ'}
            </Button>
            <Button type="button" variant="outline" disabled={write.working || write.phase === 'blocked'} onClick={() => void decide('keep_as_other')}>
              Giữ ở Tiền vào khác
            </Button>
          </div>
        </>
      )}
    </section>
  )
}

// Xác nhận lương về một chạm: chia vào hũ theo luật (do server chia, làm tròn và dồn phần dư) hoặc giữ ở Tiền vào khác.
export function SalaryPage() {
  const navigate = useNavigate()
  const events = useApiResource((api) => api.listSalaryEvents(), [])
  // Sau khi xác nhận, danh sách "chờ" của server không còn khoản đó; giữ lại các khoản đã thấy để biên nhận không biến mất.
  const [seen, setSeen] = useState<SalaryEvent[]>([])
  useEffect(() => {
    const incoming = events.data?.salary_events
    if (!incoming) return
    setSeen((prev) => {
      const ids = new Set(prev.map((e) => e.id))
      const added = incoming.filter((e) => !ids.has(e.id))
      return added.length > 0 ? [...prev, ...added] : prev
    })
  }, [events.data])
  const list = seen.length > 0 ? seen : (events.data?.salary_events ?? [])
  return (
    <>
      <ScreenHeader title="Lương về" backTo="/" />
      <div className="space-y-3 px-4 pb-10">
        {events.status === 'loading' && <ListSkeleton rows={1} label="Đang tải lương chờ xác nhận" rowClass="h-[200px]" />}
        {events.status === 'error' && <ErrorState error={events.error} title="Chưa tải được khoản lương" onRetry={() => void events.reload()} />}
        {events.status === 'ready' && list.length === 0 && (
          <EmptyState
            title="Không có lương nào chờ xác nhận"
            message="Khi tiền vào được nhận diện là lương, bạn sẽ xác nhận một chạm ở đây để chia vào các hũ."
            action={
              <Button type="button" variant="soft" onClick={() => navigate('/income')}>
                Ghi nhận tiền vào
              </Button>
            }
          />
        )}
        {list.map((ev) => (
          <SalaryCard key={ev.id} ev={ev} />
        ))}
      </div>
    </>
  )
}
