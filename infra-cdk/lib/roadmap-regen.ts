import * as fs from 'fs';
import * as path from 'path';
import { Annotations, App, Duration, RemovalPolicy, Stack } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cwActions from 'aws-cdk-lib/aws-cloudwatch-actions';
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
 * Sinh lại lộ trình chạy nền (F5, phase 4 luồng C). Mã ở `pipelines/roadmap/` (đọc cấu hình ở `yofina_roadmap/settings.py`).
 * Mọi giá trị đổi được bằng context `-c khóa=giá trị`.
 *
 * Thời gian (ràng buộc kiểm lúc synth): timeout Lambda < lease `running` < visibility timeout của hàng đợi.
 * - Lease lớn hơn timeout: lần giao lại chỉ dọn job `running` khi lần chạy trước chắc chắn đã dừng.
 * - Visibility nhỏ hơn lease thì tin được giao lại khi job cũ chưa hết lease, gặp `JobBusy` và tốn một lượt nhận; nên visibility
 *   mặc định là 6 lần timeout (khuyến nghị của tài liệu Lambda cho SQS event source).
 */
export interface RoadmapRegenConfig {
  /** Zip Lambda sinh lại (xem `ROADMAP_BUILD_COMMAND`). */
  readonly zip: string;
  readonly memoryMb: number;
  readonly timeoutSeconds: number;
  /** `YOFINA_ROADMAP_RUNNING_LEASE_SECONDS`. */
  readonly runningLeaseSeconds: number;
  readonly visibilityTimeoutSeconds: number;
  /** Mỗi tin một job chạy lâu (nhiều lượt Bedrock, Invoke tool): lô một tin. */
  readonly batchSize: number;
  /** Số Lambda chạy song song tối đa (tối thiểu 2 theo SQS event source); vai `planner` chỉ khoảng 8 lượt mỗi phút mỗi model. */
  readonly maxConcurrency: number;
  /** Số lần giao trước khi vào DLQ. `JobBusy` (người dùng đang có job khác) cũng tốn một lần, nên cần đủ lớn. */
  readonly maxReceiveCount: number;
  readonly retentionDays: number;
  readonly invokeConnectTimeoutSeconds: number;
  /** Timeout đọc kết quả Invoke tool. Vắng thì lấy timeout lớn nhất của hai Lambda tool cộng `invokeReadMarginSeconds`. */
  readonly invokeReadTimeoutSeconds?: number;
  readonly invokeReadMarginSeconds: number;
  /** `YOFINA_ROADMAP_STAGE_PROGRESS`: năm mốc phần trăm của `context,draft,allocate,suitability,save`. */
  readonly stageProgress: string;
  /** Vai model trong `llm_defaults.json` mà Lambda được gọi (Roadmap agent chỉ gọi `planner`). */
  readonly llmRoles: string[];
  readonly llmDefaults: string;
}

/** Lệnh đóng zip (handler.py ở gốc zip; strands-agents cài theo arm64; kèm yofina_core và các module yofina_agent). */
export const ROADMAP_BUILD_COMMAND =
  'uv run scripts/build_lambda.py pipelines/roadmap --arch arm64 --name roadmap --extra agent/src/yofina_agent:yofina_agent';

function ctxNum(app: App, key: string, dflt: number): number {
  const v = app.node.tryGetContext(key);
  if (v === undefined || v === null || v === '') return dflt;
  const n = Number(v);
  if (!Number.isFinite(n)) throw new Error(`context ${key} phải là số, nhận được: ${v}`);
  return n;
}

function ctxOptNum(app: App, key: string): number | undefined {
  const v = app.node.tryGetContext(key);
  return v === undefined || v === null || v === '' ? undefined : ctxNum(app, key, 0);
}

function ctxStr(app: App, key: string, dflt: string): string {
  const v = app.node.tryGetContext(key);
  return v === undefined || v === null || v === '' ? dflt : String(v);
}

