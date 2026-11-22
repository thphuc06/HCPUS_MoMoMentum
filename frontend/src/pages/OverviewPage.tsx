import { useState, type ReactNode } from 'react'
import { Link, Navigate } from 'react-router'
import { ArrowDownToLine, ArrowLeftRight, ChevronRight, ListChecks, Send, ShieldCheck } from 'lucide-react'
import { BalanceCard } from '@/components/BalanceCard'
import { JarCard } from '@/components/JarCard'
import { MiniTimeline } from '@/components/MiniTimeline'
import { Notice } from '@/components/Notice'
import { ProactiveCard } from '@/components/ProactiveCard'
import { TxRow } from '@/components/TxRow'
import { ErrorState } from '@/components/StateViews'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/auth/AuthProvider'
import { useOverview } from '@/api/OverviewProvider'
import { parseProactiveCard, type OverviewResponse } from '@/api/schemas'
import { useProactiveActions } from '@/features/overview/useProactiveActions'
import { useJarLookup } from '@/features/common/useJarLookup'
import { formatDayMonth } from '@/lib/dates'
import { formatRatioPercent, formatVnd, greetingNow } from '@/lib/format'
import { jarForecastLevel, jarLevel } from '@/lib/jar'
import { isCardHidden, nudgeKey } from '@/lib/nudgePrefs'
import { displayName } from '@/lib/user'

function Header({ name }: { name: string }) {
  return (
    <header className="flex items-center gap-3 px-4 pt-[max(16px,env(safe-area-inset-top))] pb-4">
      <span aria-hidden className="grid size-12 place-items-center rounded-full bg-brand text-subtitle font-bold text-white">
        {name.charAt(0).toUpperCase()}
      </span>
      <div className="min-w-0">
        <p className="text-small text-ink-2">{greetingNow()}</p>
        <h1 className="truncate text-section font-bold text-ink">{name}</h1>
      </div>
    </header>
  )
}

function QuickAction({ label, Icon, to, disabledNote }: { label: string; Icon: typeof Send; to?: string; disabledNote?: string }) {
  const body = (
    <>
      <span className="grid size-12 place-items-center rounded-full bg-white/20 group-active:bg-white/30">
        <Icon className="size-6" aria-hidden />
      </span>
      <span className="text-center text-small leading-tight font-semibold">{label}</span>
      {disabledNote && <span className="text-note font-medium text-white/80">{disabledNote}</span>}
    </>
  )
  if (!to || disabledNote) {
    return (
      <button type="button" disabled aria-disabled="true" title={disabledNote} className="group flex min-h-[88px] flex-1 flex-col items-center gap-1 text-white opacity-60">
        {body}
      </button>
    )
  }
  return (
    <Link to={to} className="group flex min-h-[88px] flex-1 flex-col items-center gap-1 text-white">
      {body}
    </Link>
  )
}

function QuickActions() {
  return (
    <nav aria-label="Hành động nhanh" className="mt-4 flex gap-1">
      <QuickAction label="Chuyển tiền" Icon={Send} to="/transfer" />
      <QuickAction label="Tiền vào" Icon={ArrowDownToLine} to="/income" />
      <QuickAction label="Giữa hũ" Icon={ArrowLeftRight} to="/move" />
      <QuickAction label="Kiểm tra" Icon={ShieldCheck} to="/check" disabledNote="Sắp có" />
    </nav>
  )
}

function SectionTitle({ children, to, linkLabel }: { children: ReactNode; to?: string; linkLabel?: string }) {
  return (
    <div className="flex items-center justify-between px-4 pt-6 pb-2">
      <h2 className="text-section font-bold text-ink">{children}</h2>
      {to && (
        <Link to={to} className="flex min-h-11 items-center text-small font-semibold text-brand-text">
          {linkLabel ?? 'Xem tất cả'}
        </Link>
      )}
    </div>
  )
}

function LinkCard({ to, title, subtitle, icon }: { to: string; title: string; subtitle?: string; icon: ReactNode }) {
  return (
    <Link to={to} className="mx-4 mt-3 flex min-h-16 items-center gap-3 rounded-card bg-surface p-4 shadow-card">
      <span className="grid size-11 shrink-0 place-items-center rounded-full bg-warn-bg text-warn-fg">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-subtitle font-semibold text-ink">{title}</span>
        {subtitle && <span className="block text-small text-ink-2">{subtitle}</span>}
      </span>
      <ChevronRight className="size-5 shrink-0 text-ink-2" aria-hidden />
    </Link>
  )
}

function ProactiveSection({ data }: { data: OverviewResponse }) {
  const [, force] = useState(0)
  const card = parseProactiveCard(data.proactive_card)
  const hide = () => force((n) => n + 1)
  // Hook luôn được gọi (kể cả khi chưa có thẻ) để đúng quy tắc hooks.
  const fallback = card?.data ?? { kind: 'low_data' as const, status: 'ok' as const, title: '-', reason: '-', actions: [{ kind: 'snooze' as const, label: '-' }] }
  const onAction = useProactiveActions(fallback, data.app_date, hide)
  if (!card) return null
  const d = card.data
  if (isCardHidden(nudgeKey(d.kind, d.jar_code), d.kind, data.app_date)) return null
  const jar = d.jar_code ? data.jars.find((j) => j.code === d.jar_code) : undefined
  return (
    <div className="mx-4 mt-4">
      <ProactiveCard data={d} onAction={onAction}>
        {d.kind === 'runout_warning' && data.next_payday && jar?.runout_date && (
          <MiniTimeline today={data.app_date} paydayDate={data.next_payday.date} runoutDate={jar.runout_date} />
        )}
      </ProactiveCard>
    </div>
  )
}

