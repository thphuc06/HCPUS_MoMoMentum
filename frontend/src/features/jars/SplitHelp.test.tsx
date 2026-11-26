import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { JarTemplate } from '@/api/schemas'
import { restFixture } from '@/test/fixtures'
import { backend, json, mountApp } from '@/test/mountApp'
import { SplitHelp } from './SplitHelp'

// Nút "?" cạnh tiêu đề phần chia tỷ lệ (màn "Thêm hoặc sửa hũ" và bước 2 của onboarding): mở tấm trợ giúp, đóng bằng nút,
// Esc hoặc chạm ra ngoài, trả tiêu điểm về nút; số chỉ lấy từ `GET /jar-templates`.

const TEMPLATES: JarTemplate[] = [
  { code: 'chi_hang_ngay', name: 'Chi hằng ngày', color_key: 'violet', icon_key: 'utensils', kind: 'spending', default_split_percent: 42, is_default: true },
  { code: 'nghia_vu', name: 'Nghĩa vụ', color_key: 'amber', icon_key: 'receipt', kind: 'obligation', default_split_percent: 33, is_default: true },
  { code: 'du_phong', name: 'Dự phòng', color_key: 'blue', icon_key: 'shield', kind: 'saving', purpose: 'buffer', default_split_percent: 25, is_default: true },
  { code: 'quy_don', name: 'Quỹ dồn', color_key: 'teal', icon_key: 'landmark', kind: 'saving', purpose: 'sinking', default_split_percent: 0, is_default: false },
]

const helpButton = () => screen.getByRole('button', { name: 'Cách chia hũ hợp lý' })
/** Nút "?" lúc tấm đang mở: hộp thoại modal ẩn phần ngoài tấm khỏi cây trợ năng, nên phải tìm cả phần đang ẩn. */
const helpButtonWhileOpen = () => screen.getByRole('button', { name: 'Cách chia hũ hợp lý', hidden: true })
const findHelpButton = () => screen.findByRole('button', { name: 'Cách chia hũ hợp lý' })
const dialog = () => screen.findByRole('dialog', { name: 'Chia hũ sao cho hợp lý' })
const noDialog = () => waitFor(() => expect(screen.queryByRole('dialog', { name: 'Chia hũ sao cho hợp lý' })).not.toBeInTheDocument())

