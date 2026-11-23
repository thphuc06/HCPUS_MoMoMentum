import { useWriteFlow } from '@/api/useWrite'

export type RememberJar = 'once' | 'always'

export function useAssignJar() {
  const { submit, ...flow } = useWriteFlow()
  return {
    ...flow,
    assign: (transactionId: string, jar: string, remember: RememberJar) =>
      submit('assign_jar', { transaction_id: transactionId, jar, remember }),
  }
}
