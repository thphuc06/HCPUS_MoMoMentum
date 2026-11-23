import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router'
import type { ReviewListData } from '@/contracts/blocks'
import { formatVnd } from '@/lib/format'

export function UnclassifiedSummary({ data }: { data?: ReviewListData }) {
  if (!data || data.mode !== 'daily_ask' || data.count === 0) return null

  return (
    <Link to="/review" className="flex min-h-11 items-center justify-between gap-2 rounded-card bg-warn-bg px-3 py-2 text-small font-semibold text-warn-fg">
      <span>{data.count} giao dịch chưa phân loại · <span className="num">{formatVnd(data.pending_total_vnd)}</span></span>
      <ChevronRight className="size-4 shrink-0" aria-hidden />
    </Link>
  )
}