/** Cùng luật với `RoadmapSettings.from_config`: năm số nguyên tăng ngặt, từ 0 đến 99. */
function checkStageProgress(raw: string): void {
  const parts = raw.split(',').map((s) => s.trim());
  const nums = parts.map((s) => (/^\d+$/.test(s) ? Number(s) : NaN));
  const ok =
    nums.length === 5 && nums.every((n) => Number.isInteger(n)) && nums.every((n, i) => i === 0 || n > nums[i - 1]) && nums[4] < 100;
  if (!ok) throw new Error(`roadmapStageProgress cần năm mốc tăng dần từ 0 đến 99, nhận được: ${raw}`);
}

export function loadRoadmapRegenConfig(app: App): RoadmapRegenConfig {
  const timeout = ctxNum(app, 'roadmapTimeoutSeconds', 300);
  if (timeout < 1 || timeout > 900) throw new Error('roadmapTimeoutSeconds phải trong 1..900 (giới hạn của Lambda)');
  const lease = ctxNum(app, 'roadmapRunningLeaseSeconds', timeout + 60);
  const visibility = ctxNum(app, 'roadmapVisibilityTimeoutSeconds', timeout * 6);
  if (!(lease > timeout)) throw new Error('roadmapRunningLeaseSeconds phải lớn hơn roadmapTimeoutSeconds');
  if (!(visibility > lease)) throw new Error('roadmapVisibilityTimeoutSeconds phải lớn hơn roadmapRunningLeaseSeconds');
  if (visibility > 43200) throw new Error('roadmapVisibilityTimeoutSeconds tối đa 43200 (giới hạn của SQS)');
  const maxConcurrency = ctxNum(app, 'roadmapMaxConcurrency', 2);
  if (maxConcurrency < 2 || maxConcurrency > 1000) throw new Error('roadmapMaxConcurrency phải trong 2..1000 (giới hạn của SQS event source)');
  const batchSize = ctxNum(app, 'roadmapBatchSize', 1);
  if (batchSize < 1 || batchSize > 10) throw new Error('roadmapBatchSize phải trong 1..10');
  // Tối thiểu 5 theo khuyến nghị của AWS; thêm một lượt vì JobBusy và Aurora đang dậy đều tốn lượt nhận.
  const maxReceiveCount = ctxNum(app, 'roadmapMaxReceiveCount', 6);
  if (maxReceiveCount < 1 || maxReceiveCount > 1000) throw new Error('roadmapMaxReceiveCount phải trong 1..1000');
  const retentionDays = ctxNum(app, 'roadmapRetentionDays', 4);
  if (retentionDays * 86400 <= visibility * maxReceiveCount) {
    throw new Error('roadmapRetentionDays phải dài hơn visibility × maxReceiveCount để tin kịp vào DLQ trước khi hết hạn');
  }
  const stageProgress = ctxStr(app, 'roadmapStageProgress', '5,25,45,65,85');
  checkStageProgress(stageProgress);
  return {
    zip: path.resolve(__dirname, '..', ctxStr(app, 'roadmapZip', '../build/lambda/roadmap-arm64.zip')),
    memoryMb: ctxNum(app, 'roadmapMemoryMb', 1024),
    timeoutSeconds: timeout,
    runningLeaseSeconds: lease,
    visibilityTimeoutSeconds: visibility,
    batchSize,
    maxConcurrency,
    maxReceiveCount,
    retentionDays,
    invokeConnectTimeoutSeconds: ctxNum(app, 'roadmapInvokeConnectTimeoutSeconds', 5),
    invokeReadTimeoutSeconds: ctxOptNum(app, 'roadmapInvokeReadTimeoutSeconds'),
    invokeReadMarginSeconds: ctxNum(app, 'roadmapInvokeReadMarginSeconds', 5),
    stageProgress,
    llmRoles: ctxStr(app, 'roadmapLlmRoles', 'planner')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    llmDefaults: path.resolve(
      __dirname,
      '..',
      ctxStr(app, 'roadmapLlmDefaults', '../libs/yofina_core/src/yofina_core/llm_defaults.json'),
    ),
  };
}

interface LlmDefaults {
  roles: Record<string, { models: Array<{ id: string }> }>;
}

