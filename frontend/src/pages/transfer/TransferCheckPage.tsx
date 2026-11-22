import { useMemo } from 'react'
import { Navigate, useNavigate } from 'react-router'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ScreenHeader } from '@/components/ScreenHeader'
import { ErrorState } from '@/components/StateViews'
import { useApiResource } from '@/api/resource'
import type { AffordabilityRequest } from '@/api/schemas'
import { AffordCard } from '@/features/affordability/AffordCard'
import { amountOf, useTransferFlow } from '@/features/transfer/TransferFlow'
import { formatVnd } from '@/lib/format'
import { Avatar } from './TransferPayeePage'

// Figma T3a (XANH, 19:955), T3b (VÀNG, 19:1009), T3c (ĐỎ, 19:1084): kiểm tra trước khi chuyển. Gọi `POST /affordability`
// (tất định, không qua LLM, không ghi gì) và vẽ đúng khối `affordability_card` bằng CÙNG component với chat. Giao diện không
// tính đủ/sát/hụt, phí hay tổng: mọi số do engine trả. Kiểm tra chỉ là lời khuyên (server vẫn kiểm số dư và hạn mức lúc
// ghi), nên lỗi ở bước này không chặn: cho Thử lại hoặc bỏ qua để xem lại.
export function TransferCheckPage() {
  const navigate = useNavigate()
  const { state, patch } = useTransferFlow()
  const amount = amountOf(state)
  const source = state.source
  const payee = state.payee

  const req = useMemo<AffordabilityRequest | null>(() => {
    if (!source || amount <= 0 || !payee) return null
    return source.kind === 'jar'
      ? { amount_vnd: amount, funding_source: 'jar', jar: source.code, label: payee.name.slice(0, 60) }
      : { amount_vnd: amount, funding_source: 'credit', label: payee.name.slice(0, 60) }
  }, [source, amount, payee])
  const check = useApiResource((api) => api.checkAffordability(req!), [req], req !== null)

  if (!payee) return <Navigate to="/transfer" replace />
  if (!source || amount <= 0) return <Navigate to="/transfer/amount" replace />

  const toReview = () => navigate('/transfer/review')
  const changeSource = () => {
    patch({ source: null })
    navigate('/transfer/amount')
  }

  return (
    <>
      <ScreenHeader title="Kiểm tra trước khi chuyển" backTo="/transfer/amount" />
      <div className="px-4 pb-8">
        <div className="flex flex-col items-center">
          <Avatar name={payee.name} size={48} />
          <p className="mt-2 text-body text-ink-2">Chuyển cho {payee.name}</p>
          <p className="num text-display font-extrabold text-ink" data-testid="check-amount">
            {formatVnd(amount)}
          </p>
        </div>

        <div className="mt-4">
          {check.status === 'loading' && (
            <div role="status" aria-busy="true" aria-label="Đang kiểm tra trước khi chuyển" data-testid="check-loading" className="space-y-3">
              <Skeleton className="h-[220px] w-full rounded-card" />
              <Skeleton className="h-12 w-full rounded-full" />
            </div>
          )}

          {check.status === 'error' && (
            <div data-testid="check-error" className="space-y-3">
              <ErrorState error={check.error} title="Chưa kiểm tra được" onRetry={() => void check.reload()} />
              <p className="text-small text-ink-2">Bước này chỉ để bạn cân nhắc. Bạn vẫn xem lại được; hệ thống sẽ kiểm số dư và hạn mức khi ghi.</p>
              <Button type="button" variant="outline" className="w-full" onClick={toReview}>
                Bỏ qua kiểm tra, xem lại
              </Button>
            </div>
          )}

          {check.status === 'ready' && (
            <div className={check.refreshing ? 'opacity-70' : undefined} aria-busy={check.refreshing}>
              <AffordCard
                block={check.data}
                actions={
                  <>
                    {check.data.data.verdict !== 'ok' && source.kind === 'jar' && check.data.data.credit && (
                      <Button
                        type="button"
                        onClick={() => {
                          patch({ source: { kind: 'credit' } })
                          toReview()
                        }}
                      >
                        Trả bằng {check.data.data.credit.cost.product_label}
                      </Button>
                    )}
                    <Button type="button" variant={check.data.data.verdict === 'ok' ? 'default' : 'outline'} onClick={toReview}>
                      {check.data.data.verdict === 'ok' ? 'Tiếp tục' : `Vẫn chuyển ${formatVnd(amount)}`}
                    </Button>
                    <Button type="button" variant="ghost" onClick={changeSource}>
                      Đổi nguồn
                    </Button>
                  </>
                }
              />
            </div>
          )}
        </div>
      </div>
    </>
  )
}
