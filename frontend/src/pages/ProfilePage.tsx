import { useState } from 'react'
import { Link } from 'react-router'
import { ChevronRight, LogOut, Pencil, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { MoneyInput } from '@/components/MoneyInput'
import { SimNote } from '@/components/SimNote'
import {
  AlertDialog,
  AlertDialogClose,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useAuth } from '@/auth/AuthProvider'
import { useApi, useRefreshAfterWrite } from '@/api/ApiProvider'
import { useOverview } from '@/api/OverviewProvider'
import { useWriteFlow } from '@/api/useWrite'
import { ApiError } from '@/api/errors'
import type { Profile } from '@/api/schemas'
import { useChat } from '@/chat/ChatProvider'
import { usePhoneFrame } from '@/layout/FrameContext'
import { formatAppDate, formatVnd } from '@/lib/format'
import { mutedKinds, unmuteAll } from '@/lib/nudgePrefs'
import { displayName } from '@/lib/user'

const RISK_LABEL: Record<string, string> = { low: 'Thấp', medium: 'Vừa', high: 'Cao' }

// Sửa lương, ngày nhận, tên hiển thị: chỉ gửi trường đã đổi (`update_profile`) qua /confirmations -> /actions.
function ProfileEditor({ profile, onDone }: { profile: Profile; onDone: () => void }) {
  const write = useWriteFlow()
  const [name, setName] = useState(profile.display_name)
  const [salary, setSalary] = useState(profile.monthly_salary_vnd ? String(profile.monthly_salary_vnd) : '')
  const [day, setDay] = useState(profile.payday_day ? String(profile.payday_day) : '')
  const dayNum = Number(day)
  const dayOk = day === '' || (Number.isInteger(dayNum) && dayNum >= 1 && dayNum <= 31)
  const params: Record<string, unknown> = {}
  if (name.trim() && name.trim() !== profile.display_name) params.display_name = name.trim()
  if (salary && Number(salary) !== profile.monthly_salary_vnd) params.monthly_salary_vnd = Number(salary)
  if (day && dayNum !== profile.payday_day) params.payday_day = dayNum
  const changed = Object.keys(params).length > 0

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!changed || !dayOk) return
    const r = await write.submit('update_profile', params)
    if (r) onDone()
  }

  return (
    <form onSubmit={save} noValidate className="mt-3 space-y-3" aria-label="Sửa thông tin khai báo">
      <label className="block">
        <span className="mb-1.5 block text-small font-semibold text-ink-2">Tên hiển thị</span>
        <Input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
      </label>
      <MoneyInput label="Lương thực nhận mỗi tháng" value={salary} onChange={setSalary} />
      <label className="block">
        <span className="mb-1.5 block text-small font-semibold text-ink-2">Ngày nhận lương (1 đến 31)</span>
        <Input inputMode="numeric" value={day} onChange={(e) => setDay(e.target.value.replace(/\D/g, '').slice(0, 2))} aria-invalid={!dayOk} />
        {!dayOk && <span className="mt-1 block text-note font-semibold text-bad-fg">Nhập ngày từ 1 đến 31</span>}
      </label>
      {write.error && (
        <p role="alert" className="rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
          {write.error.message}
        </p>
      )}
      <div className="flex gap-3">
        <Button type="submit" className="flex-1" disabled={!changed || !dayOk || write.working} aria-busy={write.working}>
          {write.working ? 'Đang lưu…' : 'Lưu thay đổi'}
        </Button>
        <Button type="button" variant="outline" onClick={onDone} disabled={write.working}>
          Hủy
        </Button>
      </div>
    </form>
  )
}

function NavRow({ to, label, hint }: { to: string; label: string; hint?: string }) {
  return (
    <Link to={to} className="flex min-h-14 items-center justify-between gap-3 py-2">
      <span>
        <span className="block text-body font-semibold text-ink">{label}</span>
        {hint && <span className="block text-small text-ink-2">{hint}</span>}
      </span>
      <ChevronRight className="size-5 shrink-0 text-ink-2" aria-hidden />
    </Link>
  )
}

