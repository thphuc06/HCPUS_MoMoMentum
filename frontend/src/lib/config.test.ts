import { describe, expect, it } from 'vitest'
import { buildRuntimeUrl, parseConfig } from './config'

const base = {
  VITE_AWS_REGION: 'ap-southeast-1',
  VITE_COGNITO_USER_POOL_ID: 'pool-id-gia',
  VITE_COGNITO_CLIENT_ID: 'client-id-gia',
  VITE_API_URL: 'https://api.example.invalid/',
}

describe('cấu hình từ import.meta.env', () => {
  it('dựng URL Runtime từ ARN, mã hóa ARN trong đường dẫn', () => {
    const arn = 'arn:aws:bedrock-agentcore:ap-southeast-1:000000000000:runtime/yofina_agent-AbCdEf'
    expect(buildRuntimeUrl(arn, 'ap-southeast-1')).toBe(
      'https://bedrock-agentcore.ap-southeast-1.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3Aap-southeast-1%3A000000000000%3Aruntime%2Fyofina_agent-AbCdEf/invocations?qualifier=DEFAULT',
    )
  })

  it('đủ biến: ok, bỏ dấu / cuối của URL API, ưu tiên URL đầy đủ hơn ARN', () => {
    const r = parseConfig({ ...base, VITE_AGENT_RUNTIME_ARN: 'arn:x', VITE_AGENT_RUNTIME_URL: 'https://rt.example.invalid/invocations?qualifier=DEFAULT' })
    expect(r.ok).toBe(true)
    if (r.ok) {
      expect(r.config.apiUrl).toBe('https://api.example.invalid')
      expect(r.config.agentUrl).toBe('https://rt.example.invalid/invocations?qualifier=DEFAULT')
      expect(r.config.replayEnabled).toBe(true) // mặc định bật phát lại hội thoại
      expect(r.config.demoEmail).toBeUndefined()
    }
  })

  it('chỉ có ARN thì tự dựng URL', () => {
    const r = parseConfig({ ...base, VITE_AGENT_RUNTIME_ARN: 'arn:aws:x:y' })
    expect(r.ok && r.config.agentUrl.startsWith('https://bedrock-agentcore.ap-southeast-1.amazonaws.com/runtimes/')).toBe(true)
  })

  it('chấp nhận tên cũ VITE_API_BASE_URL (print_env.py) và email demo tùy chọn', () => {
    const { VITE_API_URL: _omit, ...rest } = base
    void _omit
    const r = parseConfig({ ...rest, VITE_API_BASE_URL: 'https://api2.example.invalid', VITE_AGENT_RUNTIME_URL: 'https://rt.example.invalid/i', VITE_DEMO_EMAIL: 'demo@example.invalid' })
    expect(r.ok && r.config.apiUrl).toBe('https://api2.example.invalid')
    expect(r.ok && r.config.demoEmail).toBe('demo@example.invalid')
  })

  it('thiếu biến: báo danh sách thiếu thay vì ném lỗi', () => {
    const r = parseConfig({ VITE_AWS_REGION: 'ap-southeast-1' })
    expect(r.ok).toBe(false)
    if (!r.ok) {
      expect(r.missing).toEqual(
        expect.arrayContaining(['VITE_API_URL', 'VITE_COGNITO_USER_POOL_ID', 'VITE_COGNITO_CLIENT_ID', 'VITE_AGENT_RUNTIME_URL (hoặc VITE_AGENT_RUNTIME_ARN)']),
      )
    }
  })

  it('VITE_CONVERSATION_REPLAY=0 tắt phát lại', () => {
    const r = parseConfig({ ...base, VITE_AGENT_RUNTIME_URL: 'https://rt.example.invalid/i', VITE_CONVERSATION_REPLAY: '0' })
    expect(r.ok && r.config.replayEnabled).toBe(false)
  })

  it('làm nóng phiên mặc định bật, VITE_CHAT_WARMUP=0 tắt; cửa sổ Hoàn tác mặc định 30 giây và bị kẹp trong 5 đến 300', () => {
    const on = parseConfig({ ...base, VITE_AGENT_RUNTIME_URL: 'https://rt.example.invalid/i' })
    expect(on.ok && on.config.warmupEnabled).toBe(true)
    expect(on.ok && on.config.undoWindowSeconds).toBe(30)
    const off = parseConfig({ ...base, VITE_AGENT_RUNTIME_URL: 'https://rt.example.invalid/i', VITE_CHAT_WARMUP: '0', VITE_UNDO_WINDOW_SECONDS: '1000' })
    expect(off.ok && off.config.warmupEnabled).toBe(false)
    expect(off.ok && off.config.undoWindowSeconds).toBe(300)
    const low = parseConfig({ ...base, VITE_AGENT_RUNTIME_URL: 'https://rt.example.invalid/i', VITE_UNDO_WINDOW_SECONDS: '1' })
    expect(low.ok && low.config.undoWindowSeconds).toBe(5)
  })

  it('giá trị rỗng coi như thiếu', () => {
    const r = parseConfig({ ...base, VITE_COGNITO_CLIENT_ID: '  ', VITE_AGENT_RUNTIME_URL: 'https://rt.example.invalid/i' })
    expect(r.ok).toBe(false)
  })
})
