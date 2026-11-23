import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ResilienceScoreResponse } from '@/api/resilienceSchemas'
import { restFixture, validBlock } from '@/test/fixtures'
import { backend, callsTo, mountApp } from '@/test/mountApp'

describe('chi tiết điểm chống chịu', () => {
  it('hiện các thành phần kèm giải thích, đánh dấu yếu nhất, điểm cũ và disclaimer', async () => {
    const { data } = ResilienceScoreResponse.parse(restFixture('ResilienceScoreResponse.minh'))
    const { calls } = mountApp(backend(), '/foresight/resilience')

    const list = await screen.findByRole('list')
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(data.components.length)
    data.components.forEach((component, index) => {
      const row = within(rows[index]!)
      expect(row.getByText(component.label)).toBeInTheDocument()
      expect(row.getByText(component.explanation)).toBeInTheDocument()
      expect(Boolean(row.queryByText('Yếu nhất'))).toBe(component.key === data.weakest)
    })
    expect(screen.getByText(`Điểm lần trước ${data.previous_score}/100`)).toBeInTheDocument()
    expect(screen.getByText(data.disclaimer)).toBeInTheDocument()
    expect(callsTo(calls, 'GET', '/resilience')).toHaveLength(1)
  })

  it('ghi rõ Plan không áp dụng khi chưa có mục tiêu', async () => {
    const block = ResilienceScoreResponse.parse(validBlock('resilience_score.no_goal'))
    const plan = block.data.components.find((component) => component.key === 'plan')!
    mountApp(backend({ 'GET /resilience': block }), '/foresight/resilience')

    const explanation = await screen.findByText(plan.explanation)
    const row = within(explanation.closest('li')!)
    expect(row.getByText(plan.label)).toBeInTheDocument()
    expect(row.getByText('Không áp dụng')).toBeInTheDocument()
    expect(screen.queryByText(/^Điểm lần trước/)).not.toBeInTheDocument()
  })
})
