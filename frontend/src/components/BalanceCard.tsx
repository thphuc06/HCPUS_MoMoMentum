import { useState, type ReactNode } from 'react'
import { Eye, EyeOff, Info } from 'lucide-react'
import { formatAppDate, formatVnd } from '@/lib/format'

// Figma BalanceCard (14:143): thẻ gradient chủ đạo, tổng số dư lớn, dòng "Ví mô phỏng", hàng hành động nhanh.
// Tổng = tổng MỌI hũ (gồm Tiền vào khác và Chưa phân loại) do server tính (`balance.total_vnd`); các dòng dưới thẻ
// giải thích tổng đến từ đâu. Hũ Chưa phân loại có thể ÂM: đó là khoản đã chi mà chưa xếp hũ, ghi theo giá trị tuyệt đối.
export type BalanceParts = { total_vnd: number; jars_total_vnd: number; other_income_vnd: number; unclassified_vnd: number }

export function BalanceCard({ balance, appDate, children }: { balance: BalanceParts; appDate: string; children?: ReactNode }) {
  const [hidden, setHidden] = useState(false)
  const mask = (v: number) => (hidden ? '•••••• ₫' : formatVnd(v))
  const un = balance.unclassified_vnd
  return (
    <section
      aria-label="Tổng số dư"
      className="rounded-sheet p-5 text-white shadow-card"
      style={{ background: 'linear-gradient(135deg, var(--brand-deep), var(--brand-primary))' }}
    >
      <div className="flex items-center justify-between">
        <h2 className="text-subtitle font-semibold">Tổng số dư</h2>
        <button
          type="button"
          onClick={() => setHidden((h) => !h)}
          aria-label={hidden ? 'Hiện số dư' : 'Ẩn số dư'}
          aria-pressed={hidden}
          className="grid size-11 place-items-center rounded-full bg-white/20 active:bg-white/30"
        >
          {hidden ? <EyeOff className="size-5" aria-hidden /> : <Eye className="size-5" aria-hidden />}
        </button>
      </div>
      <p className="num mt-1 text-display font-extrabold" data-testid="balance-total">
        {mask(balance.total_vnd)}
      </p>
      <p className="mt-1 flex items-center gap-1.5 text-note font-medium text-white/90">
        <Info className="size-3.5 shrink-0" aria-hidden />
        <span>Ví mô phỏng · ngày mô phỏng {formatAppDate(appDate)}</span>
      </p>

      <dl className="mt-3 grid gap-1.5 rounded-2xl bg-white/15 px-3.5 py-2.5 text-small" data-testid="balance-parts">
        <div className="flex justify-between gap-3">
          <dt>Trong các hũ</dt>
          <dd className="num font-semibold" data-testid="balance-jars">{mask(balance.jars_total_vnd)}</dd>
        </div>
        {balance.other_income_vnd !== 0 && (
          <div className="flex justify-between gap-3">
            <dt>Tiền vào khác (chưa gán hũ)</dt>
            <dd className="num font-semibold" data-testid="balance-other">{mask(balance.other_income_vnd)}</dd>
          </div>
        )}
        {un !== 0 && (
          <div className="flex justify-between gap-3">
            <dt>{un < 0 ? 'Đã chi, chưa xếp hũ' : 'Chưa phân loại'}</dt>
            <dd className="num font-semibold" data-testid="balance-unclassified">{mask(un < 0 ? Math.abs(un) : un)}</dd>
          </div>
        )}
      </dl>
      {children}
    </section>
  )
}
