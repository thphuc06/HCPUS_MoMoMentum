// Zod schema cho các khối UI do agent trả về (discriminated union theo `type`).
// Hình dạng bám docs/research/agentic-ui-generative-ui.md §5.1 và §9.4.
// Chỉ import zod, để Node 24 chạy trực tiếp được trong scripts/check-blocks.ts.
import { z } from 'zod'

const iso = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)
const vnd = z.number().int()

const envelope = {
  v: z.number().int().default(1),
  id: z.string(),
  trace_id: z.string().optional(),
  fallback_text: z.string().max(280),
}

const band = z.object({ date: iso, p10: vnd, p50: vnd, p90: vnd })
const runout = z.object({ date_p50: iso.nullable(), p_shortfall_before_payday: z.number().min(0).max(1) })

export const ForecastTimelineBlock = z.object({
  ...envelope,
  type: z.literal('forecast_timeline'),
  data: z.object({
    jar_id: z.string(),
    jar_name: z.string(),
    today: iso,
    payday: iso,
    series: z.array(band).min(2).max(400),
    events: z.array(z.object({ date: iso, kind: z.enum(['payday', 'obligation', 'scenario']), label: z.string().max(60), amount_vnd: vnd })).max(40),
    runout,
    scenario: z.object({ label: z.string().max(80), series: z.array(band).max(400), runout }).nullable().optional(),
    data_quality: z.enum(['high', 'medium', 'low']),
    data_quality_reasons: z.array(z.string()).max(3).default([]),
  }),
})

export const JarSummaryBlock = z.object({
  ...envelope,
  type: z.literal('jar_summary'),
  data: z.object({
    jar_id: z.string(),
    name: z.string().max(40),
    balance_vnd: vnd,
    plan_vnd: vnd.positive(),
    forecast_level_vnd: vnd,
    status: z.enum(['enough', 'tight', 'short']),
    status_label: z.string().max(80),
  }),
})

export const AffordabilityCardBlock = z.object({
  ...envelope,
  type: z.literal('affordability_card'),
  data: z.object({
    verdict: z.enum(['enough', 'tight', 'short']),
    item_label: z.string().max(60),
    pay_with_label: z.string().max(40),
    cost_lines: z.array(z.object({ label: z.string().max(60), amount_vnd: vnd })).max(6),
    total_real_cost_vnd: vnd,
    gap: z.object({ jar_id: z.string(), amount_vnd: vnd, when: iso }).nullable().optional(),
    runout_shift_days: z.number().int().nullable().optional(),
    rules: z.array(z.object({ id: z.string(), passed: z.boolean(), label: z.string().max(80) })).max(6),
  }),
})

export const ConfirmBlock = z.object({
  ...envelope,
  type: z.literal('confirm'),
  data: z.object({
    interrupt_id: z.string(),
    action_kind: z.enum(['move_between_jars', 'assign_jar', 'update_profile', 'record_transaction']),
    summary: z.string().max(120),
    jars: z.array(z.object({ jar_id: z.string(), jar_name: z.string(), before_vnd: vnd, after_vnd: vnd })).max(4),
    runout_before: iso.nullable().optional(),
    runout_after: iso.nullable().optional(),
    reversible: z.boolean(),
    approve_label: z.string().max(60),
  }),
})

export const BlockSchema = z.discriminatedUnion('type', [
  ForecastTimelineBlock,
  JarSummaryBlock,
  AffordabilityCardBlock,
  ConfirmBlock,
])

export type Block = z.infer<typeof BlockSchema>
export type BlockType = Block['type']
export type ForecastTimeline = z.infer<typeof ForecastTimelineBlock>
export type JarSummary = z.infer<typeof JarSummaryBlock>
export type AffordabilityCard = z.infer<typeof AffordabilityCardBlock>
export type Confirm = z.infer<typeof ConfirmBlock>

export const blockSchemas = {
  forecast_timeline: ForecastTimelineBlock,
  jar_summary: JarSummaryBlock,
  affordability_card: AffordabilityCardBlock,
  confirm: ConfirmBlock,
} as const
