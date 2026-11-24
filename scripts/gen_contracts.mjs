#!/usr/bin/env node
// Sinh Zod (frontend) từ JSON Schema trong contracts/blocks/.
//
//   node scripts/gen_contracts.mjs           ghi frontend/src/contracts/blocks.ts
//   node scripts/gen_contracts.mjs --check   không ghi; thoát 1 nếu file đã commit lệch schema
//
// Vì sao tự viết thay vì dùng json-schema-to-zod: công cụ đó không theo $ref/$defs liên file (thứ
// hợp đồng này dùng) và đã ngừng phát triển khi Zod 4 ra mắt. Schema hợp đồng cố ý chỉ dùng một
// tập con nhỏ của JSON Schema 2020-12; script này sinh đúng tập con đó và **báo lỗi** khi gặp từ
// khóa lạ (không bỏ qua im lặng). Tập con được liệt kê ở contracts/README.md.
//
// Quy ước đọc/ghi: phía sinh dữ liệu (Pydantic, JSON Schema) chặt (`additionalProperties:false`);
// Zod sinh ra là phía đọc nên dùng `z.object` thường: trường lạ bị bỏ, không làm hỏng khối.
// Không phụ thuộc gói nào; chỉ cần Node 20+.

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, resolve, basename } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const BLOCKS_DIR = resolve(ROOT, 'contracts/blocks')
const OUT_FILE = resolve(ROOT, 'frontend/src/contracts/blocks.ts')

const ANNOTATIONS = new Set(['$schema', '$id', 'title', 'description', '$comment', 'examples', 'format'])
const KNOWN = new Set([
  ...ANNOTATIONS, '$ref', '$defs', 'type', 'const', 'enum', 'properties', 'required',
  'additionalProperties', 'items', 'minItems', 'maxItems', 'minLength', 'maxLength', 'pattern',
  'minimum', 'maximum', 'oneOf',
])

// --- nạp schema ------------------------------------------------------------------------------
const FILES = [
  'envelope', 'jar_summary', 'confirm', 'receipt', 'notice',
  'forecast_timeline', 'proactive_card', 'confirm_action', 'receipt_action',
  'suggestions', 'obligation_impact', 'options', 'affordability_card', 'explain', 'clarify',
  // phase 5 (F6): luồng frontend thêm vào REGISTERED_BY_FRONTEND khi đăng ký view
  'coverage_change', 'ingest_review',
  // phase 4 (F4, F5, F2): luồng frontend phase 4 thêm vào REGISTERED_BY_FRONTEND khi đăng ký view
  'resilience_score', 'stress_result', 'roadmap', 'roadmap_diff', 'review_list',
  // phase 5 (F7, RAG): luồng frontend phase 5 thêm vào REGISTERED_BY_FRONTEND khi đăng ký view
  'behavior_insight', 'citation',
]
const UNION_FILE = 'block'

function load(name) {
  const path = resolve(BLOCKS_DIR, `${name}.schema.json`)
  return { name, path, schema: JSON.parse(readFileSync(path, 'utf8')) }
}

const files = Object.fromEntries([...FILES, UNION_FILE].map((n) => [n, load(n)]))

// Mỗi schema có tên: root theo `title`, $defs theo khóa. Tên phải duy nhất toàn bộ.
const named = new Map() // id (file#pointer) -> { ident, schema, file }
const idents = new Set()
function register(id, ident, schema, file) {
  if (idents.has(ident)) throw new Error(`Trùng tên định danh '${ident}' (${id})`)
  idents.add(ident)
  named.set(id, { ident, schema, file })
}
for (const f of FILES) {
  const { schema } = files[f]
  register(`${f}#`, schema.title, schema, f)
  for (const [k, v] of Object.entries(schema.$defs ?? {})) register(`${f}#/$defs/${k}`, k, v, f)
}
register(`${UNION_FILE}#`, files[UNION_FILE].schema.title, files[UNION_FILE].schema, UNION_FILE)

function resolveRef(ref, fromFile) {
  const [fileRef, pointer = ''] = ref.split('#')
  const file = fileRef ? basename(fileRef).replace('.schema.json', '') : fromFile
  const id = `${file}#${pointer}`
  const hit = named.get(id)
  if (!hit) throw new Error(`$ref không tìm thấy: ${ref} (từ ${fromFile})`)
  return hit
}

