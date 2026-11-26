import * as fs from 'fs';
import * as path from 'path';
import { App, ArnFormat, CfnOutput, Duration, Fn, RemovalPolicy, Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as agentcore from 'aws-cdk-lib/aws-bedrockagentcore';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as ssm from 'aws-cdk-lib/aws-ssm';
import { YofinaConfig } from '../config/config';
import { YofinaGuardrail } from './guardrail';
import { YofinaMemory } from './memory';
import { publishParams } from './ssm-outputs';
import { ToolsConfig } from './tools-stack';

const REPO = path.resolve(__dirname, '..', '..');

/**
 * Cấu hình riêng của stack `YofinaAgent` (Gateway, interceptor, Cedar, Runtime). Đổi bằng context `-c khóa=giá trị`.
 * Không giá trị nào phụ thuộc tài khoản.
 */
export interface AgentConfig {
  /** Chế độ policy engine của Gateway: `LOG_ONLY` (chỉ ghi quyết định, mọi lời gọi qua) hoặc `ENFORCE`. */
  readonly policyMode: 'LOG_ONLY' | 'ENFORCE';
  /** `DEBUG` cho thông điệp lỗi chi tiết hơn; rỗng (mặc định) = mức mặc định của Gateway. Đã thử: với luật `permit` thì hai mức cho cùng thông điệp từ chối. */
  readonly gatewayExceptionLevel: string;
  /** Tên AgentCore Runtime (chỉ `[a-zA-Z][a-zA-Z0-9_]*`). */
  readonly runtimeName: string;
  /** Tham số SSM giữ khóa S3 của zip agent hiện hành (scripts/agent_deploy.py ghi trước mỗi lần deploy). */
  readonly zipKeyParam: string;
  readonly platformVersion: string;
  readonly interceptorTimeoutSeconds: number;
}

function ctxStr(app: App, key: string, dflt: string): string {
  const v = app.node.tryGetContext(key);
  return v === undefined || v === null ? dflt : String(v);
}

export function loadAgentConfig(app: App): AgentConfig {
  const mode = ctxStr(app, 'policyMode', 'ENFORCE');
  if (mode !== 'LOG_ONLY' && mode !== 'ENFORCE') throw new Error('context policyMode phải là LOG_ONLY hoặc ENFORCE');
  return {
    policyMode: mode,
    gatewayExceptionLevel: ctxStr(app, 'gatewayExceptionLevel', ''),
    runtimeName: ctxStr(app, 'agentRuntimeName', 'yofina_agent'),
    zipKeyParam: ctxStr(app, 'agentZipKeyParam', '/yofina/agent/zip-key'),
    platformVersion: ctxStr(app, 'agentPlatformVersion', 'V2'),
    interceptorTimeoutSeconds: Number(ctxStr(app, 'interceptorTimeoutSeconds', '5')),
  };
}

export interface AgentProps extends StackProps {
  readonly cfg: YofinaConfig;
  readonly tools: ToolsConfig;
  readonly agent: AgentConfig;
}

interface LlmDefaults {
  roles: Record<string, { models: Array<{ id: string }> }>;
}

/** Bỏ dòng chú thích `//` và thay `${GATEWAY_ARN}` bằng token CloudFormation (Fn::Join). */
function renderCedar(file: string, gatewayArn: string, limits: { move: number; transaction: number }): string {
  const raw = fs
    .readFileSync(file, 'utf-8')
    .split(/\r?\n/)
    .filter((l) => !l.trimStart().startsWith('//'))
    .join('\n')
    .trim()
    .replace(/\$\{MOVE_MAX_AMOUNT_VND\}/g, String(limits.move))
    .replace(/\$\{TRANSACTION_MAX_AMOUNT_VND\}/g, String(limits.transaction));
  const parts = raw.split('${GATEWAY_ARN}');
  const pieces: string[] = [];
  parts.forEach((p, i) => {
    if (i > 0) pieces.push(gatewayArn);
    pieces.push(p);
  });
  return Fn.join('', pieces);
}

/**
 * Gateway MCP `yofina-gateway` (JWT authorizer Cognito, interceptor ghi đè `user_id`, policy engine Cedar mỗi tool),
 * target `ledger` trỏ Lambda `yofina-ledger`, và AgentCore Runtime `yofina_agent` (CodeZip ARM64, platform V2, AG-UI).
 *
 * Phần chưa có construct L2 phù hợp dùng L1 (`Cfn*`). Giá trị của stack khác đọc từ SSM `/yofina/...` lúc deploy
 * (không `Fn::ImportValue`). Giá trị phụ thuộc tài khoản chỉ đi vào SSM, không vào repo.
 */
export class AgentStack extends Stack {
  constructor(scope: Construct, id: string, props: AgentProps) {
    super(scope, id, props);
    const { cfg, tools, agent } = props;
    const p = cfg.prefix;
    const param = (name: string) => ssm.StringParameter.valueForStringParameter(this, `/${p}/${name}`);

    const ledgerArn = param('ledger/function-arn');
    const forecastArn = param('forecast/function-arn');
    const clientId = param('auth/client-id');
    const discoveryUrl = param('auth/discovery-url');
    const artifactBucket = param('s3/artifact-bucket');
    const usageTable = param('dynamodb/usage-table');
    const zipKey = ssm.StringParameter.valueForStringParameter(this, agent.zipKeyParam);

    // --- interceptor ----------------------------------------------------------------------
    const interceptor = new lambda.Function(this, 'Interceptor', {
      functionName: `${p}-gw-interceptor`,
      description: 'Gateway request interceptor: ghi de user_id bang sub cua JWT',
      runtime: lambda.Runtime.PYTHON_3_13,
      architecture: lambda.Architecture.ARM_64,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset(path.join(REPO, 'gateway', 'interceptor'), {
        exclude: ['README.md', '__pycache__', '*.pyc'],
      }),
      memorySize: 128,
      timeout: Duration.seconds(agent.interceptorTimeoutSeconds),
      logGroup: new logs.LogGroup(this, 'InterceptorLogs', {
        logGroupName: `/aws/lambda/${p}-gw-interceptor`,
        retention: cfg.logRetentionDays as logs.RetentionDays,
        removalPolicy: RemovalPolicy.DESTROY,
      }),
    });

    // --- policy engine --------------------------------------------------------------------
    const engine = new agentcore.CfnPolicyEngine(this, 'PolicyEngine', {
      name: `${p}_policy_engine`,
      description: 'Cedar: lop phu (khop user_id, han muc) cho tool sau Gateway yofina-gateway',
    });

    // --- vai trò của Gateway --------------------------------------------------------------
    const gatewayArnPattern = this.formatArn({
      service: 'bedrock-agentcore',
      resource: 'gateway',
      resourceName: '*',
    });
    const gatewayRole = new iam.Role(this, 'GatewayRole', {
      roleName: `${p}-gateway`,
      assumedBy: new iam.PrincipalWithConditions(new iam.ServicePrincipal('bedrock-agentcore.amazonaws.com'), {
        StringEquals: { 'aws:SourceAccount': this.account },
        ArnLike: { 'aws:SourceArn': gatewayArnPattern },
      }),
    });
    gatewayRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'InvokeTargetAndInterceptor',
        actions: ['lambda:InvokeFunction'],
        resources: [ledgerArn, forecastArn, interceptor.functionArn],
      }),
    );
    gatewayRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'PolicyEngine',
        actions: [
          'bedrock-agentcore:GetPolicyEngine',
          'bedrock-agentcore:AuthorizeAction',
          'bedrock-agentcore:PartiallyAuthorizeActions',
        ],
        resources: [engine.attrPolicyEngineArn, gatewayArnPattern],
      }),
    );

    // --- Gateway --------------------------------------------------------------------------
    const gateway = new agentcore.CfnGateway(this, 'Gateway', {
      name: `${p}-gateway`,
      description: 'Cong tool MCP cua Yofina: target ledger va forecast, interceptor user_id, Cedar',
      protocolType: 'MCP',
      authorizerType: 'CUSTOM_JWT',
      authorizerConfiguration: {
        customJwtAuthorizer: { discoveryUrl, allowedClients: [clientId] },
      },
      roleArn: gatewayRole.roleArn,
      interceptorConfigurations: [
        {
          interceptor: { lambda: { arn: interceptor.functionArn } },
          interceptionPoints: ['REQUEST'],
          inputConfiguration: { passRequestHeaders: true },
        },
      ],
      policyEngineConfiguration: { arn: engine.attrPolicyEngineArn, mode: agent.policyMode },
      ...(agent.gatewayExceptionLevel ? { exceptionLevel: agent.gatewayExceptionLevel } : {}),
    });
    gateway.node.addDependency(gatewayRole);

    // --- target ledger: schema lấy từ hợp đồng --------------------------------------------
    const toolDefs = JSON.parse(
      fs.readFileSync(path.join(REPO, 'contracts', 'tools', 'ledger.json'), 'utf-8'),
    ) as Array<{ name: string }>;
    const target = new agentcore.CfnGatewayTarget(this, 'LedgerTarget', {
      gatewayIdentifier: gateway.attrGatewayIdentifier,
      name: 'ledger',
      description: 'Lambda yofina-ledger: 9 tool vi mo phong (doc, ghi co xac nhan) va luu luot hoi thoai',
      targetConfiguration: {
        mcp: { lambda: { lambdaArn: ledgerArn, toolSchema: { inlinePayload: toolDefs as any } } },
      },
      credentialProviderConfigurations: [{ credentialProviderType: 'GATEWAY_IAM_ROLE' }],
    });

    // --- Cedar: một policy mỗi tool (thiếu file là lỗi: tool không có policy sẽ bị từ chối mặc định) ---
    const policyDir = path.join(REPO, 'gateway', 'policies');
    for (const tool of toolDefs) {
      const file = path.join(policyDir, `${tool.name}.cedar`);
      if (!fs.existsSync(file)) throw new Error(`Thiếu luật Cedar cho tool ${tool.name}: ${file}`);
      const policy = new agentcore.CfnPolicy(this, `Policy-${tool.name}`, {
        policyEngineId: engine.attrPolicyEngineId,
        name: `ledger_${tool.name}_own_user`,
        description: `Cedar cho ledger___${tool.name}`,
        definition: {
          cedar: {
            statement: renderCedar(file, gateway.attrGatewayArn, {
              move: tools.moveMaxAmountVnd,
              transaction: tools.transactionMaxAmountVnd,
            }),
          },
        },
        validationMode: 'FAIL_ON_ANY_FINDINGS',
      });
      policy.node.addDependency(target);
    }

    // --- target forecast (get_forecast, run_scenario, affordability_check) và ba target phase 3 (planner, knowledge, audit) ---
    // Cùng interceptor và Cedar. `planner`, `knowledge`, `audit` cùng trỏ Lambda yofina-ledger (người điều phối chốt, không có Lambda riêng).
    const extraTargets: Array<{ name: string; arn: string; description: string }> = [
      { name: 'forecast', arn: forecastArn, description: 'Lambda yofina-forecast: du bao, kich ban what-if, kiem tra truoc khi quet' },
      { name: 'planner', arn: ledgerArn, description: 'Lambda yofina-ledger: kiem tra suitability va dat/huy loi nhac (ghi co xac nhan)' },
      { name: 'knowledge', arn: ledgerArn, description: 'Lambda yofina-ledger: bieu phi co cau truc (khong qua RAG), ty gia ngoai te va tinh ngay tu dac ta' },
      { name: 'audit', arn: ledgerArn, description: 'Lambda yofina-ledger: ban ghi luot tra loi cho bang Vi sao' },
    ];
    let previousTarget: agentcore.CfnGatewayTarget = target;
    for (const t of extraTargets) {
      const defs = JSON.parse(
        fs.readFileSync(path.join(REPO, 'contracts', 'tools', `${t.name}.json`), 'utf-8'),
      ) as Array<{ name: string }>;
      const cfnTarget = new agentcore.CfnGatewayTarget(this, `${t.name[0].toUpperCase()}${t.name.slice(1)}Target`, {
        gatewayIdentifier: gateway.attrGatewayIdentifier,
        name: t.name,
        description: t.description,
        targetConfiguration: {
          mcp: { lambda: { lambdaArn: t.arn, toolSchema: { inlinePayload: defs as any } } },
        },
        credentialProviderConfigurations: [{ credentialProviderType: 'GATEWAY_IAM_ROLE' }],
      });
      cfnTarget.node.addDependency(previousTarget); // tuần tự: một lần chỉ đổi một target của Gateway
      previousTarget = cfnTarget;
      for (const tool of defs) {
        const file = path.join(policyDir, `${tool.name}.cedar`);
        if (!fs.existsSync(file)) throw new Error(`Thiếu luật Cedar cho tool ${tool.name}: ${file}`);
        const policy = new agentcore.CfnPolicy(this, `Policy-${t.name}-${tool.name}`, {
          policyEngineId: engine.attrPolicyEngineId,
          name: `${t.name}_${tool.name}_own_user`,
          description: `Cedar cho ${t.name}___${tool.name}`,
          definition: {
            cedar: {
              statement: renderCedar(file, gateway.attrGatewayArn, {
                move: tools.moveMaxAmountVnd,
                transaction: tools.transactionMaxAmountVnd,
              }),
            },
          },
          validationMode: 'FAIL_ON_ANY_FINDINGS',
        });
        policy.node.addDependency(cfnTarget);
      }
    }

    // --- target ingest (phase 5, F6): Lambda yofina-ingest-api của stack YofinaIngest ------
    addIngestTarget(this, {
      gateway,
      gatewayRole,
      engine,
      after: previousTarget,
      functionName: param('ingest/api-function-name'),
      renderPolicy: (file) =>
        renderCedar(file, gateway.attrGatewayArn, {
          move: tools.moveMaxAmountVnd,
          transaction: tools.transactionMaxAmountVnd,
        }),
    });

    // --- vai trò của Runtime (quyền tối thiểu) --------------------------------------------
    const llm = JSON.parse(
      fs.readFileSync(path.join(REPO, 'libs', 'yofina_core', 'src', 'yofina_core', 'llm_defaults.json'), 'utf-8'),
    ) as LlmDefaults;
    const modelIds = Array.from(new Set(Object.values(llm.roles).flatMap((r) => r.models.map((m) => m.id))));
    const modelArns: string[] = [];
    for (const m of modelIds) {
      if (m.startsWith('global.')) {
        modelArns.push(`arn:aws:bedrock:${this.region}:${this.account}:inference-profile/${m}`);
        modelArns.push(`arn:aws:bedrock:*::foundation-model/${m.slice('global.'.length)}`);
      } else {
        modelArns.push(`arn:aws:bedrock:${this.region}::foundation-model/${m}`);
      }
    }
    const guardrail = new YofinaGuardrail(this, 'Guardrail');
    const runtimeRole = new iam.Role(this, 'RuntimeRole', {
      roleName: `${p}-agent-runtime`,
      assumedBy: new iam.PrincipalWithConditions(new iam.ServicePrincipal('bedrock-agentcore.amazonaws.com'), {
        StringEquals: { 'aws:SourceAccount': this.account },
        ArnLike: {
          'aws:SourceArn': this.formatArn({ service: 'bedrock-agentcore', resource: 'runtime', resourceName: '*' }),
        },
      }),
    });
    const ssmArn = (name: string) => `arn:aws:ssm:${this.region}:${this.account}:parameter/${name}`;
    const logGroupArn = `arn:aws:logs:${this.region}:${this.account}:log-group:/aws/bedrock-agentcore/runtimes/*`;
    runtimeRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'InvokeConfiguredModels',
        actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
        resources: modelArns,
      }),
    );
    runtimeRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'CountModelCalls',
        actions: ['dynamodb:UpdateItem'],
        resources: [this.formatArn({ service: 'dynamodb', resource: 'table', resourceName: usageTable })],
      }),
    );
    runtimeRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'ReadConfig',
        actions: ['ssm:GetParameter', 'ssm:GetParametersByPath'],
        resources: [
          ssmArn(`${p}/gateway_url`),
          ssmArn(`${p}/dynamodb/usage-table`),
          ssmArn(`${p}/llm`),
          ssmArn(`${p}/llm/*`),
          ssmArn(`${p}/guardrail/id`),
          ssmArn(`${p}/guardrail/version`),
          ssmArn(`${p}/quota/*`),
          ssmArn(`${p}/agent/reasoning_enabled`),
        ],
      }),
    );
    runtimeRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'ApplyGuardrail',
        actions: ['bedrock:ApplyGuardrail'],
        // Hồ sơ liên vùng có thể chuyển lời gọi sang vùng khác trong APAC: phải cho phép hồ sơ ở mọi vùng đích.
        resources: [guardrail.guardrailArn, ...guardrail.profileDestinationArns],
      }),
    );
    runtimeRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'ReadOwnCode',
        actions: ['s3:GetObject'],
        resources: [`arn:aws:s3:::${artifactBucket}/builds/*`],
      }),
    );
    runtimeRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'Logs',
        actions: ['logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents', 'logs:DescribeLogStreams'],
        resources: [logGroupArn, `${logGroupArn}:*`],
      }),
    );
    runtimeRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'LogGroups',
        actions: ['logs:DescribeLogGroups'],
        resources: [`arn:aws:logs:${this.region}:${this.account}:log-group:*`],
      }),
    );
    runtimeRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'Xray',
        actions: ['xray:PutTraceSegments', 'xray:PutTelemetryRecords', 'xray:GetSamplingRules', 'xray:GetSamplingTargets'],
        resources: ['*'],
      }),
    );
    runtimeRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'Metrics',
        actions: ['cloudwatch:PutMetricData'],
        resources: ['*'],
        conditions: { StringEquals: { 'cloudwatch:namespace': 'bedrock-agentcore' } },
      }),
    );
    runtimeRole.addToPolicy(
      new iam.PolicyStatement({
        sid: 'WorkloadIdentity',
        actions: [
          'bedrock-agentcore:GetWorkloadAccessToken',
          'bedrock-agentcore:GetWorkloadAccessTokenForJWT',
          'bedrock-agentcore:GetWorkloadAccessTokenForUserId',
        ],
        resources: [
          `arn:aws:bedrock-agentcore:${this.region}:${this.account}:workload-identity-directory/default`,
          `arn:aws:bedrock-agentcore:${this.region}:${this.account}:workload-identity-directory/default/workload-identity/${agent.runtimeName}-*`,
        ],
      }),
    );

    // --- AgentCore Memory (phase 5, luồng B): một Memory cho cả ứng dụng, namespace theo sub; quyền tối thiểu cho Runtime -------
    const memory = new YofinaMemory(this, 'LongTermMemory', {
      alertTopic: sns.Topic.fromTopicArn(this, 'AlertTopic', param('sns/alert-topic-arn')),
    });
    memory.grantAgentRuntime(runtimeRole);

    // --- Runtime --------------------------------------------------------------------------
    const runtime = new agentcore.CfnRuntime(this, 'AgentRuntime', {
      agentRuntimeName: agent.runtimeName,
      description: 'Yofina Foresight agent (Strands, AG-UI qua SSE)',
      agentRuntimeArtifact: {
        codeConfiguration: {
          code: { s3: { bucket: artifactBucket, prefix: zipKey } },
          runtime: 'PYTHON_3_13',
          entryPoint: ['main.py'],
        },
      },
      roleArn: runtimeRole.roleArn,
      networkConfiguration: { networkMode: 'PUBLIC' },
      protocolConfiguration: 'AGUI',
      platformVersion: agent.platformVersion,
      authorizerConfiguration: {
        customJwtAuthorizer: { discoveryUrl, allowedClients: [clientId] },
      },
      requestHeaderConfiguration: { requestHeaderAllowlist: ['Authorization'] },
      environmentVariables: {
        YOFINA_REGION: cfg.region,
        YOFINA_SSM_PREFIX: `/${p}`,
        YOFINA_GATEWAY_URL: gateway.attrGatewayUrl,
        YOFINA_USAGE_TABLE: usageTable,
        YOFINA_TURN_BLOCKS_TOOL: 'ledger___save_turn',
        YOFINA_TURN_RECORD_TOOL: 'audit___record_turn',
        YOFINA_LOG_LEVEL: 'INFO',
        YOFINA_MEMORY_ID: memory.memoryId,
      },
    });
    runtime.node.addDependency(runtimeRole);
    runtime.node.addDependency(guardrail);

    const runtimeUrl = Fn.join('', [
      `https://bedrock-agentcore.${this.region}.amazonaws.com/runtimes/arn%3Aaws%3Abedrock-agentcore%3A${this.region}%3A${this.account}%3Aruntime%2F`,
      runtime.attrAgentRuntimeId,
      '/invocations?qualifier=DEFAULT',
    ]);
    publishParams(this, {
      gateway_url: gateway.attrGatewayUrl,
      'gateway/id': gateway.attrGatewayIdentifier,
      'gateway/arn': gateway.attrGatewayArn,
      'agent/runtime-arn': runtime.attrAgentRuntimeArn,
      'agent/runtime-id': runtime.attrAgentRuntimeId,
      'agent/runtime-url': runtimeUrl,
    });
    new CfnOutput(this, 'GatewayId', { value: gateway.attrGatewayIdentifier });
    new CfnOutput(this, 'RuntimeId', { value: runtime.attrAgentRuntimeId });
  }
}

