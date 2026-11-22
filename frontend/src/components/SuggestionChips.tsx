import { cn } from '@/lib/cn'

// Figma SuggestionChips (10:215): chip bấm được, gửi `prompt` như tin nhắn kế tiếp. Vùng chạm tối thiểu 44 px.
export function SuggestionChips({
  items,
  onPick,
  disabled,
  label = 'Gợi ý',
  className,
}: {
  items: ReadonlyArray<{ id: string; label: string; prompt: string }>
  onPick: (prompt: string, item: { id: string; label: string }) => void
  disabled?: boolean
  label?: string
  className?: string
}) {
  return (
    <ul className={cn('flex flex-wrap gap-2', className)} aria-label={label}>
      {items.map((it) => (
        <li key={it.id}>
          <button
            type="button"
            data-chip-id={it.id}
            disabled={disabled}
            onClick={() => onPick(it.prompt, it)}
            className="min-h-11 rounded-full border border-line bg-surface px-4 py-2 text-left text-small font-semibold text-ink active:scale-[0.99] disabled:opacity-50"
          >
            {it.label}
          </button>
        </li>
      ))}
    </ul>
  )
}
