import type { JarFull, JarPurpose, JarTemplate, ToolParams } from '@/api/schemas'

export type SinkingItemState = { name: string; amount_vnd: number; needed_date: string }

export type JarRowState = {
  /** Có `code` là hũ đã có (sửa); không có là hũ mới (server sinh mã từ tên). */
  code?: string
  name: string
  color_key: string
  icon_key: string
  kind: 'spending' | 'saving' | 'obligation'
  /** Tỷ lệ chia lương, chuỗi người dùng gõ ("30", "12,5"). */
  percent: string
  purpose?: JarPurpose
  goal_vnd?: number
  goal_date?: string
  /** Khoản của Quỹ dồn (tên, số tiền, ngày cần): giữ nguyên văn để lưu lại không làm mất khoản đã cam kết. */
  sinking_items?: SinkingItemState[]
  /** Số dư hiện có (chỉ để biết hũ còn tiền thì chưa bỏ được). */
  balance_vnd: number
}

export function rowsFromJars(jars: readonly JarFull[]): JarRowState[] {
  return jars
    .filter((j) => j.kind !== 'system')
    .map((j) => ({
      code: j.code,
      name: j.name,
      color_key: j.color_key,
      icon_key: j.icon_key,
      kind: j.kind === 'system' ? 'spending' : j.kind,
      percent: String(j.split_percent),
      purpose: j.purpose,
      goal_vnd: j.goal_vnd,
      goal_date: j.goal_date,
      sinking_items: j.sinking_items,
      balance_vnd: j.balance_vnd,
    }))
}

const KINDS = ['spending', 'saving', 'obligation'] as const
const PURPOSES = ['buffer', 'sinking', 'goal', 'long_term'] as const

/**
 * Hàng của trình sửa từ tham số `save_jars` do server dựng (đề xuất theo số đã khai, "Sửa số"): giữ đúng mã, tỷ lệ, mục đích
 * và khoản Quỹ dồn server đã tính; số dư lấy từ hũ hiện có (hũ mới là 0).
 */
export function rowsFromParams(params: readonly Record<string, unknown>[], jars: readonly JarFull[]): JarRowState[] {
  const balance = new Map(jars.map((j) => [j.code, j.balance_vnd]))
  return params.map((p) => {
    const kind = KINDS.find((k) => k === p.kind) ?? 'spending'
    const purpose = PURPOSES.find((k) => k === p.purpose)
    const code = typeof p.code === 'string' ? p.code : undefined
    return {
      code,
      name: String(p.name ?? ''),
      color_key: String(p.color_key ?? ''),
      icon_key: String(p.icon_key ?? ''),
      kind,
      percent: String(p.split_percent ?? '0'),
      purpose,
      goal_vnd: typeof p.goal_vnd === 'number' ? p.goal_vnd : undefined,
      goal_date: typeof p.goal_date === 'string' ? p.goal_date : undefined,
      sinking_items: Array.isArray(p.sinking_items) ? (p.sinking_items as SinkingItemState[]) : undefined,
      balance_vnd: (code && balance.get(code)) || 0,
    }
  })
}

export function rowFromTemplate(t: JarTemplate): JarRowState {
  return { name: t.name, color_key: t.color_key, icon_key: t.icon_key, kind: t.kind, purpose: t.purpose, percent: '0', balance_vnd: 0 }
}

/** Mục đích có ô số tiền và ngày (Quỹ dồn, Mục tiêu, Tích lũy dài hạn; hũ cũ chưa đặt mục đích giữ như trước). */
const hasTarget = (purpose: JarPurpose | undefined): boolean => purpose !== 'buffer'

/**
 * Đổi mục đích của một hàng: bỏ trường không còn hợp với mục đích mới để không gửi dữ liệu ẩn lên server (server từ chối
 * `sinking_items` ngoài Quỹ dồn). Hết là Quỹ dồn thì bỏ khoản của Quỹ dồn; thành Dự phòng thì bỏ số tiền và ngày (ô đã ẩn).
 */
export function withPurpose(row: JarRowState, purpose: JarPurpose): JarRowState {
  if (purpose === row.purpose) return row
  const next: JarRowState = { ...row, purpose }
  if (purpose !== 'sinking') delete next.sinking_items
  if (!hasTarget(purpose)) {
    delete next.goal_vnd
    delete next.goal_date
  }
  return next
}

/** "12,5" -> 12.5; chuỗi hỏng -> NaN. */
export function parsePercent(s: string): number {
  const v = Number(s.trim().replace(',', '.'))
  return s.trim() === '' || !Number.isFinite(v) ? Number.NaN : v
}

/** Tổng tỷ lệ tính theo phần trăm của phần trăm (số nguyên) để tránh sai số số thực; NaN nếu có ô hỏng. */
export function totalHundredths(rows: readonly JarRowState[]): number {
  let t = 0
  for (const r of rows) {
    const v = parsePercent(r.percent)
    if (Number.isNaN(v) || v < 0 || v > 100) return Number.NaN
    t += Math.round(v * 100)
  }
  return t
}

export const isTotalOk = (rows: readonly JarRowState[]): boolean => totalHundredths(rows) === 10000

/** So sánh với danh sách hũ hiện có: đổi thứ tự, tên, tỷ lệ, thêm hoặc bớt đều là có đổi. */
export function isChanged(rows: readonly JarRowState[], original: readonly JarFull[]): boolean {
  const orig = rowsFromJars(original)
  if (rows.length !== orig.length) return true
  return rows.some((r, i) => {
    const o = orig[i]!
    return r.code !== o.code || r.name.trim() !== o.name ||
      r.purpose !== o.purpose || r.goal_vnd !== o.goal_vnd || r.goal_date !== o.goal_date ||
      JSON.stringify(r.sinking_items ?? []) !== JSON.stringify(o.sinking_items ?? []) ||
      Math.round(parsePercent(r.percent) * 100) !== Math.round(parsePercent(o.percent) * 100)
  })
}

/** Tham số `save_jars`: thay cả danh sách hũ người dùng theo thứ tự hiển thị (giữ mục tiêu và khoản Quỹ dồn đã có). */
export function saveJarsParams(rows: readonly JarRowState[]): ToolParams {
  return {
    jars: rows.map((r) => {
      const j: Record<string, unknown> = {
        name: r.name.trim(),
        color_key: r.color_key,
        icon_key: r.icon_key,
        kind: r.kind,
        split_percent: Math.round(parsePercent(r.percent) * 100) / 100,
      }
      if (r.code) j.code = r.code
      if (r.purpose) j.purpose = r.purpose
      if (hasTarget(r.purpose) && r.goal_vnd) j.goal_vnd = r.goal_vnd
      if (hasTarget(r.purpose) && r.goal_date) j.goal_date = r.goal_date
      if (r.purpose === 'sinking' && r.sinking_items && r.sinking_items.length > 0) j.sinking_items = r.sinking_items
      return j
    }),
  }
}
