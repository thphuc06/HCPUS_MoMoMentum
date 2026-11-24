import { useInRouterContext, useNavigate } from 'react-router'
import { Button } from '@/components/ui/button'
import { useChatLauncher } from '@/chat/launcher'
import type { BehaviorInsightBlock, CitationBlock } from '@/contracts/blocks'
import { BehaviorInsightCard } from '@/features/behavior/BehaviorInsightCard'
import { PROFILE_BEHAVIOR_PATH } from '@/features/behavior/format'
import { Citation } from '@/features/citation/Citation'
import type { BlockViewProps } from './views'

// Hai khối của phase 5 (F7, trích dẫn biểu phí): behavior_insight, citation.

function OpenProfileButton({ label }: { label: string }) {
  const navigate = useNavigate()
  const launcher = useChatLauncher()
  return (
    <Button type="button" size="sm" variant="soft" onClick={() => {
      launcher.close()
      navigate(PROFILE_BEHAVIOR_PATH)
    }}>
      {label}
    </Button>
  )
}

/**
 * Trong chat chỉ xem: việc cần làm có hành động thì thực hiện ở màn Hồ sơ (luồng xác nhận của màn hình), không ghi gì từ khối.
 */
export function BehaviorInsightView({ block }: BlockViewProps<BehaviorInsightBlock>) {
  const inRouter = useInRouterContext()
  const d = block.data
  return (
    <BehaviorInsightCard
      insight={d.insight}
      nextStep={d.next_step}
      footer={inRouter ? <OpenProfileButton label={d.next_step.action ? 'Thực hiện ở Hồ sơ' : 'Xem các nhận xét ở Hồ sơ'} /> : undefined}
    />
  )
}

export function CitationView({ block }: BlockViewProps<CitationBlock>) {
  return <Citation data={block.data} />
}
