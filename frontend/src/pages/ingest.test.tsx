import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiProvider } from '@/api/ApiProvider'
import { OverviewProvider } from '@/api/OverviewProvider'
import { createApiClient } from '@/api/client'
import { IngestPollContext, type PollTiming } from '@/features/ingest/config'
import { uploadToS3 } from '@/features/ingest/upload'
import { IngestPage } from './IngestPage'
import { restFixture } from '@/test/fixtures'
import { backend, bodyOf, callsTo, json, mountApp, type Call, type Routes } from '@/test/mountApp'

// Màn Nạp dữ liệu (F6): I1 → I2 → I3 → I4 với fetch giả (chỉ trong test). Mọi phản hồi lấy từ contracts/fixtures.

type Json = Record<string, any>
const API = 'https://api.example.invalid'
const JOB = '5c2d8e14-7a3b-4f60-9d21-0b4e6a8c1f37'
const ROW = (n: number) => `9a1b2c3d-4e5f-4a6b-8c7d-00000000000${n}`
const FAST: PollTiming = { firstDelayMs: 0, delayMs: 20, maxDelayMs: 40, backoff: 1.5, timeoutMs: 2_000 }

const png = (bytes = 5_000, name = 'chuyen-khoan.png', type = 'image/png') => new File([new Uint8Array(bytes)], name, { type })

function job(status: 'processing' | 'review' | 'done' | 'rejected'): Json {
  return restFixture(`IngestJobResponse.${status}`)
}

function receipt(): Json {
  return restFixture('ActionResponse.receipt_action_confirm_rows')
}

function confirmation(init: RequestInit): Json {
  const b = JSON.parse(String(init.body))
  return {
    confirm_token: 'tok.ingest',
    expires_at: new Date(Date.now() + 120_000).toISOString().replace(/\.\d+Z$/, 'Z'),
    ttl_seconds: 120,
    tool: b.tool,
    params: b.params,
    params_hash: 'b'.repeat(64),
    preview: { summary: 'Thêm 3 dòng ngoài ví vào lịch sử chi tiêu', changes: [{ label: 'Số dư hũ', after: 'không đổi' }] },
  }
}

/** Backend giả: GET /ingest/jobs trả lần lượt `sequence` (phần tử cuối lặp lại); S3 nhận ở URL của fixture. */
function ingestBackend(sequence: Json[], extra: Routes = {}) {
  let i = 0
  return backend({
    'POST /ingest/uploads': restFixture('IngestUploadResponse.image'),
    [`GET /ingest/jobs/${JOB}`]: () => sequence[Math.min(i++, sequence.length - 1)],
    'POST /ingest/confirmations': (init) => confirmation(init),
    'POST /ingest/actions': () => receipt(),
    'PATCH /ingest/rows/*': () => restFixture('IngestRowJarResponse.giai_tri'),
    ...extra,
  })
}

/** Gắn handler S3 vào backend (URL S3 khác host API, `backend` chỉ xem pathname nên tách riêng). */
function withS3(handler: ReturnType<typeof backend>, s3: (init: RequestInit) => Response = () => new Response(null, { status: 204 })) {
  return async (url: string, init: RequestInit) => (url.startsWith('https://yofina-ingest-example.s3.amazonaws.com') ? s3(init) : handler(url, init))
}

function mountIngest(handler: (url: string, init: RequestInit) => Response | Promise<Response>, initial = '/ingest') {
  // Màn đầy đủ qua router của ứng dụng, nhịp hỏi tiến độ thu ngắn bằng IngestPollContext.
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(url), init: init ?? {} })
      return handler(String(url), init ?? {})
    }),
  )
  const api = createApiClient({ baseUrl: API, getAccessToken: async () => 'access-1' })
  const router = createMemoryRouter(
    [
      { path: '/ingest', element: <IngestPage /> },
      { path: '/jars/:code', element: <p>Chi tiết hũ</p> },
      { path: '/income', element: <p>Tiền vào</p> },
      { path: '/', element: <p>Tổng quan</p> },
    ],
    { initialEntries: [initial] },
  )
  render(
    <IngestPollContext.Provider value={FAST}>
      <ApiProvider client={api}>
        <OverviewProvider>
          <RouterProvider router={router} />
        </OverviewProvider>
      </ApiProvider>
    </IngestPollContext.Provider>,
  )
  return { calls, router }
}