beforeEach(() => localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

describe('SplitHelp', () => {
  it('nút có nhãn trợ năng, báo mở hộp thoại, vùng chạm 44 px; mặc định đóng', () => {
    render(<SplitHelp place="edit" templates={TEMPLATES} />)
    const button = helpButton()
    expect(button).toHaveAttribute('aria-haspopup', 'dialog')
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(button.className).toMatch(/\bsize-11\b/)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('bấm chuột thì mở tấm có tiêu đề, ghi chú cho trình đọc màn hình và các gạch đầu dòng; nút Đóng đóng và trả tiêu điểm về nút', async () => {
    const user = userEvent.setup()
    render(<SplitHelp place="edit" templates={TEMPLATES} />)
    await user.click(helpButton())
    const panel = await dialog()
    expect(helpButtonWhileOpen()).toHaveAttribute('aria-expanded', 'true')
    expect(panel).toHaveAccessibleDescription(/Hướng dẫn chung/)
    const tips = within(panel).getByRole('list', { name: 'Gợi ý chia hũ' })
    expect(within(tips).getAllByRole('listitem').length).toBeGreaterThanOrEqual(5)
    expect(within(tips).getAllByRole('listitem').length).toBeLessThanOrEqual(7)
    await user.click(within(panel).getByRole('button', { name: 'Đóng' }))
    await noDialog()
    await waitFor(() => expect(helpButton()).toHaveFocus())
    expect(helpButton()).toHaveAttribute('aria-expanded', 'false')
  })

  it('phím Esc đóng và trả tiêu điểm về nút', async () => {
    const user = userEvent.setup()
    render(<SplitHelp place="edit" templates={TEMPLATES} />)
    helpButton().focus()
    await user.keyboard('{Enter}')
    const panel = await dialog()
    await waitFor(() => expect(panel).toContainElement(document.activeElement as HTMLElement)) // tiêu điểm vào trong tấm
    await user.keyboard('{Escape}')
    await noDialog()
    await waitFor(() => expect(helpButton()).toHaveFocus())
  })

  it('chạm ra ngoài tấm thì đóng', async () => {
    const user = userEvent.setup()
    render(<SplitHelp place="edit" templates={TEMPLATES} />)
    await user.click(helpButton())
    await dialog()
    const backdrop = document.querySelector('[data-slot="drawer-overlay"]') as HTMLElement
    expect(backdrop).toBeTruthy()
    await user.click(backdrop)
    await noDialog()
    // Trả tiêu điểm sau khi chạm ra ngoài do Base UI quyết theo trình duyệt (chỉ khi `focus({ preventScroll })` được hỗ trợ,
    // để không nhảy cuộn trên Chrome Android); jsdom không hỗ trợ tùy chọn này nên không kiểm ở đây (kiểm trên Chrome thật).
  })

  it('có dữ liệu: dòng mặc định lấy tên và tỷ lệ từ mẫu hũ của server', async () => {
    const user = userEvent.setup()
    render(<SplitHelp place="edit" templates={TEMPLATES} />)
    await user.click(helpButton())
    const panel = await dialog()
    expect(within(panel).getByTestId('split-help-defaults')).toHaveTextContent('Mặc định: Chi hằng ngày 42% · Nghĩa vụ 33% · Dự phòng 25%')
    expect(panel).not.toHaveTextContent(/Quỹ dồn 0%/)
  })

  it('thiếu dữ liệu: vẫn mở được, nói định tính, không có dòng số', async () => {
    const user = userEvent.setup()
    render(<SplitHelp place="onboarding" />)
    await user.click(helpButton())
    const panel = await dialog()
    expect(within(panel).queryByTestId('split-help-defaults')).not.toBeInTheDocument()
    expect(panel).toHaveTextContent(/tiền tiêu hằng ngày/i)
    expect(panel).toHaveTextContent(/mức sàn/)
  })

  it('"Xem thêm" thu gọn mặc định đóng, bấm thì mở', async () => {
    const user = userEvent.setup()
    render(<SplitHelp place="onboarding" templates={TEMPLATES} />)
    await user.click(helpButton())
    const panel = await dialog()
    const more = within(panel).getByRole('button', { name: 'Xem thêm' })
    expect(more).toHaveAttribute('aria-expanded', 'false')
    await user.click(more)
    expect(more).toHaveAttribute('aria-expanded', 'true')
    expect(within(panel).getByText(/kỳ này hay từ kỳ sau/)).toBeVisible()
  })
})

describe('nút trợ giúp ở hai nơi chia tỷ lệ', () => {
  it('màn "Thêm hoặc sửa hũ": nút ở đầu màn, số lấy từ GET /jar-templates', async () => {
    mountApp(backend({ 'GET /jar-templates': { templates: TEMPLATES } }), '/jars/edit')
    const user = userEvent.setup()
    await screen.findByLabelText('Tỷ lệ chia lương của Ăn uống')
    const header = screen.getByRole('heading', { name: 'Thêm hoặc sửa hũ' }).closest('header')!
    expect(within(header).getByRole('button', { name: 'Cách chia hũ hợp lý' })).toBeInTheDocument()
    await user.click(helpButton())
    const panel = await dialog()
    expect(within(panel).getByTestId('split-help-defaults')).toHaveTextContent('Chi hằng ngày 42% · Nghĩa vụ 33% · Dự phòng 25%')
    expect(panel).not.toHaveTextContent(/bước 3/)
  })

  it('màn "Thêm hoặc sửa hũ": mẫu hũ lỗi thì nút vẫn có và tấm không vỡ', async () => {
    mountApp(backend({ 'GET /jar-templates': json(503, { error: { code: 'INTERNAL', message: 'x' } }) }), '/jars/edit')
    const user = userEvent.setup()
    await user.click(await findHelpButton())
    const panel = await dialog()
    expect(within(panel).queryByTestId('split-help-defaults')).not.toBeInTheDocument()
    expect(within(panel).getByRole('list', { name: 'Gợi ý chia hũ' })).toBeInTheDocument()
  })

  it('bước chia hũ của onboarding: nút cạnh tiêu đề, lời chỉ tới bước kê khai', async () => {
    mountApp(backend({ 'GET /overview': restFixture('OverviewResponse.minh'), 'GET /jar-templates': { templates: TEMPLATES } }), '/onboarding')
    const user = userEvent.setup()
    const heading = await screen.findByRole('heading', { name: 'Chia lương vào các hũ' })
    expect(within(heading.parentElement!).getByRole('button', { name: 'Cách chia hũ hợp lý' })).toBeInTheDocument()
    await user.click(helpButton())
    const panel = await dialog()
    expect(within(panel).getByTestId('split-help-defaults')).toHaveTextContent('Chi hằng ngày 42% · Nghĩa vụ 33% · Dự phòng 25%')
    expect(panel).toHaveTextContent(/bước 3/)
    await user.keyboard('{Escape}')
    await noDialog()
    expect(screen.getByRole('heading', { name: 'Chia lương vào các hũ' })).toBeInTheDocument() // vẫn ở bước 2
  })
})
