import { useEffect, useRef, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { useApi, useRefreshAfterWrite } from '@/api/ApiProvider'
import { ApiError } from '@/api/errors'
import type { DataDeletion } from '@/api/phase5Schemas'
import type { PreviewState } from '@/api/useConfirmPreview'
import { useChat } from '@/chat/ChatProvider'
import { PreviewPanel } from '@/components/PreviewPanel'
import { Button } from '@/components/ui/button'
import { Drawer, DrawerContent, DrawerDescription, DrawerHeader, DrawerTitle } from '@/components/ui/drawer'
import { usePhoneFrame } from '@/layout/FrameContext'
import { unmuteAll } from '@/lib/nudgePrefs'

// "Xóa dữ liệu của tôi": như mọi thao tác ghi khác, đi qua token xác nhận do server cấp (ADR-0002). Mở ra thì xin bản xem trước
// (`POST /me/delete-data/confirmations`, không ghi gì); bấm xác nhận cuối thì xin token mới (token sống vài phút) rồi
// `POST /me/delete-data` kèm token. Server xóa tệp đã nạp (S3), bộ nhớ của trợ lý (Memory) và dữ liệu Aurora; không hoàn tác được.

const STEP_LABEL = { s3: 'Tệp đã nạp', memory: 'Bộ nhớ của trợ lý', aurora: 'Hồ sơ, hũ, sổ cái, hội thoại' } as const
const STEP_STATUS = { pending: 'Đang chờ', done: 'Đã xóa', failed: 'Chưa xóa được', skipped: 'Không có gì để xóa' } as const

const asApiError = (e: unknown) => (e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0))

function resultText(r: DataDeletion): { ok: boolean; text: string } {
  switch (r.status) {
    case 'done':
      return { ok: true, text: 'Đã xóa toàn bộ dữ liệu của bạn. Tài khoản đăng nhập vẫn còn và giờ như tài khoản mới.' }
    case 'partial':
      return { ok: false, text: 'Đã xóa dữ liệu chính, còn một phần chưa xóa được. Bấm “Xóa tiếp” để làm nốt.' }
    case 'running':
      return { ok: false, text: 'Lần xóa trước vẫn đang chạy. Đợi vài giây rồi bấm “Xóa tiếp” để xem kết quả.' }
    case 'failed':
      return { ok: false, text: 'Chưa xóa được hồ sơ, hũ và sổ cái. Thử lại sau ít phút; các bước bên dưới cho biết phần nào đã xóa.' }
  }
}

export function DeleteDataSection() {
  const api = useApi()
  const refresh = useRefreshAfterWrite()
  const chat = useChat()
  const frame = usePhoneFrame()
  const [open, setOpen] = useState(false)
  const [preview, setPreview] = useState<PreviewState>({ status: 'idle', preview: null, error: null })
  const [agree, setAgree] = useState(false)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [result, setResult] = useState<DataDeletion | null>(null)
  const seq = useRef(0)

  // Bản xem trước do server tính mỗi lần mở; token trong đó bị bỏ (lúc xác nhận xin token mới).
  useEffect(() => {
    if (!open) return
    const mine = ++seq.current
    setPreview({ status: 'loading', preview: null, error: null })
    api.createDeleteDataConfirmation().then(
      (r) => mine === seq.current && setPreview({ status: 'ready', preview: r.preview ?? null, error: null }),
      (e) => mine === seq.current && setPreview({ status: 'error', preview: null, error: asApiError(e) }),
    )
  }, [api, open])

  const start = () => {
    setAgree(false)
    setError(null)
    setOpen(true)
  }

  const confirm = async () => {
    setWorking(true)
    setError(null)
    try {
      const issued = await api.createDeleteDataConfirmation()
      const r = await api.deleteMyData(issued.confirm_token)
      setResult(r)
      setOpen(false)
      if (r.status === 'done' || r.status === 'partial') {
        unmuteAll() // tùy chọn hiển thị lưu trên thiết bị cũng thuộc dữ liệu của người dùng
        chat.startNew() // hội thoại đã bị xóa ở server: bắt đầu cuộc trò chuyện mới
        refresh()
      }
    } catch (e) {
      setError(asApiError(e))
    } finally {
      setWorking(false)
    }
  }

  const text = result ? resultText(result) : null
  const canRetry = result && (result.status === 'partial' || result.status === 'running' || result.status === 'failed')

  return (
    <section aria-labelledby="delete-data-heading" className="rounded-card bg-surface p-4 shadow-card">
      <h2 id="delete-data-heading" className="text-subtitle font-semibold text-ink">Xóa dữ liệu của tôi</h2>
      <p className="mt-1 text-small text-ink-2">
        Xóa hồ sơ, hũ, sổ cái, hội thoại, tệp đã nạp và bộ nhớ của trợ lý. Không hoàn tác được; tài khoản đăng nhập vẫn còn.
      </p>
      {text && (
        <div role={text.ok ? 'status' : 'alert'} data-testid="delete-result" className={`mt-3 rounded-2xl px-3 py-2 text-small ${text.ok ? 'bg-ok-bg text-ok-fg' : 'bg-warn-bg text-warn-fg'}`}>
          <p className="font-semibold">{text.text}</p>
          <dl className="mt-1 space-y-0.5">
            {(['s3', 'memory', 'aurora'] as const).map((k) => (
              <div key={k} className="flex justify-between gap-3">
                <dt>{STEP_LABEL[k]}</dt>
                <dd className="num">{STEP_STATUS[result!.steps[k].status]}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
      <Button type="button" variant="outline" className="mt-3 w-full text-bad-fg" onClick={start} disabled={working}>
        <Trash2 className="size-5" aria-hidden />
        {canRetry ? 'Xóa tiếp' : 'Xóa dữ liệu của tôi'}
      </Button>

      <Drawer open={open} onOpenChange={(o) => { if (!working) setOpen(o) }}>
        <DrawerContent container={frame} className="rounded-t-sheet bg-background pb-[max(16px,env(safe-area-inset-bottom))] shadow-sheet">
          <DrawerHeader>
            <DrawerTitle className="text-section font-bold">Xóa toàn bộ dữ liệu?</DrawerTitle>
            <DrawerDescription>Việc này không hoàn tác được.</DrawerDescription>
          </DrawerHeader>
          <div className="min-h-0 space-y-3 overflow-y-auto px-4 pt-3">
            <PreviewPanel state={preview} />
            {error && <p role="alert" className="rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">{error.message}</p>}
            <label className="flex min-h-11 items-start gap-3 text-small text-ink">
              <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-0.5 size-5 accent-[var(--brand-primary)]" />
              <span>Tôi hiểu dữ liệu sẽ bị xóa vĩnh viễn</span>
            </label>
            <div className="flex flex-col gap-2.5">
              <Button type="button" variant="destructive" disabled={!agree || working || preview.status !== 'ready'} aria-busy={working} onClick={() => void confirm()}>
                {working ? 'Đang xóa…' : 'Xóa vĩnh viễn'}
              </Button>
              <Button type="button" variant="outline" disabled={working} onClick={() => setOpen(false)}>Hủy</Button>
            </div>
          </div>
        </DrawerContent>
      </Drawer>
    </section>
  )
}
