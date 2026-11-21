import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { CognitoAuthClient } from '@/auth/cognito'
import type { AuthClient } from '@/auth/types'
import { loadConfig } from '@/lib/config'

function SetupError({ missing }: { missing: string[] }) {
  return (
    <div className="phone-stage">
      <div className="phone-frame p-6">
        <h1 className="text-title font-bold text-ink">Chưa cấu hình ứng dụng</h1>
        <p className="mt-2 text-body text-ink-2">Thiếu các biến môi trường sau trong frontend/.env.local (xem .env.example):</p>
        <ul className="mt-3 list-disc pl-5 text-small text-ink">
          {missing.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      </div>
    </div>
  )
}

async function createAuthClient(config: { userPoolId: string; clientId: string }): Promise<AuthClient> {
  // `npm run dev:mock` (mode=mock) dùng bộ đăng nhập giả của dev-mocks; ở mọi chế độ khác nhánh này bị loại khỏi bundle.
  if (import.meta.env.MODE === 'mock') {
    const { MockAuthClient } = await import('../dev-mocks/client/mock-auth')
    return new MockAuthClient()
  }
  return new CognitoAuthClient(config)
}

async function boot() {
  const root = createRoot(document.getElementById('root')!)
  const result = loadConfig()
  if (!result.ok) {
    root.render(
      <StrictMode>
        <SetupError missing={result.missing} />
      </StrictMode>,
    )
    return
  }
  const authClient = await createAuthClient(result.config)
  root.render(
    <StrictMode>
      <App config={result.config} authClient={authClient} />
    </StrictMode>,
  )
}

void boot()
