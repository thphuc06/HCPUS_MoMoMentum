import type { ReactNode } from 'react'
import { vi } from 'vitest'
import { ApiProvider } from '@/api/ApiProvider'
import { OverviewProvider } from '@/api/OverviewProvider'
import type { ApiClient } from '@/api/client'
import type {
  AffordabilityResponse,
  CreditLineResponse,
  FeedbackResponse,
  TraceResponse,
  ForecastResponse,
  JarDetailResponse,
  JarTemplatesResponse,
  JarsResponse,
  ObligationsResponse,
  OverviewResponse,
  PayeesResponse,
  ProfileResponse,
  SalaryEventsResponse,
  TransactionsResponse,
  TxTypesResponse,
} from '@/api/schemas'
import { AuthProvider } from '@/auth/AuthProvider'
import type { AuthClient, AuthSession } from '@/auth/types'
import { ChatActionsContext, type ChatActions } from '@/chat/actions'
import { restFixture, validBlock } from './fixtures'

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

const fx = <T,>(name: string) => restFixture(name) as unknown as T

/** Mặc định mọi GET trả fixture hợp đồng (persona minh); test ghi đè từng hàm khi cần. */
export function fakeApi(over: Partial<ApiClient> = {}): ApiClient {
  return {
    getJars: vi.fn(async () => jarsFromFixture()),
    getOverview: vi.fn(async () => fx<OverviewResponse>('OverviewResponse.minh')),
    getProfile: vi.fn(async () => fx<ProfileResponse>('ProfileResponse.minh')),
    getJar: vi.fn(async () => fx<JarDetailResponse>('JarDetailResponse.an_uong')),
    getForecast: vi.fn(async () => validBlock('forecast_timeline.short') as unknown as ForecastResponse),
    listTransactions: vi.fn(async () => fx<TransactionsResponse>('TransactionsResponse.page')),
    listTxTypes: vi.fn(async () => fx<TxTypesResponse>('TxTypesResponse.default')),
    listPayees: vi.fn(async () => fx<PayeesResponse>('PayeesResponse.default')),
    listObligations: vi.fn(async () => fx<ObligationsResponse>('ObligationsResponse.active')),
    getCreditLine: vi.fn(async () => fx<CreditLineResponse>('CreditLineResponse.default')),
    listSalaryEvents: vi.fn(async () => fx<SalaryEventsResponse>('SalaryEventsResponse.pending')),
    listJarTemplates: vi.fn(async () => fx<JarTemplatesResponse>('JarTemplatesResponse.default')),
    createConfirmation: vi.fn(async () => {
      throw new Error('createConfirmation chưa được giả')
    }),
    cancelConfirmation: vi.fn(async (req) => ({ block_id: req.confirm_block_id, status: 'cancelled' as const, resolved_at: '2026-12-10T03:00:00Z' })),
    applyAction: vi.fn(async () => {
      throw new Error('applyAction chưa được giả')
    }),
    resetDemo: vi.fn(async () => {
      throw new Error('resetDemo chưa được giả')
    }),
    checkAffordability: vi.fn(async () => validBlock('affordability_card.transfer_250k') as unknown as AffordabilityResponse),
    getTrace: vi.fn(async () => fx<TraceResponse>('TraceResponse.what_if')),
    submitFeedback: vi.fn(async (req) => ({ ...fx<FeedbackResponse>('FeedbackResponse.default'), decision: req.decision })),
    createIngestUpload: vi.fn(async () => {
      throw new Error('createIngestUpload chưa được giả')
    }),
    listIngestJobs: vi.fn(async () => ({ jobs: [] })),
    getIngestJob: vi.fn(async () => {
      throw new Error('getIngestJob chưa được giả')
    }),
    setIngestRowJar: vi.fn(async () => {
      throw new Error('setIngestRowJar chưa được giả')
    }),
    createIngestConfirmation: vi.fn(async () => {
      throw new Error('createIngestConfirmation chưa được giả')
    }),
    applyIngestAction: vi.fn(async () => {
      throw new Error('applyIngestAction chưa được giả')
    }),
    ...over,
  }
}

/** Id cuộc hội thoại mà `fakeChatActions` trả về. */
export const CONVERSATION_ID = '11111111-2222-4333-8444-555555555555'

export function fakeChatActions() {
  return {
    replaceBlock: vi.fn<ChatActions['replaceBlock']>(),
    markBlock: vi.fn<ChatActions['markBlock']>(),
    addSystemNote: vi.fn<ChatActions['addSystemNote']>(),
    getConversationId: vi.fn<ChatActions['getConversationId']>(() => CONVERSATION_ID),
    reloadConversation: vi.fn<ChatActions['reloadConversation']>(async () => {}),
    ask: vi.fn<ChatActions['ask']>(),
    retryLast: vi.fn<ChatActions['retryLast']>(),
    askAgain: vi.fn<ChatActions['askAgain']>(),
    revealBlock: vi.fn<ChatActions['revealBlock']>(),
    undoWindowMs: 30_000,
  }
}

export function Providers({ api, actions, auth, children }: { api: ApiClient; actions?: ChatActions; auth?: AuthClient; children: ReactNode }) {
  const inner = (
    <ApiProvider client={api}>
      <OverviewProvider>
        <ChatActionsContext.Provider value={actions ?? fakeChatActions()}>{children}</ChatActionsContext.Provider>
      </OverviewProvider>
    </ApiProvider>
  )
  return auth ? <AuthProvider client={auth}>{inner}</AuthProvider> : inner
}
