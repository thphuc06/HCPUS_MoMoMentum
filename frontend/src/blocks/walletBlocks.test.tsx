import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import type { ApiClient } from '@/api/client'
import { ApiError } from '@/api/errors'
import { ChatLauncherContext } from '@/chat/launcher'
import type { BlockUi } from '@/chat/session'
import type { ActionResponse } from '@/api/schemas'
import { ALL_BLOCK_TYPES, BLOCK_TYPES, blockSchemas } from '@/contracts/blocks'
import { CONVERSATION_ID, Providers, fakeApi, fakeChatActions } from '@/test/helpers'
import { restFixture, validBlock } from '@/test/fixtures'
import { forecastSummary } from '@/features/forecast/ForecastBlock'
import { BlockRenderer, REGISTERED_TYPES } from './registry'
import { receiptNote } from './useConfirmFlow'

type Json = Record<string, any>

describe('registry: đủ hai mươi bốn khối của hợp đồng', () => {
  it('tất cả khối đã đăng ký và có schema', () => {
    for (const t of ALL_BLOCK_TYPES) {
      expect(REGISTERED_TYPES).toContain(t)
      expect(blockSchemas[t]).toBeDefined()
    }
    expect(ALL_BLOCK_TYPES).toHaveLength(24)
    expect(BLOCK_TYPES).toEqual(ALL_BLOCK_TYPES)
  })
})

describe('forecast_timeline trong chat', () => {
  it('vẽ cùng số với ForecastBlock của màn Chi tiết hũ (cùng tóm tắt, cùng xác suất)', async () => {
    const block = validBlock('forecast_timeline.short') as Json
    render(
      <Providers api={fakeApi()}>
        <BlockRenderer raw={block} blockId={block.id} />
      </Providers>,
    )
    expect(await screen.findByTestId('forecast-summary')).toHaveTextContent(forecastSummary(block.data))
    expect(screen.getByTestId('p-shortfall')).toHaveTextContent('71%')
    expect(screen.queryByRole('button', { name: 'Vì sao' })).toBeNull() // trong chat không có nút Vì sao của màn hình
  })
})

