import { Duration, Stack } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as agentcore from 'aws-cdk-lib/aws-bedrockagentcore';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cwActions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sns from 'aws-cdk-lib/aws-sns';
import { publishParams } from './ssm-outputs';

/**
 * AgentCore Memory của Yofina (phase 5, luồng B). Thiết kế và nguồn: docs/research/agentcore-memory-design.md.
 *
 * - MỘT Memory resource cho cả ứng dụng, tách người dùng bằng namespace theo `actorId` = `sub` của JWT (agent và Lambda ledger tự ép
 *   namespace trong mã; IAM không ép được theo từng người dùng vì một role phục vụ mọi người dùng).
 * - Ba strategy dựng sẵn (built-in, không override: không cần execution role gọi model trong tài khoản, không ăn quota Claude của dự án),
 *   mỗi strategy một namespace, đúng `yofina_core.memory.MEMORY_NAMESPACE_TEMPLATES` (test Python đối chiếu chuỗi):
 *   sở thích (USER_PREFERENCE), sự thật người dùng tự kể (SEMANTIC), tóm tắt phiên (SUMMARIZATION).
 * - Agent ghi bằng `IngestData` (không lưu event ngắn hạn), nên hạn event để mức thấp nhất CDK cho phép (7 ngày) phòng khi có event.
 * - Mã hóa: khóa do AWS sở hữu và quản lý (mặc định của dịch vụ); không tạo KMS key riêng.
 * - `FailedExtraction` (metric có sẵn của AgentCore Memory) vào topic SNS cảnh báo sẵn có.
 */
export const MEMORY_NAME = 'yofina_memory';

/** Mẫu namespace theo loại (có `/` đầu và cuối). Python: `yofina_core.memory.MEMORY_NAMESPACE_TEMPLATES`. */
export const MEMORY_NAMESPACES = {
  preference: '/yofina/users/{actorId}/preferences/',
  fact: '/yofina/users/{actorId}/facts/',
  session_summary: '/yofina/users/{actorId}/sessions/{sessionId}/',
} as const;

/** Runtime của agent: đọc sở thích và sự thật, gửi lượt hội thoại cho trích xuất dài hạn. Không xóa, không tạo event. */
export const AGENT_MEMORY_ACTIONS = [
  'bedrock-agentcore:IngestData',
  'bedrock-agentcore:RetrieveMemoryRecords',
  'bedrock-agentcore:ListMemoryRecords',
];

/** Lambda ledger (REST `/memory*`, `/me/delete-data`, `quiet_hours`): xem và xóa bản ghi, xóa event nếu có. Không ghi, không đọc semantic. */
export const LEDGER_MEMORY_ACTIONS = [
  'bedrock-agentcore:ListMemoryRecords',
  'bedrock-agentcore:GetMemoryRecord',
  'bedrock-agentcore:DeleteMemoryRecord',
  'bedrock-agentcore:BatchDeleteMemoryRecords',
  'bedrock-agentcore:ListSessions',
  'bedrock-agentcore:ListEvents',
  'bedrock-agentcore:DeleteEvent',
];

/** Tham số SSM chứa id của Memory (stack YofinaAgent ghi; Lambda ledger đọc lúc chạy vì YofinaTools deploy trước YofinaAgent). */
export const MEMORY_ID_PARAM_KEY = 'memory/id';

/** Route REST quyền riêng tư (x-lambda: ledger, `privacy_rest.py`). `DELETE` cần có trong CORS của `yofina-api`. */
export const PRIVACY_ROUTES: Array<[string, apigwv2.HttpMethod]> = [
  ['/memory', apigwv2.HttpMethod.GET],
  ['/memory', apigwv2.HttpMethod.DELETE],
  ['/memory/{record_id}', apigwv2.HttpMethod.DELETE],
  ['/me/delete-data/confirmations', apigwv2.HttpMethod.POST],
  ['/me/delete-data', apigwv2.HttpMethod.POST],
];

export interface YofinaMemoryProps {
  /** Tên Memory (`[a-zA-Z][a-zA-Z0-9_]{0,47}`); id dịch vụ cấp là `<tên>-<10 ký tự>`. */
  readonly name?: string;
  /** Hạn event ngắn hạn (ngày, 7..365); agent không tạo event nên để thấp nhất. */
  readonly eventExpiryDays?: number;
  /** Topic SNS nhận cảnh báo `FailedExtraction`. Vắng thì không tạo alarm. */
  readonly alertTopic?: sns.ITopic;
}

export class YofinaMemory extends Construct {
  readonly memory: agentcore.Memory;
  readonly memoryId: string;
  readonly memoryArn: string;
  readonly failedExtractionAlarm?: cloudwatch.Alarm;

