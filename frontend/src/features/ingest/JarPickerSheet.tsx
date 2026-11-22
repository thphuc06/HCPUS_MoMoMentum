import { Check } from 'lucide-react'
import { Drawer, DrawerContent, DrawerDescription, DrawerTitle } from '@/components/ui/drawer'
import { JarIcon } from '@/components/JarIcon'
import { usePhoneFrame } from '@/layout/FrameContext'
import type { IngestJar } from '@/contracts/blocks'
import { cn } from '@/lib/cn'

/**
 * Sheet chọn hũ một chạm cho một dòng của bảng duyệt: danh sách hũ lấy từ `ingest_review.data.jars` (hũ người dùng, không có
 * hũ hệ thống). Chạm một hũ là chọn và đóng sheet; nơi gọi gửi `PATCH /ingest/rows/{row_id}`.
 */
export function JarPickerSheet({
  open,
  onOpenChange,
  jars,
  current,
  rowLabel,
  onPick,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  jars: readonly IngestJar[]
  current?: string
  rowLabel: string
  onPick: (jar: IngestJar) => void
}) {
  const frame = usePhoneFrame()
  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent container={frame} data-testid="jar-picker" className="rounded-t-sheet bg-background pb-[max(16px,env(safe-area-inset-bottom))] shadow-sheet">
        <div className="mx-auto mt-2 h-1.5 w-10 shrink-0 rounded-full bg-line" aria-hidden />
        <div className="px-4 pt-2 pb-3">
          <DrawerTitle className="text-section font-bold text-ink">Chọn hũ</DrawerTitle>
          <DrawerDescription className="mt-1 truncate text-small text-ink-2">Cho dòng {rowLabel}. Chỉ đổi đề xuất, chưa ghi gì.</DrawerDescription>
        </div>
        <div role="radiogroup" aria-label={`Hũ cho dòng ${rowLabel}`} className="space-y-1.5 overflow-y-auto px-4 pb-2">
          {jars.map((j) => {
            const on = j.code === current
            return (
              <button
                key={j.code}
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => onPick(j)}
                className={cn('flex min-h-14 w-full items-center gap-3 rounded-2xl border px-3 text-left', on ? 'border-brand bg-tint' : 'border-line bg-surface')}
              >
                <JarIcon colorKey={j.color_key} iconKey={j.icon_key} size={36} />
                <span className="flex-1 text-body font-semibold text-ink">{j.name}</span>
                {on && <Check className="size-5 text-brand-text" aria-hidden />}
              </button>
            )
          })}
          {jars.length === 0 && <p className="py-4 text-center text-small text-ink-2">Chưa có hũ nào để chọn.</p>}
        </div>
      </DrawerContent>
    </Drawer>
  )
}
