import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router'
import { useApi } from '@/api/ApiProvider'
import { ApiError } from '@/api/errors'
import type { OpsDayModelCalls, OpsModelDayCalls, OpsSummaryResponse, OpsTraceQuery, OpsTraceSummary } from '@/api/phase5Schemas'
import { useApiResource } from '@/api/resource'
import { useIsOps } from '@/auth/AuthProvider'
import { ListSkeleton } from '@/components/StateViews'
import { StatusChip, type ChipKind } from '@/components/StatusChip'
import { Button } from '@/components/ui/button'
import { opsTracePath } from '@/features/explain/TraceIdRow'
import { OpsError, OpsLayout } from '@/features/ops/OpsLayout'
import { capLevel, formatMs, OUTCOME_CHIP, shortModelNames, type CapLevel } from '@/features/ops/format'
import { formatDayMonth } from '@/lib/dates'
import { formatDateTime, formatRatioPercent, formatVnd } from '@/lib/format'

// Bảng vận hành (FR15): số tổng hợp `GET /ops/summary` và các lượt gần đây `GET /ops/traces` của mọi người dùng (người dùng hiện
// bằng `user_ref`, không có câu hỏi hay câu trả lời). Chỉ nhóm Cognito `ops`.

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-card bg-surface p-4 shadow-card">
      <dt className="text-small text-ink-2">{label}</dt>
      <dd className="num mt-1 text-section font-bold text-ink">{value}</dd>
      {hint && <dd className="text-note text-ink-2">{hint}</dd>}
    </div>
  )
}

function SummaryView({ s }: { s: OpsSummaryResponse }) {
  return (
    <section aria-labelledby="ops-summary-heading" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="ops-summary-heading" className="text-section font-bold text-ink">Tổng hợp</h2>
        <p className="text-small text-ink-2">{formatDateTime(s.from)} – {formatDateTime(s.to)}</p>
      </div>
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="ops-kpis">
        <Kpi label="Số lượt" value={n(s.turns)} hint={`${n(s.turns_rejected)} bị từ chối · ${n(s.turns_error)} lỗi`} />
        <Kpi label="Độ trễ p50 / p95" value={s.latency_ms ? `${formatMs(s.latency_ms.p50)} / ${formatMs(s.latency_ms.p95)}` : 'Chưa có lượt'} />
        <Kpi label="Lỗi tool" value={formatRatioPercent(s.tool_error_rate)} hint={`${n(s.tool_errors)} / ${n(s.tool_calls)} lần gọi`} />
        <Kpi label="Luật chặn" value={n(s.rule_fails)} hint={`Chi phí ước tính ${formatVnd(s.est_cost_vnd)}`} />
      </dl>
      <div className="rounded-card bg-surface p-4 shadow-card">
        <h3 className="text-subtitle font-semibold text-ink">Lượt gọi model theo ngày</h3>
        {s.model_calls_by_day.length === 0 ? (
          <p className="mt-2 text-small text-ink-2">Chưa có lượt gọi model nào trong khoảng này.</p>
        ) : (
          <>
            <p className="mt-1 text-note text-ink-2">Trần ngày tính riêng cho từng model, cảnh báo từ 80% trần.</p>
            <ul className="mt-2 divide-y divide-line" aria-label="Lượt gọi model theo ngày">
              {s.model_calls_by_day.map((d) => <DayRow key={d.day} d={d} />)}
            </ul>
          </>
        )}
      </div>
    </section>
  )
}

const n = (x: number) => x.toLocaleString('vi-VN')

const LEVEL: Record<CapLevel, { bar: string; chip?: { kind: ChipKind; label: string } }> = {
  ok: { bar: 'bg-brand' },
  near: { bar: 'bg-warn-line', chip: { kind: 'warn', label: 'Gần trần' } },
  over: { bar: 'bg-bad-fg', chip: { kind: 'bad', label: 'Chạm trần' } },
}

/**
 * Một ngày: tổng lượt gọi, rồi từng model so với trần của chính nó (`by_model`). Tổng ngày không so với `cap` của ngày vì đó là
 * tổng trần mọi model. Không có `by_model` (số lấy từ bản ghi lượt) thì hiện tổng so với `cap` như trước.
 */
