import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MessageList, supersededAssistantIds } from './MessageList'
import type { ChatItem } from './session'
import { Providers, fakeApi } from '@/test/helpers'
import { validBlock } from '@/test/fixtures'

const user = (id: string): ChatItem => ({ kind: 'user', id, text: `hỏi ${id}` })
const bot = (id: string, text = 'Chưa có khoản tiền nào được chuyển. Bạn bấm Xác nhận trên thẻ.'): ChatItem => ({ kind: 'assistant', id, text, done: true })
const receipt = (): ChatItem => ({ kind: 'block', id: 'receipt:1', raw: validBlock('receipt.move'), resolved: true })
const confirm = (): ChatItem => ({ kind: 'block', id: 'confirm:1', raw: validBlock('confirm.move') })

describe('lời của agent trong lượt có đề nghị đã thực hiện', () => {
  it('chỉ đánh dấu lời của lượt có khối resolved; lượt khác và lượt chưa thực hiện thì không', () => {
    const items: ChatItem[] = [user('u1'), bot('a0', 'Đây là số dư.'), user('u2'), confirm(), bot('a1'), user('u3'), receipt(), bot('a2'), user('u4'), bot('a3')]
    // u2: confirm chưa thực hiện; u3: có biên nhận (resolved); u4: bình thường
    expect([...supersededAssistantIds(items)].sort()).toEqual(['a2'])
  })

  it('không phụ thuộc nội dung chữ: lời nào cũng được đánh dấu như nhau', () => {
    const items: ChatItem[] = [user('u1'), bot('a1', 'Nội dung hoàn toàn khác.'), receipt(), bot('a2', 'Xong rồi nhé.')]
    expect([...supersededAssistantIds(items)].sort()).toEqual(['a1', 'a2'])
  })

  it('hiển thị: chữ giữ nguyên nhưng được làm mờ và ghi "Trước khi bạn xác nhận"; lượt khác không bị ảnh hưởng', () => {
    const items: ChatItem[] = [user('u1'), bot('a0', 'Đây là số dư.'), user('u2'), bot('a1'), receipt()]
    render(
      <Providers api={fakeApi()}>
        <MessageList items={items} running={false} onRetry={vi.fn()} />
      </Providers>,
    )
    const msgs = screen.getAllByTestId('assistant-message')
    expect(msgs).toHaveLength(2)
    expect(msgs[0]).not.toHaveAttribute('data-superseded')
    expect(msgs[1]).toHaveAttribute('data-superseded', 'true')
    expect(msgs[1]).toHaveTextContent('Trước khi bạn xác nhận')
    expect(msgs[1]).toHaveTextContent('Chưa có khoản tiền nào được chuyển') // nội dung không bị sửa
    expect(screen.getAllByText('Trước khi bạn xác nhận')).toHaveLength(1)
    expect(screen.getByText('Đã chuyển 100.000 ₫')).toBeInTheDocument()
  })
})
