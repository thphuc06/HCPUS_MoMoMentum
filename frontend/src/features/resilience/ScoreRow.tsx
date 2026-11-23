import type { ResilienceComponent } from '@/contracts/blocks'

export function ScoreRow({ component, weakest }: { component: ResilienceComponent; weakest: boolean }) {
  return (
    <li className="py-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="text-small font-semibold text-ink">
          {component.label}
          {weakest && <span className="ml-2 rounded-full bg-warn-bg px-2 py-0.5 text-note font-semibold text-warn-fg">Yếu nhất</span>}
        </p>
        {component.applicable ? (
          component.score !== undefined && <span className="num text-small font-bold text-ink">{component.score} điểm</span>
        ) : (
          <span className="text-small text-ink-2">Không áp dụng</span>
        )}
      </div>
      <p className="mt-1 text-small text-ink-2">{component.explanation}</p>
    </li>
  )
}
