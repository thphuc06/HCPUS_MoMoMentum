// Fixture dùng chung với phía Python: contracts/fixtures (chỉ nạp trong test, không vào bundle sản phẩm).

type Json = Record<string, unknown>

const valid = import.meta.glob('../../../contracts/fixtures/blocks/valid/*.json', { eager: true, import: 'default' }) as Record<string, Json>
const invalid = import.meta.glob('../../../contracts/fixtures/blocks/invalid/*.json', { eager: true, import: 'default' }) as Record<string, Json>
const schemaOnly = import.meta.glob('../../../contracts/fixtures/blocks/schema_only_invalid/*.json', { eager: true, import: 'default' }) as Record<string, Json>

function pick(group: Record<string, Json>, name: string): Json {
  const key = Object.keys(group).find((k) => k.endsWith(`/${name}.json`))
  if (!key) throw new Error(`không có fixture ${name}`)
  return structuredClone(group[key]!)
}

export const validBlock = (name: string): Json => pick(valid, name)
export const invalidBlock = (name: string): Json => pick(invalid, name)
export const schemaOnlyInvalidBlock = (name: string): Json => pick(schemaOnly, name)
export const validBlockEntries = (): [string, Json][] =>
  Object.entries(valid).map(([k, v]) => [k.split('/').pop()!.replace('.json', ''), structuredClone(v)])
export const invalidBlockEntries = (): [string, Json][] =>
  Object.entries(invalid).map(([k, v]) => [k.split('/').pop()!.replace('.json', ''), structuredClone(v)])

// Fixture REST (contracts/fixtures/rest/*.json): thân phản hồi và yêu cầu mẫu, chung với phía Python.
const rest = import.meta.glob('../../../contracts/fixtures/rest/*.json', { eager: true, import: 'default' }) as Record<string, Json>
const restInvalid = import.meta.glob('../../../contracts/fixtures/rest/invalid/*.json', { eager: true, import: 'default' }) as Record<string, Json>

export const restFixture = (name: string): Json => pick(rest, name)
export const restFixtureEntries = (): [string, Json][] => Object.entries(rest).map(([k, v]) => [k.split('/').pop()!.replace('.json', ''), structuredClone(v)])
export const restInvalidEntries = (): [string, Json][] => Object.entries(restInvalid).map(([k, v]) => [k.split('/').pop()!.replace('.json', ''), structuredClone(v)])
