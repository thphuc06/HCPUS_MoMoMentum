import type { ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

// Figma AppBar (14:457): nút quay lại tròn, tiêu đề, vùng phụ bên phải. Vùng chạm >= 44 px.
export function ScreenHeader({ title, right, backTo, onBack }: { title: string; right?: ReactNode; backTo?: string; onBack?: () => void }) {
  const navigate = useNavigate()
  return (
    <header className="flex items-center gap-3 px-4 pt-[max(16px,env(safe-area-inset-top))] pb-3">
      <button
        type="button"
        aria-label="Quay lại"
        onClick={() => (onBack ? onBack() : backTo ? navigate(backTo) : navigate(-1))}
        className="grid size-11 shrink-0 place-items-center rounded-full border border-line bg-surface text-ink active:bg-surface-2"
      >
        <ArrowLeft className="size-5" aria-hidden />
      </button>
      <h1 className="min-w-0 flex-1 truncate text-section font-bold text-ink">{title}</h1>
      {right}
    </header>
  )
}
