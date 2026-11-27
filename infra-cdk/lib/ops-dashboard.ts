import * as fs from 'fs';
import * as path from 'path';
import { Duration, Stack } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cwActions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { YofinaConfig } from '../config/config';

export const GUARDRAIL_METRIC_NAMESPACE = 'Yofina/Agent';
export const GUARDRAIL_ERROR_METRIC_NAME = 'GuardrailErrors';

/**
 * Cấu hình của bảng vận hành (FR15, phase 5 luồng D). Đổi bằng context `-c khóa=giá trị`; không giá trị nào phụ thuộc tài khoản.
 */
export interface OpsDashboardConfig {
  /** `llm_defaults.json` của `yofina_core.llm`: model id và trần ngày, đọc lúc synth để vẽ lượt gọi model và đặt alarm gần trần. */
  readonly llmDefaults: string;
  /** Alarm khi p95 thời lượng Lambda ledger (đường tool chính) vượt ngưỡng này (mili giây) ba chu kỳ 5 phút liền. */
  readonly ledgerP95AlarmMs: number;
  /** Alarm khi tổng lỗi (Errors) của hai Lambda tool (ledger, forecast) trong 5 phút đạt ngưỡng này. */
  readonly toolErrorsAlarmThreshold: number;
  /** Alarm khi lượt gọi một model trong 24 giờ đạt phần trăm này của trần ngày (0 thì không tạo). */
  readonly modelCapAlarmPercent: number;
  /** Alarm khi Aurora chạy ở ACU tối đa liên tục từng này phút (0 thì không tạo). */
  readonly acuAtMaxAlarmMinutes: number;
  /** Ngưỡng lỗi guardrail trong 5 phút (0 thì bỏ alarm và metric filter). */
  readonly guardrailErrorAlarmThreshold: number;
  /** Tên endpoint trong log group của AgentCore Runtime. */
  readonly runtimeEndpointName: string;
}

function ctxNum(scope: Construct, key: string, dflt: number): number {
  const v = scope.node.tryGetContext(key);
  if (v === undefined || v === null || v === '') return dflt;
  const n = Number(v);
  if (!Number.isFinite(n)) throw new Error(`context ${key} phải là số, nhận được: ${v}`);
  return n;
}

/** Đọc từ context của app (gọi được với bất kỳ construct nào trong app). */
export function loadOpsDashboardConfig(scope: Construct): OpsDashboardConfig {
  const llm = scope.node.tryGetContext('opsLlmDefaults');
  const pct = ctxNum(scope, 'opsModelCapAlarmPercent', 80);
  if (pct < 0 || pct > 100) throw new Error('opsModelCapAlarmPercent phải trong 0..100');
  const acuMinutes = ctxNum(scope, 'opsAcuAtMaxAlarmMinutes', 30);
  if (acuMinutes < 0 || acuMinutes % 5 !== 0) throw new Error('opsAcuAtMaxAlarmMinutes phải là bội của 5 (chu kỳ 5 phút)');
  const guardrailErrorAlarmThreshold = ctxNum(scope, 'opsGuardrailErrorAlarmThreshold', 1);
  if (guardrailErrorAlarmThreshold < 0) throw new Error('opsGuardrailErrorAlarmThreshold phải lớn hơn hoặc bằng 0');
  const endpoint = scope.node.tryGetContext('opsRuntimeEndpointName');
  return {
    llmDefaults: path.resolve(
      __dirname,
      '..',
      llm ? String(llm) : '../libs/yofina_core/src/yofina_core/llm_defaults.json',
    ),
    ledgerP95AlarmMs: ctxNum(scope, 'opsLedgerP95AlarmMs', 10_000),
    toolErrorsAlarmThreshold: ctxNum(scope, 'opsToolErrorsAlarmThreshold', 3),
    modelCapAlarmPercent: pct,
    acuAtMaxAlarmMinutes: acuMinutes,
    guardrailErrorAlarmThreshold,
    runtimeEndpointName: endpoint ? String(endpoint) : 'DEFAULT',
  };
}

interface LlmDefaults {
  roles: Record<string, { daily_cap?: number; models: Array<{ id: string; daily_cap?: number }> }>;
}

