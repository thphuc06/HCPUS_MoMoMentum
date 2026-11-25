import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { JarStatusChip } from './JarStatusChip'
import type { JarFull } from '@/api/schemas'

type ChipJar = Pick<JarFull, 'kind' | 'status' | 'runout_date' | 'balance_vnd'>

const chip = (jar: ChipJar) => render(<JarStatusChip jar={jar} />).container

describe('JarStatusChip: hũ 0 ₫ chưa có dự báo (#39)', () => {
  it('hũ để dành 0 ₫ (hũ mới thêm, chưa nạp tiền) không mang chip "Đã hết tiền": nói thật là chưa có dự báo', () => {
    const c = chip({ kind: 'saving', balance_vnd: 0 })
    expect(c).not.toHaveTextContent(/hết tiền/i)
    expect(c).toHaveTextContent('Chưa có dự báo')
  })

  it.each(['spending', 'obligation'] as const)('hũ %s 0 ₫ chưa có dự báo vẫn báo "Đã hết tiền"', (kind) => {
    expect(chip({ kind, balance_vnd: 0 })).toHaveTextContent('Đã hết tiền')
  })

  it('hũ có dự báo đi theo trạng thái của server, cả hũ để dành', () => {
    expect(chip({ kind: 'saving', balance_vnd: 0, status: 'ok' })).toHaveTextContent('Đủ')
    expect(chip({ kind: 'spending', balance_vnd: 200_000, status: 'short', runout_date: '2026-11-27' })).toHaveTextContent('Hụt · cạn 27/11')
    expect(chip({ kind: 'spending', balance_vnd: 200_000 })).toHaveTextContent('Chưa có dự báo')
  })
})
