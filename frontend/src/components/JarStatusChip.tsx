import { StatusChip } from './StatusChip'
import { jarStatusChip } from '@/lib/jar'
import type { JarFull } from '@/api/schemas'

/**
 * Chip trạng thái của hũ theo dự báo mới nhất: đủ / sát / hụt (biểu tượng + chữ + màu). Hũ chưa có dự báo thì nói thật
 * "Chưa có dự báo" (không đoán); hũ chi tiêu hoặc nghĩa vụ đã hết tiền mà chưa có dự báo vẫn báo "Đã hết tiền". Hũ để dành
 * (`kind` saving) 0 ₫ là hũ chưa nạp tiền, không phải hũ đã tiêu hết (#39), nên không mang chip đó; số dư 0 ₫ đã hiện cạnh chip.
 */
export function JarStatusChip({ jar, className }: { jar: Pick<JarFull, 'kind' | 'status' | 'runout_date' | 'balance_vnd'>; className?: string }) {
  if (jar.status) {
    const c = jarStatusChip(jar.status, jar.runout_date, jar.balance_vnd <= 0)
    return (
      <StatusChip kind={c.kind} className={className}>
        {c.label}
      </StatusChip>
    )
  }
  if (jar.balance_vnd <= 0 && jar.kind !== 'saving') return <StatusChip kind="bad" className={className}>Đã hết tiền</StatusChip>
  return <StatusChip kind="info" className={className}>Chưa có dự báo</StatusChip>
}
