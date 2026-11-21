import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"
import { cn } from '@/lib/cn'

// Ô nhập theo Figma: cao 52, bo viên thuốc ở chat / bo 16 ở form, viền border-default, chữ 16 (tránh iOS tự phóng to).
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        "h-13 w-full min-w-0 rounded-2xl border border-line bg-surface px-4 text-[16px] text-ink transition-colors outline-none placeholder:text-ink-2 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-bad-line aria-invalid:ring-3 aria-invalid:ring-bad-line/20",
        className
      )}
      {...props}
    />
  )
}

export { Input }
