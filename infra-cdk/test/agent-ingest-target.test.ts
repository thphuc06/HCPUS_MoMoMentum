// Test target Gateway `ingest` của stack YofinaAgent: `npm test` (node:test + tsx, không cần AWS).
import { describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import * as fs from 'fs';
import * as path from 'path';
import { App, Stack } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import * as agentcore from 'aws-cdk-lib/aws-bedrockagentcore';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { addIngestTarget } from '../lib/agent-stack';

const ENV = { account: '111111111111', region: 'ap-southeast-1' }; // account giả của test
const REPO = path.resolve(__dirname, '..', '..');
const INGEST_TOOLS = (
  JSON.parse(fs.readFileSync(path.join(REPO, 'contracts', 'tools', 'ingest.json'), 'utf-8')) as Array<{ name: string }>
).map((t) => t.name);

type Res = { Type: string; Properties: Record<string, any>; DependsOn?: string[] };

/**
 * Dựng riêng khối target `ingest` (không cả AgentStack: stack đó còn đòi Cedar của tool các luồng khác chưa cài trên nhánh này) với
 * Gateway, vai, policy engine và một target đứng trước như AgentStack dựng; đường dẫn Lambda đi qua tham số SSM như AgentStack.
 */
function synth(): Template {
  const stack = new Stack(new App(), 'YofinaAgent', { env: ENV });
  const role = new iam.Role(stack, 'GatewayRole', { assumedBy: new iam.ServicePrincipal('bedrock-agentcore.amazonaws.com') });
  const engine = new agentcore.CfnPolicyEngine(stack, 'PolicyEngine', { name: 'yofina_policy_engine' });
  const gateway = new agentcore.CfnGateway(stack, 'Gateway', {
    name: 'yofina-gateway',
    protocolType: 'MCP',
    authorizerType: 'CUSTOM_JWT',
    authorizerConfiguration: { customJwtAuthorizer: { discoveryUrl: 'https://example.invalid/.well-known/openid-configuration' } },
    roleArn: role.roleArn,
  });
  const before = new agentcore.CfnGatewayTarget(stack, 'AuditTarget', {
    gatewayIdentifier: gateway.attrGatewayIdentifier,
    name: 'audit',
    targetConfiguration: { mcp: { lambda: { lambdaArn: 'arn:aws:lambda:ap-southeast-1:111111111111:function:x', toolSchema: { inlinePayload: [] } } } },
    credentialProviderConfigurations: [{ credentialProviderType: 'GATEWAY_IAM_ROLE' }],
  });
  addIngestTarget(stack, {
    gateway,
    gatewayRole: role,
    engine,
    after: before,
    functionName: ssm.StringParameter.valueForStringParameter(stack, '/yofina/ingest/api-function-name'),
    // như renderCedar của AgentStack: bỏ chú thích, thay ${GATEWAY_ARN}
    renderPolicy: (file) =>
      fs
        .readFileSync(file, 'utf-8')
        .split(/\r?\n/)
        .filter((l) => !l.trimStart().startsWith('//'))
        .join('\n')
        .trim()
        .replace(/\$\{GATEWAY_ARN\}/g, 'arn:aws:bedrock-agentcore:ap-southeast-1:111111111111:gateway/g'),
  });
  return Template.fromStack(stack);
}
const template = synth();
const targets = template.findResources('AWS::BedrockAgentCore::GatewayTarget') as Record<string, Res>;
const [ingestId, ingest] = Object.entries(targets).find(([, r]) => r.Properties.Name === 'ingest')!;

describe('YofinaAgent: target Gateway ingest', () => {
  it('ba tool của contracts/tools/ingest.json, trỏ Lambda yofina-ingest-api qua tham số SSM, xác thực bằng vai Gateway', () => {
    assert.ok(ingest, 'thiếu target ingest');
    const lambda = ingest.Properties.TargetConfiguration.Mcp.Lambda;
    assert.deepEqual(
      lambda.ToolSchema.InlinePayload.map((t: { Name?: string; name?: string }) => t.Name ?? t.name),
      INGEST_TOOLS,
    );
    assert.deepEqual(INGEST_TOOLS, ['start_job', 'get_job_status', 'confirm_rows']);
    const arn = JSON.stringify(lambda.LambdaArn);
    assert.match(arn, /SsmParameterValueyofinaingestapifunctionname/);
    assert.match(arn, /:lambda:/);
    assert.deepEqual(ingest.Properties.CredentialProviderConfigurations, [{ CredentialProviderType: 'GATEWAY_IAM_ROLE' }]);
  });

  it('target đi sau các target khác (Gateway chỉ đổi một target mỗi lần) và sau vai có quyền gọi Lambda', () => {
    const deps = ingest.DependsOn ?? [];
    const others = Object.entries(targets).filter(([id]) => id !== ingestId).map(([id]) => id);
    assert.ok(others.some((id) => deps.includes(id)), `IngestTarget phải phụ thuộc một target khác: ${deps}`);
    assert.ok(deps.some((d) => d.startsWith('GatewayRole')), `IngestTarget phải đi sau vai Gateway: ${deps}`);
  });

  it('vai Gateway được gọi ĐÚNG hàm ingest (không ký tự thay thế)', () => {
    const policies = template.findResources('AWS::IAM::Policy') as Record<string, Res>;
    const sts = Object.values(policies)
      .filter((p) => JSON.stringify(p.Properties.Roles).includes('GatewayRole'))
      .flatMap((p) => p.Properties.PolicyDocument.Statement as any[]);
    const st = sts.find((s) => s.Sid === 'InvokeIngestTarget');
    assert.ok(st, 'thiếu InvokeIngestTarget');
    assert.equal(st.Action, 'lambda:InvokeFunction');
    const res = JSON.stringify(st.Resource);
    assert.match(res, /SsmParameterValueyofinaingestapifunctionname/);
    assert.ok(!res.includes('*'), 'không wildcard');
  });

  it('một policy Cedar mỗi tool, ép user_id; chỉ confirm_rows xét dạng confirm_token; không số gắn cứng', () => {
    const pols = template.findResources('AWS::BedrockAgentCore::Policy') as Record<string, Res>;
    const mine = Object.values(pols).filter((p) => String(p.Properties.Name).startsWith('ingest_'));
    assert.deepEqual(mine.map((p) => p.Properties.Name).sort(), INGEST_TOOLS.map((t) => `ingest_${t}_own_user`).sort());
    for (const p of mine) {
      const tool = String(p.Properties.Name).replace(/^ingest_/, '').replace(/_own_user$/, '');
      const stmt = JSON.stringify(p.Properties.Definition.Cedar.Statement);
      assert.ok(stmt.includes(`AgentCore::Action::\\"ingest___${tool}\\"`), tool);
      assert.ok(stmt.includes('context.input.user_id == principal.id'), tool);
      assert.equal(stmt.includes('confirm_token'), tool === 'confirm_rows', tool);
      assert.ok(!stmt.includes('${'), `${tool}: placeholder chưa được thay`);
      assert.equal(p.Properties.ValidationMode, 'FAIL_ON_ANY_FINDINGS');
      assert.ok((p.DependsOn ?? []).includes(ingestId), `${tool}: policy tạo sau target`);
    }
  });
});
