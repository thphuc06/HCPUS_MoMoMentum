import { ExternalLink, FileText } from 'lucide-react'
import { Disclosure } from '@/components/ui/Disclosure'
import type { CitationData } from '@/contracts/blocks'
import { formatAppDate } from '@/lib/format'

// Khối `citation`: nguồn của biểu phí Trả sau (mô phỏng). Tên nguồn, đường dẫn, ngày hiệu lực và câu trích đều chép từ bảng phí có
// cấu trúc (`knowledge___get_fee_schedule`), không do AI viết; khối không mang số tiền (số nói ra nằm ở câu trả lời và bảng phí).

/** Tên loại phí xuất hiện trong bảng phí seed và fixture hợp đồng; loại khác hiện mã gốc để không đoán nghĩa. */
const FEE_TYPE_LABEL: Record<string, string> = {
  monthly_service_fee: 'Phí dịch vụ hằng tháng',
  late_payment_fee: 'Phí trả chậm',
}

export function feeTypeLabel(code: string): string {
  return FEE_TYPE_LABEL[code] ?? code
}

export function Citation({ data }: { data: CitationData }) {
  return (
    <section data-block="citation" aria-label={`Nguồn biểu phí ${data.product_label}`} className="space-y-2 rounded-card bg-surface p-4 shadow-card">
      <header className="flex items-center gap-2">
        <FileText className="size-5 shrink-0 text-ink-2" aria-hidden />
        <h3 className="text-subtitle font-semibold text-ink">Nguồn biểu phí · {data.product_label}</h3>
      </header>
      <ol className="space-y-2">
        {data.items.map((item) => (
          <li key={`${item.source_url}|${item.effective_from}|${item.source_name}`} className="space-y-1 rounded-xl bg-surface-2 p-3">
            <a
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-start gap-1.5 text-small font-semibold text-brand-text underline-offset-2 hover:underline"
            >
              <span>{item.source_name}</span>
              <ExternalLink className="mt-0.5 size-4 shrink-0" aria-label="(mở trang mới)" />
            </a>
            <p className="text-note text-ink-2">Hiệu lực từ {formatAppDate(item.effective_from)}</p>
            {/* Loại phí áp dụng và câu trích nguyên văn: nguồn trích, mặc định thu gọn (Luật chữ, ui-design-review.md §9). */}
            <Disclosure label="Xem trích dẫn" panelClassName="space-y-1 pb-1">
              <p className="text-note text-ink-2">
                Áp dụng cho: <span className="text-ink">{item.fee_types.map(feeTypeLabel).join(', ')}</span>
              </p>
              {item.excerpt && <blockquote className="border-l-2 border-line pl-2 text-small text-ink">{item.excerpt}</blockquote>}
            </Disclosure>
          </li>
        ))}
      </ol>
      <p className="text-note text-ink-2">Trả sau là mô phỏng; biểu phí lấy nguồn công khai làm ví dụ.</p>
    </section>
  )
}
