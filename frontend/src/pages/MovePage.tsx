import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { Button } from '@/components/ui/button'
import { MoneyInput } from '@/components/MoneyInput'
import { ScreenHeader } from '@/components/ScreenHeader'
import { ErrorState } from '@/components/StateViews'
import { Skeleton } from '@/components/ui/skeleton'
import { useOverview } from '@/api/OverviewProvider'
import { useWriteFlow } from '@/api/useWrite'
import { BlockRenderer } from '@/blocks/registry'
import { formatVnd } from '@/lib/format'

const selectCls = 'h-13 w-full rounded-2xl border border-line bg-surface px-4 text-[16px] text-ink'

// Chuyển tiền giữa hai hũ (`move_between_jars`): cũng là cách gán Tiền vào khác vào một hũ (hũ nguồn là Tiền vào khác).
// Mở từ Tổng quan ("Giữa hũ"), Chi tiết hũ ("Chuyển tiền vào hũ này") và ô Tiền vào khác. Biên nhận là khối `receipt`.
export function MovePage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const ov = useOverview()
  const write = useWriteFlow()
  const [from, setFrom] = useState(params.get('from') ?? '')
  const [to, setTo] = useState(params.get('to') ?? '')
  const [amount, setAmount] = useState('')
  const prefilled = useRef(false)

  const jars = ov.data?.jars ?? []
  const other = ov.data?.system_jars.find((j) => j.system_role === 'other_income')
  const sources = [...jars, ...(other ? [other] : [])]
  const fromJar = sources.find((j) => j.code === from)
  const valid = Number(amount) > 0 && from !== '' && to !== '' && from !== to

  // Mở từ "Gán vào hũ": điền sẵn toàn bộ số đang ở hũ nguồn (người dùng sửa được).
  useEffect(() => {
    if (prefilled.current || !fromJar) return
    prefilled.current = true
    if (params.get('from') && fromJar.balance_vnd > 0) setAmount(String(fromJar.balance_vnd))
  }, [fromJar, params])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid) return
    await write.submit('move_between_jars', { from_jar: from, to_jar: to, amount_vnd: Number(amount) })
  }

  return (
    <>
      <ScreenHeader title="Chuyển giữa hũ" backTo="/" />
      <div className="space-y-4 px-4 pb-10">
        {ov.status === 'loading' && <Skeleton className="h-[320px] w-full rounded-card" role="status" aria-label="Đang tải các hũ" />}
        {ov.status === 'error' && !ov.data && <ErrorState error={ov.error} title="Chưa tải được các hũ" onRetry={() => void ov.reload()} />}

        {write.receipt ? (
          <div className="space-y-3" data-testid="move-receipt">
            <BlockRenderer raw={write.receipt} blockId={write.receipt.id} />
            <Button type="button" className="w-full" onClick={() => navigate('/', { replace: true })}>
              Xong
            </Button>
          </div>
        ) : (
          ov.data && (
            <form onSubmit={submit} noValidate className="space-y-4 rounded-card bg-surface p-4 shadow-card" aria-label="Chuyển giữa hũ">
              <label className="block">
                <span className="mb-1.5 block text-small font-semibold text-ink-2">Từ hũ</span>
                <select value={from} onChange={(e) => setFrom(e.target.value)} className={selectCls}>
                  <option value="">Chọn hũ nguồn</option>
                  {sources.map((j) => (
                    <option key={j.code} value={j.code}>
                      {j.name} · còn {formatVnd(j.balance_vnd)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1.5 block text-small font-semibold text-ink-2">Sang hũ</span>
                <select value={to} onChange={(e) => setTo(e.target.value)} className={selectCls}>
                  <option value="">Chọn hũ đích</option>
                  {jars
                    .filter((j) => j.code !== from)
                    .map((j) => (
                      <option key={j.code} value={j.code}>
                        {j.name} · còn {formatVnd(j.balance_vnd)}
                      </option>
                    ))}
                </select>
              </label>
              <MoneyInput label="Số tiền" size="lg" value={amount} onChange={setAmount} />
              {fromJar && Number(amount) > fromJar.balance_vnd && (
                <p role="status" className="rounded-2xl bg-warn-bg px-3 py-2 text-small font-medium text-warn-fg">
                  Số tiền lớn hơn số đang có ở hũ nguồn. Hệ thống sẽ từ chối nếu không đủ.
                </p>
              )}
              {write.error && (
                <p role="alert" className="rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
                  {write.error.message}
                </p>
              )}
              <Button type="submit" className="w-full" disabled={!valid || write.working || write.phase === 'blocked'} aria-busy={write.working}>
                {write.working ? 'Đang chuyển…' : 'Chuyển tiền giữa hũ'}
              </Button>
              <p className="text-note text-ink-2">Bấm chuyển thì hệ thống mới ghi và cập nhật số dư hai hũ; chưa bấm thì chưa có gì thay đổi.</p>
            </form>
          )
        )}
      </div>
    </>
  )
}
