import * as fs from 'fs';
import * as path from 'path';
import { Annotations, App, Duration, RemovalPolicy, Stack } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cwActions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as lambdaEventSources from 'aws-cdk-lib/aws-lambda-event-sources';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import { YofinaConfig } from '../config/config';

/**
 * Phân hũ tự động (F2, phase 4 luồng B). Giá trị đổi được bằng context `-c khóa=giá trị`; ngưỡng nghiệp vụ KHÔNG ở đây mà ở
 * `classify_defaults.json` (ghi đè từng số bằng context `classifyThresholds` là JSON, vào Lambda dưới dạng `YOFINA_CLASSIFY_<TÊN HOA>`).
 */
export interface ClassifyConfig {
  /** Zip Lambda phân loại (xem `CLASSIFY_BUILD_COMMAND`). */
  readonly zip: string;
  readonly memoryMb: number;
  readonly timeoutSeconds: number;
  /** Lô SQS: mỗi bản tin một giao dịch, xử lý tuần tự trong lô nên giữ nhỏ (mỗi giao dịch có thể gọi hai lần Bedrock). */
  readonly batchSize: number;
  /** Số Lambda chạy đồng thời tối đa: vai `small` giới hạn khoảng 18 lượt mỗi phút mỗi model, Aurora 0,5 ACU. */
  readonly maxConcurrency: number;
  /** SQS giao lại tối đa từng này lần trước khi vào DLQ; lần giao cuối thì phân loại suy giảm thay vì thử lại. */
  readonly maxReceiveCount: number;
  readonly idempotencyTtlSeconds: number;
  /** Vai model trong `llm_defaults.json` mà Lambda được gọi: `small` (bước 3) và `embedding` (bước 2). */
  readonly llmRoles: string[];
  /** Đường dẫn `llm_defaults.json` (mặc định là file của yofina_core; test đổi bằng context `classifyLlmDefaults`). */
  readonly llmDefaults: string;
  /** Ghi đè ngưỡng (`classifyThresholds` là JSON `{"auto_min_confidence": 0.92}`); rỗng là dùng `classify_defaults.json`. */
  readonly thresholdOverrides: Record<string, string>;
}

/** Lệnh đóng zip Lambda phân loại (zip KHÔNG cần numpy, scipy; handler_classify.py ở gốc zip). */
export const CLASSIFY_BUILD_COMMAND =
  'uv run scripts/build_lambda.py pipelines/classify --arch arm64 --name classify ' +
  '--extra gateway/tools/ledger/yofina_ledger:yofina_ledger';

function ctxNum(app: App, key: string, dflt: number): number {
  const v = app.node.tryGetContext(key);
  if (v === undefined || v === null || v === '') return dflt;
  const n = Number(v);
  if (!Number.isFinite(n)) throw new Error(`context ${key} phải là số, nhận được: ${v}`);
  return n;
}

function ctxStr(app: App, key: string, dflt: string): string {
  const v = app.node.tryGetContext(key);
  return v === undefined || v === null || v === '' ? dflt : String(v);
}

export function loadClassifyConfig(app: App): ClassifyConfig {
  const maxConcurrency = ctxNum(app, 'classifyMaxConcurrency', 3);
  if (maxConcurrency < 2 || maxConcurrency > 1000) throw new Error('classifyMaxConcurrency phải trong 2..1000 (giới hạn của SQS event source)');
  const overridesRaw = ctxStr(app, 'classifyThresholds', '');
  let overrides: Record<string, string> = {};
  if (overridesRaw) {
    const parsed = typeof overridesRaw === 'string' ? JSON.parse(overridesRaw) : overridesRaw;
    overrides = Object.fromEntries(Object.entries(parsed as Record<string, unknown>).map(([k, v]) => [k, String(v)]));
  }
  return {
    zip: path.resolve(__dirname, '..', ctxStr(app, 'classifyZip', '../build/lambda/classify-arm64.zip')),
    memoryMb: ctxNum(app, 'classifyMemoryMb', 512),
    timeoutSeconds: ctxNum(app, 'classifyTimeoutSeconds', 90),
    batchSize: ctxNum(app, 'classifyBatchSize', 5),
    maxConcurrency,
    maxReceiveCount: ctxNum(app, 'classifyMaxReceiveCount', 3),
    idempotencyTtlSeconds: ctxNum(app, 'classifyIdempotencyTtlSeconds', 259200),
    llmRoles: ctxStr(app, 'classifyLlmRoles', 'small,embedding')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    llmDefaults: path.resolve(
      __dirname,
      '..',
      ctxStr(app, 'classifyLlmDefaults', '../libs/yofina_core/src/yofina_core/llm_defaults.json'),
    ),
    thresholdOverrides: overrides,
  };
}