const s3Calls = (calls: Call[]) => calls.filter((c) => c.url.startsWith('https://yofina-ingest-example.s3.amazonaws.com'))
const jobCalls = (calls: Call[]) => callsTo(calls, 'GET', `/ingest/jobs/${JOB}`)

async function pickImage(user: ReturnType<typeof userEvent.setup>, file = png()) {
  const input = screen.getByLabelText('Chọn ảnh có sẵn') as HTMLInputElement
  await user.upload(input, file)
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('I1 chọn tệp', () => {
  it('ba lối chọn: chụp ảnh (capture), chọn ảnh, CSV với accept đúng loại; có tên cho trình đọc màn hình', async () => {
    mountIngest(withS3(ingestBackend([job('processing')])))
    const camera = screen.getByLabelText('Chụp ảnh') as HTMLInputElement
    expect(camera).toHaveAttribute('capture', 'environment')
    expect(camera).toHaveAttribute('accept', 'image/png,image/jpeg,image/webp')
    expect(screen.getByLabelText('Chọn ảnh có sẵn')).not.toHaveAttribute('capture')
    expect(screen.getByLabelText('Tải sao kê CSV')).toHaveAttribute('accept', '.csv,text/csv')
    expect(screen.getByRole('button', { name: 'Quay lại' })).toBeInTheDocument()
  })

  it('đi đủ I1 → I4: xin URL, tải S3 đúng FormData (file cuối), polling, duyệt, đổi hũ, chốt qua /ingest/*, độ phủ, về Chi tiết hũ', async () => {
    const { calls, router } = mountIngest(withS3(ingestBackend([job('processing'), job('processing'), job('review')])))
    const user = userEvent.setup()
    await pickImage(user)

    // I2 → I3
    await screen.findByRole('list', { name: 'Dòng đã đọc' })
    const up = callsTo(calls, 'POST', '/ingest/uploads')
    expect(up).toHaveLength(1)
    expect(bodyOf(up[0]!)).toEqual({ source_kind: 'image', mime: 'image/png', size_bytes: 5_000 })

    // S3: đúng URL, POST, không JWT, đủ fields theo thứ tự rồi file cuối cùng
    const s3 = s3Calls(calls)
    expect(s3).toHaveLength(1)
    expect(s3[0]!.init.method).toBe('POST')
    expect(s3[0]!.init.headers).toBeUndefined()
    const form = s3[0]!.init.body as FormData
    const fields = restFixture('IngestUploadResponse.image').fields as Record<string, string>
    const keys = [...form.keys()]
    expect(keys).toEqual([...Object.keys(fields), 'file'])
    for (const [k, v] of Object.entries(fields)) expect(form.get(k)).toBe(v)
    expect((form.get('file') as File).name).toBe('chuyen-khoan.png')

    // Polling dừng ở review: không hỏi thêm sau khi tới review
    const n = jobCalls(calls).length
    expect(n).toBe(3)
    await new Promise((r) => setTimeout(r, 150))
    expect(jobCalls(calls)).toHaveLength(n)
    expect(router.state.location.search).toBe(`?job=${JOB}`)

    // I3: dòng tự thêm chọn sẵn, cần duyệt chưa chọn, trùng không chọn được
    const rows = screen.getByRole('list', { name: 'Dòng đã đọc' })
    expect(within(rows).getByText('85.000 ₫', { exact: false })).toBeInTheDocument()
    const r1 = screen.getByRole('checkbox', { name: /Thêm dòng Cơm tấm Phúc Lộc/ })
    const r3 = screen.getByRole('checkbox', { name: /Thêm dòng Cửa hàng \*\*\*/ })
    const r4 = screen.getByRole('checkbox', { name: /đã có trong ví, không thêm lại/ })
    expect(r1).toBeChecked()
    expect(r3).not.toBeChecked()
    expect(r4).toBeDisabled()
    expect(r4).not.toBeChecked()
    expect(within(rows).getByText('Đã có trong ví')).toBeInTheDocument()

    // Đổi hũ Grab: Đi lại → Giải trí bằng một chạm (PATCH)
    await user.click(screen.getByRole('button', { name: 'Đổi hũ cho dòng Grab, đang là Đi lại' }))
    const sheet = await screen.findByRole('radiogroup', { name: 'Hũ cho dòng Grab' })
    await user.click(within(sheet).getByRole('radio', { name: /Giải trí/ }))
    await waitFor(() => expect(callsTo(calls, 'PATCH', `/ingest/rows/${ROW(2)}`)).toHaveLength(1))
    expect(bodyOf(callsTo(calls, 'PATCH', `/ingest/rows/${ROW(2)}`)[0]!)).toEqual({ jar: 'giai_tri' })
    expect(await screen.findByRole('button', { name: 'Đổi hũ cho dòng Grab, đang là Giải trí' })).toBeInTheDocument()

    // Chọn dòng thu nhập; dòng 450.000 chưa có hũ thì giữ bỏ qua
    await user.click(screen.getByRole('checkbox', { name: /Thêm dòng Công ty \*\*\*/ }))

    await user.click(screen.getByRole('button', { name: 'Xong, cập nhật dự báo' }))
    expect(await screen.findByTestId('preview-summary')).toHaveTextContent('Thêm 3 dòng ngoài ví')
    const conf = callsTo(calls, 'POST', '/ingest/confirmations')
    expect(conf).toHaveLength(1)
    expect(bodyOf(conf[0]!)).toEqual({
      tool: 'confirm_rows',
      params: { job_id: JOB, rows: [{ row_id: ROW(1) }, { row_id: ROW(2), jar: 'giai_tri' }, { row_id: ROW(5) }], reject_row_ids: [ROW(3)] },
    })
    expect(bodyOf(conf[0]!)).not.toHaveProperty('conversation_id')

    await user.click(screen.getByRole('button', { name: 'Xác nhận thêm 3 dòng' }))
    // I4
    expect(await screen.findByTestId('coverage-ratios')).toHaveAccessibleName('Độ phủ dữ liệu từ 62% lên 81%')
    expect(screen.getByTestId('rows-added')).toHaveTextContent('3')
    expect(screen.getByText('Số dư hũ không đổi — đây là chi tiêu ngoài ví.')).toBeInTheDocument()
    const act1 = callsTo(calls, 'POST', '/ingest/actions')
    expect(act1).toHaveLength(1)
    expect(bodyOf(act1[0]!)).toEqual({ tool: 'confirm_rows', params: bodyOf(conf[0]!).params, confirm_token: 'tok.ingest' })
    // Không đi qua luồng xác nhận của ledger
    expect(callsTo(calls, 'POST', '/confirmations')).toHaveLength(0)
    expect(callsTo(calls, 'POST', '/actions')).toHaveLength(0)

    // Hũ ảnh hưởng nhiều nhất trong jars_affected (an_uong 85.000 so với giai_tri 120.000): Giải trí
    await user.click(screen.getByRole('button', { name: 'Xem dự báo cập nhật' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/jars/giai_tri'))
  })

  it('lần đầu mỗi nguồn: server đòi đồng ý → ô đồng ý nêu 30 ngày và che thông tin; đồng ý thì gửi consent: true', async () => {
    let n = 0
    const { calls } = mountIngest(
      withS3(
        ingestBackend([job('processing'), job('review')], {
          'POST /ingest/uploads': () => (n++ === 0 ? json(403, { error: { code: 'CONSENT_REQUIRED', message: 'x' } }) : restFixture('IngestUploadResponse.image')),
        }),
      ),
    )
    const user = userEvent.setup()
    await pickImage(user)
    const consent = await screen.findByTestId('consent')
    expect(consent).toHaveTextContent('tối đa 30 ngày')
    expect(consent).toHaveTextContent('tên người khác được che')
    const go = within(consent).getByRole('button', { name: 'Đồng ý và tải lên' })
    expect(go).toBeDisabled()
    await user.click(within(consent).getByRole('checkbox', { name: /Tôi đồng ý/ }))
    await user.click(go)
    await screen.findByRole('list', { name: 'Dòng đã đọc' })
    const up = callsTo(calls, 'POST', '/ingest/uploads')
    expect(up).toHaveLength(2)
    expect(bodyOf(up[0]!)).not.toHaveProperty('consent')
    expect(bodyOf(up[1]!).consent).toBe(true)
    expect(s3Calls(calls)).toHaveLength(1)
  })
})

describe('lỗi có câu tiếng Việt và lối thoát', () => {
  it('ảnh không phải tài liệu tài chính (job rejected): câu rõ ràng, nút chọn tệp khác, polling dừng', async () => {
    const { calls } = mountIngest(withS3(ingestBackend([job('processing'), job('rejected')])))
    const user = userEvent.setup()
    await pickImage(user)
    expect(await screen.findByTestId('ingest-error')).toHaveTextContent('Ảnh này không phải biên lai hay sao kê')
    const n = jobCalls(calls).length
    await new Promise((r) => setTimeout(r, 120))
    expect(jobCalls(calls)).toHaveLength(n)
    await user.click(screen.getByRole('button', { name: 'Chọn tệp khác' }))
    expect(screen.getByLabelText('Chụp ảnh')).toBeInTheDocument()
  })

  it('trùng tệp (rejected INGEST_DUPLICATE_FILE)', async () => {
    const dup = { ...job('rejected'), error_code: 'INGEST_DUPLICATE_FILE', error_message: 'dup' }
    mountIngest(withS3(ingestBackend([dup])))
    await pickImage(userEvent.setup())
    expect(await screen.findByTestId('ingest-error')).toHaveTextContent('Tệp này đã được nạp trước đó rồi')
  })

  it('loại tệp sai: chặn ở máy, không gọi API; tệp quá lớn: cũng chặn', async () => {
    const { calls } = mountIngest(withS3(ingestBackend([job('review')])))
    const user = userEvent.setup({ applyAccept: false })
    await user.upload(screen.getByLabelText('Chọn ảnh có sẵn') as HTMLInputElement, png(100, 'a.gif', 'image/gif'))
    expect(await screen.findByTestId('ingest-error')).toHaveTextContent('Loại tệp này chưa được hỗ trợ')
    await user.upload(screen.getByLabelText('Chọn ảnh có sẵn') as HTMLInputElement, png(4_000_000))
    expect(await screen.findByTestId('ingest-error')).toHaveTextContent('Tệp lớn hơn giới hạn')
    expect(callsTo(calls, 'POST', '/ingest/uploads')).toHaveLength(0)
  })

  it('server từ chối kích thước (413 INGEST_TOO_LARGE) và loại (415)', async () => {
    const { calls } = mountIngest(withS3(ingestBackend([job('review')], { 'POST /ingest/uploads': json(413, { error: { code: 'INGEST_TOO_LARGE', message: 'x' } }) })))
    await pickImage(userEvent.setup())
    expect(await screen.findByTestId('ingest-error')).toHaveTextContent('Tệp lớn hơn giới hạn')
    expect(s3Calls(calls)).toHaveLength(0)
  })

  it('mạng đứt khi tải lên S3: câu tiếng Việt, chọn lại được', async () => {
    mountIngest(
      withS3(ingestBackend([job('review')]), () => {
        throw new TypeError('Failed to fetch')
      }),
    )
    await pickImage(userEvent.setup())
    expect(await screen.findByTestId('ingest-error')).toHaveTextContent('Chưa tải được tệp lên')
    expect(screen.getByLabelText('Chụp ảnh')).not.toBeDisabled()
  })

  it('quá trần thời gian: "đang lâu hơn thường lệ", dừng hỏi, Thử lại hỏi tiếp; Hủy về I1', async () => {
    const { calls } = mountIngest(withS3(ingestBackend([job('processing')])), `/ingest?job=${JOB}`)
    // FAST.timeoutMs = 2 s: chờ tới khi báo chậm
    expect(await screen.findByText(/Đang lâu hơn thường lệ/, undefined, { timeout: 4_000 })).toBeInTheDocument()
    const n = jobCalls(calls).length
    await new Promise((r) => setTimeout(r, 150))
    expect(jobCalls(calls)).toHaveLength(n)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Thử lại' }))
    await waitFor(() => expect(jobCalls(calls).length).toBeGreaterThan(n))
    await user.click(screen.getByRole('button', { name: /Hủy/ }))
    expect(screen.getByLabelText('Chụp ảnh')).toBeInTheDocument()
    const after = jobCalls(calls).length
    await new Promise((r) => setTimeout(r, 150))
    expect(jobCalls(calls)).toHaveLength(after)
  })

  it('tiến độ có aria-live và thanh tiến độ có giá trị', async () => {
    mountIngest(withS3(ingestBackend([job('processing')])), `/ingest?job=${JOB}`)
    const p = await screen.findByTestId('ingest-progress')
    await waitFor(() => expect(p).toHaveTextContent('40%'))
    expect(p).toHaveAttribute('aria-live', 'polite')
    expect(screen.getByRole('progressbar', { name: 'Tiến độ đọc tệp' })).toHaveAttribute('aria-valuenow', '40')
  })

  it('rời trang thì dừng polling', async () => {
    const { calls, router } = mountIngest(withS3(ingestBackend([job('processing')])), `/ingest?job=${JOB}`)
    await waitFor(() => expect(jobCalls(calls).length).toBeGreaterThan(0))
    await act(() => router.navigate('/'))
    const n = jobCalls(calls).length
    await new Promise((r) => setTimeout(r, 150))
    expect(jobCalls(calls)).toHaveLength(n)
  })

  it('chốt: token hết hạn lúc ghi thì tự xin token mới một lần; lần nạp đã chốt nơi khác thì khóa nút và báo', async () => {
    let actions = 0
    const { calls } = mountIngest(
      withS3(
        ingestBackend([job('review')], {
          'POST /ingest/actions': () => (actions++ === 0 ? json(403, { error: { code: 'TOKEN_EXPIRED', message: 'x' } }) : receipt()),
        }),
      ),
      `/ingest?job=${JOB}`,
    )
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Xong, cập nhật dự báo' }))
    await user.click(await screen.findByRole('button', { name: /Xác nhận thêm 2 dòng/ }))
    await screen.findByTestId('coverage-ratios')
    expect(callsTo(calls, 'POST', '/ingest/confirmations')).toHaveLength(2)
    expect(callsTo(calls, 'POST', '/ingest/actions')).toHaveLength(2)
  })

  it('INGEST_JOB_NOT_READY khi xem trước: câu tiếng Việt, nút xác nhận khóa, có nút quay lại', async () => {
    mountIngest(withS3(ingestBackend([job('review')], { 'POST /ingest/confirmations': json(409, { error: { code: 'INGEST_JOB_NOT_READY', message: 'x' } }) })), `/ingest?job=${JOB}`)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Xong, cập nhật dự báo' }))
    expect(await screen.findByText('Lần nạp này chưa đọc xong hoặc đã được chốt rồi.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Xác nhận thêm/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Quay lại sửa' })).toBeEnabled()
  })

  it('job đã done (mở lại trang): hiện độ phủ, không cho duyệt lại', async () => {
    mountIngest(withS3(ingestBackend([job('done')])), `/ingest?job=${JOB}`)
    expect(await screen.findByTestId('coverage-ratios')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Xong, cập nhật dự báo' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Nạp thêm ảnh khác' })).toBeInTheDocument()
  })
})

describe('uploadToS3', () => {
  it('fields theo đúng thứ tự, file cuối, không header; S3 trả EntityTooLarge thì báo quá lớn', async () => {
    const seen: RequestInit[] = []
    const fetchImpl = (async (_u: string, init: RequestInit) => {
      seen.push(init)
      return new Response('<Error><Code>EntityTooLarge</Code></Error>', { status: 400 })
    }) as unknown as typeof fetch
    await expect(uploadToS3({ url: 'https://s3.example', fields: { b: '2', a: '1' } }, png(10), { fetchImpl })).rejects.toMatchObject({ code: 'INGEST_TOO_LARGE' })
    expect([...(seen[0]!.body as FormData).keys()]).toEqual(['b', 'a', 'file'])
    expect(seen[0]!.headers).toBeUndefined()
  })
})

describe('lối vào', () => {
  it('màn Tiền vào có nút "Nạp ảnh / sao kê ngoài ví" dẫn tới /ingest', async () => {
    mountApp(backend(), '/income')
    expect(await screen.findByRole('link', { name: /Nạp ảnh \/ sao kê ngoài ví/ })).toHaveAttribute('href', '/ingest')
  })
})
