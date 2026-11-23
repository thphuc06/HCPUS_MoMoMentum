import type { ComponentType } from 'react'
import { Navigate, Outlet, createHashRouter, type RouteObject } from 'react-router'
import { Skeleton } from '@/components/ui/skeleton'
import { RequireAuth } from '@/auth/RequireAuth'
import { AppShell } from '@/layout/AppShell'
import { PhoneFrame } from '@/layout/PhoneFrame'
import { TransferFlowProvider } from '@/features/transfer/TransferFlow'
import { ForesightPage } from '@/pages/ForesightPage'
import { JarsPage } from '@/pages/JarsPage'
import { LoginPage } from '@/pages/LoginPage'
import { OverviewPage } from '@/pages/OverviewPage'
import { ProfilePage } from '@/pages/ProfilePage'

// Màn ít dùng hơn tải theo route (chunk riêng) để phần tải đầu nhẹ: Tổng quan, Hũ, Nhìn trước, Hồ sơ và Đăng nhập vẫn nằm sẵn.
const page = <K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) => ({
  lazy: async () => ({ Component: (await load())[name] }),
})

// Vào thẳng một màn tải theo route (chunk riêng, ví dụ mở lại #/jars/an_uong): chờ chunk về thì hiện khung chờ, khỏi trắng
// màn và khỏi cảnh báo thiếu HydrateFallback của React Router.
function InitialLoading() {
  return (
    <PhoneFrame>
      <div role="status" aria-busy="true" aria-label="Đang tải" data-state="loading" className="space-y-3 px-4 pt-[max(24px,env(safe-area-inset-top))]">
        <Skeleton className="h-14 w-full rounded-card" />
        <Skeleton className="h-[220px] w-full rounded-card" />
        <Skeleton className="h-[120px] w-full rounded-card" />
      </div>
    </PhoneFrame>
  )
}

export function appRoutes(): RouteObject[] {
  return [
    {
      HydrateFallback: InitialLoading,
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
            { path: 'onboarding', ...page(() => import('@/pages/OnboardingPage'), 'OnboardingPage') },
            { path: 'jars', element: <JarsPage /> },
            { path: 'jars/edit', ...page(() => import('@/pages/JarsEditPage'), 'JarsEditPage') },
            { path: 'jars/:code', ...page(() => import('@/pages/JarDetailPage'), 'JarDetailPage') },
            {
              path: 'foresight',
              children: [
                { index: true, element: <ForesightPage /> },
                { path: 'stress/:shockId', ...page(() => import('@/pages/StressPage'), 'StressPage') },
                { path: 'resilience', ...page(() => import('@/pages/ResilienceDetailPage'), 'ResilienceDetailPage') },
              ],
            },
            {
              path: 'roadmap',
              children: [
                { index: true, ...page(() => import('@/pages/RoadmapPage'), 'RoadmapPage') },
                { path: 'compare', ...page(() => import('@/pages/RoadmapComparePage'), 'RoadmapComparePage') },
              ],
            },
            {
              // Chuyển tiền T1 → T2 → T3 (kiểm tra) → T4 → T5; trạng thái nháp nằm trong TransferFlowProvider.
              path: 'transfer',
              element: (
                <TransferFlowProvider>
                  <Outlet />
                </TransferFlowProvider>
              ),
              children: [
                { index: true, ...page(() => import('@/pages/transfer/TransferPayeePage'), 'TransferPayeePage') },
                { path: 'amount', ...page(() => import('@/pages/transfer/TransferAmountPage'), 'TransferAmountPage') },
                { path: 'check', ...page(() => import('@/pages/transfer/TransferCheckPage'), 'TransferCheckPage') },
                { path: 'review', ...page(() => import('@/pages/transfer/TransferReviewPage'), 'TransferReviewPage') },
                { path: 'receipt', ...page(() => import('@/pages/transfer/TransferReceiptPage'), 'TransferReceiptPage') },
              ],
            },
            { path: 'activity', ...page(() => import('@/pages/ActivityPage'), 'ActivityPage') },
            { path: 'review', ...page(() => import('@/pages/ReviewPage'), 'ReviewPage') },
            { path: 'obligations', ...page(() => import('@/pages/ObligationsPage'), 'ObligationsPage') },
            { path: 'obligations/new', ...page(() => import('@/pages/ObligationEditPage'), 'ObligationEditPage') },
            { path: 'obligations/:id', ...page(() => import('@/pages/ObligationEditPage'), 'ObligationEditPage') },
            { path: 'income', ...page(() => import('@/pages/IncomePage'), 'IncomePage') },
            { path: 'ingest', ...page(() => import('@/pages/IngestPage'), 'IngestPage') },
            { path: 'move', ...page(() => import('@/pages/MovePage'), 'MovePage') },
            { path: 'salary', ...page(() => import('@/pages/SalaryPage'), 'SalaryPage') },
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