describe('proactive_card', () => {
  const card = () => validBlock('proactive_card.runout') as Json

  it('ngoài router (không có chỗ điều hướng): vẫn vẽ đủ nút, không vỡ', () => {
    render(
      <Providers api={fakeApi()}>
        <BlockRenderer raw={card()} blockId="p1" />
      </Providers>,
    )
    expect(screen.getByText('Hũ Ăn uống dự kiến cạn ngày 29/11')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Xem dự báo' })).toBeInTheDocument()
  })

  it('trong chat: nút làm được việc (Xem dự báo, Hỏi vì sao), không có Để sau / Ít nhắc loại này', async () => {
    const open = vi.fn()
    const close = vi.fn()
    const router = createMemoryRouter([{ path: '/', element: <BlockRenderer raw={card()} blockId="p1" /> }, { path: '/jars/:code', element: <p>CHI TIẾT HŨ</p> }])
    render(
      <ChatLauncherContext.Provider value={{ open, close }}>
        <Providers api={fakeApi()}>
          <RouterProvider router={router} />
        </Providers>
      </ChatLauncherContext.Provider>,
    )
    expect(screen.queryByRole('button', { name: 'Để sau' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Ít nhắc loại này' })).toBeNull()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Hỏi vì sao' }))
    expect(open).toHaveBeenCalledWith('Vì sao hũ Ăn uống sắp cạn?') // câu do khối (server) dựng
    await user.click(screen.getByRole('button', { name: 'Xem dự báo' }))
    expect(close).toHaveBeenCalled()
    expect(await screen.findByText('CHI TIẾT HŨ')).toBeInTheDocument()
  })
})

describe('receipt_action', () => {
  it('chi tiết, số dư sau (có dấu) và mã tham chiếu rút gọn; có việc kế tiếp thì có nút', async () => {
    const block = validBlock('receipt_action.record_transaction') as Json
    render(
      <Providers api={fakeApi()}>
        <BlockRenderer raw={block} blockId={block.id} />
      </Providers>,
    )
    const section = document.querySelector('[data-block="receipt_action"]') as HTMLElement
    expect(within(section).getByText(block.data.summary)).toBeInTheDocument()
    for (const d of block.data.details) expect(within(section).getByText(d.value)).toBeInTheDocument()
    expect(within(section).getByText(String(block.data.reference_id).slice(0, 8).toUpperCase())).toBeInTheDocument()
  })

  it('follow_up lương: trong router có nút dẫn tới màn Lương về', async () => {
    const block = restFixture('ActionResponse.receipt_action') as Json
    expect(block.data.follow_up.kind).toBe('confirm_salary')
    const router = createMemoryRouter([{ path: '/', element: <BlockRenderer raw={block} blockId={block.id} /> }, { path: '/salary', element: <p>MÀN LƯƠNG</p> }])
    render(
      <Providers api={fakeApi()}>
        <RouterProvider router={router} />
      </Providers>,
    )
    await userEvent.setup().click(screen.getByRole('button', { name: block.data.follow_up.label }))
    expect(await screen.findByText('MÀN LƯƠNG')).toBeInTheDocument()
  })
})

describe('confirm_action: xác nhận trước khi ghi (ADR-0002)', () => {
  function confirmAction(expiresInMs = 10 * 60_000): Json {
    const b = validBlock('confirm_action.record_transaction') as Json
    b.data.expires_at = new Date(Date.now() + expiresInMs).toISOString().replace(/\.\d+Z$/, 'Z')
    return b
  }

  function setup(over: Partial<ApiClient> = {}, ui?: BlockUi, expiresInMs?: number) {
    const block = confirmAction(expiresInMs)
    const receipt = restFixture('ActionResponse.receipt_action') as unknown as ActionResponse
    const api = fakeApi({
      createConfirmation: vi.fn(async () => ({
        confirm_token: 'abc.def',
        expires_at: '2026-12-10T03:02:00Z',
        ttl_seconds: 120,
        tool: 'record_transaction' as const,
        params: block.data.params,
        params_hash: block.data.params_hash,
      })),
      applyAction: vi.fn(async () => receipt),
      ...over,
    })
    const actions = fakeChatActions()
    render(
      <Providers api={api} actions={actions}>
        <BlockRenderer raw={block} blockId={block.id} ui={ui} />
      </Providers>,
    )
    return { api, actions, block, receipt, user: userEvent.setup() }
  }

  it('hiện tóm tắt, các dòng trước → sau, cảnh báo và đếm ngược; chưa bấm thì chưa gọi API', () => {
    const { api, block } = setup()
    expect(screen.getByText(block.data.summary)).toBeInTheDocument()
    for (const c of block.data.changes) expect(screen.getByText(c.label)).toBeInTheDocument()
    if (block.data.warnings) for (const w of block.data.warnings) expect(screen.getByText(w)).toBeInTheDocument()
    expect(screen.getByText(/Đề nghị còn/)).toBeInTheDocument()
    expect(api.createConfirmation).not.toHaveBeenCalled()
    expect(api.applyAction).not.toHaveBeenCalled()
  })

  it('bấm Xác nhận: /confirmations nguyên tool + params + hash + confirm_block_id -> /actions kèm token -> biên nhận thay chỗ -> làm mới dữ liệu -> ghi chú hệ thống', async () => {
    const { api, actions, block, receipt, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Xác nhận' }))
    await waitFor(() => expect(actions.replaceBlock).toHaveBeenCalled())
    const ref = { conversation_id: CONVERSATION_ID, confirm_block_id: block.id }
    expect(api.createConfirmation).toHaveBeenCalledWith({ tool: block.data.tool, params: block.data.params, params_hash: block.data.params_hash, ...ref })
    expect(api.applyAction).toHaveBeenCalledWith({ tool: 'record_transaction', params: block.data.params, confirm_token: 'abc.def', ...ref })
    expect(actions.replaceBlock).toHaveBeenCalledWith(block.id, receipt, receipt.id, { fresh: true })
    expect(actions.addSystemNote).toHaveBeenCalledWith(receiptNote(receipt), receipt.id)
    // Tổng quan nạp lần đầu + lần làm mới sau khi ghi
    await waitFor(() => expect(api.getOverview).toHaveBeenCalledTimes(2))
  })

  it('receiptNote nhận cả receipt (chuyển hũ) lẫn receipt_action', () => {
    const a = receiptNote(restFixture('ActionResponse.receipt_action') as unknown as ActionResponse)
    expect(a).toContain('đã xác nhận trên giao diện')
    expect(a).toContain('Mã tham chiếu')
    const b = receiptNote(restFixture('ActionResponse.receipt') as unknown as ActionResponse)
    expect(b).toContain('Mã giao dịch')
  })

  it('Không: gọi đường hủy của hợp đồng (POST /confirmations/cancel) rồi đánh dấu hủy; không cấp token', async () => {
    const { api, actions, block, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Không' }))
    await waitFor(() => expect(actions.markBlock).toHaveBeenCalledWith(block.id, 'cancelled'))
    expect(api.cancelConfirmation).toHaveBeenCalledWith({ conversation_id: CONVERSATION_ID, confirm_block_id: block.id })
    expect(api.createConfirmation).not.toHaveBeenCalled()
  })

  it('đã hủy / đã thực hiện / hết hạn: không còn nút xác nhận hoạt động', () => {
    setup({}, 'cancelled')
    expect(screen.getByText(/Đã hủy/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Xác nhận' })).toBeNull()
  })

  it('hết hạn: nút bị vô hiệu và nói rõ số liệu có thể đã cũ', () => {
    setup({}, undefined, -60_000)
    expect(screen.getByRole('button', { name: 'Xác nhận' })).toBeDisabled()
    expect(screen.getByText(/đã hết hạn/)).toBeInTheDocument()
  })

  it('server báo vượt hạn mức Trả sau: hiện thông báo tiếng Việt và khóa nút', async () => {
    const { user } = setup({ createConfirmation: vi.fn(async () => { throw new ApiError('CREDIT_LIMIT_EXCEEDED', 422) }) })
    await user.click(screen.getByRole('button', { name: 'Xác nhận' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Vượt hạn mức Trả sau')
    expect(screen.getByRole('button', { name: 'Xác nhận' })).toBeDisabled()
  })
})
