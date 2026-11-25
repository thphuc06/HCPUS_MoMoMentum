import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { MoneyInput } from '@/components/MoneyInput'
import type { SplitProposalKnownItem } from '@/api/schemas'
import { formatAppDate, formatVnd } from '@/lib/format'

/**
 * "Khoản biết trước trong 12 tháng tới" (Tết, học phí, bảo hiểm năm...), tùy chọn ở bước 3 của onboarding. Mỗi khoản có
 * tên, số tiền và ngày cần. Danh sách chỉ nằm ở giao diện cho tới khi người dùng đồng ý lưu tỷ lệ (server tính đề xuất Quỹ
 * dồn từ danh sách này và lưu khoản vào hũ khi `save_jars`). Server kiểm lại ngày trong 12 tháng tới.
 */
export function KnownItemsEditor({
  items,
  onChange,
  today,
}: {
  items: SplitProposalKnownItem[]
  onChange: (items: SplitProposalKnownItem[]) => void
  /** Ngày mô phỏng hôm nay (YYYY-MM-DD): ngày cần phải sau ngày này. */
  today?: string
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [date, setDate] = useState('')
  const [touched, setTouched] = useState(false)
  const nameErr = !name.trim()
    ? 'Nhập tên khoản'
    : items.some((i) => i.name.toLowerCase() === name.trim().toLowerCase())
      ? 'Khoản này đã có'
      : undefined
  const amountErr = !amount || Number(amount) < 1 ? 'Nhập số tiền lớn hơn 0' : undefined
  const dateErr = !/^\d{4}-\d{2}-\d{2}$/.test(date) || (today !== undefined && date <= today) ? 'Chọn ngày sau hôm nay' : undefined

  const add = () => {
    setTouched(true)
    if (nameErr || amountErr || dateErr) return
    onChange([...items, { name: name.trim(), amount_vnd: Number(amount), needed_date: date }])
    setName('')
    setAmount('')
    setDate('')
    setTouched(false)
    setOpen(false)
  }

  return (
    <section aria-label="Khoản biết trước trong 12 tháng tới" className="mt-5">
      <h2 className="text-subtitle font-semibold text-ink">Khoản biết trước trong 12 tháng tới</h2>
      <p className="text-small text-ink-2">Tùy chọn. Ví dụ Tết, học phí, bảo hiểm năm.</p>
      {items.length > 0 && (
        <ul className="mt-2 divide-y divide-line rounded-card bg-surface px-4 shadow-card" aria-label="Khoản biết trước đã thêm">
          {items.map((i) => (
            <li key={i.name} className="flex min-h-14 items-center justify-between gap-3 py-2">
              <div className="min-w-0">
                <p className="truncate text-body font-semibold text-ink">{i.name}</p>
                <p className="text-small text-ink-2">Cần trước {formatAppDate(i.needed_date)}</p>
              </div>
              <span className="num shrink-0 font-bold text-ink">{formatVnd(i.amount_vnd)}</span>
              <button
                type="button"
                aria-label={`Bỏ khoản ${i.name}`}
                onClick={() => onChange(items.filter((x) => x !== i))}
                className="grid size-11 shrink-0 place-items-center rounded-full text-ink-2"
              >
                <X className="size-5" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      {open ? (
        <div className="mt-2 space-y-3 rounded-card bg-surface p-4 shadow-card">
          <label className="block">
            <span className="mb-1.5 block text-small font-semibold text-ink-2">Tên khoản biết trước</span>
            <Input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} aria-invalid={touched && !!nameErr} placeholder="Ví dụ: Tết" />
          </label>
          {touched && nameErr && <span className="mt-1 block text-note font-semibold text-bad-fg">{nameErr}</span>}
          <MoneyInput label="Số tiền cần" value={amount} onChange={setAmount} error={touched ? amountErr : undefined} />
          <label className="block">
            <span className="mb-1.5 block text-small font-semibold text-ink-2">Ngày cần</span>
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} aria-invalid={touched && !!dateErr} />
          </label>
          {touched && dateErr && <span className="mt-1 block text-note font-semibold text-bad-fg">{dateErr}</span>}
          <div className="flex gap-2">
            <Button type="button" className="flex-1" onClick={add}>
              Thêm khoản này
            </Button>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Hủy
            </Button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="mt-2 flex min-h-12 w-full items-center justify-center gap-2 rounded-card border border-dashed border-line text-small font-semibold text-brand-text"
        >
          <Plus className="size-4" aria-hidden />
          Thêm khoản biết trước
        </button>
      )}
    </section>
  )
}
