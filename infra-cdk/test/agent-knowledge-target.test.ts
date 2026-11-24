// Test target Gateway `knowledge` của stack YofinaAgent (biểu phí và tỷ giá ngoại tệ): `npm test` (node:test + tsx, không cần AWS).
import { describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import * as fs from 'fs';
import * as path from 'path';
import { App } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { loadConfig } from '../config/config';
import { AgentStack, loadAgentConfig } from '../lib/agent-stack';
import { loadToolsConfig } from '../lib/tools-stack';

const ENV = { account: '111111111111', region: 'ap-southeast-1' }; // account giả của test
const REPO = path.resolve(__dirname, '..', '..');
const KNOWLEDGE_TOOLS = (
  JSON.parse(fs.readFileSync(path.join(REPO, 'contracts', 'tools', 'knowledge.json'), 'utf-8')) as Array<{ name: string }>
).map((t) => t.name);

type Res = { Type: string; Properties: Record<string, any>; DependsOn?: string[] };

/** Dựng cả AgentStack như bin/app.ts: thiếu `gateway/policies/<tool>.cedar` của bất kỳ tool nào thì constructor ném lỗi. */
function synth(): Template {
  const app = new App();
  const stack = new AgentStack(app, 'YofinaAgent', {
    env: ENV,
    cfg: loadConfig(app),
    tools: loadToolsConfig(app),
    agent: loadAgentConfig(app),
  });
  return Template.fromStack(stack);
}
const template = synth();
const targets = template.findResources('AWS::BedrockAgentCore::GatewayTarget') as Record<string, Res>;
const [knowledgeId, knowledge] = Object.entries(targets).find(([, r]) => r.Properties.Name === 'knowledge')!;

describe('YofinaAgent: target Gateway knowledge', () => {
  it('khai báo đúng các tool của contracts/tools/knowledge.json, có get_exchange_rate, trỏ Lambda ledger', () => {
    assert.ok(knowledge, 'thiếu target knowledge');
    assert.deepEqual(KNOWLEDGE_TOOLS, ['get_fee_schedule', 'get_exchange_rate']);
    const lambda = knowledge.Properties.TargetConfiguration.Mcp.Lambda;
    const names = lambda.ToolSchema.InlinePayload.map((t: { Name?: string; name?: string }) => t.Name ?? t.name);
    assert.deepEqual(names, KNOWLEDGE_TOOLS);
    assert.match(JSON.stringify(lambda.LambdaArn), /SsmParameterValueyofinaledgerfunctionarn/);
    assert.deepEqual(knowledge.Properties.CredentialProviderConfigurations, [{ CredentialProviderType: 'GATEWAY_IAM_ROLE' }]);
  });

  it('một policy Cedar mỗi tool của knowledge, ép user_id, không xét token, tạo sau target', () => {
    const pols = template.findResources('AWS::BedrockAgentCore::Policy') as Record<string, Res>;
    const mine = Object.values(pols).filter((p) => String(p.Properties.Name).startsWith('knowledge_'));
    assert.deepEqual(mine.map((p) => p.Properties.Name).sort(), KNOWLEDGE_TOOLS.map((t) => `knowledge_${t}_own_user`).sort());
    for (const p of mine) {
      const tool = String(p.Properties.Name).replace(/^knowledge_/, '').replace(/_own_user$/, '');
      const stmt = JSON.stringify(p.Properties.Definition.Cedar.Statement);
      assert.ok(stmt.includes(`AgentCore::Action::\\"knowledge___${tool}\\"`), tool);
      assert.ok(stmt.includes('context.input.user_id == principal.id'), tool);
      assert.ok(!stmt.includes('confirm_token'), tool);
      assert.ok(!stmt.includes('${'), `${tool}: placeholder chưa được thay`);
      assert.ok(!stmt.includes('//'), `${tool}: còn dòng chú thích`);
      assert.equal(p.Properties.ValidationMode, 'FAIL_ON_ANY_FINDINGS');
      assert.ok((p.DependsOn ?? []).includes(knowledgeId), `${tool}: policy tạo sau target`);
    }
  });
});
