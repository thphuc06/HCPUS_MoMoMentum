import { Link, useParams } from 'react-router'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { JarGlass } from '@/components/JarGlass'
import { JarStatusChip } from '@/components/JarStatusChip'
import { Notice } from '@/components/Notice'
import { SimNote } from '@/components/SimNote'
import { ScreenHeader } from '@/components/ScreenHeader'
import { ErrorState, EmptyState } from '@/components/StateViews'
import { TxRow } from '@/components/TxRow'
import { useApiResource } from '@/api/resource'
import { FORECAST_FOLLOW_UP_MS, useForecastFollowUp } from '@/api/ApiProvider'
import { useOverview } from '@/api/OverviewProvider'
import { useChatLauncher } from '@/chat/launcher'
import { ForecastBlock } from '@/features/forecast/ForecastBlock'
import { jarReference, lowestP50BeforePayday } from '@/features/forecast/model'
import { useJarLookup } from '@/features/common/useJarLookup'
import { formatDayMonth } from '@/lib/dates'
import { formatAppDate, formatPercent, formatVnd } from '@/lib/format'
import { levelOf } from '@/lib/jar'

// Figma C2 Chi tiết hũ (17:801, 17:925): hũ thủy tinh + số dư, khối dự báo 30 ngày (dùng chung với chat), giao dịch gần
// đây, luật chia và mục tiêu, hai nút. GET /jars/{code} và GET /forecasts/{code} gọi song song; dự báo lỗi hay chưa có
// thì chỉ phần dự báo báo lỗi (có Thử lại), phần còn lại vẫn hiện.
export function JarDetailPage() {
  const { code = '' } = useParams()
  const launcher = useChatLauncher()
  const lookup = useJarLookup()
  const ov = useOverview()
  const detail = useApiResource((api) => api.getJar(code), [code])
  const isSystem = detail.data?.jar.kind === 'system'
  const forecastPending = useForecastFollowUp()
  // Sau khi ghi giao dịch, dự báo mới có sau 3 đến 4 giây: đọc lại cho tới khi `computed_at` theo kịp (tối đa 60 giây).
  // Server cũng có thể trả `stale: true` (chưa tính lại được): thử lại vài lần.
  const forecast = useApiResource(
    (api) => api.getForecast(code),
    [code],
    detail.status !== 'loading' && !!detail.data && !isSystem,
    (d) => {
      if (forecastPending(d.data.computed_at)) return { delayMs: 3_000, maxMs: FORECAST_FOLLOW_UP_MS }
      if (d.data.stale) return { delayMs: 4_000, maxMs: 20_000 }
      return null
    },
  )

  const jar = detail.data?.jar
  const f = forecast.data?.data
  const ref = f && jar ? jarReference(f, jar.goal_vnd) : jar?.goal_vnd ?? Math.max(jar?.balance_vnd ?? 0, 1)
  const level = jar ? levelOf(jar.balance_vnd, ref) : 0
  const forecastLevel = f ? levelOf(lowestP50BeforePayday(f), ref) : null
  const status = jar?.status ?? f?.status
  const payday = f?.payday ?? (ov.data?.next_payday ? { date: ov.data.next_payday.date, days_until: ov.data.next_payday.days_until } : null)

  return (
    <>
      <ScreenHeader
        title={jar ? `Hũ ${jar.name}` : 'Chi tiết hũ'}
        backTo="/jars"
        right={jar && !isSystem ? <JarStatusChip jar={{ ...jar, status }} /> : undefined}
      />

      {detail.status === 'loading' && (
        <div role="status" aria-busy="true" aria-label="Đang tải hũ" data-state="loading" className="space-y-3 px-4">
          <Skeleton className="h-[170px] w-full rounded-card" />
          <Skeleton className="h-[420px] w-full rounded-card" />
        </div>
      )}
      {detail.status === 'error' && !detail.data && <ErrorState className="px-4" error={detail.error} title="Chưa tải được hũ" onRetry={() => void detail.reload()} />}

      {jar && (
        <div className="space-y-3 px-4">
          <section className="flex items-center gap-4 rounded-card bg-surface p-4 shadow-card" aria-label="Số dư hũ">
            <div className="w-[148px] shrink-0">
              <JarGlass colorKey={jar.color_key} level={level} forecastLevel={forecastLevel} label={`Hũ ${jar.name}, số dư ${formatVnd(jar.balance_vnd)}`} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-small text-ink-2">Số dư hôm nay</p>
              <p className="num text-title font-extrabold text-ink" data-testid="jar-balance">
                {formatVnd(jar.balance_vnd)}
              </p>
              {jar.system_role === 'unclassified' && jar.balance_vnd < 0 && (
                <p className="mt-1 text-small text-warn-fg">Đã chi {formatVnd(Math.abs(jar.balance_vnd))} mà chưa xếp vào hũ nào.</p>
              )}
              {jar.system_role === 'other_income' && <p className="mt-1 text-small text-ink-2">Tiền vào chưa gán hũ, không tính là thu nhập.</p>}
              {(status === 'short' || status === 'tight') && (
                <Button
                  type="button"
                  variant="soft"
                  size="sm"
                  className="mt-2"
                  onClick={() => launcher.open(`Vì sao hũ ${jar.name} ${status === 'short' ? 'sắp cạn' : 'đang sát'}?`)}
                >
                  Vì sao hũ này {status === 'short' ? 'cạn' : 'sát'}?
                </Button>
              )}
            </div>
          </section>

          {!isSystem && forecast.status === 'loading' && <Skeleton className="h-[420px] w-full rounded-card" role="status" aria-label="Đang tải dự báo" />}
          {!isSystem && forecast.status === 'error' && (
            <div data-testid="forecast-error">
              <ErrorState error={forecast.error} title="Chưa có dự báo cho hũ này" onRetry={() => void forecast.reload()} />
            </div>
          )}
          {!isSystem && forecast.data && (
            <>
              {forecastPending(forecast.data.data.computed_at) && (
                <p role="status" data-testid="forecast-recomputing" className="rounded-2xl bg-tint px-3 py-2 text-small font-medium text-brand-text">
                  Đang tính lại dự báo theo giao dịch mới, vài giây nữa là xong.
                </p>
              )}
              <ForecastBlock data={forecast.data.data} onAskWhy={() => launcher.open(`Vì sao dự báo hũ ${jar.name} ra như vậy?`)} />
            </>
          )}
          {isSystem && (
            <Notice kind="out_of_scope" title="Hũ hệ thống không có dự báo" message="Dự báo 30 ngày chỉ tính cho các hũ chi tiêu của bạn." />
          )}

          {detail.data && detail.data.obligations.length > 0 && (
            <section className="rounded-card bg-surface p-4 shadow-card" aria-label="Nghĩa vụ trả từ hũ này">
              <h2 className="text-subtitle font-semibold text-ink">Nghĩa vụ trả từ hũ này</h2>
              <ul className="mt-2 divide-y divide-line">
                {detail.data.obligations.map((o) => (
                  <li key={o.id} className="flex min-h-12 items-center justify-between gap-3 py-2">
                    <span className="min-w-0 truncate text-body text-ink">
                      {o.name} <span className="text-small text-ink-2">· {formatDayMonth(o.due_date)}</span>
                    </span>
                    <span className="num shrink-0 font-bold text-ink">{formatVnd(o.amount_vnd)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section aria-label="Giao dịch gần đây">
            <div className="flex items-center justify-between pb-2">
              <h2 className="text-section font-bold text-ink">Giao dịch gần đây</h2>
              <Link to={`/activity?jar=${jar.code}`} className="flex min-h-11 items-center text-small font-semibold text-brand-text">
                Xem tất cả
              </Link>
            </div>
            {detail.data && detail.data.recent_transactions.length === 0 ? (
              <EmptyState title="Chưa có giao dịch" message="Hũ này chưa có giao dịch nào." />
            ) : (
              <ul className="divide-y divide-line rounded-card bg-surface px-4 shadow-card" data-testid="jar-transactions">
                {detail.data?.recent_transactions.map((t) => (
                  <li key={t.id}>
                    <TxRow tx={t} jar={t.jar ? lookup.get(t.jar) : undefined} creditLabel={ov.data?.credit_line?.product_label} />
                  </li>
                ))}
              </ul>
            )}
          </section>

          {!isSystem && (
            <section className="rounded-card bg-surface p-4 shadow-card" aria-label="Luật chia và mục tiêu">
              <h2 className="text-subtitle font-semibold text-ink">Luật chia và mục tiêu</h2>
              <dl className="mt-2 space-y-1.5 text-small">
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-2">Chia từ lương</dt>
                  <dd className="num font-semibold text-ink">{formatPercent(jar.split_percent)}</dd>
                </div>
                {jar.goal_vnd && (
                  <div className="flex justify-between gap-3">
                    <dt className="text-ink-2">Mục tiêu</dt>
                    <dd className="num font-semibold text-ink">
                      {formatVnd(jar.goal_vnd)}
                      {jar.goal_date ? ` · ${formatAppDate(jar.goal_date)}` : ''}
                    </dd>
                  </div>
                )}
                {payday && (
                  <div className="flex justify-between gap-3">
                    <dt className="text-ink-2">Kỳ lương kế tiếp</dt>
                    <dd className="num font-semibold text-ink">
                      {formatDayMonth(payday.date)} · còn {payday.days_until} ngày
                    </dd>
                  </div>
                )}
              </dl>
            </section>
          )}

          <div className="flex flex-col gap-3 pt-1">
            {jar.system_role === 'other_income' ? (
              <Link to="/move?from=tien_vao_khac" className="inline-flex h-12 items-center justify-center rounded-full bg-primary px-6 text-subtitle font-bold text-primary-foreground">
                Gán vào hũ
              </Link>
            ) : (
              !isSystem && (
                <Link to={`/move?to=${jar.code}`} className="inline-flex h-12 items-center justify-center rounded-full bg-primary px-6 text-subtitle font-bold text-primary-foreground">
                  Chuyển tiền vào hũ này
                </Link>
              )
            )}
            <Button type="button" variant="outline" onClick={() => launcher.open(`Cho mình biết tình hình hũ ${jar.name}.`)}>
              Hỏi Yofina về hũ này
            </Button>
          </div>
        </div>
      )}
      {jar && <SimNote />}
    </>
  )
}
