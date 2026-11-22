import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { ChevronRight, Info, Plus, ScanLine, Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { ScreenHeader } from '@/components/ScreenHeader'
import { EmptyState, ErrorState, ListSkeleton } from '@/components/StateViews'
import { useApiResource } from '@/api/resource'
import { useTransferFlow } from '@/features/transfer/TransferFlow'
import type { Payee } from '@/api/schemas'

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  const first = parts[0]?.charAt(0) ?? ''
  const last = parts.length > 1 ? (parts[parts.length - 1]?.charAt(0) ?? '') : ''
  return (first + last).toUpperCase()
}

export function Avatar({ name, size = 44 }: { name: string; size?: number }) {
  return (
    <span aria-hidden className="grid shrink-0 place-items-center rounded-full bg-tint font-bold text-brand-text" style={{ width: size, height: size, fontSize: size * 0.34 }}>
      {initials(name)}
    </span>
  )
}

// Figma T1 chọn người nhận (19:787): tìm kiếm, "Gần đây", "Danh bạ". Danh sách đến từ GET /payees (không có số tài khoản
// đầy đủ). Quét QR và nhập số mới chưa có ở phase này: vô hiệu, có nhãn "Sắp có".
export function TransferPayeePage() {
  const navigate = useNavigate()
  const { patch } = useTransferFlow()
  const payees = useApiResource((api) => api.listPayees(), [])
  const [q, setQ] = useState('')
  const list = payees.data?.payees ?? []
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return needle ? list.filter((p) => p.name.toLowerCase().includes(needle) || (p.account_hint ?? '').toLowerCase().includes(needle)) : list
  }, [list, q])
  const recent = list.filter((p) => p.last_used_at).slice(0, 4)

  const choose = (p: Payee) => {
    patch({ payee: p })
    navigate('/transfer/amount')
  }

  return (
    <>
      <ScreenHeader title="Chuyển tiền" backTo="/" />
      <div className="space-y-4 px-4 pb-8">
        <label className="relative block">
          <span className="sr-only">Tìm người nhận</span>
          <Search className="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-ink-2" aria-hidden />
          <Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm tên người nhận" className="pl-12" />
        </label>

        <button type="button" disabled aria-disabled="true" className="flex min-h-11 items-center gap-2 text-small font-semibold text-brand-text opacity-60">
          <ScanLine className="size-4" aria-hidden />
          Quét QR để chuyển nhanh
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-note font-medium text-ink-2">Sắp có</span>
        </button>

        {payees.status === 'loading' && <ListSkeleton rows={3} label="Đang tải danh bạ" />}
        {payees.status === 'error' && <ErrorState error={payees.error} title="Chưa tải được danh bạ" onRetry={() => void payees.reload()} />}

        {payees.status === 'ready' && list.length === 0 && (
          <EmptyState title="Chưa có người nhận nào" message="Danh bạ của ví mô phỏng đang trống nên chưa chuyển tiền cho ai được." />
        )}

        {recent.length > 0 && !q && (
          <section aria-label="Gần đây">
            <h2 className="mb-2 text-section font-bold text-ink">Gần đây</h2>
            <ul className="flex gap-3 overflow-x-auto [scrollbar-width:none]">
              {recent.map((p) => (
                <li key={p.id}>
                  <button type="button" onClick={() => choose(p)} className="flex min-h-[88px] w-[72px] flex-col items-center gap-1.5" aria-label={`Chuyển cho ${p.name}`}>
                    <Avatar name={p.name} size={52} />
                    <span className="w-full truncate text-center text-small text-ink">{p.name.split(/\s+/).pop()}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {list.length > 0 && (
          <section aria-label="Danh bạ">
            <h2 className="mb-2 text-section font-bold text-ink">Danh bạ</h2>
            {filtered.length === 0 ? (
              <EmptyState title="Không tìm thấy" message="Không có người nhận nào khớp với từ khóa." />
            ) : (
              <ul className="divide-y divide-line rounded-card bg-surface px-4 shadow-card">
                {filtered.map((p) => (
                  <li key={p.id}>
                    <button type="button" onClick={() => choose(p)} className="flex min-h-[68px] w-full items-center gap-3 text-left">
                      <Avatar name={p.name} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-body font-bold text-ink">{p.name}</span>
                        {p.account_hint && <span className="block truncate text-small text-ink-2">{p.account_hint}</span>}
                      </span>
                      <ChevronRight className="size-5 shrink-0 text-ink-2" aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        <button type="button" disabled aria-disabled="true" className="flex min-h-14 w-full items-center gap-3 rounded-card bg-tint px-4 text-subtitle font-semibold text-brand-text opacity-60">
          <Plus className="size-5" aria-hidden />
          Nhập số điện thoại mới
          <span className="ml-auto rounded-full bg-surface px-2 py-0.5 text-note font-medium text-ink-2">Sắp có</span>
        </button>

        <p className="mx-auto flex w-fit items-center gap-1.5 rounded-full bg-surface-2 px-3 py-1.5 text-small text-ink-2">
          <Info className="size-4" aria-hidden />
          Ví mô phỏng · không chuyển tiền thật
        </p>
      </div>
    </>
  )
}
