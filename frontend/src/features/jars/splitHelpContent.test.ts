import { describe, expect, it } from 'vitest'
import type { JarTemplate } from '@/api/schemas'
import { splitHelpContent, type SplitHelpContent } from './splitHelpContent'

// Lời trợ giúp "Chia hũ sao cho hợp lý": ngắn, tiếng Việt, hướng dẫn chung; số chỉ lấy từ dữ liệu server (`GET /jar-templates`).

const tpl = (code: string, name: string, kind: JarTemplate['kind'], pct: number, isDefault: boolean, purpose?: JarTemplate['purpose']): JarTemplate => ({
  code,
  name,
  color_key: 'teal',
  icon_key: 'wallet',
  kind,
  default_split_percent: pct,
  is_default: isDefault,
  ...(purpose ? { purpose } : {}),
})

const CATALOGUE: JarTemplate[] = [
  tpl('chi_hang_ngay', 'Chi hằng ngày', 'spending', 42.5, true),
  tpl('nghia_vu', 'Nghĩa vụ', 'obligation', 32.5, true),
  tpl('du_phong', 'Dự phòng', 'saving', 25, true, 'buffer'),
  tpl('quy_don', 'Quỹ dồn', 'saving', 0, false, 'sinking'),
  tpl('an_uong', 'Ăn uống', 'spending', 30, false),
]

/** Mọi chữ người dùng thấy trong tấm trợ giúp. */
const allText = (c: SplitHelpContent) =>
  [c.title, c.note, ...c.tips.flatMap((t) => [t.lead, t.text, t.data ?? '']), c.more.label, ...c.more.items].join('\n')

/** Số phần trăm trong chữ, trừ "100%" (tổng các hũ là quy tắc, không phải số tự đặt). */
const percents = (s: string) => (s.match(/\d+(?:[.,]\d+)?\s?%/g) ?? []).filter((p) => p.replace(/\s/g, '') !== '100%')

