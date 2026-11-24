// CHỈ cho `npm run dev:mock`: REST giả của các màn ví và dự báo (phase 2), có trạng thái trong bộ nhớ theo từng email đăng nhập.
// KHÔNG phải server thật và KHÔNG vào bundle production: số liệu mẫu lấy từ contracts/fixtures, dự báo là công thức
// đơn giản ở đây chỉ để thấy được giao diện. Email bắt đầu bằng "trang" cho tài khoản chưa khai (onboarding), bằng "moi"
// cho tài khoản ít dữ liệu ("ước lượng ban đầu").
import { createHash, randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import path from 'node:path'

const REST = path.resolve(import.meta.dirname, '../../../contracts/fixtures/rest')
const rest = (n: string) => JSON.parse(readFileSync(path.join(REST, `${n}.json`), 'utf8')) as any

export const APP_DATE = '2026-11-21'
const nowIso = () => new Date().toISOString().replace(/\.\d+Z$/, 'Z')
const DAY = 86_400_000
const addDays = (iso: string, n: number) => new Date(Date.parse(`${iso}T00:00:00Z`) + n * DAY).toISOString().slice(0, 10)
const diffDays = (a: string, b: string) => Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / DAY)
const vnd = (n: number) => `${n.toLocaleString('vi-VN')} ₫`

type Jar = any
type Account = {
  email: string
  profile: any
  jars: Jar[]
  system: Jar[]
  txs: any[]
  obligations: any[]
  credit: any | null
  fees: any[]
  payees: any[]
  salaryEvents: any[]
  initial: boolean
  tokens: Map<string, { hash: string; used: boolean; tool: string; params: any }>
  /** Đề nghị (confirm_block_id) đã thực hiện: mỗi đề nghị chỉ một lần (ALREADY_APPLIED). */
  applied: Set<string>
}

const accounts = new Map<string, Account>()

