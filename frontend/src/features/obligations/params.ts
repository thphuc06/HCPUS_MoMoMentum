import type { Obligation, ToolParams } from '@/api/schemas'

export type ObligationKindInput = 'rent' | 'bill' | 'subscription' | 'loan'
export type CycleInput = 'monthly' | 'weekly' | 'yearly' | 'once'

export const KIND_LABEL: Record<string, string> = {
  rent: 'Tiền trọ',
  bill: 'Hóa đơn',
  subscription: 'Thuê bao',
  loan: 'Khoản vay',
  bnpl: 'Trả sau',
}

export const CYCLE_LABEL: Record<string, string> = {
  monthly: 'Hằng tháng',
  weekly: 'Hằng tuần',
  yearly: 'Hằng năm',
  once: 'Một lần',
}

export type ObligationForm = {
  id?: string
  kind: ObligationKindInput
  name: string
  /** 'fixed' dùng `amount`; 'range' dùng `min` và `max`. */
  amountMode: 'fixed' | 'range'
  amount: string
  min: string
  max: string
  cycle: CycleInput
  /** Ngày đến hạn trong tháng (chu kỳ hằng tháng). */
  dueDay: string
  /** Ngày đến hạn đầy đủ YYYY-MM-DD (các chu kỳ còn lại). */
  dueDate: string
  payJar: string
  essential: boolean
}

export const emptyForm = (): ObligationForm => ({
  kind: 'rent',
  name: '',
  amountMode: 'fixed',
  amount: '',
  min: '',
  max: '',
  cycle: 'monthly',
  dueDay: '',
  dueDate: '',
  payJar: '',
  essential: true,
})

export function formFromObligation(o: Obligation): ObligationForm {
  const range = o.amount_min_vnd !== undefined && o.amount_max_vnd !== undefined
  return {
    id: o.id,
    kind: (['rent', 'bill', 'subscription', 'loan'] as const).find((k) => k === o.kind) ?? 'bill',
    name: o.name,
    amountMode: range ? 'range' : 'fixed',
    amount: String(o.amount_vnd),
    min: range ? String(o.amount_min_vnd) : '',
    max: range ? String(o.amount_max_vnd) : '',
    cycle: o.cycle,
    dueDay: o.due_day ? String(o.due_day) : '',
    dueDate: o.due_date,
    payJar: o.pay_jar ?? '',
    essential: o.is_essential,
  }
}

/** Lỗi nhập theo trường (tiếng Việt); rỗng là hợp lệ. Server vẫn kiểm lại. */
export function validateForm(f: ObligationForm): Partial<Record<'name' | 'amount' | 'min' | 'max' | 'dueDay' | 'dueDate', string>> {
  const e: Partial<Record<'name' | 'amount' | 'min' | 'max' | 'dueDay' | 'dueDate', string>> = {}
  if (!f.name.trim()) e.name = 'Nhập tên khoản'
  if (f.amountMode === 'fixed') {
    if (!f.amount || Number(f.amount) < 1) e.amount = 'Nhập số tiền lớn hơn 0'
  } else {
    if (!f.min || Number(f.min) < 1) e.min = 'Nhập số tiền thấp nhất'
    if (!f.max || Number(f.max) < 1) e.max = 'Nhập số tiền cao nhất'
    if (f.min && f.max && Number(f.max) < Number(f.min)) e.max = 'Số cao nhất phải không nhỏ hơn số thấp nhất'
  }
  if (f.cycle === 'monthly') {
    const d = Number(f.dueDay)
    if (!Number.isInteger(d) || d < 1 || d > 31) e.dueDay = 'Nhập ngày từ 1 đến 31'
  } else if (!/^\d{4}-\d{2}-\d{2}$/.test(f.dueDate)) e.dueDate = 'Chọn ngày đến hạn'
  return e
}

/**
 * Tham số `update_profile` cho một nghĩa vụ (thêm hoặc sửa). Chỉ gửi những gì người dùng đã nhập; server điền mặc định
 * (phí, hũ trả, ngày đến hạn đầu tiên) và chuẩn hóa. Khoản khai theo khoảng thì server tính số tiền kỳ vọng.
 */
export function obligationUpsertParams(f: ObligationForm): ToolParams {
  const ob: Record<string, unknown> = {
    op: 'upsert',
    kind: f.kind,
    name: f.name.trim(),
    cycle: f.cycle,
    is_essential: f.essential,
  }
  if (f.id) ob.obligation_id = f.id
  if (f.amountMode === 'fixed') ob.amount_vnd = Number(f.amount)
  else {
    ob.amount_min_vnd = Number(f.min)
    ob.amount_max_vnd = Number(f.max)
  }
  if (f.cycle === 'monthly') ob.due_day = Number(f.dueDay)
  else ob.due_date = f.dueDate
  if (f.payJar) ob.pay_jar = f.payJar
  return { obligation: ob }
}

export const obligationDeleteParams = (id: string): ToolParams => ({ obligation: { op: 'delete', obligation_id: id } })
