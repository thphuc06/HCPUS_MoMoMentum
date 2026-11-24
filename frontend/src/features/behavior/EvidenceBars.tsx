import type { CSSProperties } from 'react'
import type { BehaviorEvidence } from '@/contracts/blocks'
import { formatEvidenceValue, shareGapText, sharePairs, type SharePair } from './format'

// B3 "Cuối tuần / đầu kỳ lương có tiêu nhiều không" (spending-visualization.md §3, §4.1 P0): với mỗi cặp bằng chứng "phần chi"
// và "phần số ngày" của cùng nhận xét, hai thanh tỷ lệ chồng nhau: thanh trên là phần chi (tô đặc), thanh dưới là phần số ngày
// làm mốc "nếu chi đều" (gạch chéo, không chỉ khác màu). Bảng bằng chứng bên dưới vẫn giữ làm bản tương đương.

const BASE_HATCH: CSSProperties = {
  backgroundImage: 'repeating-linear-gradient(135deg, var(--text-secondary) 0 2px, transparent 2px 6px)',
}

function Bar({ pct, solid }: { pct: number; solid: boolean }) {
  return (
    <div className="mt-1 h-3 rounded-md bg-surface-2">
      <div
        className={solid ? 'h-full rounded-md bg-blue' : 'h-full rounded-md shadow-[inset_0_0_0_1px_var(--text-secondary)]'}
        style={{ width: `${pct}%`, ...(solid ? null : BASE_HATCH) }}
      />
    </div>
  )
}

function PairBars({ pair }: { pair: SharePair }) {
  const { share, base } = pair
  const gap = shareGapText(pair)
  const label = `${share.label} ${formatEvidenceValue(share)}; ${base.label} ${formatEvidenceValue(base)}. ${gap}`
  return (
    <div data-share-pair={share.key}>
      <div role="img" aria-label={label} className="space-y-2.5">
        <div aria-hidden>
          <div className="flex justify-between gap-3 text-small text-ink">
            <span>{share.label}</span>
            <b className="num font-bold">{formatEvidenceValue(share)}</b>
          </div>
          <Bar pct={pair.sharePct} solid />
        </div>
        <div aria-hidden>
          <div className="flex justify-between gap-3 text-small text-ink">
            <span>{base.label} (nếu chi đều)</span>
            <b className="num font-bold">{formatEvidenceValue(base)}</b>
          </div>
          <Bar pct={pair.basePct} solid={false} />
        </div>
      </div>
      <p className="mt-2 text-small font-semibold text-blue" aria-hidden>{gap}</p>
    </div>
  )
}

/** Thanh tỷ lệ cho các cặp bằng chứng của một nhận xét; không có cặp nào thì không vẽ gì. */
export function EvidenceBars({ evidence }: { evidence: readonly BehaviorEvidence[] }) {
  const pairs = sharePairs(evidence)
  if (pairs.length === 0) return null
  return (
    <div data-testid="evidence-bars" className="space-y-4">
      {pairs.map((p) => <PairBars key={p.share.key} pair={p} />)}
    </div>
  )
}
