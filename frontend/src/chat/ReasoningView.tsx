import { useEffect, useState } from 'react'
import { Lightbulb } from 'lucide-react'
import type { BlockViewProps } from '@/blocks/views'
import { Disclosure } from '@/components/ui/Disclosure'
import type { ReasoningBlock, ReasoningStep } from '@/contracts/blocks'
import { cn } from '@/lib/cn'
import { useEntranceMotion } from '@/lib/motion'

// Khối `reasoning` (phase 6, luồng K): agent cân nhắc như người tư vấn. Chữ là lập luận có cấu trúc do Analyst hoặc planner trả
// về như dữ liệu, đã qua kiểm số và căn cứ ở agent; giao diện không tự tính hay viết thêm gì ngoài vài nhãn cố định.
//
// Lần đầu thấy khối trong phiên: các bước hiện từng dòng (nhịp STEP_INTERVAL_MS), có kết luận thì sau đó thu lại thành câu kết
// luận và mục "Xem cách mình cân nhắc" (Disclosure). Giảm chuyển động hoặc đã thấy khối (tải lại trang, mở lại chat): hiện ngay
// trạng thái cuối. Vùng ngoài cùng là aria-live="polite" và tồn tại suốt, nên trình đọc màn hình đọc từng bước khi chúng hiện và
// đọc câu kết luận khi thu gọn; các bước đã thu vẫn nằm trong DOM (Disclosure), mở ra là đọc được.

/** Nhịp hiện từng bước khi được phép chuyển động. */
export const STEP_INTERVAL_MS = 900
/** Giữ bước cuối trên màn một lúc rồi mới thu gọn (để người dùng kịp đọc). */
export const COLLAPSE_AFTER_MS = 1400

const PERSONAL_TEXT: Record<'memory' | 'behavior', string> = {
  memory: 'điều bạn đã dặn',
  behavior: 'thói quen chi tiêu của bạn',
}

function StepItem({ step, fade }: { step: ReasoningStep; fade: boolean }) {
  return (
    <li data-step={step.step_id} className={cn('flex gap-2.5', fade && 'motion-fade')}>
      <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-brand" />
      <div className="min-w-0">
        <p className="text-small text-ink">{step.seen}</p>
        <p className="mt-0.5 text-small text-ink-2">
          {step.why} {step.effect}
        </p>
        <p className="mt-0.5 text-note text-ink-2" data-testid="reasoning-basis">
          Căn cứ: {step.basis.map((b) => b.label).join(' · ')}
        </p>
      </div>
    </li>
  )
}

function StepList({ steps, fade }: { steps: readonly ReasoningStep[]; fade: boolean }) {
  return (
    <ol className="space-y-3">
      {steps.map((s) => (
        <StepItem key={s.step_id} step={s} fade={fade} />
      ))}
    </ol>
  )
}

/** Số bước đang hiện và đã thu gọn được chưa, theo nhịp khi có chuyển động; không chuyển động thì hiện đủ ngay. */
function useReveal(total: number, complete: boolean, animate: boolean): { shown: number; settled: boolean } {
  const [shown, setShown] = useState(() => (animate ? Math.min(1, total) : total))
  // không có bước nào để hiện dần (chỉ có kết luận) thì không có gì phải chờ
  const [settled, setSettled] = useState(!animate || (complete && total === 0))
  useEffect(() => {
    if (!animate) return
    if (shown < total) {
      const t = setTimeout(() => setShown((n) => Math.min(n + 1, total)), STEP_INTERVAL_MS)
      return () => clearTimeout(t)
    }
    if (complete && !settled) {
      const t = setTimeout(() => setSettled(true), total ? COLLAPSE_AFTER_MS : 0)
      return () => clearTimeout(t)
    }
  }, [animate, shown, total, complete, settled])
  return animate ? { shown: Math.min(shown, total), settled } : { shown: total, settled: true }
}

export function ReasoningView({ block, blockId }: BlockViewProps<ReasoningBlock>) {
  const d = block.data
  const animate = useEntranceMotion(`reasoning:${blockId}`)
  const { shown, settled } = useReveal(d.steps.length, d.complete, animate)
  const done = d.complete && settled
  const conclusion = d.conclusion
  const personal = (conclusion?.personal ?? []).map((p) => PERSONAL_TEXT[p])

  return (
    <div aria-live="polite" data-block="reasoning" data-context={d.context} data-state={done ? (conclusion ? 'concluded' : 'done') : 'thinking'}>
      {done && conclusion ? (
        <section aria-label="Lời khuyên của Yofina" className="rounded-card bg-tint p-4">
          <p className="flex gap-2.5 text-body font-semibold text-ink" data-testid="reasoning-conclusion">
            <Lightbulb aria-hidden className="mt-0.5 size-5 shrink-0 text-brand-text" />
            <span>{conclusion.text}</span>
          </p>
          {personal.length > 0 && <p className="mt-1 pl-7.5 text-note text-ink-2">Có tính tới {personal.join(' và ')}.</p>}
          {d.steps.length > 0 && (
            <Disclosure label="Xem cách mình cân nhắc" className="mt-1 pl-6" panelClassName="pt-2 pb-1">
              <StepList steps={d.steps} fade={false} />
            </Disclosure>
          )}
        </section>
      ) : (
        <section aria-label="Cách Yofina cân nhắc" className="rounded-card bg-surface-2 p-4">
          <h3 className="text-small font-semibold text-ink-2">{done ? 'Mình đã cân nhắc' : 'Mình đang cân nhắc'}</h3>
          <div className="mt-2">
            <StepList steps={d.steps.slice(0, shown)} fade={animate} />
          </div>
        </section>
      )}
    </div>
  )
}
