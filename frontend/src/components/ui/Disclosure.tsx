import { useId, useState, type ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/cn'
import { usePrefersReducedMotion } from '@/lib/motion'

// Mục thu gọn dùng chung (Luật chữ, ui-design-review.md §9): chữ phụ (giải thích, bằng chứng, phương pháp, nguồn, mốc chi
// tiết) mặc định đóng, ai cần thì bấm. Nút là <button> thật nên bấm được bằng Enter/Space, có aria-expanded/aria-controls,
// vùng chạm cao 44 px. Phần đã đóng vẫn nằm trong DOM (inert, ẩn khỏi trình đọc màn hình và phím Tab) để mở ra mượt bằng
// grid-template-rows 0fr → 1fr; giảm chuyển động thì mở/đóng tức thì, mũi tên không xoay dần.

export type DisclosureState = { open: boolean; setOpen: (open: boolean) => void; toggle: () => void; panelId: string }

/** Trạng thái mở/đóng và id vùng nội dung, khi nút và vùng nội dung nằm ở hai chỗ khác nhau trong bố cục. */
export function useDisclosure(defaultOpen = false): DisclosureState {
  const [open, setOpen] = useState(defaultOpen)
  const panelId = useId()
  return { open, setOpen, toggle: () => setOpen((o) => !o), panelId }
}

export function DisclosureButton({ state, children, className, label }: {
  state: DisclosureState
  children: ReactNode
  className?: string
  /** Nhãn đầy đủ cho trình đọc màn hình khi chữ hiện ra quá ngắn (ví dụ "Vì sao bước Giữ sẵn khoản Trả sau"). */
  label?: string
}) {
  const reduced = usePrefersReducedMotion()
  return (
    <button
      type="button"
      aria-expanded={state.open}
      aria-controls={state.panelId}
      aria-label={label}
      onClick={state.toggle}
      data-disclosure-button=""
      className={cn(
        'inline-flex min-h-11 min-w-11 items-center gap-1 rounded-full px-1 text-small font-semibold text-brand-text outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50',
        className,
      )}
    >
      {children}
      <ChevronDown
        aria-hidden
        className={cn('size-4 shrink-0', !reduced && 'transition-transform duration-(--dur-2) ease-(--ease-out)', state.open && 'rotate-180')}
      />
    </button>
  )
}

export function DisclosurePanel({ state, children, className }: { state: DisclosureState; children: ReactNode; className?: string }) {
  const reduced = usePrefersReducedMotion()
  const { open } = state
  return (
    <div
      id={state.panelId}
      data-disclosure-panel={open ? 'open' : 'closed'}
      inert={!open}
      aria-hidden={!open}
      className={cn(
        'grid',
        open ? 'grid-rows-[1fr] opacity-100' : 'invisible grid-rows-[0fr] opacity-0',
        !reduced && 'transition-[grid-template-rows,opacity,visibility] duration-(--dur-3) ease-(--ease-out)',
      )}
    >
      <div className="min-h-0 overflow-hidden">
        <div className={className}>{children}</div>
      </div>
    </div>
  )
}

/** Nút "Chi tiết" (hoặc nhãn ngắn khác) và vùng nội dung ngay dưới nó. */
export function Disclosure({ label, children, defaultOpen = false, className, buttonClassName, panelClassName, ariaLabel }: {
  label: ReactNode
  children: ReactNode
  defaultOpen?: boolean
  className?: string
  buttonClassName?: string
  panelClassName?: string
  ariaLabel?: string
}) {
  const state = useDisclosure(defaultOpen)
  return (
    <div className={className} data-disclosure="">
      <DisclosureButton state={state} className={buttonClassName} label={ariaLabel}>
        {label}
      </DisclosureButton>
      <DisclosurePanel state={state} className={panelClassName}>
        {children}
      </DisclosurePanel>
    </div>
  )
}
