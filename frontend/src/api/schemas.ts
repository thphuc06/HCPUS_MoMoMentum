import { z } from 'zod'
import {
  IsoDate,
  IsoDateTime,
  JarBalance,
  MoveParams,
  ReceiptBlock,
  Vnd,
} from '@/contracts/blocks'

// Zod cho thân phản hồi REST, theo contracts/rest/openapi.yaml; dùng lại kiểu nguyên tử từ
// contracts/blocks (sinh tự động) để một nguồn sự thật.

export const JarsResponse = z.object({
  app_date: IsoDate,
  as_of: IsoDateTime,
  jars: z.array(JarBalance).max(20),
  jars_total_vnd: Vnd,
})
export type JarsResponse = z.infer<typeof JarsResponse>

export const ToolName = z.enum(['move_between_jars'])
export type ToolName = z.infer<typeof ToolName>

export const ConfirmationRequest = z.object({
  tool: ToolName,
  params: MoveParams,
  params_hash: z.string().regex(/^[0-9a-f]{64}$/).optional(),
})
export type ConfirmationRequest = z.infer<typeof ConfirmationRequest>

export const ConfirmationResponse = z.object({
  confirm_token: z.string().min(3).max(1024),
  expires_at: IsoDateTime,
  ttl_seconds: z.int().min(1),
  tool: ToolName,
  params: MoveParams,
  params_hash: z.string().regex(/^[0-9a-f]{64}$/),
})
export type ConfirmationResponse = z.infer<typeof ConfirmationResponse>

export const ActionRequest = z.object({
  tool: ToolName,
  params: MoveParams,
  confirm_token: z.string().max(1024).optional(),
})
export type ActionRequest = z.infer<typeof ActionRequest>

/** POST /actions trả thẳng một khối `receipt`. */
export const ActionResponse = ReceiptBlock
export type ActionResponse = z.infer<typeof ActionResponse>

export const ResetResponse = z.object({
  reset_at: IsoDateTime,
  app_date: IsoDate,
  clock_offset_days: z.int(),
  jars_count: z.int().min(0),
  transactions_count: z.int().min(0),
})
export type ResetResponse = z.infer<typeof ResetResponse>
