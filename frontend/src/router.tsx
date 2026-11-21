import { Navigate, Outlet, createHashRouter, type RouteObject } from 'react-router'
import { TrendingUp } from 'lucide-react'
import { RequireAuth } from '@/auth/RequireAuth'
import { AppShell } from '@/layout/AppShell'
import { PhoneFrame } from '@/layout/PhoneFrame'
import { EmptyTabPage } from '@/pages/EmptyTabPage'
import { LoginPage } from '@/pages/LoginPage'
import { OverviewPage } from '@/pages/OverviewPage'
import { ProfilePage } from '@/pages/ProfilePage'

function JarGlyphLarge({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <rect x="8" y="2.5" width="8" height="3.5" rx="1" />
      <path d="M7 8.5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2V18a3.5 3.5 0 0 1-3.5 3.5h-3A3.5 3.5 0 0 1 7 18z" />
      <path d="M7 13h10" />
    </svg>
  )
}

export function appRoutes(): RouteObject[] {
  return [
    {
      element: (
        <PhoneFrame>
          <Outlet />
        </PhoneFrame>
      ),
      children: [
        { path: '/login', element: <LoginPage /> },
        {
          path: '/',
          element: (
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          ),
          children: [
            { index: true, element: <OverviewPage /> },
            {
              path: 'jars',
              element: (
                <EmptyTabPage
                  title="Hũ"
                  Icon={JarGlyphLarge}
                  message="Danh sách và chi tiết từng hũ sẽ có ở phiên bản sau. Bây giờ bạn xem số dư các hũ ở Tổng quan."
                />
              ),
            },
            {
              path: 'foresight',
              element: (
                <EmptyTabPage
                  title="Nhìn trước"
                  Icon={TrendingUp}
                  message="Dự báo ngày mỗi hũ cạn sẽ có ở phiên bản sau. Chưa có số liệu dự báo nào ở đây."
                />
              ),
            },
            { path: 'profile', element: <ProfilePage /> },
          ],
        },
        { path: '*', element: <Navigate to="/" replace /> },
      ],
    },
  ]
}

/** Hash router: không cần quy tắc rewrite SPA ở Amplify, tải lại trang không bị 404. */
export function createAppRouter() {
  return createHashRouter(appRoutes())
}
