import { useApiResource } from '@/api/resource'

export function useResilience() {
  return useApiResource((api) => api.getResilience(), [])
}

export function useShocks() {
  return useApiResource((api) => api.getShocks(), [])
}

export function useStress(shockId: string) {
  return useApiResource((api) => api.runStress({ shock_id: shockId }), [shockId])
}
