import { Link } from 'react-router'
import { AlertTriangle, Download, Plus } from 'lucide-react'
import { JarRow } from '@/components/JarRow'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/StateViews'
import { Skeleton } from '@/components/ui/skeleton'
import { SimNote } from '@/components/SimNote'
import { useOverview } from '@/api/OverviewProvider'
import { formatVnd } from '@/lib/format'

// Figma C2 Danh sách hũ (17:489): tổng trong N hũ, hai ô hũ hệ thống (Tiền vào khác, Chưa phân loại), các dòng hũ.
export function JarsPage() {
  const ov = useOverview()
  const data = ov.data
  const other = data?.system_jars.find((j) => j.system_role === 'other_income')
  const unclassified = data?.system_jars.find((j) => j.system_role === 'unclassified')

  return (
    <>
      <header className="flex items-center justify-between px-4 pt-[max(16px,env(safe-area-inset-top))] pb-3">
        <h1 className="text-title font-bold text-ink">Hũ</h1>
        <Link to="/jars/edit" aria-label="Thêm hoặc sửa hũ" className="grid size-11 place-items-center rounded-full bg-tint text-brand-text">
          <Plus className="size-5" aria-hidden />
        </Link>
      </header>

      {ov.status === 'loading' && (
        <>
          <div className="px-4 pb-3">
            <Skeleton className="h-[140px] w-full rounded-card" />
          </div>
          <ListSkeleton rows={4} label="Đang tải danh sách hũ" />
        </>
      )}
      {ov.status === 'error' && <ErrorState className="px-4" error={ov.error} title="Chưa tải được danh sách hũ" onRetry={() => void ov.reload()} />}

      {data && (
        <>
          <section className="mx-4 rounded-card bg-surface p-4 shadow-card" aria-label="Tổng các hũ">
            <p className="text-small text-ink-2">Tổng trong {data.jars.length} hũ</p>
            <p className="num text-title font-extrabold text-ink" data-testid="jars-total">
              {formatVnd(data.balance.jars_total_vnd)}
            </p>
            <div className="mt-3 grid grid-cols-2 gap-2.5">
              <Link to={other ? `/jars/${other.code}` : '/income'} className="min-h-14 rounded-2xl bg-surface-2 px-3 py-2.5" data-testid="other-income-tile">
                <span className="flex items-center gap-1.5 text-note text-ink-2">
                  <Download className="size-3.5" aria-hidden />
                  Tiền vào khác
                </span>
                <span className="num block text-body font-bold text-ink">{formatVnd(data.balance.other_income_vnd)}</span>
              </Link>
              <Link
                to={unclassified ? `/jars/${unclassified.code}` : '/review'}
                className="min-h-14 rounded-2xl bg-warn-bg px-3 py-2.5"
                data-testid="unclassified-tile"
              >
                <span className="flex items-center gap-1.5 text-note text-warn-fg">
                  <AlertTriangle className="size-3.5" aria-hidden />
                  {data.balance.unclassified_vnd < 0 ? 'Đã chi, chưa xếp hũ' : 'Chưa phân loại'}
                </span>
                <span className="num block text-body font-bold text-ink">
                  {formatVnd(data.balance.unclassified_vnd < 0 ? Math.abs(data.balance.unclassified_vnd) : data.balance.unclassified_vnd)}
                </span>
              </Link>
            </div>
          </section>

          {data.jars.length === 0 ? (
            <EmptyState className="mx-4 mt-3" title="Chưa có hũ nào" message="Thêm hũ để chia lương và theo dõi từng khoản chi." action={<Link to="/jars/edit" className="rounded-full bg-primary px-6 py-3 font-bold text-primary-foreground">Thêm hũ</Link>} />
          ) : (
            <ul className="mx-4 mt-3 space-y-3" aria-label="Các hũ">
              {data.jars.map((j) => (
                <li key={j.code}>
                  <Link to={`/jars/${j.code}`} className="block rounded-card bg-surface px-4 py-1.5 shadow-card" aria-label={`Mở hũ ${j.name}`}>
                    <JarRow jar={j} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
      <SimNote />
        </>
      )}
    </>
  )
}
