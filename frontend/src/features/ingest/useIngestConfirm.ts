import { useCallback, useRef, useState } from 'react'
import { useApi, useRefreshAfterWrite } from '@/api/ApiProvider'
import { ApiError, type ErrorCode } from '@/api/errors'
import type { ConfirmRowsParams } from '@/api/ingestSchemas'
import type { ActionResponse, ConfirmPreview, ConfirmationResponse } from '@/api/schemas'

export type IngestConfirmPhase = 'idle' | 'previewing' | 'ready' | 'working' | 'done' | 'blocked'

/** Lỗi mà bấm lại cũng vô ích: lần nạp đã chốt ở nơi khác, dòng không còn mở, token đã dùng, tham số lệch. */
const BLOCKING: ReadonlySet<string> = new Set<ErrorCode>([
  'TOKEN_REUSED',
  'ALREADY_APPLIED',
  'PARAMS_MISMATCH',
  'PARAMS_INVALID',
  'INGEST_JOB_NOT_READY',
  'INGEST_JOB_NOT_FOUND',
  'JAR_NOT_FOUND',
  'DUPLICATE_TRANSACTION',
])

/** Lỗi khiến dữ liệu có thể đã đổi ở server (đã chốt trước đó): làm mới để người dùng thấy sự thật. */
const STALE: ReadonlySet<string> = new Set<ErrorCode>(['TOKEN_REUSED', 'ALREADY_APPLIED', 'INGEST_JOB_NOT_READY', 'DUPLICATE_TRANSACTION'])

/** Còn ít nhất chừng này thì dùng lại token của bản xem trước, đỡ một lời gọi. */
const TOKEN_MARGIN_MS = 15_000

const asApiError = (e: unknown) => (e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0))

/**
 * Luồng chốt một lần nạp (`confirm_rows`), cùng hành vi với `useWriteFlow` của các màn ghi khác (ADR-0002) nhưng qua cặp
 * endpoint riêng của Lambda ingest: `POST /ingest/confirmations` (token + `preview` do server tính, không ghi gì) rồi
 * `POST /ingest/actions` kèm `confirm_token` và đúng `params` đã được server chuẩn hóa. KHÔNG gọi `/confirmations`,
 * `/actions` của ledger và không gửi `conversation_id`/`confirm_block_id` (màn hình không có khối confirm).
 *
 * - `preview(params)`: xin xem trước; lỗi nghiệp vụ hiện ngay, chưa có gì được ghi.
 * - `confirm()`: dùng lại token của bản xem trước nếu còn hạn, không thì xin token mới; token hết hạn hoặc không hợp lệ
 *   lúc ghi thì tự xin token mới và thử lại MỘT lần (người dùng không phải bấm lại).
 * - Ghi xong: làm mới mọi dữ liệu đang hiện (Tổng quan, Chi tiết hũ, dự báo) với mốc `as_of` của biên nhận.
 */
export function useIngestConfirm() {
  const api = useApi()
  const refresh = useRefreshAfterWrite()
  const [phase, setPhase] = useState<IngestConfirmPhase>('idle')
  const [error, setError] = useState<ApiError | null>(null)
  const [previewData, setPreviewData] = useState<ConfirmPreview | null>(null)
  const [receipt, setReceipt] = useState<ActionResponse | null>(null)
  const issued = useRef<ConfirmationResponse | null>(null)
  const params = useRef<ConfirmRowsParams | null>(null)
  const busy = useRef(false)
  const seq = useRef(0)

  const fail = useCallback(
    (err: ApiError) => {
      setError(err)
      setPhase(BLOCKING.has(err.code) ? 'blocked' : params.current ? 'ready' : 'idle')
      if (STALE.has(err.code)) refresh()
    },
    [refresh],
  )

  const preview = useCallback(
    async (p: ConfirmRowsParams) => {
      const mine = ++seq.current
      params.current = p
      issued.current = null
      setPreviewData(null)
      setError(null)
      setPhase('previewing')
      try {
        const res = await api.createIngestConfirmation({ tool: 'confirm_rows', params: p })
        if (mine !== seq.current) return
        issued.current = res
        setPreviewData(res.preview ?? null)
        setPhase('ready')
      } catch (e) {
        if (mine !== seq.current) return
        const err = asApiError(e)
        setError(err)
        setPhase(BLOCKING.has(err.code) ? 'blocked' : 'ready')
        if (STALE.has(err.code)) refresh()
      }
    },
    [api, refresh],
  )

  const confirm = useCallback(async (): Promise<ActionResponse | null> => {
    const p = params.current
    if (busy.current || !p) return null
    busy.current = true
    setPhase('working')
    setError(null)
    const freshToken = async () => {
      const res = await api.createIngestConfirmation({ tool: 'confirm_rows', params: p })
      issued.current = res
      return res
    }
    try {
      let tok = issued.current
      if (!tok || Date.parse(tok.expires_at) - Date.now() < TOKEN_MARGIN_MS) tok = await freshToken()
      let res: ActionResponse
      try {
        res = await api.applyIngestAction({ tool: tok.tool, params: tok.params, confirm_token: tok.confirm_token })
      } catch (e) {
        const err = asApiError(e)
        if (err.code !== 'TOKEN_EXPIRED' && err.code !== 'TOKEN_INVALID') throw err
        tok = await freshToken()
        res = await api.applyIngestAction({ tool: tok.tool, params: tok.params, confirm_token: tok.confirm_token })
      }
      issued.current = null
      setReceipt(res)
      setPhase('done')
      refresh(res.source.as_of)
      return res
    } catch (e) {
      issued.current = null
      fail(asApiError(e))
      return null
    } finally {
      busy.current = false
    }
  }, [api, fail, refresh])

  const reset = useCallback(() => {
    seq.current++
    params.current = null
    issued.current = null
    setPhase('idle')
    setError(null)
    setPreviewData(null)
    setReceipt(null)
  }, [])

  return { phase, error, preview: previewData, receipt, requestPreview: preview, confirm, reset }
}
