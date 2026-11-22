// Kiểm Zod sinh ra (frontend/src/contracts/blocks.ts) bằng đúng các fixture mà test Python dùng
// (contracts/fixtures/blocks/*). Chạy: node --test tests/unit/ts/   (cần `npm install` ở gốc repo).
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

import { ALL_BLOCK_TYPES, BLOCK_TYPES, Block, BlockEnvelope, blockSchemas } from '../../../frontend/src/contracts/blocks.ts'

const FIXTURES = resolve(dirname(fileURLToPath(import.meta.url)), '../../../contracts/fixtures/blocks')

function fixtures(dir) {
  return readdirSync(resolve(FIXTURES, dir))
    .filter((f) => f.endsWith('.json'))
    .map((f) => ({ file: `${dir}/${f}`, prefix: f.split('.')[0], json: JSON.parse(readFileSync(resolve(FIXTURES, dir, f), 'utf8')) }))
}

test('blockSchemas có đủ tám khối theo thứ tự của block.schema.json; BLOCK_TYPES (registry frontend) là phần đã đăng ký', () => {
  const all = [
    'jar_summary', 'confirm', 'receipt', 'notice',
    'forecast_timeline', 'proactive_card', 'confirm_action', 'receipt_action',
  ]
  assert.deepEqual([...ALL_BLOCK_TYPES], all)
  assert.deepEqual(Object.keys(blockSchemas), all)
  assert.deepEqual([...BLOCK_TYPES], ['jar_summary', 'confirm', 'receipt', 'notice'])
  for (const t of BLOCK_TYPES) assert.ok(t in blockSchemas)
})

test('fixture hợp lệ: qua schema riêng và qua hợp, dữ liệu không bị đổi', () => {
  const list = fixtures('valid')
  assert.ok(list.length >= 14)
  for (const { file, prefix, json } of list) {
    const own = blockSchemas[prefix].safeParse(json)
    assert.ok(own.success, `${file}: ${own.error}`)
    assert.deepEqual(own.data, json, `${file}: Zod làm đổi dữ liệu`)
    assert.ok(Block.safeParse(json).success, `${file}: không qua union`)
    assert.ok(BlockEnvelope.safeParse(json).success, `${file}: không qua phong bì`)
  }
})

test('fixture không hợp lệ: bị từ chối', () => {
  const list = fixtures('invalid')
  assert.ok(list.length >= 25)
  for (const { file, prefix, json } of list) {
    const schema = prefix === 'block' ? Block : blockSchemas[prefix]
    assert.ok(!schema.safeParse(json).success, `${file}: lẽ ra phải bị từ chối`)
  }
})

test('type lạ: union từ chối nhưng phong bì vẫn qua để hiện fallback_text', () => {
  const unknown = fixtures('invalid').find((f) => f.file.endsWith('block.unknown_type.json'))
  assert.ok(!(unknown.json.type in blockSchemas))
  const env = BlockEnvelope.safeParse(unknown.json)
  assert.ok(env.success)
  assert.equal(typeof env.data.fallback_text, 'string')
  const noType = fixtures('invalid').find((f) => f.file.endsWith('block.type_missing.json'))
  assert.ok(!BlockEnvelope.safeParse(noType.json).success)
})

test('phía đọc dễ tính: trường thừa bị bỏ chứ không làm hỏng khối (JSON Schema và Pydantic thì từ chối)', () => {
  const list = fixtures('schema_only_invalid')
  assert.ok(list.length >= 2)
  for (const { file, prefix, json } of list) {
    const r = blockSchemas[prefix].safeParse(json)
    assert.ok(r.success, `${file}: ${r.error}`)
    assert.notDeepEqual(r.data, json, `${file}: trường thừa lẽ ra bị bỏ`)
  }
})
