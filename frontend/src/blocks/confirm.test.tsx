import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/errors'
import type { ApiClient } from '@/api/client'
import { BlockRenderer } from './registry'
import { receiptNote } from './useConfirmFlow'
import { CONVERSATION_ID, Providers, fakeApi, fakeChatActions } from '@/test/helpers'
import type { BlockUi } from '@/chat/session'
import { validBlock } from '@/test/fixtures'
import type { ReceiptBlock } from '@/contracts/blocks'

type ConfirmFixture = { id: string; data: { tool: string; params: Record<string, unknown>; params_hash: string; expires_at: string } }

/** Fixture confirm với hạn của đề nghị tính theo giờ thật (mặc định còn 10 phút). */
function confirmBlock(expiresInMs = 10 * 60_000): ConfirmFixture {
  const b = validBlock('confirm.move') as ConfirmFixture
  b.data.expires_at = new Date(Date.now() + expiresInMs).toISOString().replace(/\.\d+Z$/, 'Z')
  return b
}

function issued() {
  const b = confirmBlock()
  return {
    confirm_token: 'abc123.def456',
    expires_at: '2026-12-10T03:02:00Z',
    ttl_seconds: 120,
    tool: 'move_between_jars' as const,
    params: b.data.params as { from_jar: string; to_jar: string; amount_vnd: number },
    params_hash: b.data.params_hash,
  }
}

function setup(over: Partial<ApiClient> = {}, ui?: BlockUi, expiresInMs?: number) {
  const receipt = validBlock('receipt.move') as unknown as ReceiptBlock
  const api = fakeApi({
    createConfirmation: vi.fn(async () => issued()),
    applyAction: vi.fn(async () => receipt),
    ...over,
  })
  const actions = fakeChatActions()
  const block = confirmBlock(expiresInMs)
  render(
    <Providers api={api} actions={actions}>
      <BlockRenderer raw={block} blockId={block.id} ui={ui} />
    </Providers>,
  )
  return { api, actions, block, receipt, user: userEvent.setup() }
}

const confirmButton = () => screen.getByRole('button', { name: /Xác nhận chuyển/ })

