import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { createApiClient } from '@/api/client'
import type { ConfirmActionBlock } from '@/contracts/blocks'
import { validBlock } from '@/test/fixtures'
import { CONVERSATION_ID, Providers, fakeApi, fakeChatActions } from '@/test/helpers'
import proposal from '../../../contracts/fixtures/tools/propose_jar_split.proposed.json'
import { ConfirmActionView } from './walletViews'

it('gửi đúng đề xuất save_jars qua POST /confirmations khi người dùng bấm Xác nhận', async () => {
  const preview = proposal.data.confirm
  const envelope = validBlock('confirm_action.update_profile') as ConfirmActionBlock
  const block: ConfirmActionBlock = {
    ...envelope,
    source: { ...envelope.source, tool: 'ledger___propose_jar_split' },
    data: {
      ...preview,
      tool: 'save_jars',
      expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
    },
  }
  const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 500 }))
  const { createConfirmation } = createApiClient({
    baseUrl: 'https://api.example.invalid',
    getAccessToken: async () => 'test-token',
    fetchImpl,
  })
  const api = fakeApi({ createConfirmation })
  const user = userEvent.setup()
  render(
    <Providers api={api} actions={fakeChatActions()}>
      <ConfirmActionView block={block} blockId={block.id} />
    </Providers>,
  )

  expect(fetchImpl).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Xác nhận' }))
  await waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(1))
  const [url, init] = fetchImpl.mock.calls[0]!
  expect(url).toBe('https://api.example.invalid/confirmations')
  expect(init?.method).toBe('POST')
  expect(JSON.parse(String(init?.body))).toEqual({
    tool: preview.tool,
    params: preview.params,
    params_hash: preview.params_hash,
    conversation_id: CONVERSATION_ID,
    confirm_block_id: block.id,
  })
  expect(api.applyAction).not.toHaveBeenCalled()
})
