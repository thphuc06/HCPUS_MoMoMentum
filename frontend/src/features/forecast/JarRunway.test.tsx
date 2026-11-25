import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { beforeEach, describe, expect, it } from 'vitest'
import { JarDetailResponse, type JarFull, type NextPayday } from '@/api/schemas'
import { restFixture } from '@/test/fixtures'
import { JarRunway } from './JarRunway'

// Hũ Giải trí thưa (#25): server không nêu ngày cạn (`runout_date_shown: false`, không có `runout_date`), khả năng hụt 62%.
const sparse = (): JarFull => JarDetailResponse.parse(restFixture('JarDetailResponse.giai_tri_thua')).jar
const PAYDAY: NextPayday = { date: '2026-12-05', days_until: 14, state: 'expected' }

function mount(jar: JarFull) {
  const router = createMemoryRouter([
    { path: '/', element: <JarRunway jars={[jar]} appDate="2026-11-21" nextPayday={PAYDAY} obligations={[]} forecast={null} /> },
  ])
  return render(<RouterProvider router={router} />)
}

// "cạn 29/11", "dự kiến cạn 29/11", "Hụt · cạn 29/11": mọi cách nêu một ngày cạn cụ thể
const RUNOUT_DATE = /cạn (ngày )?\d{2}\/\d{2}/i

describe('JarRunway: hũ thưa không nêu ngày cạn (#25)', () => {
  beforeEach(() => sessionStorage.clear())

  it('cờ sai: một dòng "Có thể cạn trước ngày lương" kèm %, chip chỉ "Hụt", đường băng không có chấm ngày cạn', () => {
    const { container } = mount(sparse())
    const row = container.querySelector('[data-runway="giai_tri"]') as HTMLElement
    expect(row).toHaveTextContent('Có thể cạn trước ngày lương, khả năng 60%')
    expect(row.querySelector('[data-chip]')).toHaveTextContent(/^Hụt$/)
    expect(row.querySelector('[data-part="runout"]')).toBeNull()
    expect(row.querySelector('[data-part="empty"]')).not.toBeNull() // vẫn tô vùng hụt tới kỳ lương
    expect(screen.getByRole('link', { name: /Giải trí: có thể cạn trước ngày lương/ })).toBeInTheDocument()
    expect(container.textContent).not.toMatch(RUNOUT_DATE)
  })

  it('cờ sai mà dữ liệu cũ còn ngày cạn: vẫn không hiện ngày', () => {
    const { container } = mount({ ...sparse(), runout_date: '2026-12-03' })
    expect(container.textContent).not.toMatch(RUNOUT_DATE)
    expect(container.querySelector('[data-part="runout"]')).toBeNull()
  })

  it('cờ đúng hoặc vắng: như cũ (chip và chấm ngày cạn)', () => {
    const { runout_date_shown: _, ...shown } = sparse()
    const { container } = mount({ ...shown, runout_date: '2026-11-29' })
    const row = container.querySelector('[data-runway="giai_tri"]') as HTMLElement
    expect(row.querySelector('[data-chip]')).toHaveTextContent('Hụt · cạn 29/11')
    expect(row.querySelector('[data-part="runout"]')).not.toBeNull()
    expect(row).not.toHaveTextContent('Có thể cạn trước ngày lương')
    expect(row).toHaveTextContent('Khả năng hụt 60%')
  })
})
