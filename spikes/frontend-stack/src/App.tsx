import { useMemo, useState } from 'react'
import { MotionConfig } from 'motion/react'
import NumberFlow from '@number-flow/react'
import {
  ArrowDownToLine,
  ArrowLeftRight,
  Eye,
  EyeOff,
  Home,
  MessageCircle,
  Moon,
  PiggyBank,
  ScanLine,
  Send,
  ShieldCheck,
  Sparkles,
  Sun,
  TrendingUp,
  UserRound,
} from 'lucide-react'
import { cn } from 'cn'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ForecastChart } from '@/components/ForecastChart'
import { JarCard } from '@/components/JarCard'
import { ResilienceGauge } from '@/components/ResilienceGauge'
import { ChatSheet } from '@/components/ChatSheet'
import { StatusChip, type Verdict } from '@/components/StatusChip'
import { makeForecast, jarIds, jarBalance } from '@/lib/forecast-data'
import { diffDays, formatDayMonth, formatVNDShort } from '@/lib/format'
import { BlockRenderer } from '@/blocks/registry'
import { sampleBlocks } from '@/blocks/fixtures'

const JAR_COLOR: Record<string, string> = { an_uong: '#4338ca', di_lai: '#0e9f78', giai_tri: '#c98500' }

function verdictOf(f: ReturnType<typeof makeForecast>): { v: Verdict; label: string } {
  if (!f.runout.date_p50) return { v: 'enough', label: 'Đủ tới kỳ lương' }
  const early = diffDays(f.runout.date_p50, f.payday)
  if (early <= 3) return { v: 'tight', label: `Sát, cạn sớm ${early} ngày` }
  return { v: 'short', label: `Cạn sớm ${early} ngày` }
}

const QUICK = [
  { icon: Send, label: 'Chuyển tiền' },
  { icon: ScanLine, label: 'Quét QR' },
  { icon: ArrowLeftRight, label: 'Giữa hũ' },
  { icon: ShieldCheck, label: 'Kiểm tra' },
  { icon: ArrowDownToLine, label: 'Tiền vào' },
] as const