function ForecastNotes({ data }: { data: OverviewResponse }) {
  if (data.jars.length === 0) return null
  if (!data.forecast) {
    return (
      <div className="mx-4 mt-3">
        <Notice kind="low_data" title="Chưa có dự báo" message="Hệ thống chưa tính dự báo cho các hũ. Số dư bên dưới là số thật; ngày cạn và trạng thái đủ/sát/hụt sẽ hiện khi có dự báo." />
      </div>
    )
  }
  const f = data.forecast
  if (!f.is_initial_estimate && !f.stale) return null
  return (
    <div className="mx-4 mt-3">
      <Notice
        kind="degraded"
        title={f.is_initial_estimate ? 'Dự báo mới là ước lượng ban đầu' : 'Số liệu dự báo đã cũ'}
        message={
          f.is_initial_estimate
            ? `Mới có ${f.history_days} ngày dữ liệu${f.coverage !== undefined ? `, độ phủ ${formatRatioPercent(f.coverage)}` : ''}. Càng ghi nhiều giao dịch, dự báo càng sát.`
            : 'Dự báo chưa được cập nhật theo ngày mô phỏng hôm nay. Mở chi tiết một hũ để tính lại.'
        }
      />
    </div>
  )
}

function LoadingState() {
  return (
    <div aria-busy="true" aria-label="Đang tải số dư" role="status" data-testid="overview-skeleton">
      <div className="px-4">
        <Skeleton className="h-[260px] w-full rounded-sheet" />
      </div>
      <Skeleton className="mx-4 mt-4 h-[150px] w-[calc(100%-32px)] rounded-card" />
      <Skeleton className="mx-4 mt-6 h-6 w-32 rounded-lg" />
      <div className="mt-3 flex gap-3 overflow-hidden px-4">
        <Skeleton className="h-[298px] w-[180px] shrink-0 rounded-card" />
        <Skeleton className="h-[298px] w-[180px] shrink-0 rounded-card" />
      </div>
    </div>
  )
}

export function OverviewPage() {
  const ov = useOverview()
  const { session } = useAuth()
  const lookup = useJarLookup()
  const data = ov.data
  const name = data?.profile.display_name ?? displayName(session?.email, session?.displayName) ?? 'bạn'

  if (data && !data.profile.onboarded) return <Navigate to="/onboarding" replace />

  const max = data ? Math.max(0, ...data.jars.map((j) => j.balance_vnd)) : 0
  return (
    <>
      <Header name={name} />
      {ov.status === 'loading' && <LoadingState />}
      {ov.status === 'error' && (
        <ErrorState className="px-4" error={ov.error} title="Chưa tải được tổng quan" onRetry={() => void ov.reload()} />
      )}

      {data && (
        <>
          <div className="px-4">
            <BalanceCard balance={data.balance} appDate={data.app_date}>
              <QuickActions />
            </BalanceCard>
          </div>

          {data.next_payday?.state === 'pending_confirmation' && parseProactiveCard(data.proactive_card)?.data.kind !== 'salary_pending' && (
            <LinkCard
              to="/salary"
              title="Lương về, chờ bạn xác nhận"
              subtitle="Một chạm để chia vào các hũ"
              icon={<ListChecks className="size-5" aria-hidden />}
            />
          )}
          <ProactiveSection data={data} />
          <ForecastNotes data={data} />

          <SectionTitle to="/jars">Hũ của bạn</SectionTitle>
          {data.jars.length === 0 ? (
            <p className="px-4 text-small text-ink-2">Chưa có hũ nào trong tài khoản này.</p>
          ) : (
            <ul className="flex snap-x gap-3 overflow-x-auto scroll-px-4 px-4 pt-1 pb-4 [scrollbar-width:none]" aria-label="Danh sách hũ">
              {data.jars.map((j) => (
                <li key={j.code} className="shrink-0">
                  <Link to={`/jars/${j.code}`} className="block text-left" aria-label={`Mở hũ ${j.name}`}>
                    <JarCard jar={j} level={jarLevel(j, max)} forecastLevel={jarForecastLevel(j, max)} />
                  </Link>
                </li>
              ))}
            </ul>
          )}

          {data.needs_review_count > 0 && (
            <LinkCard
              to="/activity?review=1"
              title={`Cần xem lại (${data.needs_review_count})`}
              subtitle={`${data.needs_review_count} giao dịch cần bạn xem lại hũ`}
              icon={<ListChecks className="size-5" aria-hidden />}
            />
          )}

          {data.obligations_due.length > 0 && (
            <>
              <SectionTitle to="/obligations">Nghĩa vụ sắp đến hạn</SectionTitle>
              <ul className="mx-4 divide-y divide-line rounded-card bg-surface px-4 shadow-card" data-testid="obligations-due">
                {data.obligations_due.map((o) => (
                  <li key={o.id} className="flex min-h-14 items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <p className="truncate text-body font-semibold text-ink">{o.name}</p>
                      <p className="text-small text-ink-2">Đến hạn {formatDayMonth(o.due_date)}</p>
                    </div>
                    <span className="num shrink-0 text-body font-bold text-ink">{formatVnd(o.amount_vnd)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          <SectionTitle to="/activity">Gần đây</SectionTitle>
          {data.recent_transactions.length === 0 ? (
            <p className="mx-4 rounded-card bg-surface p-4 text-small text-ink-2 shadow-card">Chưa có giao dịch nào.</p>
          ) : (
            <ul className="mx-4 divide-y divide-line rounded-card bg-surface px-4 shadow-card" data-testid="recent-transactions">
              {data.recent_transactions.map((t) => (
                <li key={t.id}>
                  <TxRow tx={t} jar={t.jar ? lookup.get(t.jar) : undefined} creditLabel={data.credit_line?.product_label} />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </>
  )
}
