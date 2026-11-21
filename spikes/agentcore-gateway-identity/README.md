# Spike: AgentCore Gateway + Lambda target + Policy (Cedar) + danh tính người dùng

Kết quả và kết luận: `docs/research/spike-agentcore-gateway-identity.md`. Manifest tài nguyên đã tạo và đã xóa: `RESOURCES.md`.

Chạy trên AWS thật, Region `ap-southeast-1`, tiền tố `yofina-spike-gw-`. Tất cả đã được dọn (`teardown.py`). Chạy lại cần credential AWS (`aws login`) và chấp nhận tạo/xóa tài nguyên.

```
uv sync                                  # boto3[crt], mcp<2 (API streamablehttp_client của mcp 1.x), httpx
set PYTHONUTF8=1                         # Windows: in tiếng Việt
uv run python setup_base.py              # IAM role, DynamoDB jti, Cognito (pool, client, user-a, user-b), 3 Lambda
uv run python step1_plain.py             # Q1/Q2 gateway trơn: tools/list, tools/call, event/context Lambda nhận
uv run python step2_interceptor.py       # Q3a interceptor: passthrough / overwrite / deny
uv run python step3_policy.py setup      # policy engine + 2 luật Cedar
uv run python step3_policy.py logonly    # Q4 LOG_ONLY
uv run python step3_policy.py enforce    # Q4 ENFORCE (chưa interceptor)
uv run python step3_policy.py order      # thứ tự interceptor so với policy
uv run python probe_deny.py              # dạng phản hồi từ chối (JSON-RPC thô)
uv run python step4_cedar_variants.py    # claim là tag, kiểm confirm_token trong Cedar, enforcementMode theo policy
uv run python step5_confirm.py           # Q5 token xác nhận HMAC (13 ca)
uv run python step6_latency.py           # Q6 độ trễ 4 cấu hình
uv run python step7_semantic.py          # Q7 semantic search
uv run python probe_limits.py            # giới hạn tên target/tool
uv run python probe_validate.py          # gateway có kiểm schema; header do client gửi
uv run python probe_hidden.py            # user_id không có trong schema nhưng interceptor tiêm vào
uv run python teardown.py                # xóa sạch theo tiền tố, liệt kê lại, ghi vào RESOURCES.md
```

Thư mục `lambdas/`: `ledger` (2 tool, in toàn bộ event/context, kiểm token HMAC), `interceptor` (request interceptor, 3 chế độ qua biến môi trường `MODE`), `confirm` (cấp token xác nhận, xác minh access token bằng `cognito-idp:GetUser`).

Lưu ý: mật khẩu user thử sinh ngẫu nhiên và đặt lại mỗi lần chạy script test (`mcpcall.tokens()`), không lưu ở đâu. Secret HMAC do `setup_base.py` sinh và chỉ nằm trong biến môi trường Lambda (bản thật phải dùng Secrets Manager). `state.json` (tên/ID, không bí mật) bị `teardown.py` xóa.
