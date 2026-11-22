import { diffDays, formatDayMonth } from '@/lib/dates'

// Figma MiniTimeline (7:146): thanh từ hôm nay tới kỳ lương; đoạn xanh là còn tiền, đoạn cam là sau ngày dự kiến cạn.
// Vị trí chỉ để vẽ (đổi ngày thành tỷ lệ trên thanh); ngày cạn và ngày lương là số server trả.
export function MiniTimeline({ today, paydayDate, runoutDate }: { today: string; paydayDate: string; runoutDate?: string }) {
  const span = Math.max(1, diffDays(today, paydayDate))
  const runoutPos = runoutDate ? Math.min(1, Math.max(0, diffDays(today, runoutDate) / span)) : null
  const label = `Từ hôm nay ${formatDayMonth(today)} đến kỳ lương ${formatDayMonth(paydayDate)}${runoutDate ? `, dự kiến cạn ${formatDayMonth(runoutDate)}` : ''}`
  return (
    <div role="img" aria-label={label} data-testid="mini-timeline" className="mt-3">
      {runoutDate && runoutPos !== null && (
        <p className="text-small font-semibold text-bad-fg" style={{ marginLeft: `${Math.min(70, runoutPos * 100)}%` }}>
          Cạn dự kiến {formatDayMonth(runoutDate)}
        </p>
      )}
      <div className="relative mt-1 h-2.5 overflow-visible rounded-full bg-ok-line">
        {runoutPos !== null && (
          <>
            <div className="absolute inset-y-0 right-0 rounded-r-full bg-bad-line" style={{ left: `${runoutPos * 100}%` }} />
            <span
              className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface bg-bad-line"
              style={{ left: `${runoutPos * 100}%` }}
              aria-hidden
            />
          </>
        )}
      </div>
      <div className="mt-2 flex justify-between text-small">
        <span className="text-ink-2">Hôm nay {formatDayMonth(today)}</span>
        <span className="font-semibold text-ok-fg">Lương {formatDayMonth(paydayDate)}</span>
      </div>
    </div>
  )
}
