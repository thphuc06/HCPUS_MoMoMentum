import { useRef } from 'react'
import { CircleHelp, X } from 'lucide-react'
import { Disclosure } from '@/components/ui/Disclosure'
import { Drawer, DrawerClose, DrawerContent, DrawerDescription, DrawerTitle, DrawerTrigger } from '@/components/ui/drawer'
import type { JarTemplate } from '@/api/schemas'
import { usePhoneFrame } from '@/layout/FrameContext'
import { cn } from '@/lib/cn'
import {
  SPLIT_HELP_CLOSE_LABEL,
  SPLIT_HELP_LIST_LABEL,
  SPLIT_HELP_TRIGGER_LABEL,
  splitHelpContent,
  type SplitHelpPlace,
} from './splitHelpContent'

const ROUND_BUTTON =
  'grid size-11 shrink-0 place-items-center rounded-full outline-none hover:bg-tint focus-visible:ring-3 focus-visible:ring-ring/50'

/**
 * Nút "?" cạnh tiêu đề phần chia tỷ lệ (màn "Thêm hoặc sửa hũ", bước chia hũ của onboarding) và tấm trợ giúp "Chia hũ sao cho
 * hợp lý" mở từ đáy (Drawer của Base UI, portal vào khung điện thoại). Hộp thoại có tên và mô tả cho trình đọc màn hình; đóng
 * bằng nút Đóng, Esc, chạm ra ngoài hoặc vuốt xuống; tiêu điểm vào trong tấm khi mở và trả về nút khi đóng. Lời ở
 * `splitHelpContent.ts`; số chỉ lấy từ `templates` (`GET /jar-templates`), vắng thì lời định tính.
 */
export function SplitHelp({ place, templates, className }: { place: SplitHelpPlace; templates?: readonly JarTemplate[]; className?: string }) {
  const frame = usePhoneFrame()
  const trigger = useRef<HTMLButtonElement>(null)
  const c = splitHelpContent({ place, templates })
  return (
    <Drawer>
      <DrawerTrigger ref={trigger} aria-label={SPLIT_HELP_TRIGGER_LABEL} data-testid="split-help-button" className={cn(ROUND_BUTTON, 'text-brand-text', className)}>
        <CircleHelp className="size-6" aria-hidden />
      </DrawerTrigger>
      <DrawerContent
        container={frame}
        finalFocus={trigger}
        data-testid="split-help"
        className="rounded-t-sheet bg-background pb-[max(16px,env(safe-area-inset-bottom))] shadow-sheet"
      >
        <div className="mx-auto mt-2 h-1.5 w-10 shrink-0 rounded-full bg-line" aria-hidden />
        <div className="flex shrink-0 items-start gap-2 pr-2 pl-4">
          <div className="min-w-0 flex-1 pt-2">
            <DrawerTitle className="text-section font-bold text-ink">{c.title}</DrawerTitle>
            <DrawerDescription className="mt-0.5 text-note text-ink-2">{c.note}</DrawerDescription>
          </div>
          <DrawerClose aria-label={SPLIT_HELP_CLOSE_LABEL} className={cn(ROUND_BUTTON, 'text-ink-2')}>
            <X className="size-5" aria-hidden />
          </DrawerClose>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-2">
          <ul aria-label={SPLIT_HELP_LIST_LABEL} className="mt-3 space-y-3">
            {c.tips.map((t) => (
              <li key={t.id} data-tip={t.id} className="flex gap-2.5">
                <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-brand" />
                <div className="min-w-0">
                  <p className="text-small font-semibold text-ink">{t.lead}</p>
                  <p className="text-small text-ink-2">{t.text}</p>
                  {t.data && (
                    <p data-testid="split-help-defaults" className="num mt-1 text-small font-semibold text-ink">
                      {t.data}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
          <Disclosure label={c.more.label} className="mt-2" panelClassName="pb-1">
            <ul className="space-y-1.5 text-small text-ink-2">
              {c.more.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </Disclosure>
        </div>
      </DrawerContent>
    </Drawer>
  )
}
