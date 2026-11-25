import { useCallback, useState, type ReactNode } from 'react'
import { Link, Navigate } from 'react-router'
import { ArrowDownToLine, ArrowLeftRight, Send } from 'lucide-react'
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
import { JarCarousel } from '@/features/overview/JarCarousel'
import { emptyDaysBeforePayday, RunoutHero } from '@/features/overview/RunoutHero'
import { creditTodo, reviewTodo, roadmapTodo, salaryTodo, TodoList } from '@/features/overview/TodoList'
import { useProactiveActions, type ProactiveAction } from '@/features/overview/useProactiveActions'
import { useTodayNudge } from '@/features/overview/useTodayNudge'
import { useRoadmapVersions } from '@/features/roadmap/useRoadmapVersions'
import { useJarLookup } from '@/features/common/useJarLookup'
import { DailyAskCard } from '@/features/review/DailyAskCard'
import { useReview } from '@/features/review/useReview'
import { formatDayMonth } from '@/lib/dates'
import { formatRatioPercent, formatVnd, greetingNow } from '@/lib/format'
import { mayRunOutBeforePayday, shownRunoutDate } from '@/lib/jar'
import { useAnimateOnce } from '@/lib/motion'
import { isCardHidden, nudgeKey } from '@/lib/nudgePrefs'
import { displayName } from '@/lib/user'

/** Nghĩa vụ sắp đến hạn ở Tổng quan: tối đa 3 dòng, danh sách đầy đủ ở màn Nghĩa vụ ("Xem tất cả"). */
const DUE_ROWS = 3

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
  const warn = d.kind === 'runout_warning' && jar !== undefined
  const runoutDate = warn ? shownRunoutDate(jar) : undefined
  const runout = data.next_payday && runoutDate ? { payday: data.next_payday.date, date: runoutDate } : null
  const emptyDays = runout ? emptyDaysBeforePayday(runout.date, runout.payday, data.app_date) : null
  // Hũ thưa (#25): không có ngày cạn nên không có số ngày hay dải ngày; còn khả năng hụt thì một dòng ngắn kèm %.
  const chance = warn && mayRunOutBeforePayday(jar) ? jar.p_shortfall : undefined
  const hero = emptyDays !== null ? <RunoutHero days={emptyDays} animate={animate} /> : chance !== undefined ? <RunoutHero chance={chance} animate={animate} /> : undefined
  return (
    <div className="mx-4 mt-4">
      <ProactiveCard data={d} onAction={onAction} hero={hero}>
        {runout && <MiniTimeline today={data.app_date} paydayDate={runout.payday} runoutDate={runout.date} animate={animate} />}
      </ProactiveCard>
      {footer}
    </div>
  )
}

/** Thẻ tất định của `GET /overview` (phase 2): "Để sau" và "Ít nhắc loại này" chỉ lưu phía giao diện. */
function OverviewCardSection({ data, card, onHide }: { data: OverviewResponse; card: ProactiveCardBlock | null; onHide: () => void }) {
  // Hook luôn được gọi (kể cả khi chưa có thẻ) để đúng quy tắc hooks.
  const fallback = card?.data ?? { kind: 'low_data' as const, status: 'ok' as const, title: '-', reason: '-', actions: [{ kind: 'snooze' as const, label: '-' }] }
  const onAction = useProactiveActions(fallback, data.app_date, onHide)
  if (!card) return null
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
 * "Việc cần làm" của hôm nay (ui-design-review.md §10). Thẻ chính là MỘT việc: có bản tin của cổng giá trị thì ưu tiên nó (hợp đồng
 * `GET /nudges/today`); người dùng đã gạt bản tin đi thì không hiện thẻ nào; chưa có bản tin (hoặc chưa tải xong, hoặc lỗi) thì dùng
 * thẻ tất định của `GET /overview`. Dưới thẻ là các dòng việc khác (lương chờ xác nhận, giao dịch chờ xếp hũ, Trả sau chưa đủ trả, lộ
 * trình có việc) và câu hỏi gộp chọn hũ của hôm nay; loại nào đã là thẻ chính thì không lặp thành dòng.
 */
function TodaySection({ data }: { data: OverviewResponse }) {
  const nudge = useTodayNudge()
  const review = useReview('daily_ask')
  const versions = useRoadmapVersions()
  const [, force] = useState(0)
  const [askSkipped, setAskSkipped] = useState(false)
  const hide = useCallback(() => force((n) => n + 1), [])

  const overviewCard = parseProactiveCard(data.proactive_card)
  const showNudge = nudge.state === 'show' && !!nudge.card
  const fallbackCard =
    nudge.state !== 'hidden' && !showNudge && overviewCard && !isCardHidden(nudgeKey(overviewCard.data.kind, overviewCard.data.jar_code), overviewCard.data.kind, data.app_date)
      ? overviewCard
      : null
  const main = showNudge ? nudge.card!.data.kind : fallbackCard?.data.kind ?? null

  const daily = review.status === 'ready' ? review.data.data : undefined
  const askShown = !!daily && daily.ask?.status === 'open' && daily.count > 0 && !askSkipped
  return (
    <>
      {showNudge ? (
        <NudgeCardSection card={nudge.card!} appDate={nudge.appDate ?? data.app_date} data={data} nudge={nudge} />
      ) : (
        <OverviewCardSection data={data} card={fallbackCard} onHide={hide} />
      )}
      <TodoList
        items={[
          salaryTodo(data, main),
          reviewTodo(data.needs_review_count, daily, askShown, main),
          creditTodo(data, main),
          roadmapTodo(versions.data ?? undefined, main),
        ]}
      />
      {askShown && (
        <div className="mx-4 mt-3">
          <DailyAskCard data={daily} refreshing={review.status === 'ready' && review.refreshing} onSkipped={() => setAskSkipped(true)} />
        </div>
      )}
    </>
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

  return (
    <>
      <Header name={name} />
      {ov.status === 'loading' && <LoadingState />}
      {ov.status === 'error' && (
        <ErrorState className="px-4" error={ov.error} title="Chưa tải được tổng quan" onRetry={() => void ov.reload()} />
      )}

      {/* Tổng quan là "hôm nay" (ui-design-review.md §10): số dư, việc cần làm, hũ, nghĩa vụ sắp đến hạn, giao dịch gần đây. Dự báo
          nhiều hũ (B2) và lộ trình ở Nhìn trước; Trả sau đầy đủ (B6) ở Nghĩa vụ; chỉ thành một dòng "Việc cần làm" khi cần làm gì. */}
      {data && (
        <>
          <div className="px-4">
            <BalanceCard balance={data.balance} appDate={data.app_date} jarsCount={data.jars.length}>
              <QuickActions />
            </BalanceCard>
          </div>

          <TodaySection data={data} />
          <ForecastNotes data={data} />

          <SectionTitle to="/jars">Hũ của bạn</SectionTitle>
          {data.jars.length === 0 ? (
            <p className="px-4 text-small text-ink-2">Chưa có hũ nào trong tài khoản này.</p>
          ) : (
            <JarCarousel jars={data.jars} />
          )}

          {data.obligations_due.length > 0 && (
            <>
              <SectionTitle to="/obligations">Nghĩa vụ sắp đến hạn</SectionTitle>
              <ul className="mx-4 divide-y divide-line rounded-card bg-surface px-4 shadow-card" data-testid="obligations-due">
                {data.obligations_due.slice(0, DUE_ROWS).map((o) => (
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
