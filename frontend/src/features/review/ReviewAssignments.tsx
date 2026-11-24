import { useState, type ReactNode } from 'react'
import { ErrorState } from '@/components/StateViews'
import { Button } from '@/components/ui/button'
import { Drawer, DrawerContent, DrawerDescription, DrawerTitle } from '@/components/ui/drawer'
import type { ReviewJarRef, ReviewListData } from '@/contracts/blocks'
import { JarPickerSheet } from '@/features/ingest/JarPickerSheet'
import { usePhoneFrame } from '@/layout/FrameContext'
import { reviewItemTitle } from './ReviewItemRow'
import { ReviewList } from './ReviewList'
import { useAssignJar, type RememberJar } from './useAssignJar'

type Selection = { transactionId: string; jar: ReviewJarRef | null }

export function ReviewAssignments({ data, disabled, footer, title }: { data: ReviewListData; disabled?: boolean; footer?: ReactNode; title?: string }) {
  const frame = usePhoneFrame()
  const write = useAssignJar()
  const [selection, setSelection] = useState<Selection | null>(null)
  const [submittedData, setSubmittedData] = useState<ReviewListData | null>(null)
  const item = selection && data.items.find((row) => row.transaction_id === selection.transactionId)
  const jar = selection?.jar
  const locked = !!disabled || write.working || submittedData === data
  const scopeDisabled = locked || write.phase === 'blocked'

  function close() {
    if (write.working) return
    setSelection(null)
    write.reset()
  }

  async function assign(remember: RememberJar) {
    if (!item || !jar || scopeDisabled || (remember === 'always' && !item.can_remember)) return
    const receipt = await write.assign(item.transaction_id, jar.code, remember)
    if (receipt) {
      // useWriteFlow yêu cầu tải lại. Khóa ảnh chụp cũ cho đến khi danh sách mới về từ server.
      setSubmittedData(data)
      setSelection(null)
    }
  }

  return (
    <>
      <ReviewList
        data={data}
        title={title}
        footer={footer}
        actions={{
          disabled: locked,
          canPickOtherJar: data.jars.length > 0,
          selectJar: (row, chosen) => {
            write.reset()
            setSelection({ transactionId: row.transaction_id, jar: chosen })
          },
          pickOtherJar: (row) => {
            write.reset()
            setSelection({ transactionId: row.transaction_id, jar: null })
          },
        }}
      />
      <JarPickerSheet
        open={!!item && !jar}
        onOpenChange={(open) => { if (!open) close() }}
        jars={data.jars}
        current={item?.current_jar?.code}
        rowLabel={item ? reviewItemTitle(item) : ''}
        onPick={(chosen) => { if (item && !locked) setSelection({ transactionId: item.transaction_id, jar: chosen }) }}
      />
      <Drawer open={!!item && !!jar} onOpenChange={(open) => { if (!open) close() }}>
        <DrawerContent container={frame} className="rounded-t-sheet bg-background pb-[max(16px,env(safe-area-inset-bottom))] shadow-sheet">
          <div className="mx-auto mt-2 h-1.5 w-10 shrink-0 rounded-full bg-line" aria-hidden />
          <div className="space-y-3 overflow-y-auto px-4 pt-3">
            <div>
              <DrawerTitle className="text-section font-bold text-ink">Áp dụng cho giao dịch nào?</DrawerTitle>
              <DrawerDescription className="mt-1 wrap-anywhere text-small text-ink-2">
                {item && jar && `${reviewItemTitle(item)} · Hũ ${jar.name}`}
              </DrawerDescription>
            </div>
            {write.error && <ErrorState error={write.error} title="Chưa gán được hũ" />}
            {write.working && <p role="status" className="text-small text-ink-2">Đang lưu lựa chọn…</p>}
            <div className="grid gap-2">
              <Button type="button" disabled={scopeDisabled} onClick={() => void assign('once')}>Chỉ lần này</Button>
              {item?.can_remember && (
                <Button type="button" variant="outline" disabled={scopeDisabled} onClick={() => void assign('always')}>
                  Luôn luôn cho người này
                </Button>
              )}
              <Button type="button" variant="ghost" size="sm" disabled={write.working} onClick={close}>Hủy</Button>
            </div>
          </div>
        </DrawerContent>
      </Drawer>
    </>
  )
}