function DayRow({ d }: { d: OpsDayModelCalls }) {
  const day = formatDayMonth(d.day)
  if (!d.by_model) {
    return (
      <li data-day={d.day} className="grid grid-cols-[56px_1fr_auto] items-center gap-3 py-2 text-small">
        <span className="text-ink-2">{day}</span>
        <meter className="h-3 w-full" min={0} max={d.cap} value={Math.min(d.model_calls, d.cap)} aria-label={`Ngày ${day}: ${d.model_calls} trên trần ${d.cap}`} />
        <span className="num text-ink">{n(d.model_calls)} / {n(d.cap)}</span>
      </li>
    )
  }
  const names = shortModelNames(d.by_model.map((m) => m.model))
  return (
    <li data-day={d.day} className="space-y-1.5 py-2 text-small">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-ink-2">{day}</span>
        <span className="num font-semibold text-ink" data-testid="ops-day-total">{n(d.model_calls)} lượt</span>
      </div>
      {d.by_model.length > 0 && (
        <ul className="space-y-1.5" aria-label={`Theo model ngày ${day}`}>
          {d.by_model.map((m, i) => <ModelRow key={m.model} m={m} name={names[i]!} />)}
        </ul>
      )}
    </li>
  )
}

function ModelRow({ m, name }: { m: OpsModelDayCalls; name: string }) {
  if (m.cap === undefined) {
    return (
      <li data-model={m.model} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 lg:grid-cols-[160px_minmax(0,1fr)_auto]">
        <span className="truncate text-ink" title={m.model}>{name}</span>
        <span className="hidden text-note text-ink-2 lg:block">Không còn trong cấu hình</span>
        <span className="num text-right text-ink">{n(m.model_calls)} lượt</span>
      </li>
    )
  }
  const level = capLevel(m.model_calls, m.cap)
  const { bar, chip } = LEVEL[level]
  const pct = m.cap > 0 ? Math.min(100, Math.round((m.model_calls / m.cap) * 100)) : 100
  return (
    <li data-model={m.model} data-level={level} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 lg:grid-cols-[160px_minmax(0,1fr)_auto]">
      <span className="truncate text-ink" title={m.model}>{name}</span>
      <span
        role="meter"
        aria-label={`${name}: ${m.model_calls} trên trần ${m.cap}`}
        aria-valuemin={0}
        aria-valuemax={m.cap}
        aria-valuenow={Math.min(m.model_calls, m.cap)}
        className="col-span-2 row-start-2 h-2.5 rounded-full bg-surface-2 lg:col-span-1 lg:row-start-auto"
      >
        <span className={`block h-full rounded-full ${bar}`} style={{ width: `${m.model_calls > 0 ? Math.max(2, pct) : 0}%` }} />
      </span>
      <span className="flex items-center justify-end gap-2">
        {chip && <StatusChip kind={chip.kind} className="h-6">{chip.label}</StatusChip>}
        <span className="num text-ink">{n(m.model_calls)} / {n(m.cap)}</span>
      </span>
    </li>
  )
}

type TraceList = { status: 'loading' | 'ready' | 'error'; items: OpsTraceSummary[]; cursor?: string; error: ApiError | null; more: boolean }

function useTraceList(query: Omit<OpsTraceQuery, 'cursor'>, enabled: boolean) {
  const api = useApi()
  const [state, setState] = useState<TraceList>({ status: 'loading', items: [], error: null, more: false })
  const key = JSON.stringify(query)
  const load = useCallback(async (cursor?: string) => {
    setState((s) => (cursor ? { ...s, more: true } : { status: 'loading', items: [], error: null, more: false }))
    try {
      const r = await api.listOpsTraces({ ...(JSON.parse(key) as OpsTraceQuery), limit: 50, cursor })
      setState((s) => ({ status: 'ready', items: cursor ? [...s.items, ...r.traces] : r.traces, cursor: r.next_cursor, error: null, more: false }))
    } catch (e) {
      const error = e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0)
      setState((s) => ({ ...s, status: 'error', error, more: false }))
    }
  }, [api, key])
  useEffect(() => {
    if (enabled) void load()
  }, [load, enabled])
  return { ...state, reload: () => load(), loadMore: () => state.cursor && load(state.cursor) }
}

const OUTCOME_FILTER = [
  { value: '', label: 'Mọi kết quả' },
  { value: 'ok', label: 'Thành công' },
  { value: 'rejected', label: 'Bị từ chối' },
  { value: 'error', label: 'Lỗi' },
] as const

