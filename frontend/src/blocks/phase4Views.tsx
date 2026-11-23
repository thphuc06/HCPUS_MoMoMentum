import type { ResilienceScoreBlock, ReviewListBlock, RoadmapBlock, RoadmapDiffBlock, StressResultBlock } from '@/contracts/blocks'
import { ResilienceScore } from '@/features/resilience/ResilienceScore'
import { StressResult } from '@/features/resilience/StressResult'
import { ReviewList } from '@/features/review/ReviewList'
import { Roadmap } from '@/features/roadmap/Roadmap'
import { RoadmapDiff } from '@/features/roadmap/RoadmapDiff'
import type { BlockViewProps } from './views'

export function ResilienceScoreView({ block }: BlockViewProps<ResilienceScoreBlock>) {
  return <ResilienceScore data={block.data} />
}

export function StressResultView({ block }: BlockViewProps<StressResultBlock>) {
  return <StressResult data={block.data} />
}

export function RoadmapView({ block }: BlockViewProps<RoadmapBlock>) {
  return <Roadmap data={block.data} />
}

export function RoadmapDiffView({ block }: BlockViewProps<RoadmapDiffBlock>) {
  return <RoadmapDiff data={block.data} />
}

export function ReviewListView({ block }: BlockViewProps<ReviewListBlock>) {
  return <ReviewList data={block.data} />
}
