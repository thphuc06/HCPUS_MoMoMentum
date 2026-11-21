import { cn } from 'cn'
import NumberFlow from '@number-flow/react'
import { JarGlass } from './JarGlass'
import { StatusChip, type Verdict } from './StatusChip'
import { formatVNDShort } from '@/lib/format'

export type JarCardProps = {
  name: string
  balance: number
  plan: number
  forecastLevel: number
  status: Verdict
  statusLabel: string
  color: string
  className?: string
}

export function JarCard({ name, balance, plan, forecastLevel, status, statusLabel, color, className }: JarCardProps) {
  return (
    <div className={cn('flex flex-col rounded-3xl bg-card p-4 shadow-[0_1px_2px_rgba(20,20,43,0.05),0_8px_24px_-12px_rgba(20,20,43,0.12)]', className)}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[15px] font-bold leading-tight">{name}</p>
          <p className="num mt-0.5 text-[12px] text-muted-foreground">Kế hoạch {formatVNDShort(plan)}</p>
        </div>
      </div>
      <div className="my-2 flex justify-center">
        <JarGlass level={balance / plan} forecast={forecastLevel / plan} color={color} size={72} />
      </div>
      <NumberFlow
        value={balance}
        locales="vi-VN"
        format={{ maximumFractionDigits: 0 }}
        suffix={' ₫'}
        className="num text-[17px] font-extrabold leading-tight tracking-tight"
      />
      <StatusChip verdict={status} className="mt-2 self-start">
        {statusLabel}
      </StatusChip>
    </div>
  )
}
