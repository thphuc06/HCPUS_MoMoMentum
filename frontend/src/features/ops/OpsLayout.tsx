import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router'
import { ShieldAlert } from 'lucide-react'
import { useIsOps } from '@/auth/AuthProvider'
import type { ApiError } from '@/api/errors'
import { EmptyState, ErrorState } from '@/components/StateViews'
import { cn } from '@/lib/cn'

// Khung của bảng vận hành và màn trace (Figma X1 `25:2591`, desktop 1280×800). `data-layout="wide"` làm khung điện thoại giãn ra
// thành khung desktop trên màn rộng (index.css); trên điện thoại vẫn một cột cuộn dọc. Logo "Yofina · Trace" về Tổng quan.

const navClass = ({ isActive }: { isActive: boolean }) =>
  cn('flex min-h-11 items-center rounded-full px-3 text-small font-semibold', isActive ? 'bg-tint text-brand-text' : 'text-ink-2')

export function OpsLayout({ title, children }: { title: string; children: ReactNode }) {
  const ops = useIsOps()
  return (
    <div data-layout="wide" className="min-h-full">
      <header className="sticky top-0 z-10 flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line bg-surface px-4 pt-[max(12px,env(safe-area-inset-top))] pb-3 lg:px-6">
        <Link to="/" className="flex min-h-11 items-center text-subtitle font-bold text-ink" aria-label="Yofina · Trace, về Tổng quan">
          Yofina <span className="mx-1 text-ink-2">·</span> <span className="text-brand-text">Trace</span>
        </Link>
        {ops && (
          <nav aria-label="Bảng vận hành" className="flex gap-1">
            <NavLink to="/ops/summary" className={navClass}>Tổng hợp</NavLink>
          </nav>
        )}
        <h1 className="sr-only">{title}</h1>
      </header>
      <div className="px-4 py-4 lg:px-6">
        {ops ? children : <OpsForbidden />}
      </div>
    </div>
  )
}

export function OpsForbidden() {
  return (
    <EmptyState
      title="Chỉ dành cho đội vận hành"
      message="Tài khoản này không thuộc nhóm vận hành nên không xem được bảng vận hành và màn trace."
      action={<ShieldAlert className="size-6 text-ink-2" aria-hidden />}
    />
  )
}

/** Lỗi của `/ops/*`: 403 là không thuộc nhóm (token cũ chưa có nhóm, hoặc bị gỡ khỏi nhóm), hiện như trên; lỗi khác cho thử lại. */
export function OpsError({ error, title, onRetry }: { error: ApiError; title: string; onRetry: () => void }) {
  if (error.code === 'FORBIDDEN') return <OpsForbidden />
  return <ErrorState error={error} title={title} onRetry={onRetry} />
}
