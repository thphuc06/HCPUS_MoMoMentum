import { useApiResource } from '@/api/resource'

export function useRoadmapVersions() {
  return useApiResource((api) => api.listRoadmapVersions(), [])
}
