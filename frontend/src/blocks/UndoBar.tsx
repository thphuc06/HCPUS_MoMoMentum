import { RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { formatCountdown } from '@/lib/format'
import type { ReceiptActionBlock, ReceiptBlock } from '@/contracts/blocks'
import { useUndo } from './useUndo'

/**
 * Hoàn tác có đếm ngược dưới biên nhận (H6b). Chỉ hiện khi biên nhận vừa được thực hiện trong phiên này (`doneAt`), thao tác
 * có thao tác ngược hợp đồng quy định và còn trong cửa sổ; hết giờ thì thanh biến mất (không để nút chết).
 */
export function UndoBar({ receipt, blockId, doneAt }: { receipt: ReceiptBlock | ReceiptActionBlock; blockId: string; doneAt?: number }) {
  const u = useUndo(receipt, blockId, doneAt)
  if (!u.available && !u.working && !u.error) return null
  return (
    <div data-testid="undo-bar" className="mt-3">
      <Button type="button" variant="outline" size="sm" className="w-full" disabled={u.working || !u.available} aria-busy={u.working} onClick={() => void u.undo()}>
        <RotateCcw className="size-4" aria-hidden />
        {u.working ? 'Đang hoàn tác…' : `Hoàn tác · còn ${formatCountdown(u.remainingMs)}`}
      </Button>
      {u.error && (
        <p role="alert" className="mt-2 rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
          {u.error.message}
        </p>
      )}
    </div>
  )
}
