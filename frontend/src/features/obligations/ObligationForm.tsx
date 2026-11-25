import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { MoneyInput } from '@/components/MoneyInput'
import { useWriteFlow } from '@/api/useWrite'
import type { ActionResponse, JarFull } from '@/api/schemas'
import { cn } from '@/lib/cn'
import {
  CYCLE_LABEL,
  KIND_LABEL,
  emptyForm,
  obligationUpsertParams,
  validateForm,
  type CycleInput,
  type ObligationForm as FormState,
  type ObligationKindInput,
} from './params'

const KINDS: ObligationKindInput[] = ['rent', 'bill', 'subscription', 'loan']
const CYCLES: CycleInput[] = ['monthly', 'weekly', 'yearly', 'once']

const selectCls = 'h-13 w-full rounded-2xl border border-line bg-surface px-4 text-[16px] text-ink'

/**
 * Form thêm hoặc sửa MỘT nghĩa vụ (tiền trọ, hóa đơn, thuê bao, khoản vay): số tiền cố định hoặc theo khoảng, chu kỳ,
 * ngày đến hạn, hũ trả. Nút "Lưu" là hành động xác nhận có nêu rõ việc làm; lưu qua /confirmations -> /actions
 * (`update_profile`). Dùng ở màn Nghĩa vụ và bước O3 của onboarding.
 */
