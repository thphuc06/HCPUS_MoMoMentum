import { AlertTriangle } from 'lucide-react'
import { JarIcon } from '@/components/JarIcon'
import { StatusChip } from '@/components/StatusChip'
import { CONFIDENCE_LABEL, statusShortChip } from '@/lib/jar'
import { formatDateTime, formatRatioPercent, formatVnd } from '@/lib/format'
import { formatDayMonth } from '@/lib/dates'
import type { ForecastBasis, ObligationImpactData } from '@/contracts/blocks'

/**
 * Chân thẻ số liệu: số này dựa trên dự báo nào (thời điểm tính, nhóm tin cậy, độ dài lịch sử) để "Vì sao" nói được và để
 * người dùng biết số cũ hay mới. Chỉ vẽ số server trả.
 */
export function BasisFooter({ basis }: { basis: ForecastBasis }) {
  return (
    <div data-testid="basis" className="mt-3 border-t border-line pt-2 text-note text-ink-2">
      <p>
        Dựa trên dự báo cập nhật {formatDateTime(basis.computed_at)} · {basis.history_days} ngày dữ liệu · nhóm tin cậy{' '}
        <span className="font-semibold text-ink">{CONFIDENCE_LABEL[basis.confidence_band]}</span>
      </p>
      {basis.is_initial_estimate && <p className="mt-0.5 font-medium text-warn-fg">Mới là ước lượng ban đầu vì còn ít dữ liệu.</p>}
      {basis.stale && <p className="mt-0.5 font-medium text-warn-fg">Số liệu dự báo chưa theo kịp hôm nay.</p>}
    </div>
  )
}

/**
 * Tác động nghĩa vụ của một món Trả sau (mô phỏng). Hai số TÁCH BẠCH theo hợp đồng: "món này tốn" (`item_cost_vnd`, gồm phần
 * phí phát sinh thêm nếu có) và "đến hạn phải trả" (`total_due_vnd`, cộng dồn với nghĩa vụ đã có). Giao diện chỉ vẽ,
 * không cộng trừ. Đủ/sát/hụt luôn kèm biểu tượng và chữ.
 */
export function ObligationImpactBody({ data, showBasis = true }: { data: ObligationImpactData; showBasis?: boolean }) {
  const c = data.cost
  const chip = statusShortChip(data.status)
  return (
    <div data-testid="obligation-impact-body" data-status={data.status}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-small font-semibold text-ink-2">{c.product_label}</p>
        <StatusChip kind={chip.kind}>{chip.label}</StatusChip>
      </div>
      <p className="mt-1 text-body font-semibold text-ink" data-testid="impact-headline">
        {data.headline}
      </p>

      <dl className="mt-3 space-y-2.5 text-body">
        <div className="flex items-start justify-between gap-3" data-testid="item-cost">
          <dt className="text-ink-2">Món này tốn</dt>
          <dd className="text-right">
            <span className="num font-bold text-ink">{formatVnd(c.item_cost_vnd)}</span>
            <span className="num block text-note font-normal text-ink-2">
              {c.fee_added_vnd > 0 ? `gồm gốc ${formatVnd(c.principal_vnd)} và phí ${formatVnd(c.fee_added_vnd)}` : `gốc ${formatVnd(c.principal_vnd)}, không phát sinh thêm phí`}
            </span>
          </dd>
        </div>
        <div className="flex items-start justify-between gap-3" data-testid="total-due">
          <dt className="text-ink-2">Đến hạn {formatDayMonth(c.due_date)} phải trả</dt>
          <dd className="text-right">
            <span className="num font-bold text-ink">{formatVnd(c.total_due_vnd)}</span>
            {c.existing_due_vnd > 0 && <span className="num block text-note font-normal text-ink-2">gồm {formatVnd(c.existing_due_vnd)} nghĩa vụ Trả sau đã có</span>}
          </dd>
        </div>
        {c.available_before_vnd !== undefined && c.available_after_vnd !== undefined && (
          <div className="flex items-start justify-between gap-3" data-testid="credit-limit">
            <dt className="text-ink-2">Hạn mức còn lại</dt>
            <dd className="num text-right font-semibold text-ink">
              {formatVnd(c.available_before_vnd)} → {formatVnd(c.available_after_vnd)}
            </dd>
          </div>
        )}
      </dl>

      {c.fee && (
        <p className="mt-2 text-note text-ink-2">
          Phí {formatVnd(c.fee.amount_vnd)} theo {c.fee.source_name} (hiệu lực từ {formatDayMonth(c.fee.effective_from)}).
        </p>
      )}
      {c.late_penalty_vnd !== undefined && c.late_penalty_vnd > 0 && <p className="mt-1 text-note text-ink-2">Trả trễ hạn bị phạt {formatVnd(c.late_penalty_vnd)}.</p>}

      <ul className="mt-3 space-y-2" aria-label="Hũ trả nghĩa vụ ngày đến hạn">
        {data.at_due.map((j) => {
          const jc = statusShortChip(j.status)
          return (
            <li key={j.jar.code} data-jar={j.jar.code} data-status={j.status} className="flex items-center gap-3 rounded-2xl bg-surface-2 px-3 py-2.5">
              <JarIcon colorKey={j.jar.color_key} iconKey={j.jar.icon_key} size={32} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-body font-semibold text-ink">Hũ {j.jar.name}</span>
                <span className="num block text-small text-ink-2">
                  Có {formatVnd(j.balance_before_due_vnd)} · cần {formatVnd(j.due_vnd)}
                </span>
                {j.shortfall_vnd > 0 && <span className="num block text-small font-semibold text-bad-fg">Hụt {formatVnd(j.shortfall_vnd)}</span>}
              </span>
              <StatusChip kind={jc.kind}>{jc.label}</StatusChip>
            </li>
          )
        })}
      </ul>

      {data.ratio && (
        <p className="mt-3 text-small text-ink" data-testid="obligation-ratio">
          Nghĩa vụ trên thu nhập: <span className="num font-semibold">{formatRatioPercent(data.ratio.ratio)}</span>, ngưỡng tham khảo{' '}
          <span className="num">{formatRatioPercent(data.ratio.threshold)}</span>
          {data.ratio.exceeds ? <span className="font-semibold text-warn-fg"> (vượt ngưỡng)</span> : ''}
        </p>
      )}

      {data.cautions && data.cautions.length > 0 && (
        <ul className="mt-3 space-y-1.5" aria-label="Lưu ý">
          {data.cautions.map((w) => (
            <li key={w.rule_id} className="flex items-start gap-2 rounded-2xl bg-warn-bg px-3 py-2 text-small font-medium text-warn-fg">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
              {w.text}
            </li>
          ))}
        </ul>
      )}

      {showBasis && <BasisFooter basis={data.basis} />}
    </div>
  )
}
