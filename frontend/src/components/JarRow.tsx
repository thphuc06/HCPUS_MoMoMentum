import { ChevronRight } from 'lucide-react'
import { JarIcon } from './JarIcon'
import { JarStatusChip } from './JarStatusChip'
import { formatPercent, formatVnd } from '@/lib/format'
import type { JarFull } from '@/api/schemas'

// Figma JarRow (14:236): icon, tên, dòng phụ, số dư, chip trạng thái. Dòng phụ: tỷ lệ chia lương (và mục tiêu nếu có).
export function JarRow({ jar }: { jar: JarFull }) {
  const sub = jar.split_percent > 0 ? `Chia lương ${formatPercent(jar.split_percent)}` : jar.kind === 'system' ? 'Hũ hệ thống' : 'Chưa chia lương'
  return (
    <div className="flex min-h-[72px] items-center gap-3" data-jar={jar.code}>
      <JarIcon colorKey={jar.color_key} iconKey={jar.icon_key} size={40} />
      <div className="min-w-0 flex-1">
        <h3 className="text-subtitle font-semibold text-ink">{jar.name}</h3>
        <p className="text-small text-ink-2">{sub}</p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        <span className="num text-amount font-extrabold text-ink">{formatVnd(jar.balance_vnd)}</span>
        {jar.kind !== 'system' && <JarStatusChip jar={jar} />}
      </div>
      <ChevronRight className="size-5 shrink-0 text-ink-2" aria-hidden />
    </div>
  )
}
