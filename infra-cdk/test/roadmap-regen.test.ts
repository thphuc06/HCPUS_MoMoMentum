// Test template của construct RoadmapRegen (F5 sinh lại lộ trình chạy nền): `npm test` (node:test + tsx, không cần AWS, không cần zip thật).
import { after, before, describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { App, Stack } from 'aws-cdk-lib';
import { Annotations, Match, Template } from 'aws-cdk-lib/assertions';
import * as events from 'aws-cdk-lib/aws-events';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sns from 'aws-cdk-lib/aws-sns';
import { loadConfig } from '../config/config';
import { loadRoadmapRegenConfig, RoadmapRegen } from '../lib/roadmap-regen';

const ENV = { account: '111111111111', region: 'ap-southeast-1' }; // account giả của test
const CLUSTER = 'arn:aws:rds:ap-southeast-1:111111111111:cluster:yofina-test';
const APP_SECRET = 'arn:aws:secretsmanager:ap-southeast-1:111111111111:secret:yofina-app-AbCdEf';
const LEDGER_ARN = 'arn:aws:lambda:ap-southeast-1:111111111111:function:yofina-ledger';
const FORECAST_TOOL_ARN = 'arn:aws:lambda:ap-southeast-1:111111111111:function:yofina-forecast';

// Biến môi trường mà mã Python đọc thật (yofina_roadmap.settings, yofina_core.config/db/llm).
const REQUIRED_ENV = [
  'YOFINA_REGION',
  'YOFINA_SSM_PREFIX',
  'YOFINA_DB_CLUSTER_ARN',
  'YOFINA_DB_APP_SECRET_ARN',
  'YOFINA_DB_NAME',
  'YOFINA_DB_RESUME_MAX_WAIT_SECONDS',
  'YOFINA_EVENT_BUS_NAME',
  'YOFINA_USAGE_TABLE',
  'YOFINA_ROADMAP_LEDGER_FUNCTION_NAME',
  'YOFINA_ROADMAP_FORECAST_FUNCTION_NAME',
  'YOFINA_ROADMAP_INVOKE_CONNECT_TIMEOUT_SECONDS',
  'YOFINA_ROADMAP_INVOKE_READ_TIMEOUT_SECONDS',
  'YOFINA_ROADMAP_RUNNING_LEASE_SECONDS',
  'YOFINA_ROADMAP_STAGE_PROGRESS',
];

// llm_defaults.json giả: planner có một model global và một model theo Region; small không được cấp.
const LLM_DEFAULTS = {
  roles: {
    planner: {
      daily_cap: 10,
      models: [
        { id: 'global.anthropic.claude-sonnet-4-6', rpm: 8 },
        { id: 'global.moonshotai.kimi-k3', rpm: 8 },
      ],
    },
    small: { daily_cap: 10, models: [{ id: 'global.amazon.nova-2-lite-v1:0', rpm: 18 }] },
    embedding: { daily_cap: 10, models: [{ id: 'cohere.embed-multilingual-v3', rpm: 18 }] },
  },
};

type Res = { Type: string; Properties: Record<string, any> };
const asList = <T>(v: T | T[]): T[] => (Array.isArray(v) ? v : [v]);

describe('RoadmapRegen', () => {
  let tmp: string;
  let zip: string;
  let llmFile: string;
  let template: Template;
  let statements: any[];

  function build(context: Record<string, unknown>): { stack: Stack; template: Template } {
    const app = new App({ context });
    const cfg = loadConfig(app);
    const s = new Stack(app, 'TestStack', { env: ENV });
    new RoadmapRegen(s, 'Roadmap', {
      cfg,
      roadmap: loadRoadmapRegenConfig(app),
      bus: events.EventBus.fromEventBusName(s, 'Bus', 'yofina-bus'),
      alertTopic: new sns.Topic(s, 'Alerts'),
      ledgerFunction: lambda.Function.fromFunctionArn(s, 'Ledger', LEDGER_ARN),
      ledgerTimeoutSeconds: 30,
      forecastToolFunction: lambda.Function.fromFunctionArn(s, 'ForecastTool', FORECAST_TOOL_ARN),
      forecastToolTimeoutSeconds: 60,
      appTimezone: 'Asia/Ho_Chi_Minh',
      clusterArn: CLUSTER,
      appSecretArn: APP_SECRET,
      dbName: 'yofina',
      dbResumeMaxWaitSeconds: 18,
      usageTableName: 'yofina-usage',
    });
    return { stack: s, template: Template.fromStack(s) };
  }

  const fnEnv = (t: Template) =>
    Object.values(t.findResources('AWS::Lambda::Function') as Record<string, Res>)[0].Properties.Environment.Variables as Record<
      string,
      any
    >;

  before(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yofina-roadmap-test-'));
    zip = path.join(tmp, 'roadmap-arm64.zip');
    // zip rỗng hợp lệ (chỉ bản ghi end-of-central-directory): đủ cho Code.fromAsset, không lên AWS
    fs.writeFileSync(zip, Buffer.from([0x50, 0x4b, 0x05, 0x06, ...new Array(18).fill(0)]));
    llmFile = path.join(tmp, 'llm_defaults.json');
    fs.writeFileSync(llmFile, JSON.stringify(LLM_DEFAULTS));
    ({ template } = build({ roadmapZip: zip, roadmapLlmDefaults: llmFile }));
    const policies = template.findResources('AWS::IAM::Policy') as Record<string, Res>;
    statements = Object.values(policies).flatMap((p) => asList(p.Properties.PolicyDocument.Statement));
  });

  after(() => fs.rmSync(tmp, { recursive: true, force: true }));

  it('Lambda: Python 3.13 arm64, handler.lambda_handler, ngoài VPC, timeout 300 s', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'yofina-roadmap-regen',
      Runtime: 'python3.13',
      Architectures: ['arm64'],
      Handler: 'handler.lambda_handler',
      Timeout: 300,
    });
    const fns = template.findResources('AWS::Lambda::Function') as Record<string, Res>;
    assert.equal(Object.keys(fns).length, 1);
    for (const f of Object.values(fns)) assert.equal(f.Properties.VpcConfig, undefined);
  });

  it('biến môi trường: đủ khóa settings.py đọc, ledger và forecast TOOL đúng hàm, mốc tiến độ hợp lệ', () => {
    const env = fnEnv(template);
    for (const k of REQUIRED_ENV) assert.ok(k in env, `thiếu ${k}`);
    assert.equal(env.YOFINA_ROADMAP_LEDGER_FUNCTION_NAME, 'yofina-ledger');
    assert.equal(env.YOFINA_ROADMAP_FORECAST_FUNCTION_NAME, 'yofina-forecast'); // hàm tool, không phải yofina-forecast-batch
    assert.equal(env.YOFINA_EVENT_BUS_NAME, 'yofina-bus');
    assert.equal(env.YOFINA_USAGE_TABLE, 'yofina-usage');
    assert.equal(env.YOFINA_ROADMAP_STAGE_PROGRESS, '5,25,45,65,85');
    // đọc Invoke chờ hết timeout lớn nhất của hai Lambda tool (60 s) cộng biên, và vẫn nhỏ hơn timeout của hàm
    const read = Number(env.YOFINA_ROADMAP_INVOKE_READ_TIMEOUT_SECONDS);
    assert.ok(read > 60 && read < 300, `read timeout ${read}`);
  });

  it('thời gian: visibility timeout > lease > timeout Lambda', () => {
    const fn = Object.values(template.findResources('AWS::Lambda::Function') as Record<string, Res>)[0];
    const timeout = Number(fn.Properties.Timeout);
    const lease = Number(fnEnv(template).YOFINA_ROADMAP_RUNNING_LEASE_SECONDS);
    const queues = template.findResources('AWS::SQS::Queue', { Properties: { QueueName: 'yofina-roadmap-events' } }) as Record<
      string,
      Res
    >;
    const visibility = Number(Object.values(queues)[0].Properties.VisibilityTimeout);
    assert.ok(lease > timeout, `lease ${lease} <= timeout ${timeout}`);
    assert.ok(visibility > lease, `visibility ${visibility} <= lease ${lease}`);
    assert.equal(visibility, timeout * 6);
  });

  it('ba rule trên yofina-bus lọc cả source và detail-type, đích SQS, gửi nguyên phong bì', () => {
    const rules = template.findResources('AWS::Events::Rule') as Record<string, Res>;
    const patterns = Object.values(rules).map((r) => r.Properties.EventPattern);
    assert.equal(patterns.length, 3);
    const expected = [
      { source: ['yofina.ledger'], 'detail-type': ['roadmap.regeneration_requested'] },
      { source: ['yofina.forecast'], 'detail-type': ['behavior.changed'] },
      { source: ['yofina.ledger'], 'detail-type': ['profile.updated'] },
    ];
    for (const e of expected) assert.ok(patterns.some((p) => JSON.stringify(p) === JSON.stringify(e)), `thiếu rule ${JSON.stringify(e)}`);
    for (const r of Object.values(rules)) {
      assert.equal(r.Properties.EventBusName, 'yofina-bus');
      const tgts = r.Properties.Targets as any[];
      assert.equal(tgts.length, 1);
      assert.match(JSON.stringify(tgts[0].Arn), /Events[A-Z0-9]*"/); // hàng đợi yofina-roadmap-events
      for (const k of ['Input', 'InputPath', 'InputTransformer']) assert.equal(tgts[0][k], undefined, `đích không được có ${k}`);
    }
  });

  it('queue policy cho events.amazonaws.com theo ARN từng rule, bắt buộc TLS', () => {
    const policies = template.findResources('AWS::SQS::QueuePolicy') as Record<string, Res>;
    const sts = Object.values(policies).flatMap((p) => asList(p.Properties.PolicyDocument.Statement));
    const fromEvents = sts.filter((s) => s.Principal?.Service === 'events.amazonaws.com');
    assert.equal(fromEvents.length, 3);
    for (const s of fromEvents) {
      assert.ok(asList(s.Action).includes('sqs:SendMessage'));
      assert.ok(s.Condition?.ArnEquals?.['aws:SourceArn'], 'thiếu điều kiện aws:SourceArn');
    }
    assert.ok(sts.some((s) => s.Effect === 'Deny' && s.Condition?.Bool?.['aws:SecureTransport'] === 'false'));
  });

  it('SQS có DLQ đủ lượt giao lại cho JobBusy, mã hóa SQS', () => {
    template.hasResourceProperties('AWS::SQS::Queue', {
      QueueName: 'yofina-roadmap-events',
      SqsManagedSseEnabled: true,
      RedrivePolicy: Match.objectLike({ maxReceiveCount: Match.anyValue() }),
    });
    const q = Object.values(
      template.findResources('AWS::SQS::Queue', { Properties: { QueueName: 'yofina-roadmap-events' } }) as Record<string, Res>,
    )[0];
    assert.ok(q.Properties.RedrivePolicy.maxReceiveCount >= 5);
    template.hasResourceProperties('AWS::SQS::Queue', { QueueName: 'yofina-roadmap-events-dlq', MessageRetentionPeriod: 1209600 });
  });

  it('event source mapping: lô 1, ReportBatchItemFailures, đồng thời tối đa 2', () => {
    template.hasResourceProperties('AWS::Lambda::EventSourceMapping', {
      BatchSize: 1,
      FunctionResponseTypes: ['ReportBatchItemFailures'],
      ScalingConfig: { MaximumConcurrency: 2 },
    });
  });

  it('IAM lambda:InvokeFunction chỉ cho đúng hai hàm ledger và forecast tool', () => {
    const invoke = statements.filter((s) => asList(s.Action).some((a: string) => a.startsWith('lambda:')));
    assert.equal(invoke.length, 1);
    assert.deepEqual(asList(invoke[0].Action), ['lambda:InvokeFunction']);
    assert.deepEqual(asList(invoke[0].Resource).sort(), [FORECAST_TOOL_ARN, LEDGER_ARN].sort());
  });

  it('IAM Bedrock: mẫu 3 phần global cho model của vai planner, không vai khác, không ký tự thay thế', () => {
    const bedrock = statements.filter((s) => asList(s.Action).some((a: string) => a.startsWith('bedrock:')));
    // 2 model global: 1 statement profile + 2 statement foundation-model mỗi model
    assert.equal(bedrock.length, 5);
    for (const s of bedrock) {
      assert.deepEqual(asList(s.Action), ['bedrock:InvokeModel']);
      assert.ok(!JSON.stringify(s.Resource).includes('*'), 'Resource Bedrock không được có *');
    }
    const text = JSON.stringify(bedrock);
    for (const base of ['anthropic.claude-sonnet-4-6', 'moonshotai.kimi-k3']) {
      assert.ok(text.includes(`inference-profile/global.${base}`), `thiếu profile ${base}`);
      assert.ok(text.includes(`arn:aws:bedrock:ap-southeast-1::foundation-model/${base}`), `thiếu FM theo Region ${base}`);
      assert.ok(text.includes(`arn:aws:bedrock:::foundation-model/${base}`), `thiếu FM toàn cầu ${base}`);
    }
    const global = bedrock.filter((s) => JSON.stringify(s.Resource).includes('arn:aws:bedrock:::foundation-model/'));
    for (const s of global) {
      assert.equal(s.Condition.StringEquals['aws:RequestedRegion'], 'unspecified');
      assert.ok(s.Condition.StringEquals['bedrock:InferenceProfileArn']);
    }
    assert.doesNotMatch(text, /nova-2-lite|cohere/); // vai small, embedding không được cấp
  });

  it('IAM Data API, secret app, bảng usage, SSM; KHÔNG có PutEvents (Lambda không phát sự kiện)', () => {
    const data = statements.filter((s) => asList(s.Action).includes('rds-data:ExecuteStatement'));
    assert.equal(data.length, 1);
    assert.deepEqual(asList(data[0].Action).sort(), [
      'rds-data:BeginTransaction',
      'rds-data:CommitTransaction',
      'rds-data:ExecuteStatement',
      'rds-data:RollbackTransaction',
    ]);
    assert.deepEqual(asList(data[0].Resource), [CLUSTER]);
    const secret = statements.filter((s) => asList(s.Action).includes('secretsmanager:GetSecretValue'));
    assert.equal(secret.length, 1);
    assert.deepEqual(asList(secret[0].Resource), [APP_SECRET]);
    const count = statements.find((s) => s.Sid === 'CountModelCalls');
    assert.deepEqual(asList(count.Action), ['dynamodb:UpdateItem']);
    assert.match(JSON.stringify(count.Resource), /table\/yofina-usage/);
    const cfg = statements.find((s) => s.Sid === 'ReadConfig');
    assert.ok(asList(cfg.Action).includes('ssm:GetParameter'));
    assert.ok(!statements.some((s) => asList(s.Action).includes('events:PutEvents')));
  });

  it('alarm khi DLQ có tin nhắn', () => {
    template.hasResourceProperties('AWS::CloudWatch::Alarm', {
      AlarmName: 'yofina-roadmap-events-dlq-not-empty',
      Threshold: 1,
      ComparisonOperator: 'GreaterThanOrEqualToThreshold',
      AlarmActions: Match.anyValue(),
    });
  });

  it('thiếu zip thì stack báo lỗi (không đưa mã thay thế lên AWS)', () => {
    const { stack: s } = build({ roadmapZip: path.join(tmp, 'khong-co.zip'), roadmapLlmDefaults: llmFile });
    assert.equal(Annotations.fromStack(s).findError('*', Match.stringLikeRegexp('Chưa có .*khong-co\\.zip')).length, 1);
  });

  it('cấu hình thời gian sai thứ tự thì từ chối lúc synth', () => {
    assert.throws(() => build({ roadmapZip: zip, roadmapLlmDefaults: llmFile, roadmapRunningLeaseSeconds: 300 }), /lớn hơn roadmapTimeoutSeconds/);
    assert.throws(
      () => build({ roadmapZip: zip, roadmapLlmDefaults: llmFile, roadmapVisibilityTimeoutSeconds: 360 }),
      /lớn hơn roadmapRunningLeaseSeconds/,
    );
    assert.throws(() => build({ roadmapZip: zip, roadmapLlmDefaults: llmFile, roadmapMaxConcurrency: 1 }), /2\.\.1000/);
    assert.throws(() => build({ roadmapZip: zip, roadmapLlmDefaults: llmFile, roadmapStageProgress: '5,25,25,65,85' }), /năm mốc/);
  });
});
