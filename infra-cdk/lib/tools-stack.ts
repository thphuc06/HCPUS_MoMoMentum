import * as fs from 'fs';
import * as path from 'path';
import { App, CfnOutput, Duration, RemovalPolicy, Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cwActions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as events from 'aws-cdk-lib/aws-events';
import * as sns from 'aws-cdk-lib/aws-sns';
import { HttpJwtAuthorizer } from 'aws-cdk-lib/aws-apigatewayv2-authorizers';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { YofinaConfig } from '../config/config';
import { ClassifyConfig, ClassifyPipeline } from './classify';
import { ForecastPipeline, ForecastPipelineConfig } from './forecast-pipeline';
import { loadOpsDashboardConfig, OpsDashboard, OpsDashboardConfig } from './ops-dashboard';
import { loadIngestConfig } from './ingest-stack';
import { grantLedgerPrivacy, PRIVACY_ROUTES } from './memory';
import { RoadmapRegen, RoadmapRegenConfig } from './roadmap-regen';
import { publishParams } from './ssm-outputs';

/**
 * Lệnh đóng zip Lambda ledger (`build/lambda/ledger-arm64.zip`). `--keep-boto`: giữ boto3/botocore ghim trong
 * `gateway/tools/ledger/requirements.txt` thay vì dùng bản có sẵn của runtime Lambda (bản đó tùy phiên bản runtime và Region,
 * có thể chưa có `namespacePath` của AgentCore Memory mà REST `/memory*` và "Xóa dữ liệu của tôi" cần).
 */
export const LEDGER_BUILD_COMMAND =
  'uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 --keep-boto --extra data/personas:personas ' +
  '--extra gateway/tools/planner/yofina_planner:yofina_planner --extra gateway/tools/planner/rules:rules ' +
  '--extra gateway/tools/knowledge/yofina_knowledge:yofina_knowledge --extra gateway/tools/audit/yofina_audit:yofina_audit';

/**
 * Route REST cho biểu đồ chi tiêu B1, B5, B7 (`GET /cashflow`, x-lambda: ledger, `cashflow_rest.py`): bản REST của tool
 * `ledger___get_cashflow_summary`. Cùng Lambda ledger và JWT authorizer mặc định như các route GET khác.
 */
export const CASHFLOW_ROUTES: Array<[string, apigwv2.HttpMethod]> = [['/cashflow', apigwv2.HttpMethod.GET]];

/**
 * Route REST của đề xuất tỷ lệ chia lương ở bước 3 onboarding (`POST /jars/split-proposal`, x-lambda: ledger,
 * `split_proposal.py`): chỉ tính, không ghi gì. Cùng Lambda ledger và JWT authorizer mặc định như các route khác.
 */
export const SPLIT_PROPOSAL_ROUTES: Array<[string, apigwv2.HttpMethod]> = [
  ['/jars/split-proposal', apigwv2.HttpMethod.POST],
];

/**
 * Cấu hình riêng của stack công cụ (Lambda ledger + HTTP API). Mọi giá trị đổi được bằng context
 * (`-c khóa=giá trị`); không giá trị nào phụ thuộc tài khoản. Các giá trị nghiệp vụ được truyền vào Lambda
 * dưới dạng biến môi trường `YOFINA_*` (xem libs/yofina_core/src/yofina_core/config.py), không gắn cứng trong mã.
 */
export interface ToolsConfig {
  /** Đường dẫn zip Lambda ledger (đóng bằng scripts/build_lambda.py). */
  readonly ledgerZip: string;
  readonly ledgerMemoryMb: number;
  readonly ledgerTimeoutSeconds: number;
  /** Hạn token xác nhận (giây); trần cũng bằng giá trị này (ADR-0002: tối đa 2 phút). */
  readonly confirmTokenTtlSeconds: number;
  /** Hạn của đề nghị trong khối `confirm` (giây). */
  readonly confirmOfferTtlSeconds: number;
  /** Hạn mức số tiền một lần chuyển hũ (VND); cùng giá trị với luật Cedar. */
  readonly moveMaxAmountVnd: number;
  readonly transactionsDefaultLimit: number;
  readonly transactionsMaxLimit: number;
  /** Hạn mức số tiền một giao dịch ghi bằng `record_transaction` (VND); cùng giá trị với luật Cedar. */
  readonly transactionMaxAmountVnd: number;
  /** Số nhận lệch lương đã khai quá ngưỡng này (phần trăm) thì hỏi có cập nhật lương không. */
  readonly salaryDeviationAskPercent: number;
  /** Hạn mức Trả sau (mô phỏng) của tài khoản mới (VND). */
  readonly defaultCreditLimitVnd: number;
  /** Tên hiển thị khi tài khoản chưa có hồ sơ và JWT không có tên. */
  readonly defaultDisplayName: string;
  /** Quá hạn độ tươi này (giây) thì dự báo bị đánh dấu `stale`. */
  readonly forecastFreshnessSeconds: number;
  /** Thẻ chủ động báo nghĩa vụ đến hạn trong N ngày tới. */
  readonly proactiveObligationDays: number;
  /** Giữ bảng tra (loại giao dịch, biểu phí, hũ mẫu) trong bộ nhớ Lambda bao lâu (giây). */
  readonly referenceCacheSeconds: number;
  /** Múi giờ ứng dụng và ngày neo của đồng hồ mô phỏng (ADR-0003). */
  readonly appTimezone: string;
  readonly demoAnchorDate: string;
  /** Thời gian tối đa chờ Aurora thức dậy trong Lambda (giây), nhỏ hơn timeout Lambda. */
  readonly dbResumeMaxWaitSeconds: number;
  /** Giới hạn tần suất mặc định của API (yêu cầu/giây và đợt cao điểm). */
  readonly apiThrottleRate: number;
  readonly apiThrottleBurst: number;
  /** Origin cho phép ngoài domain Amplify (đọc từ SSM). */
  readonly extraCorsOrigins: string[];
  /**
   * Bộ hũ của tài khoản mới (công tắc quay lui #39, `yofina_ledger.jar_layout.onboarding_override`): `catalogue` (mặc định, bộ
   * hũ `is_default` của danh mục `jar_templates`) hoặc `legacy` (bộ bảy hũ cũ). Chỉ đổi lần tạo ví sau; ví đã tạo giữ nguyên.
   */
  readonly onboardingJarLayout: OnboardingJarLayout;
}

/** Giá trị của `YOFINA_ONBOARDING_JAR_LAYOUT` mà Lambda ledger nhận (`jar_layout.py`). */
export const ONBOARDING_JAR_LAYOUTS = ['catalogue', 'legacy'] as const;
export type OnboardingJarLayout = (typeof ONBOARDING_JAR_LAYOUTS)[number];

/** Origin cho dev khi không đặt context `extraCorsOrigins`. */
export const DEFAULT_EXTRA_CORS_ORIGIN = 'http://localhost:5173';

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

export function loadToolsConfig(app: App): ToolsConfig {
  const timeout = ctxNum(app, 'ledgerTimeoutSeconds', 30);
  const ttl = ctxNum(app, 'confirmTokenTtlSeconds', 120);
  if (ttl < 1 || ttl > 120) throw new Error('confirmTokenTtlSeconds phải trong 1..120 (ADR-0002)');
  const resume = ctxNum(app, 'dbResumeMaxWaitSeconds', 18);
  if (resume >= timeout) throw new Error('dbResumeMaxWaitSeconds phải nhỏ hơn ledgerTimeoutSeconds');
  const layout = ctxStr(app, 'onboardingJarLayout', 'catalogue');
  if (!(ONBOARDING_JAR_LAYOUTS as readonly string[]).includes(layout)) {
    throw new Error(`onboardingJarLayout phải là ${ONBOARDING_JAR_LAYOUTS.join(' hoặc ')}, nhận được: ${layout}`);
  }
  return {
    ledgerZip: path.resolve(
      __dirname,
      '..',
      ctxStr(app, 'ledgerZip', '../build/lambda/ledger-arm64.zip'),
    ),
    ledgerMemoryMb: ctxNum(app, 'ledgerMemoryMb', 512),
    ledgerTimeoutSeconds: timeout,
    confirmTokenTtlSeconds: ttl,
    confirmOfferTtlSeconds: ctxNum(app, 'confirmOfferTtlSeconds', 600),
    moveMaxAmountVnd: ctxNum(app, 'moveMaxAmountVnd', 50_000_000),
    transactionsDefaultLimit: ctxNum(app, 'transactionsDefaultLimit', 20),
    transactionsMaxLimit: ctxNum(app, 'transactionsMaxLimit', 50),
    transactionMaxAmountVnd: ctxNum(app, 'transactionMaxAmountVnd', 50_000_000),
    salaryDeviationAskPercent: ctxNum(app, 'salaryDeviationAskPercent', 10),
    defaultCreditLimitVnd: ctxNum(app, 'defaultCreditLimitVnd', 3_000_000),
    defaultDisplayName: ctxStr(app, 'defaultDisplayName', 'Bạn'),
    forecastFreshnessSeconds: ctxNum(app, 'forecastFreshnessSeconds', 3600),
    proactiveObligationDays: ctxNum(app, 'proactiveObligationDays', 3),
    referenceCacheSeconds: ctxNum(app, 'referenceCacheSeconds', 300),
    appTimezone: ctxStr(app, 'appTimezone', 'Asia/Ho_Chi_Minh'),
    demoAnchorDate: ctxStr(app, 'demoAnchorDate', '2026-11-21'),
    dbResumeMaxWaitSeconds: resume,
    apiThrottleRate: ctxNum(app, 'apiThrottleRate', 20),
    apiThrottleBurst: ctxNum(app, 'apiThrottleBurst', 40),
    extraCorsOrigins: String(app.node.tryGetContext('extraCorsOrigins') ?? DEFAULT_EXTRA_CORS_ORIGIN)
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    onboardingJarLayout: layout as OnboardingJarLayout,
  };
}

export interface ToolsProps extends StackProps {
  readonly cfg: YofinaConfig;
  readonly tools: ToolsConfig;
  readonly forecast: ForecastPipelineConfig;
  /** Phase 4 (luồng B): Lambda phân loại `yofina-classify`. Vắng thì không dựng (test cũ của stack giữ nguyên). */
  readonly classify?: ClassifyConfig;
  /** Phase 4 (luồng C): Lambda sinh lại lộ trình `yofina-roadmap-regen`. Vắng thì không dựng. */
  readonly roadmap?: RoadmapRegenConfig;
  /** Phase 5 (luồng D): dashboard `yofina-ops` và alarm. Vắng thì đọc từ context (`loadOpsDashboardConfig`). */
  readonly ops?: OpsDashboardConfig;
}

/**
 * Lambda `yofina-ledger` (một mã, hai đường vào: Gateway của agent và HTTP API) và HTTP API `yofina-api`
 * với JWT authorizer của Cognito. Lambda nằm NGOÀI VPC và gọi Aurora qua Data API.
 *
 * Giá trị của stack khác được đọc từ SSM `/yofina/...` lúc deploy (dynamic reference), không dùng
 * `Fn::ImportValue`, nên có thể deploy riêng stack này. IAM tối thiểu: chỉ secret của role `yofina_app`
 * và khóa HMAC, KHÔNG secret master.
 */
export class ToolsStack extends Stack {
  public readonly ledger: lambda.Function;
  public readonly api: apigwv2.HttpApi;
  public readonly bus: events.EventBus;
  public readonly forecast: ForecastPipeline;

  constructor(scope: Construct, id: string, props: ToolsProps) {
    super(scope, id, props);
    const { cfg, tools } = props;
    const p = cfg.prefix;
    const param = (name: string) => ssm.StringParameter.valueForStringParameter(this, `/${p}/${name}`);

    if (!fs.existsSync(tools.ledgerZip)) {
      throw new Error(`Chưa có ${tools.ledgerZip}. Chạy: ${LEDGER_BUILD_COMMAND}`);
    }

    const clusterArn = param('db/cluster-arn');
    const appSecretArn = param('db/app-secret-arn');
    const hmacSecretArn = param('secrets/confirm-hmac-arn');
    const jtiTable = param('dynamodb/confirm-jti-table');
    const userPoolId = param('auth/user-pool-id');
    const clientId = param('auth/client-id');
    const amplifyUrl = param('frontend/amplify-url');

    // --- EventBridge bus: sự kiện của ledger (transaction.recorded, salary.confirmed, ...). Consumer ở đợt sau. -----
    this.bus = new events.EventBus(this, 'Bus', { eventBusName: `${p}-bus` });

    // --- Pipeline dự báo (Lambda batch, consumer sự kiện, tool; SQS, Step Functions, Scheduler): dựng TRƯỚC ledger vì ledger gọi
    // Lambda batch (đặt lại demo tính đồng bộ, đọc cũ kích hoạt tính lại). Không nhúng engine vào zip ledger: xem forecast_client.py.
    const alertTopic = sns.Topic.fromTopicArn(this, 'AlertTopic', param('sns/alert-topic-arn'));
    this.forecast = new ForecastPipeline(this, 'Forecast', {
      cfg,
      forecast: props.forecast,
      bus: this.bus,
      alertTopic,
      appTimezone: tools.appTimezone,
      freshnessSeconds: tools.forecastFreshnessSeconds,
      clusterArn,
      appSecretArn,
      dbName: param('db/name'),
      dbResumeMaxWaitSeconds: tools.dbResumeMaxWaitSeconds,
      region: cfg.region,
    });

    // --- Phase 4 luồng B: phân hũ tự động (EventBridge transaction.recorded → SQS + DLQ → Lambda yofina-classify) ----------
    if (props.classify) {
      new ClassifyPipeline(this, 'Classify', {
        cfg,
        classify: props.classify,
        bus: this.bus,
        alertTopic,
        appTimezone: tools.appTimezone,
        clusterArn,
        appSecretArn,
        dbName: param('db/name'),
        dbResumeMaxWaitSeconds: tools.dbResumeMaxWaitSeconds,
        usageTableName: param('dynamodb/usage-table'),
      });
    }

    // --- Lambda ledger ---------------------------------------------------------------------
    this.ledger = new lambda.Function(this, 'Ledger', {
      functionName: `${p}-ledger`,
      description: 'Tool ledger: vi mo phong (hu, giao dich, nghia vu, tra sau, luong, du bao doc); Gateway va HTTP API',
      runtime: lambda.Runtime.PYTHON_3_13,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset(tools.ledgerZip),
      memorySize: tools.ledgerMemoryMb,
      timeout: Duration.seconds(tools.ledgerTimeoutSeconds),
      logGroup: new logs.LogGroup(this, 'LedgerLogs', {
        logGroupName: `/aws/lambda/${p}-ledger`,
        retention: cfg.logRetentionDays as logs.RetentionDays,
        removalPolicy: RemovalPolicy.DESTROY,
      }),
      environment: {
        YOFINA_REGION: cfg.region,
        YOFINA_LOG_LEVEL: 'INFO',
        YOFINA_DB_CLUSTER_ARN: clusterArn,
        YOFINA_DB_APP_SECRET_ARN: appSecretArn,
        YOFINA_DB_NAME: param('db/name'),
        YOFINA_DB_RESUME_MAX_WAIT_SECONDS: String(tools.dbResumeMaxWaitSeconds),
        YOFINA_CONFIRM_JTI_TABLE: jtiTable,
        YOFINA_CONFIRM_HMAC_SECRET_ARN: hmacSecretArn,
        YOFINA_CONFIRM_TOKEN_TTL_SECONDS: String(tools.confirmTokenTtlSeconds),
        YOFINA_CONFIRM_TOKEN_MAX_TTL_SECONDS: String(tools.confirmTokenTtlSeconds),
        YOFINA_CONFIRM_OFFER_TTL_SECONDS: String(tools.confirmOfferTtlSeconds),
        YOFINA_MOVE_MAX_AMOUNT_VND: String(tools.moveMaxAmountVnd),
        YOFINA_TRANSACTIONS_DEFAULT_LIMIT: String(tools.transactionsDefaultLimit),
        YOFINA_TRANSACTIONS_MAX_LIMIT: String(tools.transactionsMaxLimit),
        YOFINA_TRANSACTION_MAX_AMOUNT_VND: String(tools.transactionMaxAmountVnd),
        YOFINA_SALARY_DEVIATION_ASK_PERCENT: String(tools.salaryDeviationAskPercent),
        YOFINA_DEFAULT_CREDIT_LIMIT_VND: String(tools.defaultCreditLimitVnd),
        YOFINA_DEFAULT_DISPLAY_NAME: tools.defaultDisplayName,
        YOFINA_FORECAST_FRESHNESS_SECONDS: String(tools.forecastFreshnessSeconds),
        YOFINA_PROACTIVE_OBLIGATION_DAYS: String(tools.proactiveObligationDays),
        YOFINA_REFERENCE_CACHE_SECONDS: String(tools.referenceCacheSeconds),
        YOFINA_EVENT_BUS_NAME: this.bus.eventBusName,
        YOFINA_FORECAST_FUNCTION_NAME: this.forecast.batch.functionName,
        YOFINA_FORECAST_SYNC_TIMEOUT_SECONDS: String(Math.max(tools.ledgerTimeoutSeconds - 8, 5)),
        YOFINA_SUITABILITY_WINDOW_DAYS: String(props.forecast.horizonDays),
        YOFINA_APP_TIMEZONE: tools.appTimezone,
        YOFINA_DEMO_ANCHOR_DATE: tools.demoAnchorDate,
        YOFINA_ONBOARDING_JAR_LAYOUT: tools.onboardingJarLayout,
      },
    });

    // IAM tối thiểu. Data API gọi Secrets Manager bằng quyền của người gọi nên cần GetSecretValue trên
    // secret của yofina_app; khóa HMAC để cấp/kiểm token; PutItem điều kiện lên bảng jti.
    this.ledger.addToRolePolicy(
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
    this.ledger.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'ReadAppAndHmacSecretsOnly',
        actions: ['secretsmanager:GetSecretValue'],
        resources: [appSecretArn, hmacSecretArn],
      }),
    );
    this.ledger.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'ConsumeConfirmJti',
        actions: ['dynamodb:PutItem'],
        resources: [this.formatArn({ service: 'dynamodb', resource: 'table', resourceName: jtiTable })],
      }),
    );

    // Ledger chỉ được gọi Lambda batch dự báo (đặt lại demo đồng bộ; đọc cũ kích hoạt nền), không quyền nào khác lên pipeline.
    this.forecast.batch.grantInvoke(this.ledger);
    this.ledger.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'PublishLedgerEvents',
        actions: ['events:PutEvents'],
        resources: [this.bus.eventBusArn],
      }),
    );

    // --- Phase 5 luồng B: quyền riêng tư (REST /memory*, /me/delete-data*): Memory theo tên, tệp nạp theo tiền tố, id Memory ở SSM ---
    grantLedgerPrivacy(this, this.ledger, {
      prefix: p,
      uploadPrefix: loadIngestConfig(this.node.root as App).uploadPrefix,
    });

    // --- Phase 4 luồng C: sinh lại lộ trình (EventBridge ba loại sự kiện → SQS + DLQ → Lambda yofina-roadmap-regen) -------
    // Gọi thẳng hai Lambda tool (ledger cho target ledger/planner, forecast TOOL cho target forecast), không qua Gateway.
    if (props.roadmap) {
      new RoadmapRegen(this, 'RoadmapRegen', {
        cfg,
        roadmap: props.roadmap,
        bus: this.bus,
        alertTopic,
        ledgerFunction: this.ledger,
        ledgerTimeoutSeconds: tools.ledgerTimeoutSeconds,
        forecastToolFunction: this.forecast.tool,
        forecastToolTimeoutSeconds: props.forecast.toolTimeoutSeconds,
        appTimezone: tools.appTimezone,
        clusterArn,
        appSecretArn,
        dbName: param('db/name'),
        dbResumeMaxWaitSeconds: tools.dbResumeMaxWaitSeconds,
        usageTableName: param('dynamodb/usage-table'),
      });
    }

    // --- HTTP API + JWT authorizer của Cognito -----------------------------------------------
    // Frontend chỉ gửi ACCESS token (có `client_id`, không có `aud`): HTTP API so `jwtAudience` với `aud` hoặc `client_id`.
    const issuer = `https://cognito-idp.${cfg.region}.amazonaws.com/${userPoolId}`;
    const authorizer = new HttpJwtAuthorizer('CognitoJwt', issuer, {
      authorizerName: `${p}-cognito`,
      jwtAudience: [clientId],
    });
    this.api = new apigwv2.HttpApi(this, 'Api', {
      apiName: `${p}-api`,
      description: 'Yofina REST: so du hu, cap token xac nhan, thao tac ghi, dat lai du lieu demo',
      defaultAuthorizer: authorizer,
      corsPreflight: {
        allowOrigins: [amplifyUrl, ...tools.extraCorsOrigins],
        allowMethods: [
          apigwv2.CorsHttpMethod.GET,
          apigwv2.CorsHttpMethod.POST,
          // phase 5 luồng B: `DELETE /memory`, `DELETE /memory/{record_id}`
          apigwv2.CorsHttpMethod.DELETE,
          apigwv2.CorsHttpMethod.OPTIONS,
        ],
        allowHeaders: ['authorization', 'content-type', 'traceparent'],
        maxAge: Duration.hours(1),
      },
    });
    const integration = new HttpLambdaIntegration('LedgerIntegration', this.ledger);
    // Mọi route do Lambda ledger phục vụ (contracts/rest/openapi.yaml). `GET /forecasts/{jar_code}` đọc bảng dự báo và, khi cũ
    // hoặc chưa có, gọi Lambda `yofina-forecast-batch` để tính lại (ledger giữ route này để dùng chung mã dựng khối với tool).
    const routes: Array<[string, apigwv2.HttpMethod]> = [
      ['/jars', apigwv2.HttpMethod.GET],
      ['/jars/{jar_code}', apigwv2.HttpMethod.GET],
      ['/overview', apigwv2.HttpMethod.GET],
      ['/profile', apigwv2.HttpMethod.GET],
      ['/transactions', apigwv2.HttpMethod.GET],
      ['/tx-types', apigwv2.HttpMethod.GET],
      ['/payees', apigwv2.HttpMethod.GET],
      ['/obligations', apigwv2.HttpMethod.GET],
      ['/credit-line', apigwv2.HttpMethod.GET],
      ['/salary-events', apigwv2.HttpMethod.GET],
      ['/jar-templates', apigwv2.HttpMethod.GET],
      ['/forecasts/{jar_code}', apigwv2.HttpMethod.GET],
      ['/confirmations', apigwv2.HttpMethod.POST],
      ['/confirmations/cancel', apigwv2.HttpMethod.POST],
      ['/actions', apigwv2.HttpMethod.POST],
      ['/demo/reset', apigwv2.HttpMethod.POST],
      ['/conversations', apigwv2.HttpMethod.GET],
      ['/conversations/{conversation_id}', apigwv2.HttpMethod.GET],
      ['/traces/{trace_id}', apigwv2.HttpMethod.GET],
      ['/feedback', apigwv2.HttpMethod.POST],
      // phase 4 (x-lambda: ledger): lộ trình (gói 2) và "Xem lại" / hỏi gộp (gói 4)
      ['/roadmap', apigwv2.HttpMethod.GET],
      ['/roadmap/versions', apigwv2.HttpMethod.GET],
      ['/roadmap/diff', apigwv2.HttpMethod.GET],
      ['/roadmap/steps/{step_id}/decision', apigwv2.HttpMethod.POST],
      ['/roadmap/steps/{step_id}/edit', apigwv2.HttpMethod.POST],
      ['/roadmap/versions/{version}/decision', apigwv2.HttpMethod.POST],
      ['/roadmap/regenerate', apigwv2.HttpMethod.POST],
      ['/roadmap/jobs/{job_id}', apigwv2.HttpMethod.GET],
      ['/review', apigwv2.HttpMethod.GET],
      ['/review/daily-ask/skip', apigwv2.HttpMethod.POST],
      // phase 5 (x-lambda: ledger, x-required-group: ops): bảng vận hành; Lambda kiểm nhóm Cognito `ops`, người khác 403
      ['/ops/traces', apigwv2.HttpMethod.GET],
      ['/ops/traces/{trace_id}', apigwv2.HttpMethod.GET],
      ['/ops/summary', apigwv2.HttpMethod.GET],
      // phase 5 luồng B (x-lambda: ledger): bộ nhớ của tôi, xóa dữ liệu của tôi (privacy_rest)
      ...PRIVACY_ROUTES,
      // phase 5 luồng B (x-lambda: ledger): bản tin của cổng giá trị
      ['/nudges/today', apigwv2.HttpMethod.GET],
      ['/nudges/{nudge_id}/feedback', apigwv2.HttpMethod.POST],
      // đợt giao diện (x-lambda: ledger): biểu đồ chi tiêu của màn Hoạt động
      ...CASHFLOW_ROUTES,
      // bộ hũ mặc định (x-lambda: ledger): tỷ lệ đề xuất theo kê khai ở bước 3 onboarding
      ...SPLIT_PROPOSAL_ROUTES,
    ];
    for (const [routePath, method] of routes) {
      this.api.addRoutes({ path: routePath, methods: [method], integration });
    }
    // x-lambda: forecast: Lambda yofina-forecast (có engine), cùng JWT authorizer.
    // `POST /affordability` (phase 3); `/resilience*` (phase 4, gói 1: điểm chống chịu và cú sốc).
    const forecastIntegration = new HttpLambdaIntegration('AffordIntegration', this.forecast.tool);
    const forecastRoutes: Array<[string, apigwv2.HttpMethod]> = [
      ['/affordability', apigwv2.HttpMethod.POST],
      ['/resilience', apigwv2.HttpMethod.GET],
      ['/resilience/shocks', apigwv2.HttpMethod.GET],
      ['/resilience/stress', apigwv2.HttpMethod.POST],
      // phase 5 luồng B: hồ sơ hành vi (cùng data với tool forecast___get_behavior_profile)
      ['/profile/behavior', apigwv2.HttpMethod.GET],
    ];
    for (const [routePath, method] of forecastRoutes) {
      this.api.addRoutes({ path: routePath, methods: [method], integration: forecastIntegration });
    }
    const stage = this.api.defaultStage?.node.defaultChild as apigwv2.CfnStage | undefined;
    if (stage) {
      stage.defaultRouteSettings = {
        throttlingRateLimit: tools.apiThrottleRate,
        throttlingBurstLimit: tools.apiThrottleBurst,
      };
    }

    // Cảnh báo khi phát sự kiện lỗi: metric EventPublishFailed do Lambda ghi bằng EMF (không cần quyền PutMetricData).
    const publishFailed = new cloudwatch.Metric({
      namespace: 'Yofina/Ledger',
      metricName: 'EventPublishFailed',
      statistic: 'Sum',
      period: Duration.minutes(5),
      dimensionsMap: { DetailType: 'transaction.recorded' },
    });
    new cloudwatch.Alarm(this, 'EventPublishFailedAlarm', {
      alarmName: `${p}-ledger-event-publish-failed`,
      alarmDescription: 'Ledger khong phat duoc su kien transaction.recorded len yofina-bus (viec ghi van thanh cong; nightly bu)',
      metric: publishFailed,
      threshold: 1,
      evaluationPeriods: 1,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    }).addAlarmAction(new cwActions.SnsAction(alertTopic));

    // --- Phase 5 luồng D: dashboard `yofina-ops`, alarm về SNS sẵn có, quyền đọc `yofina-usage` cho `/ops/summary` ----------
    new OpsDashboard(this, 'Ops', {
      cfg,
      ops: props.ops ?? loadOpsDashboardConfig(this),
      alertTopic,
      ledger: this.ledger,
      usageTableName: param('dynamodb/usage-table'),
      apiId: this.api.apiId,
    });

    const apiUrl = this.api.apiEndpoint;
    publishParams(this, {
      'events/bus-name': this.bus.eventBusName,
      'events/bus-arn': this.bus.eventBusArn,
      'api/url': apiUrl,
      'ledger/function-name': this.ledger.functionName,
      'ledger/function-arn': this.ledger.functionArn,
      'forecast/function-name': this.forecast.tool.functionName,
      'forecast/function-arn': this.forecast.tool.functionArn,
      'forecast/batch-function-name': this.forecast.batch.functionName,
      'forecast/nightly-arn': this.forecast.nightly.stateMachineArn,
      'forecast/events-queue-url': this.forecast.queue.queueUrl,
      'forecast/idempotency-table': this.forecast.idempotencyTable.tableName,
    });
    new CfnOutput(this, 'ApiUrl', { value: apiUrl });
  }
}
