import { useState } from 'react'
import { CheckCircle2, Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { JarIcon } from '@/components/JarIcon'
import { jarColor } from '@/components/jarTheme'
import { useWriteFlow } from '@/api/useWrite'
import type { ActionResponse, JarFull, JarTemplate } from '@/api/schemas'
import { formatPercent } from '@/lib/format'
import { isChanged, isTotalOk, parsePercent, rowFromTemplate, rowsFromJars, saveJarsParams, totalHundredths, type JarRowState } from './params'

/**
 * Chỉnh hũ và tỷ lệ chia lương (O2 của onboarding và màn "Thêm hoặc sửa hũ"): sửa tỷ lệ và tên, thêm hũ từ mẫu
 * `GET /jar-templates`, bỏ hũ (chỉ khi hũ không còn tiền; server kiểm lại). Tổng tỷ lệ phải đúng 100% mới lưu được.
 * Lưu = `save_jars` (thay cả danh sách) qua /confirmations -> /actions. Không có đổi gì thì `onUnchanged` thay vì gọi ghi.
 */
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
          return (
            <li key={`${r.code ?? 'new'}-${i}`} className="flex min-h-[64px] items-center gap-2.5 py-2" data-jar-row={r.code ?? 'new'}>
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
        <Button type="button" disabled={!ok || !namesOk || write.working || write.phase === 'blocked' || (!changed && !onUnchanged)} onClick={() => void save()} aria-busy={write.working}>
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
