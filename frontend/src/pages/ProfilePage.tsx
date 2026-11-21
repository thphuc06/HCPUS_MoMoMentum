import { useState } from 'react'
import { LogOut, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogClose,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useAuth } from '@/auth/AuthProvider'
import { useApi, useJars } from '@/api/ApiProvider'
import { ApiError } from '@/api/errors'
import { useChat } from '@/chat/ChatProvider'
import { usePhoneFrame } from '@/layout/FrameContext'
import { formatAppDate } from '@/lib/format'
import { displayName } from '@/lib/user'

// Figma S1 Hồ sơ (31:2754) là khung giữ chỗ; bản này có thông tin tài khoản, "Đặt lại dữ liệu" và đăng xuất.
export function ProfilePage() {
  const { session, signOut } = useAuth()
  const api = useApi()
  const jars = useJars()
  const chat = useChat()
  const frame = usePhoneFrame()
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const name = displayName(session?.email, session?.displayName) ?? 'Tài khoản'

  const reset = async () => {
    setBusy(true)
    setResult(null)
    try {
      const r = await api.resetDemo()
      chat.startNew() // dữ liệu hội thoại đã xóa theo: bắt đầu cuộc trò chuyện mới
      await jars.reload()
      setResult({
        ok: true,
        text: `Đã đặt lại: ${r.jars_count} hũ, ${r.transactions_count} giao dịch. Ngày mô phỏng ${formatAppDate(r.app_date)}.`,
      })
    } catch (e) {
      setResult({ ok: false, text: e instanceof ApiError ? e.message : 'Chưa đặt lại được. Thử lại sau ít phút.' })
    } finally {
      setBusy(false)
      setConfirming(false)
    }
  }

  return (
    <>
      <header className="px-4 pt-[max(16px,env(safe-area-inset-top))] pb-4">
        <h1 className="text-title font-bold text-ink">Hồ sơ</h1>
      </header>

      <div className="space-y-3 px-4">
        <section className="flex items-center gap-3 rounded-card bg-surface p-4 shadow-card" aria-label="Tài khoản">
          <span aria-hidden className="grid size-14 place-items-center rounded-full bg-brand text-section font-bold text-white">
            {name.charAt(0).toUpperCase()}
          </span>
          <div className="min-w-0">
            <p className="truncate text-subtitle font-semibold text-ink">{name}</p>
            <p className="truncate text-small text-ink-2" data-testid="profile-email">
              {session?.email}
            </p>
          </div>
        </section>

        <section className="rounded-card bg-surface p-4 shadow-card" aria-label="Dữ liệu demo">
          <h2 className="text-subtitle font-semibold text-ink">Dữ liệu demo</h2>
          <p className="mt-1 text-small text-ink-2">
            Ví này là mô phỏng. Đặt lại sẽ đưa hũ, giao dịch và cuộc trò chuyện của tài khoản này về trạng thái ban đầu.
          </p>
          <Button type="button" variant="outline" className="mt-3 w-full" onClick={() => setConfirming(true)} disabled={busy}>
            <RotateCcw className="size-5" aria-hidden />
            Đặt lại dữ liệu
          </Button>
          {result && (
            <p
              role={result.ok ? 'status' : 'alert'}
              className={`mt-3 rounded-2xl px-3 py-2 text-small font-semibold ${result.ok ? 'bg-ok-bg text-ok-fg' : 'bg-bad-bg text-bad-fg'}`}
            >
              {result.text}
            </p>
          )}
        </section>

        <Button type="button" variant="soft" className="w-full" onClick={signOut}>
          <LogOut className="size-5" aria-hidden />
          Đăng xuất
        </Button>
      </div>

      <AlertDialog open={confirming} onOpenChange={(o) => !busy && setConfirming(o)}>
        <AlertDialogContent container={frame}>
          <AlertDialogTitle>Đặt lại dữ liệu?</AlertDialogTitle>
          <AlertDialogDescription>
            Hũ, giao dịch và cuộc trò chuyện của tài khoản này sẽ quay về trạng thái ban đầu. Việc này không ảnh hưởng tài khoản khác.
          </AlertDialogDescription>
          <div className="mt-5 flex flex-col gap-3">
            <Button type="button" onClick={() => void reset()} disabled={busy} aria-busy={busy}>
              {busy ? 'Đang đặt lại…' : 'Đặt lại'}
            </Button>
            <AlertDialogClose render={<Button type="button" variant="outline" disabled={busy} />}>Hủy</AlertDialogClose>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
