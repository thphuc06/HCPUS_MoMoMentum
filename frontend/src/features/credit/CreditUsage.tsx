import { useId, type CSSProperties, type ReactNode } from 'react'
import { Link } from 'react-router'
import { ChevronRight } from 'lucide-react'
import { StatusChip } from '@/components/StatusChip'
import { Disclosure } from '@/components/ui/Disclosure'
import { jarColor } from '@/components/jarTheme'
import type { CreditLine, JarFull, Obligation } from '@/api/schemas'
import { formatDayMonth } from '@/lib/dates'
import { formatVnd } from '@/lib/format'

// B6 "Đã dùng Trả sau bao nhiêu" (spending-visualization.md §3): thanh hạn mức đã dùng trên tổng, rồi khoản Trả sau đến hạn gần
// nhất so với số dư hũ dùng để trả. Số lấy từ GET /credit-line (hạn mức), GET /obligations hoặc `obligations_due` của
// GET /overview (khoản), số dư hũ từ GET /overview. Chiều dài thanh là cách vẽ; không có số tiền nào do giao diện tự trừ.

/** Phần Trả sau: chấm trên nền nhạt (khác phần phí và phần số dư cả về hoa văn, không chỉ màu). */
const CREDIT_DOTS: CSSProperties = {
  backgroundColor: 'color-mix(in srgb, var(--accent-blue) 28%, var(--bg-surface))',
  backgroundImage: 'radial-gradient(var(--accent-blue) 1.4px, transparent 1.6px)',
  backgroundSize: '5px 5px',
}

const pct = (part: number, whole: number) => (whole > 0 ? Math.min(100, Math.max(0, (part / whole) * 100)) : 0)

