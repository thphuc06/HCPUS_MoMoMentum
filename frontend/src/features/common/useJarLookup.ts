import { useMemo } from 'react'
import { useOptionalOverview, useOverview } from '@/api/OverviewProvider'
import type { JarFull } from '@/api/schemas'

/** Tra hũ theo mã (hũ của người dùng và hai hũ hệ thống) từ Tổng quan đang nạp; rỗng khi chưa tải xong. */
export function useJarLookup(): Map<string, JarFull> {
  const ov = useOverview()
  return useMemo(() => {
    const m = new Map<string, JarFull>()
    for (const j of [...(ov.data?.jars ?? []), ...(ov.data?.system_jars ?? [])]) m.set(j.code, j)
    return m
  }, [ov.data])
}

/** Mã hũ -> tên hũ của chính người dùng (Tổng quan đang nạp), cộng thêm tên có sẵn trong dữ liệu khối (`known`, ưu tiên).
 *  Dùng được ở cả màn hình và khối chat; ngoài <OverviewProvider> hoặc khi Tổng quan chưa tải chỉ còn tên trong `known`. */
export function useJarNames(known?: Iterable<readonly [string, string]>): Map<string, string> {
  const ov = useOptionalOverview()
  const data = ov?.data
  return useMemo(() => {
    const m = new Map<string, string>()
    for (const j of [...(data?.jars ?? []), ...(data?.system_jars ?? [])]) m.set(j.code, j.name)
    for (const [code, name] of known ?? []) m.set(code, name)
    return m
  }, [data, known])
}