function TraceTable({ enabled }: { enabled: boolean }) {
  const [outcome, setOutcome] = useState<'' | 'ok' | 'rejected' | 'error'>('')
  const list = useTraceList(outcome ? { outcome } : {}, enabled)
  return (
    <section aria-labelledby="ops-traces-heading" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="ops-traces-heading" className="text-section font-bold text-ink">Các lượt gần đây</h2>
        <label className="flex items-center gap-2 text-small text-ink-2">
          Kết quả
          <select
            value={outcome}
            onChange={(e) => setOutcome(e.target.value as typeof outcome)}
            className="min-h-11 rounded-xl border border-line bg-surface px-3 text-small text-ink"
          >
            {OUTCOME_FILTER.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
      </div>
      {list.status === 'loading' && <ListSkeleton rows={3} rowClass="h-12" label="Đang tải các lượt" />}
      {list.status === 'error' && list.error && <OpsError error={list.error} title="Chưa tải được các lượt" onRetry={() => void list.reload()} />}
      {list.status === 'ready' && list.items.length === 0 && <p className="text-small text-ink-2">Không có lượt nào.</p>}
      {list.items.length > 0 && (
        <div className="overflow-x-auto rounded-card bg-surface shadow-card">
          <table className="w-full min-w-[640px] text-left text-small">
            <caption className="sr-only">Các lượt gần đây của mọi người dùng</caption>
            <thead className="text-note text-ink-2">
              <tr className="border-b border-line">
                <th scope="col" className="px-3 py-2 font-semibold">Thời điểm</th>
                <th scope="col" className="px-3 py-2 font-semibold">Mã trace</th>
                <th scope="col" className="px-3 py-2 font-semibold">Người dùng</th>
                <th scope="col" className="px-3 py-2 font-semibold">Ý định</th>
                <th scope="col" className="px-3 py-2 font-semibold">Kết quả</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">Thời lượng</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">Tool (lỗi)</th>
                <th scope="col" className="px-3 py-2 text-right font-semibold">Chi phí</th>
              </tr>
            </thead>
            <tbody>
              {list.items.map((t) => {
                const chip = OUTCOME_CHIP[t.outcome]
                return (
                  <tr key={t.trace_id} className="border-b border-line last:border-0">
                    <td className="px-3 py-2 whitespace-nowrap text-ink-2">{formatDateTime(t.created_at)}</td>
                    <td className="px-3 py-2">
                      <Link to={opsTracePath(t.trace_id)} className="num inline-flex min-h-11 items-center font-semibold text-brand-text">
                        {t.trace_id.slice(0, 8)}
                      </Link>
                    </td>
                    <td className="num px-3 py-2 text-ink-2">{t.user_ref}</td>
                    <td className="px-3 py-2 text-ink">{t.intent ?? '—'}</td>
                    <td className="px-3 py-2"><StatusChip kind={chip.kind}>{chip.label}{t.code ? ` · ${t.code}` : ''}</StatusChip></td>
                    <td className="num px-3 py-2 text-right text-ink">{formatMs(t.duration_ms)}</td>
                    <td className="num px-3 py-2 text-right text-ink">{t.tool_calls} ({t.tool_errors})</td>
                    <td className="num px-3 py-2 text-right text-ink">{formatVnd(t.est_cost_vnd)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {list.cursor && list.status === 'ready' && (
        <Button type="button" variant="outline" size="sm" disabled={list.more} onClick={() => void list.loadMore()}>
          {list.more ? 'Đang tải…' : 'Xem thêm'}
        </Button>
      )}
    </section>
  )
}

export function OpsSummaryPage() {
  const ops = useIsOps()
  const summary = useApiResource((api) => api.getOpsSummary(), [], ops)
  return (
    <OpsLayout title="Bảng vận hành">
      <div className="space-y-6">
        {summary.status === 'loading' && <ListSkeleton rows={2} rowClass="h-24" label="Đang tải số tổng hợp" />}
        {summary.status === 'error' && <OpsError error={summary.error} title="Chưa tải được số tổng hợp" onRetry={() => void summary.reload()} />}
        {summary.data && <SummaryView s={summary.data} />}
        {!(summary.status === 'error' && summary.error.code === 'FORBIDDEN') && <TraceTable enabled={ops} />}
      </div>
    </OpsLayout>
  )
}
