import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from '@/lib/cn'

// Nút theo Figma `Button` (5:26): dạng viên thuốc, 4 kiểu, chữ 16/20 đậm; vùng chạm tối thiểu 44 px.
const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center gap-2 rounded-full border border-transparent bg-clip-padding font-bold whitespace-nowrap transition-all outline-none select-none focus-visible:ring-3 focus-visible:ring-ring/50 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-5",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        outline: "border-primary bg-transparent text-brand-text hover:bg-tint",
        soft: "bg-tint text-brand-text hover:bg-tint/70",
        ghost: "text-brand-text hover:bg-tint",
        destructive: "bg-bad-bg text-bad-fg hover:bg-bad-bg/70",
        link: "text-brand-text underline-offset-4 hover:underline",
      },
      size: {
        default: "h-12 px-6 text-subtitle",
        sm: "h-11 px-4 text-small",
        icon: "size-11",
        "icon-lg": "size-12",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