/** Trần ngày của từng model id (lớn nhất nếu một model ở nhiều vai), cùng cách đọc với `yofina_ledger.ops.OpsSettings`. */
export function modelCaps(llmDefaultsFile: string): Map<string, number> {
  const llm = JSON.parse(fs.readFileSync(llmDefaultsFile, 'utf-8')) as LlmDefaults;
  const caps = new Map<string, number>();
  for (const role of Object.values(llm.roles)) {
    for (const m of role.models) {
      const cap = Number(m.daily_cap ?? role.daily_cap ?? 0);
      caps.set(m.id, Math.max(caps.get(m.id) ?? 0, cap));
    }
  }
  return caps;
}

export interface OpsDashboardProps {
  readonly cfg: YofinaConfig;
  readonly ops: OpsDashboardConfig;
  /** Topic SNS cảnh báo sẵn có (`/yofina/sns/alert-topic-arn` của YofinaFoundation). */
  readonly alertTopic: sns.ITopic;
  /** Lambda ledger: phục vụ `/ops/*`, được đọc (Query) bảng đếm lượt gọi model. */
  readonly ledger: lambda.Function;
  /** Tên bảng DynamoDB đếm lượt gọi model (`yofina-usage`, SSM `dynamodb/usage-table`). */
  readonly usageTableName: string;
  /** HTTP API `yofina-api` (lỗi 5xx và độ trễ của REST). */
  readonly apiId: string;
}

/**
 * Bảng vận hành phía hạ tầng: dashboard CloudWatch `yofina-ops`, alarm về topic SNS sẵn có, và quyền đọc bảng `yofina-usage` cho
 * Lambda ledger (`GET /ops/summary` so lượt gọi model theo ngày với trần).
 *
 * Dashboard dùng metric AWS có sẵn (Lambda, SQS, RDS, Bedrock, API Gateway, `AWS/Bedrock-AgentCore`). Alarm guardrail dùng metric
 * từ log AgentCore Runtime, tra runtime id qua SSM lúc deploy. Tài nguyên khác (Lambda nạp dữ liệu, interceptor, DLQ, Aurora) được
 * tham chiếu theo tên dựng từ tiền tố. DLQ có alarm riêng. Dashboard không bật CloudWatch Transaction Search hay span OTel.
 */
export class OpsDashboard extends Construct {
  public readonly dashboard: cloudwatch.Dashboard;
  public readonly alarms: cloudwatch.Alarm[] = [];