// --- sinh biểu thức Zod ----------------------------------------------------------------------
const q = (s) => JSON.stringify(s)

function checkKeywords(schema, where) {
  for (const k of Object.keys(schema)) {
    if (!KNOWN.has(k)) throw new Error(`Từ khóa JSON Schema chưa hỗ trợ '${k}' tại ${where}`)
  }
}

function numberBounds(schema, expr) {
  if (schema.minimum !== undefined) expr += `.min(${schema.minimum})`
  if (schema.maximum !== undefined) expr += `.max(${schema.maximum})`
  return expr
}

const deps = [] // thứ tự phát sinh khi duyệt (để xuất theo thứ tự phụ thuộc)

function expr(schema, file, where, indent) {
  checkKeywords(schema, where)
  if (schema.$ref !== undefined) {
    const hit = resolveRef(schema.$ref, file)
    emit(hit)
    return hit.ident
  }
  if (schema.const !== undefined) return `z.literal(${q(schema.const)})`
  if (schema.enum !== undefined) return `z.enum([${schema.enum.map(q).join(', ')}])`
  if (schema.oneOf !== undefined) {
    const members = schema.oneOf.map((s, i) => {
      if (s.$ref === undefined) throw new Error(`oneOf chỉ nhận $ref (${where}[${i}])`)
      const hit = resolveRef(s.$ref, file)
      emit(hit)
      return hit.ident
    })
    return `z.discriminatedUnion('type', [${members.join(', ')}])`
  }
  switch (schema.type) {
    case 'string': {
      let e = 'z.string()'
      if (schema.minLength !== undefined) e += `.min(${schema.minLength})`
      if (schema.maxLength !== undefined) e += `.max(${schema.maxLength})`
      if (schema.pattern !== undefined) e += `.regex(new RegExp(${q(schema.pattern)}))`
      return e
    }
    case 'integer':
      return numberBounds(schema, 'z.int()')
    case 'number':
      return numberBounds(schema, 'z.number()')
    case 'boolean':
      return 'z.boolean()'
    case 'array': {
      if (schema.items === undefined) throw new Error(`array thiếu items (${where})`)
      let e = `z.array(${expr(schema.items, file, `${where}.items`, indent)})`
      if (schema.minItems !== undefined) e += `.min(${schema.minItems})`
      if (schema.maxItems !== undefined) e += `.max(${schema.maxItems})`
      return e
    }
    case 'object': {
      if (schema.properties === undefined) return 'z.record(z.string(), z.unknown())'
      const required = new Set(schema.required ?? [])
      for (const r of required) {
        if (!(r in schema.properties)) throw new Error(`required '${r}' không có trong properties (${where})`)
      }
      const pad = ' '.repeat(indent + 2)
      const lines = Object.entries(schema.properties).map(([k, v]) => {
        const inner = expr(v, file, `${where}.${k}`, indent + 2)
        const key = /^[A-Za-z_$][\w$]*$/.test(k) ? k : q(k)
        return `${pad}${key}: ${inner}${required.has(k) ? '' : '.optional()'},`
      })
      return `z.object({\n${lines.join('\n')}\n${' '.repeat(indent)}})`
    }
    default:
      throw new Error(`type chưa hỗ trợ: ${JSON.stringify(schema.type)} tại ${where}`)
  }
}

const emitted = new Set()
const out = []
function emit(hit) {
  if (emitted.has(hit.ident)) return
  emitted.add(hit.ident) // đánh dấu trước để tránh vòng
  const body = expr(hit.schema, hit.file, hit.ident, 0)
  const doc = hit.schema.description ? `/** ${String(hit.schema.description).replaceAll('*/', '* /')} */\n` : ''
  out.push(`${doc}export const ${hit.ident} = ${body}\nexport type ${hit.ident} = z.infer<typeof ${hit.ident}>\n`)
  deps.push(hit.ident)
}

// Xuất mọi $defs của envelope trước (kiểu cơ bản), rồi từng khối, rồi hợp.
for (const f of FILES) {
  for (const k of Object.keys(files[f].schema.$defs ?? {})) emit(named.get(`${f}#/$defs/${k}`))
  emit(named.get(`${f}#`))
}
emit(named.get(`${UNION_FILE}#`))

