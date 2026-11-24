import { describe, expect, it } from 'vitest'

// Vitest (`css: false`) trả chuỗi rỗng cho mọi import `.css`, kể cả `?raw`: đọc file bằng fs của Node (test chạy trong Node).
// Tên mô-đun để trong biến để tsconfig của app (không có @types/node) không phải biết kiểu của nó.
const FS = 'node:fs'
const { readFileSync } = (await import(/* @vite-ignore */ FS)) as { readFileSync: (path: string, encoding: 'utf8') => string }
// Trong môi trường jsdom, import.meta.url là URL http; thư mục thật của file nằm ở import.meta.dirname (Vite module runner).
const here = (import.meta as unknown as { dirname: string }).dirname
const css = readFileSync(`${here}/../index.css`, 'utf8')
const html = readFileSync(`${here}/../../index.html`, 'utf8')

// Bảng màu theo docs/research/ui-design-review.md §4.1: đọc thẳng giá trị trong index.css và tính tương phản WCAG 2.x,
// để đổi một mã màu mà tụt dưới ngưỡng thì test đỏ (không chép số tỷ lệ của tài liệu vào đây).

type Tokens = Record<string, string>

function block(selector: string): Tokens {
  const start = css.indexOf(`${selector} {`)
  expect(start, `không thấy khối ${selector}`).toBeGreaterThanOrEqual(0)
  const body = css.slice(start + selector.length + 2, css.indexOf('}', start))
  const out: Tokens = {}
  for (const m of body.matchAll(/(--[\w-]+):\s*([^;]+);/g)) out[m[1]!] = m[2]!.trim()
  return out
}

const light = block(':root')
const darkMedia = block(':root:not([data-theme="light"])')
const darkForced = block(':root[data-theme="dark"]')
// Bộ Tối chỉ ghi đè; biến không ghi đè thì lấy từ bộ Sáng.
const dark = { ...light, ...darkForced }

function luminance(hex: string): number {
  const m = /^#([0-9a-f]{6})$/i.exec(hex)
  if (!m) throw new Error(`không phải mã hex 6 chữ số: ${hex}`)
  const n = parseInt(m[1]!, 16)
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const s = v / 255
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * ch[0]! + 0.7152 * ch[1]! + 0.0722 * ch[2]!
}

function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p)
  return (x! + 0.05) / (y! + 0.05)
}

const TEXT = 4.5
const GRAPHIC = 3

// [chữ hoặc nét, nền, ngưỡng]
const PAIRS: [string, string, number][] = [
  ...['--text-primary', '--text-secondary', '--text-tertiary'].flatMap((fg) =>
    ['--bg-app', '--bg-surface', '--bg-surface-2'].map((bg) => [fg, bg, TEXT] as [string, string, number]),
  ),
  ['--text-on-brand', '--brand-primary', TEXT],
  ['--text-on-brand', '--brand-deep', TEXT],
  ['--text-on-brand', '--brand-vivid', GRAPHIC], // chỉ chữ lớn
  ['--text-brand', '--bg-surface', TEXT],
  ['--text-brand', '--bg-app', TEXT],
  ['--text-brand', '--bg-tint', TEXT],
  ['--accent-blue', '--bg-surface', TEXT],
  ['--accent-blue', '--accent-blue-tint', TEXT],
  ...(['ok', 'warn', 'bad'] as const).flatMap((s) => [
    [`--status-${s}-fg`, `--status-${s}-bg`, TEXT] as [string, string, number],
    [`--status-${s}-fg`, '--bg-surface', TEXT] as [string, string, number],
    // Nét trạng thái là đồ họa mang nghĩa (mốc nghĩa vụ trên biểu đồ dự báo, thanh "trụ được"): WCAG 1.4.11.
    [`--status-${s}-line`, '--bg-surface', GRAPHIC] as [string, string, number],
  ]),
  ['--border-strong', '--bg-surface', GRAPHIC],
  ...['an-uong', 'di-lai', 'hoa-don', 'giai-tri', 'du-lich', 'du-phong', 'nghia-vu'].map(
    (jar) => [`--jar-${jar}`, '--bg-surface', GRAPHIC] as [string, string, number],
  ),
]

describe('bảng màu', () => {
  it('không còn mã #A50064 (màu logo MoMo) trong token và theme-color', () => {
    const code = css.replace(/\/\*[\s\S]*?\*\//g, '').toLowerCase()
    expect(code).not.toContain('#a50064')
    expect(html.toLowerCase()).not.toContain('#a50064')
  })

  it('hai khối token Tối (theo máy và ép bằng data-theme) giống hệt nhau', () => {
    expect(darkMedia).toEqual(darkForced)
  })

  it('theme-color khớp nền app của hai chế độ', () => {
    expect(html).toContain(`content="${light['--bg-app']}" media="(prefers-color-scheme: light)"`)
    expect(html).toContain(`content="${dark['--bg-app']}" media="(prefers-color-scheme: dark)"`)
  })

  it('gradient thẻ số dư đi từ brand-deep tới brand-primary, chữ trắng đọc được ở mọi điểm', () => {
    expect(light['--gradient-hero']).toMatch(/var\(--brand-deep\).*var\(--brand-primary\)/)
    for (const t of [light, dark]) {
      expect(contrast(t['--text-on-brand']!, t['--brand-deep']!)).toBeGreaterThanOrEqual(TEXT)
      expect(contrast(t['--text-on-brand']!, t['--brand-primary']!)).toBeGreaterThanOrEqual(TEXT)
    }
  })

  it.each([
    ['Sáng', light],
    ['Tối', dark],
  ] as const)('tương phản bộ %s đạt ngưỡng (chữ 4,5:1, đồ họa 3:1)', (_name, tokens) => {
    const failures = PAIRS.map(([fg, bg, min]) => ({ fg, bg, min, ratio: contrast(tokens[fg]!, tokens[bg]!) }))
      .filter((p) => p.ratio < p.min)
      .map((p) => `${p.fg} trên ${p.bg}: ${p.ratio.toFixed(2)} < ${p.min}`)
    expect(failures).toEqual([])
  })

  it('màu hũ Đi lại và Du lịch bản Sáng đã đổi khỏi mã cũ dưới 3:1', () => {
    expect(light['--jar-di-lai']).not.toBe('#2fa3d6')
    expect(light['--jar-du-lich']).not.toBe('#1fa6a0')
  })
})
