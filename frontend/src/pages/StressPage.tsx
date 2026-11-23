import { useParams } from 'react-router'
import { StressResultScreen } from '@/features/resilience/StressResultScreen'

export function StressPage() {
  const { shockId = '' } = useParams()
  return <StressResultScreen key={shockId} shockId={shockId} />
}
