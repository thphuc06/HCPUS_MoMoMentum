import { describe, expect, it } from 'vitest'
import { capLevel, shortModelName, shortModelNames } from './format'

describe('shortModelName: tên ngắn suy từ model id bằng luật chung', () => {
  it.each([
    ['global.anthropic.claude-sonnet-4-6', 'Sonnet 4.6'],
    ['global.anthropic.claude-haiku-4-5-20251001-v1:0', 'Haiku 4.5'],
    ['global.amazon.nova-2-lite-v1:0', 'Nova 2 Lite'],
    ['global.moonshotai.kimi-k3', 'Kimi K3'],
    ['cohere.embed-multilingual-v3', 'Embed Multilingual v3'],
    ['amazon.titan-embed-text-v2:0', 'Titan Embed Text v2'],
    ['anthropic.claude-3-5-sonnet-20240620-v1:0', 'Claude 3.5 Sonnet'],
    ['apac.amazon.nova-pro-v1:0', 'Nova Pro'],
    ['unknown', 'Unknown'],
  ])('%s -> %s', (id, name) => {
    expect(shortModelName(id)).toBe(name)
  })

  it('hai id ra cùng tên ngắn: hiện nguyên id cho khỏi lẫn', () => {
    expect(shortModelNames(['apac.anthropic.claude-sonnet-4-6', 'global.anthropic.claude-sonnet-4-6', 'global.amazon.nova-2-lite-v1:0']))
      .toEqual(['apac.anthropic.claude-sonnet-4-6', 'global.anthropic.claude-sonnet-4-6', 'Nova 2 Lite'])
  })
})

describe('capLevel: mức dùng so với trần ngày của một model', () => {
  it.each([
    [0, 400, 'ok'],
    [319, 400, 'ok'],
    [320, 400, 'near'],
    [399, 400, 'near'],
    [400, 400, 'over'],
    [450, 400, 'over'],
    [1599, 2000, 'ok'],
    [1600, 2000, 'near'],
    [0, 0, 'ok'],
    [1, 0, 'over'],
  ] as const)('%i / %i -> %s', (calls, cap, level) => {
    expect(capLevel(calls, cap)).toBe(level)
  })
})
