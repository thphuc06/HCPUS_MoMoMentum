import { Navigate, useNavigate } from 'react-router'
import { Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { BlockRenderer } from '@/blocks/registry'
import { useTransferFlow } from '@/features/transfer/TransferFlow'
import { formatSimMoment, formatVnd } from '@/lib/format'

// Figma T5 biên nhận (19:1217): toàn bộ số liệu lấy từ biên nhận `receipt_action` của server (số dư sau, phí và tổng
// phải trả gồm phí nằm trong `details`), giao diện không tự tính lại.
export function TransferReceiptPage() {
  const navigate = useNavigate()
  const { state, reset } = useTransferFlow()
  const receipt = state.receipt
  if (!receipt) return <Navigate to="/transfer" replace />

  const done = () => {
    reset()
    navigate('/', { replace: true })
  }

  if (receipt.type !== 'receipt_action') {
    return (
      <div className="space-y-4 px-4 pt-[max(24px,env(safe-area-inset-top))]">
        <BlockRenderer raw={receipt} blockId={receipt.id} />
        <Button type="button" className="w-full" onClick={done}>
          Xong
        </Button>
      </div>
    )
  }
  const d = receipt.data
  return (
    <div className="px-4 pt-[max(40px,env(safe-area-inset-top))] pb-8" data-testid="transfer-receipt">
      <div className="flex flex-col items-center text-center">
        <span className="grid size-20 place-items-center rounded-full bg-ok-bg text-ok-fg">
          <Check className="size-10" aria-hidden />
        </span>
        <h1 className="mt-4 text-title font-bold text-ink">{d.summary}</h1>
        <p className="mt-1 text-small text-ink-2">
          {formatSimMoment(d.app_date, d.occurred_at)} · Ví mô phỏng
        </p>
      </div>

      <dl className="mt-5 space-y-3 rounded-card bg-surface p-4 text-body shadow-card">
        {d.details.map((x, i) => (
          <div key={`${x.label}-${i}`} className="flex justify-between gap-4">
            <dt className="text-ink-2">{x.label}</dt>
            <dd className="num text-right font-semibold text-ink">{x.value}</dd>
          </div>
        ))}
        {d.jars_after.map((j) => (
          <div key={j.code} className="flex justify-between gap-4">
            <dt className="text-ink-2">Hũ {j.name} còn lại</dt>
            <dd className="num text-right font-bold text-ink">{formatVnd(j.balance_after_vnd)}</dd>
          </div>
        ))}
        {d.reference_id && (
          <div className="flex justify-between gap-4">
            <dt className="text-ink-2">Mã giao dịch</dt>
            <dd className="num text-right font-semibold text-ink" data-testid="receipt-ref">
              {d.reference_id.slice(0, 8).toUpperCase()}
            </dd>
          </div>
        )}
      </dl>

      {d.follow_up?.kind === 'review_unclassified' && (
        <div className="mt-3 rounded-card bg-warn-bg p-4 text-small text-ink">
          <p>{d.follow_up.label}</p>
          <Button type="button" variant="soft" size="sm" className="mt-2 bg-surface" onClick={() => navigate('/activity?review=1')}>
            Xem lại giao dịch
          </Button>
        </div>
      )}

      <div className="mt-8 flex flex-col gap-3">
        <Button type="button" onClick={done}>
          Xong
        </Button>
        <Button type="button" variant="ghost" onClick={() => navigate('/activity')}>
          Xem trong Hoạt động
        </Button>
        <p className="text-center text-note text-ink-2">Ví mô phỏng · không phải giao dịch thật</p>
      </div>
    </div>
  )
}
