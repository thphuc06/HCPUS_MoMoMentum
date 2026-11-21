// Kiểm THẬT đăng nhập Cognito SRP bằng đúng CognitoAuthClient của app. Chỉ chạy khi có biến môi trường
// (bỏ qua trong `npm test` thường):
//   YOFINA_LIVE_EMAIL=... YOFINA_LIVE_PASSWORD=... npx vitest run src/auth/cognito.live.test.ts
// Pool id và client id đọc từ frontend/.env.local. Mật khẩu chỉ nằm trong bộ nhớ tiến trình, không ghi ra đâu.
import { describe, expect, it } from 'vitest'
import { CognitoAuthClient } from './cognito'
import { AuthError } from './types'

declare const process: { env: Record<string, string | undefined> }

const email = process.env.YOFINA_LIVE_EMAIL
const password = process.env.YOFINA_LIVE_PASSWORD
const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID as string | undefined
const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID as string | undefined
const enabled = !!email && !!password && !!userPoolId && !!clientId

function claims(jwt: string): Record<string, unknown> {
  const payload = jwt.split('.')[1]!.replace(/-/g, '+').replace(/_/g, '/')
  return JSON.parse(atob(payload))
}

describe.skipIf(!enabled)('Cognito SRP thật (CognitoAuthClient)', () => {
  const client = new CognitoAuthClient({ userPoolId: userPoolId!, clientId: clientId! })

  it('đăng nhập đúng: access token của đúng client, sống khoảng 60 phút', async () => {
    const s = await client.signIn(email!, password!)
    const c = claims(s.accessToken)
    expect(c.token_use).toBe('access')
    expect(c.client_id).toBe(clientId)
    const ttlMin = (s.expiresAt - Date.now()) / 60_000
    expect(ttlMin).toBeGreaterThan(55)
    expect(ttlMin).toBeLessThanOrEqual(61)
    expect(s.email).toBeTruthy()
  })

  it('khôi phục phiên và làm mới bằng refresh token (token mới, vẫn hợp lệ)', async () => {
    const before = await client.getSession()
    expect(before).not.toBeNull()
    await new Promise((r) => setTimeout(r, 1100)) // iat tính theo giây
    const after = await client.getSession({ force: true })
    expect(after).not.toBeNull()
    expect(after!.accessToken).not.toBe(before!.accessToken)
    expect(claims(after!.accessToken).client_id).toBe(clientId)
    expect(after!.expiresAt).toBeGreaterThanOrEqual(before!.expiresAt)
  })

  it('đăng xuất thì không còn phiên', async () => {
    client.signOut()
    expect(await client.getSession()).toBeNull()
  })

  it('sai mật khẩu: lỗi INVALID_CREDENTIALS, thông báo tiếng Việt', async () => {
    const err = await client.signIn(email!, `${password!}-sai`).catch((e) => e)
    expect(err).toBeInstanceOf(AuthError)
    expect((err as AuthError).code).toBe('INVALID_CREDENTIALS')
    expect((err as AuthError).message).toMatch(/chưa đúng/)
  })
})
