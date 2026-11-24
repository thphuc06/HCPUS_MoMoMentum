import { ChevronRight } from 'lucide-react'
import { useInRouterContext, useNavigate } from 'react-router'
import { useIsOps } from '@/auth/AuthProvider'
import { useChatLauncher } from '@/chat/launcher'

/** Đường dẫn màn trace X1 của một lượt (chỉ nhóm `ops`). */
export const opsTracePath = (traceId: string) => `/ops/traces/${encodeURIComponent(traceId)}`

function OpenTraceButton({ traceId }: { traceId: string }) {
  const navigate = useNavigate()
  const launcher = useChatLauncher()
  return (
    <button
      type="button"
      onClick={() => {
        launcher.close()
        navigate(opsTracePath(traceId))
      }}
      aria-label={`Mở màn trace của lượt ${traceId}`}
      className="flex min-h-11 w-full items-center justify-between gap-3 rounded-xl bg-surface-2 px-3 text-left text-small text-ink-2"
    >
      <span>
        Mã trace <span className="num font-semibold text-ink" data-testid="explain-trace-id">{traceId}</span>
      </span>
      <span className="flex shrink-0 items-center gap-1 font-semibold text-brand-text">
        Mở trace
        <ChevronRight className="size-4" aria-hidden />
      </span>
    </button>
  )
}

/**
 * Hàng "Mã trace" của bảng "Vì sao". Tài khoản thuộc nhóm `ops` (đọc nhóm từ token) bấm vào để mở màn trace X1; người khác chỉ thấy
 * mã, không có lối vào (server cũng trả 403 cho `/ops/*`).
 */
export function TraceIdRow({ traceId }: { traceId: string }) {
  const inRouter = useInRouterContext()
  const ops = useIsOps()
  if (ops && inRouter) return <OpenTraceButton traceId={traceId} />
  return (
    <p className="text-small text-ink-2">
      Mã trace <span className="num font-semibold text-ink" data-testid="explain-trace-id">{traceId}</span>
    </p>
  )
}
