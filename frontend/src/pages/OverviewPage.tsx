import { RotateCw } from 'lucide-react'
import { BalanceCard } from '@/components/BalanceCard'
import { JarCard } from '@/components/JarCard'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/auth/AuthProvider'
import { useJars } from '@/api/ApiProvider'
import { greetingNow } from '@/lib/format'
import { displayName } from '@/lib/user'
import type { JarsResponse } from '@/api/schemas'

function Header() {
  const { session } = useAuth()
  const name = displayName(session?.email, session?.displayName) ?? 'bạn'
  return (
    <header className="flex items-center gap-3 px-4 pt-[max(16px,env(safe-area-inset-top))] pb-4">
      <span
        aria-hidden
        className="grid size-12 place-items-center rounded-full bg-brand text-subtitle font-bold text-white"
      >
        {name.charAt(0).toUpperCase()}
      </span>
      <div className="min-w-0">
        <p className="text-small text-ink-2">{greetingNow()}</p>
        <h1 className="truncate text-section font-bold text-ink">{name}</h1>
      </div>
    </header>
  )
}

function JarStrip({ data }: { data: JarsResponse }) {
  const max = Math.max(0, ...data.jars.map((j) => j.balance_vnd))
  if (data.jars.length === 0) {
    return <p className="px-4 text-small text-ink-2">Chưa có hũ nào trong tài khoản này.</p>
  }
  return (
    <ul className="flex snap-x gap-3 overflow-x-auto scroll-px-4 px-4 pt-1 pb-4 [scrollbar-width:none]" aria-label="Danh sách hũ">
      {data.jars.map((j) => (
        <li key={j.code} className="shrink-0">
          <JarCard jar={j} level={j.balance_vnd === 0 || max === 0 ? 0 : Math.max(0.08, j.balance_vnd / max)} />
        </li>
      ))}
    </ul>
  )
}

function LoadingState() {
  return (
    <div aria-busy="true" aria-label="Đang tải số dư" role="status" data-testid="overview-skeleton">
      <div className="px-4">
        <Skeleton className="h-[148px] w-full rounded-sheet" />
      </div>
      <Skeleton className="mx-4 mt-6 h-6 w-32 rounded-lg" />
      <div className="mt-3 flex gap-3 overflow-hidden px-4">
        <Skeleton className="h-[298px] w-[180px] shrink-0 rounded-card" />
        <Skeleton className="h-[298px] w-[180px] shrink-0 rounded-card" />
      </div>
    </div>
  )
}

export function OverviewPage() {
  const { state, reload } = useJars()
  return (
    <>
      <Header />
      {state.status === 'loading' && <LoadingState />}

      {state.status === 'error' && (
        <div className="px-4" role="alert">
          <div className="rounded-card bg-bad-bg p-4 text-bad-fg">
            <p className="text-subtitle font-semibold">Chưa tải được số dư</p>
            <p className="mt-1 text-small text-ink">{state.error.message}</p>
            <Button type="button" variant="soft" size="sm" className="mt-3 bg-surface" onClick={() => void reload()}>
              <RotateCw className="size-4" aria-hidden />
              Thử lại
            </Button>
          </div>
        </div>
      )}

      {state.data && (
        <>
          <div className="px-4">
            <BalanceCard totalVnd={state.data.jars_total_vnd} appDate={state.data.app_date} />
          </div>
          <h2 className="px-4 pt-6 pb-2 text-section font-bold text-ink">Hũ của bạn</h2>
          <JarStrip data={state.data} />
        </>
      )}
    </>
  )
}
