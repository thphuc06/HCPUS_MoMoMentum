import { AlertTriangle, Check, Minus, XCircle } from 'lucide-react'
import { StatusChip, type ChipKind } from '@/components/StatusChip'
import { CONFIDENCE_LABEL } from '@/lib/jar'
import { formatDateTime } from '@/lib/format'
import type { TraceDetail } from '@/api/schemas'
import type { ExplainBlock, RuleCheck } from '@/contracts/blocks'
import { TraceIdRow } from './TraceIdRow'
import { stepLabel } from './stepLabels'

// Figma ExplainSheet (11:378) và H4: bảng "Vì sao" = dữ liệu đã dùng, luật đã kiểm, nhóm tin cậy Cao/Vừa/Thấp kèm lý do, mã
// trace. Do CODE dựng từ bản ghi lượt (`GET /traces/{id}` hoặc khối `explain` do agent phát); giao diện chỉ vẽ.

const BAND_CHIP: Record<ExplainBlock['data']['confidence']['band'], ChipKind> = { high: 'ok', medium: 'warn', low: 'bad' }

const OUTCOME: Record<RuleCheck['outcome'], { label: string; cls: string; Icon: typeof Check }> = {
  pass: { label: 'Đạt', cls: 'text-ok-fg', Icon: Check },
  warn: { label: 'Cảnh báo', cls: 'text-warn-fg', Icon: AlertTriangle },
  fail: { label: 'Không đạt', cls: 'text-bad-fg', Icon: XCircle },
  skipped: { label: 'Không áp dụng', cls: 'text-ink-2', Icon: Minus },
}

export function ExplainBody({ block, detail }: { block: ExplainBlock; detail?: TraceDetail }) {
  const d = block.data
  const band = d.confidence.band
  return (
    <div data-block="explain" data-band={band} className="space-y-4">
      <div>
        <h3 className="text-section font-bold text-ink">{d.headline ?? 'Vì sao có câu trả lời này'}</h3>
        {d.ai_generated && <p className="mt-0.5 text-note text-ink-2">Lời giải thích trong câu trả lời do AI viết; con số và bảng này do hệ thống ghi lại.</p>}
      </div>

      <section aria-label="Dữ liệu đã dùng">
        <h4 className="text-small font-semibold text-ink-2">Dữ liệu đã dùng</h4>
        <ul className="mt-1.5 divide-y divide-line rounded-card bg-surface-2 px-3" data-testid="explain-data-used">
          {d.data_used.map((u, i) => (
            <li key={`${u.label}-${i}`} className="py-2.5">
              <div className="flex items-start justify-between gap-3">
                <span className="text-body font-medium text-ink">{u.label}</span>
                {u.value && <span className="num shrink-0 text-body font-semibold text-ink">{u.value}</span>}
              </div>
              <p className="text-note text-ink-2">
                {u.tool}
                {u.as_of ? ` · ${formatDateTime(u.as_of)}` : ''}
              </p>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Luật đã kiểm">
        <h4 className="text-small font-semibold text-ink-2">Luật đã kiểm</h4>
        {d.rules_checked.length === 0 ? (
          <p className="mt-1.5 text-small text-ink-2">Lượt này không có luật nào cần kiểm.</p>
        ) : (
          <ul className="mt-1.5 space-y-2" data-testid="explain-rules">
            {d.rules_checked.map((r) => {
              const o = OUTCOME[r.outcome]
              return (
                <li key={r.rule_id} data-rule={r.rule_id} data-outcome={r.outcome} className="flex items-start gap-2.5">
                  <o.Icon className={`mt-0.5 size-4 shrink-0 ${o.cls}`} aria-hidden />
                  <span className="min-w-0 flex-1 text-small text-ink">
                    <span className="font-medium">{r.label}</span>
                    <span className={`ml-1.5 font-semibold ${o.cls}`}>{o.label}</span>
                    {r.detail && <span className="block text-ink-2">{r.detail}</span>}
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section aria-label="Độ tin cậy">
        <h4 className="text-small font-semibold text-ink-2">Độ tin cậy</h4>
        <div className="mt-1.5 flex items-center gap-2">
          <StatusChip kind={BAND_CHIP[band]}>{CONFIDENCE_LABEL[band]}</StatusChip>
          <span className="text-small text-ink-2">Nhóm do hệ thống xếp, không phải phần trăm do AI nói.</span>
        </div>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-small text-ink" data-testid="explain-reasons">
          {d.confidence.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        {band === 'low' && (
          <p role="status" data-testid="explain-low-invite" className="mt-3 rounded-2xl bg-tint px-3 py-2.5 text-small text-ink">
            Độ tin cậy đang thấp vì còn ít dữ liệu. Ghi thêm giao dịch hoặc khai thêm thu nhập và chi phí cố định thì dự báo sẽ sát hơn.
          </p>
        )}
      </section>

      <TraceIdRow traceId={d.subject_trace_id} />

      {detail && (
        <details className="rounded-card bg-surface-2 px-3 py-2.5 text-small" data-testid="explain-detail">
          <summary className="cursor-pointer font-semibold text-ink">Chi tiết kỹ thuật</summary>
          <dl className="mt-2 space-y-1 text-ink-2">
            {detail.intent && (
              <div className="flex justify-between gap-3">
                <dt>Ý định</dt>
                <dd className="num text-ink">{detail.intent}</dd>
              </div>
            )}
            <div className="flex justify-between gap-3">
              <dt>Thời lượng</dt>
              <dd className="num text-ink">{(detail.duration_ms / 1000).toLocaleString('vi-VN', { maximumFractionDigits: 1 })} giây</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt>Lượt gọi mô hình</dt>
              <dd className="num text-ink">{detail.token_usage.model_calls}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt>Token vào / ra</dt>
              <dd className="num text-ink">
                {detail.token_usage.input_tokens.toLocaleString('vi-VN')} / {detail.token_usage.output_tokens.toLocaleString('vi-VN')}
              </dd>
            </div>
            {detail.step_timings.map((s, i) => (
              <div key={`${s.step}-${i}`} data-step={s.step} className="flex justify-between gap-3">
                <dt>{stepLabel(s.step)}</dt>
                <dd className="num text-ink">{s.ms.toLocaleString('vi-VN')} ms</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </div>
  )
}
