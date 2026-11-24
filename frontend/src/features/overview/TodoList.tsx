import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { ChevronRight, CreditCard, ListChecks, Route, Wallet } from 'lucide-react'
import type { OverviewResponse } from '@/api/schemas'
import type { RoadmapVersionsResponse } from '@/api/roadmapSchemas'
import type { ProactiveCardData, ReviewListData } from '@/contracts/blocks'
import { nearestBnpl, payJarFor } from '@/features/credit/select'
import { ROADMAP_PATH, summarizeRoadmap } from '@/features/roadmap/RoadmapEntry'
import { cn } from '@/lib/cn'
import { formatDayMonth } from '@/lib/dates'
import { formatVnd } from '@/lib/format'

// "Việc cần làm" của Tổng quan ngoài thẻ chính (ui-design-review.md §10 "Mỗi thông tin một nhà"): mỗi loại thông tin có nhà ở màn
// khác (Lộ trình ở Nhìn trước, Trả sau ở Nghĩa vụ, giao dịch chờ xếp hũ ở Xem lại); Tổng quan chỉ có MỘT dòng có liên kết khi người
// dùng cần làm gì đó, không có việc thì không có dòng. Loại đã là thẻ chính hôm nay thì không lặp thành dòng.

type MainKind = ProactiveCardData['kind'] | null

export type TodoItem = {
  key: 'salary' | 'review' | 'credit' | 'roadmap'
  to: string
  title: string
  subtitle?: string
  tone: 'warn' | 'bad' | 'info'
  icon: ReactNode
}

const TONE: Record<TodoItem['tone'], string> = {
  warn: 'bg-warn-bg text-warn-fg',
  bad: 'bg-bad-bg text-bad-fg',
  info: 'bg-tint text-brand-text',
}

const icon = (I: typeof Wallet) => <I className="size-5" aria-hidden />

/** Lương về chờ xác nhận (một chạm chia vào hũ). */
export function salaryTodo(data: OverviewResponse, main: MainKind): TodoItem | null {
  if (data.next_payday?.state !== 'pending_confirmation' || main === 'salary_pending') return null
  return { key: 'salary', to: '/salary', title: 'Lương về, chờ bạn xác nhận', subtitle: 'Một chạm để chia vào các hũ', tone: 'warn', icon: icon(Wallet) }
}

/**
 * Giao dịch chờ xếp hũ: hai hàng chờ khác bản chất (đọc `app_get_review_list`, migration 0052) nhưng cùng một việc và cùng màn Xem lại.
 * `needs_review_count` của `/overview` là tổng của cả hai: giao dịch đang ở hũ Chưa phân loại (hỏi gộp `daily_ask`, có tổng tiền) và
 * giao dịch Yofina đã tự xếp ở mức tin cậy vừa (`review`). Câu hỏi gộp của hôm nay đang hiện ngay trên Tổng quan (`askShown`) thì
 * dòng chỉ còn phần "cần xem lại".
 */
export function reviewTodo(needsReviewCount: number, daily: ReviewListData | undefined, askShown: boolean, main: MainKind): TodoItem | null {
  if (main === 'review_needed') return null
  const base = { key: 'review' as const, to: '/review', tone: 'warn' as const, icon: icon(ListChecks) }
  if (!daily) return needsReviewCount > 0 ? { ...base, title: `${needsReviewCount} giao dịch cần xem lại hũ` } : null
  const unclassified = daily.count
  const review = Math.max(0, needsReviewCount - unclassified)
  const reviewOnly = { ...base, title: `Xem lại ${review} giao dịch`, subtitle: 'Yofina đã tự xếp hũ, bạn kiểm giúp' }
  if (askShown || unclassified === 0) return review > 0 ? reviewOnly : null
  const money = formatVnd(daily.pending_total_vnd)
  if (review === 0) return { ...base, title: `${unclassified} giao dịch chưa xếp hũ`, subtitle: money }
  return { ...base, title: `Xếp hũ cho ${unclassified + review} giao dịch`, subtitle: `${unclassified} chưa xếp hũ · ${money}; ${review} cần xem lại` }
}

/** Hũ trả khoản Trả sau đến hạn gần nhất đang có ít hơn số phải trả. Đủ trả thì không có việc (B6 đầy đủ ở màn Nghĩa vụ). */
export function creditTodo(data: OverviewResponse, main: MainKind): TodoItem | null {
  const due = nearestBnpl(data.obligations_due)
  const jar = payJarFor(due, data.jars)
  if (!due || !jar || jar.balance_vnd >= due.amount_vnd) return null
  if (main === 'obligation_due') return null
  return {
    key: 'credit',
    to: '/obligations',
    title: `Hũ ${jar.name} chưa đủ trả ${due.name}`,
    subtitle: `Đến hạn ${formatDayMonth(due.due_date)} · hũ đang có ${formatVnd(jar.balance_vnd)}`,
    tone: 'bad',
    icon: icon(CreditCard),
  }
}

/** Lộ trình có việc: phiên bản mới chờ chọn, hoặc bản đang dùng còn bước chờ bạn quyết. Không có lộ trình thì không có dòng. */
export function roadmapTodo(versions: RoadmapVersionsResponse | undefined, main: MainKind): TodoItem | null {
  if (!versions || main === 'roadmap_proposed') return null
  const s = summarizeRoadmap(versions)
  if (!s) return null
  const base = { key: 'roadmap' as const, to: ROADMAP_PATH, tone: 'info' as const, icon: icon(Route) }
  if (s.hasProposed) return { ...base, title: 'Lộ trình mới chờ bạn chọn', subtitle: `Phiên bản ${versions.proposed_version}` }
  if (s.pending > 0) return { ...base, title: `Lộ trình: ${s.pending} bước chờ bạn`, subtitle: `Phiên bản ${s.version}` }
  return null
}

export function TodoList({ items }: { items: Array<TodoItem | null> }) {
  const shown = items.filter((i): i is TodoItem => i !== null)
  if (shown.length === 0) return null
  return (
    <ul aria-label="Việc cần làm khác" data-testid="todo-list" className="mx-4 mt-3 divide-y divide-line rounded-card bg-surface px-4 shadow-card">
      {shown.map((i) => (
        <li key={i.key} data-todo={i.key}>
          <Link to={i.to} className="flex min-h-16 items-center gap-3 py-3">
            <span className={cn('grid size-10 shrink-0 place-items-center rounded-full', TONE[i.tone])}>{i.icon}</span>
            <span className="min-w-0 flex-1">
              <span className="block text-body font-semibold text-ink">{i.title}</span>{' '}
              {i.subtitle && <span className="num block text-small text-ink-2">{i.subtitle}</span>}
            </span>
            <ChevronRight className="size-5 shrink-0 text-ink-2" aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  )
}