function initialDark() {
  try {
    const p = new URLSearchParams(location.search).get('theme')
    if (p) return p === 'dark'
  } catch {
    /* ignore */
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

export default function App() {
  const [dark, setDark] = useState(() => {
    const d = initialDark()
    document.documentElement.classList.toggle('dark', d)
    return d
  })
  const [hidden, setHidden] = useState(false)
  const [balance, setBalance] = useState(12_480_000)
  const [chatOpen, setChatOpen] = useState(false)
  const [jar, setJar] = useState('an_uong')
  const [whatIf, setWhatIf] = useState(false)
  const [score, setScore] = useState(68)
  const showBlocks = new URLSearchParams(location.search).has('blocks')

  const forecasts = useMemo(() => Object.fromEntries(jarIds().map((id) => [id, makeForecast(id, id === 'an_uong')])), [])
  const f = forecasts[jar]
  const anUong = forecasts.an_uong
  const runoutNow = (whatIf && f.scenario ? f.scenario.runout : f.runout).date_p50
  const daysToRunout = runoutNow ? diffDays(f.today, runoutNow) : null

  const toggleDark = () => {
    const d = !dark
    setDark(d)
    document.documentElement.classList.toggle('dark', d)
  }

  return (
    <MotionConfig reducedMotion="user">
      <div className="mx-auto min-h-dvh w-full max-w-[430px] bg-background pb-[calc(104px+env(safe-area-inset-bottom))]">
        <header className="flex items-center justify-between px-5 pb-2 pt-[max(20px,env(safe-area-inset-top))]">
          <div className="flex items-center gap-3">
            <div className="grid size-11 place-items-center rounded-full bg-primary text-[15px] font-extrabold text-primary-foreground" aria-hidden>
              M
            </div>
            <div className="leading-tight">
              <p className="text-[13px] text-muted-foreground">Chào buổi sáng</p>
              <p className="text-[17px] font-bold">Minh Anh</p>
            </div>
          </div>
          <button
            type="button"
            onClick={toggleDark}
            aria-label={dark ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'}
            className="grid size-11 place-items-center rounded-full bg-card text-foreground shadow-sm ring-1 ring-border/60"
          >
            {dark ? <Sun className="size-5" /> : <Moon className="size-5" />}
          </button>
        </header>

        <main className="space-y-5 px-4 pt-2">
          {/* số dư + hành động nhanh */}
          <section className="rounded-[28px] bg-primary p-5 text-primary-foreground shadow-[0_18px_40px_-20px_rgba(67,56,202,0.65)]">
            <div className="flex items-center justify-between">
              <p className="text-[13px] font-semibold opacity-85">Tổng số dư</p>
              <button type="button" onClick={() => setHidden((h) => !h)} aria-label={hidden ? 'Hiện số dư' : 'Ẩn số dư'} className="grid size-9 place-items-center rounded-full bg-white/15">
                {hidden ? <EyeOff className="size-[18px]" /> : <Eye className="size-[18px]" />}
              </button>
            </div>
            <div className="mt-2 h-[46px]" data-testid="balance">
              {hidden ? (
                <span className="text-[34px] font-extrabold leading-[46px] tracking-widest">••••••••</span>
              ) : (
                <NumberFlow
                  value={balance}
                  locales="vi-VN"
                  format={{ maximumFractionDigits: 0 }}
                  suffix={' ₫'}
                  className="num text-[36px] font-extrabold leading-[46px] tracking-tight"
                />
              )}
            </div>
            <p className="mt-1 text-[12px] opacity-80">Ví mô phỏng · dữ liệu minh họa</p>
            <div className="mt-5 grid grid-cols-5">
              {QUICK.map(({ icon: Icon, label }) => (
                <button
                  key={label}
                  type="button"
                  onClick={label === 'Tiền vào' ? () => setBalance((b) => b + 15_000_000) : undefined}
                  className="flex flex-col items-center gap-1.5 rounded-2xl py-1 active:scale-95"
                >
                  <span className="grid size-12 place-items-center rounded-2xl bg-white/16 ring-1 ring-white/20">
                    <Icon className="size-[22px]" aria-hidden />
                  </span>
                  <span className="whitespace-nowrap text-[11px] font-semibold leading-tight">{label}</span>
                </button>
              ))}
            </div>
          </section>

          {/* câu "nhìn trước" */}
          <section className="flex items-start gap-3 rounded-3xl bg-card p-4 ring-1 ring-border/60">
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-secondary text-secondary-foreground">
              <Sparkles className="size-[18px]" aria-hidden />
            </span>
            <p className="text-[14.5px] leading-snug">
              Hũ <b>Ăn uống</b> dự kiến cạn ngày <b>{formatDayMonth(anUong.runout.date_p50!)}</b>, còn{' '}
              <b>{diffDays(anUong.runout.date_p50!, anUong.payday)} ngày</b> nữa mới tới lương ({formatDayMonth(anUong.payday)}).
              <button type="button" className="ml-1 font-bold text-primary" onClick={() => setChatOpen(true)}>
                Hỏi vì sao
              </button>
            </p>
          </section>

          {/* hũ */}
          <section>
            <div className="mb-2 flex items-baseline justify-between px-1">
              <h2 className="text-[18px] font-extrabold">Hũ của bạn</h2>
              <span className="text-[13px] font-semibold text-primary">Xem tất cả</span>
            </div>
            <div className="-mx-4 flex snap-x snap-mandatory gap-3 overflow-x-auto scroll-px-4 px-4 pb-2 [scrollbar-width:none]" data-testid="jar-row">
              {jarIds().map((id) => {
                const fc = forecasts[id]
                const { v, label } = verdictOf(fc)
                return (
                  <JarCard
                    key={id}
                    name={fc.jar_name}
                    balance={jarBalance(id)}
                    plan={4_000_000}
                    forecastLevel={v === 'short' ? 300_000 : v === 'tight' ? 700_000 : 1_100_000}
                    status={v}
                    statusLabel={label}
                    color={JAR_COLOR[id]}
                    className="w-[168px] shrink-0 snap-start"
                  />
                )
              })}
            </div>
          </section>

          {/* biểu đồ dự báo */}
          <section className="rounded-[28px] bg-card p-4 shadow-sm ring-1 ring-border/60" data-testid="forecast-card">
            <div className="mb-3 flex items-center justify-between gap-2">
              <h2 className="text-[18px] font-extrabold">Nhìn trước 30 ngày</h2>
              <StatusChip verdict={verdictOf(f).v}>{verdictOf(f).label}</StatusChip>
            </div>
            <Tabs
              value={jar}
              onValueChange={(v) => {
                setJar(String(v))
                setWhatIf(false)
              }}
            >
              <TabsList className="mb-3 h-11 w-full rounded-2xl p-1">
                {jarIds().map((id) => (
                  <TabsTrigger key={id} value={id} className="h-full rounded-xl text-[13.5px] font-semibold">
                    {forecasts[id].jar_name}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <ForecastChart data={f} showScenario={whatIf && !!f.scenario} height={236} />
            <div className="mt-3 flex items-center justify-between gap-3 rounded-2xl bg-muted px-4 py-3">
              <div>
                <p className="text-[12px] text-muted-foreground">Còn đến ngày cạn</p>
                <p className="text-[22px] font-extrabold leading-tight">
                  {daysToRunout === null ? (
                    'Đủ tới lương'
                  ) : (
                    <>
                      <NumberFlow value={daysToRunout} className="num" /> ngày
                    </>
                  )}
                </p>
              </div>
              {f.scenario ? (
                <Button
                  onClick={() => setWhatIf((w) => !w)}
                  variant={whatIf ? 'default' : 'secondary'}
                  className="h-11 rounded-full px-4 text-[13.5px] font-bold"
                  data-testid="whatif-toggle"
                >
                  {whatIf ? 'Bỏ kịch bản' : 'Mua tai nghe 1,2 triệu?'}
                </Button>
              ) : (
                <span className="text-[12px] text-muted-foreground">Kịch bản what-if có ở hũ Ăn uống</span>
              )}
            </div>
            <p className="num mt-2 text-[12px] text-muted-foreground">
              Dự báo mô phỏng (dữ liệu giả). Tiền dự kiến ra/vào: {formatVNDShort(f.events.reduce((s, e) => s + e.amount_vnd, 0))}.
            </p>
          </section>

          {/* điểm chống chịu */}
          <section className="rounded-[28px] bg-card p-5 shadow-sm ring-1 ring-border/60">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-[18px] font-extrabold">Điểm chống chịu</h2>
              <Button
                variant="secondary"
                className="h-9 rounded-full px-3 text-[12.5px] font-bold"
                onClick={() => setScore((s) => (s === 68 ? 41 : 68))}
                data-testid="score-toggle"
              >
                {score === 68 ? 'Mất việc 2 tháng?' : 'Về hiện tại'}
              </Button>
            </div>
            <ResilienceGauge
              score={score}
              parts={score === 68 ? { save: 72, spend: 64, borrow: 80, plan: 55 } : { save: 38, spend: 52, borrow: 61, plan: 30 }}
            />
          </section>

          {showBlocks && (
            <section className="space-y-3" data-testid="blocks-demo">
              <h2 className="px-1 text-[18px] font-extrabold">Khối UI từ JSON (registry)</h2>
              {sampleBlocks().map((b, i) => (
                <BlockRenderer key={i} raw={b} />
              ))}
            </section>
          )}
        </main>

        {/* thanh tab dưới 5 mục, nút giữa nổi */}
        <nav
          className="fixed inset-x-0 bottom-0 z-40 mx-auto max-w-[430px] border-t border-border/70 bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
          aria-label="Điều hướng chính"
        >
          <ul className="grid grid-cols-5 items-end px-2 pt-2 pb-2">
            {[
              { icon: Home, label: 'Tổng quan', active: true },
              { icon: PiggyBank, label: 'Hũ' },
              { icon: MessageCircle, label: 'Hỏi Yofina', center: true },
              { icon: TrendingUp, label: 'Nhìn trước' },
              { icon: UserRound, label: 'Hồ sơ' },
            ].map(({ icon: Icon, label, active, center }) => (
              <li key={label} className="flex justify-center">
                {center ? (
                  <button
                    type="button"
                    onClick={() => setChatOpen(true)}
                    aria-label="Hỏi Yofina"
                    data-testid="open-chat"
                    className="-mt-7 flex flex-col items-center gap-1 active:scale-95"
                  >
                    <span className="grid size-[58px] place-items-center rounded-full bg-primary text-primary-foreground shadow-[0_10px_24px_-6px_rgba(67,56,202,0.7)] ring-4 ring-card">
                      <Icon className="size-[26px]" aria-hidden />
                    </span>
                    <span className="text-[11px] font-bold text-primary">{label}</span>
                  </button>
                ) : (
                  <button type="button" className={cn('flex min-h-12 min-w-14 flex-col items-center justify-center gap-0.5', active ? 'text-primary' : 'text-muted-foreground')} aria-current={active ? 'page' : undefined}>
                    <Icon className="size-[22px]" aria-hidden />
                    <span className={cn('text-[11px]', active ? 'font-bold' : 'font-semibold')}>{label}</span>
                  </button>
                )}
              </li>
            ))}
          </ul>
        </nav>

        <ChatSheet open={chatOpen} onOpenChange={setChatOpen} />
      </div>
    </MotionConfig>
  )
}
