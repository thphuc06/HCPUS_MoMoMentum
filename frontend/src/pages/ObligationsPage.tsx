import { Link } from 'react-router'
import { Plus } from 'lucide-react'
import { ScreenHeader } from '@/components/ScreenHeader'
import { SimNote } from '@/components/SimNote'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/StateViews'
import { Disclosure } from '@/components/ui/Disclosure'
import { useApiResource } from '@/api/resource'
import { useJarLookup } from '@/features/common/useJarLookup'
import { CreditUsage } from '@/features/credit/CreditUsage'
import { nearestBnpl, payJarFor } from '@/features/credit/select'
import { CYCLE_LABEL, KIND_LABEL } from '@/features/obligations/params'
import { formatDayMonth } from '@/lib/dates'
import { formatVnd } from '@/lib/format'
import type { Obligation } from '@/api/schemas'

function amountText(o: Obligation): string {
  return o.amount_min_vnd !== undefined && o.amount_max_vnd !== undefined ? `${formatVnd(o.amount_min_vnd)} đến ${formatVnd(o.amount_max_vnd)}` : formatVnd(o.amount_vnd)
}

// Danh sách nghĩa vụ đã khai (tiền trọ, hóa đơn, thuê bao, khoản vay) và khoản Trả sau tự sinh khi mua bằng hạn mức.
// Khoản Trả sau không khai tay được nên không có nút sửa; số gốc và phí lấy từ server.
export function ObligationsPage() {
  const list = useApiResource((api) => api.listObligations(), [])
  const credit = useApiResource((api) => api.getCreditLine(), [])
  const lookup = useJarLookup()
  const line = credit.data?.credit_line ?? null
  // B6: khoản Trả sau đến hạn gần nhất (danh sách nghĩa vụ) so với số dư hũ trả (GET /overview dùng chung).
  const due = list.status === 'ready' ? nearestBnpl(list.data.obligations) : undefined
  const payJar = payJarFor(due, [...lookup.values()])

  return (
    <>
      <ScreenHeader
        title="Nghĩa vụ"
        backTo="/profile"
        right={
          <Link to="/obligations/new" aria-label="Thêm khoản nghĩa vụ" className="grid size-11 place-items-center rounded-full bg-tint text-brand-text">
            <Plus className="size-5" aria-hidden />
          </Link>
        }
      />
      <div className="space-y-3 px-4 pb-8">
        {line && (
          <CreditUsage line={line} due={due} payJar={payJar}>
            <p className="mt-2 text-note text-ink-2">Đến hạn ngày {line.due_day} hằng tháng.{line.status === 'suspended' ? ' Hạn mức đang tạm khóa.' : ''}</p>
            {(credit.data?.fees ?? []).length > 0 && (
              // Điều kiện tính phí và nguồn trích: căn cứ, mặc định thu gọn (Luật chữ, ui-design-review.md §9).
              <Disclosure label="Phí và nguồn" panelClassName="pb-1">
                {(credit.data?.fees ?? []).map((f) => (
                  <p key={f.fee_type} className="mt-1 text-note text-ink-2">
                    {f.amount_vnd !== undefined ? `Phí ${formatVnd(f.amount_vnd)}` : 'Phí'}
                    {f.condition_note ? `: ${f.condition_note}` : ''} (Nguồn: {f.source_name})
                  </p>
                ))}
              </Disclosure>
            )}
          </CreditUsage>
        )}

        {list.status === 'loading' && <ListSkeleton rows={4} label="Đang tải nghĩa vụ" />}
        {list.status === 'error' && <ErrorState error={list.error} title="Chưa tải được nghĩa vụ" onRetry={() => void list.reload()} />}

        {list.status === 'ready' && list.data.obligations.length === 0 && (
          <EmptyState
            title="Chưa có khoản nghĩa vụ nào"
            message="Khai tiền trọ, hóa đơn, thuê bao hay khoản vay để dự báo biết trước ngày tiền ra. Khoản Trả sau sẽ tự hiện khi bạn mua bằng hạn mức."
            action={
              <Link to="/obligations/new" className="inline-flex h-12 items-center rounded-full bg-primary px-6 font-bold text-primary-foreground">
                Thêm khoản
              </Link>
            }
          />
        )}

        {list.status === 'ready' && list.data.obligations.length > 0 && (
          <>
            <ul className="divide-y divide-line rounded-card bg-surface px-4 shadow-card" aria-label="Các khoản nghĩa vụ" data-testid="obligation-list">
              {list.data.obligations.map((o) => {
                const body = (
                  <div className="min-h-[68px] py-2.5">
                    <div className="flex items-start justify-between gap-3">
                      <p className="min-w-0 flex-1 text-body font-semibold text-ink">{o.name}</p>
                      <span className="num max-w-[55%] shrink-0 text-right text-body font-bold text-ink">{amountText(o)}</span>
                    </div>
                    <p className="text-small text-ink-2">
                      {KIND_LABEL[o.kind] ?? o.kind} · {CYCLE_LABEL[o.cycle] ?? o.cycle} · đến hạn {formatDayMonth(o.due_date)}
                      {o.pay_jar ? ` · hũ ${lookup.get(o.pay_jar)?.name ?? o.pay_jar}` : ''}
                    </p>
                    {o.kind === 'bnpl' && o.principal_vnd !== undefined && (
                      <p className="num text-note text-ink-2">
                        Gốc {formatVnd(o.principal_vnd)} + phí {formatVnd(o.fee_vnd)}
                      </p>
                    )}
                  </div>
                )
                return (
                  <li key={o.id} data-obligation={o.id}>
                    {o.source === 'declared' ? (
                      <Link to={`/obligations/${o.id}`} aria-label={`Sửa ${o.name}`}>
                        {body}
                      </Link>
                    ) : (
                      body
                    )}
                  </li>
                )
              })}
            </ul>
            <p className="flex justify-between rounded-card bg-surface-2 px-4 py-3 text-small">
              <span className="text-ink-2">Tổng các khoản đang hoạt động</span>
              <span className="num font-bold text-ink" data-testid="obligations-total">
                {formatVnd(list.data.total_due_vnd)}
              </span>
            </p>
          </>
        )}
      <SimNote />
      </div>
    </>
  )
}
