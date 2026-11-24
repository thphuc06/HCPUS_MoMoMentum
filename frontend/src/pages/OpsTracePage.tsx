import { Link, useParams } from 'react-router'
import { AlertTriangle, ArrowLeft, Check, Minus, XCircle } from 'lucide-react'
import type { OpsTraceDetail } from '@/api/phase5Schemas'
import { useApiResource } from '@/api/resource'
import { useIsOps } from '@/auth/AuthProvider'
import { ListSkeleton } from '@/components/StateViews'
import { StatusChip, type ChipKind } from '@/components/StatusChip'
import type { RuleCheck } from '@/contracts/blocks'
import { OpsError, OpsLayout } from '@/features/ops/OpsLayout'
import { stepLabel } from '@/features/explain/stepLabels'
import { formatMs, OUTCOME_CHIP, splitToolStep, TOOL_STATUS_CHIP } from '@/features/ops/format'
import { CONFIDENCE_LABEL } from '@/lib/jar'
import { formatDateTime, formatVnd } from '@/lib/format'

// Màn trace X1 (Figma `25:2591`, desktop 1280×800; trên điện thoại xếp một cột): mọi bước của một lượt từ `GET /ops/traces/{id}`:
// router, từng lần gọi tool kèm thời lượng và trạng thái, verifier, luật đã kiểm, dữ liệu đã dùng (đã che PII), độ tin cậy, khối đã
// phát, token và chi phí ước tính. Không có câu hỏi hay câu trả lời của người dùng. Chỉ nhóm Cognito `ops`.

const RULE: Record<RuleCheck['outcome'], { label: string; cls: string; Icon: typeof Check }> = {
  pass: { label: 'Đạt', cls: 'text-ok-fg', Icon: Check },
  warn: { label: 'Cảnh báo', cls: 'text-warn-fg', Icon: AlertTriangle },
  fail: { label: 'Không đạt', cls: 'text-bad-fg', Icon: XCircle },
  skipped: { label: 'Không áp dụng', cls: 'text-ink-2', Icon: Minus },
}
const BAND_CHIP: Record<'high' | 'medium' | 'low', ChipKind> = { high: 'ok', medium: 'warn', low: 'bad' }

function Card({ title, children, id }: { title: string; children: React.ReactNode; id: string }) {
  return (
    <section aria-labelledby={id} className="rounded-card bg-surface p-4 shadow-card">
      <h2 id={id} className="text-subtitle font-semibold text-ink">{title}</h2>
      <div className="mt-2">{children}</div>
    </section>
  )
}

function Header({ t }: { t: OpsTraceDetail }) {
  const chip = OUTCOME_CHIP[t.outcome]
  const n = (x: number) => x.toLocaleString('vi-VN')
  return (
    <section aria-label="Tóm tắt lượt" className="rounded-card bg-surface p-4 shadow-card">
      <div className="flex flex-wrap items-center gap-2">
        <p className="num text-section font-bold break-all text-ink" data-testid="ops-trace-id">{t.trace_id}</p>
        <StatusChip kind={chip.kind}>{chip.label}{t.code ? ` · ${t.code}` : ''}</StatusChip>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-small lg:grid-cols-6">
        <div><dt className="text-ink-2">Thời điểm</dt><dd className="font-semibold text-ink">{formatDateTime(t.created_at)}</dd></div>
        <div><dt className="text-ink-2">Người dùng</dt><dd className="num font-semibold text-ink">{t.user_ref}</dd></div>
        <div><dt className="text-ink-2">Ý định</dt><dd className="font-semibold text-ink">{t.intent ?? '—'}</dd></div>
        <div><dt className="text-ink-2">Thời lượng</dt><dd className="num font-semibold text-ink" data-testid="ops-duration">{formatMs(t.duration_ms)}</dd></div>
        <div>
          <dt className="text-ink-2">Token vào / ra</dt>
          <dd className="num font-semibold text-ink" data-testid="ops-tokens">{n(t.token_usage.input_tokens)} / {n(t.token_usage.output_tokens)}</dd>
        </div>
        <div><dt className="text-ink-2">Chi phí ước tính</dt><dd className="num font-semibold text-ink" data-testid="ops-cost">{formatVnd(t.est_cost_vnd)}</dd></div>
      </dl>
      <p className="mt-2 text-note text-ink-2">
        {n(t.token_usage.model_calls)} lượt gọi model
        {t.token_usage.cache_read_tokens !== undefined ? ` · ${n(t.token_usage.cache_read_tokens)} token đọc từ cache` : ''}
        {' · '}Dữ liệu người dùng đã che thông tin cá nhân
      </p>
    </section>
  )
}

