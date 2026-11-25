import * as fs from 'fs';
import * as path from 'path';
import { Annotations, App, ArnFormat, Aws, CfnOutput, Duration, Fn, RemovalPolicy, Stack, StackProps } from 'aws-cdk-lib';
import { Construct, IConstruct } from 'constructs';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cwActions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as lambdaEventSources from 'aws-cdk-lib/aws-lambda-event-sources';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { YofinaConfig } from '../config/config';
import { loadClassifyConfig } from './classify';
import { publishParams } from './ssm-outputs';
import { ToolsConfig } from './tools-stack';

/**
 * Cấu hình riêng của stack `YofinaIngest` (F6: nạp dữ liệu từ ảnh và CSV, phase 5). Đổi bằng context `-c khóa=giá trị`.
 * Giá trị nghiệp vụ dùng chung với ledger (TTL token, offer TTL, chờ Aurora, đồng hồ mô phỏng, hạn mức) KHÔNG nằm ở đây:
 * lấy từ `ToolsConfig` (cùng nguồn, cùng context) để hai Lambda không lệch nhau.
 */
export interface IngestConfig {
  /** Zip chung của hai Lambda (`handler_api`, `handler_worker`), đóng bằng scripts/build_lambda.py (`INGEST_BUILD_COMMAND`). */
  readonly zip: string;
  readonly apiMemoryMb: number;
  readonly apiTimeoutSeconds: number;
  readonly workerMemoryMb: number;
  readonly workerTimeoutSeconds: number;
  /**
   * Reserved concurrency của worker. 0 = không đặt (mặc định): tài khoản hiện có quota 10 lần chạy đồng thời và Lambda bắt
   * buộc giữ tối thiểu 10 unreserved, nên đặt bất kỳ giá trị nào cũng làm deploy lỗi. Trần thật nằm ở `workerMaxConcurrency`
   * của event source SQS (worker chỉ được gọi qua SQS). Nâng quota rồi mới đặt, ví dụ `-c ingestWorkerReservedConcurrency=2`.
   */
  readonly workerReservedConcurrency: number;
  /** Số worker SQS chạy song song tối đa (tối thiểu 2 theo AWS); giữ thấp vì Claude 4.x chỉ khoảng 8–10 request/phút. */
  readonly workerMaxConcurrency: number;
  /** SQS giao lại tối đa từng này lần trước khi vào DLQ. */
  readonly maxReceiveCount: number;
  /** Xóa tệp người dùng tải lên sau N ngày. */
  readonly objectExpirationDays: number;
  /** Hủy multipart upload dở sau N ngày. */
  readonly abortMultipartDays: number;
  /** Tiền tố khóa của tệp người dùng (`u/{user_id}/{job_id}`); chỉ tiền tố này kích hoạt worker. */
  readonly uploadPrefix: string;
  /**
   * Vai model trong `llm_defaults.json` mà worker được gọi (quyền Bedrock lấy từ chuỗi model của các vai này): `ingest` (đọc ảnh:
   * Sonnet 4.6, dự phòng Kimi K3), `ingest_columns` (ánh xạ cột và gắn nhãn CSV: model nhỏ) và `embedding` (Cohere Embed, bước k-NN
   * của bộ phân loại phase 4 khi gán hũ cho dòng nạp). Vai chưa có trong file thì bỏ qua kèm cảnh báo; không vai nào có thì stack báo
   * lỗi (không có model nào để cấp quyền).
   */
  readonly llmRoles: string[];
  /** Cửa sổ lịch sử của độ phủ dữ liệu (ngày): CÙNG context `forecastHistoryWindowDays` với pipeline dự báo, để hai bên cùng một công thức. */
  readonly forecastHistoryWindowDays: number;
  /** Đường dẫn `llm_defaults.json` (mặc định là file của yofina_core; test đổi bằng context `ingestLlmDefaults`). */
  readonly llmDefaults: string;
  /**
   * Ghi đè ngưỡng của bộ phân loại phase 4 (CÙNG context `classifyThresholds` với Lambda `yofina-classify`, xem `classify.ts`): worker
   * gán hũ cho dòng nạp bằng đúng bộ phân loại đó, nên hai Lambda phải cùng ngưỡng. Vào worker dưới dạng `YOFINA_CLASSIFY_<TÊN HOA>`.
   */
  readonly classifyThresholdOverrides: Record<string, string>;
}

