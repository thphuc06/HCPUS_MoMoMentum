import { ChevronDown, Copy, ShieldCheck } from 'lucide-react'
import { JarIcon } from '@/components/JarIcon'
import { MoneyInput } from '@/components/MoneyInput'
import { Disclosure } from '@/components/ui/Disclosure'
import type { IngestFx, IngestJar, IngestRow as Row } from '@/contracts/blocks'
import { formatAppDate, formatVnd } from '@/lib/format'
import { cn } from '@/lib/cn'

// Figma IngestRow (14:417), hai biến thể "tự thêm" / "cần duyệt", thêm biến thể "trùng" (đã có trong ví) và trạng thái sau
// khi chốt. Dùng chung cho màn Nạp dữ liệu (I3, có chọn dòng và đổi hũ) và khối `ingest_review` trong chat (chỉ xem).

const STATUS: Record<Row['review_status'], { label: string; cls: string }> = {
  auto_added: { label: 'Tự thêm', cls: 'bg-ok-bg text-ok-fg' },
  pending: { label: 'Cần duyệt', cls: 'bg-warn-bg text-warn-fg' },
  duplicate: { label: 'Đã có trong ví', cls: 'bg-surface-2 text-ink-2' },
  approved: { label: 'Đã thêm', cls: 'bg-ok-bg text-ok-fg' },
  rejected: { label: 'Đã bỏ', cls: 'bg-surface-2 text-ink-2' },
}

/** Dòng còn mở (chưa chốt, không trùng): chọn hoặc bỏ được. */
export const isOpenRow = (r: Row) => r.review_status === 'auto_added' || r.review_status === 'pending'

/** Tên ngắn để đọc màn hình: đối tác, không có thì nội dung, không có nữa thì số thứ tự. */
export const rowTitle = (r: Row) => r.counterparty ?? r.description ?? `Dòng ${r.seq}`

type PiiKind = NonNullable<Row['pii_masked']>[number]

/** Nhãn của loại thông tin cá nhân đã che: ngắn trên chip, đầy đủ cho trình đọc màn hình. Chỉ loại, không bao giờ là giá trị. */
const PII_LABEL: Record<PiiKind, { short: string; full: string }> = {
  name: { short: 'tên', full: 'tên người' },
  phone: { short: 'SĐT', full: 'số điện thoại' },
  account: { short: 'số TK', full: 'số tài khoản' },
  card: { short: 'số thẻ', full: 'số thẻ' },
}

/** Tổng số loại thông tin cá nhân đã che trên các dòng (mỗi loại của mỗi dòng tính một). */
export const piiMaskedCount = (rows: readonly Row[]) => rows.reduce((n, r) => n + (r.pii_masked?.length ?? 0), 0)

/** Số theo ngoại tệ như chứng từ, viết kiểu Việt Nam: "111,11 USD". */
export function formatFxOriginal(fx: IngestFx): string {
  return `${Number(fx.amount_original).toLocaleString('vi-VN', { maximumFractionDigits: 4 })} ${fx.currency}`
}

/** Câu tỷ giá trong mục thu gọn của dòng ngoại tệ. */
export function fxRateText(fx: IngestFx): string {
  if (fx.status !== 'converted' || !fx.rate || !fx.rate_date) return 'Chưa lấy được tỷ giá. Nhập số VND trên sao kê của bạn.'
  const rate = Number(fx.rate).toLocaleString('vi-VN', { maximumFractionDigits: 2 })
  return `Tỷ giá bán Vietcombank ${rate} ₫ ngày ${formatAppDate(fx.rate_date)}. Sao kê thẻ có thể khác do phí.`
}

export type IngestRowProps = {
  row: Row
  /** Hũ đang hiện (đề xuất của server, hoặc hũ người dùng vừa đổi). */
  jar?: IngestJar
  /** Có thì dòng chọn được (ô đánh dấu). */
  selected?: boolean
  onToggle?: (next: boolean) => void
  /** Có thì nút hũ bấm được (mở sheet chọn hũ). */
  onPickJar?: () => void
  /** Đang gửi đổi hũ. */
  jarBusy?: boolean
  disabled?: boolean
  /** Dòng ngoại tệ ở màn duyệt: số VND đang nhập (chữ số, chưa định dạng) và hàm đổi; vắng thì chỉ xem. */
  amountDigits?: string
  onAmountChange?: (digits: string) => void
}

