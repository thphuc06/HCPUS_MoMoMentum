import { DisclosureButton, DisclosurePanel, useDisclosure } from '@/components/ui/Disclosure'
import type { ResilienceComponent } from '@/contracts/blocks'

/** Một thành phần điểm: tên và điểm hiện ngay; câu giải thích (căn cứ, mức tham chiếu) mở bằng chạm vào hàng (Luật chữ §9). */
export function ScoreRow({ component, weakest }: { component: ResilienceComponent; weakest: boolean }) {
  const why = useDisclosure()
  return (
    <li className="py-1">
      <DisclosureButton
        state={why}
        label={`${component.label}${weakest ? ', yếu nhất' : ''}: ${component.applicable && component.score !== undefined ? `${component.score} điểm` : 'không áp dụng'}. Vì sao?`}
        className="flex w-full justify-between gap-x-3 rounded-xl px-0 text-left font-normal text-ink hover:no-underline"
      >
        <span className="text-small font-semibold text-ink">
          {component.label}
          {weakest && <span className="ml-2 rounded-full bg-warn-bg px-2 py-0.5 text-note font-semibold text-warn-fg">Yếu nhất</span>}
        </span>
        <span className="ml-auto">
          {component.applicable ? (
            component.score !== undefined && <span className="num text-small font-bold text-ink">{component.score} điểm</span>
          ) : (
            <span className="text-small text-ink-2">Không áp dụng</span>
          )}
        </span>
      </DisclosureButton>
      <DisclosurePanel state={why} className="pb-1.5 text-small text-ink-2">
        <p>{component.explanation}</p>
      </DisclosurePanel>
    </li>
  )
}
