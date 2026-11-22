import { Navigate, useNavigate } from 'react-router'
import { Lock, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScreenHeader } from '@/components/ScreenHeader'
import { useApiResource } from '@/api/resource'
import { useOverview } from '@/api/OverviewProvider'
import { useWriteFlow } from '@/api/useWrite'
import { usePreview } from '@/api/useConfirmPreview'
import { PreviewPanel } from '@/components/PreviewPanel'
import { amountOf, useTransferFlow } from '@/features/transfer/TransferFlow'
import { transferParams } from '@/features/transfer/params'
import { formatAppDate, formatVnd } from '@/lib/format'
import { Avatar } from './TransferPayeePage'

// Figma T4 xem lại và xác nhận (19:1158). Nhãn nút là "Xác nhận" thường (không giả lập Face ID). Số dư sau, phí và tổng
// phải trả gồm phí KHÔNG tính ở đây: server tính trong `preview` của POST /confirmations (không ghi gì) và hiện trong
// PreviewPanel; lỗi nghiệp vụ (không đủ số dư, vượt hạn mức) cũng hiện sớm ở đó. Với Trả sau còn trích dòng biểu phí có
// nguồn từ GET /credit-line.
export function TransferReviewPage() {
  const navigate = useNavigate()
  const { state, patch, reset } = useTransferFlow()
  const ov = useOverview()
  const txTypes = useApiResource((api) => api.listTxTypes(), [])
  const credit = useApiResource((api) => api.getCreditLine(), [])
  const write = useWriteFlow()
  const amount = amountOf(state)
  const params =
    state.payee && state.source && amount > 0 && txTypes.status !== 'loading'
      ? transferParams({
          amountVnd: amount,
          source: state.source,
          payeeId: state.payee.id,
          note: state.note,
          clientRef: state.clientRef,
          txTypes: txTypes.data?.tx_types ?? [],
          creditJar: state.creditJar || undefined,
        })
      : null
  const preview = usePreview('record_transaction', write.phase === 'done' ? null : params)
  const previewBlocked = preview.status === 'error' && !preview.error.retryable

  if (!state.payee) return <Navigate to="/transfer" replace />
  if (!state.source || amount <= 0) return <Navigate to="/transfer/amount" replace />

  const jar = state.source.kind === 'jar' ? ov.data?.jars.find((j) => j.code === (state.source as { code: string }).code) : undefined
  const line = credit.data?.credit_line ?? null
  const feeLines = (credit.data?.fees ?? []).filter((f) => f.amount_vnd !== undefined && f.condition_code !== 'overdue')
  const isCredit = state.source.kind === 'credit'

  const confirm = async () => {
    if (!params) return
    const res = await write.submit('record_transaction', params)
    if (res) {
      patch({ receipt: res })
      navigate('/transfer/receipt', { replace: true })
    }
  }

  return (
    <>
      <ScreenHeader title="Xem lại và xác nhận" backTo="/transfer/amount" />
      <div className="px-4">
        <div className="flex flex-col items-center">
          <Avatar name={state.payee.name} size={56} />
          <p className="mt-2 text-body text-ink-2">Chuyển cho {state.payee.name}</p>
          <p className="num text-display font-extrabold text-ink" data-testid="review-amount">
            {formatVnd(amount)}
          </p>
        </div>

        <dl className="mt-4 space-y-3 rounded-card bg-surface p-4 text-body shadow-card">
          <div className="flex justify-between gap-4">
            <dt className="text-ink-2">Người nhận</dt>
            <dd className="text-right font-semibold text-ink">
              {state.payee.name}
              {state.payee.account_hint ? ` · ${state.payee.account_hint}` : ''}
            </dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-ink-2">Trả từ</dt>
            <dd className="text-right font-semibold text-ink" data-testid="review-source">
              {isCredit ? (line?.product_label ?? 'Trả sau (mô phỏng)') : `Hũ ${jar?.name ?? (state.source.kind === 'jar' ? state.source.code : '')}`}
              {jar && <span className="num block text-small font-normal text-ink-2">Hiện còn {formatVnd(jar.balance_vnd)}</span>}
              {isCredit && line && <span className="num block text-small font-normal text-ink-2">Hạn mức còn {formatVnd(line.available_vnd)}</span>}
            </dd>
          </div>
          {state.note.trim() && (
            <div className="flex justify-between gap-4">
              <dt className="text-ink-2">Lời nhắn</dt>
              <dd className="text-right font-semibold text-ink">{state.note.trim()}</dd>
            </div>
          )}
          <div className="flex justify-between gap-4">
            <dt className="text-ink-2">Thời gian</dt>
            <dd className="text-right font-semibold text-ink">Ngay bây giờ{ov.data ? ` · ngày mô phỏng ${formatAppDate(ov.data.app_date)}` : ''}</dd>
          </div>
        </dl>

        {isCredit && (
          <div className="mt-3 rounded-card bg-warn-bg p-4 text-small text-ink" data-testid="credit-fee-note">
            <p className="font-semibold text-warn-fg">Có phí khi trả bằng {line?.product_label ?? 'Trả sau'}</p>
            {credit.status === 'loading' && <p className="mt-1 text-ink-2">Đang tải biểu phí…</p>}
            {credit.status === 'error' && <p className="mt-1 text-ink-2">Chưa tải được biểu phí; tổng phải trả sẽ hiện trên biên nhận.</p>}
            <ul className="mt-1 space-y-1">
              {feeLines.map((f) => (
                <li key={f.fee_type}>
                  Phí {formatVnd(f.amount_vnd ?? 0)}
                  {f.condition_note ? `: ${f.condition_note}` : ''}
                  <span className="block text-note text-ink-2">Nguồn: {f.source_name}</span>
                </li>
              ))}
            </ul>
            {preview.status !== 'ready' && (
              <p className="mt-1 text-ink-2">Tổng phải trả gồm phí do hệ thống tính; nghĩa vụ này đến hạn ngày {line?.due_day ?? '5'} hằng tháng.</p>
            )}
          </div>
        )}

        <PreviewPanel state={preview} className="mt-3" />

        <div className="mt-3 flex items-start gap-2 rounded-card bg-tint p-3.5 text-small text-ink">
          <Sparkles className="mt-0.5 size-4 shrink-0 text-brand-text" aria-hidden />
          <p>
            Bấm xác nhận thì hệ thống mới ghi giao dịch và cập nhật số dư. Dự báo hũ sẽ tính lại sau đó. Chưa bấm thì chưa có gì thay đổi.
          </p>
        </div>

        {write.error && (
          <p role="alert" className="mt-3 rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
            {write.error.message}
          </p>
        )}
      </div>

      <div className="mt-6 flex flex-col items-center gap-2 px-4 pb-6">
        <Button type="button" className="w-full" onClick={() => void confirm()} disabled={!params || previewBlocked || write.phase === 'working' || write.phase === 'blocked' || write.phase === 'done'} aria-busy={write.working}>
          {write.working ? 'Đang xác nhận…' : `Xác nhận chuyển ${formatVnd(amount)}`}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={write.working}
          onClick={() => {
            if (write.phase === 'blocked') {
              reset()
              navigate('/transfer')
            } else navigate('/transfer/amount')
          }}
        >
          {write.phase === 'blocked' ? 'Làm lại từ đầu' : 'Quay lại sửa'}
        </Button>
        <p className="mt-1 flex items-center gap-1.5 text-note text-ink-2">
          <Lock className="size-3.5" aria-hidden />
          Ví mô phỏng · không phải giao dịch thật
        </p>
      </div>
    </>
  )
}
