import { CognitoAccessToken, CognitoIdToken, CognitoRefreshToken, CognitoUserSession } from 'amazon-cognito-identity-js'
import { describe, expect, it } from 'vitest'
import { toSession } from './cognito'

// JWT giả không ký (thư viện chỉ giải mã phần payload; chữ ký do server kiểm).
const b64 = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_')
const jwt = (payload: object) => `${b64({ alg: 'none' })}.${b64(payload)}.sig`

function cognitoSession(access: object) {
  const exp = Math.floor(Date.now() / 1000) + 3600
  return new CognitoUserSession({
    AccessToken: new CognitoAccessToken({ AccessToken: jwt({ exp, token_use: 'access', ...access }) }),
    IdToken: new CognitoIdToken({ IdToken: jwt({ exp, email: 'nguoi.dung@example.invalid', name: 'Minh' }) }),
    RefreshToken: new CognitoRefreshToken({ RefreshToken: 'r' }),
  })
}

describe('toSession', () => {
  it('đọc nhóm Cognito từ claim cognito:groups của access token', () => {
    const s = toSession(cognitoSession({ 'cognito:groups': ['ops', 'persona-vy'] }))
    expect(s.groups).toEqual(['ops', 'persona-vy'])
    expect(s.email).toBe('nguoi.dung@example.invalid')
    expect(s.displayName).toBe('Minh')
  })

  it('không có claim hoặc claim lạ: không thuộc nhóm nào', () => {
    expect(toSession(cognitoSession({})).groups).toEqual([])
    expect(toSession(cognitoSession({ 'cognito:groups': 'ops' })).groups).toEqual([])
  })
})