export function IngestRow({ row, jar, selected, onToggle, onPickJar, jarBusy, disabled, amountDigits, onAmountChange }: IngestRowProps) {
  const status = STATUS[row.review_status]
  const title = rowTitle(row)
  const income = row.kind === 'income'
  const editing = !!onAmountChange && !!row.fx && isOpenRow(row)
  const shown = editing && amountDigits ? Number(amountDigits) : row.amount_vnd
  const amount = shown === undefined ? 'Chưa có số VND' : `${income ? '+' : '−'}${formatVnd(shown)}`
  const selectable = !!onToggle && isOpenRow(row)
  const duplicate = row.review_status === 'duplicate'
  const checkId = `ingest-row-${row.row_id}`
  const amountInput = editing ? (
    <MoneyInput
      label="Số VND sẽ ghi"
      value={amountDigits ?? ''}
      onChange={(d) => onAmountChange!(d)}
      error={row.fx!.status === 'rate_unavailable' && !amountDigits ? 'Nhập số VND trước khi thêm' : undefined}
      className="mt-2"
    />
  ) : null

  return (
    <li
      data-ingest-row={row.row_id}
      data-status={row.review_status}
      className={cn('flex gap-3 rounded-2xl bg-surface px-3 py-3', duplicate && 'opacity-75', selectable && selected === false && 'bg-surface-2')}
    >
      {onToggle && (
        <span className="grid min-h-11 min-w-11 shrink-0 place-items-center">
          <input
            id={checkId}
            type="checkbox"
            className="size-5 accent-[var(--brand-primary)]"
            checked={selectable ? !!selected : false}
            disabled={!selectable || disabled}
            onChange={(e) => onToggle(e.target.checked)}
            aria-label={duplicate ? `${title}, ${amount}: đã có trong ví, không thêm lại` : `Thêm dòng ${title}, ${amount}, ngày ${formatAppDate(row.app_date)}`}
          />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-body font-semibold text-ink">{title}</p>
            {row.description && row.counterparty && <p className="truncate text-small text-ink-2">{row.description}</p>}
          </div>
          <p className={cn('num shrink-0 text-body font-bold', shown === undefined ? 'text-small text-warn-fg' : income ? 'text-ok-fg' : 'text-ink')}>{amount}</p>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-2 text-note text-ink-2">
          <span className="num">{formatAppDate(row.app_date)}</span>
          <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-semibold', status.cls)}>
            {duplicate && <Copy className="size-3" aria-hidden />}
            {status.label}
          </span>
          {income && <span className="rounded-full bg-surface-2 px-2 py-0.5 font-semibold">Thu nhập ngoài ví</span>}
          {row.pii_masked?.length ? (
            <span
              role="note"
              data-testid="ingest-pii"
              aria-label={`Đã che trước khi lưu: ${row.pii_masked.map((k) => PII_LABEL[k].full).join(', ')}`}
              className="inline-flex items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 font-semibold"
            >
              <ShieldCheck className="size-3" aria-hidden />
              Đã che: {row.pii_masked.map((k) => PII_LABEL[k].short).join(', ')}
            </span>
          ) : null}
        </div>
        {row.fx &&
          (row.fx.status === 'converted' ? (
            <Disclosure
              label={<span className="num">{formatFxOriginal(row.fx)}</span>}
              ariaLabel={`${formatFxOriginal(row.fx)}: tỷ giá của dòng ${title}`}
              buttonClassName="text-note"
              panelClassName="pb-1 text-note text-ink-2"
            >
              <p data-testid="ingest-fx-rate">{fxRateText(row.fx)}</p>
              {amountInput}
            </Disclosure>
          ) : (
            <div className="mt-1 text-note text-ink-2">
              <p data-testid="ingest-fx-rate">
                <span className="num font-semibold text-ink">{formatFxOriginal(row.fx)}</span> · {fxRateText(row.fx)}
              </p>
              {amountInput}
            </div>
          ))}
        {!income && (
          <div className="mt-2">
            {onPickJar && isOpenRow(row) ? (
              <button
                type="button"
                onClick={onPickJar}
                disabled={disabled || jarBusy}
                aria-busy={jarBusy}
                aria-label={jar ? `Đổi hũ cho dòng ${title}, đang là ${jar.name}` : `Chọn hũ cho dòng ${title}, chưa có hũ`}
                className={cn(
                  'inline-flex min-h-11 items-center gap-2 rounded-full border px-3 text-small font-semibold',
                  jar ? 'border-line bg-surface text-ink' : 'border-warn-fg bg-warn-bg text-warn-fg',
                )}
              >
                {jar && <JarIcon colorKey={jar.color_key} iconKey={jar.icon_key} size={28} />}
                <span>{jarBusy ? 'Đang đổi…' : jar ? jar.name : 'Chọn hũ'}</span>
                <ChevronDown className="size-4" aria-hidden />
              </button>
            ) : jar ? (
              <span className="inline-flex items-center gap-2 text-small font-semibold text-ink">
                <JarIcon colorKey={jar.color_key} iconKey={jar.icon_key} size={28} />
                {jar.name}
              </span>
            ) : (
              <span className="text-small text-ink-2">Chưa xếp hũ</span>
            )}
          </div>
        )}
      </div>
    </li>
  )
}
