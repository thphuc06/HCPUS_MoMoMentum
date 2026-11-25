import { z } from 'zod'
import {
  IsoDate,
  IsoDateTime,
  RoadmapAlternative,
  RoadmapBlock,
  RoadmapCounts,
  RoadmapData,
  RoadmapDiffBlock,
  RoadmapReason,
  RoadmapReasonCode,
  RoadmapStepStatus,
  RoadmapVersion,
  RoadmapVersionStatus,
  Uuid,
  VndPositive,
} from '@/contracts/blocks'
import { isIsoDate } from '@/lib/dates'
import { ApiError } from './errors'

export const RoadmapResponse = RoadmapBlock
export const RoadmapDiffResponse = RoadmapDiffBlock
export type RoadmapResponse = z.infer<typeof RoadmapResponse>
export type RoadmapDiffResponse = z.infer<typeof RoadmapDiffResponse>

export const RoadmapJob = z.strictObject({
  job_id: Uuid,
  status: z.enum(['queued', 'running', 'done', 'failed']),
  trigger: z.enum(['user_request', 'behavior_changed', 'goal_changed', 'income_changed', 'forecast_drift']),
  stage: z.enum(['context', 'draft', 'allocate', 'suitability', 'save']).optional(),
  progress: z.int().min(0).max(100),
  requested_at: IsoDateTime,
  finished_at: IsoDateTime.optional(),
  version: RoadmapVersion.optional(),
  roadmap_id: Uuid.optional(),
  error_code: z.string().regex(/^[A-Z][A-Z0-9_]*$/).optional(),
  error_message: z.string().min(1).max(280).optional(),
})
export type RoadmapJob = z.infer<typeof RoadmapJob>

export const RoadmapVersionSummary = z.strictObject({
  roadmap_id: Uuid,
  version: RoadmapVersion,
  status: RoadmapVersionStatus,
  reason_code: RoadmapReasonCode,
  reason_text: RoadmapReason.shape.text,
  based_on_version: RoadmapVersion.optional(),
  created_at: IsoDateTime,
  app_date: IsoDate,
  feasibility: RoadmapData.shape.feasibility,
  counts: RoadmapCounts,
})

export const RoadmapVersionsResponse = z.strictObject({
  versions: z.array(RoadmapVersionSummary).max(50),
  active_version: RoadmapVersion.optional(),
  proposed_version: RoadmapVersion.optional(),
  current_job: RoadmapJob.optional(),
})
export type RoadmapVersionsResponse = z.infer<typeof RoadmapVersionsResponse>

export const RoadmapStepDecisionRequest = z.strictObject({
  version: RoadmapVersion,
  decision: RoadmapStepStatus,
  reason: z.string().min(1).max(200).optional(),
})
export type RoadmapStepDecisionRequest = z.infer<typeof RoadmapStepDecisionRequest>

export const RoadmapStepEditRequest = z.strictObject({
  version: RoadmapVersion,
  amount_vnd: VndPositive.optional(),
  due_date: IsoDate.refine(isIsoDate).optional(),
}).refine(({ amount_vnd, due_date }) => amount_vnd !== undefined || due_date !== undefined)
export type RoadmapStepEditRequest = z.infer<typeof RoadmapStepEditRequest>

export const RoadmapVersionDecisionRequest = z.strictObject({
  decision: z.enum(['adopt', 'keep_previous']),
  // Một câu lý do tùy chọn khi "Giữ bản cũ" (server che PII rồi lưu cùng quyết định); với adopt thì server bỏ qua.
  reason: z.string().min(1).max(200).optional(),
})
export type RoadmapVersionDecisionRequest = z.infer<typeof RoadmapVersionDecisionRequest>

export const RegenerateRoadmapRequest = z.strictObject({
  note: z.string().min(1).max(200).optional(),
  alternative_id: RoadmapAlternative.shape.option_id.optional(),
  based_on_version: RoadmapVersion.optional(),
})
export type RegenerateRoadmapRequest = z.infer<typeof RegenerateRoadmapRequest>

type RoadmapQuery = { version: number } | { which: 'active' | 'proposed' | 'latest' }
type DiffQuery = { from_version?: number; to_version?: number }
type Call = <T>(method: string, path: string, schema: z.ZodType<T>, body?: unknown) => Promise<T>

function withQuery(path: string, query: Record<string, string | number | undefined>) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) params.set(key, String(value))
  }
  return params.size ? `${path}?${params}` : path
}

export function createRoadmapApi(call: Call) {
  async function post<T>(path: string, response: z.ZodType<T>, request: z.ZodType, body: unknown) {
    const parsed = request.safeParse(body)
    if (!parsed.success) throw new ApiError('PARAMS_INVALID', 0)
    return call('POST', path, response, parsed.data)
  }

  return {
    getRoadmap: (query?: RoadmapQuery) => call('GET', withQuery('/roadmap', query ?? {}), RoadmapResponse),
    listRoadmapVersions: (limit?: number) =>
      call('GET', withQuery('/roadmap/versions', { limit }), RoadmapVersionsResponse),
    getRoadmapDiff: (query: DiffQuery = {}) => call('GET', withQuery('/roadmap/diff', query), RoadmapDiffResponse),
    decideRoadmapStep: (stepId: string, req: RoadmapStepDecisionRequest) =>
      post(`/roadmap/steps/${encodeURIComponent(stepId)}/decision`, RoadmapResponse, RoadmapStepDecisionRequest, req),
    editRoadmapStep: (stepId: string, req: RoadmapStepEditRequest) =>
      post(`/roadmap/steps/${encodeURIComponent(stepId)}/edit`, RoadmapResponse, RoadmapStepEditRequest, req),
    decideRoadmapVersion: (version: number, req: RoadmapVersionDecisionRequest) =>
      post(`/roadmap/versions/${version}/decision`, RoadmapResponse, RoadmapVersionDecisionRequest, req),
    regenerateRoadmap: (req: RegenerateRoadmapRequest = {}) =>
      post('/roadmap/regenerate', RoadmapJob, RegenerateRoadmapRequest, req),
    getRoadmapJob: (jobId: string) => call('GET', `/roadmap/jobs/${encodeURIComponent(jobId)}`, RoadmapJob),
  }
}