export interface IngestTargetProps {
  readonly gateway: agentcore.CfnGateway;
  readonly gatewayRole: iam.Role;
  readonly engine: agentcore.CfnPolicyEngine;
  /** Target tạo trước (Gateway chỉ đổi một target mỗi lần): target ingest đi sau nó. */
  readonly after: agentcore.CfnGatewayTarget;
  /** Tên Lambda `yofina-ingest-api` (SSM `/yofina/ingest/api-function-name` do stack YofinaIngest ghi). */
  readonly functionName: string;
  /** Đọc một file Cedar và thay placeholder (cùng hàm với các target khác). */
  readonly renderPolicy: (file: string) => string;
}

/**
 * Target Gateway `ingest` (phase 5, F6): ba tool `ingest___start_job`, `ingest___get_job_status`, `ingest___confirm_rows` của
 * `contracts/tools/ingest.json`, trỏ Lambda `yofina-ingest-api` (cùng Lambda với REST `/ingest/*`: `handler_api.handler` rẽ theo dạng
 * sự kiện). Cùng interceptor ghi đè `user_id` và một policy Cedar mỗi tool (`gateway/policies/<tool>.cedar`, thiếu là lỗi synth).
 * `confirm_rows` chỉ ghi khi có token xác nhận do REST cấp (Lambda kiểm, như `POST /ingest/actions`).
 *
 * Quyền: vai của Gateway được `lambda:InvokeFunction` đúng hàm này (không wildcard). Deploy YofinaIngest TRƯỚC YofinaAgent (tham số SSM).
 */
