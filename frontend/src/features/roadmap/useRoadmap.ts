import { useCallback, useState } from 'react'
import { useDataVersion } from '@/api/ApiProvider'
import { useApiResource } from '@/api/resource'
import type { RoadmapResponse } from '@/api/roadmapSchemas'

export function useRoadmap() {
  const dataVersion = useDataVersion()
  const resource = useApiResource((api) => api.getRoadmap(), [])
  const { reload: reloadResource } = resource
  const [updated, setUpdated] = useState<{ block: RoadmapResponse; dataVersion: number } | null>(null)
  const replace = (block: RoadmapResponse) => setUpdated({ block, dataVersion })
  const reload = useCallback(() => {
    setUpdated(null)
    return reloadResource()
  }, [reloadResource])

  if (updated?.dataVersion === dataVersion) {
    return { status: 'ready', data: updated.block, error: null, refreshing: false, replace, reload } as const
  }
  return { ...resource, replace, reload }
}