  constructor(scope: Construct, id: string, props: OpsDashboardProps) {
    super(scope, id);
    const { cfg, ops, alertTopic, ledger } = props;
    const p = cfg.prefix;
    const stack = Stack.of(this);

    // --- quyền và cấu hình cho /ops/summary: chỉ Query trên đúng bảng đếm, không ghi ------------------------------------
    ledger.addToRolePolicy(
      new iam.PolicyStatement({
        sid: 'OpsReadModelUsage',
        actions: ['dynamodb:Query'],
        resources: [stack.formatArn({ service: 'dynamodb', resource: 'table', resourceName: props.usageTableName })],
      }),
    );
    ledger.addEnvironment('YOFINA_USAGE_TABLE', props.usageTableName);

    const five = Duration.minutes(5);
    const toolFns = [`${p}-ledger`, `${p}-forecast`];
    const otherFns = [
      `${p}-forecast-batch`,
      `${p}-on-transaction`,
      `${p}-classify`,
      `${p}-roadmap-regen`,
      `${p}-ingest-api`,
      `${p}-ingest`,
      `${p}-gw-interceptor`,
    ];
    const fnMetric = (name: string, metricName: string, statistic: string, period = five) =>
      new cloudwatch.Metric({
        namespace: 'AWS/Lambda',
        metricName,
        statistic,
        period,
        dimensionsMap: { FunctionName: name },
        label: name,
      });
    const dlqs = [`${p}-forecast-events-dlq`, `${p}-classify-events-dlq`, `${p}-roadmap-events-dlq`, `${p}-ingest-jobs-dlq`];
    const caps = modelCaps(ops.llmDefaults);
    const day = Duration.days(1);
    const invocations = (modelId: string) =>
      new cloudwatch.Metric({
        namespace: 'AWS/Bedrock',
        metricName: 'Invocations',
        statistic: 'Sum',
        period: day,
        dimensionsMap: { ModelId: modelId },
        label: `${modelId} (trần ${caps.get(modelId)}/ngày)`,
      });
    // Quyết định Cedar của Gateway: metric có sẵn của AgentCore Policy, theo policy engine `${p}_policy_engine` (id có hậu tố do
    // dịch vụ sinh nên tìm theo tên). SEARCH chỉ vẽ được, không đặt alarm được.
    const decisions = (metricName: string) =>
      new cloudwatch.MathExpression({
        expression: `SEARCH('{AWS/Bedrock-AgentCore,OperationName,PolicyEngine} MetricName="${metricName}" PolicyEngine=${p}_policy_engine', 'Sum', 300)`,
        label: metricName,
        period: five,
      });
    const cluster = `${p}-db`;
    const rds = (metricName: string, statistic: string) =>
      new cloudwatch.Metric({
        namespace: 'AWS/RDS',
        metricName,
        statistic,
        period: five,
        dimensionsMap: { DBClusterIdentifier: cluster },
        label: `${metricName} ${statistic}`,
      });
    const api = (metricName: string, statistic: string) =>
      new cloudwatch.Metric({
        namespace: 'AWS/ApiGateway',
        metricName,
        statistic,
        period: five,
        dimensionsMap: { ApiId: props.apiId },
        label: `${metricName} ${statistic}`,
      });

    this.dashboard = new cloudwatch.Dashboard(this, 'Dashboard', {
      dashboardName: `${p}-ops`,
      defaultInterval: Duration.days(1),
    });
    this.dashboard.addWidgets(
      new cloudwatch.TextWidget({
        markdown:
          `## ${p}-ops\nTừng lượt chat (router, tool, verifier, luật, token, chi phí ước tính) xem ở màn trace của app (` +
          '`GET /ops/traces`, chỉ nhóm Cognito `ops`). Dashboard này chỉ dùng metric AWS có sẵn; không bật Transaction Search.',
        width: 24,
        height: 2,
      }),
    );
    this.dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'Độ trễ tool (Lambda ledger, forecast): p50 và p95, ms',
        left: toolFns.flatMap((n) =>
          ['p50', 'p95'].map((s) => fnMetric(n, 'Duration', s).with({ label: `${n} ${s}` })),
        ),
        leftAnnotations: [{ value: ops.ledgerP95AlarmMs, label: 'Ngưỡng alarm p95 ledger' }],
        width: 12,
      }),
      new cloudwatch.GraphWidget({
        title: 'Lỗi Lambda (Errors, tổng 5 phút)',
        left: [...toolFns, ...otherFns].map((n) => fnMetric(n, 'Errors', 'Sum')),
        width: 12,
      }),
    );
    this.dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'DLQ: tin chưa xử lý được (ApproximateNumberOfMessagesVisible, lớn nhất)',
        left: dlqs.map(
          (q) =>
            new cloudwatch.Metric({
              namespace: 'AWS/SQS',
              metricName: 'ApproximateNumberOfMessagesVisible',
              statistic: 'Maximum',
              period: five,
              dimensionsMap: { QueueName: q },
              label: q,
            }),
        ),
        width: 12,
      }),
      new cloudwatch.GraphWidget({
        title: `Gateway: quyết định Cedar (AllowDecisions, DenyDecisions của ${p}_policy_engine)`,
        left: [decisions('AllowDecisions')],
        right: [decisions('DenyDecisions')],
        width: 12,
      }),
    );
    this.dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: `Aurora ${cluster}: ACU (ServerlessDatabaseCapacity) và % dùng`,
        left: [rds('ServerlessDatabaseCapacity', 'Average'), rds('ServerlessDatabaseCapacity', 'Maximum')],
        right: [rds('ACUUtilization', 'Maximum')],
        leftAnnotations: [{ value: cfg.dbMaxAcu, label: 'ACU tối đa' }],
        width: 12,
      }),
      new cloudwatch.GraphWidget({
        title: 'Lượt gọi model mỗi ngày (AWS/Bedrock Invocations, cả tài khoản) so với trần của yofina_core.llm',
        left: [...caps.keys()].map(invocations),
        width: 12,
      }),
    );
    this.dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: `REST ${p}-api: lỗi 5xx, 4xx`,
        left: [api('5xx', 'Sum'), api('4xx', 'Sum')],
        width: 12,
      }),
      new cloudwatch.GraphWidget({
        title: `REST ${p}-api: độ trễ p95 (ms)`,
        left: [api('Latency', 'p95'), api('IntegrationLatency', 'p95')],
        width: 12,
      }),
    );

    // --- alarm về topic SNS sẵn có ---------------------------------------------------------------------------------------
    const alarm = (logicalId: string, props: cloudwatch.AlarmProps): cloudwatch.Alarm => {
      const a = new cloudwatch.Alarm(this, logicalId, props);
      a.addAlarmAction(new cwActions.SnsAction(alertTopic));
      this.alarms.push(a);
      return a;
    };
    if (ops.guardrailErrorAlarmThreshold > 0) {
      const runtimeId = ssm.StringParameter.valueForStringParameter(this, `/${p}/agent/runtime-id`);
      const runtimeLogs = logs.LogGroup.fromLogGroupName(
        this,
        'RuntimeLogs',
        `/aws/bedrock-agentcore/runtimes/${runtimeId}-${ops.runtimeEndpointName}`,
      );
      // main.py ghi %(message)s ra stdout. Lọc trường event để bỏ qua lý do của memory_write_skipped.
      new logs.MetricFilter(this, 'GuardrailErrorsFilter', {
        logGroup: runtimeLogs,
        filterPattern: logs.FilterPattern.stringValue('$.event', '=', 'guardrail_error'),
        metricNamespace: GUARDRAIL_METRIC_NAMESPACE,
        metricName: GUARDRAIL_ERROR_METRIC_NAME,
        metricValue: '1',
      });
      alarm('GuardrailErrorsAlarm', {
        alarmName: `${p}-ops-guardrail-errors`,
        alarmDescription: 'Loi guardrail trong 5 phut. Xem log Runtime va kiem tra che do fail-open/fail-closed theo cau hinh.',
        metric: new cloudwatch.Metric({
          namespace: GUARDRAIL_METRIC_NAMESPACE,
          metricName: GUARDRAIL_ERROR_METRIC_NAME,
          statistic: 'Sum',
          period: five,
        }),
        threshold: ops.guardrailErrorAlarmThreshold,
        comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        evaluationPeriods: 1,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
    }
    const errorsExpr = new cloudwatch.MathExpression({
      expression: toolFns.map((_, i) => `e${i}`).join(' + '),
      usingMetrics: Object.fromEntries(toolFns.map((n, i) => [`e${i}`, fnMetric(n, 'Errors', 'Sum')])),
      period: five,
      label: 'Lỗi Lambda tool',
    });
    alarm('ToolErrorsAlarm', {
      alarmName: `${p}-ops-tool-lambda-errors`,
      alarmDescription: `Lambda tool (${toolFns.join(', ')}) loi chua bat duoc trong 5 phut: xem log va man trace /ops/traces?outcome=error`,
      metric: errorsExpr,
      threshold: ops.toolErrorsAlarmThreshold,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      evaluationPeriods: 1,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    alarm('LedgerLatencyAlarm', {
      alarmName: `${p}-ops-ledger-p95-latency`,
      alarmDescription: `p95 thoi luong ${p}-ledger vuot ${ops.ledgerP95AlarmMs} ms 15 phut lien (Aurora dang thuc day hoac truy van cham)`,
      metric: fnMetric(`${p}-ledger`, 'Duration', 'p95'),
      threshold: ops.ledgerP95AlarmMs,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      evaluationPeriods: 3,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    if (ops.acuAtMaxAlarmMinutes > 0) {
      alarm('AcuAtMaxAlarm', {
        alarmName: `${p}-ops-aurora-acu-at-max`,
        alarmDescription: `Aurora ${cluster} chay o ACU toi da (${cfg.dbMaxAcu}) lien ${ops.acuAtMaxAlarmMinutes} phut`,
        metric: rds('ServerlessDatabaseCapacity', 'Minimum'),
        threshold: cfg.dbMaxAcu,
        comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        evaluationPeriods: ops.acuAtMaxAlarmMinutes / 5,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
    }
    if (ops.modelCapAlarmPercent > 0) {
      // Một alarm mỗi model: tổng 24 giờ (cửa sổ trượt, không theo ngày lịch như trần) đạt phần trăm của trần ngày. Metric Bedrock tính cả
      // tài khoản, nên có thể kêu sớm nếu tài khoản có ứng dụng khác dùng cùng model; số chính xác theo trần ở /ops/summary.
      [...caps.entries()].forEach(([modelId, cap], i) => {
        if (cap <= 0) return;
        alarm(`ModelCapAlarm${i}`, {
          alarmName: `${p}-ops-model-calls-${modelId.replace(/[^A-Za-z0-9-]+/g, '-')}`,
          alarmDescription: `Luot goi ${modelId} trong 24 gio dat ${ops.modelCapAlarmPercent}% tran ngay (${cap}) cua yofina_core.llm`,
          metric: invocations(modelId),
          threshold: Math.ceil((cap * ops.modelCapAlarmPercent) / 100),
          comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
          evaluationPeriods: 1,
          treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
        });
      });
    }
  }
}