/** Các bước theo thứ tự, thanh dài theo phần thời lượng của cả lượt. Bước là lần gọi tool thì có trạng thái. */
function Steps({ t }: { t: OpsTraceDetail }) {
  const total = Math.max(t.duration_ms, ...t.steps.map((s) => s.ms), 1)
  return (
    <ol aria-label="Các bước của lượt" className="space-y-2">
      {t.steps.map((s, i) => {
        const tool = splitToolStep(s.step)
        const status = s.status ? TOOL_STATUS_CHIP[s.status] : null
        return (
          <li key={`${s.step}-${i}`} data-step={s.step} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 lg:grid-cols-[260px_minmax(0,1fr)_auto]">
            <span className="min-w-0 text-small text-ink">
              {tool ? (
                <><span className="text-ink-2">{tool.target} · </span><span className="font-semibold">{tool.tool}</span></>
              ) : (
                <><span className="font-semibold">{stepLabel(s.step)}</span>{stepLabel(s.step) !== s.step && <span className="text-ink-2"> · {s.step}</span>}</>
              )}
              {status && <StatusChip kind={status.kind} className="ml-2 h-6">{status.label}{s.code ? ` · ${s.code}` : ''}</StatusChip>}
            </span>
            <span className="col-span-2 row-start-2 h-2.5 rounded-full bg-surface-2 lg:col-span-1 lg:row-start-auto" aria-hidden>
              <span
                className={`block h-full rounded-full ${s.status === 'error' || s.status === 'denied' ? 'bg-bad-fg' : tool ? 'bg-blue' : 'bg-brand'}`}
                style={{ width: `${Math.max(2, Math.round((s.ms / total) * 100))}%` }}
              />
            </span>
            <span className="num text-right text-small text-ink">{formatMs(s.ms)}</span>
          </li>
        )
      })}
    </ol>
  )
}

function Detail({ t }: { t: OpsTraceDetail }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="space-y-4">
        <Card id="ops-steps" title="Các bước">
          {t.steps.length === 0 ? <p className="text-small text-ink-2">Lượt này không ghi bước nào.</p> : <Steps t={t} />}
        </Card>
        <Card id="ops-tools" title={`Lần gọi tool (${t.tool_calls.length})`}>
          {t.tool_calls.length === 0 ? (
            <p className="text-small text-ink-2">Lượt này không gọi tool.</p>
          ) : (
            <ul className="divide-y divide-line text-small">
              {t.tool_calls.map((c, i) => {
                const st = TOOL_STATUS_CHIP[c.status]
                return (
                  <li key={`${c.target}-${c.tool}-${i}`} className="flex min-h-11 flex-wrap items-center justify-between gap-2 py-1.5">
                    <span className="text-ink"><span className="text-ink-2">{c.target}___</span>{c.tool}</span>
                    <span className="flex items-center gap-2">
                      <StatusChip kind={st.kind}>{st.label}{c.code ? ` · ${c.code}` : ''}</StatusChip>
                      <span className="num text-ink">{formatMs(c.ms)}</span>
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </Card>
      </div>
      <div className="space-y-4">
        <Card id="ops-rules" title="Luật đã kiểm">
          {t.rules_checked.length === 0 ? (
            <p className="text-small text-ink-2">Lượt này không có luật nào cần kiểm.</p>
          ) : (
            <ul className="space-y-2">
              {t.rules_checked.map((r) => {
                const o = RULE[r.outcome]
                return (
                  <li key={r.rule_id} data-rule={r.rule_id} data-outcome={r.outcome} className="flex items-start gap-2 text-small">
                    <o.Icon className={`mt-0.5 size-4 shrink-0 ${o.cls}`} aria-hidden />
                    <span className="min-w-0">
                      <span className="font-medium text-ink">{r.label}</span>
                      <span className={`ml-1.5 font-semibold ${o.cls}`}>{o.label}</span>
                      {r.detail && <span className="block text-ink-2">{r.detail}</span>}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </Card>
        <Card id="ops-data" title="Dữ liệu đã dùng">
          <ul className="divide-y divide-line text-small">
            {t.data_used.map((u, i) => (
              <li key={`${u.label}-${i}`} className="py-1.5">
                <span className="flex justify-between gap-3">
                  <span className="text-ink">{u.label}</span>
                  {u.value && <span className="num shrink-0 font-semibold text-ink">{u.value}</span>}
                </span>
                <span className="block text-note text-ink-2">{u.tool}{u.as_of ? ` · ${formatDateTime(u.as_of)}` : ''}</span>
              </li>
            ))}
          </ul>
        </Card>
        {t.confidence && (
          <Card id="ops-confidence" title="Độ tin cậy">
            <StatusChip kind={BAND_CHIP[t.confidence.band]}>{CONFIDENCE_LABEL[t.confidence.band]}</StatusChip>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-small text-ink">
              {t.confidence.reasons.map((r) => <li key={r}>{r}</li>)}
            </ul>
          </Card>
        )}
        <Card id="ops-blocks" title="Khối đã phát">
          {t.blocks_emitted.length === 0 ? (
            <p className="text-small text-ink-2">Không có khối nào.</p>
          ) : (
            <ul className="space-y-1 text-small">
              {t.blocks_emitted.map((b) => (
                <li key={b.id} className="flex flex-wrap justify-between gap-2">
                  <span className="font-semibold text-ink">{b.type}</span>
                  <span className="num break-all text-note text-ink-2">{b.id}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}

export function OpsTracePage() {
  const { traceId = '' } = useParams()
  const ops = useIsOps()
  const trace = useApiResource((api) => api.getOpsTrace(traceId), [traceId], ops && !!traceId)
  return (
    <OpsLayout title={`Trace ${traceId}`}>
      <div className="space-y-4">
        <Link to="/ops/summary" className="inline-flex min-h-11 items-center gap-1.5 text-small font-semibold text-brand-text">
          <ArrowLeft className="size-4" aria-hidden />
          Về bảng vận hành
        </Link>
        {trace.status === 'loading' && <ListSkeleton rows={3} rowClass="h-24" label="Đang tải trace" />}
        {trace.status === 'error' && <OpsError error={trace.error} title="Chưa mở được trace" onRetry={() => void trace.reload()} />}
        {trace.data && (
          <>
            <Header t={trace.data} />
            <Detail t={trace.data} />
          </>
        )}
      </div>
    </OpsLayout>
  )
}
