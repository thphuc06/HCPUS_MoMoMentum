import { AlertDialog as AlertDialogPrimitive } from "@base-ui/react/alert-dialog"
import { cn } from '@/lib/cn'

// Hộp thoại xác nhận (dùng cho "Đặt lại dữ liệu"). Portal vào khung điện thoại để không tràn ra ngoài khung.
function AlertDialog(props: AlertDialogPrimitive.Root.Props) {
  return <AlertDialogPrimitive.Root {...props} />
}

function AlertDialogContent({
  className,
  children,
  container,
  ...props
}: AlertDialogPrimitive.Popup.Props & { container?: HTMLElement | null }) {
  return (
    <AlertDialogPrimitive.Portal container={container ?? undefined}>
      <AlertDialogPrimitive.Backdrop className="absolute inset-0 z-50 bg-black/40 transition-opacity data-ending-style:opacity-0 data-starting-style:opacity-0" />
      <AlertDialogPrimitive.Viewport className="absolute inset-0 z-50 grid place-items-center p-6">
        <AlertDialogPrimitive.Popup
          className={cn(
            "w-full max-w-[340px] rounded-sheet bg-surface p-5 text-ink shadow-sheet outline-none transition-all data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0",
            className
          )}
          {...props}
        >
          {children}
        </AlertDialogPrimitive.Popup>
      </AlertDialogPrimitive.Viewport>
    </AlertDialogPrimitive.Portal>
  )
}

function AlertDialogTitle({ className, ...props }: AlertDialogPrimitive.Title.Props) {
  return <AlertDialogPrimitive.Title className={cn("text-section font-bold", className)} {...props} />
}

function AlertDialogDescription({ className, ...props }: AlertDialogPrimitive.Description.Props) {
  return <AlertDialogPrimitive.Description className={cn("mt-2 text-body text-ink-2", className)} {...props} />
}

function AlertDialogClose(props: AlertDialogPrimitive.Close.Props) {
  return <AlertDialogPrimitive.Close {...props} />
}

export { AlertDialog, AlertDialogContent, AlertDialogTitle, AlertDialogDescription, AlertDialogClose }
