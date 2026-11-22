import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AlertDialog, AlertDialogClose, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { ScreenHeader } from '@/components/ScreenHeader'
import { ErrorState } from '@/components/StateViews'
import { Skeleton } from '@/components/ui/skeleton'
import { useApiResource } from '@/api/resource'
import { useOverview } from '@/api/OverviewProvider'
import { useWriteFlow } from '@/api/useWrite'
import { usePhoneFrame } from '@/layout/FrameContext'
import { ObligationFormView } from '@/features/obligations/ObligationForm'
import { formFromObligation, obligationDeleteParams } from '@/features/obligations/params'

// Thêm (/obligations/new) hoặc sửa/xóa (/obligations/:id) một khoản nghĩa vụ đã khai. Xóa có hộp xác nhận và đi qua
// cùng luồng /confirmations -> /actions (update_profile, op delete).
export function ObligationEditPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const frame = usePhoneFrame()
  const ov = useOverview()
  const list = useApiResource((api) => api.listObligations(), [], !!id)
  const del = useWriteFlow()
  const [confirming, setConfirming] = useState(false)
  const jars = ov.data?.jars ?? []
  const current = id ? list.data?.obligations.find((o) => o.id === id) : undefined

  const remove = async () => {
    if (!id) return
    const r = await del.submit('update_profile', obligationDeleteParams(id))
    setConfirming(false)
    if (r) navigate('/obligations', { replace: true })
  }

  return (
    <>
      <ScreenHeader title={id ? 'Sửa khoản nghĩa vụ' : 'Thêm khoản nghĩa vụ'} backTo="/obligations" />
      <div className="px-4 pb-10">
        {id && list.status === 'loading' && <Skeleton className="h-[420px] w-full rounded-card" role="status" aria-label="Đang tải khoản" />}
        {id && list.status === 'error' && <ErrorState error={list.error} title="Chưa tải được khoản này" onRetry={() => void list.reload()} />}
        {id && list.status === 'ready' && !current && (
          <p role="alert" className="rounded-card bg-warn-bg p-4 text-small text-ink">
            Không tìm thấy khoản này. Có thể nó đã được xóa hoặc đã trả xong.
          </p>
        )}
        {current && current.source === 'bnpl_auto' && (
          <p role="status" className="rounded-card bg-surface-2 p-4 text-small text-ink-2">
            Khoản Trả sau tự sinh khi mua bằng hạn mức nên không sửa hay xóa tay được. Trả nó từ một hũ khi đến hạn.
          </p>
        )}
        {(!id || (current && current.source === 'declared')) && (
          <>
            <ObligationFormView
              key={current?.id ?? 'new'}
              initial={current ? formFromObligation(current) : undefined}
              jars={jars}
              onSaved={() => navigate('/obligations', { replace: true })}
              onCancel={() => navigate('/obligations')}
            />
            {current && (
              <Button type="button" variant="destructive" className="mt-4 w-full" onClick={() => setConfirming(true)}>
                <Trash2 className="size-5" aria-hidden />
                Xóa khoản này
              </Button>
            )}
          </>
        )}
        {del.error && (
          <p role="alert" className="mt-3 rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
            {del.error.message}
          </p>
        )}
      </div>

      <AlertDialog open={confirming} onOpenChange={(o) => !del.working && setConfirming(o)}>
        <AlertDialogContent container={frame}>
          <AlertDialogTitle>Xóa khoản này?</AlertDialogTitle>
          <AlertDialogDescription>Khoản “{current?.name}” sẽ không còn nằm trong dự báo tiền ra. Bạn có thể khai lại sau.</AlertDialogDescription>
          <div className="mt-5 flex flex-col gap-3">
            <Button type="button" variant="destructive" onClick={() => void remove()} disabled={del.working} aria-busy={del.working}>
              {del.working ? 'Đang xóa…' : 'Xóa'}
            </Button>
            <AlertDialogClose render={<Button type="button" variant="outline" disabled={del.working} />}>Hủy</AlertDialogClose>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