export interface RoadmapRegenProps {
  readonly cfg: YofinaConfig;
  readonly roadmap: RoadmapRegenConfig;
  /** Bus `yofina-bus`: ba rule nghe sự kiện kích hoạt sinh lại. Lambda KHÔNG phát sự kiện nên không có quyền PutEvents. */
  readonly bus: events.IEventBus;
  readonly alertTopic: sns.ITopic;
  /** Lambda tool của target `ledger` và `planner` (`yofina-ledger`). */
  readonly ledgerFunction: lambda.IFunction;
  readonly ledgerTimeoutSeconds: number;
  /** Lambda tool của target `forecast` (`yofina-forecast`, KHÔNG phải `yofina-forecast-batch`). */
  readonly forecastToolFunction: lambda.IFunction;
  readonly forecastToolTimeoutSeconds: number;
  readonly appTimezone: string;
  readonly clusterArn: string;
  readonly appSecretArn: string;
  readonly dbName: string;
  readonly dbResumeMaxWaitSeconds: number;
  /** Bảng đếm lượt gọi model (`yofina-usage`) mà `LlmGateway` dùng để giữ trần ngày. */
  readonly usageTableName: string;
}

/** Ba loại sự kiện mà `yofina_roadmap.events.parse_event` nhận, cùng nguồn bắt buộc của từng loại. */
export const ROADMAP_TRIGGERS: ReadonlyArray<{ id: string; detailType: string; source: string; description: string }> = [
  {
    id: 'RegenerationRequested',
    detailType: 'roadmap.regeneration_requested',
    source: 'yofina.ledger',
    description: 'POST /roadmap/regenerate da ghi roadmap_jobs -> hang doi yofina-roadmap-events',
  },
  {
    id: 'BehaviorChanged',
    detailType: 'behavior.changed',
    source: 'yofina.forecast',
    description: 'PELT xac nhan doi hanh vi chi tieu -> hang doi yofina-roadmap-events',
  },
  {
    id: 'ProfileUpdated',
    detailType: 'profile.updated',
    source: 'yofina.ledger',
    description: 'Ho so doi (luong, hu, muc tieu) -> hang doi yofina-roadmap-events',
  },
];

/**
 * Lambda `yofina-roadmap-regen` (Python 3.13 arm64, ngoài VPC): ba rule trên `yofina-bus` (lọc `source` và `detail-type`, gửi NGUYÊN
 * phong bì) -> SQS `yofina-roadmap-events` (+DLQ, alarm) -> Lambda (lô 1, partial batch response, đồng thời tối đa 2).
 * Lambda chạy cùng mã Roadmap agent và gọi đồng bộ hai Lambda tool bằng `lambda:InvokeFunction` (bỏ qua Gateway và Cedar, nên quyền
 * Invoke chỉ cấp cho đúng hai hàm). DB qua Data API bằng secret của role `yofina_app`, không bao giờ secret master.
 */
export class RoadmapRegen extends Construct {
  public readonly fn: lambda.Function;
  public readonly queue: sqs.Queue;
  public readonly deadLetterQueue: sqs.Queue;

