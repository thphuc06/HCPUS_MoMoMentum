import type { ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import { JarIcon } from '@/components/JarIcon'
import { StatusChip } from '@/components/StatusChip'
import { statusShortChip } from '@/lib/jar'
import { formatShortfallChance, formatVnd } from '@/lib/format'
import { formatDayMonth } from '@/lib/dates'
import type { AffordabilityCardBlock, JarCheck } from '@/contracts/blocks'
import { BasisFooter, ObligationImpactBody } from './ObligationImpactBody'

// Figma AffordCard (11:196): XANH (đủ), VÀNG (sát), ĐỎ (hụt). Dùng CHUNG cho màn chuyển tiền (T3a, T3b, T3c, số từ
// `POST /affordability`) và cho chat (khối `affordability_card` từ tool `forecast___affordability_check`), nên hai nơi cùng số.
// Mọi con số là số engine trả; giao diện chỉ vẽ. Ba trạng thái luôn có biểu tượng + chữ (Đủ, Sát, Hụt), không chỉ màu.

const BORDER = { ok: 'border-ok-line', tight: 'border-warn-line', short: 'border-bad-line' } as const

function JarCheckRow({ c, selected }: { c: JarCheck; selected: boolean }) {
  const chip = statusShortChip(c.status)
  return (
    <li
      data-jar={c.jar.code}
      data-status={c.status}
      data-selected={selected ? 'true' : undefined}
      className={`flex items-start gap-3 rounded-2xl px-3 py-2.5 ${selected ? 'bg-surface-2 ring-2 ring-line' : 'bg-surface-2'}`}
    >
      <JarIcon colorKey={c.jar.color_key} iconKey={c.jar.icon_key} size={32} />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate text-body font-semibold text-ink">Hũ {c.jar.name}</span>
          {selected && <span className="shrink-0 text-note font-semibold text-brand-text">Đang chọn</span>}
        </span>
        <span className="num block text-small text-ink-2">
          Còn {formatVnd(c.balance_before_vnd)} → {formatVnd(c.balance_after_vnd)}
        </span>
        {c.days_earlier !== undefined && c.days_earlier > 0 && c.runout_date_after && (
          <span className="block text-small text-warn-fg">
            Cạn sớm hơn {c.days_earlier} ngày
            {c.runout_date_before ? ` (${formatDayMonth(c.runout_date_before)} → ${formatDayMonth(c.runout_date_after)})` : ` (cạn ngày ${formatDayMonth(c.runout_date_after)})`}
          </span>
        )}
        {c.shortfall_vnd !== undefined && c.shortfall_vnd > 0 && <span className="num block text-small font-semibold text-bad-fg">Hụt {formatVnd(c.shortfall_vnd)} trước kỳ lương</span>}
        {c.p_shortfall_after !== undefined && <span className="block text-note text-ink-2">Khả năng hụt: {formatShortfallChance(c.p_shortfall_after).toLowerCase()}</span>}
      </span>
      <StatusChip kind={chip.kind}>{chip.label}</StatusChip>
    </li>
  )
}

export function AffordCard({
  block,
  actions,
  onAskWhy,
  className,
}: {
  block: AffordabilityCardBlock
  /** Nút hành động của nơi dùng (màn chuyển tiền có "Vẫn chuyển", "Đổi nguồn"...). */
  actions?: ReactNode
  /** Có thì hiện nút "Vì sao" (chỉ trong chat: màn chuyển tiền không có bản ghi lượt agent để giải thích). */
  onAskWhy?: () => void
  className?: string
}) {
  const d = block.data
  const chip = statusShortChip(d.verdict)
  const credit = d.credit
  const creditPrimary = d.funding_source === 'credit'
  return (
    <section data-block="affordability_card" data-verdict={d.verdict} data-source={d.funding_source} className={`rounded-card border-2 bg-surface p-4 ${BORDER[d.verdict]} ${className ?? ''}`}>
      <header className="flex items-center justify-between gap-2">
        <h3 className="text-subtitle font-semibold text-ink">Kiểm tra trước khi trả</h3>
        <StatusChip kind={chip.kind}>{chip.label}</StatusChip>
      </header>
      <p className="mt-2 text-subtitle font-bold text-ink" data-testid="afford-headline">
        {d.headline}
      </p>
      <p className="num mt-1 text-small text-ink-2">
        Số tiền {formatVnd(d.amount_vnd)}
        {d.label ? ` · ${d.label}` : ''}
        {d.pay_date ? ` · ngày ${formatDayMonth(d.pay_date)}` : ''}
      </p>

      {d.jar_checks.length > 0 && (
        <ul className="mt-3 space-y-2" aria-label="Kiểm tra từng hũ">
          {d.jar_checks.map((c) => (
            <JarCheckRow key={c.jar.code} c={c} selected={d.selected_jar_code === c.jar.code} />
          ))}
        </ul>
      )}

      {credit && (
        <div data-testid="afford-credit" className={`mt-3 rounded-2xl p-3 ${creditPrimary ? 'border border-line bg-surface' : 'bg-surface-2'}`}>
          {!creditPrimary && <p className="mb-1 text-small font-semibold text-ink-2">Nếu trả bằng {credit.cost.product_label}</p>}
          <ObligationImpactBody data={credit} showBasis={false} />
        </div>
      )}

      {d.cautions && d.cautions.length > 0 && !credit && (
        <ul className="mt-3 space-y-1.5" aria-label="Lưu ý">
          {d.cautions.map((w) => (
            <li key={w.rule_id} className="flex items-start gap-2 rounded-2xl bg-warn-bg px-3 py-2 text-small font-medium text-warn-fg">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
              {w.text}
            </li>
          ))}
        </ul>
      )}

      {d.options.length > 0 && (
        <div className="mt-3" data-testid="afford-options">
          <p className="text-small font-semibold text-ink-2">Các cách khác</p>
          <ul className="mt-1.5 space-y-2">
            {d.options.map((o) => {
              const oc = statusShortChip(o.status)
              return (
                <li key={o.option_id} data-option={o.option_id} className="flex items-start gap-3 rounded-2xl bg-surface-2 px-3 py-2.5">
                  <span className="min-w-0 flex-1">
                    <span className="block text-body font-semibold text-ink">
                      {o.label}
                      {o.recommended && <span className="ml-2 text-note font-semibold text-brand-text">Gợi ý</span>}
                    </span>
                    <span className="block text-small text-ink-2">{o.summary}</span>
                  </span>
                  <StatusChip kind={oc.kind}>{oc.label}</StatusChip>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {actions && <div className="mt-4 flex flex-col gap-3">{actions}</div>}

      <BasisFooter basis={d.basis} />
      {onAskWhy && (
        <div className="mt-1 flex justify-end">
          <button type="button" onClick={onAskWhy} className="min-h-11 px-2 text-small font-semibold text-brand-text">
            Vì sao
          </button>
        </div>
      )}
    </section>
  )
}
