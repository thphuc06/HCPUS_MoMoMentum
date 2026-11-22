import { useId } from 'react'
import { Input } from '@/components/ui/input'
import { formatVndNumber } from '@/lib/format'
import { cn } from '@/lib/cn'

const MAX_DIGITS = 11

/** Chỉ giữ chữ số, bỏ số 0 đầu, giới hạn độ dài (dưới trần numeric(14,0)). */
export function cleanDigits(raw: string): string {
  return raw.replace(/\D/g, '').replace(/^0+/, '').slice(0, MAX_DIGITS)
}

/**
 * Ô nhập tiền: người dùng gõ chữ số, ô hiện có dấu chấm nhóm nghìn; giá trị giữ dạng chuỗi chữ số (không dấu chấm).
 * Nhãn gắn bằng label thật để đọc màn hình và test tìm theo nhãn.
 */
export function MoneyInput({
  label,
  value,
  onChange,
  hint,
  error,
  className,
  size = 'md',
}: {
  label: string
  value: string
  onChange: (digits: string) => void
  hint?: string
  error?: string
  className?: string
  size?: 'md' | 'lg'
}) {
  const id = useId()
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1.5 block text-small font-semibold text-ink-2">
        {label}
      </label>
      <div className="relative">
        <Input
          id={id}
          inputMode="numeric"
          autoComplete="off"
          value={value ? formatVndNumber(Number(value)) : ''}
          onChange={(e) => onChange(cleanDigits(e.target.value))}
          aria-invalid={!!error}
          aria-describedby={hint || error ? `${id}-d` : undefined}
          placeholder="0"
          className={cn('num pr-10', size === 'lg' && 'h-16 text-[28px] font-extrabold')}
        />
        <span aria-hidden className="pointer-events-none absolute top-1/2 right-4 -translate-y-1/2 text-body font-semibold text-ink-2 underline">
          ₫
        </span>
      </div>
      {(hint || error) && (
        <p id={`${id}-d`} className={cn('mt-1 text-note', error ? 'font-semibold text-bad-fg' : 'text-ink-2')}>
          {error ?? hint}
        </p>
      )}
    </div>
  )
}
