import { JarIcon } from './JarIcon'
import { cn } from '@/lib/cn'
import { formatDayMonth } from '@/lib/dates'
import { formatSignedVnd } from '@/lib/format'
import type { Transaction } from '@/api/schemas'

export type JarRef = { name: string; color_key: string; icon_key: string }

/** Tiêu đề một dòng giao dịch: người nhận, đối tác, lời nhắn; không có thì nêu loại bằng chữ. */
export function txTitle(tx: Transaction): string {
  return tx.payee_name || tx.merchant || tx.note || (tx.kind === 'income' ? 'Tiền vào' : tx.kind === 'transfer' ? 'Chuyển giữa hũ' : 'Giao dịch')
}

// Figma TxRow (14:264): icon hũ, tiêu đề, "dd/mm · hũ · nguồn", số tiền có dấu. Số tiền vào màu xanh (đủ), ra màu chữ chính.
export function TxRow({ tx, jar, creditLabel }: { tx: Transaction; jar?: JarRef; creditLabel?: string }) {
  const credit = tx.funding_source === 'credit'
  const sub = [formatDayMonth(tx.app_date), jar?.name ?? (tx.jar ? undefined : 'Chưa gán hũ'), credit ? (creditLabel ?? 'Trả sau') : undefined, tx.needs_review ? 'Cần xem lại' : undefined]
    .filter(Boolean)
    .join(' · ')
  return (
    <div className="flex min-h-[64px] items-center gap-3 py-2" data-tx={tx.id}>
      <JarIcon colorKey={jar?.color_key ?? 'gray'} iconKey={jar?.icon_key ?? (tx.kind === 'income' ? 'inbox' : 'wallet')} size={40} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-body font-semibold text-ink">{txTitle(tx)}</p>
        <p className="truncate text-small text-ink-2">{sub}</p>
      </div>
      <span className={cn('num shrink-0 text-body font-bold', tx.amount_vnd > 0 ? 'text-ok-fg' : 'text-ink')}>{formatSignedVnd(tx.amount_vnd)}</span>
    </div>
  )
}
