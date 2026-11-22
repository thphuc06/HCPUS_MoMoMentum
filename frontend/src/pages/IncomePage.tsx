import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { CheckCircle2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { MoneyInput } from '@/components/MoneyInput'
import { ScreenHeader } from '@/components/ScreenHeader'
import { SimNote } from '@/components/SimNote'
import { ErrorState } from '@/components/StateViews'
import { Skeleton } from '@/components/ui/skeleton'
import { useApiResource } from '@/api/resource'
import { useOverview } from '@/api/OverviewProvider'
import { useWriteFlow } from '@/api/useWrite'
import { usePreview } from '@/api/useConfirmPreview'
import { PreviewPanel } from '@/components/PreviewPanel'
import { newUuid } from '@/lib/ids'
import { formatVnd } from '@/lib/format'
import { cn } from '@/lib/cn'

// Ghi nhận tiền vào trên ví mô phỏng (lương hoặc loại khác, danh sách loại lấy từ GET /tx-types) và ô "Tiền vào khác".
// Tiền vào luôn nằm ở hũ Tiền vào khác; riêng lương sinh một sự kiện chờ xác nhận để chia vào hũ (màn Lương về).
export function IncomePage() {
  const ov = useOverview()
  const types = useApiResource((api) => api.listTxTypes(), [])
  const write = useWriteFlow()
  const [amount, setAmount] = useState('')
  const [txType, setTxType] = useState('')
  const [from, setFrom] = useState('')
  const [note, setNote] = useState('')
  const [clientRef, setClientRef] = useState(() => `ui-${newUuid()}`)
  const incomeTypes = useMemo(() => (types.data?.tx_types ?? []).filter((t) => t.direction === 'in'), [types.data])
  const valid = Number(amount) > 0 && txType !== ''
  const other = ov.data?.balance.other_income_vnd ?? 0

  const params: Record<string, unknown> = { kind: 'income', amount_vnd: Number(amount), tx_type: txType, client_ref: clientRef }
  if (from.trim()) params.counterparty = from.trim()
  if (note.trim()) params.note = note.trim()
  const preview = usePreview('record_transaction', valid && !write.receipt ? params : null, 400)
  const previewBlocked = preview.status === 'error' && !preview.error.retryable

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid) return
    await write.submit('record_transaction', params)
  }

  const again = () => {
    write.reset()
    setAmount('')
    setFrom('')
    setNote('')
    setClientRef(`ui-${newUuid()}`)
  }

  const receipt = write.receipt?.type === 'receipt_action' ? write.receipt.data : null

  return (
    <>
      <ScreenHeader title="Tiền vào" backTo="/" />
      <div className="space-y-4 px-4 pb-10">
        {receipt ? (
          <section className="rounded-card bg-surface p-5 shadow-card" data-testid="income-receipt">
            <div className="flex items-start gap-3">
              <span className="grid size-12 shrink-0 place-items-center rounded-full bg-ok-bg text-ok-fg">
                <CheckCircle2 className="size-6" aria-hidden />
              </span>
              <div>
                <h2 className="text-section font-bold text-ink">{receipt.summary}</h2>
                <p className="text-small text-ink-2">Ví mô phỏng · không phải giao dịch thật</p>
              </div>
            </div>
            <dl className="mt-3 space-y-1.5 text-body">
              {receipt.details.map((d, i) => (
                <div key={`${d.label}-${i}`} className="flex justify-between gap-3">
                  <dt className="text-ink-2">{d.label}</dt>
                  <dd className="text-right font-semibold text-ink">{d.value}</dd>
                </div>
              ))}
              {receipt.jars_after.map((j) => (
                <div key={j.code} className="flex justify-between gap-3">
                  <dt className="text-ink-2">Số dư {j.name}</dt>
                  <dd className="num font-bold text-ink">{formatVnd(j.balance_after_vnd)}</dd>
                </div>
              ))}
            </dl>
            {receipt.follow_up?.kind === 'confirm_salary' && (
              <Link to="/salary" className="mt-4 inline-flex h-12 w-full items-center justify-center rounded-full bg-primary px-6 text-subtitle font-bold text-primary-foreground">
                {receipt.follow_up.label}
              </Link>
            )}
            <Button type="button" variant="outline" className="mt-3 w-full" onClick={again}>
              Ghi tiếp một khoản
            </Button>
          </section>
        ) : (
          <form onSubmit={submit} noValidate className="space-y-4 rounded-card bg-surface p-4 shadow-card" aria-label="Ghi nhận tiền vào">
            <h2 className="text-subtitle font-semibold text-ink">Ghi nhận tiền vào</h2>
            <MoneyInput label="Số tiền" size="lg" value={amount} onChange={setAmount} />

            <div>
              <span className="mb-1.5 block text-small font-semibold text-ink-2" id="income-type-label">
                Loại tiền vào
              </span>
              {types.status === 'loading' && <Skeleton className="h-12 w-full rounded-2xl" role="status" aria-label="Đang tải loại tiền vào" />}
              {types.status === 'error' && <ErrorState error={types.error} title="Chưa tải được loại tiền vào" onRetry={() => void types.reload()} />}
              {types.status === 'ready' && incomeTypes.length === 0 && <p className="text-small text-ink-2">Chưa có loại tiền vào nào để chọn.</p>}
              <div role="radiogroup" aria-labelledby="income-type-label" className="flex flex-wrap gap-2">
                {incomeTypes.map((t) => (
                  <button
                    key={t.tx_type}
                    type="button"
                    role="radio"
                    aria-checked={txType === t.tx_type}
                    onClick={() => setTxType(t.tx_type)}
                    className={cn('min-h-11 rounded-full border px-4 text-small font-semibold', txType === t.tx_type ? 'border-brand bg-tint text-brand-text' : 'border-line bg-surface text-ink')}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            <label className="block">
              <span className="mb-1.5 block text-small font-semibold text-ink-2">Từ ai (tùy chọn)</span>
              <Input value={from} maxLength={120} onChange={(e) => setFrom(e.target.value)} />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-small font-semibold text-ink-2">Ghi chú (tùy chọn)</span>
              <Input value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} />
            </label>

            <PreviewPanel state={preview} />
            {write.error && (
              <p role="alert" className="rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
                {write.error.message}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={!valid || previewBlocked || write.working || write.phase === 'blocked'} aria-busy={write.working}>
              {write.working ? 'Đang ghi…' : 'Ghi nhận tiền vào'}
            </Button>
            <p className="text-note text-ink-2">Tiền vào được ghi vào hũ Tiền vào khác. Riêng lương sẽ chờ bạn xác nhận một chạm để chia vào các hũ.</p>
          </form>
        )}

        <section className="rounded-card bg-surface p-4 shadow-card" aria-label="Tiền vào khác" data-testid="other-income">
          <h2 className="text-subtitle font-semibold text-ink">Tiền vào khác</h2>
          <p className="text-small text-ink-2">Tiền vào chưa gán hũ. Không tính là thu nhập khi dự báo.</p>
          <p className="num mt-1 text-title font-extrabold text-ink" data-testid="other-income-amount">
            {ov.data ? formatVnd(other) : '…'}
          </p>
          {other > 0 && (
            <Link to="/move?from=tien_vao_khac" className="mt-3 inline-flex h-11 items-center justify-center rounded-full bg-tint px-5 text-small font-bold text-brand-text">
              Gán vào hũ
            </Link>
          )}
        </section>
      <SimNote />
      </div>
    </>
  )
}