// Figma S1 Hồ sơ (31:2754) là khung giữ chỗ; bản này có tên và thông tin khai báo (sửa được), lối vào Nghĩa vụ và Hũ,
// "Đặt lại dữ liệu" và đăng xuất.
export function ProfilePage() {
  const { session, signOut } = useAuth()
  const api = useApi()
  const refresh = useRefreshAfterWrite()
  const ov = useOverview()
  const chat = useChat()
  const frame = usePhoneFrame()
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [muted, setMuted] = useState(() => mutedKinds().length)
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const profile = ov.data?.profile
  const name = profile?.display_name ?? displayName(session?.email, session?.displayName) ?? 'Tài khoản'

  const reset = async () => {
    setBusy(true)
    setResult(null)
    try {
      const r = await api.resetDemo()
      chat.startNew() // dữ liệu hội thoại đã xóa theo: bắt đầu cuộc trò chuyện mới
      refresh()
      setResult({
        ok: true,
        text: `Đã đặt lại: ${r.jars_count} hũ, ${r.transactions_count} giao dịch. Ngày mô phỏng ${formatAppDate(r.app_date)}.${r.forecast_ready === false ? ' Dự báo đang được tính, mở lại Tổng quan sau ít giây.' : ''}`,
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
        <section className="rounded-card bg-surface p-4 shadow-card" aria-label="Tài khoản">
          <div className="flex items-center gap-3">
            <span aria-hidden className="grid size-14 place-items-center rounded-full bg-brand text-section font-bold text-white">
              {name.charAt(0).toUpperCase()}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-subtitle font-semibold text-ink" data-testid="profile-name">
                {name}
              </p>
              <p className="truncate text-small text-ink-2" data-testid="profile-email">
                {session?.email}
              </p>
            </div>
            {profile?.onboarded && !editing && (
              <Button type="button" variant="soft" size="sm" onClick={() => setEditing(true)}>
                <Pencil className="size-4" aria-hidden />
                Sửa
              </Button>
            )}
          </div>

          {profile && !editing && (
            <dl className="mt-3 space-y-1.5 border-t border-line pt-3 text-small" data-testid="profile-declared">
              <div className="flex justify-between gap-3">
                <dt className="text-ink-2">Lương thực nhận mỗi tháng</dt>
                <dd className="num font-semibold text-ink">{profile.monthly_salary_vnd ? formatVnd(profile.monthly_salary_vnd) : 'Chưa khai'}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-ink-2">Ngày nhận lương</dt>
                <dd className="font-semibold text-ink">{profile.payday_day ? `Ngày ${profile.payday_day} hằng tháng` : 'Chưa khai'}</dd>
              </div>
              {profile.risk_tolerance && (
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-2">Mức chấp nhận rủi ro</dt>
                  <dd className="font-semibold text-ink">{RISK_LABEL[profile.risk_tolerance] ?? profile.risk_tolerance}</dd>
                </div>
              )}
            </dl>
          )}
          {profile && !profile.onboarded && (
            <p className="mt-3 border-t border-line pt-3 text-small text-ink-2">
              Bạn chưa khai lương và ngày nhận. <Link to="/onboarding" className="font-semibold text-brand-text">Khai ngay</Link>
            </p>
          )}
          {profile && editing && <ProfileEditor profile={profile} onDone={() => setEditing(false)} />}
        </section>

        <section className="divide-y divide-line rounded-card bg-surface px-4 shadow-card" aria-label="Quản lý">
          <NavRow to="/obligations" label="Nghĩa vụ" hint="Tiền trọ, hóa đơn, thuê bao, khoản vay, Trả sau" />
          <NavRow to="/jars/edit" label="Thêm hoặc sửa hũ" hint="Tên, tỷ lệ chia lương" />
          <NavRow to="/income" label="Tiền vào" hint="Ghi nhận lương, gán Tiền vào khác vào hũ" />
          <NavRow to="/activity" label="Hoạt động" hint="Mọi giao dịch" />
        </section>

        {muted > 0 && (
          <section className="rounded-card bg-surface p-4 shadow-card" aria-label="Lời nhắc đã ẩn">
            <h2 className="text-subtitle font-semibold text-ink">Lời nhắc đã ẩn</h2>
            <p className="mt-1 text-small text-ink-2">Bạn đã chọn “Ít nhắc loại này” cho {muted} loại lời nhắc ở Tổng quan (lưu trên thiết bị này).</p>
            <Button
              type="button"
              variant="soft"
              size="sm"
              className="mt-2"
              onClick={() => {
                unmuteAll()
                setMuted(0)
              }}
            >
              Bật lại lời nhắc
            </Button>
          </section>
        )}

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

      <SimNote />

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
