import type { OverviewResponse } from '@/api/schemas'

/**
 * Khóa `description` của mục ngữ cảnh AG-UI mang danh sách hũ của ví (hợp đồng với agent: `router.WALLET_CONTEXT`). Mục này tùy
 * chọn: thiếu hoặc sai thì agent tự đọc ví như trước.
 */
export const WALLET_CONTEXT = 'yofina.wallet'

/** Một mục `context` của `RunAgentInput` (AG-UI). */
export type AgentContext = { description: string; value: string }

/**
 * Danh sách hũ người dùng (mã, tên, kind, purpose) và ngày mô phỏng, lấy từ GET /overview đã tải sẵn, gửi kèm mỗi lượt chat để router
 * chọn hũ chi mà agent không phải đọc ví trước router (#39). Không có số dư hay số tiền nào: agent tính mọi thứ bằng tool phía server.
 * Không gửi khi dữ liệu chưa chắc đúng (đang tải, đang tải lại sau một lần ghi, lỗi): agent tự đọc ví.
 */
export function walletContext(
  overview: { status: string; refreshing?: boolean; data: OverviewResponse | null } | null | undefined,
): AgentContext | null {
  if (!overview || overview.status !== 'ready' || overview.refreshing || !overview.data) return null
  const jars = overview.data.jars
    .filter((j) => j.kind !== 'system' && !j.system_role)
    .map((j) => ({ code: j.code, name: j.name, kind: j.kind, ...(j.purpose ? { purpose: j.purpose } : {}) }))
  if (jars.length === 0) return null
  return { description: WALLET_CONTEXT, value: JSON.stringify({ app_date: overview.data.app_date, jars }) }
}
