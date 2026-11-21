import { parse } from 'yaml'
import { describe, expect, it } from 'vitest'
import { ERROR_CODES, HTTP_STATUS } from './errors'
import { ConversationResponse, Resolution, StoredTurn } from '@/chat/repository'
import { ActionRequest, ConfirmationRequest, JarsResponse, ResetResponse } from './schemas'
import { jarsFromFixture } from '@/test/helpers'

// Đối chiếu code frontend với contracts/rest/openapi.yaml (nguồn duy nhất của hợp đồng REST).
const raw = Object.values(
  import.meta.glob('../../../contracts/rest/openapi.yaml', { eager: true, query: '?raw', import: 'default' }),
)[0] as string
const spec = parse(raw) as {
  paths: Record<string, Record<string, { operationId: string }>>
  components: {
    schemas: {
      ErrorCode: { enum: string[]; 'x-http-status': Record<string, number> }
      JarsResponse: { required: string[] }
      ResetResponse: { required: string[] }
      ConversationResponse: { required: string[] }
      ConversationTurn: { required: string[] }
      ConfirmResolution: { oneOf: Array<{ properties: { status: { const?: string; enum?: string[] } } }> }
      ActionRequest: { properties: Record<string, unknown> }
      ConfirmationRequest: { properties: Record<string, unknown> }
    }
  }
}

describe('khớp openapi.yaml', () => {
  it('có các endpoint frontend gọi, đúng method và operationId', () => {
    expect(Object.keys(spec.paths)).toEqual(expect.arrayContaining(['/actions', '/confirmations', '/demo/reset', '/jars', '/conversations/{conversation_id}']))
    expect(spec.paths['/conversations/{conversation_id}']!.get!.operationId).toBe('getConversation')
    expect(spec.paths['/jars']!.get!.operationId).toBe('getJars')
    expect(spec.paths['/confirmations']!.post!.operationId).toBe('createConfirmation')
    expect(spec.paths['/actions']!.post!.operationId).toBe('applyAction')
    expect(spec.paths['/demo/reset']!.post!.operationId).toBe('resetDemo')
  })

  it('ErrorCode: cùng danh sách và cùng HTTP status', () => {
    expect([...ERROR_CODES].sort()).toEqual([...spec.components.schemas.ErrorCode.enum].sort())
    expect(HTTP_STATUS).toEqual(spec.components.schemas.ErrorCode['x-http-status'])
  })

  it('JarsResponse và ResetResponse có đúng các trường bắt buộc', () => {
    expect(Object.keys(JarsResponse.shape).sort()).toEqual([...spec.components.schemas.JarsResponse.required].sort())
    expect(Object.keys(ResetResponse.shape).sort()).toEqual([...spec.components.schemas.ResetResponse.required].sort())
    expect(JarsResponse.safeParse(jarsFromFixture()).success).toBe(true)
  })

  it('trạng thái đề nghị: Resolution khớp ConfirmResolution; hai yêu cầu nhận conversation_id + confirm_block_id', () => {
    const statuses = spec.components.schemas.ConfirmResolution.oneOf.flatMap((o) => o.properties.status.enum ?? [o.properties.status.const!])
    expect(statuses.sort()).toEqual([...Resolution.shape.status.options].sort())
    for (const name of ['ActionRequest', 'ConfirmationRequest'] as const) {
      const props = Object.keys(spec.components.schemas[name].properties)
      expect(props).toEqual(expect.arrayContaining(['conversation_id', 'confirm_block_id']))
    }
    expect(Object.keys(ActionRequest.shape)).toEqual(expect.arrayContaining(['conversation_id', 'confirm_block_id']))
    expect(Object.keys(ConfirmationRequest.shape)).toEqual(expect.arrayContaining(['conversation_id', 'confirm_block_id']))
  })

  it('ConversationResponse và ConversationTurn (phát lại hội thoại) có đúng các trường bắt buộc', () => {
    expect(Object.keys(ConversationResponse.shape).sort()).toEqual([...spec.components.schemas.ConversationResponse.required].sort())
    expect(Object.keys(StoredTurn.shape).sort()).toEqual([...spec.components.schemas.ConversationTurn.required].sort())
  })
})