describe('luồng xác nhận (ADR-0002)', () => {
  it('hiện đúng số tiền, xem trước hai hũ và đếm ngược của đề nghị', () => {
    setup()
    expect(screen.getByText('Chuyển 100.000 ₫ từ Giải trí sang Ăn uống')).toBeInTheDocument()
    expect(confirmButton()).toHaveTextContent('Xác nhận chuyển 100.000 ₫')
    expect(screen.getByText('660.000 ₫')).toBeInTheDocument()
    expect(screen.getByText('480.000 ₫')).toBeInTheDocument()
    expect(screen.getByText(/^(10:00|09:5\d)$/)).toBeInTheDocument() // đề nghị còn khoảng 10 phút
    expect(screen.getByRole('button', { name: 'Không' })).toBeEnabled()
  })

  it('bấm xác nhận: /confirmations (tool + params nguyên từ khối) -> /actions kèm token -> receipt thay confirm -> tải lại số dư -> ghi chú hệ thống', async () => {
    const { api, actions, block, receipt, user } = setup()
    await user.click(confirmButton())
    await waitFor(() => expect(actions.replaceBlock).toHaveBeenCalled())

    expect(api.createConfirmation).toHaveBeenCalledTimes(1)
    // Cả hai lời gọi kèm đề nghị đang thực hiện: server chỉ cho thực hiện một lần và lưu biên nhận gắn với nó.
    const ref = { conversation_id: CONVERSATION_ID, confirm_block_id: block.id }
    expect(api.createConfirmation).toHaveBeenCalledWith({
      tool: block.data.tool,
      params: block.data.params,
      params_hash: block.data.params_hash,
      ...ref,
    })
    expect(api.applyAction).toHaveBeenCalledTimes(1)
    expect(api.applyAction).toHaveBeenCalledWith({ tool: 'move_between_jars', params: block.data.params, confirm_token: 'abc123.def456', ...ref })

    // thứ tự: cấp token trước, ghi sau
    const order = [
      (api.createConfirmation as ReturnType<typeof vi.fn>).mock.invocationCallOrder[0]!,
      (api.applyAction as ReturnType<typeof vi.fn>).mock.invocationCallOrder[0]!,
    ]
    expect(order[0]).toBeLessThan(order[1]!)

    expect(actions.replaceBlock).toHaveBeenCalledWith(block.id, receipt, receipt.id)
    expect(actions.addSystemNote).toHaveBeenCalledTimes(1)
    expect(actions.addSystemNote.mock.calls[0]![1]).toBe(receipt.id) // cùng khóa với lúc đồng bộ lại từ server: chỉ một ghi chú
    const note = actions.addSystemNote.mock.calls[0]![0] as string
    expect(note).toBe(receiptNote(receipt))
    expect(note).toContain('đã xác nhận')
    expect(note).toContain('100.000 ₫')
    expect(note).toContain(receipt.data.transaction_id)

    // JarsProvider: lần nạp đầu + lần làm mới sau khi ghi
    await waitFor(() => expect(api.getJars).toHaveBeenCalledTimes(2))
  })

  it('bấm hai lần liên tiếp vẫn chỉ gọi một lần', async () => {
    let release!: (v: ReturnType<typeof issued>) => void
    const pending = new Promise<ReturnType<typeof issued>>((r) => (release = r))
    const { api, user } = setup({ createConfirmation: vi.fn(() => pending) })
    const btn = confirmButton()
    await user.click(btn)
    await user.click(btn)
    expect(api.createConfirmation).toHaveBeenCalledTimes(1)
    const busy = screen.getByRole('button', { name: /Đang xác nhận/ })
    expect(busy).toBeDisabled()
    await act(async () => release(issued()))
  })

  it('"Không": đánh dấu hủy, không gọi API nào', async () => {
    const { api, actions, block, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Không' }))
    expect(actions.markBlock).toHaveBeenCalledWith(block.id, 'cancelled')
    expect(api.createConfirmation).not.toHaveBeenCalled()
    expect(api.applyAction).not.toHaveBeenCalled()
    expect(actions.replaceBlock).not.toHaveBeenCalled()
  })

  it('đã hủy (ui=cancelled): chỉ còn dòng "Đã hủy", không còn nút', () => {
    setup({}, 'cancelled')
    expect(screen.getByText(/Đã hủy/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Xác nhận chuyển/ })).toBeNull()
  })

  it('token hết hạn (403 TOKEN_EXPIRED): báo bằng tiếng Việt và cho bấm lại, lần sau lấy token mới', async () => {
    const createConfirmation = vi
      .fn()
      .mockResolvedValueOnce(issued())
      .mockResolvedValueOnce({ ...issued(), confirm_token: 'moi.token' })
    const applyAction = vi
      .fn()
      .mockRejectedValueOnce(new ApiError('TOKEN_EXPIRED', 403))
      .mockResolvedValueOnce(validBlock('receipt.move'))
    const { actions, user } = setup({ createConfirmation, applyAction })
    await user.click(confirmButton())
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Phiên xác nhận đã hết hạn'))
    expect(confirmButton()).toBeEnabled()
    expect(actions.replaceBlock).not.toHaveBeenCalled()

    await user.click(confirmButton())
    await waitFor(() => expect(actions.replaceBlock).toHaveBeenCalled())
    expect(createConfirmation).toHaveBeenCalledTimes(2) // bấm lại lấy token mới, không dùng lại token cũ
    expect(applyAction).toHaveBeenLastCalledWith(expect.objectContaining({ confirm_token: 'moi.token' }))
  })

  it('token đã dùng (409 TOKEN_REUSED): khóa nút và tải lại số dư vì có thể đã ghi', async () => {
    const { api, user } = setup({ applyAction: vi.fn().mockRejectedValue(new ApiError('TOKEN_REUSED', 409)) })
    await user.click(confirmButton())
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('đã được thực hiện trước đó'))
    expect(confirmButton()).toBeDisabled()
    await waitFor(() => expect(api.getJars).toHaveBeenCalledTimes(2))
  })

  it('đề nghị đã thực hiện rồi (409 ALREADY_APPLIED): khóa nút, tải lại số dư và đồng bộ trạng thái từ server', async () => {
    const { api, actions, user } = setup({ applyAction: vi.fn().mockRejectedValue(new ApiError('ALREADY_APPLIED', 409)) })
    await user.click(confirmButton())
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('đã được thực hiện rồi'))
    expect(confirmButton()).toBeDisabled()
    expect(actions.replaceBlock).not.toHaveBeenCalled()
    await waitFor(() => expect(actions.reloadConversation).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(api.getJars).toHaveBeenCalledTimes(2))
  })

  it('server từ chối cấp token vì đề nghị đã thực hiện (409 ALREADY_APPLIED ở /confirmations): cũng khóa nút', async () => {
    const { api, user } = setup({ createConfirmation: vi.fn().mockRejectedValue(new ApiError('ALREADY_APPLIED', 409)) })
    await user.click(confirmButton())
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('đã được thực hiện rồi'))
    expect(confirmButton()).toBeDisabled()
    expect(api.applyAction).not.toHaveBeenCalled()
  })

  it('không đủ số dư (422): hiện lý do, khóa nút xác nhận, vẫn bấm được "Không"', async () => {
    const { user } = setup({ createConfirmation: vi.fn().mockRejectedValue(new ApiError('INSUFFICIENT_FUNDS', 422)) })
    await user.click(confirmButton())
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('không đủ số dư'))
    expect(confirmButton()).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Không' })).toBeEnabled()
  })

  it('mất mạng: báo lỗi, cho thử lại', async () => {
    const { user } = setup({ createConfirmation: vi.fn().mockRejectedValue(new ApiError('NETWORK', 0)) })
    await user.click(confirmButton())
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Không kết nối được'))
    expect(confirmButton()).toBeEnabled()
  })

  it('server báo hết hạn (ui=expired) dù đồng hồ máy còn hạn: không có nút bấm được', () => {
    const { api } = setup({}, 'expired', 10 * 60_000)
    expect(screen.getByText(/đã hết hạn nên số dư xem trước có thể đã cũ/)).toBeInTheDocument()
    expect(confirmButton()).toBeDisabled()
    expect(api.createConfirmation).not.toHaveBeenCalled()
  })

  it('server báo đã thực hiện nhưng không có biên nhận dùng được (ui=done): chỉ còn dòng trạng thái, không nút', () => {
    setup({}, 'done')
    expect(screen.getByText(/đã được thực hiện rồi/)).toBeInTheDocument()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('đề nghị quá hạn (expires_at): vô hiệu nút xác nhận và bảo hỏi lại', async () => {
    const { api } = setup({}, undefined, -1000)
    expect(screen.getByText(/đã hết hạn nên số dư xem trước có thể đã cũ/)).toBeInTheDocument()
    expect(confirmButton()).toBeDisabled()
    expect(api.createConfirmation).not.toHaveBeenCalled()
  })
})
