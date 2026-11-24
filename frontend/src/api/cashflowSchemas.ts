import { z } from 'zod'
import { IsoDate, IsoDateTime, JarCode, Vnd, VndSigned } from '@/contracts/blocks'

// Zod của `GET /cashflow` (contracts/rest/openapi.yaml, `CashflowResponse`): bản REST của tool `ledger___get_cashflow_summary` cho
// ba biểu đồ chi tiêu ở màn Hoạt động (B1, B5, B7). Viết tay như các REST khác (gen_contracts.mjs chỉ sinh khối); test
// api/openapi.test.ts so trường bắt buộc với hợp đồng và chạy fixture contracts/fixtures/rest/CashflowResponse.* qua đây.
// Phía đọc dễ tính (z.object bỏ trường lạ). Mọi số tiền, chênh lệch và lũy kế là số server trả; giao diện chỉ vẽ.

const DayIndex = z.int().min(1).max(31)

export const CashflowPeriod = z.object({
  kind: z.enum(['pay_period', 'calendar_month']),
  from_date: IsoDate,
  to_date: IsoDate,
  end_date: IsoDate,
  day_index: DayIndex,
  days_total: DayIndex,
})
export type CashflowPeriod = z.infer<typeof CashflowPeriod>

export const CashflowTotals = z.object({
  from_date: IsoDate,
  to_date: IsoDate,
  end_date: IsoDate.optional(),
  salary_income_vnd: Vnd,
  other_income_vnd: Vnd,
  spent_vnd: Vnd,
  net_vnd: VndSigned,
  obligation_vnd: Vnd.optional(),
  credit_vnd: Vnd.optional(),
  regular_spent_vnd: Vnd.optional(),
})
export type CashflowTotals = z.infer<typeof CashflowTotals>

export const CashflowJar = z.object({
  jar: JarCode,
  name: z.string().min(1).max(40),
  spent_vnd: Vnd,
  tx_count: z.int().min(0),
  obligation_vnd: Vnd.optional(),
  credit_vnd: Vnd.optional(),
  previous_spent_vnd: Vnd.optional(),
  change_vnd: VndSigned.optional(),
})
export type CashflowJar = z.infer<typeof CashflowJar>

export const CashflowDay = z.object({
  date: IsoDate,
  day_index: DayIndex,
  spent_vnd: Vnd,
  cumulative_vnd: Vnd,
  obligation_vnd: Vnd.optional(),
  regular_cumulative_vnd: Vnd.optional(),
})
export type CashflowDay = z.infer<typeof CashflowDay>

export const CashflowChange = z.object({ spent_vnd: VndSigned, regular_vnd: VndSigned.optional() })

export const CashflowResponse = z.object({
  as_of: IsoDateTime,
  app_date: IsoDate,
  period: CashflowPeriod,
  current: CashflowTotals,
  previous: CashflowTotals.optional(),
  change: CashflowChange.optional(),
  by_jar: z.array(CashflowJar).max(40),
  daily: z.array(CashflowDay).min(1).max(31),
  previous_daily: z.array(CashflowDay).min(1).max(31).optional(),
  unclassified_pending_vnd: Vnd,
  split_complete: z.boolean(),
})
export type CashflowResponse = z.infer<typeof CashflowResponse>

type Call = <T>(method: string, path: string, schema: z.ZodType<T>, body?: unknown) => Promise<T>

export function createCashflowApi(call: Call) {
  return {
    /** Thu, chi, chi theo hũ của kỳ lương này so với kỳ trước cùng thời điểm, kèm chuỗi theo ngày (chỉ đọc). */
    getCashflow: () => call('GET', '/cashflow', CashflowResponse),
  }
}
