// Test quyền đọc công tắc khối lập luận (#7) của vai Runtime trong stack YofinaAgent: `npm test` (node:test + tsx, không cần AWS).
import { describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import { App } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { loadConfig } from '../config/config';
import { AgentStack, loadAgentConfig } from '../lib/agent-stack';
import { loadToolsConfig } from '../lib/tools-stack';

const ENV = { account: '111111111111', region: 'ap-southeast-1' }; // account giả của test

type Statement = { Sid?: string; Action: string | string[]; Resource: unknown };

describe('YofinaAgent: công tắc khối lập luận', () => {
  it('vai Runtime đọc được đúng khóa SSM agent/reasoning_enabled trong ReadConfig', () => {
    const app = new App();
    const stack = new AgentStack(app, 'YofinaAgent', {
      env: ENV,
      cfg: loadConfig(app),
      tools: loadToolsConfig(app),
      agent: loadAgentConfig(app),
    });
    const policies = Template.fromStack(stack).findResources('AWS::IAM::Policy') as Record<
      string,
      { Properties: { PolicyDocument: { Statement: Statement[] } } }
    >;
    const statements = Object.values(policies).flatMap((p) => p.Properties.PolicyDocument.Statement);
    const cfg = statements.find((s) => s.Sid === 'ReadConfig');
    assert.ok(cfg, 'thiếu statement ReadConfig');
    assert.ok([cfg.Action].flat().includes('ssm:GetParameter'));
    const resources = JSON.stringify(cfg.Resource);
    assert.match(resources, /:parameter\/yofina\/agent\/reasoning_enabled"/);
    assert.doesNotMatch(resources, /:parameter\/yofina\/agent\/\*/, 'chỉ đúng một khóa, không mở cả nhánh agent/');
  });
});
