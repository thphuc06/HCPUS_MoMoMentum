// Test template của stack YofinaIngest: `npm test` (node:test + tsx, không cần AWS, không cần zip thật).
import { after, before, describe, it } from 'node:test';
import * as assert from 'node:assert/strict';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { App, Tags } from 'aws-cdk-lib';
import { Annotations, Match, Template } from 'aws-cdk-lib/assertions';
import { loadConfig } from '../config/config';
import { IngestStack, loadIngestConfig } from '../lib/ingest-stack';
import { loadToolsConfig } from '../lib/tools-stack';

const ENV = { account: '111111111111', region: 'ap-southeast-1' }; // account giả của test

// Biến môi trường mà mã ingest đọc thật (yofina_core.config, db, confirm, llm; yofina_ingest.settings).
const REQUIRED_ENV = [
  'YOFINA_REGION',
  'YOFINA_LOG_LEVEL',
  'YOFINA_SSM_PREFIX',
  'YOFINA_DB_CLUSTER_ARN',
  'YOFINA_DB_APP_SECRET_ARN',
  'YOFINA_DB_NAME',
  'YOFINA_DB_RESUME_MAX_WAIT_SECONDS',
  'YOFINA_INGEST_BUCKET',
  'YOFINA_INGEST_UPLOAD_PREFIX',
  'YOFINA_INGEST_MAX_RECEIVE_COUNT',
  'YOFINA_CONFIRM_HMAC_SECRET_ARN',
  'YOFINA_CONFIRM_JTI_TABLE',
  'YOFINA_CONFIRM_TOKEN_TTL_SECONDS',
  'YOFINA_CONFIRM_TOKEN_MAX_TTL_SECONDS',
  'YOFINA_CONFIRM_OFFER_TTL_SECONDS',
  'YOFINA_FORECAST_FUNCTION_NAME',
  'YOFINA_FORECAST_SYNC_TIMEOUT_SECONDS',
  'YOFINA_FORECAST_HISTORY_WINDOW_DAYS',
  'YOFINA_APP_TIMEZONE',
  'YOFINA_USAGE_TABLE',
];

// llm_defaults.json giả: có `ingest` (Sonnet 4.6 + Kimi K3), CHƯA có `ingest_columns`, thêm một model không global để kiểm nhánh
// gọi thẳng ở region.
const LLM_DEFAULTS = {
  roles: {
    ingest: {
      daily_cap: 300,
      models: [
        { id: 'global.anthropic.claude-sonnet-4-6', rpm: 8 },
        { id: 'global.moonshotai.kimi-k3', rpm: 8 },
      ],
    },
    regional_only: { daily_cap: 1, models: [{ id: 'amazon.titan-text-lite-v1', rpm: 1 }] },
    planner: { daily_cap: 1, models: [{ id: 'global.amazon.nova-2-lite-v1:0', rpm: 1 }] },
  },
};

let defaultContext: Record<string, unknown> = {};

function build(context: Record<string, unknown>): { stack: IngestStack; template: Template } {
  const app = new App({ context: { ...defaultContext, ...context } });
  const cfg = loadConfig(app);
  const stack = new IngestStack(app, 'YofinaIngest', {
    env: ENV,
    cfg,
    tools: loadToolsConfig(app),
    ingest: loadIngestConfig(app),
  });
  Tags.of(app).add('project', 'yofina'); // như bin/yofina.ts
  return { stack, template: Template.fromStack(stack) };
}

type Res = { Type: string; Properties: Record<string, any> };

function statementsOf(template: Template, roleLogicalPrefix: string): any[] {
  const policies = template.findResources('AWS::IAM::Policy') as Record<string, Res>;
  const out: any[] = [];
  for (const pol of Object.values(policies)) {
    const roles = JSON.stringify(pol.Properties.Roles);
    if (roles.includes(roleLogicalPrefix)) out.push(...pol.Properties.PolicyDocument.Statement);
  }
  return out;
}

const asList = <T>(v: T | T[]): T[] => (Array.isArray(v) ? v : [v]);

