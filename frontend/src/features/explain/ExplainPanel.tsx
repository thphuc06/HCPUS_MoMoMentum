import { useEffect } from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/StateViews'
import { useApiResource } from '@/api/resource'
import { ExplainBody } from './ExplainBody'

/**
 * Bảng "Vì sao" (H4): phủ lên sheet chat. Gọi `GET /traces/{trace_id}` (bản ghi lượt của chính người dùng; của người khác
 * hay không tồn tại đều là TRACE_NOT_FOUND) rồi vẽ khối `explain` do server dựng. Không có số hay luật nào do giao diện nghĩ ra.
 */
export function ExplainPanel({ traceId, onClose }: { traceId: string; onClose: () => void }) {
  const trace = useApiResource((api) => api.getTrace(traceId), [traceId])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onClose])

  return (
    <div role="dialog" aria-modal="false" aria-label="Vì sao" data-testid="explain-panel" className="absolute inset-0 z-20 flex flex-col rounded-t-sheet bg-background">
      <header className="flex items-center justify-between gap-2 px-4 pt-4 pb-2">
        <h2 className="text-section font-bold text-ink">Vì sao</h2>
        <Button type="button" variant="soft" size="icon" aria-label="Đóng bảng Vì sao" className="bg-surface-2 text-ink" onClick={onClose}>
          <X className="size-5" aria-hidden />
        </Button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-6">
        {trace.status === 'loading' && (
          <div role="status" aria-busy="true" aria-label="Đang tải bảng Vì sao" className="space-y-3">
            <Skeleton className="h-6 w-2/3 rounded-xl" />
            <Skeleton className="h-28 w-full rounded-card" />
            <Skeleton className="h-20 w-full rounded-card" />
          </div>
        )}
        {trace.status === 'error' && <ErrorState error={trace.error} title="Chưa mở được bảng Vì sao" onRetry={() => void trace.reload()} />}
        {trace.status === 'ready' && <ExplainBody block={trace.data.explain} detail={trace.data.detail} />}
      </div>
    </div>
  )
}