  constructor(scope: Construct, id: string, props: RoadmapRegenProps) {
    super(scope, id);
    const { cfg, roadmap: c, bus, alertTopic } = props;
    const p = cfg.prefix;
    const stack = Stack.of(this);

    if (props.dbResumeMaxWaitSeconds >= c.timeoutSeconds) {
      throw new Error('dbResumeMaxWaitSeconds phải nhỏ hơn roadmapTimeoutSeconds');
    }
    // Đọc kết quả Invoke phải chờ hết timeout của Lambda tool, nếu không job báo tool lỗi trong khi tool vẫn chạy.
    const readTimeout =
      c.invokeReadTimeoutSeconds ?? Math.max(props.ledgerTimeoutSeconds, props.forecastToolTimeoutSeconds) + c.invokeReadMarginSeconds;
    if (readTimeout >= c.timeoutSeconds) {
      throw new Error('roadmapInvokeReadTimeoutSeconds phải nhỏ hơn roadmapTimeoutSeconds');
    }

    let code: lambda.Code;
    if (fs.existsSync(c.zip)) {
      code = lambda.Code.fromAsset(c.zip);
    } else {
      Annotations.of(this).addError(`Chưa có ${c.zip}. Chạy: ${ROADMAP_BUILD_COMMAND} (hoặc -c roadmapZip=<đường dẫn>)`);
      code = lambda.Code.fromInline('raise RuntimeError("roadmap zip missing")');
    }

    this.fn = new lambda.Function(this, 'Fn', {
      functionName: `${p}-roadmap-regen`,
      description: 'F5 sinh lai lo trinh chay nen: consumer SQS cua roadmap.regeneration_requested, behavior.changed, profile.updated',
      runtime: lambda.Runtime.PYTHON_3_13,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code,
      memorySize: c.memoryMb,
      timeout: Duration.seconds(c.timeoutSeconds),
      logGroup: new logs.LogGroup(this, 'FnLogs', {
        logGroupName: `/aws/lambda/${p}-roadmap-regen`,
        retention: cfg.logRetentionDays as logs.RetentionDays,
        removalPolicy: RemovalPolicy.DESTROY,
      }),
      environment: {
        YOFINA_REGION: cfg.region,
        YOFINA_LOG_LEVEL: 'INFO',
        // yofina_core.llm đọc ghi đè ở nhánh SSM /yofina/llm; AgentSettings tự bỏ khóa này nên không tra SSM của chat
        YOFINA_SSM_PREFIX: `/${p}`,
        YOFINA_DB_CLUSTER_ARN: props.clusterArn,
        YOFINA_DB_APP_SECRET_ARN: props.appSecretArn,
        YOFINA_DB_NAME: props.dbName,
        YOFINA_DB_RESUME_MAX_WAIT_SECONDS: String(props.dbResumeMaxWaitSeconds),
        YOFINA_APP_TIMEZONE: props.appTimezone,
        YOFINA_EVENT_BUS_NAME: bus.eventBusName,
        YOFINA_USAGE_TABLE: props.usageTableName,
        YOFINA_ROADMAP_LEDGER_FUNCTION_NAME: props.ledgerFunction.functionName,
        YOFINA_ROADMAP_FORECAST_FUNCTION_NAME: props.forecastToolFunction.functionName,
        YOFINA_ROADMAP_INVOKE_CONNECT_TIMEOUT_SECONDS: String(c.invokeConnectTimeoutSeconds),
        YOFINA_ROADMAP_INVOKE_READ_TIMEOUT_SECONDS: String(readTimeout),
        YOFINA_ROADMAP_RUNNING_LEASE_SECONDS: String(c.runningLeaseSeconds),
        YOFINA_ROADMAP_STAGE_PROGRESS: c.stageProgress,
      },
    });

    // --- IAM tối thiểu -------------------------------------------------------------------------------------------------------
    this.fn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'DataApiAppRole',
        actions: [
          'rds-data:ExecuteStatement',
          'rds-data:BeginTransaction',
          'rds-data:CommitTransaction',
          'rds-data:RollbackTransaction',
        ],
        resources: [props.clusterArn],
      }),
    );
    this.fn.addToRolePolicy(
      new iam.PolicyStatement({ sid: 'ReadAppSecretOnly', actions: ['secretsmanager:GetSecretValue'], resources: [props.appSecretArn] }),
    );
    // Đường này bỏ qua Gateway và Cedar: chỉ đúng hai Lambda tool (ledger phục vụ cả target planner; forecast là hàm tool).
    this.fn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'InvokeToolLambdas',
        actions: ['lambda:InvokeFunction'],
        resources: [props.ledgerFunction.functionArn, props.forecastToolFunction.functionArn],
      }),
    );
    this.fn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'CountModelCalls',
        actions: ['dynamodb:UpdateItem'],
        resources: [stack.formatArn({ service: 'dynamodb', resource: 'table', resourceName: props.usageTableName })],
      }),
    );
    // Khóa roadmap_*, bảng usage và DB bắt buộc đều có trong env nên không tra SSM. Chỉ còn: nhánh /yofina/llm đọc gộp
    // (GetParametersByPath, yofina_core.llm) và khóa DB tùy chọn vắng trong env (db_resume_sleep_seconds) đi GetParameter, phải nhận
    // ParameterNotFound thay vì AccessDenied.
    const ssmArn = (name: string) => stack.formatArn({ service: 'ssm', resource: 'parameter', resourceName: name });
    this.fn.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'ReadConfig',
        actions: ['ssm:GetParameter', 'ssm:GetParametersByPath'],
        resources: [ssmArn(`${p}/llm`), ssmArn(`${p}/llm/*`), ssmArn(`${p}/db_*`)],
      }),
    );

    // Bedrock: model của các vai cấu hình (mặc định `planner`), đọc lúc synth từ llm_defaults.json.
    const llm = JSON.parse(fs.readFileSync(c.llmDefaults, 'utf-8')) as LlmDefaults;
    const modelIds: string[] = [];
    for (const role of c.llmRoles) {
      const r = llm.roles[role];
      if (!r) {
        Annotations.of(this).addError(`roadmapLlmRoles: không có vai '${role}' trong llm_defaults.json`);
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
      // Global cross-Region inference, mẫu 3 phần của tài liệu Bedrock: profile ở Region gọi, foundation model ở Region gọi, và
      // foundation model không Region (mọi Region đích, `aws:RequestedRegion = unspecified`), hai cái sau chỉ khi đi qua đúng profile.
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
      bedrock.push(new iam.PolicyStatement({ sid: 'InvokeRegionalModels', actions: ['bedrock:InvokeModel'], resources: directModelArns }));
    }
    for (const st of bedrock) this.fn.addToRolePolicy(st);

    // --- đường sự kiện: yofina-bus -> SQS (+DLQ) -> yofina-roadmap-regen ---------------------------------------------------------
    this.deadLetterQueue = new sqs.Queue(this, 'EventsDlq', {
      queueName: `${p}-roadmap-events-dlq`,
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      retentionPeriod: Duration.days(14),
      enforceSSL: true,
    });
    this.queue = new sqs.Queue(this, 'Events', {
      queueName: `${p}-roadmap-events`,
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      visibilityTimeout: Duration.seconds(c.visibilityTimeoutSeconds),
      retentionPeriod: Duration.days(c.retentionDays),
      enforceSSL: true,
      deadLetterQueue: { queue: this.deadLetterQueue, maxReceiveCount: c.maxReceiveCount },
    });
    // Đích SqsQueue không có `message`: EventBridge gửi nguyên phong bì (handler đọc `source`, `detail-type`, `detail`).
    // CDK thêm queue policy cho events.amazonaws.com với `aws:SourceArn` là ARN của từng rule.
    for (const t of ROADMAP_TRIGGERS) {
      new events.Rule(this, `${t.id}Rule`, {
        ruleName: `${p}-roadmap-${t.detailType.replace(/[._]/g, '-')}`,
        description: t.description,
        eventBus: bus,
        eventPattern: { source: [t.source], detailType: [t.detailType] },
        targets: [new targets.SqsQueue(this.queue)],
      });
    }
    this.fn.addEventSource(
      new lambdaEventSources.SqsEventSource(this.queue, {
        batchSize: c.batchSize,
        maxBatchingWindow: Duration.seconds(0),
        reportBatchItemFailures: true,
        maxConcurrency: c.maxConcurrency,
      }),
    );
    new cloudwatch.Alarm(this, 'DlqAlarm', {
      alarmName: `${p}-roadmap-events-dlq-not-empty`,
      alarmDescription: 'Co su kien sinh lai lo trinh khong xu ly duoc (da vao DLQ yofina-roadmap-events-dlq): kiem log yofina-roadmap-regen',
      metric: this.deadLetterQueue.metricApproximateNumberOfMessagesVisible({ period: Duration.minutes(1), statistic: 'Maximum' }),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    }).addAlarmAction(new cwActions.SnsAction(alertTopic));
  }
}
