import { z } from 'zod'

// Cấu hình chạy đọc từ import.meta.env (file .env.local, không commit). Thiếu giá trị thì app hiện màn
// "chưa cấu hình" thay vì vỡ; không có giá trị mặc định nào trỏ tới tài nguyên thật.

export type Config = {
  region: string
  userPoolId: string
  clientId: string
  apiUrl: string
  agentUrl: string
  /** Phát lại hội thoại từ GET /conversations/{id} (mặc định bật; VITE_CONVERSATION_REPLAY=0 để tắt). */
  replayEnabled: boolean
  demoEmail?: string
}

export type ConfigResult = { ok: true; config: Config } | { ok: false; missing: string[] }

const envSchema = z.object({
  VITE_AWS_REGION: z.string().trim().optional(),
  VITE_COGNITO_USER_POOL_ID: z.string().trim().optional(),
  VITE_COGNITO_CLIENT_ID: z.string().trim().optional(),
  VITE_API_URL: z.string().trim().optional(),
  VITE_API_BASE_URL: z.string().trim().optional(),
  VITE_AGENT_RUNTIME_URL: z.string().trim().optional(),
  VITE_AGENT_RUNTIME_ARN: z.string().trim().optional(),
  VITE_CONVERSATION_REPLAY: z.string().trim().optional(),
  VITE_DEMO_EMAIL: z.string().trim().optional(),
})

/** https://bedrock-agentcore.<region>.amazonaws.com/runtimes/<ARN url-encode>/invocations?qualifier=DEFAULT */
export function buildRuntimeUrl(arn: string, region: string, qualifier = 'DEFAULT'): string {
  return `https://bedrock-agentcore.${region}.amazonaws.com/runtimes/${encodeURIComponent(arn)}/invocations?qualifier=${qualifier}`
}

function trimSlash(s: string): string {
  return s.replace(/\/+$/, '')
}

export function parseConfig(rawEnv: Record<string, unknown>): ConfigResult {
  const env = envSchema.parse(
    Object.fromEntries(Object.entries(rawEnv).filter(([, v]) => typeof v === 'string')),
  )
  const region = env.VITE_AWS_REGION
  const apiUrl = env.VITE_API_URL || env.VITE_API_BASE_URL
  let agentUrl = env.VITE_AGENT_RUNTIME_URL
  if (!agentUrl && env.VITE_AGENT_RUNTIME_ARN && region) {
    agentUrl = buildRuntimeUrl(env.VITE_AGENT_RUNTIME_ARN, region)
  }
  const missing: string[] = []
  if (!region) missing.push('VITE_AWS_REGION')
  if (!apiUrl) missing.push('VITE_API_URL')
  if (!agentUrl) missing.push('VITE_AGENT_RUNTIME_URL (hoặc VITE_AGENT_RUNTIME_ARN)')
  if (!env.VITE_COGNITO_USER_POOL_ID) missing.push('VITE_COGNITO_USER_POOL_ID')
  if (!env.VITE_COGNITO_CLIENT_ID) missing.push('VITE_COGNITO_CLIENT_ID')
  if (missing.length > 0 || !region || !apiUrl || !agentUrl || !env.VITE_COGNITO_USER_POOL_ID || !env.VITE_COGNITO_CLIENT_ID) return { ok: false, missing }
  return {
    ok: true,
    config: {
      region,
      userPoolId: env.VITE_COGNITO_USER_POOL_ID!,
      clientId: env.VITE_COGNITO_CLIENT_ID!,
      apiUrl: trimSlash(apiUrl),
      agentUrl,
      replayEnabled: env.VITE_CONVERSATION_REPLAY !== '0',
      demoEmail: env.VITE_DEMO_EMAIL || undefined,
    },
  }
}

export function loadConfig(): ConfigResult {
  return parseConfig(import.meta.env as unknown as Record<string, unknown>)
}
