import { useState } from 'react'
import type { ApiError } from '@/api/errors'
import { RoadmapStepDecisionRequest, RoadmapStepEditRequest } from '@/api/roadmapSchemas'
import { usePreview } from '@/api/useConfirmPreview'
import { useWriteFlow } from '@/api/useWrite'
import { BlockRenderer } from '@/blocks/registry'
import { MoneyInput } from '@/components/MoneyInput'
import { Numpad } from '@/components/Numpad'
import { PreviewPanel } from '@/components/PreviewPanel'
import { ErrorState } from '@/components/StateViews'
import { AlertDialog, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Drawer, DrawerContent, DrawerDescription, DrawerHeader, DrawerTitle } from '@/components/ui/drawer'
import { Input } from '@/components/ui/input'
import { VndPositive, type RoadmapStep, type RoadmapStepAction } from '@/contracts/blocks'
import { usePhoneFrame } from '@/layout/FrameContext'

type DecisionProps = {
  step: RoadmapStep
  working: boolean
  error: ApiError | null
  onClose: () => void
}

export function RejectStepDialog({ step, working, error, onClose, onReject }: DecisionProps & {
  onReject: (reason?: string) => void
}) {
  const frame = usePhoneFrame()
  const [reason, setReason] = useState('')
  return (
    <AlertDialog open onOpenChange={(open) => { if (!open && !working) onClose() }}>
      <AlertDialogContent container={frame}>
        <AlertDialogTitle>Từ chối bước</AlertDialogTitle>
        <AlertDialogDescription>{step.title}</AlertDialogDescription>
        <form className="mt-3 space-y-3" onSubmit={(e) => {
          e.preventDefault()
          onReject(reason.trim() || undefined)
        }}>
          <label className="block space-y-1 text-small font-semibold text-ink-2">
            <span>Vì sao bạn muốn từ chối? (không bắt buộc)</span>
            <textarea
              className="min-h-20 w-full rounded-xl border border-line bg-surface p-3 text-body text-ink"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={RoadmapStepDecisionRequest.shape.reason.unwrap().maxLength ?? undefined}
            />
          </label>
          {error && <ErrorState error={error} title="Chưa lưu được quyết định" />}
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" size="sm" variant="ghost" disabled={working} onClick={onClose}>Hủy</Button>
            <Button type="submit" size="sm" variant="destructive" disabled={working}>Từ chối</Button>
          </div>
        </form>
      </AlertDialogContent>
    </AlertDialog>
  )
}

const drawerClass = 'rounded-t-sheet bg-background pb-[max(16px,env(safe-area-inset-bottom))] shadow-sheet'

export function EditStepDrawer({ step, version, working, error, onClose, onEdit }: DecisionProps & {
  version: number
  onEdit: (request: RoadmapStepEditRequest) => void
}) {
  const frame = usePhoneFrame()
  const initialAmount = step.amount_vnd?.toString() ?? ''
  const initialDate = step.due_date ?? ''
  const [amount, setAmount] = useState(initialAmount)
  const [date, setDate] = useState(initialDate)
  const [showNumpad, setShowNumpad] = useState(false)
  const request = RoadmapStepEditRequest.safeParse({
    version,
    ...(amount !== initialAmount && { amount_vnd: Number(amount) }),
    ...(date !== initialDate && { due_date: date }),
  })
  const appendDigit = (digit: string) => setAmount((value) => {
    const candidate = VndPositive.safeParse(Number(value + digit))
    return candidate.success ? String(candidate.data) : value
  })
  return (
    <Drawer open onOpenChange={(open) => { if (!open && !working) onClose() }}>
      <DrawerContent container={frame} className={drawerClass}>
        <DrawerHeader>
          <DrawerTitle className="text-section font-bold">Sửa bước</DrawerTitle>
          <DrawerDescription>{step.title}</DrawerDescription>
        </DrawerHeader>
        <form className="min-h-0 space-y-3 overflow-y-auto px-4 pt-3" onSubmit={(e) => {
          e.preventDefault()
          if (request.success) onEdit(request.data)
        }}>
          <MoneyInput label="Số tiền" value={amount} onChange={setAmount} />
          <Button type="button" variant="ghost" size="sm" aria-expanded={showNumpad} onClick={() => setShowNumpad(!showNumpad)}>
            {showNumpad ? 'Ẩn bàn phím số' : 'Mở bàn phím số'}
          </Button>
          {showNumpad && <Numpad onDigit={appendDigit} onDelete={() => setAmount((value) => value.slice(0, -1))} />}
          <label className="block space-y-1 text-small font-semibold text-ink-2">
            <span>Ngày đến hạn</span>
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          {error && <ErrorState error={error} title="Chưa lưu được bước" />}
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" size="sm" variant="ghost" disabled={working} onClick={onClose}>Hủy</Button>
            <Button type="submit" size="sm" disabled={working || !request.success}>Lưu thay đổi</Button>
          </div>
        </form>
      </DrawerContent>
    </Drawer>
  )
}

export function ExecuteStepDrawer({ title, action, available, onClose }: {
  title: string
  action: RoadmapStepAction
  available: boolean
  onClose: () => void
}) {
  const frame = usePhoneFrame()
  const write = useWriteFlow()
  const preview = usePreview(action.tool, available && !write.receipt ? action.params : null)
  const canConfirm = available && preview.status === 'ready' && write.phase === 'idle'
  return (
    <Drawer open onOpenChange={(open) => { if (!open && !write.working) onClose() }}>
      <DrawerContent container={frame} className={drawerClass}>
        <DrawerHeader>
          <DrawerTitle className="text-section font-bold">{write.receipt ? 'Kết quả thực hiện' : 'Xác nhận thực hiện'}</DrawerTitle>
          <DrawerDescription>{title}</DrawerDescription>
        </DrawerHeader>
        <div className="min-h-0 space-y-3 overflow-y-auto px-4 pt-3">
          {write.receipt ? (
            <>
              <BlockRenderer raw={write.receipt} blockId={write.receipt.id} />
              <Button type="button" className="w-full" onClick={onClose}>Xong</Button>
            </>
          ) : (
            <>
              <PreviewPanel state={preview} />
              {write.error && <ErrorState error={write.error} title="Chưa thực hiện được bước" />}
              {!available && <p role="status" className="text-small text-ink-2">Bước này hiện chưa thể thực hiện. Quay lại để xem lộ trình hiện tại.</p>}
              <div className="flex flex-wrap justify-end gap-2">
                <Button type="button" size="sm" variant="ghost" disabled={write.working} onClick={onClose}>Hủy</Button>
                <Button
                  type="button"
                  size="sm"
                  disabled={!canConfirm}
                  aria-busy={write.working}
                  onClick={() => void write.submit(action.tool, action.params)}
                >
                  Xác nhận thực hiện
                </Button>
              </div>
            </>
          )}
        </div>
      </DrawerContent>
    </Drawer>
  )
}
