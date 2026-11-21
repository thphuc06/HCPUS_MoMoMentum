import { useState } from 'react'
import { Eye, EyeOff, Info } from 'lucide-react'
import { formatAppDate, formatVnd } from '@/lib/format'

// Figma BalanceCard (14:143): thẻ gradient chủ đạo, tổng số dư lớn, dòng "Ví mô phỏng". Tổng = jars_total_vnd
// của GET /jars. Hàng nút nhanh (Chuyển tiền, Quét QR...) của Figma thuộc các phase sau nên chưa có.
export function BalanceCard({ totalVnd, appDate }: { totalVnd: number; appDate: string }) {
  const [hidden, setHidden] = useState(false)
  return (
    <section
      aria-label="Tổng số dư"
      className="rounded-sheet p-5 text-white shadow-card"
      style={{ background: 'linear-gradient(135deg, var(--brand-deep), var(--brand-primary))' }}
    >
      <div className="flex items-center justify-between">
        <h2 className="text-subtitle font-semibold">Tổng số dư các hũ</h2>
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
        {hidden ? '••••••• ₫' : formatVnd(totalVnd)}
      </p>
      <p className="mt-1 flex items-center gap-1.5 text-note font-medium text-white/90">
        <Info className="size-3.5 shrink-0" aria-hidden />
        <span>Ví mô phỏng · ngày mô phỏng {formatAppDate(appDate)}</span>
      </p>
    </section>
  )
}
