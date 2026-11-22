import { useMemo } from 'react'
import { useOverview } from '@/api/OverviewProvider'
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
