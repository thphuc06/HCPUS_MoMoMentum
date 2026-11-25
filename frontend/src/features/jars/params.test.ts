import { describe, expect, it } from 'vitest'
import { saveJarsParams, withPurpose, type JarRowState } from './params'

const items = [{ name: 'Tết', amount_vnd: 920000, needed_date: '2027-01-03' }]
const sinking: JarRowState = {
  code: 'quy_don', name: 'Quỹ dồn', color_key: 'teal', icon_key: 'wallet', kind: 'saving', percent: '10',
  purpose: 'sinking', goal_vnd: 920000, goal_date: '2027-01-03', sinking_items: items, balance_vnd: 0,
}

describe('withPurpose: đổi mục đích bỏ trường không còn hợp', () => {
  it('hết là Quỹ dồn thì bỏ khoản của Quỹ dồn, giữ số tiền và ngày đang hiện', () => {
    for (const purpose of ['goal', 'long_term'] as const) {
      const r = withPurpose(sinking, purpose)
      expect(r).toMatchObject({ purpose, goal_vnd: 920000, goal_date: '2027-01-03' })
      expect(r.sinking_items).toBeUndefined()
    }
  })

  it('thành Dự phòng thì bỏ cả số tiền, ngày (ô đã ẩn) và khoản của Quỹ dồn', () => {
    const r = withPurpose(sinking, 'buffer')
    expect(r.purpose).toBe('buffer')
    expect(r.goal_vnd).toBeUndefined()
    expect(r.goal_date).toBeUndefined()
    expect(r.sinking_items).toBeUndefined()
  })

  it('giữ nguyên mục đích thì không mất gì', () => {
    expect(withPurpose(sinking, 'sinking')).toEqual(sinking)
  })
})

describe('saveJarsParams chỉ gửi trường hợp với mục đích', () => {
  it('không gửi sinking_items cho hũ không phải Quỹ dồn, không gửi mục tiêu cho Dự phòng', () => {
    const [goal, buffer] = saveJarsParams([
      { ...sinking, purpose: 'goal' },
      { ...sinking, code: 'du_phong', purpose: 'buffer' },
    ]).jars as Record<string, unknown>[]
    expect(goal).not.toHaveProperty('sinking_items')
    expect(goal).toMatchObject({ goal_vnd: 920000, goal_date: '2027-01-03' })
    expect(buffer).not.toHaveProperty('sinking_items')
    expect(buffer).not.toHaveProperty('goal_vnd')
    expect(buffer).not.toHaveProperty('goal_date')
  })

  it('Quỹ dồn giữ khoản và ngày đã cam kết', () => {
    const [j] = saveJarsParams([sinking]).jars as Record<string, unknown>[]
    expect(j).toMatchObject({ purpose: 'sinking', sinking_items: items, goal_date: '2027-01-03' })
  })
})