interface LlmDefaults {
  roles: Record<string, { models: Array<{ id: string }> }>;
}

export interface ClassifyPipelineProps {
  readonly cfg: YofinaConfig;
  readonly classify: ClassifyConfig;
  /** Bus `yofina-bus` (rule nghe `transaction.recorded` cần phân loại; Lambda phát lại `transaction.recorded` loại jar_assign sau khi gán). */
  readonly bus: events.IEventBus;
  readonly alertTopic: sns.ITopic;
  readonly appTimezone: string;
  readonly clusterArn: string;
  readonly appSecretArn: string;
  readonly dbName: string;
  readonly dbResumeMaxWaitSeconds: number;
  /** Bảng bộ đếm lượt gọi model (`yofina-usage`), `yofina_core.llm` đếm vào đó. */
  readonly usageTableName: string;
}

/**
 * Lambda `yofina-classify` (Python 3.13 arm64, ngoài VPC, gọi Aurora qua Data API bằng secret của role `yofina_app`, không bao giờ secret master):
 * rule trên `yofina-bus` (`source yofina.ledger`, `detail-type transaction.recorded`, `detail.needs_classification = true`) -> SQS
 * `yofina-classify-events` (+DLQ, alarm) -> Lambda. Idempotent theo id sự kiện bằng bảng DynamoDB riêng `yofina-classify-idempotency`.
 * IAM Bedrock `InvokeModel` CHỈ cho model của vai `small` (bước 3) và `embedding` (bước 2: Cohere Embed v3, model theo Region).
 * CHƯA nối vào stack nào: người điều phối thêm `new ClassifyPipeline(...)` vào `YofinaTools`.
 */
export class ClassifyPipeline extends Construct {
  public readonly fn: lambda.Function;
  public readonly queue: sqs.Queue;
  public readonly deadLetterQueue: sqs.Queue;
  public readonly idempotencyTable: dynamodb.Table;

