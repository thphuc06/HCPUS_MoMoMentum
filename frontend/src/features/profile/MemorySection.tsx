import { useCallback, useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { useApi } from '@/api/ApiProvider'
import { ApiError } from '@/api/errors'
import type { MemoryClearResponse, MemoryKind, MemoryRecord } from '@/api/phase5Schemas'
import { ErrorState, ListSkeleton } from '@/components/StateViews'
import { Button } from '@/components/ui/button'
import { Disclosure } from '@/components/ui/Disclosure'
import { AlertDialog, AlertDialogClose, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { usePhoneFrame } from '@/layout/FrameContext'
import { formatDateTime } from '@/lib/format'

// "Bộ nhớ của tôi" (AgentCore Memory của chính người dùng, `GET /memory`): xem, xóa từng mục (`DELETE /memory/{id}`), xóa hết
// (`DELETE /memory`, hỏi lại trước). Không qua token vì không đụng tiền (hợp đồng). Bản ghi không có số dư hay giao dịch.

export const MEMORY_KIND_LABEL: Record<MemoryKind, string> = {
  preference: 'Sở thích bạn đã nói',
  fact: 'Điều bạn đã kể',
  session_summary: 'Tóm tắt cuộc trò chuyện',
  behavior: 'Thói quen chi tiêu (hệ thống ghi)',
  lesson: 'Điều trợ lý rút ra từ phản hồi của bạn',
}

type ListState = {
  status: 'loading' | 'ready' | 'error'
  records: MemoryRecord[]
  cursor?: string
  error: ApiError | null
  more: boolean
}

function useMemoryList() {
  const api = useApi()
  const [state, setState] = useState<ListState>({ status: 'loading', records: [], error: null, more: false })
  const load = useCallback(async (cursor?: string) => {
    setState((s) => (cursor ? { ...s, more: true } : { ...s, status: s.records.length ? s.status : 'loading', error: null }))
    try {
      const r = await api.listMemory({ limit: 50, cursor })
      setState((s) => ({ status: 'ready', records: cursor ? [...s.records, ...r.records] : r.records, cursor: r.next_cursor, error: null, more: false }))
    } catch (e) {
      setState((s) => ({ ...s, status: 'error', error: e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0), more: false }))
    }
  }, [api])
  useEffect(() => {
    void load()
  }, [load])
  const remove = (id: string) => setState((s) => ({ ...s, records: s.records.filter((r) => r.record_id !== id) }))
  return { ...state, reload: () => load(), loadMore: () => (state.cursor ? load(state.cursor) : Promise.resolve()), remove }
}

export function MemorySection() {
  const api = useApi()
  const frame = usePhoneFrame()
  const list = useMemoryList()
  const [deleting, setDeleting] = useState<string | null>(null)
  const [actionError, setActionError] = useState<ApiError | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [cleared, setCleared] = useState<MemoryClearResponse | null>(null)

  const deleteOne = async (record: MemoryRecord) => {
    setDeleting(record.record_id)
    setActionError(null)
    setCleared(null)
    try {
      await api.deleteMemoryRecord(record.record_id)
      list.remove(record.record_id)
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0)
      // Đã bị xóa ở nơi khác: coi như xong, bỏ khỏi danh sách.
      if (err.code === 'MEMORY_RECORD_NOT_FOUND') list.remove(record.record_id)
      else setActionError(err)
    } finally {
      setDeleting(null)
    }
  }

  const clearAll = async () => {
    setClearing(true)
    setActionError(null)
    try {
      const r = await api.clearMemory()
      setCleared(r)
      await list.reload()
    } catch (e) {
      setActionError(e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0))
    } finally {
      setClearing(false)
      setConfirmClear(false)
    }
  }

  const busy = clearing || deleting !== null
  return (
    <section aria-labelledby="memory-heading" className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 id="memory-heading" className="text-section font-bold text-ink">Bộ nhớ của tôi</h2>
        {list.records.length > 0 && (
          <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => setConfirmClear(true)}>Xóa hết</Button>
        )}
      </div>
      <Disclosure label="Bộ nhớ là gì?" className="-mt-2" panelClassName="pb-1 text-small text-ink-2">
        <p>Những điều trợ lý nhớ để không phải hỏi lại. Bộ nhớ không chứa số dư hay giao dịch của bạn.</p>
      </Disclosure>
      {list.status === 'loading' && <ListSkeleton rows={2} rowClass="h-14" label="Đang tải bộ nhớ" />}
      {list.status === 'error' && list.error && <ErrorState error={list.error} title="Chưa tải được bộ nhớ" onRetry={() => void list.reload()} />}
      {actionError && (
        <p role="alert" className="rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">{actionError.message}</p>
      )}
      {cleared && (
        <p role="status" className={`rounded-2xl px-3 py-2 text-small font-semibold ${cleared.failed > 0 ? 'bg-warn-bg text-warn-fg' : 'bg-ok-bg text-ok-fg'}`}>
          {cleared.failed > 0
            ? `Đã xóa ${cleared.deleted_records} mục, còn ${cleared.failed} mục chưa xóa được. Bấm Xóa hết lần nữa để xóa nốt.`
            : `Đã xóa ${cleared.deleted_records} mục nhớ và lịch sử trò chuyện ngắn hạn của trợ lý.`}
        </p>
      )}
      {list.status === 'ready' && list.records.length === 0 && (
        <p className="rounded-card bg-surface p-4 text-small text-ink-2 shadow-card" data-testid="memory-empty">Trợ lý chưa nhớ điều gì về bạn.</p>
      )}
      {list.records.length > 0 && (
        <ul aria-label="Các mục nhớ" className="divide-y divide-line rounded-card bg-surface px-4 shadow-card">
          {list.records.map((r) => (
            <li key={r.record_id} data-memory={r.kind} className="flex items-start gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-note font-semibold text-ink-2">{MEMORY_KIND_LABEL[r.kind]}</p>
                <p className="text-body text-ink">{r.text}</p>
                <p className="text-note text-ink-2">{formatDateTime(r.created_at)}</p>
              </div>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                aria-label={`Xóa mục nhớ: ${r.text}`}
                disabled={busy}
                aria-busy={deleting === r.record_id}
                onClick={() => void deleteOne(r)}
              >
                <Trash2 className="size-5" aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      )}
      {list.cursor && (
        <Button type="button" size="sm" variant="soft" disabled={list.more || busy} onClick={() => void list.loadMore()}>
          {list.more ? 'Đang tải…' : 'Xem thêm'}
        </Button>
      )}

      <AlertDialog open={confirmClear} onOpenChange={(o) => !clearing && setConfirmClear(o)}>
        <AlertDialogContent container={frame}>
          <AlertDialogTitle>Xóa hết bộ nhớ của trợ lý?</AlertDialogTitle>
          <AlertDialogDescription>
            Trợ lý sẽ quên mọi sở thích và điều bạn đã kể, và phải hỏi lại khi cần. Hũ, giao dịch và hội thoại đã lưu không đổi.
          </AlertDialogDescription>
          <div className="mt-5 flex flex-col gap-3">
            <Button type="button" variant="destructive" onClick={() => void clearAll()} disabled={clearing} aria-busy={clearing}>
              {clearing ? 'Đang xóa…' : 'Xóa hết bộ nhớ'}
            </Button>
            <AlertDialogClose render={<Button type="button" variant="outline" disabled={clearing} />}>Hủy</AlertDialogClose>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}
