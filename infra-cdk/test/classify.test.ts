// Test template của construct ClassifyPipeline (F2 phân hũ tự động): `npm test` (node:test + tsx, không cần AWS, không cần zip thật).
import { after, before, describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { App, Stack } from 'aws-cdk-lib';
import { Annotations, Match, Template } from 'aws-cdk-lib/assertions';
import * as events from 'aws-cdk-lib/aws-events';
import * as sns from 'aws-cdk-lib/aws-sns';
import { loadConfig } from '../config/config';
import { ClassifyPipeline, loadClassifyConfig } from '../lib/classify';

const ENV = { account: '111111111111', region: 'ap-southeast-1' }; // account giả của test
const CLUSTER = 'arn:aws:rds:ap-southeast-1:111111111111:cluster:yofina-test';
const APP_SECRET = 'arn:aws:secretsmanager:ap-southeast-1:111111111111:secret:yofina-app-AbCdEf';

// Biến môi trường mà mã Python đọc thật (yofina_core.config, db, llm; yofina_classify.settings; yofina_ledger.classify_config).
const REQUIRED_ENV = [
  'YOFINA_REGION',
  'YOFINA_LOG_LEVEL',
  'YOFINA_SSM_PREFIX',
  'YOFINA_DB_CLUSTER_ARN',
  'YOFINA_DB_APP_SECRET_ARN',
  'YOFINA_DB_NAME',
  'YOFINA_DB_RESUME_MAX_WAIT_SECONDS',
  'YOFINA_APP_TIMEZONE',
  'YOFINA_EVENT_BUS_NAME',
  'YOFINA_USAGE_TABLE',
  'YOFINA_CLASSIFY_IDEMPOTENCY_TABLE',
  'YOFINA_CLASSIFY_IDEMPOTENCY_TTL_SECONDS',
  'YOFINA_CLASSIFY_IDEMPOTENCY_LEASE_SECONDS',
  'YOFINA_CLASSIFY_MAX_RECEIVE_COUNT',
];

// llm_defaults.json giả: vai small (một model global + một model theo Region) và embedding (Cohere theo Region)
const LLM_DEFAULTS = {
  roles: {
    small: {
      daily_cap: 10,
      models: [
        { id: 'global.amazon.nova-2-lite-v1:0', rpm: 18 },
        { id: 'global.anthropic.claude-haiku-4-5-20251001-v1:0', rpm: 8 },
      ],
    },
    embedding: { daily_cap: 10, models: [{ id: 'cohere.embed-multilingual-v3', rpm: 18 }] },
    planner: { daily_cap: 1, models: [{ id: 'global.anthropic.claude-sonnet-4-6', rpm: 8 }] },
  },
};

type Res = { Type: string; Properties: Record<string, any> };
const asList = <T>(v: T | T[]): T[] => (Array.isArray(v) ? v : [v]);

describe('ClassifyPipeline', () => {
  let tmp: string;
  let template: Template;
  let statements: any[];

  function build(context: Record<string, unknown>): { stack: Stack; template: Template } {
    const app = new App({ context });
    const cfg = loadConfig(app);
    const s = new Stack(app, 'TestStack', { env: ENV });
    const bus = events.EventBus.fromEventBusName(s, 'Bus', 'yofina-bus');
    const topic = new sns.Topic(s, 'Alerts');
    new ClassifyPipeline(s, 'Classify', {
      cfg,
      classify: loadClassifyConfig(app),
      bus,
      alertTopic: topic,
      appTimezone: 'Asia/Ho_Chi_Minh',
      clusterArn: CLUSTER,
      appSecretArn: APP_SECRET,
      dbName: 'yofina',
      dbResumeMaxWaitSeconds: 20,
      usageTableName: 'yofina-usage',
    });
    return { stack: s, template: Template.fromStack(s) };
  }

  before(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yofina-classify-test-'));
    const zip = path.join(tmp, 'classify-arm64.zip');
    // zip rỗng hợp lệ (chỉ bản ghi end-of-central-directory): đủ cho Code.fromAsset, không lên AWS
    fs.writeFileSync(zip, Buffer.from([0x50, 0x4b, 0x05, 0x06, ...new Array(18).fill(0)]));
    const llm = path.join(tmp, 'llm_defaults.json');
    fs.writeFileSync(llm, JSON.stringify(LLM_DEFAULTS));
    ({ template } = build({
      classifyZip: zip,
      classifyLlmDefaults: llm,
      classifyThresholds: JSON.stringify({ auto_min_confidence: 0.93 }),
    }));
    const policies = template.findResources('AWS::IAM::Policy') as Record<string, Res>;
    statements = Object.values(policies).flatMap((p) => asList(p.Properties.PolicyDocument.Statement));
  });

  after(() => fs.rmSync(tmp, { recursive: true, force: true }));

  it('Lambda: Python 3.13 arm64, handler ở gốc zip, ngoài VPC, timeout và bộ nhớ từ cấu hình', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'yofina-classify',
      Runtime: 'python3.13',
      Architectures: ['arm64'],
      Handler: 'handler_classify.lambda_handler',
      MemorySize: 512,
      Timeout: 90,
    });
    const fns = template.findResources('AWS::Lambda::Function') as Record<string, Res>;
    for (const f of Object.values(fns)) assert.equal(f.Properties.VpcConfig, undefined);
  });

  it('biến môi trường: đủ khóa mà mã Python đọc, ngưỡng ghi đè qua YOFINA_CLASSIFY_<TÊN>', () => {
    const fn = Object.values(template.findResources('AWS::Lambda::Function') as Record<string, Res>)[0];
    const env = fn.Properties.Environment.Variables as Record<string, unknown>;
    for (const k of REQUIRED_ENV) assert.ok(k in env, `thiếu ${k}`);
    assert.equal(env.YOFINA_CLASSIFY_AUTO_MIN_CONFIDENCE, '0.93');
    assert.equal(env.YOFINA_USAGE_TABLE, 'yofina-usage');
    assert.equal(env.YOFINA_APP_TIMEZONE, 'Asia/Ho_Chi_Minh');
    // khóa thuê idempotency dài hơn timeout của hàm
    assert.ok(Number(env.YOFINA_CLASSIFY_IDEMPOTENCY_LEASE_SECONDS) > 90);
  });

  it('rule EventBridge chỉ nhận transaction.recorded cần phân loại của ledger, đích là SQS', () => {
    template.hasResourceProperties('AWS::Events::Rule', {
      EventBusName: 'yofina-bus',
      EventPattern: {
        source: ['yofina.ledger'],
        'detail-type': ['transaction.recorded'],
        detail: { needs_classification: [true] },
      },
      Targets: [Match.objectLike({ Arn: Match.anyValue() })],
    });
  });

  it('SQS có DLQ (redrive 3 lần), visibility timeout từ 6 lần timeout của hàm, mã hóa SQS, bắt buộc TLS', () => {
    template.hasResourceProperties('AWS::SQS::Queue', {
      QueueName: 'yofina-classify-events',
      VisibilityTimeout: 540,
      SqsManagedSseEnabled: true,
      RedrivePolicy: Match.objectLike({ maxReceiveCount: 3 }),
    });
    template.hasResourceProperties('AWS::SQS::Queue', { QueueName: 'yofina-classify-events-dlq', MessageRetentionPeriod: 1209600 });
    template.hasResourceProperties('AWS::SQS::QueuePolicy', {
      PolicyDocument: {
        Statement: Match.arrayWith([Match.objectLike({ Effect: 'Deny', Condition: { Bool: { 'aws:SecureTransport': 'false' } } })]),
      },
    });
  });

  it('event source mapping: partial batch response, giới hạn đồng thời, lô nhỏ', () => {
    template.hasResourceProperties('AWS::Lambda::EventSourceMapping', {
      FunctionResponseTypes: ['ReportBatchItemFailures'],
      BatchSize: 5,
      ScalingConfig: { MaximumConcurrency: 3 },
    });
  });

  it('bảng idempotency riêng: khóa event_id, TTL, theo yêu cầu', () => {
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      TableName: 'yofina-classify-idempotency',
      KeySchema: [{ AttributeName: 'event_id', KeyType: 'HASH' }],
      TimeToLiveSpecification: { AttributeName: 'ttl', Enabled: true },
      BillingMode: 'PAY_PER_REQUEST',
    });
  });

  it('IAM Bedrock: InvokeModel chỉ cho model của vai small và embedding, KHÔNG dùng ký tự thay thế', () => {
    const bedrock = statements.filter((s) => asList(s.Action).some((a: string) => a.startsWith('bedrock:')));
    assert.ok(bedrock.length >= 4);
    for (const s of bedrock) {
      assert.deepEqual(asList(s.Action), ['bedrock:InvokeModel']);
      assert.ok(!JSON.stringify(s.Resource).includes('"*"'), 'Resource Bedrock không được là *');
    }
    const text = JSON.stringify(bedrock);
    assert.match(text, /foundation-model\/cohere\.embed-multilingual-v3/); // embedding theo Region, gọi thẳng
    assert.match(text, /inference-profile\/global\.amazon\.nova-2-lite-v1:0/); // model nhỏ qua profile global
    assert.doesNotMatch(text, /claude-sonnet-4-6/); // vai planner KHÔNG được cấp
  });

  it('IAM Data API và secret: chỉ secret của role yofina_app, không secret master', () => {
    const secret = statements.filter((s) => asList(s.Action).includes('secretsmanager:GetSecretValue'));
    assert.equal(secret.length, 1);
    assert.deepEqual(asList(secret[0].Resource), [APP_SECRET]);
    const data = statements.filter((s) => asList(s.Action).includes('rds-data:ExecuteStatement'));
    assert.equal(data.length, 1);
    assert.deepEqual(asList(data[0].Resource), [CLUSTER]);
  });

  it('IAM: phát sự kiện lên bus, đếm lượt gọi model, đọc cấu hình llm', () => {
    assert.ok(statements.some((s) => asList(s.Action).includes('events:PutEvents')));
    const count = statements.find((s) => s.Sid === 'CountModelCalls');
    assert.deepEqual(asList(count.Action), ['dynamodb:UpdateItem']);
    assert.match(JSON.stringify(count.Resource), /table\/yofina-usage/);
    const cfg = statements.find((s) => s.Sid === 'ReadConfig');
    assert.ok(asList(cfg.Action).includes('ssm:GetParametersByPath'));
  });

  it('alarm khi DLQ có tin nhắn', () => {
    template.hasResourceProperties('AWS::CloudWatch::Alarm', {
      AlarmName: 'yofina-classify-events-dlq-not-empty',
      Threshold: 1,
      ComparisonOperator: 'GreaterThanOrEqualToThreshold',
    });
  });

  it('thiếu zip thì stack báo lỗi (không đưa mã thay thế lên AWS)', () => {
    const { stack: s } = build({ classifyZip: path.join(tmp, 'khong-co.zip'), classifyLlmDefaults: path.join(tmp, 'llm_defaults.json') });
    const errors = Annotations.fromStack(s).findError('*', Match.stringLikeRegexp('Chưa có .*khong-co\\.zip'));
    assert.equal(errors.length, 1);
  });

  it('vai model thiếu trong llm_defaults.json thì stack báo lỗi', () => {
    const { stack: s } = build({
      classifyZip: path.join(tmp, 'classify-arm64.zip'),
      classifyLlmDefaults: path.join(tmp, 'llm_defaults.json'),
      classifyLlmRoles: 'small,khong_co_vai_nay',
    });
    assert.equal(Annotations.fromStack(s).findError('*', Match.stringLikeRegexp("không có vai 'khong_co_vai_nay'")).length, 1);
  });
});