describe('YofinaIngest', () => {
  let tmp: string;
  let template: Template;
  let stack: IngestStack;

  before(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yofina-ingest-test-'));
    const zip = path.join(tmp, 'ingest-arm64.zip');
    // zip rỗng hợp lệ (chỉ bản ghi end-of-central-directory): đủ cho Code.fromAsset, không lên AWS
    fs.writeFileSync(zip, Buffer.from([0x50, 0x4b, 0x05, 0x06, ...new Array(18).fill(0)]));
    const llm = path.join(tmp, 'llm_defaults.json');
    fs.writeFileSync(llm, JSON.stringify(LLM_DEFAULTS));
    defaultContext = { ingestZip: zip, ingestLlmDefaults: llm };
    ({ stack, template } = build({}));
  });

  after(() => fs.rmSync(tmp, { recursive: true, force: true }));

  it('bucket: chặn public, SSE-S3, owner enforced, không versioning, lifecycle 30 ngày, CORS POST', () => {
    template.hasResourceProperties('AWS::S3::Bucket', {
      PublicAccessBlockConfiguration: {
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      },
      BucketEncryption: {
        ServerSideEncryptionConfiguration: [{ ServerSideEncryptionByDefault: { SSEAlgorithm: 'AES256' } }],
      },
      OwnershipControls: { Rules: [{ ObjectOwnership: 'BucketOwnerEnforced' }] },
      LifecycleConfiguration: {
        Rules: Match.arrayWith([
          Match.objectLike({ AbortIncompleteMultipartUpload: { DaysAfterInitiation: 1 }, Status: 'Enabled' }),
          Match.objectLike({ ExpirationInDays: 30, Status: 'Enabled' }),
        ]),
      },
      CorsConfiguration: {
        CorsRules: [Match.objectLike({ AllowedMethods: ['POST'], AllowedOrigins: Match.arrayWith(['http://localhost:5173']) })],
      },
    });
    const buckets = template.findResources('AWS::S3::Bucket') as Record<string, Res & { DeletionPolicy?: string }>;
    const [bucket] = Object.values(buckets);
    assert.equal(bucket.Properties.VersioningConfiguration, undefined);
    assert.equal(bucket.DeletionPolicy, 'Retain');
    assert.match(JSON.stringify(bucket.Properties.BucketName), /yofina-ingest-/);
  });

  it('bucket policy bắt buộc TLS', () => {
    template.hasResourceProperties('AWS::S3::BucketPolicy', {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({ Effect: 'Deny', Condition: { Bool: { 'aws:SecureTransport': 'false' } } }),
        ]),
      },
    });
  });

  it('S3 ObjectCreated tiền tố u/ -> SQS, queue policy có SourceArn và SourceAccount', () => {
    template.hasResourceProperties('Custom::S3BucketNotifications', {
      NotificationConfiguration: {
        QueueConfigurations: [
          Match.objectLike({
            Events: ['s3:ObjectCreated:*'],
            Filter: { Key: { FilterRules: [{ Name: 'prefix', Value: 'u/' }] } },
          }),
        ],
      },
    });
    template.hasResourceProperties('AWS::SQS::QueuePolicy', {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Principal: { Service: 's3.amazonaws.com' },
            Action: 'sqs:SendMessage',
            Condition: { ArnLike: { 'aws:SourceArn': Match.anyValue() }, StringEquals: { 'aws:SourceAccount': Match.anyValue() } },
          }),
        ]),
      },
    });
  });

  it('SQS + DLQ: SSE-SQS, visibility >= 6x timeout worker, maxReceiveCount 3, DLQ 14 ngày; alarm DLQ -> SNS', () => {
    template.hasResourceProperties('AWS::SQS::Queue', {
      QueueName: 'yofina-ingest-jobs',
      SqsManagedSseEnabled: true,
      VisibilityTimeout: 720,
      RedrivePolicy: { maxReceiveCount: 3, deadLetterTargetArn: Match.anyValue() },
    });
    template.hasResourceProperties('AWS::SQS::Queue', {
      QueueName: 'yofina-ingest-jobs-dlq',
      SqsManagedSseEnabled: true,
      MessageRetentionPeriod: 14 * 24 * 3600,
    });
    template.hasResourceProperties('AWS::CloudWatch::Alarm', {
      AlarmName: 'yofina-ingest-jobs-dlq-not-empty',
      Threshold: 1,
      AlarmActions: [Match.anyValue()],
    });
  });

  it('hai Lambda arm64 python3.13, handler, timeout, memory, đủ biến môi trường', () => {
    const fns = template.findResources('AWS::Lambda::Function') as Record<string, Res>;
    const byName = Object.fromEntries(Object.values(fns).map((f) => [f.Properties.FunctionName, f.Properties]));
    const api = byName['yofina-ingest-api'];
    const worker = byName['yofina-ingest'];
    assert.ok(api && worker, 'thiếu Lambda');
    for (const [fn, handler, timeout, mem] of [
      [api, 'handler_api.handler', 30, 512],
      [worker, 'handler_worker.handler', 120, 1024],
    ] as const) {
      assert.equal(fn.Runtime, 'python3.13');
      assert.deepEqual(fn.Architectures, ['arm64']);
      assert.equal(fn.Handler, handler);
      assert.equal(fn.Timeout, timeout);
      assert.equal(fn.MemorySize, mem);
      const vars = Object.keys(fn.Environment.Variables);
      for (const k of REQUIRED_ENV) assert.ok(vars.includes(k), `${fn.FunctionName} thiếu ${k}`);
      assert.equal(fn.Environment.Variables.YOFINA_CONFIRM_TOKEN_TTL_SECONDS, '120');
      assert.equal(fn.Environment.Variables.YOFINA_CONFIRM_OFFER_TTL_SECONDS, '600');
      assert.equal(fn.Environment.Variables.YOFINA_DB_RESUME_MAX_WAIT_SECONDS, '18');
      assert.equal(fn.Environment.Variables.YOFINA_INGEST_UPLOAD_PREFIX, 'u/');
      assert.equal(fn.Environment.Variables.YOFINA_INGEST_MAX_RECEIVE_COUNT, '3');
      assert.equal(fn.Environment.Variables.YOFINA_FORECAST_HISTORY_WINDOW_DAYS, '330');
      assert.equal(fn.Environment.Variables.YOFINA_FORECAST_FUNCTION_NAME !== undefined, true);
      assert.ok(!('YOFINA_DB_SECRET_ARN' in fn.Environment.Variables), 'chỉ tên db_app_secret_arn mà yofina_core.db đọc');
      assert.equal(fn.Environment.Variables.YOFINA_SSM_PREFIX, '/yofina');
    }
    // mặc định không reserved concurrency (quota tài khoản 10); trần nằm ở maxConcurrency của event source
    assert.equal(worker.ReservedConcurrentExecutions, undefined);
    template.hasResourceProperties('AWS::Lambda::EventSourceMapping', {
      BatchSize: 1,
      FunctionResponseTypes: ['ReportBatchItemFailures'],
      ScalingConfig: { MaximumConcurrency: 2 },
    });
    template.hasResourceProperties('AWS::Logs::LogGroup', { LogGroupName: '/aws/lambda/yofina-ingest', RetentionInDays: 14 });
    template.hasResourceProperties('AWS::Logs::LogGroup', { LogGroupName: '/aws/lambda/yofina-ingest-api', RetentionInDays: 14 });
  });

  it('reserved concurrency đặt được bằng context', () => {
    const zip = path.join(tmp, 'ingest-arm64.zip');
    const { template: t } = build({ ingestZip: zip, ingestWorkerReservedConcurrency: 2 });
    t.hasResourceProperties('AWS::Lambda::Function', { FunctionName: 'yofina-ingest', ReservedConcurrentExecutions: 2 });
  });

  it('IAM: mỗi Lambda một role; không * cho rds-data/secrets/s3/dynamodb/bedrock; không master secret', () => {
    const roles = template.findResources('AWS::IAM::Role') as Record<string, Res>;
    const lambdaRoles = Object.entries(roles).filter(([, r]) =>
      JSON.stringify(r.Properties.AssumeRolePolicyDocument).includes('lambda.amazonaws.com'),
    );
    const roleIds = lambdaRoles.map(([id]) => id);
    assert.ok(roleIds.some((id) => id.startsWith('ApiServiceRole')));
    assert.ok(roleIds.some((id) => id.startsWith('WorkerServiceRole')));

    const all = JSON.stringify(template.toJSON());
    assert.ok(!/master/i.test(all), 'không được tham chiếu secret master');

    for (const prefix of ['ApiServiceRole', 'WorkerServiceRole']) {
      for (const st of statementsOf(template, prefix)) {
        const actions = asList<string>(st.Action);
        const sensitive = actions.some((a) => /^(rds-data|secretsmanager|s3|dynamodb|bedrock|lambda|events|ssm):/.test(a));
        if (!sensitive) continue;
        for (const r of asList<any>(st.Resource)) assert.notEqual(r, '*', `${prefix} ${actions} có Resource *`);
      }
    }
    const worker = statementsOf(template, 'WorkerServiceRole');
    const api = statementsOf(template, 'ApiServiceRole');
    const has = (sts: any[], action: string) => sts.some((s) => asList<string>(s.Action).includes(action));
    assert.ok(has(worker, 's3:GetObject') && has(worker, 's3:DeleteObject') && !has(worker, 's3:PutObject'));
    assert.ok(has(api, 's3:PutObject') && !has(api, 's3:DeleteObject') && !has(api, 's3:ListBucket'));
    assert.ok(!has(api, 's3:GetObject'), 'API không cần đọc tệp người dùng');
    // S3 chỉ trên tiền tố u/* (trừ ListBucket trên bucket, có điều kiện prefix)
    for (const st of [...api, ...worker]) {
      const actions = asList<string>(st.Action);
      if (!actions.some((a) => /^s3:(Get|Put|Delete)Object$/.test(a))) continue;
      for (const r of asList<any>(st.Resource)) assert.match(JSON.stringify(r), /\/u\/\*/);
    }
    // PutObject chỉ qua presigned POST
    const put = api.filter((s) => asList<string>(s.Action).includes('s3:PutObject'));
    assert.equal(put.length, 1);
    assert.deepEqual(put[0].Condition, { StringEquals: { 's3:authType': 'POST' } });
    assert.deepEqual(asList(put[0].Action), ['s3:PutObject']);
    assert.ok(has(api, 'dynamodb:PutItem') && !has(worker, 'dynamodb:PutItem'));
    // mỗi Lambda chỉ có quyền nó dùng: API (token, presigned POST, kích hoạt dự báo), worker (Bedrock, bộ đếm lượt gọi, đọc tệp)
    for (const a of ['rds-data:ExecuteStatement', 'secretsmanager:GetSecretValue', 'rds-data:BeginTransaction']) {
      assert.ok(has(api, a) && has(worker, a), `thiếu ${a}`);
    }
    for (const a of ['lambda:InvokeFunction', 'dynamodb:PutItem', 's3:PutObject']) {
      assert.ok(has(api, a) && !has(worker, a), a);
    }
    for (const a of ['bedrock:InvokeModel', 'dynamodb:UpdateItem', 's3:GetObject']) {
      assert.ok(has(worker, a) && !has(api, a), a);
    }
    for (const sts of [api, worker]) assert.ok(!has(sts, 'events:PutEvents'), 'không phát sự kiện: không cần quyền EventBridge');
    // gọi lại dự báo chỉ trên yofina-forecast-batch
    const invoke = api.find((s) => asList<string>(s.Action).includes('lambda:InvokeFunction'));
    assert.match(JSON.stringify(invoke.Resource), /forecastbatchfunctionname/);
    // HMAC chỉ cho API
    const secretRes = (sts: any[]) =>
      JSON.stringify(sts.filter((s) => asList<string>(s.Action).includes('secretsmanager:GetSecretValue')).map((s) => s.Resource));
    assert.match(secretRes(api), /confirmhmacarn/);
    assert.doesNotMatch(secretRes(worker), /confirmhmacarn/);
  });

  it('Bedrock: mẫu 3 phần của global cross-Region inference, chỉ model của vai ingest', () => {
    assert.ok(!statementsOf(template, 'ApiServiceRole').some((s) => asList<string>(s.Action).includes('bedrock:InvokeModel')));
    for (const prefix of ['WorkerServiceRole']) {
      const sts = statementsOf(template, prefix).filter((s) => asList<string>(s.Action).includes('bedrock:InvokeModel'));
      const json = JSON.stringify(sts);
      for (const m of ['anthropic.claude-sonnet-4-6', 'moonshotai.kimi-k3']) {
        const profile = sts.find((s) => JSON.stringify(s.Resource).includes(`inference-profile/global.${m}`));
        assert.ok(profile, `thiếu profile ${m}`);
        assert.equal(profile.Condition.StringEquals['aws:RequestedRegion'], 'ap-southeast-1');
        const regional = sts.find((s) => JSON.stringify(s.Resource).includes(`ap-southeast-1::foundation-model/${m}`));
        assert.ok(regional, `thiếu foundation model ở region gọi ${m}`);
        assert.equal(regional.Condition.StringEquals['aws:RequestedRegion'], 'ap-southeast-1');
        assert.match(JSON.stringify(regional.Condition.StringEquals['bedrock:InferenceProfileArn']), new RegExp(`global\\.${m}`));
        const global = sts.find((s) => asList(s.Resource).includes(`arn:aws:bedrock:::foundation-model/${m}`));
        assert.ok(global, `thiếu foundation model toàn cầu ${m}`);
        assert.equal(global.Condition.StringEquals['aws:RequestedRegion'], 'unspecified');
        assert.match(JSON.stringify(global.Condition.StringEquals['bedrock:InferenceProfileArn']), new RegExp(`global\\.${m}`));
      }
      // vai không nằm trong ingestLlmRoles không được cấp; không wildcard region cho foundation model
      assert.ok(!json.includes('nova-2-lite'), `${prefix}: không được cấp model của vai planner`);
      assert.ok(!json.includes('titan'), `${prefix}: không được cấp model của vai khác`);
      assert.ok(!json.includes('arn:aws:bedrock:*'), `${prefix}: không dùng region *`);
    }
  });

  it('vai model chưa có trong llm_defaults.json: bỏ qua kèm cảnh báo; không vai nào có: lỗi', () => {
    Annotations.fromStack(stack).hasWarning('*', Match.stringLikeRegexp("chưa có vai 'ingest_columns'"));
    const { stack: none } = build({ ingestLlmRoles: 'khong_co_a,khong_co_b' });
    Annotations.fromStack(none).hasError('*', Match.stringLikeRegexp('không vai nào có trong llm_defaults.json'));
    // model không global: foundation model ở region gọi, không điều kiện profile
    const { template: t } = build({ ingestLlmRoles: 'regional_only' });
    const sts = statementsOf(t, 'WorkerServiceRole').filter((s) => asList<string>(s.Action).includes('bedrock:InvokeModel'));
    assert.equal(sts.length, 1);
    assert.match(JSON.stringify(sts[0].Resource), /ap-southeast-1::foundation-model\/amazon\.titan-text-lite-v1/);
  });

  it('llm_defaults.json thật của repo có hai vai ingest: không cảnh báo, quyền đúng model của vai', () => {
    const real = path.resolve(__dirname, '..', '..', 'libs', 'yofina_core', 'src', 'yofina_core', 'llm_defaults.json');
    const defaults = JSON.parse(fs.readFileSync(real, 'utf-8'));
    assert.ok(defaults.roles.ingest && defaults.roles.ingest_columns, 'llm_defaults.json thiếu vai ingest hoặc ingest_columns');
    const { stack: s, template: t } = build({ ingestLlmDefaults: real });
    Annotations.fromStack(s).hasNoWarning('*', Match.stringLikeRegexp('llm-role-missing|chưa có vai'));
    Annotations.fromStack(s).hasNoError('*', Match.anyValue());
    const json = JSON.stringify(statementsOf(t, 'WorkerServiceRole').filter((x) => asList<string>(x.Action).includes('bedrock:InvokeModel')));
    for (const m of ['claude-sonnet-4-6', 'kimi-k3', 'nova-2-lite-v1:0', 'claude-haiku-4-5-20251001-v1:0']) assert.ok(json.includes(m), m);
    assert.ok(!json.includes('embed'), 'vai embedding không thuộc ingest');
  });

  it('6 route JWT trên API có sẵn, chỉ GET/POST (CORS của yofina-api), authorizer cùng issuer/audience, AWS_PROXY 2.0', () => {
    const routes = template.findResources('AWS::ApiGatewayV2::Route') as Record<string, Res>;
    const keys = Object.values(routes).map((r) => r.Properties.RouteKey).sort();
    assert.deepEqual(keys, [
      'GET /ingest/jobs',
      'GET /ingest/jobs/{job_id}',
      'POST /ingest/actions',
      'POST /ingest/confirmations',
      'POST /ingest/rows/{row_id}/jar',
      'POST /ingest/uploads',
    ]);
    for (const k of keys) assert.match(k, /^(GET|POST) /, `${k}: preflight của yofina-api chỉ cho GET, POST, OPTIONS`);
    assert.ok(!keys.some((k) => k.startsWith('PATCH ')), 'không route PATCH');
    const apiIdJson = JSON.stringify(Object.values(routes)[0].Properties.ApiId);
    assert.match(apiIdJson, /Fn::Split/);
    assert.match(apiIdJson, /SsmParameterValueyofinaapiurl/);
    for (const r of Object.values(routes)) {
      assert.equal(r.Properties.AuthorizationType, 'JWT');
      assert.ok(r.Properties.AuthorizerId);
      assert.equal(JSON.stringify(r.Properties.ApiId), apiIdJson);
    }
    template.hasResourceProperties('AWS::ApiGatewayV2::Authorizer', {
      Name: 'yofina-cognito-ingest',
      AuthorizerType: 'JWT',
      IdentitySource: ['$request.header.Authorization'],
      JwtConfiguration: { Audience: [Match.anyValue()], Issuer: Match.anyValue() },
    });
    template.hasResourceProperties('AWS::ApiGatewayV2::Integration', {
      IntegrationType: 'AWS_PROXY',
      PayloadFormatVersion: '2.0',
    });
    // không tạo API, stage hay sửa CORS của API chung
    template.resourceCountIs('AWS::ApiGatewayV2::Api', 0);
    template.resourceCountIs('AWS::ApiGatewayV2::Stage', 0);
  });

  it('permission cho API Gateway giới hạn đúng API và /ingest/*', () => {
    const perms = template.findResources('AWS::Lambda::Permission', {
      Properties: { Principal: 'apigateway.amazonaws.com' },
    }) as Record<string, Res>;
    const list = Object.values(perms);
    assert.equal(list.length, 1);
    const src = JSON.stringify(list[0].Properties.SourceArn);
    assert.match(src, /\/\*\/\*\/ingest\/\*/);
    assert.match(src, /Fn::Split/);
    assert.ok(list[0].Properties.SourceAccount);
  });

  it('SSM output và tag project=yofina', () => {
    for (const k of ['bucket-name', 'api-function-name', 'worker-function-name', 'queue-url']) {
      template.hasResourceProperties('AWS::SSM::Parameter', { Name: `/yofina/ingest/${k}` });
    }
    for (const type of ['AWS::S3::Bucket', 'AWS::SQS::Queue', 'AWS::Lambda::Function', 'AWS::IAM::Role', 'AWS::Logs::LogGroup', 'AWS::CloudWatch::Alarm']) {
      const all = template.findResources(type) as Record<string, Res>;
      assert.ok(Object.keys(all).length > 0, type);
      for (const [id, r] of Object.entries(all)) {
        assert.ok(asList<any>(r.Properties.Tags ?? []).some((t) => t.Key === 'project' && t.Value === 'yofina'), `${id} thiếu tag`);
      }
    }
    for (const [id, r] of Object.entries(template.findResources('AWS::SSM::Parameter') as Record<string, Res>)) {
      assert.equal(r.Properties.Tags?.project, 'yofina', `${id} thiếu tag`); // SSM Parameter: Tags là map
    }
  });

  it('không có tài nguyên tính tiền theo giờ', () => {
    const types = new Set(Object.values(template.toJSON().Resources as Record<string, Res>).map((r) => r.Type));
    for (const t of ['AWS::EC2::NatGateway', 'AWS::EC2::VPCEndpoint', 'AWS::KMS::Key', 'AWS::OpenSearchService::Domain']) {
      assert.ok(!types.has(t), t);
    }
    for (const t of types) {
      assert.ok(!/^AWS::(EC2|OpenSearchService|OpenSearchServerless|ElasticLoadBalancingV2|RDS|ElastiCache)::/.test(t), `tài nguyên tính giờ: ${t}`);
    }
    assert.ok(stack.bucket);
  });

  it('thiếu zip: stack báo lỗi (không deploy được mã thay thế)', () => {
    const { stack: s } = build({ ingestZip: path.join(tmp, 'khong-co.zip') });
    Annotations.fromStack(s).hasError('*', Match.stringLikeRegexp('Chưa có .*khong-co\\.zip'));
  });
});
