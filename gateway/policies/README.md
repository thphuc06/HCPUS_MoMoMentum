# gateway/policies/

Luật Cedar của AgentCore Policy tại Gateway `yofina-gateway` (proposal §9, §16). Một file `.cedar` cho **mỗi tool** của [contracts/tools/ledger.json](../../contracts/tools/ledger.json) và [forecast.json](../../contracts/tools/forecast.json), tên file trùng tên tool; mặc định từ chối, nên tool nào thiếu policy thì không gọi được. Stack `YofinaAgent` (`infra-cdk/lib/agent-stack.ts`) đọc các file này, bỏ dòng chú thích `//`, thay `${GATEWAY_ARN}` (token CloudFormation), `${MOVE_MAX_AMOUNT_VND}` và `${TRANSACTION_MAX_AMOUNT_VND}` (cùng giá trị với `moveMaxAmountVnd` và `transactionMaxAmountVnd` của Lambda ledger) rồi tạo `AWS::BedrockAgentCore::Policy` với `validationMode: FAIL_ON_ANY_FINDINGS`. Synth báo lỗi nếu một tool không có file.

| File | Điều kiện (`when`) |
|---|---|
| `get_jar_balances.cedar`, `query_transactions.cedar`, `get_cashflow_summary.cedar`, `get_obligations.cedar`, `get_unclassified.cedar`, `save_turn.cedar`, `get_forecast.cedar` (action `forecast___get_forecast`, target `forecast`), `list_scenarios.cedar` (action `forecast___list_scenarios`, target `forecast`; cùng mẫu với `run_scenario.cedar`) | `context.input has user_id && context.input.user_id == principal.id` |
| `move_between_jars.cedar` | như trên, thêm `context.input.amount_vnd <= ${MOVE_MAX_AMOUNT_VND}` và `if context.input has confirm_token then context.input.confirm_token like "*.*" else true` |
| `record_transaction.cedar` | như `move_between_jars` với hạn mức `${TRANSACTION_MAX_AMOUNT_VND}` |
| `get_resilience_score.cedar`, `stress_test.cedar` (target `forecast`), `optimize_allocation.cedar`, `get_roadmap.cedar` (target `planner`; phase 4) | `context.input has user_id && context.input.user_id == principal.id` |
| `save_roadmap.cedar` (target `planner`; phase 4) | như trên: tool GHI nhưng KHÔNG đổi số dư nên KHÔNG qua token, Cedar chỉ ép `user_id` (không `confirm_token`); Lambda chạy lại luật suitability cho từng bước |
| `get_fee_schedule.cedar`, `get_exchange_rate.cedar` (target `knowledge`; tỷ giá ngoại tệ thêm 25/11), `resolve_date.cedar` (target `knowledge`; tính ngày từ đặc tả, thêm 26/11, #39) | `context.input has user_id && context.input.user_id == principal.id` |
| `update_profile.cedar`, `assign_jar.cedar` | khớp `user_id` và, nếu có `confirm_token`, dạng `"*.*"`; không có số tiền một lần nên không có hạn mức |

`save_jars` và `confirm_salary` không có policy vì không lộ cho agent (chỉ REST). Test `tests/unit/test_ledger_wallet.py` khẳng định mỗi tool của hợp đồng có đúng một file, đúng dạng, và hạn mức luôn đi qua placeholder (không có số gắn cứng).

Cedar ở đây là **lớp phụ** ([ADR-0002](../../docs/decisions/0002-xac-nhan-truoc-khi-ghi.md)), không phải cơ chế xác nhận:

- Lớp chính là interceptor ([../interceptor/](../interceptor/README.md)) ghi đè `user_id` từ JWT; Cedar thấy tham số **đã bị ghi đè** (thứ tự `JWT authorizer -> interceptor -> Cedar -> kiểm schema -> Lambda`), nên điều kiện `user_id == principal.id` luôn đúng khi interceptor chạy và đóng vai bảo hiểm cấu hình: gỡ interceptor thì Cedar vẫn chặn (đã thử ở [spike-vertical-slice.md](../../docs/research/spike-vertical-slice.md) mục 2: Gateway thử không interceptor, `user_id` của người khác hoặc vắng đều bị `-32002`).
- **Cedar không được chặn lời gọi tool ghi (`move_between_jars`, `record_transaction`, `update_profile`, `assign_jar`) thiếu `confirm_token`**: agent gọi các tool này không token để nhận `NEEDS_CONFIRMATION` (không ghi). Việc kiểm token (chữ ký HMAC, hạn, tool, người, hash tham số, `jti` dùng một lần) nằm ở Lambda; Cedar không kiểm được chữ ký.
- Bộ kiểm kiểu của Cedar từ chối `!(context.input has x) || context.input.x ...` ("unable to guarantee safety of access to optional attribute"); dạng `if context.input has x then ... else true` hoặc `has x && ...` thì qua.
- `user_id` là tham số **tùy chọn** trong schema (LLM thấy "hệ thống tự điền, để trống"); vắng `user_id` ở Cedar thì `has` ra false và bị từ chối, nên interceptor là bắt buộc cho đường chạy bình thường.
- Chế độ engine đặt bằng context CDK `policyMode` (`LOG_ONLY` hoặc `ENFORCE`, mặc định `ENFORCE`). Đưa lên `LOG_ONLY`, xem metric CloudWatch `AWS/Bedrock-AgentCore` (`AllowDecisions`, `DenyDecisions` theo `Mode`, `ToolName`), rồi `ENFORCE`; test `tests/integration/test_gateway_config.py` khẳng định `ENFORCE` để chạy lại khi đóng phase.
- Khi Cedar từ chối: HTTP 200, JSON-RPC `error.code = -32002`, thông điệp `Tool Execution Denied: ... [No policy applies to the request (denied by default).]` (tham số sai kiểu thì `... policy evaluation errors: Value does not match expected type`; Cedar chạy trước kiểm schema). Agent đổi thành `ToolKind.DENIED` và khối `notice` "Bạn không có quyền thực hiện thao tác này".

Cú pháp đã chạy thật, thứ tự tạo (target rồi policy rồi gắn engine) và bẫy `LOG_ONLY`: [spike-agentcore-gateway-identity.md](../../docs/research/spike-agentcore-gateway-identity.md) mục 3b và 4; kết quả của bước ghép thật: [spike-vertical-slice.md](../../docs/research/spike-vertical-slice.md).
