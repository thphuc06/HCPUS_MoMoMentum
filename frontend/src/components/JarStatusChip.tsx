import { StatusChip } from './StatusChip'
import { jarStatusChip, NEVER_FUNDED_CHIP } from '@/lib/jar'
import type { JarFull } from '@/api/schemas'

/**
 * Chip trạng thái của hũ theo dự báo mới nhất: đủ / sát / hụt (biểu tượng + chữ + màu). Hũ chưa có dự báo thì nói thật
 * "Chưa có dự báo" (không đoán); hũ chi tiêu hoặc nghĩa vụ đã hết tiền mà chưa có dự báo vẫn báo "Đã hết tiền". Hũ để dành
 * (`kind` saving) 0 ₫ là hũ chưa nạp tiền, không phải hũ đã tiêu hết (#39), nên không mang chip đó; số dư 0 ₫ đã hiện cạnh chip.
 * Hũ 0 ₫ mà server cho biết chưa từng có dòng sổ cái nào (`has_activity: false`, tài khoản mới chưa có lương) nói "Chưa có tiền"
 * thay cho "Đang hết tiền" / "Đã hết tiền": quyết theo dữ liệu của server, không theo mã hay loại hũ.
 */
export function JarStatusChip({ jar, className }: { jar: Pick<JarFull, 'kind' | 'status' | 'runout_date' | 'balance_vnd' | 'has_activity'>; className?: string }) {
  const empty = jar.balance_vnd <= 0
  const neverFunded = empty && jar.has_activity === false
  if (jar.status) {
    const c = jarStatusChip(jar.status, jar.runout_date, empty, neverFunded)
    return (
      <StatusChip kind={c.kind} className={className}>
        {c.label}
      </StatusChip>
    )
  }
  if (neverFunded) return <StatusChip kind={NEVER_FUNDED_CHIP.kind} className={className}>{NEVER_FUNDED_CHIP.label}</StatusChip>
  if (empty && jar.kind !== 'saving') return <StatusChip kind="bad" className={className}>Đã hết tiền</StatusChip>
  return <StatusChip kind="info" className={className}>Chưa có dự báo</StatusChip>
}
