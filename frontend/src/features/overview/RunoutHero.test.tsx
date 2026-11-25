import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RunoutHero } from './RunoutHero'

describe('RunoutHero', () => {
  it('có ngày cạn: số ngày hũ trống trước kỳ lương (như cũ)', () => {
    render(<RunoutHero days={6} />)
    expect(screen.getByTestId('runout-hero')).toHaveTextContent('6 ngày hũ trống trước kỳ lương')
  })

  it('hũ thưa (#25, server không nêu ngày cạn): một dòng "Có thể cạn trước ngày lương" kèm khả năng hụt, không có ngày', () => {
    render(<RunoutHero chance={0.62} />)
    const hero = screen.getByTestId('runout-hero')
    expect(hero).toHaveTextContent(/^Có thể cạn trước ngày lương, khả năng 60%$/)
    expect(hero.textContent).not.toMatch(/\d{2}\/\d{2}/)
    expect(hero).not.toHaveTextContent('ngày hũ trống')
  })

  it('khả năng làm tròn như mọi nơi khác: không nói 100%', () => {
    render(<RunoutHero chance={0.99} />)
    expect(screen.getByTestId('runout-hero')).toHaveTextContent(/^Có thể cạn trước ngày lương, khả năng gần như chắc chắn$/)
  })
})
