import * as path from 'path';
import { App, Duration, RemovalPolicy } from 'aws-cdk-lib';
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
import * as scheduler from 'aws-cdk-lib/aws-scheduler';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import { YofinaConfig } from '../config/config';

/**
 * Cấu hình pipeline dự báo (phase 2, luồng C). Mọi giá trị đổi được bằng context `-c khóa=giá trị`; các giá trị nghiệp vụ được
 * truyền vào Lambda dưới dạng biến môi trường `YOFINA_FORECAST_*` (xem pipelines/forecast/yofina_forecast/settings.py), không gắn
 * cứng trong mã.
 */
export interface ForecastPipelineConfig {
  /** Zip Lambda dự báo (scripts/build_lambda.py pipelines/forecast ... --slim): batch, consumer sự kiện và tool dùng chung một zip. */
  readonly zip: string;
  readonly memoryMb: number;
  readonly batchTimeoutSeconds: number;
  readonly eventTimeoutSeconds: number;
  readonly toolTimeoutSeconds: number;
  readonly horizonDays: number;
  readonly historyWindowDays: number;
  readonly nPathsFull: number;
  readonly nPathsFast: number;
  readonly coldStartMinDays: number;
  readonly aciGamma: number;
  readonly coverageTarget: number;
  readonly shortThreshold: number;
  readonly tightThreshold: number;
  readonly bandHighMinDays: number;
  readonly bandHighMinCoverage: number;
  readonly bandMediumMinDays: number;
  /** Công tắc xác suất: false thì chỉ hiện nhóm Cao/Vừa/Thấp bất kể kết quả hiệu chỉnh. */
  readonly probabilityEnabled: boolean;
  readonly keepRuns: number;
  readonly fastMaxAgeSeconds: number;
  readonly recomputeGuardSeconds: number;
  readonly idempotencyTtlSeconds: number;
  readonly idempotencyLeaseSeconds: number;
  readonly nightlyMaxUsers: number;
  readonly nightlyConcurrency: number;
  /** Giờ và phút chạy batch đêm (múi giờ Asia/Ho_Chi_Minh, đặt ở `appTimezone` của YofinaTools). */
  readonly nightlyHour: number;
  readonly nightlyMinute: number;
  /** Số Lambda consumer chạy đồng thời tối đa (Aurora 0,5 ACU nên giữ thấp). */
  readonly eventMaxConcurrency: number;
  readonly eventBatchSize: number;
  /** SQS giao lại tối đa từng này lần trước khi vào DLQ. */
  readonly eventMaxReceiveCount: number;
}

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

function ctxBool(app: App, key: string, dflt: boolean): boolean {
  const v = app.node.tryGetContext(key);
  if (v === undefined || v === null || v === '') return dflt;
  return String(v).toLowerCase() === 'true' || String(v) === '1';
}

