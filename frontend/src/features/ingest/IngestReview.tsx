import type { ReactNode } from 'react'
import type { IngestReviewData, IngestRow as Row } from '@/contracts/blocks'
import { IngestRow, type IngestRowProps } from './IngestRow'

/** Câu tóm tắt số dòng theo trạng thái (số từ `counts` của server). */
export function countsSummary(d: IngestReviewData): string {
  const c = d.counts
  const parts: string[] = []
  if (c.auto_added) parts.push(`${c.auto_added} tự thêm`)
  if (c.pending) parts.push(`${c.pending} cần duyệt`)
  if (c.duplicate) parts.push(`${c.duplicate} đã có trong ví`)
  if (c.approved) parts.push(`${c.approved} đã thêm`)
  if (c.rejected) parts.push(`${c.rejected} đã bỏ`)
  return `Đọc được ${d.rows_total} dòng${parts.length ? `: ${parts.join(', ')}` : ''}.`
}

/**
 * Figma I3 (24:2269): danh sách dòng của MỘT lần nạp (khối `ingest_review`). Chỉ xem khi không truyền `rowProps`
 * (khối trong chat); màn Nạp dữ liệu truyền `rowProps` để chọn dòng và đổi hũ.
 */
export function IngestReviewList({
  data,
  rowProps,
  footer,
}: {
  data: IngestReviewData
  rowProps?: (row: Row) => Omit<IngestRowProps, 'row'>
  footer?: ReactNode
}) {
  const hidden = data.rows_total - data.rows.length
  return (
    <section data-block="ingest_review" aria-labelledby={`ir-${data.job_id}`} className="rounded-card bg-surface-2 p-3">
      <h2 id={`ir-${data.job_id}`} className="px-1 text-subtitle font-semibold text-ink">
        {data.source_kind === 'csv' ? 'Các dòng đọc từ sao kê' : 'Các dòng đọc từ ảnh'}
      </h2>
      <p className="px-1 text-small text-ink-2" data-testid="ingest-counts">
        {countsSummary(data)}
      </p>
      <ul className="mt-3 space-y-2" aria-label="Dòng đã đọc">
        {data.rows.map((r) => {
          const p = rowProps?.(r)
          return <IngestRow key={r.row_id} row={r} {...p} jar={p?.jar ?? r.suggested_jar} />
        })}
      </ul>
      {hidden > 0 && <p className="mt-2 px-1 text-note text-ink-2">Còn {hidden} dòng nữa chưa hiện ở đây.</p>}
      {footer}
    </section>
  )
}
