import { useCallback, useState, type ReactNode } from 'react'
import { Link, Navigate } from 'react-router'
import { ArrowDownToLine, ArrowLeftRight, ChevronRight, ListChecks, Send } from 'lucide-react'
import { BalanceCard } from '@/components/BalanceCard'
import { MiniTimeline } from '@/components/MiniTimeline'
import { Notice } from '@/components/Notice'
import { ProactiveCard } from '@/components/ProactiveCard'
import { TxRow } from '@/components/TxRow'
import { ErrorState } from '@/components/StateViews'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/auth/AuthProvider'
import { useOverview } from '@/api/OverviewProvider'
import { parseProactiveCard, type OverviewResponse } from '@/api/schemas'
import type { NudgeOutcome } from '@/api/phase5Schemas'
import type { ProactiveCardBlock } from '@/contracts/blocks'
import { CreditUsage } from '@/features/credit/CreditUsage'
import { nearestBnpl, payJarFor } from '@/features/credit/select'
import { JarCarousel } from '@/features/overview/JarCarousel'
import { JarRunway } from '@/features/overview/JarRunway'
import { emptyDaysBeforePayday, RunoutHero } from '@/features/overview/RunoutHero'
import { useProactiveActions, type ProactiveAction } from '@/features/overview/useProactiveActions'
import { useTodayNudge } from '@/features/overview/useTodayNudge'
import { RoadmapEntryRow } from '@/features/roadmap/RoadmapEntry'
import { useJarLookup } from '@/features/common/useJarLookup'
import { DailyAskCard } from '@/features/review/DailyAskCard'
import { UnclassifiedSummary } from '@/features/review/UnclassifiedSummary'
import { useReview } from '@/features/review/useReview'
import { formatDayMonth } from '@/lib/dates'
import { formatRatioPercent, formatVnd, greetingNow } from '@/lib/format'
import { useAnimateOnce } from '@/lib/motion'
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

function QuickAction({ label, Icon, to }: { label: string; Icon: typeof Send; to: string }) {
  return (
    <Link to={to} className="group flex min-h-[88px] flex-1 flex-col items-center gap-1 text-white">
      <span className="grid size-12 place-items-center rounded-full bg-white/20 group-active:bg-white/30">
        <Icon className="size-6" aria-hidden />
      </span>
      <span className="text-center text-small leading-tight font-semibold">{label}</span>
    </Link>
  )
}