export function addIngestTarget(stack: Stack, props: IngestTargetProps): agentcore.CfnGatewayTarget {
  const fnArn = stack.formatArn({
    service: 'lambda',
    resource: 'function',
    resourceName: props.functionName,
    arnFormat: ArnFormat.COLON_RESOURCE_NAME,
  });
  props.gatewayRole.addToPolicy(
    new iam.PolicyStatement({ sid: 'InvokeIngestTarget', actions: ['lambda:InvokeFunction'], resources: [fnArn] }),
  );
  const defs = JSON.parse(
    fs.readFileSync(path.join(REPO, 'contracts', 'tools', 'ingest.json'), 'utf-8'),
  ) as Array<{ name: string }>;
  const target = new agentcore.CfnGatewayTarget(stack, 'IngestTarget', {
    gatewayIdentifier: props.gateway.attrGatewayIdentifier,
    name: 'ingest',
    description: 'Lambda yofina-ingest-api: trang thai lan nap anh/CSV, bang duyet dong, chot dong (ghi co xac nhan)',
    targetConfiguration: {
      mcp: { lambda: { lambdaArn: fnArn, toolSchema: { inlinePayload: defs as any } } },
    },
    credentialProviderConfigurations: [{ credentialProviderType: 'GATEWAY_IAM_ROLE' }],
  });
  target.node.addDependency(props.after);
  target.node.addDependency(props.gatewayRole); // quyền gọi Lambda có trước khi Gateway gắn target
  const policyDir = path.join(REPO, 'gateway', 'policies');
  for (const tool of defs) {
    const file = path.join(policyDir, `${tool.name}.cedar`);
    if (!fs.existsSync(file)) throw new Error(`Thiếu luật Cedar cho tool ${tool.name}: ${file}`);
    const policy = new agentcore.CfnPolicy(stack, `Policy-ingest-${tool.name}`, {
      policyEngineId: props.engine.attrPolicyEngineId,
      name: `ingest_${tool.name}_own_user`,
      description: `Cedar cho ingest___${tool.name}`,
      definition: { cedar: { statement: props.renderPolicy(file) } },
      validationMode: 'FAIL_ON_ANY_FINDINGS',
    });
    policy.node.addDependency(target);
  }
  return target;
}