/** Lệnh đóng zip của hai Lambda ingest (luồng backend xác nhận). */
export const INGEST_BUILD_COMMAND =
  'uv run scripts/build_lambda.py gateway/tools/ingest --arch arm64 --name ingest ' +
  '--extra pipelines/ingest/yofina_ingest:yofina_ingest --extra gateway/tools/ledger/yofina_ledger:yofina_ledger ' +
  '--extra pipelines/classify/yofina_classify:yofina_classify --extra db/seed:seed';

/** Route REST của F6. Chỉ GET/POST: CORS preflight của `yofina-api` (YofinaTools) chỉ cho GET, POST, OPTIONS. */
export const INGEST_ROUTES: ReadonlyArray<readonly [method: 'GET' | 'POST', path: string]> = [
  ['POST', '/ingest/uploads'],
  ['GET', '/ingest/jobs'],
  ['GET', '/ingest/jobs/{job_id}'],
  ['POST', '/ingest/rows/{row_id}/jar'],
  ['POST', '/ingest/confirmations'],
  ['POST', '/ingest/actions'],
];

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

export function loadIngestConfig(app: App): IngestConfig {
  const workerMax = ctxNum(app, 'ingestWorkerMaxConcurrency', 2);
  if (workerMax < 2 || workerMax > 1000) throw new Error('ingestWorkerMaxConcurrency phải trong 2..1000 (giới hạn của SQS event source)');
  const prefix = ctxStr(app, 'ingestUploadPrefix', 'u/');
  if (!prefix.endsWith('/')) throw new Error('ingestUploadPrefix phải kết thúc bằng /');
  return {
    zip: path.resolve(__dirname, '..', ctxStr(app, 'ingestZip', '../build/lambda/ingest-arm64.zip')),
    apiMemoryMb: ctxNum(app, 'ingestApiMemoryMb', 512),
    apiTimeoutSeconds: ctxNum(app, 'ingestApiTimeoutSeconds', 30),
    workerMemoryMb: ctxNum(app, 'ingestWorkerMemoryMb', 1024),
    workerTimeoutSeconds: ctxNum(app, 'ingestWorkerTimeoutSeconds', 120),
    workerReservedConcurrency: ctxNum(app, 'ingestWorkerReservedConcurrency', 0),
    workerMaxConcurrency: workerMax,
    maxReceiveCount: ctxNum(app, 'ingestMaxReceiveCount', 3),
    objectExpirationDays: ctxNum(app, 'ingestObjectExpirationDays', 30),
    abortMultipartDays: ctxNum(app, 'ingestAbortMultipartDays', 1),
    uploadPrefix: prefix,
    forecastHistoryWindowDays: ctxNum(app, 'forecastHistoryWindowDays', 330),
    llmRoles: ctxStr(app, 'ingestLlmRoles', 'ingest,ingest_columns,embedding')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    llmDefaults: path.resolve(
      __dirname,
      '..',
      ctxStr(app, 'ingestLlmDefaults', '../libs/yofina_core/src/yofina_core/llm_defaults.json'),
    ),
    classifyThresholdOverrides: loadClassifyConfig(app).thresholdOverrides,
  };
}

export interface IngestProps extends StackProps {
  readonly cfg: YofinaConfig;
  readonly tools: ToolsConfig;
  readonly ingest: IngestConfig;
}

interface LlmDefaults {
  roles: Record<string, { models: Array<{ id: string }> }>;
}

