// Bản ghi bộ nhớ vừa xóa trên màn "Bộ nhớ của tôi". AgentCore Memory xóa có độ trễ: ngay sau `DELETE /memory` (200, failed 0) một lần
// `GET /memory` vẫn liệt kê bản ghi cũ, khoảng một phút sau mới hết (đo Runtime v25, file phase 5 mục "Đo sau đợt sửa kiểm toán và bộ
// nhớ"). Màn ẩn bản ghi ngay khi bấm xóa (optimistic) và không hiện lại chúng trong `MEMORY_DELETE_GRACE_MS` dù API còn trả; API báo
// lỗi thì người gọi bỏ ẩn. Sống ở mức module để rời Hồ sơ rồi quay lại vẫn nhớ; id bản ghi là duy nhất nên không cần tách theo tài khoản.

/** Thời gian ẩn bản ghi đã xóa (gấp đôi độ trễ đo được). */
export const MEMORY_DELETE_GRACE_MS = 120_000

const hiddenIds = new Map<string, number>() // record_id -> hết ẩn lúc (ms)
let hiddenBefore: { cutoff: number; until: number } | null = null // "Xóa hết": mọi bản ghi tạo trước `cutoff`

/** Ẩn các bản ghi theo id trong `MEMORY_DELETE_GRACE_MS`. */
export function hideMemoryRecords(ids: Iterable<string>, now = Date.now()): void {
  for (const id of ids) hiddenIds.set(id, now + MEMORY_DELETE_GRACE_MS)
}

/** Bỏ ẩn (API báo lỗi: bản ghi chưa bị xóa). */
export function unhideMemoryRecords(ids: Iterable<string>): void {
  for (const id of ids) hiddenIds.delete(id)
}

/** "Xóa hết": ẩn cả bản ghi chưa tải (trang sau) nếu chúng được tạo trước lúc bấm xóa. */
export function hideMemoryCreatedBefore(cutoff: number, now = Date.now()): void {
  hiddenBefore = { cutoff, until: now + MEMORY_DELETE_GRACE_MS }
}

export function unhideMemoryCreatedBefore(): void {
  hiddenBefore = null
}

export function isMemoryRecordHidden(r: { record_id: string; created_at: string }, now = Date.now()): boolean {
  const until = hiddenIds.get(r.record_id)
  if (until !== undefined) {
    if (now < until) return true
    hiddenIds.delete(r.record_id)
  }
  if (hiddenBefore) {
    if (now >= hiddenBefore.until) hiddenBefore = null
    else if (Date.parse(r.created_at) < hiddenBefore.cutoff) return true
  }
  return false
}

/** Chỉ cho test: xóa trạng thái giữa các ca. */
export function resetHiddenMemory(): void {
  hiddenIds.clear()
  hiddenBefore = null
}
