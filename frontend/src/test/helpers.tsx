import type { ReactNode } from 'react'
import { vi } from 'vitest'
import { ApiProvider, JarsProvider } from '@/api/ApiProvider'
import type { ApiClient } from '@/api/client'
import type { JarsResponse } from '@/api/schemas'
import { AuthProvider } from '@/auth/AuthProvider'
import type { AuthClient, AuthSession } from '@/auth/types'
import { ChatActionsContext, type ChatActions } from '@/chat/actions'
import { validBlock } from './fixtures'

export function session(overrides: Partial<AuthSession> = {}): AuthSession {
  return { accessToken: 'access-1', expiresAt: Date.now() + 60 * 60_000, email: 'nguoi.dung@example.invalid', ...overrides }
}

/** Máy khách xác thực giả có thể đếm lời gọi. */
export function fakeAuth(initial: AuthSession | null = session()): AuthClient & { current: AuthSession | null; getSession: ReturnType<typeof vi.fn> } {
  const c = {
    current: initial,
    restore: vi.fn(async () => c.current),
    signIn: vi.fn(async () => {
      c.current = session()
      return c.current
    }),
    getSession: vi.fn(async () => c.current),
    signOut: vi.fn(() => {
      c.current = null
    }),
  }
  return c as unknown as AuthClient & { current: AuthSession | null; getSession: ReturnType<typeof vi.fn> }
}

export function jarsFromFixture(): JarsResponse {
  const b = validBlock('jar_summary.seven_jars') as { data: { jars: JarsResponse['jars']; jars_total_vnd: number } }
  return { app_date: '2026-11-21', as_of: '2026-12-10T03:00:00Z', jars: b.data.jars, jars_total_vnd: b.data.jars_total_vnd }
}

export function fakeApi(over: Partial<ApiClient> = {}): ApiClient {
  return {
    getJars: vi.fn(async () => jarsFromFixture()),
    createConfirmation: vi.fn(async () => {
      throw new Error('createConfirmation chưa được giả')
    }),
    applyAction: vi.fn(async () => {
      throw new Error('applyAction chưa được giả')
    }),
    resetDemo: vi.fn(async () => {
      throw new Error('resetDemo chưa được giả')
    }),
    ...over,
  }
}

export function fakeChatActions() {
  return {
    replaceBlock: vi.fn<ChatActions['replaceBlock']>(),
    markBlock: vi.fn<ChatActions['markBlock']>(),
    addSystemNote: vi.fn<ChatActions['addSystemNote']>(),
  }
}

export function Providers({ api, actions, auth, children }: { api: ApiClient; actions?: ChatActions; auth?: AuthClient; children: ReactNode }) {
  const inner = (
    <ApiProvider client={api}>
      <JarsProvider>
        <ChatActionsContext.Provider value={actions ?? fakeChatActions()}>{children}</ChatActionsContext.Provider>
      </JarsProvider>
    </ApiProvider>
  )
  return auth ? <AuthProvider client={auth}>{inner}</AuthProvider> : inner
}
