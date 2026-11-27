import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { expect, it } from 'vitest'
import { ApiProvider } from '@/api/ApiProvider'
import { fakeApi } from '@/test/helpers'
import { ConsentSection } from './ConsentSection'

it('mở mục về nơi xử lý dữ liệu để xem thông tin Singapore, Bedrock và bản demo', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter><ApiProvider client={fakeApi()}><ConsentSection /></ApiProvider></MemoryRouter>)

  const disclosure = await screen.findByRole('button', { name: 'Dữ liệu được xử lý ở đâu?' })
  expect(disclosure).toHaveAttribute('aria-expanded', 'false')
  await user.click(disclosure)
  expect(disclosure).toHaveAttribute('aria-expanded', 'true')
  const copy = screen.getByText(/AWS tại Singapore \(ap-southeast-1\)/)
  expect(copy).toBeVisible()
  expect(copy).toHaveTextContent(/Amazon Bedrock có thể xử lý dữ liệu ngoài Singapore/)
  expect(copy).toHaveTextContent('Bản demo dùng dữ liệu tổng hợp.')
})