/** Đích SQS cho S3 notification, với queue policy có CẢ `aws:SourceArn` và `aws:SourceAccount` (bản có sẵn của CDK chỉ có SourceArn). */
class QueueDestination implements s3.IBucketNotificationDestination {
  constructor(private readonly queue: sqs.IQueue) {}

  bind(_scope: Construct, bucket: s3.IBucket): s3.BucketNotificationDestinationConfig {
    this.queue.addToResourcePolicy(
      new iam.PolicyStatement({
        sid: 'AllowIngestBucketNotifications',
        principals: [new iam.ServicePrincipal('s3.amazonaws.com')],
        actions: ['sqs:SendMessage'],
        resources: [this.queue.queueArn],
        conditions: {
          ArnLike: { 'aws:SourceArn': bucket.bucketArn },
          StringEquals: { 'aws:SourceAccount': Aws.ACCOUNT_ID },
        },
      }),
    );
    const deps: IConstruct[] = [this.queue];
    const policy = this.queue.node.tryFindChild('Policy');
    if (policy) deps.push(policy);
    return { arn: this.queue.queueArn, type: s3.BucketNotificationDestinationType.QUEUE, dependencies: deps };
  }
}

/**
 * F6, nạp dữ liệu từ ảnh và CSV: bucket `yofina-ingest-*` (presigned POST từ trình duyệt), S3 ObjectCreated `u/` -> SQS
 * `yofina-ingest-jobs` (+DLQ, alarm) -> Lambda worker `yofina-ingest`; Lambda `yofina-ingest-api` phục vụ 6 route `/ingest/*` gắn
 * vào HTTP API `yofina-api` CÓ SẴN (stack YofinaTools không bị sửa; route, integration, authorizer thuộc stack này).
 *
 * Giá trị của stack khác đọc từ SSM `/yofina/...` lúc deploy (không `Fn::ImportValue`), nên deploy/xóa riêng được: xóa stack
 * này thì route `/ingest/*` mất, API và route của ledger không ảnh hưởng.
 */
export class IngestStack extends Stack {
  public readonly bucket: s3.Bucket;
  public readonly queue: sqs.Queue;
  public readonly deadLetterQueue: sqs.Queue;
  public readonly api: lambda.Function;
  public readonly worker: lambda.Function;

