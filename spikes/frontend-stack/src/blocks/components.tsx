import { useState } from 'react'
import { Check, Undo2 } from 'lucide-react'
import NumberFlow from '@number-flow/react'
import { Button } from '@/components/ui/button'
import { ForecastChart } from '@/components/ForecastChart'
import { JarCard } from '@/components/JarCard'
import { StatusChip } from '@/components/StatusChip'
import { formatDayMonth, formatVND } from '@/lib/format'
import type { AffordabilityCard, Confirm, ForecastTimeline, JarSummary } from './schemas'

const JAR_COLORS: Record<string, string> = { an_uong: '#4338ca', di_lai: '#0e9f78', giai_tri: '#c98500' }

function AiTag() {
  return (
    <span className="rounded-full bg-secondary px-2 py-0.5 text-[10.5px] font-bold uppercase tracking-wide text-secondary-foreground">
      AI
    </span>
  )
}

export function ForecastTimelineView({ block }: { block: ForecastTimeline }) {
  const d = block.data
  const [after, setAfter] = useState(false)
  const hasScn = !!d.scenario
  return (
    <section className="w-full rounded-3xl bg-card p-4 shadow-sm ring-1 ring-border/60" data-block="forecast_timeline">
      <header className="mb-1 flex items-center justify-between gap-2">
        <h3 className="text-[15px] font-bold">Dự báo hũ {d.jar_name}</h3>
        <AiTag />
      </header>
      <p className="mb-2 text-[13px] text-muted-foreground">{block.fallback_text}</p>
      <ForecastChart
        data={{ ...d, scenario: d.scenario ?? null }}
        showScenario={hasScn && after}
        height={200}
        ariaLabel={block.fallback_text}
      />
      {hasScn && (
        <div className="mt-3 flex items-center gap-2">
          <Button size="sm" variant={after ? 'default' : 'secondary'} className="rounded-full" onClick={() => setAfter((v) => !v)}>
            {after ? 'Bỏ kịch bản' : `Thử: ${d.scenario!.label}`}
          </Button>
        </div>
      )}
    </section>
  )
}

export function JarSummaryView({ block }: { block: JarSummary }) {
  const d = block.data
  return (
    <div className="w-full max-w-[220px]" data-block="jar_summary">
      <JarCard
        name={d.name}
        balance={d.balance_vnd}
        plan={d.plan_vnd}
        forecastLevel={d.forecast_level_vnd}
        status={d.status}
        statusLabel={d.status_label}
        color={JAR_COLORS[d.jar_id] ?? '#4338ca'}
      />
    </div>
  )
}

export function AffordabilityCardView({ block }: { block: AffordabilityCard }) {
  const d = block.data
  const title = { enough: 'Đủ để mua', tight: 'Sát, cân nhắc', short: 'Hụt, chưa nên' }[d.verdict]
  return (
    <section className="w-full rounded-3xl bg-card p-4 shadow-sm ring-1 ring-border/60" data-block="affordability_card">
      <header className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-[15px] font-bold">{d.item_label}</h3>
        <AiTag />
      </header>
      <StatusChip verdict={d.verdict}>{title}</StatusChip>
      <p className="mt-3 text-[12.5px] text-muted-foreground">Thanh toán bằng {d.pay_with_label}</p>
      <ul className="mt-1 divide-y divide-border/70 text-[14px]">
        {d.cost_lines.map((l) => (
          <li key={l.label} className="flex items-center justify-between py-1.5">
            <span>{l.label}</span>
            <span className="num font-semibold">{formatVND(l.amount_vnd)}</span>
          </li>
        ))}
        <li className="flex items-center justify-between py-2 text-[15px] font-bold">
          <span>Tổng chi phí thật</span>
          <span className="num">{formatVND(d.total_real_cost_vnd)}</span>
        </li>
      </ul>
      {d.gap && (
        <p className="mt-1 rounded-2xl bg-warn-soft px-3 py-2 text-[13px] leading-snug text-warn-ink">
          Hũ có thể thiếu <b className="num">{formatVND(d.gap.amount_vnd)}</b> trước ngày {formatDayMonth(d.gap.when)}
          {d.runout_shift_days ? `; ngày cạn dịch sớm ${Math.abs(d.runout_shift_days)} ngày` : ''}.
        </p>
      )}
      <ul className="mt-3 space-y-1 text-[12.5px] text-muted-foreground">
        {d.rules.map((r) => (
          <li key={r.id} className="flex items-start gap-1.5">
            <span aria-hidden className={r.passed ? 'text-ok-ink' : 'text-warn-ink'}>
              {r.passed ? '✓' : '!'}
            </span>
            <span>{r.label}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function ConfirmView({ block }: { block: Confirm }) {
  const d = block.data
  const [state, setState] = useState<'idle' | 'ok' | 'cancel'>('idle')
  return (
    <section className="w-full rounded-3xl bg-card p-4 shadow-sm ring-1 ring-primary/30" data-block="confirm">
      <header className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-[15px] font-bold">Xác nhận trước khi thực hiện</h3>
        <AiTag />
      </header>
      <p className="text-[14px] leading-snug">{d.summary}</p>
      <ul className="mt-3 space-y-2">
        {d.jars.map((j) => (
          <li key={j.jar_id} className="flex items-center justify-between rounded-2xl bg-muted px-3 py-2 text-[13.5px]">
            <span className="font-semibold">{j.jar_name}</span>
            <span className="num text-muted-foreground">
              {formatVND(j.before_vnd)} → <b className="text-foreground">{state === 'ok' ? <NumberFlow value={j.after_vnd} locales="vi-VN" format={{ maximumFractionDigits: 0 }} suffix={' ₫'} /> : formatVND(j.after_vnd)}</b>
            </span>
          </li>
        ))}
      </ul>
      {d.runout_before && d.runout_after && (
        <p className="mt-2 text-[12.5px] text-muted-foreground">
          Ngày cạn dự kiến: {formatDayMonth(d.runout_before)} → {formatDayMonth(d.runout_after)}
          {d.reversible ? ' · có thể hoàn tác' : ''}
        </p>
      )}
      <div className="mt-3">
        {state === 'idle' ? (
          <div className="flex gap-2">
            <Button className="h-11 flex-1 rounded-2xl text-[14px] font-bold" onClick={() => setState('ok')}>
              {d.approve_label}
            </Button>
            <Button variant="secondary" className="h-11 rounded-2xl" onClick={() => setState('cancel')}>
              Hủy
            </Button>
          </div>
        ) : state === 'ok' ? (
          <p className="flex items-center gap-1.5 text-[13.5px] font-semibold text-ok-ink">
            <Check className="size-4" aria-hidden /> Đã xác nhận (mô phỏng, chưa gửi về agent)
          </p>
        ) : (
          <p className="flex items-center gap-1.5 text-[13.5px] font-semibold text-muted-foreground">
            <Undo2 className="size-4" aria-hidden /> Đã hủy
          </p>
        )}
      </div>
    </section>
  )
}
