# gateway/interceptor/

Lambda `yofina-gw-interceptor` (Python 3.13, arm64, chỉ thư viện chuẩn): request interceptor của AgentCore Gateway `yofina-gateway`. Ghi đè `params.arguments.user_id` bằng `sub` của JWT cho mọi `tools/call`; thiếu danh tính thì từ chối. Lớp 1 của "danh tính xuống tool" ([spike Gateway §8](../../docs/research/spike-agentcore-gateway-identity.md)); lớp 2 là Cedar ([../policies/](../policies/README.md)).

- Đầu vào/ra: `interceptorInputVersion/OutputVersion 1.0`, `passRequestHeaders: true` để thấy `Authorization`. Chỉ giải mã payload JWT (Gateway đã xác minh chữ ký).
- Mã: [handler.py](handler.py); test: `tests/unit/test_gateway_interceptor.py`. Triển khai bởi stack `YofinaAgent` (`infra-cdk/lib/agent-stack.ts`), không cần build (không có phụ thuộc).
- Không bao giờ ghi token ra log; chỉ ghi tên tool và cờ "client gửi `user_id` khác `sub`" (đây cũng là tín hiệu tấn công đáng theo dõi).
