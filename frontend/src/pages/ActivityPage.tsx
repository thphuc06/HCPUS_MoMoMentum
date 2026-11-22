import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { Button } from '@/components/ui/button'
import { ScreenHeader } from '@/components/ScreenHeader'
import { SimNote } from '@/components/SimNote'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/StateViews'
import { TxRow } from '@/components/TxRow'
import { useApi, useDataVersion } from '@/api/ApiProvider'
import { ApiError } from '@/api/errors'
import { useOverview } from '@/api/OverviewProvider'
import type { Transaction } from '@/api/schemas'
import { useJarLookup } from '@/features/common/useJarLookup'
import { cn } from '@/lib/cn'

const PAGE = 20

type Load = { status: 'loading' | 'ready' | 'error'; error: ApiError | null }

// Figma S3 Hoạt động (31:2830) là khung giữ chỗ; bản này là danh sách giao dịch thật: lọc theo hũ hoặc "Cần xem lại",
// phân trang bằng con trỏ (`next_cursor` của server, truyền lại nguyên văn), tải thêm khi cuộn tới cuối (hoặc bấm nút).
export function ActivityPage() {
  const api = useApi()
  const version = useDataVersion()
  const ov = useOverview()
  const lookup = useJarLookup()
  const [params, setParams] = useSearchParams()
  const jar = params.get('jar') ?? ''
  const review = params.get('review') === '1'

  const [items, setItems] = useState<Transaction[]>([])
  const [cursor, setCursor] = useState<string | undefined>()
  const [load, setLoad] = useState<Load>({ status: 'loading', error: null })
  const [more, setMore] = useState<'idle' | 'loading' | 'error'>('idle')
  const seq = useRef(0)
  const sentinel = useRef<HTMLDivElement>(null)

  const fetchFirst = useCallback(async () => {
    const mine = ++seq.current
    setLoad({ status: 'loading', error: null })
    setMore('idle')
    try {
      const r = await api.listTransactions({ jar: jar || undefined, needsReview: review || undefined, limit: PAGE })
      if (mine !== seq.current) return
      setItems(r.transactions)
      setCursor(r.next_cursor)
      setLoad({ status: 'ready', error: null })
    } catch (e) {
      if (mine !== seq.current) return
      setLoad({ status: 'error', error: e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0) })
    }
  }, [api, jar, review])

  useEffect(() => {
    void fetchFirst()
  }, [fetchFirst, version])

  const loadMore = useCallback(async () => {
    if (!cursor || more === 'loading') return
    const mine = seq.current
    setMore('loading')
    try {
      const r = await api.listTransactions({ jar: jar || undefined, needsReview: review || undefined, limit: PAGE, cursor })
      if (mine !== seq.current) return
      setItems((prev) => {
        const seen = new Set(prev.map((t) => t.id))
        return [...prev, ...r.transactions.filter((t) => !seen.has(t.id))]
      })
      setCursor(r.next_cursor)
      setMore('idle')
    } catch {
      if (mine === seq.current) setMore('error')
    }
  }, [api, cursor, jar, review, more])

  useEffect(() => {
    const el = sentinel.current
    if (!el || !cursor || more !== 'idle' || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) void loadMore()
    })
    io.observe(el)
    return () => io.disconnect()
  }, [cursor, more, loadMore, items.length])

  const setFilter = (next: { jar?: string; review?: boolean }) => {
    const p = new URLSearchParams()
    if (next.jar) p.set('jar', next.jar)
    if (next.review) p.set('review', '1')
    setParams(p, { replace: true })
  }

  const chips: Array<{ key: string; label: string; active: boolean; onClick: () => void }> = [
    { key: 'all', label: 'Tất cả', active: !jar && !review, onClick: () => setFilter({}) },
    { key: 'review', label: 'Cần xem lại', active: review, onClick: () => setFilter({ review: true }) },
    ...[...(ov.data?.jars ?? []), ...(ov.data?.system_jars ?? [])].map((j) => ({
      key: j.code,
      label: j.name,
      active: jar === j.code,
      onClick: () => setFilter({ jar: j.code }),
    })),
  ]

  return (
    <>
      <ScreenHeader title="Hoạt động" backTo="/" />
      <nav aria-label="Lọc giao dịch" className="mb-3 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none]">
        {chips.map((c) => (
          <button
            key={c.key}
            type="button"
            onClick={c.onClick}
            aria-pressed={c.active}
            className={cn('min-h-11 shrink-0 rounded-full border px-4 text-small font-semibold', c.active ? 'border-brand bg-tint text-brand-text' : 'border-line bg-surface text-ink')}
          >
            {c.label}
          </button>
        ))}
      </nav>

      {load.status === 'loading' && <ListSkeleton rows={6} label="Đang tải giao dịch" rowClass="h-16" />}
      {load.status === 'error' && load.error && <ErrorState className="px-4" error={load.error} title="Chưa tải được giao dịch" onRetry={() => void fetchFirst()} />}

      {load.status === 'ready' && items.length === 0 && (
        <EmptyState
          className="mx-4"
          title={review ? 'Không có giao dịch cần xem lại' : 'Chưa có giao dịch'}
          message={review || jar ? 'Không có giao dịch nào khớp bộ lọc này.' : 'Khi bạn chi tiêu hoặc nhận tiền trên ví mô phỏng, giao dịch sẽ hiện ở đây.'}
        />
      )}

      {load.status === 'ready' && items.length > 0 && (
        <>
          <ul className="mx-4 divide-y divide-line rounded-card bg-surface px-4 shadow-card" aria-label="Giao dịch" data-testid="activity-list">
            {items.map((t) => (
              <li key={t.id}>
                <TxRow tx={t} jar={t.jar ? lookup.get(t.jar) : undefined} creditLabel={ov.data?.credit_line?.product_label} />
              </li>
            ))}
          </ul>
          <div ref={sentinel} className="flex min-h-16 items-center justify-center px-4 py-4">
            {cursor ? (
              <div className="flex flex-col items-center gap-2">
                {more === 'error' && (
                  <p role="alert" className="text-small font-semibold text-bad-fg">
                    Chưa tải thêm được. Thử lại nhé.
                  </p>
                )}
                <Button type="button" variant="soft" size="sm" onClick={() => void loadMore()} disabled={more === 'loading'} aria-busy={more === 'loading'}>
                  {more === 'loading' ? 'Đang tải…' : 'Tải thêm'}
                </Button>
              </div>
            ) : (
              <p className="text-small text-ink-2">Đã hết giao dịch.</p>
            )}
          </div>
      <SimNote />
        </>
      )}
    </>
  )
}
