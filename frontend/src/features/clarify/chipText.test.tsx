import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { BlockRenderer } from '@/blocks/registry'
import { Providers, fakeApi, fakeChatActions } from '@/test/helpers'
import { validBlock } from '@/test/fixtures'
import { readableChipText } from './chipText'

type Json = Record<string, any>

describe('readableChipText (chip số tiền của khối clarify)', () => {
  it('số trần thành chữ người đọc được', () => {
    expect(readableChipText('250000', 'amount')).toBe('250 nghìn')
    expect(readableChipText('1200000', 'amount')).toBe('1,2 triệu')
    expect(readableChipText('5000000', 'amount')).toBe('5 triệu')
  })

  it('chữ gọn làm tròn đổi số tiền thì dùng dạng đầy đủ', () => {
    // formatVnd đặt NBSP trước ₫; parser số tiền phía agent đọc được (tests/unit/agent/test_clarify_merge.py)
    expect(readableChipText('1250000', 'amount')).toBe('1.250.000\u00a0₫')
  })

  it('chữ sẵn có và ô khác giữ nguyên', () => {
    expect(readableChipText('1 triệu', 'amount')).toBe('1 triệu')
    expect(readableChipText('Hũ Hóa đơn', 'jar')).toBe('Hũ Hóa đơn')
    expect(readableChipText('250000', 'jar')).toBe('250000')
  })
})

describe('ClarifyView: chip số tiền gửi chữ, không gửi số trần', () => {
  it('bấm chip "250000" gửi "250 nghìn"', async () => {
    const base = validBlock('clarify.amount') as Json
    const raw = { ...base, data: { ...base.data, slot: 'amount', chips: [{ id: 'c1', label: '250000', value: '250000' }] } }
    const actions = fakeChatActions()
    render(
      <Providers api={fakeApi()} actions={actions}>
        <BlockRenderer raw={raw} blockId="b1" />
      </Providers>,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '250 nghìn' }))
    expect(actions.ask).toHaveBeenCalledWith('250 nghìn')
  })
})
