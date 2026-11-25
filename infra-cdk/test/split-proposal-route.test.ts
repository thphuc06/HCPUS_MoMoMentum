// Route REST của đề xuất tỷ lệ ở bước 3 onboarding (`POST /jars/split-proposal`): khớp contracts/rest/openapi.yaml và nối vào
// Lambda ledger cùng JWT authorizer mặc định. Thiếu route này thì HTTP API trả 404 và bước 3 luôn báo "Chưa tính được tỷ lệ đề xuất".
// `npm test` (node:test + tsx, không cần AWS, không synth cả ToolsStack vì cần zip Lambda đã build).
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
import { SPLIT_PROPOSAL_ROUTES } from '../lib/tools-stack';

const REPO = path.resolve(__dirname, '..', '..');

/** Khối `paths./jars/split-proposal` của openapi.yaml (đọc chữ: infra-cdk không có thư viện YAML). */
function openapiSplitProposal(): string {
  const text = fs.readFileSync(path.join(REPO, 'contracts', 'rest', 'openapi.yaml'), 'utf8').replace(/\r\n/g, '\n');
  const m = text.match(/\n {2}\/jars\/split-proposal:\n([\s\S]*?)\n {2}\//);
  assert.ok(m, 'openapi.yaml thiếu paths./jars/split-proposal');
  return m[1];
}

describe('POST /jars/split-proposal', () => {
  it('đúng một route POST /jars/split-proposal, khớp hợp đồng (x-lambda: ledger, chỉ POST)', () => {
    assert.deepEqual(SPLIT_PROPOSAL_ROUTES.map(([p, m]) => `${m} ${p}`), ['POST /jars/split-proposal']);
    const block = openapiSplitProposal();
    assert.match(block, /^ {4}post:\n/m);
    assert.doesNotMatch(block, /^ {4}(get|put|patch|delete):/m);
    assert.match(block, /^ {6}x-lambda: ledger$/m);
  });

  it('nằm trong danh sách route của Lambda ledger (không phải forecast)', () => {
    const src = fs.readFileSync(path.join(REPO, 'infra-cdk', 'lib', 'tools-stack.ts'), 'utf8');
    const ledger = src.slice(src.indexOf('const routes: Array<'), src.indexOf('for (const [routePath, method] of routes)'));
    const forecast = src.slice(src.indexOf('const forecastRoutes'), src.indexOf('for (const [routePath, method] of forecastRoutes)'));
    assert.match(ledger, /\.\.\.SPLIT_PROPOSAL_ROUTES,/);
    assert.doesNotMatch(forecast, /SPLIT_PROPOSAL_ROUTES|split-proposal/);
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
    for (const [routePath, method] of SPLIT_PROPOSAL_ROUTES) api.addRoutes({ path: routePath, methods: [method], integration });
    const t = Template.fromStack(stack);
    t.hasResourceProperties('AWS::ApiGatewayV2::Route', { RouteKey: 'POST /jars/split-proposal', AuthorizationType: 'JWT' });
    t.hasResourceProperties('AWS::ApiGatewayV2::Integration', { IntegrationType: 'AWS_PROXY', PayloadFormatVersion: '2.0' });
  });
});
