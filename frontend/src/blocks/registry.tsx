import { Component, type ComponentType, type ReactNode } from 'react'
import { Info } from 'lucide-react'
import type { z } from 'zod'
import { BLOCK_TYPES, blockSchemas, type BlockType } from '@/contracts/blocks'
import type { BlockUi } from '@/chat/session'
import { ConfirmView, JarSummaryView, NoticeView, ReceiptView, type BlockViewProps } from './views'
import { ConfirmActionView, ForecastTimelineView, ProactiveCardView, ReceiptActionView } from './walletViews'
import { CoverageChangeView, IngestReviewView } from './ingestViews'

// Registry `type -> { schema Zod, Component }`. Thêm một loại khối: schema ở contracts/ (sinh Zod), một dòng ở đây.
// Parse TỪNG khối riêng; type lạ hoặc sai schema hiện fallback_text; error boundary bọc từng khối.

type Entry = {
  render: (raw: unknown, props: { blockId: string; ui?: BlockUi }) => ReactNode
  parse: (raw: unknown) => boolean
}

function defineBlock<S extends z.ZodType>(schema: S, View: ComponentType<BlockViewProps<z.infer<S>>>): Entry {
  return {
    parse: (raw) => schema.safeParse(raw).success,
    render: (raw, props) => {
      const parsed = schema.safeParse(raw)
      if (!parsed.success) return null
      return <View block={parsed.data} blockId={props.blockId} ui={props.ui} />
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
  coverage_change: defineBlock(blockSchemas.coverage_change, CoverageChangeView),
  ingest_review: defineBlock(blockSchemas.ingest_review, IngestReviewView),
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

export function BlockRenderer({ raw, blockId, ui }: { raw: unknown; blockId: string; ui?: BlockUi }) {
  const type = raw && typeof raw === 'object' ? (raw as { type?: unknown }).type : undefined
  if (!isBlockType(type)) return <FallbackBlock raw={raw} reason="unknown_type" />
  const entry = registry[type]
  if (!entry.parse(raw)) {
    const v = (raw as { v?: unknown }).v
    console.warn('[block] sai schema', type)
    return <FallbackBlock raw={raw} reason={typeof v === 'number' && v > 1 ? 'newer_version' : 'invalid_schema'} />
  }
  return <BlockBoundary raw={raw}>{entry.render(raw, { blockId, ui })}</BlockBoundary>
}