describe('splitHelpContent', () => {
  it.each(['onboarding', 'edit'] as const)('%s: tiêu đề và 5 đến 7 gạch đầu dòng, mỗi gạch một ý ngắn', (place) => {
    const c = splitHelpContent({ place, templates: CATALOGUE })
    expect(c.title).toBe('Chia hũ sao cho hợp lý')
    expect(c.tips.length).toBeGreaterThanOrEqual(5)
    expect(c.tips.length).toBeLessThanOrEqual(7)
    for (const t of c.tips) {
      expect(t.lead.length).toBeGreaterThan(0)
      expect(t.lead.length).toBeLessThanOrEqual(40)
      expect(t.text.length).toBeGreaterThan(0)
      expect(t.text.length).toBeLessThanOrEqual(150)
    }
    expect(new Set(c.tips.map((t) => t.id)).size).toBe(c.tips.length)
    expect(c.more.label).toBe('Xem thêm')
    expect(c.more.items.length).toBeGreaterThan(0)
    expect(c.note).toMatch(/hướng dẫn chung/i)
  })

  it('có dữ liệu mẫu hũ: hiện tên và tỷ lệ của đúng các hũ mặc định, theo thứ tự server trả', () => {
    const c = splitHelpContent({ place: 'edit', templates: CATALOGUE })
    const first = c.tips[0]!
    expect(first.id).toBe('defaults')
    expect(first.data).toBe('Mặc định: Chi hằng ngày 42,5% · Nghĩa vụ 32,5% · Dự phòng 25%')
    expect(allText(c)).not.toMatch(/Ăn uống 30%/) // hũ không mặc định không vào dòng mặc định
  })

  it.each([
    ['thiếu dữ liệu', undefined],
    ['danh sách rỗng', []],
    ['không có hũ mặc định', [tpl('quy_don', 'Quỹ dồn', 'saving', 0, false, 'sinking')]],
  ])('%s: nói định tính, không có số tỷ lệ nào', (_name, templates) => {
    for (const place of ['onboarding', 'edit'] as const) {
      const c = splitHelpContent({ place, templates })
      expect(c.tips[0]!.data).toBeUndefined()
      expect(percents(allText(c))).toEqual([])
      expect(c.tips.length).toBeGreaterThanOrEqual(5)
    }
  })

  it('không chép cứng số: tỷ lệ mặc định và mức sàn Dự phòng chỉ có khi server trả', () => {
    const c = splitHelpContent({ place: 'onboarding', templates: CATALOGUE })
    // chỉ ba số của dòng mặc định (lấy từ dữ liệu); mức sàn nói định tính
    expect(percents(allText(c))).toEqual(['42,5%', '32,5%', '25%'])
    expect(allText(c)).toMatch(/mức sàn/)
    expect(allText(c)).toMatch(/100%/)
    expect(allText(c)).not.toMatch(/₫/)
  })

  it('bám quy tắc sản phẩm: ba nhóm mục đích, Nghĩa vụ theo số thật, Dự phòng trước, Quỹ dồn, tách hũ, ít hũ, xác nhận', () => {
    const c = splitHelpContent({ place: 'onboarding', templates: CATALOGUE })
    expect(c.tips.map((t) => t.id)).toEqual(['defaults', 'obligation', 'buffer', 'sinking', 'track', 'few', 'review'])
    const byId = Object.fromEntries(c.tips.map((t) => [t.id, `${t.lead} ${t.text}`]))
    expect(byId.defaults).toMatch(/tiền tiêu hằng ngày/i)
    expect(byId.defaults).toMatch(/nhà, hóa đơn, nợ, Trả sau/)
    expect(byId.defaults).toMatch(/dự phòng/i)
    expect(byId.obligation).toMatch(/chia cho lương/)
    expect(byId.buffer).toMatch(/Dự phòng trước, mục tiêu sau/)
    expect(byId.buffer).toMatch(/không hạ Dự phòng dưới mức sàn/)
    expect(byId.sinking).toMatch(/Tết, học phí, bảo hiểm/)
    expect(byId.sinking).toMatch(/Quỹ dồn/)
    expect(byId.track).toMatch(/ăn uống, đi lại, giải trí/)
    expect(byId.few).toMatch(/Không cần nhiều hũ/)
    expect(byId.review).toMatch(/điểm bắt đầu/)
    expect(byId.review).toMatch(/sau khi bạn xác nhận/)
  })

  it('onboarding chỉ tới bước kê khai (bước 3); màn sửa hũ không hứa đề xuất ở màn này', () => {
    const onboarding = splitHelpContent({ place: 'onboarding', templates: CATALOGUE })
    const edit = splitHelpContent({ place: 'edit', templates: CATALOGUE })
    const tip = (c: SplitHelpContent, id: string) => c.tips.find((t) => t.id === id)!.text
    expect(tip(onboarding, 'obligation')).toMatch(/bước 3/)
    expect(tip(onboarding, 'sinking')).toMatch(/bước 3/)
    expect(allText(edit)).not.toMatch(/bước 3/)
    expect(tip(edit, 'sinking')).toMatch(/số tiền và ngày dự kiến/) // đúng nhãn ô của trình sửa
  })

  it('không nêu tên tổ chức nước ngoài, tên sản phẩm cấm, hay sản phẩm đầu tư cụ thể', () => {
    for (const place of ['onboarding', 'edit'] as const) {
      const text = allText(splitHelpContent({ place, templates: CATALOGUE }))
      expect(text).not.toMatch(/CFPB|JPMorgan|Chase|Monarch|YNAB|NBER|Madrian/i)
      expect(text).not.toMatch(/MoMo|Ví Trả Sau|FinHealth/)
      expect(text).not.toMatch(/cổ phiếu|trái phiếu|chứng chỉ quỹ|tiền số|crypto|vàng|bất động sản/i)
    }
  })
})