export function loadForecastConfig(app: App): ForecastPipelineConfig {
  const batchTimeout = ctxNum(app, 'forecastBatchTimeoutSeconds', 120);
  const eventTimeout = ctxNum(app, 'forecastEventTimeoutSeconds', 90);
  return {
    zip: path.resolve(__dirname, '..', ctxStr(app, 'forecastZip', '../build/lambda/forecast-arm64.zip')),
    memoryMb: ctxNum(app, 'forecastMemoryMb', 1769),
    batchTimeoutSeconds: batchTimeout,
    eventTimeoutSeconds: eventTimeout,
    toolTimeoutSeconds: ctxNum(app, 'forecastToolTimeoutSeconds', 60),
    horizonDays: ctxNum(app, 'forecastHorizonDays', 30),
    historyWindowDays: ctxNum(app, 'forecastHistoryWindowDays', 330),
    nPathsFull: ctxNum(app, 'forecastNPathsFull', 10000),
    nPathsFast: ctxNum(app, 'forecastNPathsFast', 5000),
    coldStartMinDays: ctxNum(app, 'forecastColdStartMinDays', 21),
    aciGamma: ctxNum(app, 'forecastAciGamma', 0.01),
    coverageTarget: ctxNum(app, 'forecastCoverageTarget', 0.8),
    shortThreshold: ctxNum(app, 'forecastShortThreshold', 0.5),
    tightThreshold: ctxNum(app, 'forecastTightThreshold', 0.2),
    bandHighMinDays: ctxNum(app, 'forecastBandHighMinDays', 60),
    bandHighMinCoverage: ctxNum(app, 'forecastBandHighMinCoverage', 0.7),
    bandMediumMinDays: ctxNum(app, 'forecastBandMediumMinDays', 21),
    probabilityEnabled: ctxBool(app, 'forecastProbabilityEnabled', true),
    keepRuns: ctxNum(app, 'forecastKeepRuns', 6),
    fastMaxAgeSeconds: ctxNum(app, 'forecastFastMaxAgeSeconds', 86400),
    recomputeGuardSeconds: ctxNum(app, 'forecastRecomputeGuardSeconds', 20),
    idempotencyTtlSeconds: ctxNum(app, 'forecastIdempotencyTtlSeconds', 259200),
    idempotencyLeaseSeconds: ctxNum(app, 'forecastIdempotencyLeaseSeconds', Math.max(eventTimeout + 30, 120)),
    nightlyMaxUsers: ctxNum(app, 'forecastNightlyMaxUsers', 200),
    nightlyConcurrency: ctxNum(app, 'forecastNightlyConcurrency', 3),
    nightlyHour: ctxNum(app, 'forecastNightlyHour', 2),
    nightlyMinute: ctxNum(app, 'forecastNightlyMinute', 0),
    eventMaxConcurrency: ctxNum(app, 'forecastEventMaxConcurrency', 5),
    eventBatchSize: ctxNum(app, 'forecastEventBatchSize', 10),
    eventMaxReceiveCount: ctxNum(app, 'forecastEventMaxReceiveCount', 3),
  };
}

export interface ForecastPipelineProps {
  readonly cfg: YofinaConfig;
  readonly forecast: ForecastPipelineConfig;
  readonly bus: events.IEventBus;
  readonly alertTopic: sns.ITopic;
  readonly appTimezone: string;
  readonly freshnessSeconds: number;
  readonly clusterArn: string;
  readonly appSecretArn: string;
  readonly dbName: string;
  readonly dbResumeMaxWaitSeconds: number;
  readonly region: string;
}

/**
 * Pipeline dự báo: ba Lambda dùng CHUNG một zip (Python 3.13 arm64, ngoài VPC, gọi Aurora qua Data API bằng secret của role
 * `yofina_app`, không bao giờ secret master):
 *
 * - `yofina-forecast-batch`: batch đêm, đặt lại demo, tính lại khi đọc cũ (op `list_users`, `run_user`, `run_users`, `summarize`);
 * - `yofina-on-transaction`: consumer SQS của sự kiện ledger (chỉnh nhanh hoặc chạy đầy đủ), idempotent theo `event_id`;
 * - `yofina-forecast`: target `forecast` của AgentCore Gateway (tool `forecast___get_forecast`).
 *
 * Cộng: bảng DynamoDB `yofina-idempotency` (khóa `event_id`, TTL), rule trên `yofina-bus` -> SQS `yofina-forecast-events` (có DLQ và
 * alarm), Step Functions `yofina-nightly` (Standard) và EventBridge Scheduler 02:00 giờ Việt Nam, alarm thất bại -> SNS `yofina-alerts`.
 */
export class ForecastPipeline extends Construct {
  public readonly batch: lambda.Function;
  public readonly onTransaction: lambda.Function;
  public readonly tool: lambda.Function;
  public readonly queue: sqs.Queue;
  public readonly deadLetterQueue: sqs.Queue;
  public readonly idempotencyTable: dynamodb.Table;
  public readonly nightly: sfn.StateMachine;

