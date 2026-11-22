import { ChevronRight } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import type { PreviewState } from '@/api/useConfirmPreview'

/**
 * Bản xem trước do server tính (`POST /confirmations` → `preview`): các dòng "trước → sau" và lưu ý, chỉ vẽ lại, không
 * tính gì. Lỗi nghiệp vụ (không đủ số dư, vượt hạn mức...) hiện ngay ở đây để người dùng sửa trước khi bấm xác nhận.
 * Không hiện gì khi chưa đủ dữ liệu (`idle`) hoặc khi server không trả `preview` (bản server cũ).
 */
export function PreviewPanel({ state, className }: { state: PreviewState; className?: string }) {
  if (state.status === 'idle') return null
  if (state.status === 'error') {
    return (
      <p role="alert" data-testid="preview-error" className={`rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg ${className ?? ''}`}>
        {state.error.message}
      </p>
    )
  }
  const p = state.preview
  if (!p) {
    return state.status === 'loading' ? <Skeleton role="status" aria-label="Đang tính xem trước" className={`h-[120px] w-full rounded-card ${className ?? ''}`} /> : null
  }
  return (
    <section aria-label="Xem trước" aria-busy={state.status === 'loading'} data-testid="preview" className={`rounded-card bg-surface p-4 shadow-card ${state.status === 'loading' ? 'opacity-70' : ''} ${className ?? ''}`}>
      <h2 className="text-subtitle font-semibold text-ink">Xem trước kết quả</h2>
      <p className="mt-1 text-small text-ink-2" data-testid="preview-summary">
        {p.summary}
      </p>
      <ul className="mt-3 space-y-2">
        {p.changes.map((c, i) => (
          <li key={`${c.label}-${i}`} className="flex items-center justify-between gap-2 rounded-2xl bg-surface-2 px-4 py-3">
            <span className="text-body font-semibold text-ink">{c.label}</span>
            <span className="num flex min-w-0 items-center gap-1.5 text-right text-small text-ink-2">
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
      {p.warnings && p.warnings.length > 0 && (
        <ul className="mt-3 space-y-1.5" aria-label="Lưu ý">
          {p.warnings.map((w) => (
            <li key={w} className="rounded-2xl bg-warn-bg px-3 py-2 text-small font-medium text-warn-fg">
              {w}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
