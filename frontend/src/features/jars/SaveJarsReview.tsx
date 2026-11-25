import type { ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useOverview } from '@/api/OverviewProvider'
import { usePreview } from '@/api/useConfirmPreview'
import { useWriteFlow } from '@/api/useWrite'
import type { ActionResponse, ToolParams } from '@/api/schemas'

/**
 * Xác nhận MỌI thay đổi tỷ lệ chia lương (`save_jars`, BR-45): bản xem trước do server tính (lý do bằng số đo, tỷ lệ và
 * tiền mỗi kỳ trước và sau, phần chênh; BR-47) rồi người dùng chọn Đồng ý, Sửa số hoặc Không đổi. Có lương đang chờ chia
 * thì hỏi rõ: áp tỷ lệ mới cho kỳ này (lưu trước, lương chờ chia theo tỷ lệ mới) hay từ kỳ sau (chia lương chờ theo tỷ lệ
 * cũ rồi mới lưu). Giao diện không tính số nào; lời giải thích nằm trong phần mở rộng.
 */
export function SaveJarsReview({
  params,
  onSaved,
  onEdit,
  onKeep,
  children,
}: {
  params: ToolParams
  onSaved: (r: ActionResponse) => void
  onEdit?: () => void
  onKeep: () => void
  /** Thông tin thêm do server tính (ví dụ kiểm tra theo ngày của đề xuất), vẽ trong phần mở rộng. */
  children?: ReactNode
}) {
  const ov = useOverview()
  const write = useWriteFlow()
  const salary = useWriteFlow()
  const preview = usePreview('save_jars', write.receipt ? null : params)
  const next = ov.data?.next_payday
  const pendingId = next?.state === 'pending_confirmation' ? next.salary_event_id : undefined
  const busy = write.working || salary.working
  const ready = preview.status === 'ready' && !busy && write.phase !== 'blocked'
  const p = preview.status === 'ready' || preview.status === 'loading' ? preview.preview : null

  const save = async () => {
    const r = await write.submit('save_jars', params)
    if (r) onSaved(r)
  }
  const fromNextPeriod = async () => {
    if (!pendingId) return
    const done = await salary.submit('confirm_salary', { salary_event_id: pendingId, decision: 'split' })
    if (done) await save()
  }

  return (
    <section aria-label="Xác nhận tỷ lệ chia lương" data-testid="save-jars-review" className="rounded-card bg-surface p-4 shadow-card">
      <h2 className="text-subtitle font-semibold text-ink">Xác nhận tỷ lệ mới</h2>
      {preview.status === 'loading' && !p && <Skeleton role="status" aria-label="Đang tính xem trước" className="mt-3 h-[120px] w-full rounded-card" />}
      {preview.status === 'error' && (
        <p role="alert" className="mt-3 rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
          {preview.error.message}
        </p>
      )}
      {p && (
        <>
          <p className="mt-1 text-small text-ink-2" data-testid="save-jars-summary">
            {p.summary}
          </p>
          <ul className="mt-3 space-y-2" aria-label="Thay đổi">
            {p.changes.map((c, i) => (
              <li key={`${c.label}-${i}`} className="rounded-2xl bg-surface-2 px-3 py-2.5">
                <p className="text-small font-semibold text-ink">{c.label}</p>
                <p className="num mt-0.5 flex flex-wrap items-center gap-1.5 text-small text-ink-2">
                  {c.before && (
                    <>
                      <span>{c.before}</span>
                      <ChevronRight className="size-4 shrink-0" aria-hidden />
                    </>
                  )}
                  <span className="font-bold text-ink">{c.after}</span>
                </p>
              </li>
            ))}
          </ul>
          {((p.warnings && p.warnings.length > 0) || children) && (
            <details className="mt-3 rounded-2xl bg-surface-2 px-3 py-2 text-small text-ink-2">
              <summary className="cursor-pointer font-semibold text-ink">Áp dụng khi nào, vì sao</summary>
              {p.warnings && p.warnings.length > 0 && (
                <ul className="mt-2 space-y-1" aria-label="Lưu ý">
                  {p.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              )}
              {children}
            </details>
          )}
        </>
      )}
      {(write.error || salary.error) && (
        <p role="alert" className="mt-3 rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
          {(salary.error ?? write.error)!.message}
        </p>
      )}
      <div className="mt-4 flex flex-col gap-2.5">
        {pendingId ? (
          <>
            <Button type="button" disabled={!ready} onClick={() => void save()} aria-busy={write.working}>
              {write.working ? 'Đang lưu…' : 'Đồng ý, áp cho kỳ này'}
            </Button>
            <Button type="button" variant="soft" disabled={!ready} onClick={() => void fromNextPeriod()} aria-busy={salary.working}>
              {salary.working ? 'Đang chia lương…' : 'Đồng ý, từ kỳ sau'}
            </Button>
            <p className="text-note text-ink-2">Từ kỳ sau: lương đang chờ được chia theo tỷ lệ cũ trước, rồi mới lưu.</p>
          </>
        ) : (
          <Button type="button" disabled={!ready} onClick={() => void save()} aria-busy={write.working}>
            {write.working ? 'Đang lưu…' : 'Đồng ý'}
          </Button>
        )}
        {onEdit && (
          <Button type="button" variant="outline" disabled={busy} onClick={onEdit}>
            Sửa số
          </Button>
        )}
        <Button type="button" variant="ghost" disabled={busy} onClick={onKeep}>
          Không đổi
        </Button>
      </div>
    </section>
  )
}
