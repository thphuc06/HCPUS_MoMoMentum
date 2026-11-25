import { useState } from 'react'
import type { ApiError } from '@/api/errors'
import { RoadmapVersionDecisionRequest } from '@/api/roadmapSchemas'
import { ErrorState } from '@/components/StateViews'
import { AlertDialog, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { usePhoneFrame } from '@/layout/FrameContext'

/** "Giữ bản cũ": hỏi MỘT câu lý do, không bắt buộc (để trống là bỏ qua), rồi gửi cùng quyết định. */
export function KeepPreviousDialog({ fromVersion, toVersion, working, error, onClose, onKeep }: {
  fromVersion: number
  toVersion: number
  working: boolean
  error: ApiError | null
  onClose: () => void
  onKeep: (reason?: string) => void
}) {
  const frame = usePhoneFrame()
  const [reason, setReason] = useState('')
  return (
    <AlertDialog open onOpenChange={(open) => { if (!open && !working) onClose() }}>
      <AlertDialogContent container={frame}>
        <AlertDialogTitle>Giữ bản cũ</AlertDialogTitle>
        <AlertDialogDescription>Bỏ phiên bản {toVersion}, tiếp tục dùng phiên bản {fromVersion}.</AlertDialogDescription>
        <form className="mt-3 space-y-3" onSubmit={(e) => {
          e.preventDefault()
          onKeep(reason.trim() || undefined)
        }}>
          <label className="block space-y-1 text-small font-semibold text-ink-2">
            <span>Vì sao bạn giữ bản cũ? (không bắt buộc)</span>
            <textarea
              className="min-h-20 w-full rounded-xl border border-line bg-surface p-3 text-body text-ink"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={RoadmapVersionDecisionRequest.shape.reason.unwrap().maxLength ?? undefined}
            />
          </label>
          {error && <ErrorState error={error} title="Chưa lưu được lựa chọn" />}
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" size="sm" variant="ghost" disabled={working} onClick={onClose}>Hủy</Button>
            <Button type="submit" size="sm" disabled={working}>Giữ bản cũ</Button>
          </div>
        </form>
      </AlertDialogContent>
    </AlertDialog>
  )
}
