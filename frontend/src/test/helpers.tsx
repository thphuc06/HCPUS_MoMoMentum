import type { ReactNode } from 'react'
import { vi } from 'vitest'
import { ApiProvider } from '@/api/ApiProvider'
import { OverviewProvider } from '@/api/OverviewProvider'
import type { ApiClient } from '@/api/client'
import type { ResilienceScoreResponse, ShocksResponse, StressResultResponse } from '@/api/resilienceSchemas'
import type { RoadmapDiffResponse, RoadmapResponse, RoadmapVersionsResponse } from '@/api/roadmapSchemas'
import type { CashflowResponse } from '@/api/cashflowSchemas'
import type {
  BehaviorProfileResponse,
  DataDeletion,
  DeleteDataConfirmationResponse,
  MemoryClearResponse,
  MemoryListResponse,
  NudgeTodayResponse,
  OpsSummaryResponse,
  OpsTraceDetail,
  OpsTraceListResponse,
} from '@/api/phase5Schemas'
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
    getCashflow: vi.fn(async () => fx<CashflowResponse>('CashflowResponse.minh')),
    getProfile: vi.fn(async () => fx<ProfileResponse>('ProfileResponse.minh')),
    getJar: vi.fn(async () => fx<JarDetailResponse>('JarDetailResponse.an_uong')),
    getForecast: vi.fn(async () => validBlock('forecast_timeline.short') as unknown as ForecastResponse),
    getResilience: vi.fn(async () => fx<ResilienceScoreResponse>('ResilienceScoreResponse.minh')),
    getShocks: vi.fn(async () => fx<ShocksResponse>('ShocksResponse.default')),
    runStress: vi.fn(async () => fx<StressResultResponse>('StressResultResponse.mat_viec')),
    getRoadmap: vi.fn(async () => fx<RoadmapResponse>('RoadmapResponse.minh_v3')),
    listRoadmapVersions: vi.fn(async () => fx<RoadmapVersionsResponse>('RoadmapVersionsResponse.minh')),
    getRoadmapDiff: vi.fn(async () => fx<RoadmapDiffResponse>('RoadmapDiffResponse.v2_v3')),
    decideRoadmapStep: vi.fn(async () => { throw new Error('decideRoadmapStep chưa được giả') }),
    editRoadmapStep: vi.fn(async () => { throw new Error('editRoadmapStep chưa được giả') }),
    decideRoadmapVersion: vi.fn(async () => { throw new Error('decideRoadmapVersion chưa được giả') }),
    regenerateRoadmap: vi.fn(async () => { throw new Error('regenerateRoadmap chưa được giả') }),
    getRoadmapJob: vi.fn(async () => { throw new Error('getRoadmapJob chưa được giả') }),
    getReview: vi.fn(async (mode) => fx<Awaited<ReturnType<ApiClient['getReview']>>>(`ReviewListResponse.${mode}`)),
    skipReviewAsk: vi.fn(async () => { throw new Error('skipReviewAsk chưa được giả') }),
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
    getBehaviorProfile: vi.fn(async () => fx<BehaviorProfileResponse>('BehaviorProfileResponse.minh')),
    getTodayNudge: vi.fn(async () => fx<NudgeTodayResponse>('NudgeTodayResponse.trong')),
    submitNudgeFeedback: vi.fn(async (nudgeId, req) => ({ nudge_id: nudgeId, outcome: req.outcome, recorded_at: '2026-12-10T03:00:00Z' })),
    listMemory: vi.fn(async () => fx<MemoryListResponse>('MemoryListResponse.minh')),
    deleteMemoryRecord: vi.fn(async (recordId) => ({ record_id: recordId, deleted: true as const })),
    clearMemory: vi.fn(async () => fx<MemoryClearResponse>('MemoryClearResponse.default')),
    createDeleteDataConfirmation: vi.fn(async () => fx<DeleteDataConfirmationResponse>('ConfirmationResponse.delete_my_data')),
    deleteMyData: vi.fn(async () => fx<DataDeletion>('DataDeletion.done')),
    listOpsTraces: vi.fn(async () => fx<OpsTraceListResponse>('OpsTraceListResponse.default')),
    getOpsTrace: vi.fn(async () => fx<OpsTraceDetail>('OpsTraceDetail.what_if')),
    getOpsSummary: vi.fn(async () => fx<OpsSummaryResponse>('OpsSummaryResponse.default')),
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