function Track({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <div
      className="mt-1 flex h-3 overflow-hidden rounded-md bg-surface-2 shadow-[inset_0_0_0_1px_var(--border-default)]"
      {...(label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': true })}
    >
      {children}
    </div>
  )
}

function DueCompare({ due, payJar }: { due: Obligation; payJar?: Pick<JarFull, 'name' | 'balance_vnd' | 'color_key'> }) {
  const balance = payJar?.balance_vnd
  const scale = Math.max(due.amount_vnd, balance ?? 0)
  const enough = balance !== undefined && balance >= due.amount_vnd
  const principal = due.principal_vnd
  return (
    <div className="mt-3 border-t border-line pt-3" data-testid="credit-due">
      <h3 className="text-small font-semibold text-ink">Đến hạn {formatDayMonth(due.due_date)}</h3>
      <div className="mt-2 flex justify-between gap-3 text-small text-ink">
        <span className="num">{principal !== undefined ? `Phải trả: gốc ${formatVnd(principal)} + phí ${formatVnd(due.fee_vnd)}` : 'Phải trả'}</span>
        <b className="num shrink-0 font-bold">{formatVnd(due.amount_vnd)}</b>
      </div>
      <Track>
        {principal !== undefined ? (
          <>
            <span className="h-full" style={{ ...CREDIT_DOTS, width: `${pct(principal, scale)}%` }} />
            <span className="h-full bg-ink" style={{ width: `${pct(due.fee_vnd, scale)}%` }} />
          </>
        ) : (
          <span className="h-full" style={{ ...CREDIT_DOTS, width: `${pct(due.amount_vnd, scale)}%` }} />
        )}
      </Track>
      {payJar && balance !== undefined && (
        <>
          <div className="mt-2 flex justify-between gap-3 text-small text-ink">
            <span>Hũ {payJar.name} đang có</span>
            <b className="num shrink-0 font-bold">{formatVnd(balance)}</b>
          </div>
          <Track>
            <span className="h-full" style={{ background: jarColor(payJar.color_key), width: `${pct(balance, scale)}%` }} />
          </Track>
          <p className="mt-2 flex flex-wrap items-center gap-2" data-testid="credit-due-status">
            <StatusChip kind={enough ? 'ok' : 'bad'}>{enough ? 'Đủ trả' : 'Chưa đủ trả'}</StatusChip>
            {/* Chip đã nói đủ hay chưa: câu đầy đủ chỉ cho trình đọc màn hình. */}
            <span className="sr-only">
              {enough ? `Hũ ${payJar.name} đủ cho khoản này.` : `Hũ ${payJar.name} đang có ít hơn số phải trả.`}
            </span>
          </p>
        </>
      )}
    </div>
  )
}

export function CreditUsage({ line, due, payJar, to, testId = 'credit-line', children }: {
  line: CreditLine
  /** Khoản Trả sau đến hạn gần nhất (nếu có). */
  due?: Obligation
  payJar?: Pick<JarFull, 'name' | 'balance_vnd' | 'color_key'>
  /** Có thì cả thẻ có lối "Xem các khoản" (bản rút gọn ở Tổng quan). */
  to?: string
  testId?: string
  children?: ReactNode
}) {
  const titleId = useId()
  const used = pct(line.outstanding_vnd, line.limit_vnd)
  const usedPct = Math.round(used)
  const dueSentence =
    due && payJar
      ? ` Ngày ${formatDayMonth(due.due_date)} phải trả ${formatVnd(due.amount_vnd)}, hũ ${payJar.name} ${payJar.balance_vnd >= due.amount_vnd ? 'đang có đủ' : 'đang có chưa đủ'}.`
      : due
        ? ` Ngày ${formatDayMonth(due.due_date)} phải trả ${formatVnd(due.amount_vnd)}.`
        : ''
  const lead =
    line.outstanding_vnd > 0
      ? `Đang nợ gốc ${formatVnd(line.outstanding_vnd)} trên hạn mức ${formatVnd(line.limit_vnd)}.${dueSentence}`
      : `Chưa dùng Trả sau. Hạn mức ${formatVnd(line.limit_vnd)}.`
  return (
    <section className="rounded-card bg-surface p-4 shadow-card" aria-labelledby={titleId} data-testid={testId}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 id={titleId} className="min-w-0 flex-1 text-subtitle font-semibold text-ink">Đã dùng Trả sau bao nhiêu</h2>
        {line.status === 'suspended' && <StatusChip kind="warn">Tạm khóa</StatusChip>}
        <span className="inline-flex h-7 items-center rounded-full bg-surface-2 px-2.5 text-note font-semibold text-ink-2">{line.product_label}</span>
      </div>
      {/* Câu tóm tắt nhắc lại hai thanh bên dưới: trình đọc màn hình đọc ngay, người nhìn mở "Chi tiết" (Luật chữ §9). */}
      <p className="sr-only">{lead}</p>
      <div className="mt-3">
        <div className="flex justify-between gap-3 text-small text-ink">
          <span className="num">
            Đã dùng <b className="font-bold">{formatVnd(line.outstanding_vnd)}</b>
            {line.limit_vnd > 0 ? ` (${usedPct}%)` : ''}
          </span>
          <span className="num">
            Còn <b className="font-bold text-ok-fg">{formatVnd(line.available_vnd)}</b>
          </span>
        </div>
        <Track label={`Đã dùng ${formatVnd(line.outstanding_vnd)} trên hạn mức ${formatVnd(line.limit_vnd)}, còn ${formatVnd(line.available_vnd)}`}>
          <span className="h-full" style={{ ...CREDIT_DOTS, width: `${used}%` }} />
        </Track>
        <p className="mt-1 text-note text-ink-2">Hạn mức {formatVnd(line.limit_vnd)}</p>
      </div>
      {due && <DueCompare due={due} payJar={payJar} />}
      <Disclosure label="Chi tiết" className="mt-1" panelClassName="pb-1 text-small text-ink-2">
        <p aria-hidden>{lead}</p>
      </Disclosure>
      {children}
      {to && (
        <Link to={to} className="mt-2 -mb-2 flex min-h-11 items-center justify-between text-small font-semibold text-brand-text">
          Xem các khoản Trả sau
          <ChevronRight className="size-5" aria-hidden />
        </Link>
      )}
    </section>
  )
}
