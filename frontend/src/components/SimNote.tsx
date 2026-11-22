import { Info } from 'lucide-react'
import { useOverview } from '@/api/OverviewProvider'
import { formatAppDate } from '@/lib/format'

/** Dòng cuối mỗi màn: "Ví mô phỏng · ngày mô phỏng dd/mm/yyyy" (ngày lấy từ server; chưa có thì chỉ ghi "Ví mô phỏng"). */
export function SimNote({ className }: { className?: string }) {
  const ov = useOverview()
  return (
    <p className={`flex items-center justify-center gap-1.5 px-4 py-4 text-note text-ink-2 ${className ?? ''}`} data-testid="sim-note">
      <Info className="size-3.5 shrink-0" aria-hidden />
      <span>Ví mô phỏng{ov.data ? ` · ngày mô phỏng ${formatAppDate(ov.data.app_date)}` : ''}</span>
    </p>
  )
}