  constructor(scope: Construct, id: string, props: IngestProps) {
    super(scope, id, props);
    const { cfg, tools, ingest } = props;
    const p = cfg.prefix;
    const param = (name: string) => ssm.StringParameter.valueForStringParameter(this, `/${p}/${name}`);

    if (tools.dbResumeMaxWaitSeconds >= Math.min(ingest.apiTimeoutSeconds, ingest.workerTimeoutSeconds)) {
      throw new Error('dbResumeMaxWaitSeconds phải nhỏ hơn ingestApiTimeoutSeconds và ingestWorkerTimeoutSeconds');
    }

    const clusterArn = param('db/cluster-arn');
    const appSecretArn = param('db/app-secret-arn');
    const dbName = param('db/name');
    const hmacSecretArn = param('secrets/confirm-hmac-arn');
    const jtiTable = param('dynamodb/confirm-jti-table');
    const usageTable = param('dynamodb/usage-table');
    const userPoolId = param('auth/user-pool-id');
    const clientId = param('auth/client-id');
    const amplifyUrl = param('frontend/amplify-url');
    const apiUrl = param('api/url');
    const forecastBatchName = param('forecast/batch-function-name');
    const alertTopic = sns.Topic.fromTopicArn(this, 'AlertTopic', param('sns/alert-topic-arn'));

    // --- bucket tệp tải lên --------------------------------------------------------------------------------------------
    // RETAIN như bucket artifact (quy ước của dự án cho S3): đây là dữ liệu người dùng; vòng đời tự xóa object sau
    // `objectExpirationDays`, nên bucket giữ lại khi xóa stack gần như rỗng. Tạo lại stack thì phải xóa tay bucket cũ (tên cố định).
    this.bucket = new s3.Bucket(this, 'Uploads', {
      bucketName: `${p}-ingest-${Aws.ACCOUNT_ID}-${Aws.REGION}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      versioned: false,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      removalPolicy: RemovalPolicy.RETAIN,
      lifecycleRules: [
        { id: 'abort-incomplete-multipart', abortIncompleteMultipartUploadAfter: Duration.days(ingest.abortMultipartDays) },
        { id: 'expire-uploads', expiration: Duration.days(ingest.objectExpirationDays) },
      ],
      // Presigned POST từ trình duyệt: form multipart gửi thẳng tới S3, cần CORS cho POST từ Amplify và localhost.
      cors: [
        {
          id: 'presigned-post',
          allowedMethods: [s3.HttpMethods.POST],
          allowedOrigins: [amplifyUrl, ...tools.extraCorsOrigins],
          allowedHeaders: ['content-type'],
          exposedHeaders: ['ETag', 'Location'],
          maxAge: 3600,
        },
      ],
    });
    const userObjects = this.bucket.arnForObjects(`${ingest.uploadPrefix}*`);

    // --- hàng đợi job + DLQ ------------------------------------------------------------------------------------------
    this.deadLetterQueue = new sqs.Queue(this, 'JobsDlq', {
      queueName: `${p}-ingest-jobs-dlq`,
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      retentionPeriod: Duration.days(14),
      enforceSSL: true,
    });
    this.queue = new sqs.Queue(this, 'Jobs', {
      queueName: `${p}-ingest-jobs`,
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      // khuyến nghị của AWS: tối thiểu 6 lần timeout của hàm tiêu thụ
      visibilityTimeout: Duration.seconds(ingest.workerTimeoutSeconds * 6),
      retentionPeriod: Duration.days(4),
      enforceSSL: true,
      deadLetterQueue: { queue: this.deadLetterQueue, maxReceiveCount: ingest.maxReceiveCount },
    });
    this.bucket.addEventNotification(s3.EventType.OBJECT_CREATED, new QueueDestination(this.queue), {
      prefix: ingest.uploadPrefix,
    });
    new cloudwatch.Alarm(this, 'DlqAlarm', {
      alarmName: `${p}-ingest-jobs-dlq-not-empty`,
      alarmDescription: 'Co tep nap khong xu ly duoc (da vao DLQ yofina-ingest-jobs-dlq): kiem log yofina-ingest',
      metric: this.deadLetterQueue.metricApproximateNumberOfMessagesVisible({ period: Duration.minutes(1), statistic: 'Maximum' }),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    }).addAlarmAction(new cwActions.SnsAction(alertTopic));

    // --- mã Lambda -------------------------------------------------------------------------------------------------------
    // Thiếu zip thì KHÔNG ném lỗi lúc dựng (để synth/deploy các stack khác không bị chặn trước khi luồng backend có zip), mà
    // gắn lỗi vào stack này: CLI từ chối synth/deploy `YofinaIngest` và mã thay thế không bao giờ lên AWS.
    let code: lambda.Code;
    if (fs.existsSync(ingest.zip)) {
      code = lambda.Code.fromAsset(ingest.zip);
    } else {
      Annotations.of(this).addError(
        `Chưa có ${ingest.zip}. Chạy: ${INGEST_BUILD_COMMAND} (hoặc -c ingestZip=<đường dẫn>)`,
      );
      code = lambda.Code.fromInline('raise RuntimeError("ingest zip missing")');
    }

    // Biến môi trường: chỉ những khóa mà mã ingest đọc (yofina_core.config, yofina_core.db, yofina_core.confirm, yofina_core.llm,
    // yofina_ingest.settings). Giá trị dùng chung với ledger lấy từ ToolsConfig nên hai Lambda không lệch nhau.
    const environment = (timeoutSeconds: number): Record<string, string> => ({
      YOFINA_REGION: cfg.region,
      YOFINA_LOG_LEVEL: 'INFO',
      YOFINA_SSM_PREFIX: `/${p}`,
      // yofina_core.db (role yofina_app, không bao giờ secret master)
      YOFINA_DB_CLUSTER_ARN: clusterArn,
      YOFINA_DB_APP_SECRET_ARN: appSecretArn,
      YOFINA_DB_NAME: dbName,
      YOFINA_DB_RESUME_MAX_WAIT_SECONDS: String(tools.dbResumeMaxWaitSeconds),
      // F6
      YOFINA_INGEST_BUCKET: this.bucket.bucketName,
      YOFINA_INGEST_UPLOAD_PREFIX: ingest.uploadPrefix,
      YOFINA_INGEST_MAX_RECEIVE_COUNT: String(ingest.maxReceiveCount),
      // yofina_core.confirm (cùng khóa HMAC và bảng jti với ledger)
      YOFINA_CONFIRM_HMAC_SECRET_ARN: hmacSecretArn,
      YOFINA_CONFIRM_JTI_TABLE: jtiTable,
      YOFINA_CONFIRM_TOKEN_TTL_SECONDS: String(tools.confirmTokenTtlSeconds),
      YOFINA_CONFIRM_TOKEN_MAX_TTL_SECONDS: String(tools.confirmTokenTtlSeconds),
      YOFINA_CONFIRM_OFFER_TTL_SECONDS: String(tools.confirmOfferTtlSeconds),
      // tính lại dự báo sau khi chốt (ledger gọi cùng Lambda khi đặt lại demo) và cửa sổ độ phủ dữ liệu
      YOFINA_FORECAST_FUNCTION_NAME: forecastBatchName,
      YOFINA_FORECAST_SYNC_TIMEOUT_SECONDS: String(Math.max(timeoutSeconds - 8, 5)),
      YOFINA_FORECAST_HISTORY_WINDOW_DAYS: String(ingest.forecastHistoryWindowDays),
      // đồng hồ mô phỏng (ADR-0003)
      YOFINA_APP_TIMEZONE: tools.appTimezone,
      // yofina_core.llm (worker) và yofina_core.quota (API, trần nạp tệp theo tài khoản): DynamoUsageStore đọc YOFINA_USAGE_TABLE
      YOFINA_USAGE_TABLE: usageTable,
    });

    const makeFn = (
      logicalId: string,
      name: string,
      handler: string,
      description: string,
      memoryMb: number,
      timeoutSeconds: number,
      extra: Partial<lambda.FunctionProps> = {},
    ): lambda.Function =>
      new lambda.Function(this, logicalId, {
        functionName: name,
        description,
        runtime: lambda.Runtime.PYTHON_3_13,
        architecture: lambda.Architecture.ARM_64,
        handler,
        code,
        memorySize: memoryMb,
        timeout: Duration.seconds(timeoutSeconds),
        logGroup: new logs.LogGroup(this, `${logicalId}Logs`, {
          logGroupName: `/aws/lambda/${name}`,
          retention: cfg.logRetentionDays as logs.RetentionDays,
          removalPolicy: RemovalPolicy.DESTROY,
        }),
        environment: environment(timeoutSeconds),
        ...extra,
      });

    this.api = makeFn(
      'Api',
      `${p}-ingest-api`,
      'handler_api.handler',
      'F6 nap du lieu: REST /ingest/* (presigned POST, tien do job, doi hu de xuat, xac nhan, chot dong)',
      ingest.apiMemoryMb,
      ingest.apiTimeoutSeconds,
    );
    this.worker = makeFn(
      'Worker',
      `${p}-ingest`,
      'handler_worker.handler',
      'F6 nap du lieu: worker SQS doc anh/CSV (Bedrock Converse), khu trung, de xuat hu',
      ingest.workerMemoryMb,
      ingest.workerTimeoutSeconds,
      ingest.workerReservedConcurrency > 0 ? { reservedConcurrentExecutions: ingest.workerReservedConcurrency } : {},
    );
    // Bộ phân loại phase 4 (gán hũ cho dòng nạp) đọc ngưỡng từ classify_defaults.json; ghi đè bằng đúng biến của yofina-classify.
    for (const [k, v] of Object.entries(ingest.classifyThresholdOverrides)) {
      this.worker.addEnvironment(`YOFINA_CLASSIFY_${k.toUpperCase()}`, v);
    }
    this.worker.addEventSource(
      new lambdaEventSources.SqsEventSource(this.queue, {
        batchSize: 1,
        maxBatchingWindow: Duration.seconds(0),
        reportBatchItemFailures: true,
        maxConcurrency: ingest.workerMaxConcurrency,
      }),
    );

    // --- IAM tối thiểu (mỗi Lambda một role do CDK sinh) -------------------------------------------------------------------
    // Đọc lúc synth như YofinaAgent. Vai chưa có (luồng backend thêm `ingest_vision`, `ingest_columns` sau) thì bỏ qua kèm
    // cảnh báo; không còn model nào thì stack báo lỗi (deploy Lambda gọi Bedrock mà không có quyền là vô nghĩa).
    const llm = JSON.parse(fs.readFileSync(ingest.llmDefaults, 'utf-8')) as LlmDefaults;
    const modelIds: string[] = [];
    for (const role of ingest.llmRoles) {
      const r = llm.roles[role];
      if (!r) {
        Annotations.of(this).addWarningV2(
          `yofina:ingest:llm-role-missing:${role}`,
          `ingestLlmRoles: chưa có vai '${role}' trong llm_defaults.json, bỏ qua (không cấp quyền Bedrock cho vai này)`,
        );
        continue;
      }
      for (const m of r.models) if (!modelIds.includes(m.id)) modelIds.push(m.id);
    }
    if (modelIds.length === 0) {
      Annotations.of(this).addError(
        `ingestLlmRoles (${ingest.llmRoles.join(',')}): không vai nào có trong llm_defaults.json, không có model để cấp quyền Bedrock`,
      );
    }
    // Global cross-Region inference theo mẫu 3 phần của tài liệu Bedrock: (1) profile `global.*` ở region gọi; (2) foundation
    // model ở region gọi, chỉ khi đi qua đúng profile đó; (3) foundation model không region (`arn:aws:bedrock:::`), Bedrock đặt
    // `aws:RequestedRegion` = `unspecified`, cũng chỉ qua đúng profile. Model không có tiền tố `global.` gọi thẳng ở region.
    const bedrockStatements: iam.PolicyStatement[] = [];
    const profileArns: string[] = [];
    const directModelArns: string[] = [];
    for (const m of modelIds) {
      if (!m.startsWith('global.')) {
        directModelArns.push(`arn:aws:bedrock:${this.region}::foundation-model/${m}`);
        continue;
      }
      const base = m.slice('global.'.length);
      const profileArn = `arn:aws:bedrock:${this.region}:${this.account}:inference-profile/${m}`;
      profileArns.push(profileArn);
      bedrockStatements.push(
        new iam.PolicyStatement({
          actions: ['bedrock:InvokeModel'],
          resources: [`arn:aws:bedrock:${this.region}::foundation-model/${base}`],
          conditions: { StringEquals: { 'aws:RequestedRegion': this.region, 'bedrock:InferenceProfileArn': profileArn } },
        }),
        new iam.PolicyStatement({
          actions: ['bedrock:InvokeModel'],
          resources: [`arn:aws:bedrock:::foundation-model/${base}`],
          conditions: { StringEquals: { 'aws:RequestedRegion': 'unspecified', 'bedrock:InferenceProfileArn': profileArn } },
        }),
      );
    }
    if (profileArns.length > 0) {
      bedrockStatements.unshift(
        new iam.PolicyStatement({
          sid: 'InvokeGlobalInferenceProfiles',
          actions: ['bedrock:InvokeModel'], // Converse dùng quyền bedrock:InvokeModel (không có action riêng)
          resources: profileArns,
          conditions: { StringEquals: { 'aws:RequestedRegion': this.region } },
        }),
      );
    }
    if (directModelArns.length > 0) {
      bedrockStatements.push(
        new iam.PolicyStatement({ sid: 'InvokeRegionalModels', actions: ['bedrock:InvokeModel'], resources: directModelArns }),
      );
    }
    const ssmArn = (name: string) => `arn:aws:ssm:${this.region}:${this.account}:parameter/${name}`;
    const forecastBatchArn = this.formatArn({
      service: 'lambda',
      resource: 'function',
      resourceName: forecastBatchName,
      arnFormat: ArnFormat.COLON_RESOURCE_NAME,
    });

    // Quyền chung của hai Lambda: Data API (role yofina_app) và đọc cấu hình. Mọi khóa `YOFINA_*` vắng trong môi trường đi
    // GetParameter (yofina_core.config), nên phải được phép để nhận ParameterNotFound thay vì AccessDenied.
    const configParams = [
      ssmArn(`${p}/ingest_*`),
      ssmArn(`${p}/db_*`),
      ssmArn(`${p}/confirm_*`),
      ssmArn(`${p}/forecast_*`),
    ];
    for (const fn of [this.api, this.worker]) {
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
          resources: [clusterArn],
        }),
      );
      // CHỈ secret của yofina_app (không master)
      fn.addToRolePolicy(
        new iam.PolicyStatement({
          sid: 'ReadAppSecretOnly',
          actions: ['secretsmanager:GetSecretValue'],
          resources: [appSecretArn],
        }),
      );
    }

    // --- worker: Bedrock, bộ đếm lượt gọi, đọc/xóa tệp người dùng ------------------------------------------------------------
    for (const st of bedrockStatements) this.worker.addToRolePolicy(st);
    this.worker.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'CountModelCalls',
        actions: ['dynamodb:UpdateItem'],
        resources: [this.formatArn({ service: 'dynamodb', resource: 'table', resourceName: usageTable })],
      }),
    );
    // yofina_core.llm đọc gộp nhánh /yofina/llm (GetParametersByPath) và khóa `dynamodb/usage-table` khi không có biến môi trường
    this.worker.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'ReadConfig',
        actions: ['ssm:GetParameter', 'ssm:GetParametersByPath'],
        resources: [ssmArn(`${p}/llm`), ssmArn(`${p}/llm/*`), ssmArn(`${p}/dynamodb/usage-table`), ...configParams],
      }),
    );
    this.worker.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'ReadAndDeleteUserUploads',
        // GetObject cũng là quyền của HeadObject; DeleteObject để worker xóa tệp gốc ngay khi đọc xong (không chờ vòng đời 30 ngày)
        actions: ['s3:GetObject', 's3:DeleteObject'],
        resources: [userObjects],
      }),
    );

    // --- API: khóa HMAC, token một lần, presigned POST, kích hoạt tính lại dự báo ---------------------------------------------
    // Presigned POST được S3 kiểm bằng quyền của role ký, nên role cần s3:PutObject; điều kiện `s3:authType = POST` làm quyền
    // này CHỈ dùng được qua form POST đã ký (Lambda không PutObject trực tiếp, không presigned PUT). Kích thước và Content-Type
    // do điều kiện `content-length-range`, `Content-Type` trong POST policy mà backend ký (S3 kiểm khi nhận form).
    this.api.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'ReadHmacSecretOnly',
        actions: ['secretsmanager:GetSecretValue'],
        resources: [hmacSecretArn],
      }),
    );
    this.api.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'ReadConfig',
        actions: ['ssm:GetParameter'],
        // yofina_core.quota: trần lượt nạp tệp mỗi tài khoản mỗi ngày (`quota/uploads_per_day`), đổi không cần deploy
        resources: [...configParams, ssmArn(`${p}/quota/*`)],
      }),
    );
    // yofina_core.quota: đếm lần nạp tệp mỗi tài khoản mỗi ngày ở bảng usage (phân vùng `quota#<ngày>`, khóa băm `sub`)
    this.api.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'CountUploads',
        actions: ['dynamodb:UpdateItem'],
        resources: [this.formatArn({ service: 'dynamodb', resource: 'table', resourceName: usageTable })],
      }),
    );
    this.api.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'SignPresignedPostOnly',
        actions: ['s3:PutObject'],
        resources: [userObjects],
        conditions: { StringEquals: { 's3:authType': 'POST' } },
      }),
    );
    this.api.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'ConsumeConfirmJti',
        actions: ['dynamodb:PutItem'],
        resources: [this.formatArn({ service: 'dynamodb', resource: 'table', resourceName: jtiTable })],
      }),
    );
    // sau khi chốt: tính lại dự báo ĐẦY ĐỦ (bất đồng bộ, như ledger khi đặt lại demo); lỗi không làm hỏng việc đã ghi
    this.api.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'InvokeForecastBatch',
        actions: ['lambda:InvokeFunction'],
        resources: [forecastBatchArn],
      }),
    );

    // --- route REST trên HTTP API yofina-api có sẵn -------------------------------------------------------------------------
    // api/url = https://<apiId>.execute-api.<region>.amazonaws.com: valueForStringParameter là tham số CFN kiểu SSM (Ref), dùng
    // được trong Fn::Split (khác dynamic reference {{resolve:ssm:...}}).
    const apiId = Fn.select(0, Fn.split('.', Fn.select(2, Fn.split('/', apiUrl))));
    // Authorizer riêng của stack này, CÙNG issuer/audience với `yofina-cognito` của YofinaTools: id của authorizer đó không có ở
    // SSM, và tra bằng custom resource phải dựa vào thứ tự mảng GetAuthorizers (không lọc theo tên được).
    const issuer = `https://cognito-idp.${cfg.region}.amazonaws.com/${userPoolId}`;
    const authorizer = new apigwv2.CfnAuthorizer(this, 'CognitoJwt', {
      apiId,
      name: `${p}-cognito-ingest`,
      authorizerType: 'JWT',
      identitySource: ['$request.header.Authorization'],
      jwtConfiguration: { issuer, audience: [clientId] },
    });
    const integration = new apigwv2.CfnIntegration(this, 'ApiIntegration', {
      apiId,
      integrationType: 'AWS_PROXY',
      integrationUri: this.api.functionArn,
      payloadFormatVersion: '2.0',
      timeoutInMillis: Math.min(ingest.apiTimeoutSeconds, 30) * 1000,
    });
    for (const [method, routePath] of INGEST_ROUTES) {
      new apigwv2.CfnRoute(this, `Route-${method}-${routePath.replace(/[^A-Za-z0-9]/g, '')}`, {
        apiId,
        routeKey: `${method} ${routePath}`,
        target: `integrations/${integration.ref}`,
        authorizationType: 'JWT',
        authorizerId: authorizer.ref,
      });
    }
    new lambda.CfnPermission(this, 'ApiInvokePermission', {
      action: 'lambda:InvokeFunction',
      functionName: this.api.functionArn,
      principal: 'apigateway.amazonaws.com',
      sourceAccount: this.account,
      sourceArn: `arn:aws:execute-api:${this.region}:${this.account}:${apiId}/*/*/ingest/*`,
    });

    publishParams(this, {
      'ingest/bucket-name': this.bucket.bucketName,
      'ingest/api-function-name': this.api.functionName,
      'ingest/worker-function-name': this.worker.functionName,
      'ingest/queue-url': this.queue.queueUrl,
    });
    new CfnOutput(this, 'IngestBucket', { value: this.bucket.bucketName });
  }
}
