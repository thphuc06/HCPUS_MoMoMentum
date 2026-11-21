import { useMemo } from 'react'
import { RouterProvider, type createMemoryRouter } from 'react-router'
import { AuthProvider } from '@/auth/AuthProvider'
import type { AuthClient } from '@/auth/types'
import type { Config } from '@/lib/config'
import { ConfigContext } from './AppContext'
import { createAppRouter } from './router'

export default function App({
  config,
  authClient,
  router,
}: {
  config: Config
  authClient: AuthClient
  router?: ReturnType<typeof createMemoryRouter>
}) {
  const r = useMemo(() => router ?? createAppRouter(), [router])
  return (
    <ConfigContext.Provider value={config}>
      <AuthProvider client={authClient}>
        <RouterProvider router={r} />
      </AuthProvider>
    </ConfigContext.Provider>
  )
}
