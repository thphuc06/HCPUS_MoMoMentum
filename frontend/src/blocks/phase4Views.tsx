import type { ResilienceScoreBlock, ReviewListBlock, RoadmapBlock, RoadmapDiffBlock, StressResultBlock } from '@/contracts/blocks'
import { useInRouterContext } from 'react-router'
import { ResilienceScore } from '@/features/resilience/ResilienceScore'
import { StressResult } from '@/features/resilience/StressResult'
import { ReviewList } from '@/features/review/ReviewList'
import { Roadmap } from '@/features/roadmap/Roadmap'
import { RoadmapChatLinks } from '@/features/roadmap/RoadmapChatLinks'
import { RoadmapDiff } from '@/features/roadmap/RoadmapDiff'
import type { BlockViewProps } from './views'

export function ResilienceScoreView({ block }: BlockViewProps<ResilienceScoreBlock>) {
  return <ResilienceScore data={block.data} />
}

export function StressResultView({ block }: BlockViewProps<StressResultBlock>) {
  return <StressResult data={block.data} />
}

/** Trong chat (có router): thêm lối sang trang Lộ trình để người dùng thấy các phiên bản khác và so với bản đang dùng. */
export function RoadmapView({ block }: BlockViewProps<RoadmapBlock>) {
  const inRouter = useInRouterContext()
  return <Roadmap data={block.data} footer={inRouter ? <RoadmapChatLinks data={block.data} /> : undefined} />
}

export function RoadmapDiffView({ block }: BlockViewProps<RoadmapDiffBlock>) {
  return <RoadmapDiff data={block.data} />
}

export function ReviewListView({ block }: BlockViewProps<ReviewListBlock>) {
  return <ReviewList data={block.data} />
}
