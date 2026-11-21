import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { useAuth } from './AuthProvider'

// Route guard: chưa đăng nhập thì chuyển tới /login (nhớ trang đang xem); đang khôi phục phiên thì hiện chờ.
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  const location = useLocation()
  if (status === 'loading') {
    return (
      <div className="grid h-full place-items-center" role="status" aria-label="Đang tải">
        <div className="size-8 animate-spin rounded-full border-4 border-tint border-t-brand" />
      </div>
    )
  }
  if (status === 'signedOut') return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <>{children}</>
}
