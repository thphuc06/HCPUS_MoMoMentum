import { z } from 'zod'
import { ResilienceScoreBlock, ShockSummary, StressResultBlock } from '@/contracts/blocks'

export const ResilienceScoreResponse = ResilienceScoreBlock
export type ResilienceScoreResponse = z.infer<typeof ResilienceScoreResponse>

export const ShocksResponse = z.object({
  shocks: z.array(ShockSummary).min(1).max(12),
})
export type ShocksResponse = z.infer<typeof ShocksResponse>

export const StressRequest = z.strictObject({ shock_id: ShockSummary.shape.shock_id })
export type StressRequest = z.infer<typeof StressRequest>

export const StressResultResponse = StressResultBlock
export type StressResultResponse = z.infer<typeof StressResultResponse>
