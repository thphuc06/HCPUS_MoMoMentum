import { ChevronRight } from 'lucide-react'
import { useId } from 'react'
import { Link } from 'react-router'
import type { ShockSummary } from '@/contracts/blocks'

export function ShockCard({ shock }: { shock: ShockSummary }) {
  const descriptionId = useId()

  return (
    <Link
      to={`/foresight/stress/${encodeURIComponent(shock.shock_id)}`}
      aria-label={shock.label}
      aria-describedby={descriptionId}
      className="flex min-h-11 items-center gap-3 rounded-card bg-surface px-4 py-3 shadow-card outline-none hover:bg-surface-2 focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <span className="min-w-0 flex-1">
        <span className="block text-subtitle font-semibold text-ink">{shock.label}</span>
        <span id={descriptionId} className="mt-0.5 block text-small text-ink-2">{shock.description}</span>
      </span>
      <ChevronRight className="size-5 shrink-0 text-ink-2" aria-hidden />
    </Link>
  )
}
