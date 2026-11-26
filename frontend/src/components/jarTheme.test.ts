import { ShoppingBasket, Utensils, Wallet } from 'lucide-react'
import { describe, expect, it } from 'vitest'
import { jarColor, jarIconFor } from './jarTheme'

describe('jarTheme: hũ Chi hằng ngày có biểu tượng riêng (#39)', () => {
  it('khóa basket là giỏ, khác biểu tượng Ăn uống và Nghĩa vụ (ví)', () => {
    expect(jarIconFor('basket')).toBe(ShoppingBasket)
    expect(jarIconFor('basket')).not.toBe(Utensils)
    expect(jarIconFor('basket')).not.toBe(Wallet)
  })

  it('khóa lạ vẫn rơi về biểu tượng, màu trung tính', () => {
    expect(jarIconFor('khong_co')).toBe(Wallet)
    expect(jarColor('khong_co')).toBe('var(--jar-nghia-vu)')
    expect(jarColor('brown')).toBe('var(--jar-hoa-don)')
  })
})
