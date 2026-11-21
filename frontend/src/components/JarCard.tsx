import { cn } from '@/lib/cn'
import { JarGlass } from './JarGlass'
import { JarIcon } from './JarIcon'
import { StatusChip } from './StatusChip'
import { formatVnd } from '@/lib/format'
import type { JarBalance } from '@/contracts/blocks'

// Figma JarCard (7:130): đầu thẻ (icon + tên + dòng phụ), hũ thủy tinh, số dư, chip trạng thái.
// Dòng phụ là tỷ lệ chia lương của hũ (có trong API). Mực nước = số dư so với hũ đầy nhất đang hiển thị
// (API phase 1 chưa có hạn mức hay kế hoạch tháng để đo "đầy" thật). Chip trạng thái chỉ hiện khi hũ hết tiền.
export function JarCard({ jar, level, className }: { jar: JarBalance; level: number; className?: string }) {
  const empty = jar.balance_vnd === 0
  return (
    <article
      data-jar={jar.code}
      className={cn('flex w-[180px] shrink-0 snap-start flex-col items-stretch gap-1.5 rounded-card bg-surface p-4 shadow-card', className)}
    >
      <header className="flex items-center gap-2">
        <JarIcon colorKey={jar.color_key} iconKey={jar.icon_key} size={32} />
        <div className="min-w-0">
          <h3 className="truncate text-subtitle font-semibold text-ink">{jar.name}</h3>
          <p className="truncate text-note font-medium text-ink-2">Chia lương {jar.split_percent}%</p>
        </div>
      </header>
      <JarGlass colorKey={jar.color_key} level={level} label={`Hũ ${jar.name}, số dư ${formatVnd(jar.balance_vnd)}`} />
      <p className="num text-center text-amount font-extrabold text-ink">{formatVnd(jar.balance_vnd)}</p>
      <div className="flex min-h-7 justify-center">{empty && <StatusChip kind="bad">Đã hết tiền</StatusChip>}</div>
    </article>
  )
}
