import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { JarStatusChip } from './JarStatusChip'
import type { JarFull } from '@/api/schemas'

type ChipJar = Pick<JarFull, 'kind' | 'status' | 'runout_date' | 'balance_vnd' | 'has_activity'>

const chip = (jar: ChipJar) => render(<JarStatusChip jar={jar} />).container

describe('JarStatusChip: hũ 0 ₫ chưa từng có tiền (has_activity của server, #39 lỗi 4c)', () => {
  it('hũ chi tiêu 0 ₫ chưa từng có dòng sổ cái (tài khoản mới chưa có lương) không báo "Đang hết tiền" dù dự báo hụt', () => {
    const c = chip({ kind: 'spending', balance_vnd: 0, status: 'short', has_activity: false })
    expect(c).not.toHaveTextContent(/hết tiền/i)
    expect(c).toHaveTextContent('Chưa có tiền')
  })

  it('cùng hũ đó sau khi đã có tiền vào rồi tiêu hết vẫn báo "Đang hết tiền"', () => {
    expect(chip({ kind: 'spending', balance_vnd: 0, status: 'short', has_activity: true })).toHaveTextContent('Đang hết tiền')
    // server cũ chưa gửi trường: giữ hành vi cũ
    expect(chip({ kind: 'spending', balance_vnd: 0, status: 'short' })).toHaveTextContent('Đang hết tiền')
  })

  it('chưa có dự báo: hũ chưa từng có tiền nói "Chưa có tiền", hũ đã tiêu hết vẫn "Đã hết tiền"', () => {
    expect(chip({ kind: 'obligation', balance_vnd: 0, has_activity: false })).toHaveTextContent('Chưa có tiền')
    expect(chip({ kind: 'obligation', balance_vnd: 0, has_activity: true })).toHaveTextContent('Đã hết tiền')
  })

  it('quyết theo dữ liệu, không theo loại hay mã hũ; trạng thái Đủ, Sát của dự báo giữ nguyên', () => {
    for (const kind of ['spending', 'obligation', 'saving'] as const) {
      expect(chip({ kind, balance_vnd: 0, status: 'short', has_activity: false })).toHaveTextContent('Chưa có tiền')
    }
    expect(chip({ kind: 'obligation', balance_vnd: 0, status: 'ok', has_activity: false })).toHaveTextContent('Đủ')
    expect(chip({ kind: 'spending', balance_vnd: 0, status: 'tight', has_activity: false })).toHaveTextContent('Sát')
  })
})

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
