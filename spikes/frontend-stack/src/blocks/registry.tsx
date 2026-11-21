import { Component, type ComponentType, type ReactNode } from 'react'
import { Info } from 'lucide-react'
import { blockSchemas, type BlockType } from './schemas'
import { AffordabilityCardView, ConfirmView, ForecastTimelineView, JarSummaryView } from './components'

// registry: type -> { schema, Component }. Thêm khối mới = thêm một dòng ở đây và một schema.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyComp = ComponentType<{ block: any }>
const registry: Record<BlockType, { schema: (typeof blockSchemas)[BlockType]; Component: AnyComp }> = {
  forecast_timeline: { schema: blockSchemas.forecast_timeline, Component: ForecastTimelineView },
  jar_summary: { schema: blockSchemas.jar_summary, Component: JarSummaryView },
  affordability_card: { schema: blockSchemas.affordability_card, Component: AffordabilityCardView },
  confirm: { schema: blockSchemas.confirm, Component: ConfirmView },
}

function FallbackBlock({ raw, reason }: { raw: unknown; reason: string }) {
  const text =
    raw && typeof raw === 'object' && typeof (raw as { fallback_text?: unknown }).fallback_text === 'string'
      ? (raw as { fallback_text: string }).fallback_text
      : 'Mình chưa hiển thị được phần này.'
  return (
    <div
      className="flex w-full items-start gap-2 rounded-2xl border border-dashed border-border bg-muted/60 px-3 py-2.5 text-[13px] text-muted-foreground"
      data-block="fallback"
      data-reason={reason}
    >
      <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>
        <p className="text-foreground">{text}</p>
        <p className="mt-0.5 text-[11.5px]">
          {reason === 'unknown_type' ? 'Cập nhật ứng dụng để xem đầy đủ.' : 'Không hiển thị được khối này.'}
        </p>
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
    console.warn('[block] render error', err)
  }
  render() {
    return this.state.failed ? <FallbackBlock raw={this.props.raw} reason="render_error" /> : this.props.children
  }
}

export function BlockRenderer({ raw }: { raw: unknown }) {
  const type = raw && typeof raw === 'object' ? (raw as { type?: unknown }).type : undefined
  if (typeof type !== 'string' || !(type in registry)) {
    return <FallbackBlock raw={raw} reason="unknown_type" />
  }
  const entry = registry[type as BlockType]
  const parsed = entry.schema.safeParse(raw)
  if (!parsed.success) {
    console.warn('[block] schema invalid', type, parsed.error.issues.slice(0, 3))
    return <FallbackBlock raw={raw} reason="invalid_schema" />
  }
  const C = entry.Component
  return (
    <BlockBoundary raw={raw}>
      <C block={parsed.data} />
    </BlockBoundary>
  )
}
