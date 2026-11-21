import { createContext, useContext } from 'react'
import type { Config } from '@/lib/config'

export const ConfigContext = createContext<Config | null>(null)

export function useConfig(): Config {
  const c = useContext(ConfigContext)
  if (!c) throw new Error('useConfig phải nằm trong ConfigContext.Provider')
  return c
}
