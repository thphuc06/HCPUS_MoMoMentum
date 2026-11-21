import * as fs from 'fs';
import * as path from 'path';
import { App, CfnOutput, Duration, RemovalPolicy, Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpJwtAuthorizer } from 'aws-cdk-lib/aws-apigatewayv2-authorizers';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { YofinaConfig } from '../config/config';
import { publishParams } from './ssm-outputs';

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

export function loadToolsConfig(app: App): ToolsConfig {
  const timeout = ctxNum(app, 'ledgerTimeoutSeconds', 30);
  const ttl = ctxNum(app, 'confirmTokenTtlSeconds', 120);
  if (ttl < 1 || ttl > 120) throw new Error('confirmTokenTtlSeconds phải trong 1..120 (ADR-0002)');
  const resume = ctxNum(app, 'dbResumeMaxWaitSeconds', 18);
  if (resume >= timeout) throw new Error('dbResumeMaxWaitSeconds phải nhỏ hơn ledgerTimeoutSeconds');
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
    appTimezone: ctxStr(app, 'appTimezone', 'Asia/Ho_Chi_Minh'),
    demoAnchorDate: ctxStr(app, 'demoAnchorDate', '2026-11-21'),
    dbResumeMaxWaitSeconds: resume,
    apiThrottleRate: ctxNum(app, 'apiThrottleRate', 20),
    apiThrottleBurst: ctxNum(app, 'apiThrottleBurst', 40),
    extraCorsOrigins: ctxStr(app, 'extraCorsOrigins', 'http://localhost:5173')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
  };
}

export interface ToolsProps extends StackProps {
  readonly cfg: YofinaConfig;
  readonly tools: ToolsConfig;
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

  constructor(scope: Construct, id: string, props: ToolsProps) {
    super(scope, id, props);
    const { cfg, tools } = props;
    const p = cfg.prefix;
    const param = (name: string) => ssm.StringParameter.valueForStringParameter(this, `/${p}/${name}`);

    if (!fs.existsSync(tools.ledgerZip)) {
      throw new Error(
        `Chưa có ${tools.ledgerZip}. Chạy: uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 --extra data/personas:personas`,
      );
    }

    const clusterArn = param('db/cluster-arn');
    const appSecretArn = param('db/app-secret-arn');
    const hmacSecretArn = param('secrets/confirm-hmac-arn');
    const jtiTable = param('dynamodb/confirm-jti-table');
    const userPoolId = param('auth/user-pool-id');
    const clientId = param('auth/client-id');
    const amplifyUrl = param('frontend/amplify-url');

    // --- Lambda ledger ---------------------------------------------------------------------
    this.ledger = new lambda.Function(this, 'Ledger', {
      functionName: `${p}-ledger`,
      description: 'Tool ledger: so du hu, giao dich, chuyen hu co xac nhan; Gateway va HTTP API',
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
        YOFINA_APP_TIMEZONE: tools.appTimezone,
        YOFINA_DEMO_ANCHOR_DATE: tools.demoAnchorDate,
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
          apigwv2.CorsHttpMethod.OPTIONS,
        ],
        allowHeaders: ['authorization', 'content-type', 'traceparent'],
        maxAge: Duration.hours(1),
      },
    });
    const integration = new HttpLambdaIntegration('LedgerIntegration', this.ledger);
    const routes: Array<[string, apigwv2.HttpMethod]> = [
      ['/jars', apigwv2.HttpMethod.GET],
      ['/confirmations', apigwv2.HttpMethod.POST],
      ['/actions', apigwv2.HttpMethod.POST],
      ['/demo/reset', apigwv2.HttpMethod.POST],
      ['/conversations', apigwv2.HttpMethod.GET],
      ['/conversations/{conversation_id}', apigwv2.HttpMethod.GET],
    ];
    for (const [routePath, method] of routes) {
      this.api.addRoutes({ path: routePath, methods: [method], integration });
    }
    const stage = this.api.defaultStage?.node.defaultChild as apigwv2.CfnStage | undefined;
    if (stage) {
      stage.defaultRouteSettings = {
        throttlingRateLimit: tools.apiThrottleRate,
        throttlingBurstLimit: tools.apiThrottleBurst,
      };
    }

    const apiUrl = this.api.apiEndpoint;
    publishParams(this, {
      'api/url': apiUrl,
      'ledger/function-name': this.ledger.functionName,
      'ledger/function-arn': this.ledger.functionArn,
    });
    new CfnOutput(this, 'ApiUrl', { value: apiUrl });
  }
}
