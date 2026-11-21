import { cn } from '@/lib/cn'
import { jarColor, jarIconFor } from './jarTheme'

// Figma JarIcon (7:46): vòng tròn nền nhạt theo màu hũ, biểu tượng nét mảnh cùng màu.
export function JarIcon({ colorKey, iconKey, size = 40, className }: { colorKey: string; iconKey: string; size?: number; className?: string }) {
  const Icon = jarIconFor(iconKey)
  const color = jarColor(colorKey)
  return (
    <span
      aria-hidden
      className={cn('grid shrink-0 place-items-center rounded-full', className)}
      style={{ width: size, height: size, background: `color-mix(in srgb, ${color} 22%, var(--bg-surface))`, color }}
    >
      <Icon style={{ width: size * 0.5, height: size * 0.5 }} strokeWidth={2.2} />
    </span>
  )
}