// Ba lối đi thật. Nút "Kiểm tra" (chưa có màn) đã bỏ: thứ trông như bấm được thì phải bấm được (ui-design-review.md §3.2 #3);
// kiểm tra trước khi chi vẫn có ở bước chuyển tiền và trong chat.
function QuickActions() {
  return (
    <nav aria-label="Hành động nhanh" className="mt-4 flex gap-1">
      <QuickAction label="Chuyển tiền" Icon={Send} to="/transfer" />
      <QuickAction label="Tiền vào" Icon={ArrowDownToLine} to="/income" />
      <QuickAction label="Giữa hũ" Icon={ArrowLeftRight} to="/move" />
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

function ProactiveCardFor({ card, data, onAction, footer }: {
  card: ProactiveCardBlock
  data: OverviewResponse
  onAction: (a: ProactiveAction) => void
  footer?: ReactNode
}) {
  const d = card.data
  const jar = d.jar_code ? data.jars.find((j) => j.code === d.jar_code) : undefined
  // Cảnh 1: thẻ cảnh báo cạn có số lớn "N ngày" hũ trống trước kỳ lương và dải ô ngày tới kỳ lương; chạy một lần mỗi phiên.
  const animate = useAnimateOnce('runout-strip')
  const runout = d.kind === 'runout_warning' && data.next_payday && jar?.runout_date ? { payday: data.next_payday.date, date: jar.runout_date } : null
  const emptyDays = runout ? emptyDaysBeforePayday(runout.date, runout.payday, data.app_date) : null
  return (
    <div className="mx-4 mt-4">
      <ProactiveCard data={d} onAction={onAction} hero={emptyDays !== null ? <RunoutHero days={emptyDays} animate={animate} /> : undefined}>
        {runout && <MiniTimeline today={data.app_date} paydayDate={runout.payday} runoutDate={runout.date} animate={animate} />}
      </ProactiveCard>
      {footer}
    </div>
  )
}

/** Thẻ tất định của `GET /overview` (phase 2): "Để sau" và "Ít nhắc loại này" chỉ lưu phía giao diện. */
function OverviewCardSection({ data }: { data: OverviewResponse }) {
  const [, force] = useState(0)
  const card = parseProactiveCard(data.proactive_card)
  const hide = () => force((n) => n + 1)
  // Hook luôn được gọi (kể cả khi chưa có thẻ) để đúng quy tắc hooks.
  const fallback = card?.data ?? { kind: 'low_data' as const, status: 'ok' as const, title: '-', reason: '-', actions: [{ kind: 'snooze' as const, label: '-' }] }
  const onAction = useProactiveActions(fallback, data.app_date, hide)
  if (!card) return null
  const d = card.data
  if (isCardHidden(nudgeKey(d.kind, d.jar_code), d.kind, data.app_date)) return null
  return <ProactiveCardFor card={card} data={data} onAction={onAction} />
}

/** Bản tin của cổng giá trị (`GET /nudges/today`): phản hồi gửi về server để cổng tôn trọng "Ít nhắc loại này" ở các ngày sau. */
function NudgeCardSection({ card, appDate, data, nudge }: { card: ProactiveCardBlock; appDate: string; data: OverviewResponse; nudge: ReturnType<typeof useTodayNudge> }) {
  const { feedback } = nudge
  const onFeedback = useCallback((outcome: NudgeOutcome) => void feedback(outcome), [feedback])
  const onAction = useProactiveActions(card.data, appDate, undefined, onFeedback)
  return (
    <ProactiveCardFor
      card={card}
      data={data}
      onAction={onAction}
      footer={nudge.error && (
        <p role="alert" className="mt-2 rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
          Chưa ghi được lựa chọn của bạn. {nudge.error.message}
        </p>
      )}
    />
  )
}

/**
 * MỘT việc cần làm hôm nay. Có bản tin của cổng giá trị thì ưu tiên nó (hợp đồng `GET /nudges/today`); người dùng đã gạt bản tin đi
 * thì không hiện thẻ nào; chưa có bản tin (hoặc chưa tải xong, hoặc lỗi) thì dùng thẻ tất định của `GET /overview`.
 */
function ProactiveSection({ data }: { data: OverviewResponse }) {
  const nudge = useTodayNudge()
  if (nudge.state === 'hidden') return null
  if (nudge.state === 'show' && nudge.card) return <NudgeCardSection card={nudge.card} appDate={nudge.appDate ?? data.app_date} data={data} nudge={nudge} />
  return <OverviewCardSection data={data} />
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

function PendingReviewSection() {
  const review = useReview('daily_ask')
  if (review.status !== 'ready') return null
  const { data } = review.data
  if (data.count === 0 && data.ask?.status !== 'open') return null

  return (
    <div className="mx-4 mt-3 space-y-3">
      <UnclassifiedSummary data={data} />
      <DailyAskCard data={data} refreshing={review.refreshing} />
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

  const bnplDue = data ? nearestBnpl(data.obligations_due) : undefined
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
          <PendingReviewSection />

          <SectionTitle to="/jars">Hũ của bạn</SectionTitle>
          {data.jars.length === 0 ? (
            <p className="px-4 text-small text-ink-2">Chưa có hũ nào trong tài khoản này.</p>
          ) : (
            <JarCarousel jars={data.jars} />
          )}

          <JarRunway
            jars={data.jars}
            appDate={data.app_date}
            nextPayday={data.next_payday}
            obligations={data.obligations_due}
            forecast={data.forecast}
          />

          <RoadmapEntryRow />

          {data.needs_review_count > 0 && (
            <LinkCard
              to="/review"
              title={`Cần xem lại (${data.needs_review_count})`}
              subtitle="Kiểm tra các hũ Yofina đã tự chọn"
              icon={<ListChecks className="size-5" aria-hidden />}
            />
          )}

          {data.credit_line && data.credit_line.outstanding_vnd > 0 && (
            <div className="mx-4 mt-3">
              <CreditUsage
                line={data.credit_line}
                due={bnplDue}
                payJar={payJarFor(bnplDue, data.jars)}
                to="/obligations"
                testId="credit-usage"
              />
            </div>
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