export function ObligationFormView({
  initial,
  jars,
  onSaved,
  onCancel,
  submitLabel = 'Lưu khoản này',
}: {
  initial?: FormState
  jars: JarFull[]
  onSaved: (r: ActionResponse) => void
  onCancel?: () => void
  submitLabel?: string
}) {
  const userJars = jars.filter((j) => j.kind !== 'system')
  const defaultJar = userJars.find((j) => j.kind === 'obligation' && j.code === 'nghia_vu') ??
    userJars.find((j) => j.kind === 'obligation')
  const [f, setF] = useState<FormState>(() => initial ?? emptyForm())
  // Hũ trả mặc định suy từ danh sách hũ ở mỗi lần vẽ: danh sách có thể về sau lần vẽ đầu (mở thẳng /obligations/new), nên
  // không chốt nó vào state lúc khởi tạo. Người dùng chọn hũ khác thì giữ lựa chọn đó.
  const payJar = f.payJar || defaultJar?.code || ''
  const [touched, setTouched] = useState(false)
  const payJarError = touched && !payJar ? 'Chọn hũ sẽ dùng để trả.' : undefined
  const write = useWriteFlow()
  const errors = validateForm(f)
  const invalid = Object.keys(errors).length > 0
  const set = (p: Partial<FormState>) => setF((s) => ({ ...s, ...p }))
  const show = (k: keyof typeof errors) => (touched ? errors[k] : undefined)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (invalid || !payJar) return
    const r = await write.submit('update_profile', obligationUpsertParams({ ...f, payJar }))
    if (r) onSaved(r)
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4" aria-label={initial?.id ? 'Sửa khoản nghĩa vụ' : 'Thêm khoản nghĩa vụ'}>
      <div>
        <span className="mb-1.5 block text-small font-semibold text-ink-2">Loại khoản</span>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Loại khoản">
          {KINDS.map((k) => (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={f.kind === k}
              onClick={() => set({ kind: k })}
              className={cn('min-h-11 rounded-full border px-4 text-small font-semibold', f.kind === k ? 'border-brand bg-tint text-brand-text' : 'border-line bg-surface text-ink')}
            >
              {KIND_LABEL[k]}
            </button>
          ))}
        </div>
      </div>

      <label className="block">
        <span className="mb-1.5 block text-small font-semibold text-ink-2">Tên khoản</span>
        <Input value={f.name} maxLength={80} onChange={(e) => set({ name: e.target.value })} aria-invalid={!!show('name')} placeholder="Ví dụ: Tiền trọ" />
        {show('name') && <span className="mt-1 block text-note font-semibold text-bad-fg">{show('name')}</span>}
      </label>

      <div>
        <div className="mb-1.5 flex gap-2" role="radiogroup" aria-label="Cách khai số tiền">
          {(['fixed', 'range'] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={f.amountMode === m}
              onClick={() => set({ amountMode: m })}
              className={cn('min-h-11 rounded-full border px-4 text-small font-semibold', f.amountMode === m ? 'border-brand bg-tint text-brand-text' : 'border-line bg-surface text-ink')}
            >
              {m === 'fixed' ? 'Số tiền cố định' : 'Dao động theo tháng'}
            </button>
          ))}
        </div>
        {f.amountMode === 'fixed' ? (
          <MoneyInput label="Số tiền mỗi kỳ" value={f.amount} onChange={(v) => set({ amount: v })} error={show('amount')} />
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <MoneyInput label="Thấp nhất" value={f.min} onChange={(v) => set({ min: v })} error={show('min')} />
            <MoneyInput label="Cao nhất" value={f.max} onChange={(v) => set({ max: v })} error={show('max')} />
          </div>
        )}
      </div>

      <label className="block">
        <span className="mb-1.5 block text-small font-semibold text-ink-2">Chu kỳ</span>
        <select value={f.cycle} onChange={(e) => set({ cycle: e.target.value as CycleInput })} className={selectCls}>
          {CYCLES.map((c) => (
            <option key={c} value={c}>
              {CYCLE_LABEL[c]}
            </option>
          ))}
        </select>
      </label>

      {f.cycle === 'monthly' ? (
        <label className="block">
          <span className="mb-1.5 block text-small font-semibold text-ink-2">Ngày đến hạn trong tháng</span>
          <Input inputMode="numeric" value={f.dueDay} onChange={(e) => set({ dueDay: e.target.value.replace(/\D/g, '').slice(0, 2) })} aria-invalid={!!show('dueDay')} placeholder="1 đến 31" />
          {show('dueDay') && <span className="mt-1 block text-note font-semibold text-bad-fg">{show('dueDay')}</span>}
        </label>
      ) : (
        <label className="block">
          <span className="mb-1.5 block text-small font-semibold text-ink-2">Ngày đến hạn (ngày mô phỏng)</span>
          <Input type="date" value={f.dueDate} onChange={(e) => set({ dueDate: e.target.value })} aria-invalid={!!show('dueDate')} />
          {show('dueDate') && <span className="mt-1 block text-note font-semibold text-bad-fg">{show('dueDate')}</span>}
        </label>
      )}

      <label className="block">
        <span className="mb-1.5 block text-small font-semibold text-ink-2">Hũ dùng để trả</span>
        <select value={payJar} onChange={(e) => set({ payJar: e.target.value })} className={selectCls} aria-invalid={!!payJarError}>
          <option value="" disabled>Chọn hũ</option>
          {userJars.map((j) => (
            <option key={j.code} value={j.code}>
              {j.name}
            </option>
          ))}
        </select>
        {payJarError && <span className="mt-1 block text-note font-semibold text-bad-fg">{payJarError}</span>}
      </label>

      <label className="flex min-h-11 items-center gap-3">
        <input type="checkbox" checked={f.essential} onChange={(e) => set({ essential: e.target.checked })} className="size-5 accent-[var(--brand-primary)]" />
        <span className="text-body text-ink">Khoản thiết yếu (không gợi ý cắt giảm)</span>
      </label>

      {write.error && (
        <p role="alert" className="rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
          {write.error.message}
        </p>
      )}

      <div className="flex flex-col gap-3">
        <Button type="submit" disabled={write.working || write.phase === 'blocked'} aria-busy={write.working}>
          {write.working ? 'Đang lưu…' : submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={write.working}>
            Hủy
          </Button>
        )}
      </div>
    </form>
  )
}
