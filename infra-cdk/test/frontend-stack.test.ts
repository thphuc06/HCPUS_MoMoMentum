// Test FrontendStack (custom headers của Amplify): `npm test` (node:test + tsx, không cần AWS).
import { describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import { App } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { loadConfig } from '../config/config';
import { FrontendStack } from '../lib/frontend-stack';

const ACCOUNT = '111111111111'; // account giả của test

/** Header của pattern `**\/*` trong customHeaders (YAML do stack sinh), dạng tên → giá trị. */
function headersOf(region = 'ap-southeast-1'): Record<string, string> {
  const app = new App({ context: { region } });
  const cfg = loadConfig(app);
  const stack = new FrontendStack(app, 'F', { env: { account: ACCOUNT, region: cfg.region }, cfg });
  const apps = Template.fromStack(stack).findResources('AWS::Amplify::App');
  const yaml = (Object.values(apps)[0] as any).Properties.CustomHeaders as string;
  assert.match(yaml, /^customHeaders:\n {2}- pattern: "\*\*\/\*"\n/);
  const out: Record<string, string> = {};
  for (const m of yaml.matchAll(/- key: (.+)\n\s+value: (.+)/g)) {
    const v = m[2].trim();
    out[m[1].trim()] = v.startsWith('"') ? JSON.parse(v) : v;
  }
  return out;
}

/** CSP tách thành chỉ thị → danh sách nguồn. */
function cspOf(region?: string): Record<string, string[]> {
  const csp = headersOf(region)['Content-Security-Policy'];
  assert.ok(csp, 'thiếu Content-Security-Policy');
  return Object.fromEntries(
    csp.split(';').map((d) => d.trim()).filter(Boolean).map((d) => {
      const [name, ...sources] = d.split(/\s+/);
      return [name, sources];
    }),
  );
}

describe('FrontendStack custom headers', () => {
  it('CSP chặn nhúng trang (frame-ancestors none) và chỉ cho script cùng nguồn', () => {
    const csp = cspOf();
    assert.deepEqual(csp['frame-ancestors'], ["'none'"]);
    assert.deepEqual(csp['default-src'], ["'self'"]);
    assert.deepEqual(csp['script-src'], ["'self'"], 'không unsafe-inline/unsafe-eval cho script');
    assert.deepEqual(csp['object-src'], ["'none'"]);
    assert.deepEqual(csp['base-uri'], ["'self'"]);
  });

  it('connect-src có Cognito SRP, Runtime SSE, HTTP API và S3 presigned POST của đúng vùng', () => {
    const connect = cspOf()['connect-src'];
    for (const src of [
      "'self'",
      'https://cognito-idp.ap-southeast-1.amazonaws.com',
      'https://bedrock-agentcore.ap-southeast-1.amazonaws.com',
      'https://*.execute-api.ap-southeast-1.amazonaws.com',
      'https://*.s3.ap-southeast-1.amazonaws.com',
    ]) {
      assert.ok(connect.includes(src), `connect-src thiếu ${src}`);
    }
  });

  it('nguồn AWS theo vùng của cấu hình, không gắn cứng', () => {
    const connect = cspOf('ap-northeast-1')['connect-src'];
    assert.ok(connect.includes('https://cognito-idp.ap-northeast-1.amazonaws.com'));
    assert.ok(!connect.some((s) => s.includes('ap-southeast-1')));
  });

  it('font và ảnh cho data: (Vite nhúng font nhỏ thành data URI), style cho inline (thư viện UI chèn style)', () => {
    const csp = cspOf();
    assert.deepEqual(csp['font-src'], ["'self'", 'data:']);
    assert.ok(csp['img-src'].includes("'self'") && csp['img-src'].includes('data:'));
    assert.deepEqual(csp['style-src'], ["'self'", "'unsafe-inline'"]);
  });

  it('giữ nosniff, Referrer-Policy, HSTS; header không chứa account ID', () => {
    const h = headersOf();
    assert.equal(h['X-Content-Type-Options'], 'nosniff');
    assert.equal(h['Referrer-Policy'], 'strict-origin-when-cross-origin');
    assert.equal(h['Strict-Transport-Security'], 'max-age=31536000; includeSubDomains');
    assert.ok(!JSON.stringify(h).includes(ACCOUNT));
  });
});
