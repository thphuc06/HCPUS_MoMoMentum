# gateway/

Phần "cổng tool" của AgentCore: Lambda tool đăng ký làm target của AgentCore Gateway (MCP), Lambda interceptor và luật Cedar của AgentCore Policy. Dựng bởi stack CDK `YofinaAgent` ([infra-cdk/lib/agent-stack.ts](../infra-cdk/lib/agent-stack.ts)).

```
agent (Runtime) --Bearer access token--> Gateway `yofina-gateway` (MCP, JWT authorizer Cognito, allowedClients = yofina-web)
   1. JWT authorizer          kiểm chữ ký, hạn, client_id (ID token và token lạ bị 401/403)
   2. request interceptor     Lambda yofina-gw-interceptor: ghi đè arguments.user_id = sub (interceptor/)
   3. policy engine (Cedar)   một policy mỗi tool, ENFORCE (policies/)
   4. kiểm schema             tool schema lấy từ contracts/tools/ledger.json
   5. target `ledger`         Lambda yofina-ledger (tools/ledger/); tên tool qua Gateway: ledger___<tool>
```

- `interceptor/`: [README](interceptor/README.md) — ghi đè `user_id` từ JWT cho mọi `tools/call`, đóng cửa khi thiếu danh tính.
- `policies/`: [README](policies/README.md) — Cedar lớp phụ (khớp `user_id`, hạn mức chuyển hũ, dạng `confirm_token`); không phải cơ chế xác nhận (ADR-0002).
- `tools/`: một thư mục con cho mỗi nhóm tool, xem [tools/README.md](tools/README.md). Hiện có `ledger` (4 tool: `get_jar_balances`, `query_transactions`, `move_between_jars`, `save_turn`).

## Cấu hình, deploy, ngoài CDK

- Tất cả nằm trong CDK (L1 `aws-cdk-lib/aws-bedrockagentcore`: `CfnGateway`, `CfnGatewayTarget`, `CfnPolicyEngine`, `CfnPolicy`, `CfnRuntime`); **không có tài nguyên nào dựng ngoài CDK** ngoài tham số SSM `/yofina/agent/zip-key` (do `scripts/agent_deploy.py` ghi trước mỗi lần deploy để Runtime đọc khóa zip mới).
- Context CDK của stack: `policyMode` (`ENFORCE` mặc định hoặc `LOG_ONLY`), `gatewayExceptionLevel` (rỗng mặc định; `DEBUG` thêm chi tiết lỗi), `agentRuntimeName`, `agentPlatformVersion` (`V2`), `interceptorTimeoutSeconds`; hạn mức chuyển hũ lấy từ `moveMaxAmountVnd` của `YofinaTools`.
- Deploy: `uv run scripts/cdk.py deploy YofinaAgent --require-approval never` (Gateway, interceptor, Cedar; Runtime không đổi nếu khóa zip không đổi) hoặc `uv run scripts/agent_deploy.py` (build agent, upload, deploy, chờ READY: [agent/README.md](../agent/README.md)).
- URL Gateway ghi vào SSM `/yofina/gateway_url` (`/yofina/gateway/id`, `/yofina/gateway/arn`); agent đọc từ env `YOFINA_GATEWAY_URL` của Runtime.
- Kiểm: `uv run pytest tests/integration/test_gateway_config.py tests/integration/test_gateway_identity.py -m integration` (cấu hình Gateway, danh tính, Cedar, token bịa, hạn mức) và `uv run pytest tests/unit/test_gateway_interceptor.py`.
- Đã chạy thật và số đo: [spike-agentcore-gateway-identity.md](../docs/research/spike-agentcore-gateway-identity.md) (thiết kế), [spike-vertical-slice.md](../docs/research/spike-vertical-slice.md) (bước ghép).
- Proposal: §9 (Tool và MCP, Guardrail và policy), §8. Tóm tắt: [../docs/architecture/overview.md](../docs/architecture/overview.md).
