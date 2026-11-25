// Quyền IAM của trần theo tài khoản mỗi ngày (#13, B4): `npm test` (node:test + tsx, không cần AWS, không cần zip thật).
// yofina_core.quota đếm ở bảng usage (`UpdateItem` có điều kiện) và đọc trần ở SSM `/<prefix>/quota/<tên>` (`GetParameter`).
import { after, before, describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { App } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { loadConfig } from '../config/config';
import { AgentStack, loadAgentConfig } from '../lib/agent-stack';
import { IngestStack, loadIngestConfig } from '../lib/ingest-stack';
import { loadToolsConfig } from '../lib/tools-stack';

const ENV = { account: '111111111111', region: 'ap-southeast-1' }; // account giả của test
const QUOTA_PARAMS = 'arn:aws:ssm:ap-southeast-1:111111111111:parameter/yofina/quota/*';

type Res = { Type: string; Properties: Record<string, any> };
const asList = <T>(v: T | T[]): T[] => (Array.isArray(v) ? v : [v]);

function statementsOf(template: Template, roleLogicalPrefix: string): any[] {
  const policies = template.findResources('AWS::IAM::Policy') as Record<string, Res>;
  const out: any[] = [];
  for (const pol of Object.values(policies)) {
    if (JSON.stringify(pol.Properties.Roles).includes(roleLogicalPrefix)) out.push(...pol.Properties.PolicyDocument.Statement);
  }
  return out;
}

const withAction = (sts: any[], action: string) => sts.filter((s) => asList<string>(s.Action).includes(action));

describe('trần theo tài khoản: quyền IAM', () => {
  let tmp: string;
  let ingest: Template;

  before(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yofina-quota-test-'));
    const zip = path.join(tmp, 'ingest-arm64.zip');
    // zip rỗng hợp lệ (chỉ bản ghi end-of-central-directory): đủ cho Code.fromAsset, không lên AWS
    fs.writeFileSync(zip, Buffer.from([0x50, 0x4b, 0x05, 0x06, ...new Array(18).fill(0)]));
    const app = new App({ context: { ingestZip: zip } });
    const stack = new IngestStack(app, 'YofinaIngest', {
      env: ENV,
      cfg: loadConfig(app),
      tools: loadToolsConfig(app),
      ingest: loadIngestConfig(app),
    });
    ingest = Template.fromStack(stack);
  });

  after(() => fs.rmSync(tmp, { recursive: true, force: true }));

  it('Lambda ingest API: UpdateItem chỉ trên bảng usage, GetParameter trên /yofina/quota/*', () => {
    const api = statementsOf(ingest, 'ApiServiceRole');
    const update = withAction(api, 'dynamodb:UpdateItem');
    assert.equal(update.length, 1, 'một statement UpdateItem');
    assert.deepEqual(asList(update[0].Action), ['dynamodb:UpdateItem']);
    const resources = asList<any>(update[0].Resource);
    assert.equal(resources.length, 1);
    assert.match(JSON.stringify(resources[0]), /table\/".*SsmParameterValueyofinadynamodbusagetable/);
    const read = withAction(api, 'ssm:GetParameter');
    assert.ok(read.some((s) => asList(s.Resource).includes(QUOTA_PARAMS)), 'thiếu GetParameter trên /yofina/quota/*');
    // trần chỉ đọc từng khóa: không cần GetParametersByPath, không ghi SSM
    for (const s of api) for (const a of asList<string>(s.Action)) assert.ok(!/^ssm:(Put|Delete|GetParametersByPath)/.test(a), a);
  });

  it('Runtime agent: /yofina/quota/* nằm trong ReadConfig', () => {
    const app = new App();
    const stack = new AgentStack(app, 'YofinaAgent', {
      env: ENV,
      cfg: loadConfig(app),
      tools: loadToolsConfig(app),
      agent: loadAgentConfig(app),
    });
    const runtime = statementsOf(Template.fromStack(stack), 'RuntimeRole');
    const cfg = runtime.find((s) => s.Sid === 'ReadConfig');
    assert.ok(cfg, 'thiếu ReadConfig');
    assert.ok(asList<string>(cfg.Action).includes('ssm:GetParameter'));
    assert.ok(asList(cfg.Resource).includes(QUOTA_PARAMS), 'ReadConfig thiếu /yofina/quota/*');
    // bộ đếm lượt chat dùng chung quyền UpdateItem trên bảng usage của bộ đếm lượt gọi model
    assert.ok(withAction(runtime, 'dynamodb:UpdateItem').length > 0);
  });
});
