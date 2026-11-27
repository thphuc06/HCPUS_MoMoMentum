// Kiểm CORS của HTTP API trong template YofinaTools bằng zip giả, không cần AWS.
import { after, before, describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { App } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { loadConfig } from '../config/config';
import { loadForecastConfig } from '../lib/forecast-pipeline';
import { loadToolsConfig, ToolsStack } from '../lib/tools-stack';

const ENV = { account: '111111111111', region: 'ap-southeast-1' };
const EMPTY_ZIP = Buffer.from([0x50, 0x4b, 0x05, 0x06, ...new Array(18).fill(0)]);

describe('CORS của YofinaTools', () => {
  let tmp: string;
  let ledgerZip: string;
  let forecastZip: string;

  before(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yofina-cors-test-'));
    ledgerZip = path.join(tmp, 'ledger-arm64.zip');
    forecastZip = path.join(tmp, 'forecast-arm64.zip');
    for (const zip of [ledgerZip, forecastZip]) fs.writeFileSync(zip, EMPTY_ZIP);
  });

  after(() => {
    for (const zip of [ledgerZip, forecastZip]) fs.unlinkSync(zip);
    fs.rmdirSync(tmp);
  });

  function assertApiOrigins(context: Record<string, string>, extraOrigins: string[]): void {
    const app = new App({ context: { ledgerZip, forecastZip, ...context } });
    const stack = new ToolsStack(app, 'YofinaTools', {
      env: ENV,
      cfg: loadConfig(app),
      tools: loadToolsConfig(app),
      forecast: loadForecastConfig(app),
    });
    const template = Template.fromStack(stack);
    const [amplifyUrl] = Object.entries(template.toJSON().Parameters ?? {}).find(
      ([, parameter]) => (parameter as { Default?: string }).Default === '/yofina/frontend/amplify-url',
    ) ?? [];
    assert.ok(amplifyUrl, 'thiếu tham số SSM chứa URL Amplify');
    template.hasResourceProperties('AWS::ApiGatewayV2::Api', {
      Name: 'yofina-api',
      CorsConfiguration: { AllowOrigins: [{ Ref: amplifyUrl }, ...extraOrigins] },
    });
  }

  it('context vắng hoặc null dùng localhost mặc định', () => {
    assert.deepEqual(loadToolsConfig(new App()).extraCorsOrigins, ['http://localhost:5173']);
    assert.deepEqual(loadToolsConfig(new App({ context: { extraCorsOrigins: null } })).extraCorsOrigins, ['http://localhost:5173']);
    assertApiOrigins({}, ['http://localhost:5173']);
  });

  it('context rỗng chỉ cho phép origin Amplify', () => {
    assert.deepEqual(loadToolsConfig(new App({ context: { extraCorsOrigins: '' } })).extraCorsOrigins, []);
    assert.deepEqual(loadToolsConfig(new App({ context: { extraCorsOrigins: ' , , ' } })).extraCorsOrigins, []);
  });

  it('HTTP API giữ origin Amplify khi bỏ localhost', () => {
    assertApiOrigins({ extraCorsOrigins: '' }, []);
  });

  it('context CSV cắt khoảng trắng và bỏ mục rỗng', () => {
    const app = new App({ context: { extraCorsOrigins: ' https://dev.example.org, ,https://preview.example.org ' } });
    assert.deepEqual(loadToolsConfig(app).extraCorsOrigins, ['https://dev.example.org', 'https://preview.example.org']);
  });
});
