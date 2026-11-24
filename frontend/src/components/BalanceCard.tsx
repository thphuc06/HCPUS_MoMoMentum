import { useState, type ReactNode } from 'react'
import { Eye, EyeOff, Info } from 'lucide-react'
import { Disclosure } from '@/components/ui/Disclosure'
import { formatAppDate, formatVnd } from '@/lib/format'
import { useAnimateOnce, useCountUp } from '@/lib/motion'

// Figma BalanceCard (14:143): thẻ gradient chủ đạo, tổng số dư lớn, dòng "Ví mô phỏng", hàng hành động nhanh.
// Tổng = tổng MỌI hũ (gồm Tiền vào khác và Chưa phân loại) do server tính (`balance.total_vnd`); các dòng dưới thẻ
// giải thích tổng đến từ đâu. Hũ Chưa phân loại có thể ÂM: đó là khoản đã chi mà chưa xếp hũ, ghi theo giá trị tuyệt đối.
// Mỗi dòng có dấu cộng/trừ để "Trong N hũ" (đúng số "Tổng trong N hũ" ở tab Hũ) cộng trừ ra đúng Tổng số dư, không đọc thành
// hai con số mâu thuẫn (ui-design-review.md §10). Dấu chỉ để đọc; số vẫn là số server trả.
export type BalanceParts = { total_vnd: number; jars_total_vnd: number; other_income_vnd: number; unclassified_vnd: number }

/** Dấu cộng/trừ trước nhãn dòng; trình đọc màn hình đọc "cộng"/"trừ". */
function Sign({ plus }: { plus: boolean }) {
  return (
    <>
      <span aria-hidden className="num mr-1 inline-block w-3 font-bold">{plus ? '+' : '−'}</span>
      <span className="sr-only">{plus ? 'cộng ' : 'trừ '}</span>
    </>
  )
}

export function BalanceCard({ balance, appDate, jarsCount, children }: { balance: BalanceParts; appDate: string; jarsCount?: number; children?: ReactNode }) {
  const [hidden, setHidden] = useState(false)
  // Tổng số dư đếm lên một lần mỗi phiên khi mở app (cảnh 1); giảm chuyển động thì hiện thẳng số cuối.
  const shown = useCountUp(balance.total_vnd, useAnimateOnce('balance-total'))
  const mask = (v: number) => (hidden ? '•••••• ₫' : formatVnd(v))
  const un = balance.unclassified_vnd
  return (
    <section
      aria-label="Tổng số dư"
      className="rounded-sheet p-5 text-white shadow-card"
      style={{ background: 'var(--gradient-hero)' }}
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
      <p className="num mt-1 text-display font-extrabold">
        {/* Số cuối cho trình đọc màn hình; số đang đếm chỉ để nhìn (ui-design-review.md §4.6). */}
        <span className="sr-only" data-testid="balance-total">{mask(balance.total_vnd)}</span>
        <span aria-hidden>{hidden ? mask(balance.total_vnd) : formatVnd(shown)}</span>
      </p>
      <p className="mt-1 flex items-center gap-1.5 text-note font-medium text-white/90">
        <Info className="size-3.5 shrink-0" aria-hidden />
        <span>Ví mô phỏng · ngày mô phỏng {formatAppDate(appDate)}</span>
      </p>

      {/* Bảng ba dòng giải thích tổng đến từ đâu: chữ phụ, mặc định thu gọn (ui-design-review.md §5 cảnh 1, §9). */}
      <Disclosure label="Chi tiết số dư" className="mt-1" buttonClassName="text-white/90" panelClassName="pt-1">
      <dl className="grid gap-1.5 rounded-2xl bg-white/15 px-3.5 py-2.5 text-small" data-testid="balance-parts">
        <div className="flex justify-between gap-3">
          <dt>{jarsCount !== undefined ? `Trong ${jarsCount} hũ` : 'Trong các hũ'}</dt>
          <dd className="num font-semibold" data-testid="balance-jars">{mask(balance.jars_total_vnd)}</dd>
        </div>
        {balance.other_income_vnd !== 0 && (
          <div className="flex justify-between gap-3">
            <dt><Sign plus={balance.other_income_vnd > 0} /><span>Tiền vào khác (chưa gán hũ)</span></dt>
            <dd className="num font-semibold" data-testid="balance-other">{mask(Math.abs(balance.other_income_vnd))}</dd>
          </div>
        )}
        {un !== 0 && (
          <div className="flex justify-between gap-3">
            <dt><Sign plus={un > 0} /><span>{un < 0 ? 'Đã chi, chưa xếp hũ' : 'Chưa phân loại'}</span></dt>
            <dd className="num font-semibold" data-testid="balance-unclassified">{mask(Math.abs(un))}</dd>
          </div>
        )}
      </dl>
      </Disclosure>
      {children}
    </section>
  )
}
