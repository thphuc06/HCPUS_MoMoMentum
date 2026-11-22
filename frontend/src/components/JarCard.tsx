import { cn } from '@/lib/cn'
import { JarGlass } from './JarGlass'
import { JarIcon } from './JarIcon'
import { JarStatusChip } from './JarStatusChip'
import { formatPercent, formatVnd } from '@/lib/format'
import type { JarFull } from '@/api/schemas'

// Figma JarCard (7:130): đầu thẻ (icon + tên + dòng phụ), hũ thủy tinh có vạch "dự báo", số dư, chip trạng thái.
// Dòng phụ là tỷ lệ chia lương (có trong API). Vạch dự báo chỉ vẽ khi dự báo cho biết hũ cạn (mức 0); các hũ khác
// chưa có số dự báo ở Tổng quan nên không vẽ vạch.
export function JarCard({ jar, level, className }: { jar: JarFull; level: number; className?: string }) {
  const forecastLevel = jar.status === 'short' && jar.runout_date ? 0 : null
  return (
    <article
      data-jar={jar.code}
      data-status={jar.status ?? 'none'}
      className={cn('flex w-[180px] shrink-0 snap-start flex-col items-stretch gap-1.5 rounded-card bg-surface p-4 shadow-card', className)}
    >
      <header className="flex items-center gap-2">
        <JarIcon colorKey={jar.color_key} iconKey={jar.icon_key} size={32} />
        <div className="min-w-0">
          <h3 className="truncate text-subtitle font-semibold text-ink">{jar.name}</h3>
          <p className="truncate text-note font-medium text-ink-2">Chia lương {formatPercent(jar.split_percent)}</p>
        </div>
      </header>
      <JarGlass colorKey={jar.color_key} level={level} forecastLevel={forecastLevel} label={`Hũ ${jar.name}, số dư ${formatVnd(jar.balance_vnd)}`} />
      <p className="num text-center text-amount font-extrabold text-ink">{formatVnd(jar.balance_vnd)}</p>
      <div className="flex min-h-7 justify-center">
        <JarStatusChip jar={jar} />
      </div>
    </article>
  )
}