  constructor(scope: Construct, id: string, props: ForecastPipelineProps) {
    super(scope, id);
    const { cfg, forecast: f, bus, alertTopic } = props;
    const p = cfg.prefix;

    // --- bảng idempotency: nằm cùng consumer (không đụng stack Foundation có termination protection), tự dọn bằng TTL ------------
    this.idempotencyTable = new dynamodb.Table(this, 'Idempotency', {
      tableName: `${p}-idempotency`,
      partitionKey: { name: 'event_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'ttl',
      removalPolicy: RemovalPolicy.DESTROY,
    });

    const environment: Record<string, string> = {
      YOFINA_REGION: props.region,
      YOFINA_LOG_LEVEL: 'INFO',
      YOFINA_DB_CLUSTER_ARN: props.clusterArn,
      YOFINA_DB_APP_SECRET_ARN: props.appSecretArn,
      YOFINA_DB_NAME: props.dbName,
      YOFINA_DB_RESUME_MAX_WAIT_SECONDS: String(props.dbResumeMaxWaitSeconds),
      YOFINA_APP_TIMEZONE: props.appTimezone,
      YOFINA_EVENT_BUS_NAME: bus.eventBusName,
      YOFINA_FORECAST_IDEMPOTENCY_TABLE: this.idempotencyTable.tableName,
      YOFINA_FORECAST_HORIZON_DAYS: String(f.horizonDays),
      YOFINA_FORECAST_HISTORY_WINDOW_DAYS: String(f.historyWindowDays),
      YOFINA_FORECAST_N_PATHS_FULL: String(f.nPathsFull),
      YOFINA_FORECAST_N_PATHS_FAST: String(f.nPathsFast),
      YOFINA_FORECAST_COLD_START_MIN_DAYS: String(f.coldStartMinDays),
      YOFINA_FORECAST_ACI_GAMMA: String(f.aciGamma),
      YOFINA_FORECAST_COVERAGE_TARGET: String(f.coverageTarget),
      YOFINA_FORECAST_SHORT_THRESHOLD: String(f.shortThreshold),
      YOFINA_FORECAST_TIGHT_THRESHOLD: String(f.tightThreshold),
      YOFINA_FORECAST_BAND_HIGH_MIN_DAYS: String(f.bandHighMinDays),
      YOFINA_FORECAST_BAND_HIGH_MIN_COVERAGE: String(f.bandHighMinCoverage),
      YOFINA_FORECAST_BAND_MEDIUM_MIN_DAYS: String(f.bandMediumMinDays),
      YOFINA_FORECAST_PROBABILITY_ENABLED: String(f.probabilityEnabled),
      YOFINA_FORECAST_KEEP_RUNS: String(f.keepRuns),
      YOFINA_FORECAST_FAST_MAX_AGE_SECONDS: String(f.fastMaxAgeSeconds),
      YOFINA_FORECAST_RECOMPUTE_GUARD_SECONDS: String(f.recomputeGuardSeconds),
      YOFINA_FORECAST_FRESHNESS_SECONDS: String(props.freshnessSeconds),
      YOFINA_FORECAST_IDEMPOTENCY_TTL_SECONDS: String(f.idempotencyTtlSeconds),
      YOFINA_FORECAST_IDEMPOTENCY_LEASE_SECONDS: String(f.idempotencyLeaseSeconds),
      YOFINA_FORECAST_NIGHTLY_MAX_USERS: String(f.nightlyMaxUsers),
    };

    const code = lambda.Code.fromAsset(f.zip);
    const makeFn = (
      logicalId: string,
      name: string,
      handler: string,
      description: string,
      timeoutSeconds: number,
    ): lambda.Function => {
      const fn = new lambda.Function(this, logicalId, {
        functionName: name,
        description,
        runtime: lambda.Runtime.PYTHON_3_13,
        architecture: lambda.Architecture.ARM_64,
        handler,
        code,
        memorySize: f.memoryMb,
        timeout: Duration.seconds(timeoutSeconds),
        logGroup: new logs.LogGroup(this, `${logicalId}Logs`, {
          logGroupName: `/aws/lambda/${name}`,
          retention: cfg.logRetentionDays as logs.RetentionDays,
          removalPolicy: RemovalPolicy.DESTROY,
        }),
        environment,
      });
      // IAM tối thiểu: Data API trên cluster + CHỈ secret của role yofina_app (không master) + phát sự kiện lên bus.
      fn.addToRolePolicy(
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
      fn.addToRolePolicy(
        new iam.PolicyStatement({
          sid: 'ReadAppSecretOnly',
          actions: ['secretsmanager:GetSecretValue'],
          resources: [props.appSecretArn],
        }),
      );
      fn.addToRolePolicy(
        new iam.PolicyStatement({
          sid: 'PublishForecastEvents',
          actions: ['events:PutEvents'],
          resources: [bus.eventBusArn],
        }),
      );
      return fn;
    };

    this.batch = makeFn(
      'Batch',
      `${p}-forecast-batch`,
      'handler_batch.lambda_handler',
      'Du bao: batch dem (Step Functions), dat lai demo, tinh lai khi doc cu',
      f.batchTimeoutSeconds,
    );
    this.onTransaction = makeFn(
      'OnTransaction',
      `${p}-on-transaction`,
      'handler_event.lambda_handler',
      'Du bao: consumer SQS cua su kien ledger (chinh nhanh hoac chay day du), idempotent theo event_id',
      f.eventTimeoutSeconds,
    );
    this.tool = makeFn(
      'Tool',
      `${p}-forecast`,
      'handler_tool.lambda_handler',
      'Tool forecast___get_forecast cho AgentCore Gateway (tinh lai truoc khi tra neu cu)',
      f.toolTimeoutSeconds,
    );
    this.idempotencyTable.grant(
      this.onTransaction,
      'dynamodb:PutItem',
      'dynamodb:GetItem',
      'dynamodb:UpdateItem',
      'dynamodb:DeleteItem',
    );

    // --- đường sự kiện: yofina-bus -> SQS (+DLQ) -> yofina-on-transaction --------------------------------------------------
    this.deadLetterQueue = new sqs.Queue(this, 'EventsDlq', {
      queueName: `${p}-forecast-events-dlq`,
      retentionPeriod: Duration.days(14),
      enforceSSL: true,
    });
    this.queue = new sqs.Queue(this, 'Events', {
      queueName: `${p}-forecast-events`,
      // khuyến nghị của AWS: tối thiểu 6 lần timeout của hàm tiêu thụ
      visibilityTimeout: Duration.seconds(f.eventTimeoutSeconds * 6),
      retentionPeriod: Duration.days(4),
      enforceSSL: true,
      deadLetterQueue: { queue: this.deadLetterQueue, maxReceiveCount: f.eventMaxReceiveCount },
    });
    new events.Rule(this, 'LedgerEventsRule', {
      ruleName: `${p}-forecast-ledger-events`,
      description: 'Su kien ledger lam doi du bao -> hang doi yofina-forecast-events',
      eventBus: bus,
      eventPattern: {
        source: ['yofina.ledger'],
        detailType: ['transaction.recorded', 'salary.confirmed', 'obligation.changed', 'profile.updated'],
      },
      targets: [new targets.SqsQueue(this.queue)],
    });
    this.onTransaction.addEventSource(
      new lambdaEventSources.SqsEventSource(this.queue, {
        batchSize: f.eventBatchSize,
        maxBatchingWindow: Duration.seconds(0),
        reportBatchItemFailures: true,
        maxConcurrency: f.eventMaxConcurrency,
      }),
    );
    new cloudwatch.Alarm(this, 'DlqAlarm', {
      alarmName: `${p}-forecast-events-dlq-not-empty`,
      alarmDescription: 'Co su kien ledger khong xu ly duoc (da vao DLQ yofina-forecast-events-dlq): kiem log yofina-on-transaction',
      metric: this.deadLetterQueue.metricApproximateNumberOfMessagesVisible({ period: Duration.minutes(1), statistic: 'Maximum' }),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    }).addAlarmAction(new cwActions.SnsAction(alertTopic));

    // --- batch đêm: liệt kê người dùng -> Map (giới hạn song song) -> yofina-forecast-batch -> tổng hợp ---------------------
    const listUsers = new tasks.LambdaInvoke(this, 'ListUsers', {
      lambdaFunction: this.batch,
      payload: sfn.TaskInput.fromObject({ op: 'list_users' }),
      payloadResponseOnly: true,
      resultPath: '$.list',
    });
    const runUser = new tasks.LambdaInvoke(this, 'RunUser', {
      lambdaFunction: this.batch,
      payload: sfn.TaskInput.fromObject({
        op: 'run_user',
        user_id: sfn.JsonPath.stringAt('$.user_id'),
        trigger: 'nightly',
      }),
      payloadResponseOnly: true,
    });
    // Aurora vừa tự dừng thì lần đầu có thể chưa sẵn sàng: thử lại có lùi; lỗi khác thì ghi nhận từng mục, không làm hỏng người khác.
    runUser.addRetry({ errors: ['DatabaseUnavailable'], interval: Duration.seconds(10), maxAttempts: 3, backoffRate: 2 });
    runUser.addCatch(
      new sfn.Pass(this, 'UserFailed', {
        parameters: { status: 'failed', 'user_id.$': '$.user_id', 'error.$': '$.error.Error' },
      }),
      { errors: ['States.ALL'], resultPath: '$.error' },
    );
    const forEachUser = new sfn.Map(this, 'ForEachUser', {
      itemsPath: sfn.JsonPath.stringAt('$.list.user_ids'),
      itemSelector: { 'user_id.$': '$$.Map.Item.Value' },
      maxConcurrency: f.nightlyConcurrency,
      resultPath: '$.results',
    });
    forEachUser.itemProcessor(runUser);
    const summarize = new tasks.LambdaInvoke(this, 'Summarize', {
      lambdaFunction: this.batch,
      payload: sfn.TaskInput.fromObject({ op: 'summarize', results: sfn.JsonPath.objectAt('$.results') }),
      payloadResponseOnly: true,
    });
    const stateLogs = new logs.LogGroup(this, 'NightlyLogs', {
      logGroupName: `/aws/vendedlogs/states/${p}-nightly`,
      retention: cfg.logRetentionDays as logs.RetentionDays,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    this.nightly = new sfn.StateMachine(this, 'Nightly', {
      stateMachineName: `${p}-nightly`,
      stateMachineType: sfn.StateMachineType.STANDARD,
      definitionBody: sfn.DefinitionBody.fromChainable(listUsers.next(forEachUser).next(summarize)),
      timeout: Duration.minutes(30),
      logs: { destination: stateLogs, level: sfn.LogLevel.ERROR },
    });

    // --- lịch 02:00 giờ Việt Nam (EventBridge Scheduler hỗ trợ múi giờ IANA, không cần đổi sang UTC) ----------------------------
    const schedulerRole = new iam.Role(this, 'SchedulerRole', {
      roleName: `${p}-nightly-scheduler`,
      assumedBy: new iam.ServicePrincipal('scheduler.amazonaws.com'),
    });
    this.nightly.grantStartExecution(schedulerRole);
    new scheduler.CfnSchedule(this, 'NightlySchedule', {
      name: `${p}-nightly-0200`,
      description: 'Chay yofina-nightly moi dem (du bao lai moi nguoi dung)',
      scheduleExpression: `cron(${f.nightlyMinute} ${f.nightlyHour} * * ? *)`,
      scheduleExpressionTimezone: props.appTimezone,
      flexibleTimeWindow: { mode: 'OFF' },
      target: {
        arn: this.nightly.stateMachineArn,
        roleArn: schedulerRole.roleArn,
        input: '{}',
        retryPolicy: { maximumRetryAttempts: 2, maximumEventAgeInSeconds: 3600 },
      },
    });

    // --- alarm khi execution thất bại hoặc quá thời gian -> SNS yofina-alerts ----------------------------------------------
    for (const [suffix, metric, desc] of [
      ['failed', this.nightly.metricFailed({ period: Duration.minutes(5) }), 'that bai'],
      ['timed-out', this.nightly.metricTimedOut({ period: Duration.minutes(5) }), 'qua thoi gian'],
    ] as const) {
      new cloudwatch.Alarm(this, `NightlyAlarm-${suffix}`, {
        alarmName: `${p}-nightly-${suffix}`,
        alarmDescription: `Step Functions yofina-nightly ${desc}: kiem execution va log yofina-forecast-batch`,
        metric,
        threshold: 1,
        evaluationPeriods: 1,
        comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      }).addAlarmAction(new cwActions.SnsAction(alertTopic));
    }
  }
}