  constructor(scope: Construct, id: string, props: ClassifyPipelineProps) {
    super(scope, id);
    const { cfg, classify: c, bus, alertTopic } = props;
    const p = cfg.prefix;
    const stack = Stack.of(this);

    if (props.dbResumeMaxWaitSeconds >= c.timeoutSeconds) {
      throw new Error('dbResumeMaxWaitSeconds phải nhỏ hơn classifyTimeoutSeconds');
    }

    this.idempotencyTable = new dynamodb.Table(this, 'Idempotency', {
      tableName: `${p}-classify-idempotency`,
      partitionKey: { name: 'event_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'ttl',
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // Thiếu zip thì gắn lỗi vào stack (như YofinaIngest): CLI từ chối synth/deploy và mã thay thế không bao giờ lên AWS.
    let code: lambda.Code;
    if (fs.existsSync(c.zip)) {
      code = lambda.Code.fromAsset(c.zip);
    } else {
      Annotations.of(this).addError(`Chưa có ${c.zip}. Chạy: ${CLASSIFY_BUILD_COMMAND} (hoặc -c classifyZip=<đường dẫn>)`);
      code = lambda.Code.fromInline('raise RuntimeError("classify zip missing")');
    }

    const thresholdEnv = Object.fromEntries(
      Object.entries(c.thresholdOverrides).map(([k, v]) => [`YOFINA_CLASSIFY_${k.toUpperCase()}`, v]),
    );
    this.fn = new lambda.Function(this, 'Fn', {
      functionName: `${p}-classify`,
      description: 'F2 phan hu tu dong: consumer SQS cua transaction.recorded (bang tra -> luat -> embedding -> model nho), idempotent',
      runtime: lambda.Runtime.PYTHON_3_13,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler_classify.lambda_handler',
      code,
      memorySize: c.memoryMb,
      timeout: Duration.seconds(c.timeoutSeconds),
      logGroup: new logs.LogGroup(this, 'FnLogs', {
        logGroupName: `/aws/lambda/${p}-classify`,
        retention: cfg.logRetentionDays as logs.RetentionDays,
        removalPolicy: RemovalPolicy.DESTROY,
      }),
      environment: {
        YOFINA_REGION: cfg.region,
        YOFINA_LOG_LEVEL: 'INFO',
        YOFINA_SSM_PREFIX: `/${p}`,
        YOFINA_DB_CLUSTER_ARN: props.clusterArn,
        YOFINA_DB_APP_SECRET_ARN: props.appSecretArn,
        YOFINA_DB_NAME: props.dbName,
        YOFINA_DB_RESUME_MAX_WAIT_SECONDS: String(props.dbResumeMaxWaitSeconds),
        YOFINA_APP_TIMEZONE: props.appTimezone,
        YOFINA_EVENT_BUS_NAME: bus.eventBusName,
        YOFINA_USAGE_TABLE: props.usageTableName,
        YOFINA_CLASSIFY_IDEMPOTENCY_TABLE: this.idempotencyTable.tableName,
        YOFINA_CLASSIFY_IDEMPOTENCY_TTL_SECONDS: String(c.idempotencyTtlSeconds),
        // khóa thuê dài hơn timeout của hàm: lần giao lại không giành khóa khi lần đầu còn đang chạy
        YOFINA_CLASSIFY_IDEMPOTENCY_LEASE_SECONDS: String(c.timeoutSeconds + 30),
        YOFINA_CLASSIFY_MAX_RECEIVE_COUNT: String(c.maxReceiveCount),
        ...thresholdEnv,
      },
    });

    // --- IAM tối thiểu -------------------------------------------------------------------------------------------------------
    this.fn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'DataApiAppRole',
        actions: [
          'rds-data:ExecuteStatement',
          'rds-data:BatchExecuteStatement',
          'rds-data:BeginTransaction',
          'rds-data:CommitTransaction',
          'rds-data:RollbackTransaction',
        ],
        resources: [props.clusterArn],
      }),
    );
    // CHỈ secret của yofina_app (không master)
    this.fn.addToRolePolicy(
      new iam.PolicyStatement({ sid: 'ReadAppSecretOnly', actions: ['secretsmanager:GetSecretValue'], resources: [props.appSecretArn] }),
    );
    this.fn.addToRolePolicy(
      new iam.PolicyStatement({ sid: 'PublishLedgerEvents', actions: ['events:PutEvents'], resources: [bus.eventBusArn] }),
    );
    this.idempotencyTable.grant(this.fn, 'dynamodb:PutItem', 'dynamodb:GetItem', 'dynamodb:UpdateItem', 'dynamodb:DeleteItem');
    this.fn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'CountModelCalls',
        actions: ['dynamodb:UpdateItem'],
        resources: [stack.formatArn({ service: 'dynamodb', resource: 'table', resourceName: props.usageTableName })],
      }),
    );
    // yofina_core.llm đọc gộp nhánh /yofina/llm (GetParametersByPath); mọi khóa YOFINA_* vắng đi GetParameter (yofina_core.config)
    const ssmArn = (name: string) => stack.formatArn({ service: 'ssm', resource: 'parameter', resourceName: name });
    this.fn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'ReadConfig',
        actions: ['ssm:GetParameter', 'ssm:GetParametersByPath'],
        resources: [ssmArn(`${p}/llm`), ssmArn(`${p}/llm/*`), ssmArn(`${p}/dynamodb/usage-table`), ssmArn(`${p}/classify_*`), ssmArn(`${p}/db_*`), ssmArn(`${p}/reference_*`)],
      }),
    );

    // Bedrock: model của các vai small và embedding (đọc lúc synth từ llm_defaults.json, như YofinaIngest)
    const llm = JSON.parse(fs.readFileSync(c.llmDefaults, 'utf-8')) as LlmDefaults;
    const modelIds: string[] = [];
    for (const role of c.llmRoles) {
      const r = llm.roles[role];
      if (!r) {
        Annotations.of(this).addError(`classifyLlmRoles: không có vai '${role}' trong llm_defaults.json`);
        continue;
      }
      for (const m of r.models) if (!modelIds.includes(m.id)) modelIds.push(m.id);
    }
    const profileArns: string[] = [];
    const directModelArns: string[] = [];
    const bedrock: iam.PolicyStatement[] = [];
    for (const m of modelIds) {
      if (!m.startsWith('global.')) {
        directModelArns.push(`arn:aws:bedrock:${stack.region}::foundation-model/${m}`);
        continue;
      }
      // Global cross-Region inference (mẫu 3 phần của tài liệu Bedrock): profile `global.*` + foundation model ở Region gọi và không Region,
      // chỉ khi đi qua đúng profile đó.
      const base = m.slice('global.'.length);
      const profileArn = `arn:aws:bedrock:${stack.region}:${stack.account}:inference-profile/${m}`;
      profileArns.push(profileArn);
      bedrock.push(
        new iam.PolicyStatement({
          actions: ['bedrock:InvokeModel'],
          resources: [`arn:aws:bedrock:${stack.region}::foundation-model/${base}`],
          conditions: { StringEquals: { 'aws:RequestedRegion': stack.region, 'bedrock:InferenceProfileArn': profileArn } },
        }),
        new iam.PolicyStatement({
          actions: ['bedrock:InvokeModel'],
          resources: [`arn:aws:bedrock:::foundation-model/${base}`],
          conditions: { StringEquals: { 'aws:RequestedRegion': 'unspecified', 'bedrock:InferenceProfileArn': profileArn } },
        }),
      );
    }
    if (profileArns.length > 0) {
      bedrock.unshift(
        new iam.PolicyStatement({
          sid: 'InvokeGlobalInferenceProfiles',
          actions: ['bedrock:InvokeModel'], // Converse dùng quyền bedrock:InvokeModel
          resources: profileArns,
          conditions: { StringEquals: { 'aws:RequestedRegion': stack.region } },
        }),
      );
    }
    if (directModelArns.length > 0) {
      // Cohere Embed v3 (InvokeModel) và các model gọi thẳng ở Region
      bedrock.push(new iam.PolicyStatement({ sid: 'InvokeRegionalModels', actions: ['bedrock:InvokeModel'], resources: directModelArns }));
    }
    for (const st of bedrock) this.fn.addToRolePolicy(st);

    // --- đường sự kiện: yofina-bus -> SQS (+DLQ) -> yofina-classify --------------------------------------------------------------
    this.deadLetterQueue = new sqs.Queue(this, 'EventsDlq', {
      queueName: `${p}-classify-events-dlq`,
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      retentionPeriod: Duration.days(14),
      enforceSSL: true,
    });
    this.queue = new sqs.Queue(this, 'Events', {
      queueName: `${p}-classify-events`,
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      // khuyến nghị của AWS: tối thiểu 6 lần timeout của hàm tiêu thụ
      visibilityTimeout: Duration.seconds(c.timeoutSeconds * 6),
      retentionPeriod: Duration.days(4),
      enforceSSL: true,
      deadLetterQueue: { queue: this.deadLetterQueue, maxReceiveCount: c.maxReceiveCount },
    });
    new events.Rule(this, 'NeedsClassificationRule', {
      ruleName: `${p}-classify-needs-classification`,
      description: 'Giao dich chi chua xep hu (transaction.recorded, needs_classification) -> hang doi yofina-classify-events',
      eventBus: bus,
      eventPattern: {
        source: ['yofina.ledger'],
        detailType: ['transaction.recorded'],
        detail: { needs_classification: [true] },
      },
      targets: [new targets.SqsQueue(this.queue)],
    });
    this.fn.addEventSource(
      new lambdaEventSources.SqsEventSource(this.queue, {
        batchSize: c.batchSize,
        maxBatchingWindow: Duration.seconds(0),
        reportBatchItemFailures: true,
        maxConcurrency: c.maxConcurrency,
      }),
    );
    new cloudwatch.Alarm(this, 'DlqAlarm', {
      alarmName: `${p}-classify-events-dlq-not-empty`,
      alarmDescription: 'Co giao dich khong phan loai duoc (da vao DLQ yofina-classify-events-dlq): kiem log yofina-classify',
      metric: this.deadLetterQueue.metricApproximateNumberOfMessagesVisible({ period: Duration.minutes(1), statistic: 'Maximum' }),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    }).addAlarmAction(new cwActions.SnsAction(alertTopic));
  }
}
