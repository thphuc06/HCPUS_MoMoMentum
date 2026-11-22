// "Để sau" và "Ít nhắc loại này" của thẻ chủ động: phase 2 chỉ lưu phía giao diện (quyết định hợp đồng số 15), tới khi có
// bảng `nudges` ở server (F7). Đây là tùy chọn hiển thị, không phải dữ liệu tài chính; localStorage hỏng thì bỏ qua.

const SNOOZE_KEY = 'yofina.nudge.snoozed'
const MUTE_KEY = 'yofina.nudge.muted'

function readList(key: string): string[] {
  try {
    const raw = localStorage.getItem(key)
    const v = raw ? JSON.parse(raw) : []
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

function writeList(key: string, list: string[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(list.slice(-50)))
  } catch {
    /* trình duyệt chặn lưu trữ: chỉ mất khả năng nhớ */
  }
}

/** Khóa ổn định của một việc (id khối đổi theo từng lần gọi nên không dùng): loại việc + hũ. */
export const nudgeKey = (kind: string, jarCode?: string): string => `${kind}:${jarCode ?? ''}`

export const mutedKinds = (): string[] => readList(MUTE_KEY)

/** "Để sau": ẩn việc này trong ngày mô phỏng `appDate`; sang ngày mới thì hiện lại nếu còn đúng. */
export function snoozeCard(key: string, appDate: string): void {
  writeList(SNOOZE_KEY, [...readList(SNOOZE_KEY).filter((x) => x !== `${key}|${appDate}`), `${key}|${appDate}`])
}

/** "Ít nhắc loại này": ẩn mọi thẻ cùng loại (kind) cho tới khi bật lại ở Hồ sơ. */
export function muteKind(kind: string): void {
  writeList(MUTE_KEY, [...mutedKinds().filter((x) => x !== kind), kind])
}

export function unmuteAll(): void {
  writeList(MUTE_KEY, [])
  writeList(SNOOZE_KEY, [])
}

export function isCardHidden(key: string, kind: string, appDate: string): boolean {
  return mutedKinds().includes(kind) || readList(SNOOZE_KEY).includes(`${key}|${appDate}`)
}
