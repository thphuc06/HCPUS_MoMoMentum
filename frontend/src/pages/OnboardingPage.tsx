import { useState } from 'react'
import { useNavigate } from 'react-router'
import { ArrowLeft, Info, MessageCircle, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { MoneyInput } from '@/components/MoneyInput'
import { ErrorState } from '@/components/StateViews'
import { Skeleton } from '@/components/ui/skeleton'
import { useApiResource } from '@/api/resource'
import { useOverview } from '@/api/OverviewProvider'
import { useWriteFlow } from '@/api/useWrite'
import { useChatLauncher } from '@/chat/launcher'
import { JarSplitEditor } from '@/features/jars/JarSplitEditor'
import { KnownItemsEditor } from '@/features/jars/KnownItemsEditor'
import { SplitProposalCard } from '@/features/jars/SplitProposalCard'
import { ObligationFormView } from '@/features/obligations/ObligationForm'
import { CYCLE_LABEL, KIND_LABEL } from '@/features/obligations/params'
import type { SplitProposalKnownItem } from '@/api/schemas'
import { formatVnd } from '@/lib/format'
import { cn } from '@/lib/cn'

// Gợi ý chọn nhanh ngày nhận lương (giao diện); ngày khác nhập tay 1 đến 31.
const QUICK_DAYS = [1, 5, 10, 15, 20, 25]

function Progress({ step }: { step: 1 | 2 | 3 }) {
  return (
    <div className="flex items-center gap-3" role="progressbar" aria-valuemin={1} aria-valuemax={3} aria-valuenow={step} aria-label={`Bước ${step} trên 3`}>
      <div className="flex flex-1 gap-1.5" aria-hidden>
        {[1, 2, 3].map((n) => (
          <span key={n} className={cn('h-1.5 flex-1 rounded-full', n <= step ? 'bg-brand' : 'bg-line')} />
        ))}
      </div>
      <span className="text-small font-semibold text-ink-2">Bước {step}/3</span>
    </div>
  )
}

function StepShell({ step, onBack, children }: { step: 1 | 2 | 3; onBack?: () => void; children: React.ReactNode }) {
  return (
    <div className="px-5 pt-[max(16px,env(safe-area-inset-top))] pb-10">
      <div className="mb-4 flex items-center gap-3">
        {onBack ? (
          <button type="button" aria-label="Quay lại bước trước" onClick={onBack} className="grid size-11 shrink-0 place-items-center rounded-full border border-line bg-surface">
            <ArrowLeft className="size-5" aria-hidden />
          </button>
        ) : (
          <span className="size-11 shrink-0" aria-hidden />
        )}
        <div className="min-w-0 flex-1">
          <Progress step={step} />
        </div>
      </div>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------- O1: lương và ngày nhận (bắt buộc)

function SalaryStep({ onDone, initialSalary, initialDay, name }: { onDone: () => void; initialSalary?: number; initialDay?: number; name: string }) {
  const launcher = useChatLauncher()
  const write = useWriteFlow()
  const [salary, setSalary] = useState(initialSalary ? String(initialSalary) : '')
  const [day, setDay] = useState<number | null>(initialDay ?? null)
  const [other, setOther] = useState(initialDay !== undefined && !QUICK_DAYS.includes(initialDay))
  const [otherText, setOtherText] = useState(initialDay !== undefined && !QUICK_DAYS.includes(initialDay) ? String(initialDay) : '')
  const salaryNum = salary ? Number(salary) : 0
  const valid = salaryNum > 0 && day !== null && day >= 1 && day <= 31

  const next = async () => {
    if (!valid || day === null) return
    const r = await write.submit('update_profile', { monthly_salary_vnd: salaryNum, payday_day: day })
    if (r) onDone()
  }

  return (
    <StepShell step={1}>
      <h1 className="text-title font-bold text-ink">Chào {name}, mình bắt đầu từ lương nhé</h1>
      <p className="mt-1 text-small text-ink-2">Chỉ cần lương và ngày nhận là bắt buộc. Mọi thứ khác khai dần được.</p>

      <MoneyInput className="mt-5" size="lg" label="Lương thực nhận mỗi tháng (bắt buộc)" value={salary} onChange={setSalary} />

      <p className="mt-5 mb-2 text-small font-semibold text-ink-2" id="payday-label">
        Ngày nhận lương (bắt buộc)
      </p>
      <div role="radiogroup" aria-labelledby="payday-label" className="flex flex-wrap gap-2.5">
        {QUICK_DAYS.map((d) => (
          <button
            key={d}
            type="button"
            role="radio"
            aria-checked={!other && day === d}
            onClick={() => {
              setDay(d)
              setOther(false)
            }}
            className={cn('h-12 min-w-12 rounded-2xl border px-4 text-subtitle font-bold', !other && day === d ? 'border-brand bg-brand text-white' : 'border-line bg-surface text-ink')}
          >
            {d}
          </button>
        ))}
        <button
          type="button"
          role="radio"
          aria-checked={other}
          onClick={() => {
            setOther(true)
            const n = Number(otherText)
            setDay(n >= 1 && n <= 31 ? n : null)
          }}
          className={cn('h-12 rounded-2xl border px-4 text-subtitle font-semibold', other ? 'border-brand bg-tint text-brand-text' : 'border-line bg-surface text-ink')}
        >
          Ngày khác
        </button>
      </div>
      {other && (
        <label className="mt-3 block">
          <span className="mb-1.5 block text-small font-semibold text-ink-2">Ngày trong tháng (1 đến 31)</span>
          <Input
            inputMode="numeric"
            value={otherText}
            onChange={(e) => {
              const t = e.target.value.replace(/\D/g, '').slice(0, 2)
              setOtherText(t)
              const n = Number(t)
              setDay(n >= 1 && n <= 31 ? n : null)
            }}
          />
        </label>
      )}
      <p className="mt-3 text-small text-ink-2">Khi lương về, bạn chỉ cần xác nhận một chạm để chia vào hũ.</p>

      <div className="mt-5 rounded-card bg-tint p-4">
        <p className="flex items-center gap-2 text-subtitle font-semibold text-brand-text">
          <MessageCircle className="size-5" aria-hidden />
          Hoặc khai bằng chat
        </p>
        <p className="mt-1 text-small text-ink-2">Gõ như nói chuyện, Yofina điền giúp và hỏi lại để bạn kiểm.</p>
        <Button type="button" variant="soft" size="sm" className="mt-2 bg-surface" onClick={() => launcher.open('Mình muốn khai lương và ngày nhận lương.')}>
          Mở chat để khai
        </Button>
      </div>

      {write.error && (
        <p role="alert" className="mt-4 rounded-2xl bg-bad-bg px-3 py-2 text-small font-semibold text-bad-fg">
          {write.error.message}
        </p>
      )}
      <Button type="button" className="mt-6 w-full" disabled={!valid || write.working} onClick={() => void next()} aria-busy={write.working}>
        {write.working ? 'Đang lưu…' : 'Tiếp tục'}
      </Button>
      <p className="mt-2 text-center text-note text-ink-2">Bấm Tiếp tục thì lương và ngày nhận mới được lưu.</p>
    </StepShell>
  )
}

// ---------------------------------------------------------------- O2: hũ và tỷ lệ chia

function JarsStep({ onNext, onBack, onSkip }: { onNext: () => void; onBack: () => void; onSkip: () => void }) {
  const ov = useOverview()
  const templates = useApiResource((api) => api.listJarTemplates(), [])
  const loading = ov.status === 'loading' || templates.status === 'loading'
  return (
    <StepShell step={2} onBack={onBack}>
      <h1 className="text-title font-bold text-ink">Chia lương vào các hũ</h1>
      <p className="mt-1 mb-4 text-small text-ink-2">Hệ thống đã gợi ý sẵn các hũ. Bạn sửa tỷ lệ được; tổng phải đúng 100%.</p>
      {loading && <Skeleton className="h-[320px] w-full rounded-card" role="status" aria-label="Đang tải các hũ" />}
      {ov.status === 'error' && !ov.data && <ErrorState error={ov.error} title="Chưa tải được các hũ" onRetry={() => void ov.reload()} />}
      {templates.status === 'error' && <ErrorState error={templates.error} title="Chưa tải được hũ mẫu" onRetry={() => void templates.reload()} />}
      {ov.data && templates.data && ov.data.jars.length === 0 && (
        <p role="status" className="rounded-card bg-warn-bg p-4 text-small text-ink">
          Tài khoản chưa có hũ nào. Hãy thêm hũ ở tab Hũ sau khi vào Tổng quan.
        </p>
      )}
      {ov.data && templates.data && ov.data.jars.length > 0 && (
        <JarSplitEditor
          jars={ov.data.jars}
          templates={templates.data.templates}
          submitLabel="Tiếp tục"
          onSaved={onNext}
          onUnchanged={onNext}
          onSkip={onSkip}
          skipLabel="Bỏ qua, dùng gợi ý này"
        />
      )}
    </StepShell>
  )
}

// ---------------------------------------------------------------- O3: chi phí cố định (tùy chọn)

function ObligationsStep({ onBack, onFinish }: { onBack: () => void; onFinish: () => void }) {
  const ov = useOverview()
  const list = useApiResource((api) => api.listObligations(), [])
  const [adding, setAdding] = useState(false)
  const [known, setKnown] = useState<SplitProposalKnownItem[]>([])
  const [saved, setSaved] = useState(false)
  // Đề xuất tỷ lệ do server tính từ nghĩa vụ đã khai (tự tải lại sau mỗi lần ghi) và khoản biết trước chưa lưu.
  const proposal = useApiResource((api) => api.proposeJarSplit(known.length > 0 ? { sinking_items: known } : {}), [known])
  const declared = (list.data?.obligations ?? []).filter((o) => o.source === 'declared')
  return (
    <StepShell step={3} onBack={onBack}>
      <h1 className="text-title font-bold text-ink">Chi phí cố định</h1>
      <p className="mt-1 mb-4 text-small text-ink-2">Khai dần được. Yofina dùng để biết tiền ra theo lịch và không gợi ý cắt khoản thiết yếu.</p>

      {list.status === 'loading' && <Skeleton className="h-24 w-full rounded-card" role="status" aria-label="Đang tải chi phí" />}
      {list.status === 'error' && <ErrorState error={list.error} title="Chưa tải được chi phí" onRetry={() => void list.reload()} />}
      {declared.length > 0 && (
        <ul className="divide-y divide-line rounded-card bg-surface px-4 shadow-card" aria-label="Chi phí đã khai">
          {declared.map((o) => (
            <li key={o.id} className="flex min-h-16 items-center justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <p className="truncate text-body font-semibold text-ink">{o.name}</p>
                <p className="text-small text-ink-2">
                  {KIND_LABEL[o.kind] ?? o.kind} · {CYCLE_LABEL[o.cycle] ?? o.cycle}
                </p>
              </div>
              <span className="num shrink-0 font-bold text-ink">{formatVnd(o.amount_vnd)}</span>
            </li>
          ))}
        </ul>
      )}

      {adding ? (
        <div className="mt-3 rounded-card bg-surface p-4 shadow-card">
          <ObligationFormView
            jars={ov.data?.jars ?? []}
            onSaved={() => setAdding(false)}
            onCancel={() => setAdding(false)}
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="mt-3 flex min-h-14 w-full items-center justify-center gap-2 rounded-card border-2 border-dashed border-brand text-subtitle font-semibold text-brand-text"
        >
          <Plus className="size-5" aria-hidden />
          Thêm khoản
        </button>
      )}

      <p className="mt-3 flex items-start gap-2 rounded-2xl bg-surface-2 p-3 text-small text-ink-2">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
        Khoản trả sau không cần khai: tự sinh khi bạn mua bằng hạn mức Trả sau.
      </p>

      <KnownItemsEditor items={known} onChange={setKnown} today={ov.data?.app_date} />

      {saved && (
        <p role="status" data-testid="split-saved" className="mt-4 rounded-2xl bg-ok-bg px-4 py-3 text-small font-semibold text-ok-fg">
          Đã lưu tỷ lệ mới. Dự báo đang tính lại theo tỷ lệ này.
        </p>
      )}
      {proposal.status === 'error' && !proposal.data && (
        <p className="mt-4 text-small text-ink-2" data-testid="split-proposal-error">
          Chưa tính được tỷ lệ đề xuất: {proposal.error.message}{' '}
          <button type="button" className="font-semibold text-brand-text underline" onClick={() => void proposal.reload()}>
            Thử lại
          </button>
        </p>
      )}
      {proposal.data && ov.data && (
        <SplitProposalCard
          key={`${proposal.data.status}:${JSON.stringify(proposal.data.params ?? null)}`}
          proposal={proposal.data}
          jars={ov.data.jars}
          onSaved={() => {
            setSaved(true)
            setKnown([])
          }}
        />
      )}

      <Button type="button" className="mt-6 w-full" onClick={onFinish}>
        {declared.length > 0 ? 'Xong, xem dự báo' : 'Xong'}
      </Button>
      {declared.length === 0 && (
        <Button type="button" variant="ghost" className="mt-2 w-full" onClick={onFinish}>
          Bỏ qua, khai sau
        </Button>
      )}
    </StepShell>
  )
}

/**
 * Onboarding O1–O3 (Figma 25:2327, 25:2391, 25:2508) cho tài khoản chưa khai (`profile.onboarded` false). Chỉ lương và
 * ngày nhận là bắt buộc: bấm Tiếp tục ở O1 là ghi `update_profile` (server tạo hồ sơ, hai hũ hệ thống và các hũ mẫu mặc định),
 * từ đó tài khoản vào được Tổng quan; O2 (`save_jars`) và O3 (`update_profile` nghĩa vụ) là tùy chọn, bỏ qua được.
 * Mọi thao tác ghi đi qua /confirmations -> /actions.
 */
export function OnboardingPage() {
  const navigate = useNavigate()
  const ov = useOverview()
  // Bước bắt đầu quyết định một lần khi dữ liệu tải xong: chưa khai thì O1; đã khai (mở lại giữa chừng) thì O2.
  const [step, setStep] = useState<1 | 2 | 3 | null>(null)
  const profile = ov.data?.profile

  if (ov.status === 'loading') return <Skeleton className="m-5 h-[420px] rounded-card" role="status" aria-label="Đang tải" />
  if (ov.status === 'error' && !ov.data) return <ErrorState className="p-5" error={ov.error} title="Chưa tải được tài khoản" onRetry={() => void ov.reload()} />
  if (!profile) return null
  const current = step ?? (profile.onboarded ? 2 : 1)
  const finish = () => navigate('/', { replace: true })

  if (current === 1) {
    return <SalaryStep name={profile.display_name} initialSalary={profile.monthly_salary_vnd} initialDay={profile.payday_day} onDone={() => setStep(2)} />
  }
  if (!profile.onboarded) {
    // Vừa ghi lương ở O1, đang chờ Tổng quan tải lại để thấy hồ sơ mới (hoặc tải lại lỗi).
    return ov.status === 'error' ? (
      <ErrorState className="p-5" error={ov.error} title="Chưa cập nhật được tài khoản" onRetry={() => void ov.reload()} />
    ) : (
      <Skeleton className="m-5 h-[420px] rounded-card" role="status" aria-label="Đang cập nhật tài khoản" />
    )
  }
  if (current === 2) return <JarsStep onBack={() => setStep(1)} onNext={() => setStep(3)} onSkip={() => setStep(3)} />
  return <ObligationsStep onBack={() => setStep(2)} onFinish={finish} />
}
