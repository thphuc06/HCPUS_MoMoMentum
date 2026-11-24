import type { JarFull, Obligation } from '@/api/schemas'

/** Khoản Trả sau đang hoạt động đến hạn gần nhất (theo `due_date` server trả), hoặc undefined. */
export function nearestBnpl(obligations: readonly Obligation[]): Obligation | undefined {
  return obligations
    .filter((o) => o.kind === 'bnpl' && o.status === 'active')
    .reduce<Obligation | undefined>((best, o) => (!best || o.due_date < best.due_date ? o : best), undefined)
}

/** Hũ dùng để trả khoản: hũ ghi trong `pay_jar`, không có thì hũ loại nghĩa vụ (nếu chỉ có một). */
export function payJarFor(o: Obligation | undefined, jars: readonly JarFull[]): JarFull | undefined {
  if (!o) return undefined
  if (o.pay_jar) return jars.find((j) => j.code === o.pay_jar)
  const obligationJars = jars.filter((j) => j.kind === 'obligation')
  return obligationJars.length === 1 ? obligationJars[0] : undefined
}
