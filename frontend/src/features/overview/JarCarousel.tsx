import { Link } from 'react-router'
import { JarCard } from '@/components/JarCard'
import type { JarFull } from '@/api/schemas'
import { jarForecastLevel, jarLevel } from '@/lib/jar'
import { useAnimateOnce, useRisingLevels } from '@/lib/motion'

/**
 * Dải thẻ hũ ở Tổng quan. Lần đầu mở trong phiên, nước trong từng hũ dâng từ đáy lên mức thật, lệch 40 ms mỗi hũ (cảnh 1,
 * ui-design-review.md §5); giảm chuyển động thì vẽ thẳng mức thật. Mức nước chỉ để vẽ (lib/jar.ts), số dư là số server trả.
 */
export function JarCarousel({ jars }: { jars: JarFull[] }) {
  const max = Math.max(0, ...jars.map((j) => j.balance_vnd))
  const levels = useRisingLevels(
    jars.map((j) => jarLevel(j, max)),
    useAnimateOnce('jar-water'),
  )
  return (
    <ul className="flex snap-x gap-3 overflow-x-auto scroll-px-4 px-4 pt-1 pb-4 [scrollbar-width:none]" aria-label="Danh sách hũ">
      {jars.map((j, i) => (
        <li key={j.code} className="shrink-0">
          <Link to={`/jars/${j.code}`} className="block text-left" aria-label={`Mở hũ ${j.name}`}>
            <JarCard jar={j} level={levels[i] ?? 0} forecastLevel={jarForecastLevel(j, max)} />
          </Link>
        </li>
      ))}
    </ul>
  )
}
