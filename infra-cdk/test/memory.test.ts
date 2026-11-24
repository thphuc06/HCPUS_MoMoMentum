// Test construct YofinaMemory và quyền REST quyền riêng tư của ledger: `npm test` (node:test + tsx, không cần AWS).
import { describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import { App, Stack } from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sns from 'aws-cdk-lib/aws-sns';
import {
  AGENT_MEMORY_ACTIONS,
  LEDGER_MEMORY_ACTIONS,
  MEMORY_NAMESPACES,
  PRIVACY_ROUTES,
  YofinaMemory,
  grantLedgerPrivacy,
} from '../lib/memory';

const ENV = { account: '111111111111', region: 'ap-southeast-1' }; // account giả của test

function memoryStack(withTopic = true) {
  const stack = new Stack(new App(), 'T', { env: ENV });
  const topic = withTopic ? new sns.Topic(stack, 'Topic') : undefined;
  const mem = new YofinaMemory(stack, 'M', { alertTopic: topic });
  return { stack, mem, get t() { return Template.fromStack(stack); } };
}

function statementsOf(t: Template, actionPrefix: string): any[] {
  const out: any[] = [];
  for (const p of Object.values(t.findResources('AWS::IAM::Policy')) as any[]) {
    for (const s of p.Properties.PolicyDocument.Statement) {
      const actions = ([] as string[]).concat(s.Action);
      if (actions.some((a) => a.startsWith(actionPrefix))) out.push(s);
    }
  }
  return out;
}

describe('YofinaMemory', () => {
  it('một Memory, ba strategy dựng sẵn, mỗi strategy một namespace có / đầu và cuối, hạn event 7 ngày, khóa AWS', () => {
    const { t } = memoryStack();
    const mems = Object.values(t.findResources('AWS::BedrockAgentCore::Memory')) as any[];
    assert.equal(mems.length, 1);
    const p = mems[0].Properties;
    assert.equal(p.Name, 'yofina_memory');
    assert.equal(p.EventExpiryDuration, 7);
    assert.equal(p.EncryptionKeyArn, undefined, 'mặc định khóa do AWS quản lý');
    const strategies = p.MemoryStrategies as any[];
    assert.equal(strategies.length, 3);
    const byKey = Object.fromEntries(strategies.map((s) => [Object.keys(s)[0], Object.values(s)[0] as any]));
    assert.deepEqual(byKey.UserPreferenceMemoryStrategy.Namespaces, [MEMORY_NAMESPACES.preference]);
    assert.deepEqual(byKey.SemanticMemoryStrategy.Namespaces, [MEMORY_NAMESPACES.fact]);
    assert.deepEqual(byKey.SummaryMemoryStrategy.Namespaces, [MEMORY_NAMESPACES.session_summary]);
    assert.equal(byKey.CustomMemoryStrategy, undefined, 'không override: không cần model trong tài khoản');
    for (const ns of Object.values(MEMORY_NAMESPACES)) {
      assert.ok(ns.startsWith('/') && ns.endsWith('/') && ns.includes('{actorId}'), ns);
    }
    // L2 luôn tạo execution role; với strategy dựng sẵn role không dùng tới nên không được có quyền nào.
    const roles = Object.values(t.findResources('AWS::IAM::Role')) as any[];
    assert.equal(roles.length, 1);
    assert.equal(roles[0].Properties.Policies, undefined);
    assert.equal(roles[0].Properties.ManagedPolicyArns, undefined);
    assert.equal(Object.keys(t.findResources('AWS::IAM::Policy')).length, 0);
  });

  it('Runtime chỉ được IngestData, RetrieveMemoryRecords, ListMemoryRecords trên ĐÚNG ARN Memory này', () => {
    const { stack, mem } = memoryStack(false);
    const role = new iam.Role(stack, 'R', { assumedBy: new iam.ServicePrincipal('bedrock-agentcore.amazonaws.com') });
    mem.grantAgentRuntime(role);
    const t = Template.fromStack(stack);
    const st = statementsOf(t, 'bedrock-agentcore:');
    assert.equal(st.length, 1);
    assert.deepEqual([...st[0].Action].sort(), [...AGENT_MEMORY_ACTIONS].sort());
    assert.ok(!AGENT_MEMORY_ACTIONS.some((a) => /Delete|CreateEvent|BatchCreate/.test(a)));
    const resource = JSON.stringify(st[0].Resource);
    assert.ok(resource.includes('MemoryArn') && !resource.includes('*'), resource);
  });

  it('FailedExtraction vào topic cảnh báo bằng truy vấn Metrics Insights theo ARN Memory', () => {
    const { t } = memoryStack();
    const alarms = Object.values(t.findResources('AWS::CloudWatch::Alarm')) as any[];
    assert.equal(alarms.length, 1);
    const a = alarms[0].Properties;
    const expr = JSON.stringify(a.Metrics);
    assert.ok(expr.includes('SELECT SUM(FailedExtraction) FROM \\"AWS/Bedrock-AgentCore\\" WHERE Resource ='), expr);
    assert.equal(a.TreatMissingData, 'notBreaching');
    assert.equal(a.AlarmActions.length, 1);
    assert.equal(memoryStack(false).t.findResources('AWS::CloudWatch::Alarm') && Object.keys(memoryStack(false).t.findResources('AWS::CloudWatch::Alarm')).length, 0);
  });

  it('id Memory ra SSM /yofina/memory/id cho Lambda ledger', () => {
    const { t } = memoryStack(false);
    const names = (Object.values(t.findResources('AWS::SSM::Parameter')) as any[]).map((p) => p.Properties.Name);
    assert.ok(names.includes('/yofina/memory/id') && names.includes('/yofina/memory/arn'));
  });
});

describe('grantLedgerPrivacy', () => {
  function ledgerStack() {
    const stack = new Stack(new App(), 'L', { env: ENV });
    const fn = new lambda.Function(stack, 'Fn', {
      runtime: lambda.Runtime.PYTHON_3_13,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromInline('def lambda_handler(e, c): pass'),
    });
    grantLedgerPrivacy(stack, fn, { prefix: 'yofina', uploadPrefix: 'u/' });
    return { t: Template.fromStack(stack) };
  }

  it('Memory: chỉ xem và xóa, theo tên Memory; không ghi, không semantic search', () => {
    const { t } = ledgerStack();
    const st = statementsOf(t, 'bedrock-agentcore:');
    assert.equal(st.length, 1);
    assert.deepEqual([...st[0].Action].sort(), [...LEDGER_MEMORY_ACTIONS].sort());
    assert.ok(!st[0].Action.includes('bedrock-agentcore:RetrieveMemoryRecords'));
    assert.ok(!st[0].Action.some((a: string) => /Ingest|CreateEvent|BatchCreate|BatchUpdate/.test(a)));
    assert.match(JSON.stringify(st[0].Resource), /memory\/yofina_memory-\*/);
  });

  it('S3: chỉ liệt kê và xóa dưới tiền tố tệp người dùng của bucket nạp; SSM chỉ một tham số', () => {
    const { t } = ledgerStack();
    const s3 = statementsOf(t, 's3:');
    const list = s3.find((s) => s.Action === 's3:ListBucket');
    const del = s3.find((s) => s.Action === 's3:DeleteObject');
    assert.deepEqual(list.Condition, { StringLike: { 's3:prefix': ['u/*'] } });
    assert.ok(JSON.stringify(list.Resource).endsWith('s3:::yofina-ingest-111111111111-ap-southeast-1"]]}'));
    assert.match(JSON.stringify(del.Resource), /yofina-ingest-111111111111-ap-southeast-1\/u\/\*/);
    assert.ok(!s3.some((s) => /GetObject|PutObject/.test(JSON.stringify(s.Action))));
    const ssm = statementsOf(t, 'ssm:');
    assert.equal(ssm.length, 1);
    assert.match(JSON.stringify(ssm[0].Resource), /parameter\/yofina\/memory\/id/);
    const env = (Object.values(t.findResources('AWS::Lambda::Function'))[0] as any).Properties.Environment.Variables;
    assert.equal(env.YOFINA_MEMORY_ID_PARAM, '/yofina/memory/id');
    assert.equal(env.YOFINA_INGEST_UPLOAD_PREFIX, 'u/');
    assert.equal(env.YOFINA_INGEST_BUCKET, 'yofina-ingest-111111111111-ap-southeast-1');
  });

  it('route REST quyền riêng tư đủ năm thao tác của hợp đồng', () => {
    const keys = PRIVACY_ROUTES.map(([p, m]) => `${m} ${p}`).sort();
    assert.deepEqual(keys, [
      'DELETE /memory',
      'DELETE /memory/{record_id}',
      'GET /memory',
      'POST /me/delete-data',
      'POST /me/delete-data/confirmations',
    ]);
  });
});
