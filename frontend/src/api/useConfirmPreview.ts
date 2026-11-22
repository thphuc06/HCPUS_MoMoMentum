import { useEffect, useRef, useState } from 'react'
import { useApi, useDataVersion } from './ApiProvider'
import { ApiError } from './errors'
import type { ConfirmPreview, ToolName, ToolParams } from './schemas'

export type PreviewState =
  | { status: 'idle'; preview: null; error: null }
  | { status: 'loading'; preview: ConfirmPreview | null; error: null }
  | { status: 'ready'; preview: ConfirmPreview | null; error: null }
  | { status: 'error'; preview: null; error: ApiError }

const IDLE: PreviewState = { status: 'idle', preview: null, error: null }

/**
 * Xin bản xem trước của một thao tác ghi: `POST /confirmations` trả `preview` do SERVER tính (số dư trước và sau, phí
 * Trả sau, hạn mức, phần chia lương) và không ghi gì. Token trong phản hồi bị bỏ: lúc người dùng bấm xác nhận,
 * `useWriteFlow` xin token mới (token chỉ sống vài phút), nên ngồi xem lâu cũng không hết hạn.
 *
 * `params = null` thì không gọi gì (chưa đủ dữ liệu). Chạy lại khi `params` đổi (sau `debounceMs`) hoặc sau mỗi lần ghi
 * thành công (số dư đổi). Lỗi nghiệp vụ (không đủ số dư, vượt hạn mức...) trả về để màn hình báo sớm.
 */
export function usePreview(tool: ToolName, params: ToolParams | null, debounceMs = 0): PreviewState {
  const api = useApi()
  const version = useDataVersion()
  const [state, setState] = useState<PreviewState>(IDLE)
  const seq = useRef(0)
  const key = params === null ? null : JSON.stringify(params)

  useEffect(() => {
    if (key === null) {
      seq.current++
      setState(IDLE)
      return
    }
    const mine = ++seq.current
    setState((prev) => ({ status: 'loading', preview: prev.preview, error: null }))
    const timer = setTimeout(async () => {
      try {
        const res = await api.createConfirmation({ tool, params: JSON.parse(key) as ToolParams })
        if (mine === seq.current) setState({ status: 'ready', preview: res.preview ?? null, error: null })
      } catch (e) {
        if (mine !== seq.current) return
        setState({ status: 'error', preview: null, error: e instanceof ApiError ? e : new ApiError('INTERNAL_ERROR', 0) })
      }
    }, debounceMs)
    return () => clearTimeout(timer)
  }, [api, tool, key, version, debounceMs])

  return state
}
