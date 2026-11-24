// Test template của construct OpsDashboard (phase 5 luồng D): `npm test` (node:test + tsx, không cần AWS).
import { before, describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { App, Stack } from 'aws-cdk-lib';
import { Match, Template } from 'aws-cdk-lib/assertions';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sns from 'aws-cdk-lib/aws-sns';
import { loadConfig } from '../config/config';
import { loadOpsDashboardConfig, modelCaps, OpsDashboard } from '../lib/ops-dashboard';

const ENV = { account: '111111111111', region: 'ap-southeast-1' }; // account giả của test

// llm_defaults.json giả: một model ở hai vai với trần khác nhau (lấy trần lớn nhất), một model có trần riêng.
const LLM_DEFAULTS = {
  roles: {
    planner: { daily_cap: 400, models: [{ id: 'global.anthropic.claude-sonnet-4-6' }, { id: 'global.moonshotai.kimi-k3' }] },
    ingest: { daily_cap: 300, models: [{ id: 'global.anthropic.claude-sonnet-4-6' }] },
    embedding: { daily_cap: 3000, models: [{ id: 'cohere.embed-multilingual-v3', daily_cap: 50 }] },
  },
};

type Res = { Type: string; Properties: Record<string, any> };

describe('OpsDashboard', () => {
  let llmFile: string;
  let template: Template;

  function build(context: Record<string, unknown>): Template {
    const app = new App({ context: { opsLlmDefaults: llmFile, ...context } });
    const cfg = loadConfig(app);
    const s = new Stack(app, 'TestStack', { env: ENV });
    const ledger = new lambda.Function(s, 'Ledger', {
      functionName: 'yofina-ledger',
      runtime: lambda.Runtime.PYTHON_3_13,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromInline('def lambda_handler(e, c): return {}'),
    });
    new OpsDashboard(s, 'Ops', {
      cfg,
      ops: loadOpsDashboardConfig(app),
      alertTopic: new sns.Topic(s, 'Alerts'),
      ledger,
      usageTableName: 'yofina-usage',
      apiId: 'abc123',
    });
    return Template.fromStack(s);
  }

  before(() => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yofina-ops-test-'));
    llmFile = path.join(tmp, 'llm_defaults.json');
    fs.writeFileSync(llmFile, JSON.stringify(LLM_DEFAULTS));
    template = build({});
  });

  it('trần theo model: lớn nhất giữa các vai, trần riêng của model thắng trần của vai', () => {
    assert.deepEqual(
      [...modelCaps(llmFile).entries()],
      [
        ['global.anthropic.claude-sonnet-4-6', 400],
        ['global.moonshotai.kimi-k3', 400],
        ['cohere.embed-multilingual-v3', 50],
      ],
    );
  });

  it('dashboard yofina-ops có đủ nhóm metric yêu cầu', () => {
    const dashboards = template.findResources('AWS::CloudWatch::Dashboard') as Record<string, Res>;
    const [d] = Object.values(dashboards);
    assert.equal(d.Properties.DashboardName, 'yofina-ops');
    const body = JSON.stringify(d.Properties.DashboardBody);
    for (const needle of [
      'AWS/Lambda',
      'Duration',
      'yofina-ledger',
      'yofina-forecast',
      'Errors',
      'yofina-ingest',
      'ApproximateNumberOfMessagesVisible',
      'yofina-forecast-events-dlq',
      'yofina-classify-events-dlq',
      'yofina-roadmap-events-dlq',
      'yofina-ingest-jobs-dlq',
      'AllowDecisions',
      'DenyDecisions',
      'yofina_policy_engine',
      'ServerlessDatabaseCapacity',
      'yofina-db',
      'AWS/Bedrock',
      'Invocations',
      'global.anthropic.claude-sonnet-4-6',
      'cohere.embed-multilingual-v3',
      'AWS/ApiGateway',
    ]) {
      assert.ok(body.includes(needle), `dashboard thiếu ${needle}`);
    }
  });

  it('alarm đều gửi về topic SNS sẵn có, đúng ngưỡng', () => {
    const alarms = Object.values(template.findResources('AWS::CloudWatch::Alarm') as Record<string, Res>);
    const names = alarms.map((a) => a.Properties.AlarmName).sort();
    assert.deepEqual(names, [
      'yofina-ops-aurora-acu-at-max',
      'yofina-ops-ledger-p95-latency',
      'yofina-ops-model-calls-cohere-embed-multilingual-v3',
      'yofina-ops-model-calls-global-anthropic-claude-sonnet-4-6',
      'yofina-ops-model-calls-global-moonshotai-kimi-k3',
      'yofina-ops-tool-lambda-errors',
    ]);
    for (const a of alarms) {
      assert.equal(a.Properties.AlarmActions.length, 1);
      assert.match(JSON.stringify(a.Properties.AlarmActions[0]), /Alerts/);
      assert.equal(a.Properties.TreatMissingData, 'notBreaching');
    }
    const byName = Object.fromEntries(alarms.map((a) => [a.Properties.AlarmName, a.Properties]));
    // metric có label thì CDK ghi alarm dạng `Metrics` (MetricStat) thay vì Period/Statistic ở cấp trên
    const stat = (p: Record<string, any>) => p.Metrics?.[0]?.MetricStat ?? { Period: p.Period, Stat: p.ExtendedStatistic ?? p.Statistic };
    const sonnet = byName['yofina-ops-model-calls-global-anthropic-claude-sonnet-4-6'];
    assert.equal(sonnet.Threshold, 320); // 80% của 400
    assert.equal(stat(sonnet).Period, 86400);
    assert.equal(byName['yofina-ops-ledger-p95-latency'].Threshold, 10000);
    assert.equal(stat(byName['yofina-ops-ledger-p95-latency']).Stat, 'p95');
    assert.equal(byName['yofina-ops-aurora-acu-at-max'].EvaluationPeriods, 6);
  });

  it('ledger chỉ được Query bảng yofina-usage và biết tên bảng', () => {
    template.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Sid: 'OpsReadModelUsage',
            Action: 'dynamodb:Query',
            Effect: 'Allow',
          }),
        ]),
      },
    });
    const policies = JSON.stringify(template.findResources('AWS::IAM::Policy'));
    assert.match(policies, /table\/yofina-usage/);
    for (const forbidden of ['dynamodb:PutItem', 'dynamodb:UpdateItem', 'dynamodb:Scan', 'dynamodb:DeleteItem']) {
      assert.ok(!policies.includes(forbidden), `không được cấp ${forbidden}`);
    }
    const fn = Object.values(template.findResources('AWS::Lambda::Function') as Record<string, Res>)[0];
    assert.equal(fn.Properties.Environment.Variables.YOFINA_USAGE_TABLE, 'yofina-usage');
  });

  it('không bật Transaction Search hay span (không tài nguyên X-Ray, không resource policy của Logs)', () => {
    const types = Object.values(template.toJSON().Resources as Record<string, Res>).map((r) => r.Type);
    assert.ok(!types.some((t) => t.startsWith('AWS::XRay::')));
    assert.ok(!types.includes('AWS::Logs::ResourcePolicy'));
  });

  it('tắt được alarm gần trần và ACU bằng context', () => {
    const t = build({ opsModelCapAlarmPercent: 0, opsAcuAtMaxAlarmMinutes: 0 });
    const names = Object.values(t.findResources('AWS::CloudWatch::Alarm') as Record<string, Res>).map(
      (a) => a.Properties.AlarmName,
    );
    assert.deepEqual(names.sort(), ['yofina-ops-ledger-p95-latency', 'yofina-ops-tool-lambda-errors']);
    assert.throws(() => build({ opsAcuAtMaxAlarmMinutes: 7 }), /bội của 5/);
  });
});
