import { NavLink } from 'react-router'
import { Home, MessageCircle, TrendingUp, User } from 'lucide-react'
import { cn } from '@/lib/cn'

// Figma TabBar (5:218): 5 mục, nút giữa "Hỏi Yofina" nổi và mở sheet chat. Mỗi mục cao >= 56 px (vùng chạm >= 44 px).
function JarGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <rect x="8" y="2.5" width="8" height="3.5" rx="1" />
      <path d="M7 8.5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2V18a3.5 3.5 0 0 1-3.5 3.5h-3A3.5 3.5 0 0 1 7 18z" />
      <path d="M7 13h10" />
    </svg>
  )
}

const itemClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-note font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/40',
    isActive ? 'text-brand-text' : 'text-ink-2',
  )

export function TabBar({ onOpenChat, chatOpen }: { onOpenChat: () => void; chatOpen: boolean }) {
  return (
    <nav
      aria-label="Điều hướng chính"
      className="absolute inset-x-0 bottom-0 z-20 flex items-end border-t border-line bg-surface pb-[env(safe-area-inset-bottom)]"
    >
      <NavLink to="/" end className={itemClass}>
        <Home className="size-6" aria-hidden />
        Tổng quan
      </NavLink>
      <NavLink to="/jars" className={itemClass}>
        <JarGlyph className="size-6" />
        Hũ
      </NavLink>
      <div className="flex flex-1 flex-col items-center">
        <button
          type="button"
          onClick={onOpenChat}
          aria-haspopup="dialog"
          aria-expanded={chatOpen}
          className="-mt-5 flex min-h-14 flex-col items-center gap-0.5 text-note font-medium text-ink-2 outline-none"
        >
          <span className="grid size-14 place-items-center rounded-full bg-brand text-white shadow-card ring-4 ring-surface active:scale-95">
            <MessageCircle className="size-7" aria-hidden />
          </span>
          <span className="-mt-0.5">Hỏi Yofina</span>
        </button>
      </div>
      <NavLink to="/foresight" className={itemClass}>
        <TrendingUp className="size-6" aria-hidden />
        Nhìn trước
      </NavLink>
      <NavLink to="/profile" className={itemClass}>
        <User className="size-6" aria-hidden />
        Hồ sơ
      </NavLink>
    </nav>
  )
}
