import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Disclosure, DisclosureButton, DisclosurePanel, useDisclosure } from './Disclosure'

const reduceMotion = (on: boolean) =>
  vi.stubGlobal('matchMedia', vi.fn((q: string) => ({ matches: on && q === '(prefers-reduced-motion: reduce)', addEventListener: vi.fn(), removeEventListener: vi.fn() })))

afterEach(() => vi.unstubAllGlobals())

describe('Disclosure', () => {
  it('mặc định đóng: nút có aria-expanded=false, aria-controls trỏ vào vùng nội dung đang inert', () => {
    render(<Disclosure label="Chi tiết"><p>Đoạn giải thích dài</p></Disclosure>)
    const button = screen.getByRole('button', { name: 'Chi tiết' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    const panel = document.getElementById(button.getAttribute('aria-controls')!)!
    expect(panel).toContainElement(screen.getByText('Đoạn giải thích dài'))
    expect(panel).toHaveAttribute('inert')
    expect(panel).toHaveAttribute('aria-hidden', 'true')
    expect(panel).toHaveAttribute('data-disclosure-panel', 'closed')
  })

  it('bấm chuột thì mở, bấm lần nữa thì đóng', async () => {
    const user = userEvent.setup()
    render(<Disclosure label="Vì sao?"><p>Lý do</p></Disclosure>)
    const button = screen.getByRole('button', { name: 'Vì sao?' })
    await user.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    const panel = document.getElementById(button.getAttribute('aria-controls')!)!
    expect(panel).not.toHaveAttribute('inert')
    expect(panel).toHaveAttribute('data-disclosure-panel', 'open')
    await user.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'false')
  })

  it('bấm được bằng bàn phím (Tab rồi Enter, Space)', async () => {
    const user = userEvent.setup()
    render(<Disclosure label="Xem căn cứ"><p>Nguồn</p></Disclosure>)
    await user.tab()
    const button = screen.getByRole('button', { name: 'Xem căn cứ' })
    expect(button).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(button).toHaveAttribute('aria-expanded', 'true')
    await user.keyboard(' ')
    expect(button).toHaveAttribute('aria-expanded', 'false')
  })

  it('vùng chạm tối thiểu 44 px và mũi tên xoay khi mở', async () => {
    const user = userEvent.setup()
    render(<Disclosure label="Chi tiết"><p>x</p></Disclosure>)
    const button = screen.getByRole('button', { name: 'Chi tiết' })
    expect(button.className).toMatch(/\bmin-h-11\b/)
    expect(button.className).toMatch(/\bmin-w-11\b/)
    const arrow = button.querySelector('svg')!
    expect(arrow.getAttribute('class')).not.toMatch(/rotate-180/)
    await user.click(button)
    expect(arrow.getAttribute('class')).toMatch(/rotate-180/)
  })

  it('có chuyển động thì mở/đóng mượt; giảm chuyển động thì tắt transition', () => {
    reduceMotion(false)
    const { unmount } = render(<Disclosure label="Chi tiết"><p>x</p></Disclosure>)
    const panelOf = () => document.querySelector('[data-disclosure-panel]')!
    expect(panelOf().className).toMatch(/transition-/)
    expect(screen.getByRole('button').querySelector('svg')!.getAttribute('class')).toMatch(/transition-transform/)
    unmount()
    reduceMotion(true)
    render(<Disclosure label="Chi tiết"><p>x</p></Disclosure>)
    expect(panelOf().className).not.toMatch(/transition-/)
    expect(screen.getByRole('button').querySelector('svg')!.getAttribute('class')).not.toMatch(/transition/)
  })

  it('defaultOpen mở sẵn', () => {
    render(<Disclosure label="Chi tiết" defaultOpen><p>x</p></Disclosure>)
    expect(screen.getByRole('button', { name: 'Chi tiết' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('nút và vùng nội dung tách rời vẫn nối bằng aria-controls; nhãn đầy đủ cho trình đọc màn hình', async () => {
    const user = userEvent.setup()
    function Split() {
      const state = useDisclosure()
      return (
        <div>
          <div><DisclosureButton state={state} label="Vì sao bước Giữ sẵn">Vì sao</DisclosureButton></div>
          <DisclosurePanel state={state}><p>Lý do bước</p></DisclosurePanel>
        </div>
      )
    }
    render(<Split />)
    const button = screen.getByRole('button', { name: 'Vì sao bước Giữ sẵn' })
    const panel = document.getElementById(button.getAttribute('aria-controls')!)!
    expect(panel).toContainElement(screen.getByText('Lý do bước'))
    await user.click(button)
    expect(panel).toHaveAttribute('data-disclosure-panel', 'open')
  })
})
