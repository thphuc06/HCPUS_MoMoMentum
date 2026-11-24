// Test template của ForecastPipeline, phần phase 5 luồng B (quyền model nhỏ cho bước hồ sơ hành vi của batch đêm):
// `npm test` (node:test + tsx, không cần AWS, không cần zip thật).
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
import { ForecastPipeline, loadForecastConfig } from '../lib/forecast-pipeline';

const ENV = { account: '111111111111', region: 'ap-southeast-1' }; // account giả của test
const CLUSTER = 'arn:aws:rds:ap-southeast-1:111111111111:cluster:yofina-test';
const APP_SECRET = 'arn:aws:secretsmanager:ap-southeast-1:111111111111:secret:yofina-app-AbCdEf';

const LLM_DEFAULTS = {
  roles: {
    small: {
      daily_cap: 10,
      models: [
        { id: 'global.amazon.nova-2-lite-v1:0', rpm: 18 },
        { id: 'global.anthropic.claude-haiku-4-5-20251001-v1:0', rpm: 8 },
      ],
    },
    planner: { daily_cap: 1, models: [{ id: 'global.anthropic.claude-sonnet-4-6', rpm: 8 }] },
  },
};

type Res = { Type: string; Properties: Record<string, any> };
const asList = <T>(v: T | T[]): T[] => (Array.isArray(v) ? v : [v]);

describe('ForecastPipeline (phase 5: model nhỏ cho batch)', () => {
  let tmp: string;
  let zip: string;
  let llm: string;

  function build(context: Record<string, unknown>): { stack: Stack; template: Template } {
    const app = new App({ context: { forecastZip: zip, forecastLlmDefaults: llm, ...context } });
    const s = new Stack(app, 'TestStack', { env: ENV });
    new ForecastPipeline(s, 'Forecast', {
      cfg: loadConfig(app),
      forecast: loadForecastConfig(app),
      bus: events.EventBus.fromEventBusName(s, 'Bus', 'yofina-bus'),
      alertTopic: new sns.Topic(s, 'Alerts'),
      appTimezone: 'Asia/Ho_Chi_Minh',
      freshnessSeconds: 3600,
      clusterArn: CLUSTER,
      appSecretArn: APP_SECRET,
      dbName: 'yofina',
      dbResumeMaxWaitSeconds: 20,
      region: ENV.region,
    });
    return { stack: s, template: Template.fromStack(s) };
  }

  /** Câu lệnh IAM gắn vào vai của Lambda có tên `name`. */
  function statementsOf(template: Template, name: string): any[] {
    const fns = template.findResources('AWS::Lambda::Function', { Properties: { FunctionName: name } }) as Record<string, Res>;
    const fn = Object.values(fns)[0];
    assert.ok(fn, `không có Lambda ${name}`);
    const roleId = fn.Properties.Role['Fn::GetAtt'][0];
    const policies = template.findResources('AWS::IAM::Policy') as Record<string, Res>;
    return Object.values(policies)
      .filter((p) => asList(p.Properties.Roles).some((r: any) => r.Ref === roleId))
      .flatMap((p) => asList(p.Properties.PolicyDocument.Statement));
  }

  before(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yofina-forecast-test-'));
    zip = path.join(tmp, 'forecast-arm64.zip');
    fs.writeFileSync(zip, Buffer.from([0x50, 0x4b, 0x05, 0x06, ...new Array(18).fill(0)]));
    llm = path.join(tmp, 'llm_defaults.json');
    fs.writeFileSync(llm, JSON.stringify(LLM_DEFAULTS));
  });

  after(() => fs.rmSync(tmp, { recursive: true, force: true }));

  it('batch: InvokeModel chỉ cho model của vai small, không ký tự thay thế, không vai planner', () => {
    const { template } = build({});
    const bedrock = statementsOf(template, 'yofina-forecast-batch').filter((s) =>
      asList(s.Action).some((a: string) => a.startsWith('bedrock:')),
    );
    assert.ok(bedrock.length >= 5); // profile + 2 x (foundation model ở Region gọi, không Region) cho 2 model
    for (const s of bedrock) {
      assert.deepEqual(asList(s.Action), ['bedrock:InvokeModel']);
      assert.ok(!JSON.stringify(s.Resource).includes('"*"'), 'Resource Bedrock không được là *');
    }
    const text = JSON.stringify(bedrock);
    assert.match(text, /inference-profile\/global\.amazon\.nova-2-lite-v1:0/);
    assert.match(text, /foundation-model\/anthropic\.claude-haiku-4-5/);
    assert.doesNotMatch(text, /claude-sonnet-4-6/);
  });

  it('batch: đếm lượt gọi model (UpdateItem trên bảng usage) và có YOFINA_USAGE_TABLE', () => {
    const { template } = build({});
    const count = statementsOf(template, 'yofina-forecast-batch').filter((s) => s.Sid === 'CountModelCalls');
    assert.equal(count.length, 1);
    assert.deepEqual(asList(count[0].Action), ['dynamodb:UpdateItem']);
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'yofina-forecast-batch',
      Environment: { Variables: Match.objectLike({ YOFINA_USAGE_TABLE: Match.anyValue() }) },
    });
  });

  it('tool và consumer sự kiện KHÔNG có quyền Bedrock hay bảng usage', () => {
    const { template } = build({});
    for (const name of ['yofina-forecast', 'yofina-on-transaction']) {
      const text = JSON.stringify(statementsOf(template, name));
      assert.doesNotMatch(text, /bedrock:/, name);
      assert.doesNotMatch(text, /CountModelCalls/, name);
    }
    const fns = template.findResources('AWS::Lambda::Function', { Properties: { FunctionName: 'yofina-forecast' } }) as Record<string, Res>;
    assert.equal(Object.values(fns)[0].Properties.Environment.Variables.YOFINA_USAGE_TABLE, undefined);
  });

  it('vai không có trong llm_defaults.json thì gắn lỗi vào construct', () => {
    const { stack } = build({ forecastBehaviorLlmRoles: 'small,khong_co' });
    const errors = Annotations.fromStack(stack).findError('*', Match.stringLikeRegexp('khong_co'));
    assert.equal(errors.length, 1);
  });
});
