// Kiểm bản build (dist/): không có mock, fixture, dữ liệu persona, mật khẩu hay từ cấm trên giao diện; in kích thước gzip.
//   npm run build && npm run check:bundle
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { gzipSync } from 'node:zlib'
import path from 'node:path'

const DIST = path.resolve(import.meta.dirname, '..', 'dist')

function walk(dir) {
  return readdirSync(dir).flatMap((n) => {
    const p = path.join(dir, n)
    return statSync(p).isDirectory() ? walk(p) : [p]
  })
}

const files = walk(DIST)
const textFiles = files.filter((f) => /\.(js|css|html|map|json|svg|txt)$/.test(f))

// Mỗi mục: [nhãn, regex]. Khớp là lỗi.
const FORBIDDEN = [
  // mock và fixture
  ['mã dev-mocks', /dev-mocks|yofina-dev-mock|MockAuthClient|mock-auth/],
  ['đường dẫn máy chủ giả', /\/mock-api|\/mock-agent/],
  ['id khối fixture', /8f3a21c94b7e4d0aa1c25e6f7b8c9d01|3b9f6c1e-7a52-4d8e-9c4b-0e1f2a3b4c5d/],
  ['tên miền fixture/test', /example\.invalid|contracts\.yofina\.invalid/],
  // số liệu persona (số dư hũ theo bảng Figma) không được nằm trong bundle
  ['số dư persona (dạng số)', /\b(7730000|8260000|380000|640000|450000|760000|1800000|2700000)\b/],
  ['số dư persona (dạng chuỗi)', /7\.730\.000|8\.260\.000|380\.000|640\.000|1\.800\.000|2\.700\.000/],
  // bí mật
  ['mật khẩu / secret demo', /yofina-demo-accounts|minh\.demo|giamkhao\d/],
  ['khóa AWS', /AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|aws_secret_access_key/i],
  ['account id trong ARN', /arn:aws:[a-z-]+:[a-z0-9-]*:\d{12}:/],
  // từ không được hiện trên giao diện
  ['"MoMo"', /MoMo/],
  ['"Ví Trả Sau"', /Ví Trả Sau/],
  ['"FinHealth"', /FinHealth/i],
]

let failed = false
for (const [label, re] of FORBIDDEN) {
  const hits = textFiles.filter((f) => re.test(readFileSync(f, 'utf8')))
  if (hits.length) {
    failed = true
    console.error(`LỖI: bundle chứa ${label}: ${hits.map((h) => path.relative(DIST, h)).join(', ')}`)
  }
}

// Kích thước
let totalGz = 0
const rows = []
for (const f of files.filter((f) => /\.(js|css|html)$/.test(f))) {
  const buf = readFileSync(f)
  const gz = gzipSync(buf).length
  totalGz += gz
  rows.push([path.relative(DIST, f), buf.length, gz])
}
for (const f of files.filter((f) => f.endsWith('.woff2'))) rows.push([path.relative(DIST, f), statSync(f).size, null])
console.log('Tệp'.padEnd(60), 'Byte'.padStart(10), 'Gzip'.padStart(10))
for (const [n, raw, gz] of rows) console.log(n.padEnd(60), String(raw).padStart(10), gz === null ? ''.padStart(10) : String(gz).padStart(10))
console.log(`Tổng gzip (js + css + html): ${(totalGz / 1024).toFixed(1)} KB`)

if (failed) process.exit(1)
console.log('Bundle sạch: không có mock, fixture, số liệu persona, bí mật hay từ cấm.')