  constructor(scope: Construct, id: string, props: YofinaMemoryProps = {}) {
    super(scope, id);
    const name = props.name ?? MEMORY_NAME;
    this.memory = new agentcore.Memory(this, 'Memory', {
      memoryName: name,
      description: 'Yofina long-term memory - preferences facts and session summaries per Cognito sub',
      expirationDuration: Duration.days(props.eventExpiryDays ?? 7),
      memoryStrategies: [
        agentcore.MemoryStrategy.usingUserPreference({
          strategyName: 'preferences',
          description: 'So thich nguoi dung tu noi (gio khong muon duoc nhac, hu uu tien)',
          namespaces: [MEMORY_NAMESPACES.preference],
        }),
        agentcore.MemoryStrategy.usingSemantic({
          strategyName: 'facts',
          description: 'Su that nguoi dung tu ke (nghe nghiep, ke hoach lon); khong so du, khong giao dich',
          namespaces: [MEMORY_NAMESPACES.fact],
        }),
        agentcore.MemoryStrategy.usingSummarization({
          strategyName: 'session_summaries',
          description: 'Tom tat tung phien hoi thoai',
          namespaces: [MEMORY_NAMESPACES.session_summary],
        }),
      ],
      tags: { project: 'yofina' },
    });
    this.memoryId = this.memory.memoryId;
    this.memoryArn = this.memory.memoryArn;

    publishParams(this, { [MEMORY_ID_PARAM_KEY]: this.memoryId, 'memory/arn': this.memoryArn });

    if (props.alertTopic) {
      // FailedExtraction có ba chiều (StrategyId, Resource, StrategyType) và strategy id không có ở CloudFormation: dùng truy vấn
      // Metrics Insights lọc theo Resource (ARN của Memory) để một alarm phủ cả ba strategy.
      const query = new cloudwatch.MathExpression({
        expression: `SELECT SUM(FailedExtraction) FROM "AWS/Bedrock-AgentCore" WHERE Resource = '${this.memoryArn}'`,
        period: Duration.minutes(5),
        label: 'FailedExtraction',
      });
      this.failedExtractionAlarm = new cloudwatch.Alarm(this, 'FailedExtractionAlarm', {
        alarmName: `${name.replace(/_/g, '-')}-failed-extraction`,
        alarmDescription:
          'AgentCore Memory khong trich xuat duoc bo nho dai han (LTM_RATE_EXCEEDED...): xem ListMemoryExtractionJobs roi StartMemoryExtractionJob',
        metric: query,
        threshold: 1,
        evaluationPeriods: 1,
        comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      this.failedExtractionAlarm.addAlarmAction(new cwActions.SnsAction(props.alertTopic));
    }
  }

  /** Quyền tối thiểu của Runtime trên ĐÚNG Memory này. */
  grantAgentRuntime(role: iam.IRole): void {
    role.addToPrincipalPolicy(
      new iam.PolicyStatement({ sid: 'AgentMemory', actions: AGENT_MEMORY_ACTIONS, resources: [this.memoryArn] }),
    );
  }
}

/**
 * ARN của Memory theo TÊN (`memory/<tên>-*`), cho stack không đọc được ARN lúc deploy (YofinaTools deploy trước YofinaAgent). Tên Memory
 * là duy nhất trong một vùng của tài khoản nên mẫu này khớp đúng một Memory.
 */
export function memoryArnByName(stack: Stack, name: string = MEMORY_NAME): string {
  return stack.formatArn({ service: 'bedrock-agentcore', resource: 'memory', resourceName: `${name}-*` });
}

export interface LedgerPrivacyProps {
  /** Tiền tố tài nguyên (`yofina`). */
  readonly prefix: string;
  /** Tiền tố khóa của tệp người dùng trong bucket nạp (`u/`), cùng giá trị với `IngestConfig.uploadPrefix`. */
  readonly uploadPrefix: string;
  readonly memoryName?: string;
}

/**
 * Quyền và biến môi trường cho REST quyền riêng tư của Lambda ledger (`/memory*`, `/me/delete-data*`): Memory (xem, xóa), xóa tệp nạp
 * dưới tiền tố người dùng, đọc id Memory từ SSM. Bucket nạp có tên cố định `<prefix>-ingest-<account>-<region>` (stack YofinaIngest).
 */
export function grantLedgerPrivacy(stack: Stack, fn: lambda.Function, props: LedgerPrivacyProps): void {
  if (!props.uploadPrefix.endsWith('/')) throw new Error('uploadPrefix phải kết thúc bằng /');
  const bucket = `${props.prefix}-ingest-${stack.account}-${stack.region}`;
  const bucketArn = `arn:${stack.partition}:s3:::${bucket}`;
  const paramName = `/${props.prefix}/${MEMORY_ID_PARAM_KEY}`;
  fn.addToRolePolicy(
    new iam.PolicyStatement({
      sid: 'PrivacyMemory',
      actions: LEDGER_MEMORY_ACTIONS,
      resources: [memoryArnByName(stack, props.memoryName)],
    }),
  );
  fn.addToRolePolicy(
    new iam.PolicyStatement({
      sid: 'PrivacyListUserUploads',
      actions: ['s3:ListBucket'],
      resources: [bucketArn],
      conditions: { StringLike: { 's3:prefix': [`${props.uploadPrefix}*`] } },
    }),
  );
  fn.addToRolePolicy(
    new iam.PolicyStatement({
      sid: 'PrivacyDeleteUserUploads',
      actions: ['s3:DeleteObject'],
      resources: [`${bucketArn}/${props.uploadPrefix}*`],
    }),
  );
  fn.addToRolePolicy(
    new iam.PolicyStatement({
      sid: 'PrivacyReadMemoryId',
      actions: ['ssm:GetParameter'],
      resources: [stack.formatArn({ service: 'ssm', resource: 'parameter', resourceName: paramName.slice(1) })],
    }),
  );
  fn.addEnvironment('YOFINA_MEMORY_ID_PARAM', paramName);
  fn.addEnvironment('YOFINA_INGEST_BUCKET', bucket);
  fn.addEnvironment('YOFINA_INGEST_UPLOAD_PREFIX', props.uploadPrefix);
}