function canonical(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canonical).join(',')}]`
  if (v && typeof v === 'object') {
    const o = v as Record<string, unknown>
    return `{${Object.keys(o).sort().map((k) => `${JSON.stringify(k)}:${canonical(o[k])}`).join(',')}}`
  }
  return JSON.stringify(v)
}
export const paramsHash = (tool: string, params: unknown) => createHash('sha256').update(canonical({ tool, params })).digest('hex')

// ---- dữ liệu mẫu ----
const MERCHANTS: Record<string, string[]> = {
  an_uong: ['Highlands Coffee', 'Grab Food', 'Bách Hóa Xanh', 'Cơm tấm Ba Ghiền', 'Quán cơm'],
  di_lai: ['Grab', 'Xăng', 'Xe buýt'],
  hoa_don: ['Tiền nước', 'Internet'],
  giai_tri: ['Rạp chiếu phim', 'Spotify'],
}

function seedTransactions(jars: Jar[]): any[] {
  const out: any[] = []
  let seed = 7
  const rnd = () => (seed = (seed * 48271) % 2147483647) / 2147483647
  for (let d = 0; d < 20; d++) {
    for (const j of jars) {
      const pool = MERCHANTS[j.code]
      if (!pool || rnd() > (j.code === 'an_uong' ? 0.9 : 0.25)) continue
      const date = addDays(APP_DATE, -d - 1)
      out.push({
        id: randomUUID(),
        occurred_at: `${date}T0${Math.floor(rnd() * 9)}:${String(10 + Math.floor(rnd() * 49))}:00Z`,
        app_date: date,
        kind: 'expense',
        jar: j.code,
        amount_vnd: -Math.round((20 + rnd() * 140) / 1) * 1000,
        merchant: pool[Math.floor(rnd() * pool.length)],
        tx_type: 'food_drink',
        funding_source: 'jar',
        ...(rnd() > 0.85 ? { needs_review: true } : {}),
      })
    }
  }
  return out.sort((a, b) => (a.occurred_at < b.occurred_at ? 1 : -1))
}

function makeAccount(email: string): Account {
  const ov = rest('OverviewResponse.minh')
  const blank = email.startsWith('trang')
  const initial = email.startsWith('moi')
  const sys = ov.system_jars.map((j: Jar) => ({ ...j }))
  const jars: Jar[] = blank ? [] : ov.jars.map((j: Jar) => ({ ...j }))
  return {
    email,
    profile: blank ? { display_name: email.split('@')[0], onboarded: false } : { ...ov.profile },
    jars,
    system: blank ? [] : sys,
    txs: blank ? [] : seedTransactions(jars),
    obligations: blank ? [] : rest('ObligationsResponse.active').obligations.map((o: any) => ({ ...o })),
    credit: blank ? null : { ...ov.credit_line },
    fees: rest('CreditLineResponse.default').fees,
    payees: rest('PayeesResponse.default').payees,
    salaryEvents: [],
    initial,
    tokens: new Map(),
    applied: new Set(),
  }
}

export function resetAccount(email: string): Account {
  const a = makeAccount(email.startsWith('trang') ? 'nguoidung@example.invalid' : email)
  accounts.set(email, a)
  return a
}

function account(email: string): Account {
  let a = accounts.get(email)
  if (!a) {
    a = makeAccount(email)
    accounts.set(email, a)
  }
  return a
}

const allJars = (a: Account) => [...a.jars, ...a.system]
const jarByCode = (a: Account, c: string) => allJars(a).find((j) => j.code === c)

// ---- dự báo (công thức đơn giản chỉ để thấy giao diện) ----
function nextPayday(a: Account): { date: string; days_until: number } | null {
  const day = a.profile.payday_day
  if (!day) return null
  for (let n = 1; n <= 62; n++) {
    const d = addDays(APP_DATE, n)
    if (Number(d.slice(8, 10)) === day) return { date: d, days_until: n }
  }
  return null
}

function dueDatesWithin(o: any, from: string, to: string): string[] {
  const out: string[] = []
  if (o.cycle === 'once') return o.due_date >= from && o.due_date <= to ? [o.due_date] : []
  const step = o.cycle === 'weekly' ? 7 : 0
  if (step) {
    for (let d = o.due_date; d <= to; d = addDays(d, step)) if (d >= from) out.push(d)
    return out
  }
  for (let n = 0; n <= diffDays(from, to); n++) {
    const d = addDays(from, n)
    if (o.cycle === 'yearly' ? d.slice(5) === o.due_date.slice(5) : Number(d.slice(8, 10)) === (o.due_day ?? Number(o.due_date.slice(8, 10)))) out.push(d)
  }
  return out
}

function forecastFor(a: Account, jar: Jar, trace: string) {
  const pd = nextPayday(a) ?? { date: addDays(APP_DATE, 30), days_until: 30 }
  const recent = a.txs.filter((t) => t.jar === jar.code && t.kind === 'expense' && t.funding_source !== 'credit' && diffDays(t.app_date, APP_DATE) <= 14)
  const perDay = Math.max(15_000, Math.round(recent.reduce((s, t) => s - t.amount_vnd, 0) / 14 / 1000) * 1000)
  const events: any[] = []
  for (const o of a.obligations) {
    if (o.status !== 'active' || (o.pay_jar ?? '') !== jar.code) continue
    for (const d of dueDatesWithin(o, addDays(APP_DATE, 1), addDays(APP_DATE, 30))) {
      events.push({ date: d, kind: 'obligation', label: o.name.slice(0, 60), amount_vnd: o.amount_vnd, ...(o.amount_max_vnd ? { amount_max_vnd: o.amount_max_vnd } : {}) })
    }
  }
  const salary = a.profile.monthly_salary_vnd ?? 0
  const share = Math.floor((salary * jar.split_percent) / 100)
  if (share > 0 && pd.days_until <= 30) events.push({ date: pd.date, kind: 'salary', label: 'Lương', amount_vnd: share })
  events.sort((x, y) => (x.date < y.date ? -1 : 1))

  const days: any[] = []
  let minBefore = jar.balance_vnd
  let runout: string | undefined
  for (let d = 1; d <= 30; d++) {
    const date = addDays(APP_DATE, d)
    let p50 = jar.balance_vnd - perDay * d
    for (const e of events) if (e.date <= date) p50 += e.kind === 'salary' ? e.amount_vnd : -e.amount_vnd
    const spread = Math.round((perDay * 0.55 * Math.sqrt(d)) / 1000) * 1000
    days.push({ date, p10_vnd: p50 - Math.round(spread * 1.28), p50_vnd: p50, p90_vnd: p50 + Math.round(spread * 1.28) })
    if (date < pd.date) minBefore = Math.min(minBefore, p50)
    if (!runout && p50 <= 0) runout = date
  }
  const sigma = Math.max(1, perDay * 0.55 * Math.sqrt(Math.max(1, pd.days_until)))
  const p = 1 / (1 + Math.exp(minBefore / sigma))
  const status = p >= 0.5 ? 'short' : p >= 0.2 ? 'tight' : 'ok'
  const historyDays = a.initial ? 18 : 47
  return {
    v: 1,
    id: `forecast_timeline:${trace}:${jar.code}`,
    type: 'forecast_timeline',
    trace_id: trace,
    fallback_text: `Dự báo hũ ${jar.name}: ${runout ? `dự kiến cạn ngày ${runout.slice(8, 10)}/${runout.slice(5, 7)}` : 'đủ tới kỳ lương'}.`,
    source: { tool: 'rest:GET /forecasts/{jar_code}', as_of: nowIso(), app_date: APP_DATE },
    data: {
      jar: { code: jar.code, name: jar.name, color_key: jar.color_key, icon_key: jar.icon_key },
      status,
      origin_date: APP_DATE,
      start_balance_vnd: jar.balance_vnd,
      horizon_days: 30,
      payday: pd,
      ...(runout ? { runout_date: runout } : {}),
      ...(a.initial ? {} : { p_shortfall: Math.round(p * 100) / 100, p_shortfall_se: 0.006 }),
      confidence_band: a.initial ? 'low' : 'medium',
      ...(a.initial ? { coverage: 0.38 } : { coverage: 0.62 }),
      history_days: historyDays,
      is_initial_estimate: a.initial,
      model: 'hurdle_calendar',
      computed_at: nowIso(),
      stale: false,
      days,
      events,
    },
  }
}

function jarFull(a: Account, j: Jar, trace: string) {
  const out = { ...j }
  delete out.status
  delete out.runout_date
  delete out.p_shortfall
  delete out.confidence_band
  if (j.kind === 'system' || !a.profile.onboarded) return out
  const f = forecastFor(a, j, trace).data
  out.status = f.status
  if (f.runout_date) out.runout_date = f.runout_date
  if (f.p_shortfall !== undefined) out.p_shortfall = f.p_shortfall
  out.confidence_band = f.confidence_band
  return out
}

function overview(a: Account, trace: string) {
  const jars = a.jars.map((j) => jarFull(a, j, trace))
  const jarsTotal = a.jars.reduce((s, j) => s + j.balance_vnd, 0)
  const other = a.system.find((j) => j.system_role === 'other_income')?.balance_vnd ?? 0
  const uncl = a.system.find((j) => j.system_role === 'unclassified')?.balance_vnd ?? 0
  const pd = nextPayday(a)
  const pending = a.salaryEvents.find((e) => e.status === 'pending')
  const f = a.profile.onboarded && jars.length ? forecastFor(a, a.jars[0], trace).data : null
  let card: any = null
  if (pending) {
    card = {
      v: 1, id: `proactive_card:${trace}:salary_pending`, type: 'proactive_card', trace_id: trace,
      fallback_text: 'Lương về, chờ bạn xác nhận chia vào các hũ.', source: { tool: 'rest:GET /overview', as_of: nowIso(), app_date: APP_DATE },
      data: { kind: 'salary_pending', status: 'ok', title: 'Lương về, chờ bạn xác nhận', reason: `Đã nhận ${vnd(pending.amount_vnd)}. Một chạm để chia vào các hũ.`, actions: [{ kind: 'confirm_salary', label: 'Xác nhận chia lương' }, { kind: 'snooze', label: 'Để sau' }] },
    }
  } else {
    const rank = (st: string) => (st === 'short' ? 0 : 1)
    const worst = [...jars].filter((j) => j.status === 'short' || j.status === 'tight').sort((x, y) => rank(x.status) - rank(y.status) || (x.runout_date ?? '9').localeCompare(y.runout_date ?? '9'))[0]
    if (worst) {
      card = {
        v: 1, id: `proactive_card:${trace}:runout_warning`, type: 'proactive_card', trace_id: trace,
        fallback_text: `Hũ ${worst.name} ${worst.runout_date ? `dự kiến cạn ngày ${worst.runout_date.slice(8, 10)}/${worst.runout_date.slice(5, 7)}` : 'đang sát'}.`,
        source: { tool: 'rest:GET /overview', as_of: nowIso(), app_date: APP_DATE },
        data: {
          kind: 'runout_warning', status: worst.status, jar_code: worst.code,
          title: worst.runout_date ? `Hũ ${worst.name} dự kiến cạn ngày ${worst.runout_date.slice(8, 10)}/${worst.runout_date.slice(5, 7)}` : `Hũ ${worst.name} đang sát`,
          reason: `Còn ${vnd(worst.balance_vnd)}${pd ? `, còn ${pd.days_until} ngày tới kỳ lương ${pd.date.slice(8, 10)}/${pd.date.slice(5, 7)}` : ''}.`,
          actions: [
            { kind: 'ask_why', label: 'Hỏi vì sao', jar_code: worst.code, prompt: `Vì sao hũ ${worst.name} ${worst.status === 'short' ? 'sắp cạn' : 'đang sát'}?` },
            { kind: 'open_forecast', label: 'Xem dự báo', jar_code: worst.code },
            { kind: 'snooze', label: 'Để sau' },
            { kind: 'mute_kind', label: 'Ít nhắc loại này' },
          ],
        },
      }
    }
  }
  return {
    app_date: APP_DATE,
    as_of: nowIso(),
    profile: a.profile,
    balance: { total_vnd: jarsTotal + other + uncl, jars_total_vnd: jarsTotal, other_income_vnd: other, unclassified_vnd: uncl },
    jars,
    system_jars: a.system,
    next_payday: pd && a.profile.onboarded ? { ...pd, expected_vnd: a.profile.monthly_salary_vnd, state: pending ? 'pending_confirmation' : 'expected', ...(pending ? { salary_event_id: pending.id } : {}) } : null,
    forecast: f ? { computed_at: f.computed_at, run_app_date: APP_DATE, stale: false, is_initial_estimate: a.initial, confidence_band: f.confidence_band, coverage: f.coverage, history_days: f.history_days, model: f.model } : null,
    proactive_card: card,
    credit_line: a.credit,
    obligations_due: a.obligations.filter((o) => o.status === 'active' && diffDays(APP_DATE, o.due_date) <= 30).sort((x, y) => (x.due_date < y.due_date ? -1 : 1)).slice(0, 5),
    recent_transactions: a.txs.filter((t) => t.kind !== 'transfer').slice(0, 5),
    needs_review_count: a.txs.filter((t) => t.needs_review).length,
  }
}

// ---- ghi ----
const TX_TYPES = () => rest('TxTypesResponse.default').tx_types

/** Hũ mẫu cho onboarding: bảy hũ mặc định (tổng 100%) và hai hũ tùy chọn. */
const TEMPLATES = () => [
  ...rest('OverviewResponse.minh').jars.map((j: any) => ({ code: j.code, name: j.name, color_key: j.color_key, icon_key: j.icon_key, kind: j.kind, default_split_percent: j.split_percent, is_default: true })),
  { code: 'hoc_tap', name: 'Học tập', color_key: 'teal', icon_key: 'landmark', kind: 'saving', default_split_percent: 5, is_default: false },
  { code: 'gia_dinh', name: 'Gia đình', color_key: 'sky', icon_key: 'umbrella', kind: 'spending', default_split_percent: 5, is_default: false },
]

function receiptAction(tool: string, trace: string, summary: string, jarsAfter: any[], details: any[], extra: Record<string, unknown> = {}) {
  const ref = randomUUID()
  return {
    v: 1,
    id: `receipt:${tool}:${ref}`,
    type: 'receipt_action',
    trace_id: trace,
    fallback_text: summary,
    source: { tool: 'rest:POST /actions', as_of: nowIso(), app_date: APP_DATE },
    data: { tool, reference_id: ref, occurred_at: nowIso(), app_date: APP_DATE, summary, jars_after: jarsAfter.map((j) => ({ code: j.code, name: j.name, balance_after_vnd: j.balance_vnd })), details, ...extra },
  }
}

type Fail = { status: number; code: string; message: string }
const fail = (status: number, code: string, message: string): Fail => ({ status, code, message })

function applyRecord(a: Account, p: any, trace: string): any | Fail {
  const amount = Number(p.amount_vnd)
  if (!(amount > 0)) return fail(400, 'PARAMS_INVALID', 'Số tiền phải lớn hơn 0.')
  const date = APP_DATE
  if (p.client_ref && a.txs.some((t) => t.client_ref === p.client_ref)) return fail(409, 'DUPLICATE_TRANSACTION', 'Giao dịch này đã được ghi rồi.')
  if (p.kind === 'income') {
    const other = a.system.find((j) => j.system_role === 'other_income')!
    other.balance_vnd += amount
    const tx = { id: randomUUID(), client_ref: p.client_ref, occurred_at: nowIso(), app_date: date, kind: 'income', jar: other.code, amount_vnd: amount, merchant: p.counterparty, note: p.note, tx_type: p.tx_type ?? 'income_other', funding_source: 'jar' }
    a.txs.unshift(tx)
    let follow: any
    if (p.tx_type === 'salary') {
      const expected = a.profile.monthly_salary_vnd
      const ev = {
        id: randomUUID(), period_date: nextPayday(a)?.date ?? date, received_on: date, ...(expected ? { expected_vnd: expected } : {}), amount_vnd: amount,
        deviation_percent: expected ? Math.round(((amount - expected) / expected) * 10000) / 100 : 0, ask_update_salary: expected ? Math.abs(amount - expected) / expected > 0.1 : false, status: 'pending',
      }
      a.salaryEvents.push(ev)
      follow = { follow_up: { kind: 'confirm_salary', label: 'Xác nhận chia lương vào các hũ', salary_event_id: ev.id, received_vnd: amount, ...(expected ? { expected_vnd: expected } : {}), deviation_percent: ev.deviation_percent, ask_update_salary: ev.ask_update_salary } }
    }
    return receiptAction('record_transaction', trace, `Đã ghi tiền vào ${vnd(amount)} vào ${other.name}`, [other], [{ label: 'Loại', value: TX_TYPES().find((t: any) => t.tx_type === p.tx_type)?.label ?? 'Tiền vào' }], { amount_vnd: amount, ...follow })
  }
  // chi
  const credit = p.funding === 'credit'
  const jarCode = p.jar ?? a.system.find((j) => j.system_role === 'unclassified')?.code
  const jar = jarCode ? jarByCode(a, jarCode) : undefined
  if (!jar) return fail(404, 'JAR_NOT_FOUND', 'Không có hũ này.')
  const payee = p.payee_id ? a.payees.find((x) => x.id === p.payee_id) : undefined
  if (p.payee_id && !payee) return fail(404, 'PAYEE_NOT_FOUND', 'Không có người nhận này.')
  const details: any[] = []
  if (credit) {
    if (!a.credit || a.credit.available_vnd < amount) return fail(422, 'CREDIT_LIMIT_EXCEEDED', 'Vượt hạn mức Trả sau còn lại.')
    const feeLine = a.fees.find((f) => f.condition_code === 'month_has_transaction')
    let ob = a.obligations.find((o) => o.kind === 'bnpl' && o.status === 'active')
    const fee = feeLine?.amount_vnd ?? 0
    if (!ob) {
      const due = (() => { for (let n = 1; n <= 62; n++) { const d = addDays(date, n); if (Number(d.slice(8, 10)) === a.credit.due_day) return d } return addDays(date, 14) })()
      ob = { id: randomUUID(), kind: 'bnpl', name: a.credit.product_label, amount_vnd: amount + fee, fee_vnd: fee, principal_vnd: amount, due_date: due, cycle: 'once', status: 'active', pay_jar: a.jars.find((j) => j.kind === 'obligation')?.code, is_essential: false, source: 'bnpl_auto' }
      a.obligations.push(ob)
    } else {
      ob.principal_vnd += amount
      ob.amount_vnd = ob.principal_vnd + ob.fee_vnd
    }
    a.credit.outstanding_vnd += amount
    a.credit.available_vnd -= amount
    details.push({ label: 'Nghĩa vụ Trả sau', value: `${vnd(ob.amount_vnd)} đến hạn ${ob.due_date.slice(8, 10)}/${ob.due_date.slice(5, 7)}` }, { label: 'Trong đó phí', value: vnd(ob.fee_vnd) })
  } else {
    if (jar.kind !== 'system' && jar.balance_vnd < amount) return fail(422, 'INSUFFICIENT_FUNDS', 'Hũ nguồn không đủ số dư.')
    jar.balance_vnd -= amount
  }
  const tx = { id: randomUUID(), client_ref: p.client_ref, occurred_at: nowIso(), app_date: date, kind: 'expense', jar: jar.code, amount_vnd: -amount, ...(payee ? { payee_id: payee.id, payee_name: payee.name } : {}), merchant: p.counterparty, note: p.note, tx_type: p.tx_type ?? 'other_expense', funding_source: credit ? 'credit' : 'jar', ...(jar.system_role === 'unclassified' ? { needs_review: true } : {}) }
  a.txs.unshift(tx)
  if (payee) payee.last_used_at = nowIso()
  return receiptAction('record_transaction', trace, `Đã chuyển ${vnd(amount)}${payee ? ` cho ${payee.name}` : ''}${credit ? ` bằng ${a.credit.product_label}` : ''}`, credit ? [] : [jar], details, { amount_vnd: amount })
}

function applyAction(a: Account, tool: string, p: any, trace: string): any | Fail {
  if (tool === 'move_between_jars') {
    const from = jarByCode(a, p.from_jar)
    const to = jarByCode(a, p.to_jar)
    if (!from || !to) return fail(404, 'JAR_NOT_FOUND', 'Không có hũ này.')
    if (from.balance_vnd < p.amount_vnd) return fail(422, 'INSUFFICIENT_FUNDS', 'Không đủ số dư.')
    from.balance_vnd -= p.amount_vnd
    to.balance_vnd += p.amount_vnd
    const tx = randomUUID()
    a.txs.unshift({ id: randomUUID(), transfer_id: tx, occurred_at: nowIso(), app_date: APP_DATE, kind: 'transfer', jar: to.code, amount_vnd: p.amount_vnd, note: `Từ ${from.name}`, tx_type: 'jar_transfer', funding_source: 'jar' })
    return {
      v: 1, id: `receipt:${tx}`, type: 'receipt', trace_id: trace, fallback_text: `Đã chuyển ${vnd(p.amount_vnd)} từ ${from.name} sang ${to.name}.`, source: { tool: 'rest:POST /actions', as_of: nowIso(), app_date: APP_DATE },
      data: { tool: 'move_between_jars', transaction_id: tx, occurred_at: nowIso(), app_date: APP_DATE, amount_vnd: p.amount_vnd, summary: `Đã chuyển ${vnd(p.amount_vnd)} từ ${from.name} sang ${to.name}`, from_jar: { code: from.code, name: from.name, balance_after_vnd: from.balance_vnd }, to_jar: { code: to.code, name: to.name, balance_after_vnd: to.balance_vnd } },
    }
  }
  if (tool === 'record_transaction') return applyRecord(a, p, trace)
  if (tool === 'update_profile') {
    if (p.obligation) {
      const ob = p.obligation
      if (ob.op === 'delete') {
        const o = a.obligations.find((x) => x.id === ob.obligation_id)
        if (!o) return fail(404, 'OBLIGATION_NOT_FOUND', 'Không có khoản này.')
        o.status = 'cancelled'
        return receiptAction('update_profile', trace, `Đã xóa khoản ${o.name}`, [], [])
      }
      const existing = ob.obligation_id ? a.obligations.find((x) => x.id === ob.obligation_id) : undefined
      if (ob.obligation_id && !existing) return fail(404, 'OBLIGATION_NOT_FOUND', 'Không có khoản này.')
      const dueDate = ob.due_date ?? (() => { for (let n = 0; n <= 62; n++) { const d = addDays(APP_DATE, n); if (Number(d.slice(8, 10)) === ob.due_day) return d } return APP_DATE })()
      const amount = ob.amount_vnd ?? Math.floor((ob.amount_min_vnd + ob.amount_max_vnd) / 2)
      const next = { id: existing?.id ?? randomUUID(), kind: ob.kind, name: ob.name, amount_vnd: amount, ...(ob.amount_min_vnd ? { amount_min_vnd: ob.amount_min_vnd, amount_max_vnd: ob.amount_max_vnd } : {}), fee_vnd: 0, due_date: dueDate, cycle: ob.cycle ?? 'monthly', ...(ob.due_day ? { due_day: ob.due_day } : {}), status: 'active', ...(ob.pay_jar ? { pay_jar: ob.pay_jar } : {}), is_essential: ob.is_essential ?? false, source: 'declared' }
      if (existing) Object.assign(existing, next)
      else a.obligations.push(next)
      return receiptAction('update_profile', trace, existing ? `Đã sửa khoản ${next.name}` : `Đã thêm khoản ${next.name}`, [], [{ label: 'Số tiền', value: vnd(amount) }, { label: 'Đến hạn', value: `${dueDate.slice(8, 10)}/${dueDate.slice(5, 7)}` }])
    }
    const first = !a.profile.onboarded
    if (first && (!p.monthly_salary_vnd || !p.payday_day)) return fail(422, 'PROFILE_INCOMPLETE', 'Cần khai cả lương và ngày nhận lương.')
    Object.assign(a.profile, p)
    if (first) {
      const fresh = makeAccount('nguoidung@example.invalid')
      a.profile.onboarded = true
      a.system = fresh.system.map((j: Jar) => ({ ...j, balance_vnd: 0 }))
      const templates = TEMPLATES().filter((t: any) => t.is_default)
      a.jars = templates.map((t: any) => ({ code: t.code, name: t.name, color_key: t.color_key, icon_key: t.icon_key, kind: t.kind, balance_vnd: 0, split_percent: t.default_split_percent }))
      a.credit = { ...fresh.credit }
    }
    return receiptAction('update_profile', trace, first ? 'Đã tạo hồ sơ' : 'Đã cập nhật hồ sơ', [], [
      ...(p.monthly_salary_vnd ? [{ label: 'Lương', value: vnd(p.monthly_salary_vnd) }] : []),
      ...(p.payday_day ? [{ label: 'Ngày nhận lương', value: `Ngày ${p.payday_day} hằng tháng` }] : []),
    ])
  }
  if (tool === 'save_jars') {
    const total = Math.round(p.jars.reduce((s: number, j: any) => s + j.split_percent, 0) * 100)
    if (total !== 10000) return fail(400, 'PARAMS_INVALID', 'Tổng tỷ lệ phải bằng 100.')
    const kept = new Set<string>()
    const next = p.jars.map((j: any) => {
      const old = j.code ? a.jars.find((x) => x.code === j.code) : undefined
      const code = old?.code ?? j.name.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/gi, 'd').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 32) ?? 'hu'
      kept.add(code)
      return { code, name: j.name, color_key: j.color_key, icon_key: j.icon_key, kind: j.kind, balance_vnd: old?.balance_vnd ?? 0, split_percent: j.split_percent, ...(j.goal_vnd ? { goal_vnd: j.goal_vnd } : {}), ...(j.goal_date ? { goal_date: j.goal_date } : {}) }
    })
    const dropped = a.jars.find((j) => !kept.has(j.code) && j.balance_vnd > 0)
    if (dropped) return fail(422, 'JAR_PROTECTED', `Hũ ${dropped.name} còn tiền nên chưa bỏ được.`)
    a.jars = next
    return receiptAction('save_jars', trace, 'Đã lưu các hũ và tỷ lệ chia lương', [], next.map((j: any) => ({ label: j.name, value: `${j.split_percent}%` })).slice(0, 20))
  }
  if (tool === 'confirm_salary') {
    const ev = a.salaryEvents.find((e) => e.id === p.salary_event_id)
    if (!ev) return fail(404, 'SALARY_EVENT_NOT_FOUND', 'Không có khoản lương này.')
    const other = a.system.find((j) => j.system_role === 'other_income')!
    if (p.decision === 'keep_as_other') {
      ev.status = 'kept_other'
      return receiptAction('confirm_salary', trace, 'Đã giữ khoản lương ở Tiền vào khác', [other], [], { amount_vnd: ev.amount_vnd })
    }
    let left = ev.amount_vnd
    other.balance_vnd -= ev.amount_vnd
    const biggest = [...a.jars].sort((x, y) => y.split_percent - x.split_percent)[0]
    for (const j of a.jars) {
      const share = Math.floor((ev.amount_vnd * j.split_percent) / 100)
      j.balance_vnd += share
      left -= share
    }
    if (biggest) biggest.balance_vnd += left
    if (p.update_declared_salary) a.profile.monthly_salary_vnd = ev.amount_vnd
    ev.status = 'confirmed'
    return receiptAction('confirm_salary', trace, `Đã chia lương ${vnd(ev.amount_vnd)} vào ${a.jars.length} hũ`, [...a.jars, other], [], { amount_vnd: ev.amount_vnd })
  }
  if (tool === 'assign_jar') {
    const tx = a.txs.find((t) => t.id === p.transaction_id)
    const jar = jarByCode(a, p.jar)
    if (!tx) return fail(404, 'TRANSACTION_NOT_FOUND', 'Không có giao dịch này.')
    if (!jar) return fail(404, 'JAR_NOT_FOUND', 'Không có hũ này.')
    tx.jar = jar.code
    delete tx.needs_review
    return receiptAction('assign_jar', trace, `Đã gán giao dịch vào hũ ${jar.name}`, [jar], [])
  }
  return fail(400, 'PARAMS_INVALID', 'Tool không hỗ trợ.')
}

// ---- định tuyến ----
export type Ctx = { method: string; path: string; query: URLSearchParams; body: any; email: string; trace: string }
export type Reply = { status: number; body: unknown }
const ok = (body: unknown): Reply => ({ status: 200, body })
const err = (f: Fail): Reply => ({ status: f.status, body: { error: { code: f.code, message: f.message } } })

export function handleWallet(c: Ctx): Reply | null {
  const a = account(c.email)
  const { method, path } = c
  if (method === 'GET') {
    if (path === '/jars') {
      const jars = a.jars.map(({ status: _s, runout_date: _r, p_shortfall: _p, confidence_band: _c, goal_vnd: _g, goal_date: _d, kind: _k, ...j }) => j)
      return ok({ app_date: APP_DATE, as_of: nowIso(), jars, jars_total_vnd: a.jars.reduce((s, j) => s + j.balance_vnd, 0) })
    }
    if (path === '/overview') return ok(overview(a, c.trace))
    // Hồ sơ hành vi (fixture hợp đồng) kèm vế "phần số ngày" mà batch thật phát cạnh "phần chi", để thấy thanh B3 ở Hồ sơ.
    if (path === '/profile/behavior') {
      const p = rest('BehaviorProfileResponse.minh')
      p.insights[0].evidence.push({ key: 'first_week_day_share', label: 'Phần số ngày thuộc tuần đầu sau lương', value: 23, unit: 'percent' })
      return ok(p)
    }
    if (path === '/profile') return ok({ app_date: APP_DATE, as_of: nowIso(), profile: a.profile })
    if (path === '/tx-types') return ok({ tx_types: TX_TYPES() })
    if (path === '/payees') return ok({ payees: [...a.payees].sort((x, y) => Number(y.is_favorite) - Number(x.is_favorite)) })
    if (path === '/jar-templates') return ok({ templates: TEMPLATES() })
    if (path === '/credit-line') return ok({ app_date: APP_DATE, credit_line: a.credit, fees: a.fees })
    if (path === '/salary-events') return ok({ salary_events: a.salaryEvents.filter((e) => e.status === 'pending') })
    if (path === '/obligations') {
      const list = a.obligations.filter((o) => o.status === 'active').sort((x, y) => (x.due_date < y.due_date ? -1 : 1))
      return ok({ app_date: APP_DATE, obligations: list, total_due_vnd: list.reduce((s, o) => s + o.amount_vnd, 0) })
    }
    if (path === '/transactions') {
      const jar = c.query.get('jar')
      const review = c.query.get('needs_review') === 'true'
      const limit = Math.min(50, Number(c.query.get('limit') ?? 20))
      const offset = Number(Buffer.from(c.query.get('cursor') ?? '', 'base64url').toString() || 0)
      const list = a.txs.filter((t) => (!jar || t.jar === jar) && (!review || t.needs_review))
      const page = list.slice(offset, offset + limit)
      const next = offset + limit < list.length ? Buffer.from(String(offset + limit)).toString('base64url') : undefined
      return ok({ app_date: APP_DATE, as_of: nowIso(), transactions: page.map(({ client_ref: _c, ...t }) => t), ...(next ? { next_cursor: next } : {}) })
    }
    const jm = /^\/jars\/([a-z][a-z0-9_]*)$/.exec(path)
    if (jm) {
      const j = jarByCode(a, jm[1]!)
      if (!j) return err(fail(404, 'JAR_NOT_FOUND', 'Không có hũ này.'))
      const full = jarFull(a, j, c.trace)
      return ok({
        app_date: APP_DATE, as_of: nowIso(), jar: full,
        forecast: j.kind === 'system' || !a.profile.onboarded ? null : (({ data: f }) => ({ computed_at: f.computed_at, run_app_date: APP_DATE, stale: false, is_initial_estimate: a.initial, confidence_band: f.confidence_band, coverage: f.coverage, history_days: f.history_days, model: f.model }))(forecastFor(a, j, c.trace)),
        recent_transactions: a.txs.filter((t) => t.jar === j.code).slice(0, 10),
        obligations: a.obligations.filter((o) => o.status === 'active' && o.pay_jar === j.code).slice(0, 10),
      })
    }
    const fm = /^\/forecasts\/([a-z][a-z0-9_]*)$/.exec(path)
    if (fm) {
      const j = jarByCode(a, fm[1]!)
      if (!j) return err(fail(404, 'JAR_NOT_FOUND', 'Không có hũ này.'))
      if (!a.profile.onboarded) return err(fail(422, 'PROFILE_INCOMPLETE', 'Cần khai lương trước.'))
      if (j.kind === 'system') return err(fail(503, 'FORECAST_UNAVAILABLE', 'Hũ hệ thống không có dự báo.'))
      return ok(forecastFor(a, j, c.trace))
    }
  }
  if (method === 'POST') {
    if (path === '/confirmations') {
      const b = c.body
      const params = b.params ?? {}
      if (b.confirm_block_id && a.applied.has(b.confirm_block_id)) return err(fail(409, 'ALREADY_APPLIED', 'Đề nghị này đã được thực hiện rồi.'))
      if (b.tool === 'record_transaction' && params.client_ref && a.txs.some((t) => t.client_ref === params.client_ref)) return err(fail(409, 'DUPLICATE_TRANSACTION', 'Giao dịch này đã được ghi rồi.'))
      const hash = paramsHash(b.tool, params)
      if (b.params_hash && b.params_hash !== hash) return err(fail(409, 'PARAMS_MISMATCH', 'Tham số lệch.'))
      const token = `${randomUUID().replace(/-/g, '')}.${randomUUID().replace(/-/g, '').slice(0, 16)}`
      a.tokens.set(token, { hash, used: false, tool: b.tool, params })
      return ok({ confirm_token: token, expires_at: new Date(Date.now() + 120_000).toISOString().replace(/\.\d+Z$/, 'Z'), ttl_seconds: 120, tool: b.tool, params, params_hash: hash })
    }
    if (path === '/actions') {
      const b = c.body
      if (!b.confirm_token) return err(fail(428, 'NEEDS_CONFIRMATION', 'Cần xác nhận.'))
      if (b.confirm_block_id && a.applied.has(b.confirm_block_id)) return err(fail(409, 'ALREADY_APPLIED', 'Đề nghị này đã được thực hiện rồi.'))
      const t = a.tokens.get(b.confirm_token)
      if (!t) return err(fail(403, 'TOKEN_INVALID', 'Token không hợp lệ.'))
      if (t.used) return err(fail(409, 'TOKEN_REUSED', 'Token đã dùng.'))
      if (t.hash !== paramsHash(b.tool, b.params)) return err(fail(409, 'PARAMS_MISMATCH', 'Tham số lệch.'))
      t.used = true
      const r = applyAction(a, b.tool, b.params, c.trace)
      if ('code' in r && 'status' in r && typeof r.code === 'string') return err(r as Fail)
      if (b.confirm_block_id) a.applied.add(b.confirm_block_id)
      return ok(r)
    }
    if (path === '/demo/reset') {
      const fresh = resetAccount(c.email)
      return ok({ reset_at: nowIso(), app_date: APP_DATE, clock_offset_days: 0, jars_count: fresh.jars.length, transactions_count: fresh.txs.length, obligations_count: fresh.obligations.length, forecast_ready: true })
    }
  }
  return null
}

/** Dự báo của một hũ cho agent giả (câu hỏi "dự báo hũ ..." trong chat). */
export function forecastBlockFor(email: string, trace: string, nameHint: string): any | null {
  const a = account(email)
  const j = a.jars.find((x) => nameHint.includes(x.name.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').toLowerCase())) ?? a.jars[0]
  return j && a.profile.onboarded ? forecastFor(a, j, trace) : null
}


/** Các hũ của tài khoản (cho agent giả: số dư và câu hỏi chuyển hũ). */
export function jarsOf(email: string): Array<{ code: string; name: string; color_key: string; icon_key: string; balance_vnd: number; split_percent: number }> {
  return account(email).jars.map((j) => ({ code: j.code, name: j.name, color_key: j.color_key, icon_key: j.icon_key, balance_vnd: j.balance_vnd, split_percent: j.split_percent }))
}
