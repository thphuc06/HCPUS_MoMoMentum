import { useState } from 'react'
import { CheckCircle2, Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { MoneyInput } from '@/components/MoneyInput'
import { JarIcon } from '@/components/JarIcon'
import { jarColor } from '@/components/jarTheme'
import { useWriteFlow } from '@/api/useWrite'
import type { ActionResponse, JarFull, JarPurpose, JarTemplate } from '@/api/schemas'
import { formatPercent } from '@/lib/format'
import { isChanged, isTotalOk, parsePercent, rowFromTemplate, rowsFromJars, saveJarsParams, totalHundredths, type JarRowState } from './params'

/**
 * Chỉnh hũ và tỷ lệ chia lương (O2 của onboarding và màn "Thêm hoặc sửa hũ"): sửa tỷ lệ và tên, thêm hũ từ mẫu
 * `GET /jar-templates`, bỏ hũ (chỉ khi hũ không còn tiền; server kiểm lại). Tổng tỷ lệ phải đúng 100% mới lưu được.
 * Lưu = `save_jars` (thay cả danh sách) qua /confirmations -> /actions. Không có đổi gì thì `onUnchanged` thay vì gọi ghi.
 */
const PURPOSE_LABEL: Record<JarPurpose, string> = {
  buffer: 'Dự phòng',
  sinking: 'Quỹ dồn',
  goal: 'Mục tiêu',
  long_term: 'Tích lũy dài hạn',
}

export function JarSplitEditor({
  jars,
  templates,
  onSaved,
  onUnchanged,
  onSkip,
  submitLabel = 'Lưu',
  skipLabel,
}: {
  jars: JarFull[]
  templates: JarTemplate[]
  onSaved: (r: ActionResponse) => void
  onUnchanged?: () => void
  onSkip?: () => void
  submitLabel?: string
  skipLabel?: string
}) {
  const [rows, setRows] = useState<JarRowState[]>(() => rowsFromJars(jars))
  const write = useWriteFlow()
  const total = totalHundredths(rows)
  const ok = isTotalOk(rows)
  const namesOk = rows.length > 0 && rows.every((r) => r.name.trim().length > 0)
  const targetsOk = rows.every((r) =>
    !r.goal_date || !!r.goal_vnd || r.purpose === 'sinking' || r.purpose === 'long_term',
  )
  const changed = isChanged(rows, jars)
  const available = templates.filter((t) => !rows.some((r) => r.code === t.code || r.name.trim().toLowerCase() === t.name.toLowerCase()))

  const setRow = (i: number, p: Partial<JarRowState>) => setRows((rs) => rs.map((r, k) => (k === i ? { ...r, ...p } : r)))

  const save = async () => {
    if (!changed) return onUnchanged?.()
    const r = await write.submit('save_jars', saveJarsParams(rows))
    if (r) onSaved(r)
  }

  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full bg-surface-2" aria-hidden>
        {rows.map((r, i) => {
          const v = parsePercent(r.percent)
          return Number.isNaN(v) || v <= 0 ? null : <span key={`${r.code ?? r.name}-${i}`} style={{ width: `${Math.min(100, v)}%`, background: jarColor(r.color_key) }} />
        })}
      </div>

      <ul className="mt-3 divide-y divide-line rounded-card bg-surface px-3 shadow-card" aria-label="Các hũ và tỷ lệ chia lương">
        {rows.map((r, i) => {
          const locked = r.code !== undefined && r.balance_vnd > 0
          const committed = r.purpose === 'sinking' &&
            jars.some((jar) => jar.code === r.code && jar.purpose === 'sinking' && !!jar.goal_date)
          return (
            <li key={`${r.code ?? 'new'}-${i}`} className="py-2" data-jar-row={r.code ?? 'new'}>
              <div className="flex min-h-12 items-center gap-2.5">
                <JarIcon colorKey={r.color_key} iconKey={r.icon_key} size={36} />
                <Input
                  aria-label={`Tên hũ ${i + 1}`}
                  value={r.name}
                  maxLength={40}
                  onChange={(e) => setRow(i, { name: e.target.value })}
                  className="h-11 min-w-0 flex-1 border-transparent bg-transparent px-1 text-body font-semibold"
                />
                <div className="relative w-[84px] shrink-0">
                  <Input
                    aria-label={`Tỷ lệ chia lương của ${r.name || `hũ ${i + 1}`}`}
                    inputMode="decimal"
                    value={r.percent}
                    onChange={(e) => setRow(i, { percent: e.target.value.replace(/[^\d.,]/g, '').slice(0, 6) })}
                    className="num h-11 bg-surface-2 pr-7 text-right font-bold"
                  />
                  <span aria-hidden className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-small text-ink-2">
                    %
                  </span>
                </div>
                <button
                  type="button"
                  aria-label={locked ? `Hũ ${r.name} còn tiền nên chưa bỏ được` : `Bỏ hũ ${r.name}`}
                  disabled={locked || rows.length <= 1}
                  onClick={() => setRows((rs) => rs.filter((_, k) => k !== i))}
                  className="grid size-11 shrink-0 place-items-center rounded-full text-ink-2 disabled:opacity-30"
                >
                  <X className="size-5" aria-hidden />
                </button>
              </div>
              {r.kind === 'saving' && (
                <div className="space-y-2 pb-2 pl-[46px]">
                  <label className="block text-small font-semibold text-ink-2">
                    Mục đích
                    <select
                      aria-label={`Mục đích của ${r.name}`}
                      className="mt-1 block h-10 w-full rounded-xl border border-line bg-surface px-2"
                      value={r.purpose ?? ''}
                      onChange={(e) => setRow(i, { purpose: e.target.value as JarPurpose })}
                    >
                      <option value="" disabled>Chưa đặt mục đích</option>
                      {Object.entries(PURPOSE_LABEL).map(([purpose, label]) => (
                        <option key={purpose} value={purpose}>{label}</option>
                      ))}
                    </select>
                  </label>
                  {r.purpose && r.purpose !== 'buffer' && (
                    <div className="grid gap-2 sm:grid-cols-2">
                      <MoneyInput
                        label={r.purpose === 'sinking' ? 'Số tiền dự kiến' : 'Số tiền muốn dành'}
                        value={r.goal_vnd ? String(r.goal_vnd) : ''}
                        onChange={(v) => setRow(i, { goal_vnd: v ? Number(v) : undefined })}
                      />
                      <label className="block text-small font-semibold text-ink-2">
                        {r.purpose === 'sinking' ? 'Ngày dự kiến' : 'Ngày đích'}
                        <Input
                          className="mt-1"
                          type="date"
                          readOnly={committed}
                          value={r.goal_date ?? ''}
                          onChange={(e) => setRow(i, { goal_date: e.target.value || undefined })}
                          aria-invalid={r.purpose === 'goal' && !!r.goal_date && !r.goal_vnd}
                        />
                        {r.purpose === 'goal' && r.goal_date && !r.goal_vnd && (
                          <span className="mt-1 block text-bad-fg">Nhập số tiền cho mục tiêu này.</span>
                        )}
                      </label>
                    </div>
                  )}
                </div>
              )}
            </li>
          )
        })}
      </ul>

      <div
        role="status"
        data-testid="split-total"
        data-ok={ok}
        className={`mt-3 flex items-center justify-between rounded-2xl px-4 py-3 text-small font-semibold ${ok ? 'bg-ok-bg text-ok-fg' : 'bg-warn-bg text-warn-fg'}`}
      >
        <span className="flex items-center gap-2">
          {ok ? <CheckCircle2 className="size-4" aria-hidden /> : null}
          {ok ? 'Tổng đủ 100%' : Number.isNaN(total) ? 'Có ô tỷ lệ chưa hợp lệ' : `Tổng đang là ${formatPercent(total / 100)}, cần đúng 100%`}
        </span>
      </div>

      {available.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-small font-semibold text-ink-2">Thêm hũ</p>
          <div className="flex flex-wrap gap-2">
            {available.map((t) => (
              <button
                key={t.code}
                type="button"
                onClick={() => setRows((rs) => [...rs, rowFromTemplate(t)])}
                className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-dashed border-brand px-4 text-small font-semibold text-brand-text"
              >
                <Plus className="size-4" aria-hidden />
                {t.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {write.error && (
        <p role="alert" className="mt-3 rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
          {write.error.message}
        </p>
      )}

      <div className="mt-5 flex flex-col gap-3">
        <Button type="button" disabled={!ok || !namesOk || !targetsOk || write.working || write.phase === 'blocked' || (!changed && !onUnchanged)} onClick={() => void save()} aria-busy={write.working}>
          {write.working ? 'Đang lưu…' : submitLabel}
        </Button>
        {onSkip && (
          <Button type="button" variant="ghost" onClick={onSkip} disabled={write.working}>
            {skipLabel ?? 'Bỏ qua'}
          </Button>
        )}
      </div>
    </div>
  )
}
