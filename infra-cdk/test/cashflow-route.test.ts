// Route REST của biểu đồ chi tiêu (`GET /cashflow`): khớp contracts/rest/openapi.yaml và nối vào Lambda ledger cùng JWT authorizer
// mặc định. `npm test` (node:test + tsx, không cần AWS, không synth cả ToolsStack vì cần zip Lambda đã build).
import { describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import * as fs from 'fs';
import * as path from 'path';
import { App, Stack } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpJwtAuthorizer } from 'aws-cdk-lib/aws-apigatewayv2-authorizers';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { CASHFLOW_ROUTES } from '../lib/tools-stack';

const REPO = path.resolve(__dirname, '..', '..');

/** Khối `paths./cashflow` của openapi.yaml (đọc chữ: infra-cdk không có thư viện YAML). */
function openapiCashflow(): string {
  const text = fs.readFileSync(path.join(REPO, 'contracts', 'rest', 'openapi.yaml'), 'utf8').replace(/\r\n/g, '\n');
  const m = text.match(/\n {2}\/cashflow:\n([\s\S]*?)\n {2}\/|\n {2}\/cashflow:\n([\s\S]*?)\ncomponents:/);
  assert.ok(m, 'openapi.yaml thiếu paths./cashflow');
  return m[1] ?? m[2] ?? '';
}

describe('GET /cashflow', () => {
  it('đúng một route GET /cashflow, khớp hợp đồng (x-lambda: ledger, chỉ GET)', () => {
    assert.deepEqual(CASHFLOW_ROUTES.map(([p, m]) => `${m} ${p}`), ['GET /cashflow']);
    const block = openapiCashflow();
    assert.match(block, /^ {4}get:\n/m);
    assert.doesNotMatch(block, /^ {4}(post|put|patch|delete):/m);
    assert.match(block, /^ {6}x-lambda: ledger$/m);
    assert.match(block, /operationId: getCashflow/);
  });

  it('nằm trong danh sách route của Lambda ledger (không phải forecast)', () => {
    const src = fs.readFileSync(path.join(REPO, 'infra-cdk', 'lib', 'tools-stack.ts'), 'utf8');
    const ledger = src.slice(src.indexOf('const routes: Array<'), src.indexOf('for (const [routePath, method] of routes)'));
    const forecast = src.slice(src.indexOf('const forecastRoutes'), src.indexOf('for (const [routePath, method] of forecastRoutes)'));
    assert.match(ledger, /\.\.\.CASHFLOW_ROUTES,/);
    assert.doesNotMatch(forecast, /CASHFLOW_ROUTES|\/cashflow/);
  });

  it('cách stack nối route (addRoutes với authorizer mặc định) cho ra route JWT, AWS_PROXY tới Lambda', () => {
    const stack = new Stack(new App(), 'T', { env: { account: '111111111111', region: 'ap-southeast-1' } }); // account giả
    const fn = new lambda.Function(stack, 'Ledger', {
      runtime: lambda.Runtime.PYTHON_3_13,
      handler: 'handler.handler',
      code: lambda.Code.fromInline('def handler(e, c): return {}'),
    });
    const api = new apigwv2.HttpApi(stack, 'Api', {
      defaultAuthorizer: new HttpJwtAuthorizer('Jwt', 'https://cognito-idp.ap-southeast-1.amazonaws.com/pool', { jwtAudience: ['client'] }),
    });
    const integration = new HttpLambdaIntegration('LedgerIntegration', fn);
    for (const [routePath, method] of CASHFLOW_ROUTES) api.addRoutes({ path: routePath, methods: [method], integration });
    const t = Template.fromStack(stack);
    t.hasResourceProperties('AWS::ApiGatewayV2::Route', { RouteKey: 'GET /cashflow', AuthorizationType: 'JWT' });
    t.hasResourceProperties('AWS::ApiGatewayV2::Integration', { IntegrationType: 'AWS_PROXY', PayloadFormatVersion: '2.0' });
  });
});
