import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router'
import { Check, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { JarIcon } from '@/components/JarIcon'
import { Numpad } from '@/components/Numpad'
import { ScreenHeader } from '@/components/ScreenHeader'
import { useApiResource } from '@/api/resource'
import { useOverview } from '@/api/OverviewProvider'
import { amountOf, useTransferFlow } from '@/features/transfer/TransferFlow'
import { formatVnd, formatVndNumber, vndInWords } from '@/lib/format'
import { cn } from '@/lib/cn'
import { Avatar } from './TransferPayeePage'

// Gợi ý số tiền chọn nhanh của giao diện (không phải số liệu của người dùng).
const QUICK = [50_000, 100_000, 200_000, 500_000]
const MAX_DIGITS = 11 // 99.999.999.999 ₫ < trần numeric(14,0)

// Figma T2 nhập số tiền + hũ nguồn (19:872). Chọn hũ nguồn hoặc Trả sau (mô phỏng); nhãn và hạn mức lấy từ GET /credit-line.
// Bước kế tiếp là kiểm tra đủ/sát/hụt (T3, `POST /affordability`), rồi mới xem lại (T4).
export function TransferAmountPage() {
  const navigate = useNavigate()
  const { state, patch } = useTransferFlow()
  const ov = useOverview()
  const credit = useApiResource((api) => api.getCreditLine(), [])
  const [open, setOpen] = useState(state.source === null)
  const amount = amountOf(state)
  const jars = ov.data?.jars ?? []
  const line = credit.data?.credit_line ?? null

  useEffect(() => {
    if (state.source === null) setOpen(true)
  }, [state.source])

  if (!state.payee) return <Navigate to="/transfer" replace />

  const sourceJar = state.source?.kind === 'jar' ? jars.find((j) => j.code === (state.source as { code: string }).code) : undefined
  const overBalance = sourceJar !== undefined && amount > sourceJar.balance_vnd
  const overCredit = state.source?.kind === 'credit' && line !== null && amount > line.available_vnd
  const addDigit = (d: string) => {
    const next = (state.amountDigits + d).replace(/^0+/, '')
    if (next.length <= MAX_DIGITS) patch({ amountDigits: next })
  }
  const label =
    state.source?.kind === 'credit'
      ? `Trả bằng ${line?.product_label ?? 'Trả sau'}`
      : sourceJar
        ? `Trả từ hũ ${sourceJar.name}`
        : 'Chọn nguồn tiền'
  const sub =
    state.source?.kind === 'credit' && line
      ? `Hạn mức còn ${formatVnd(line.available_vnd)}`
      : sourceJar
        ? `Còn ${formatVnd(sourceJar.balance_vnd)}`
        : 'Hũ hoặc Trả sau (mô phỏng)'
  const canContinue = amount > 0 && state.source !== null

  return (
    <>
      <ScreenHeader title="Chuyển tiền" backTo="/transfer" />
      <div className="px-4">
        <div className="mx-auto flex w-fit items-center gap-2 rounded-full border border-line bg-surface py-1.5 pr-4 pl-1.5">
          <Avatar name={state.payee.name} size={32} />
          <span className="text-small font-semibold text-ink">{state.payee.name}</span>
        </div>

        <div className="mt-3 text-center">
          <p className="num text-[44px] leading-[52px] font-extrabold text-ink" data-testid="amount-display" aria-live="polite">
            {amount > 0 ? formatVndNumber(amount) : '0'} <span className="text-section align-top underline">₫</span>
          </p>
          <p className="min-h-5 text-small text-ink-2" data-testid="amount-words">
            {amount > 0 ? `Bằng chữ: ${vndInWords(amount)}` : 'Nhập số tiền cần chuyển'}
          </p>
        </div>

        <div className="mt-3 rounded-card border border-line bg-surface">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            aria-label={`Nguồn tiền: ${label}. ${sub}`}
            className="flex min-h-[68px] w-full items-center gap-3 px-4 text-left"
          >
            {sourceJar ? (
              <JarIcon colorKey={sourceJar.color_key} iconKey={sourceJar.icon_key} size={36} />
            ) : (
              <span className="size-9 shrink-0 rounded-full bg-surface-2" aria-hidden />
            )}
            <span className="min-w-0 flex-1">
              <span className="block text-subtitle font-semibold text-ink" data-testid="source-label">
                {label}
              </span>
              <span className="block text-small text-ink-2">{sub}</span>
            </span>
            <ChevronDown className={cn('size-5 shrink-0 text-ink-2 transition-transform', open && 'rotate-180')} aria-hidden />
          </button>
          {open && (
            <ul role="radiogroup" aria-label="Nguồn tiền" className="divide-y divide-line border-t border-line">
              {jars.map((j) => {
                const selected = state.source?.kind === 'jar' && state.source.code === j.code
                return (
                  <li key={j.code}>
                    <button
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => {
                        patch({ source: { kind: 'jar', code: j.code } })
                        setOpen(false)
                      }}
                      className="flex min-h-14 w-full items-center gap-3 px-4 text-left"
                    >
                      <JarIcon colorKey={j.color_key} iconKey={j.icon_key} size={32} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-body font-semibold text-ink">Hũ {j.name}</span>
                        <span className="num block text-small text-ink-2">Còn {formatVnd(j.balance_vnd)}</span>
                      </span>
                      {selected && <Check className="size-5 text-brand-text" aria-hidden />}
                    </button>
                  </li>
                )
              })}
              <li>
                <button
                  type="button"
                  role="radio"
                  aria-checked={state.source?.kind === 'credit'}
                  disabled={!line || line.status !== 'active'}
                  onClick={() => {
                    patch({ source: { kind: 'credit' } })
                    setOpen(false)
                  }}
                  className="flex min-h-14 w-full items-center gap-3 px-4 text-left disabled:opacity-50"
                >
                  <span className="grid size-8 place-items-center rounded-full bg-blue-tint text-note font-bold text-blue" aria-hidden>
                    TS
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-body font-semibold text-ink">{line?.product_label ?? 'Trả sau (mô phỏng)'}</span>
                    <span className="num block text-small text-ink-2">
                      {credit.status === 'loading'
                        ? 'Đang tải hạn mức…'
                        : line
                          ? line.status === 'active'
                            ? `Hạn mức còn ${formatVnd(line.available_vnd)}`
                            : 'Hạn mức đang tạm khóa'
                          : credit.status === 'error'
                            ? 'Chưa tải được hạn mức'
                            : 'Chưa có hạn mức'}
                    </span>
                  </span>
                  {state.source?.kind === 'credit' && <Check className="size-5 text-brand-text" aria-hidden />}
                </button>
              </li>
            </ul>
          )}
        </div>

        {state.source?.kind === 'credit' && jars.length > 0 && (
          <label className="mt-3 block">
            <span className="mb-1 block text-small font-semibold text-ink-2">Tính vào hũ (tùy chọn)</span>
            <select
              value={state.creditJar}
              onChange={(e) => patch({ creditJar: e.target.value })}
              aria-label="Tính vào hũ (tùy chọn)"
              className="h-12 w-full rounded-2xl border border-line bg-surface px-4 text-body text-ink"
            >
              <option value="">Để hệ thống xếp</option>
              {jars.map((j) => (
                <option key={j.code} value={j.code}>
                  {j.name}
                </option>
              ))}
            </select>
            <span className="mt-1 block text-note text-ink-2">Mua bằng Trả sau không trừ tiền hũ ngay; hũ này chỉ để tính chi tiêu.</span>
          </label>
        )}

        {(overBalance || overCredit) && (
          <p role="status" className="mt-2 rounded-2xl bg-warn-bg px-3 py-2 text-small font-medium text-warn-fg">
            {overBalance ? 'Số tiền lớn hơn số dư của hũ này.' : 'Số tiền lớn hơn hạn mức còn lại.'} Hệ thống sẽ từ chối nếu không đủ; bạn có thể đổi nguồn tiền.
          </p>
        )}

        <div className="mt-3 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none]" aria-label="Chọn nhanh số tiền">
          {QUICK.map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => patch({ amountDigits: String(v) })}
              aria-pressed={amount === v}
              className={cn('min-h-11 shrink-0 rounded-full border px-4 text-small font-semibold', amount === v ? 'border-brand bg-tint text-brand-text' : 'border-line bg-surface text-ink')}
            >
              {formatVndNumber(v)}
            </button>
          ))}
        </div>

        <label className="mt-2 block">
          <span className="sr-only">Lời nhắn</span>
          <Input value={state.note} onChange={(e) => patch({ note: e.target.value.slice(0, 200) })} placeholder="Lời nhắn (tùy chọn)" maxLength={200} />
        </label>
      </div>

      <div className="mt-3">
        <Numpad onDigit={addDigit} onDelete={() => patch({ amountDigits: state.amountDigits.slice(0, -1) })} />
      </div>
      <div className="px-4 pt-3 pb-6">
        <Button type="button" className="w-full" disabled={!canContinue} onClick={() => navigate('/transfer/check')}>
          Kiểm tra trước khi chuyển
        </Button>
      </div>
    </>
  )
}
