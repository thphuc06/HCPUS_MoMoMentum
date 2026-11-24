import { Component, type ComponentType, type ReactNode } from 'react'
import { Info } from 'lucide-react'
import type { z } from 'zod'
import { BLOCK_TYPES, blockSchemas, type BlockType } from '@/contracts/blocks'
import type { BlockUi } from '@/chat/session'
import { ConfirmView, JarSummaryView, NoticeView, ReceiptView, type BlockViewProps } from './views'
import { AffordabilityCardView, ClarifyView, ExplainView, ObligationImpactView, OptionsView, SuggestionsView } from './phase3Views'
import { ConfirmActionView, ForecastTimelineView, ProactiveCardView, ReceiptActionView } from './walletViews'
import { CoverageChangeView, IngestReviewView } from './ingestViews'
import { ResilienceScoreView, ReviewListView, RoadmapDiffView, RoadmapView, StressResultView } from './phase4Views'
import { BehaviorInsightView, CitationView } from './phase5Views'

// Registry `type -> { schema Zod, Component }`. Thêm một loại khối: schema ở contracts/ (sinh Zod), một dòng ở đây.
// Parse TỪNG khối riêng; type lạ hoặc sai schema hiện fallback_text; error boundary bọc từng khối.

type Entry = {
  render: (raw: unknown, props: { blockId: string; ui?: BlockUi; doneAt?: number; stale?: boolean }) => ReactNode
  parse: (raw: unknown) => boolean
}

function defineBlock<S extends z.ZodType>(schema: S, View: ComponentType<BlockViewProps<z.infer<S>>>): Entry {
  return {
    parse: (raw) => schema.safeParse(raw).success,
    render: (raw, props) => {
      const parsed = schema.safeParse(raw)
      if (!parsed.success) return null
      return <View block={parsed.data} blockId={props.blockId} ui={props.ui} doneAt={props.doneAt} stale={props.stale} />
    },
  }
}

export const registry: Record<BlockType, Entry> = {
  jar_summary: defineBlock(blockSchemas.jar_summary, JarSummaryView),
  confirm: defineBlock(blockSchemas.confirm, ConfirmView),
  receipt: defineBlock(blockSchemas.receipt, ReceiptView),
  notice: defineBlock(blockSchemas.notice, NoticeView),
  forecast_timeline: defineBlock(blockSchemas.forecast_timeline, ForecastTimelineView),
  proactive_card: defineBlock(blockSchemas.proactive_card, ProactiveCardView),
  confirm_action: defineBlock(blockSchemas.confirm_action, ConfirmActionView),
  receipt_action: defineBlock(blockSchemas.receipt_action, ReceiptActionView),
  affordability_card: defineBlock(blockSchemas.affordability_card, AffordabilityCardView),
  obligation_impact: defineBlock(blockSchemas.obligation_impact, ObligationImpactView),
  options: defineBlock(blockSchemas.options, OptionsView),
  explain: defineBlock(blockSchemas.explain, ExplainView),
  clarify: defineBlock(blockSchemas.clarify, ClarifyView),
  suggestions: defineBlock(blockSchemas.suggestions, SuggestionsView),
  coverage_change: defineBlock(blockSchemas.coverage_change, CoverageChangeView),
  ingest_review: defineBlock(blockSchemas.ingest_review, IngestReviewView),
  resilience_score: defineBlock(blockSchemas.resilience_score, ResilienceScoreView),
  stress_result: defineBlock(blockSchemas.stress_result, StressResultView),
  roadmap: defineBlock(blockSchemas.roadmap, RoadmapView),
  roadmap_diff: defineBlock(blockSchemas.roadmap_diff, RoadmapDiffView),
  review_list: defineBlock(blockSchemas.review_list, ReviewListView),
  behavior_insight: defineBlock(blockSchemas.behavior_insight, BehaviorInsightView),
  citation: defineBlock(blockSchemas.citation, CitationView),
}

export const REGISTERED_TYPES = BLOCK_TYPES

function isBlockType(t: unknown): t is BlockType {
  return typeof t === 'string' && Object.prototype.hasOwnProperty.call(registry, t)
}

export type FallbackReason = 'unknown_type' | 'invalid_schema' | 'newer_version' | 'render_error'

const HINTS: Record<FallbackReason, string> = {
  unknown_type: 'Cập nhật ứng dụng để xem đầy đủ.',
  newer_version: 'Cập nhật ứng dụng để xem đầy đủ.',
  invalid_schema: 'Không hiển thị được khối này.',
  render_error: 'Không hiển thị được khối này.',
}

export function FallbackBlock({ raw, reason }: { raw: unknown; reason: FallbackReason }) {
  const text =
    raw && typeof raw === 'object' && typeof (raw as { fallback_text?: unknown }).fallback_text === 'string' && (raw as { fallback_text: string }).fallback_text
      ? (raw as { fallback_text: string }).fallback_text
      : 'Mình chưa hiển thị được phần này.'
  return (
    <div
      data-block="fallback"
      data-reason={reason}
      className="flex w-full items-start gap-2 rounded-card border border-dashed border-line bg-surface-2 px-4 py-3 text-small text-ink-2"
    >
      <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>
        <p className="text-ink">{text}</p>
        <p className="mt-0.5 text-note">{HINTS[reason]}</p>
      </div>
    </div>
  )
}

class BlockBoundary extends Component<{ raw: unknown; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch(err: unknown) {
    console.warn('[block] lỗi khi vẽ', err)
  }
  render() {
    return this.state.failed ? <FallbackBlock raw={this.props.raw} reason="render_error" /> : this.props.children
  }
}

export function BlockRenderer({ raw, blockId, ui, doneAt, stale }: { raw: unknown; blockId: string; ui?: BlockUi; doneAt?: number; stale?: boolean }) {
  const type = raw && typeof raw === 'object' ? (raw as { type?: unknown }).type : undefined
  if (!isBlockType(type)) return <FallbackBlock raw={raw} reason="unknown_type" />
  const entry = registry[type]
  if (!entry.parse(raw)) {
    const v = (raw as { v?: unknown }).v
    console.warn('[block] sai schema', type)
    return <FallbackBlock raw={raw} reason={typeof v === 'number' && v > 1 ? 'newer_version' : 'invalid_schema'} />
  }
  return <BlockBoundary raw={raw}>{entry.render(raw, { blockId, ui, doneAt, stale })}</BlockBoundary>
}
