import type { JarFull, JarPurpose, JarTemplate, ToolParams } from '@/api/schemas'

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
      balance_vnd: j.balance_vnd,
    }))
}

export function rowFromTemplate(t: JarTemplate): JarRowState {
  return { name: t.name, color_key: t.color_key, icon_key: t.icon_key, kind: t.kind, purpose: t.purpose, percent: '0', balance_vnd: 0 }
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
      Math.round(parsePercent(r.percent) * 100) !== Math.round(parsePercent(o.percent) * 100)
  })
}

/** Tham số `save_jars`: thay cả danh sách hũ người dùng theo thứ tự hiển thị (giữ mục tiêu đã có). */
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
      if (r.goal_vnd) j.goal_vnd = r.goal_vnd
      if (r.goal_date) j.goal_date = r.goal_date
      return j
    }),
  }
}