// Registry type -> schema, theo thứ tự oneOf của block.schema.json.
const blockRefs = files[UNION_FILE].schema.oneOf.map((s) => resolveRef(s.$ref, UNION_FILE))
const registry = blockRefs.map((hit) => {
  const t = hit.schema.properties?.type?.const
  if (typeof t !== 'string') throw new Error(`${hit.ident} thiếu type const`)
  return [t, hit.ident]
})

const header = `// GENERATED FILE. DO NOT EDIT.
// Nguồn: contracts/blocks/*.schema.json (JSON Schema draft 2020-12).
// Sinh bởi: node scripts/gen_contracts.mjs   (kiểm lệch: node scripts/gen_contracts.mjs --check)
// Sửa hợp đồng ở contracts/, rồi sinh lại; không sửa tay file này.
//
// Phía đọc: z.object thường (trường lạ bị bỏ), khác phía sinh dữ liệu (additionalProperties:false).
// Frontend parse TỪNG khối bằng \`blockSchemas[type]\`; khối lạ hoặc sai schema hiện fallback_text.
import { z } from 'zod'
`

// Khối mà registry của frontend (frontend/src/blocks/registry.tsx, `Record<BlockType, Entry>`) hiện vẽ được.
// `BlockType` và `BLOCK_TYPES` chỉ gồm các khối này để registry biên dịch được và hiện fallback_text cho khối
// chưa đăng ký. Luồng frontend (phase 2) thêm bốn khối mới vào danh sách ĐỒNG THỜI với việc đăng ký view trong
// registry.tsx. `blockSchemas`, `ALL_BLOCK_TYPES` và `Block` luôn gồm MỌI khối trong block.schema.json.
// Phase 3 thêm sáu khối (affordability_card, obligation_impact, options, explain, clarify, suggestions) vào hợp đồng nhưng
// CHƯA vào danh sách dưới đây: luồng frontend của phase 3 thêm chúng cùng lúc với việc đăng ký view trong registry.tsx.
// Phase 5 (F6) đã đăng ký view cho ingest_review và coverage_change (sau 6 khối của phase 3).
// Phase 4 thêm năm khối (resilience_score, stress_result, roadmap, roadmap_diff, review_list) vào hợp đồng nhưng CHƯA vào danh sách
// dưới đây: luồng frontend phase 4 thêm chúng cùng lúc với việc đăng ký view trong registry.tsx.
const REGISTERED_BY_FRONTEND = ['jar_summary', 'confirm', 'receipt', 'notice', 'forecast_timeline', 'proactive_card', 'confirm_action', 'receipt_action', 'affordability_card', 'obligation_impact', 'options', 'explain', 'clarify', 'suggestions', 'coverage_change', 'ingest_review', 'resilience_score', 'stress_result', 'roadmap', 'roadmap_diff', 'review_list']
for (const t of REGISTERED_BY_FRONTEND) {
  if (!registry.some(([name]) => name === t)) throw new Error(`REGISTERED_BY_FRONTEND có type lạ: ${t}`)
}
const registered = registry.filter(([t]) => REGISTERED_BY_FRONTEND.includes(t))

const footer = `
/** type -> schema của MỌI khối, thứ tự như contracts/blocks/block.schema.json. */
export const blockSchemas = {
${registry.map(([t, id]) => `  ${t}: ${id},`).join('\n')}
} as const

export type AnyBlockType = keyof typeof blockSchemas
export const ALL_BLOCK_TYPES = [${registry.map(([t]) => q(t)).join(', ')}] as const

/** Khối mà registry frontend đã đăng ký (xem scripts/gen_contracts.mjs, REGISTERED_BY_FRONTEND). */
export const BLOCK_TYPES = [${registered.map(([t]) => q(t)).join(', ')}] as const
export type BlockType = (typeof BLOCK_TYPES)[number]
`

const text = `${header}\n${out.join('\n')}${footer}`

if (process.argv.includes('--check')) {
  const current = existsSync(OUT_FILE) ? readFileSync(OUT_FILE, 'utf8') : ''
  if (current.replaceAll('\r\n', '\n') !== text) {
    console.error(`LỆCH: ${OUT_FILE} không khớp contracts/blocks. Chạy: node scripts/gen_contracts.mjs`)
    process.exit(1)
  }
  console.log('OK: Zod sinh ra khớp contracts/blocks.')
} else {
  mkdirSync(dirname(OUT_FILE), { recursive: true })
  writeFileSync(OUT_FILE, text)
  console.log(`Đã ghi ${OUT_FILE} (${deps.length} schema).`)
}
