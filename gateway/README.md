# gateway/

Phần "cổng tool" của AgentCore: Lambda tool đăng ký làm target của AgentCore Gateway (MCP) và luật Cedar của AgentCore Policy.
- `policies/`: luật Cedar, mặc định từ chối; ép `user_id == principal.id` và hạn mức số tiền (proposal cho tool ghi qua khi có cờ xác nhận, hiện đề xuất thay bằng token xác nhận, chưa chốt); chạy chế độ chỉ ghi log trước khi bật chặn.
- Cổng gồm Lambda interceptor (ghi đè `user_id` từ JWT) đứng trước Cedar; tên tool lộ ra là `<target>___<tool>`. Đã chạy thử: [spike-agentcore-gateway-identity.md](../docs/research/spike-agentcore-gateway-identity.md).
- `tools/`: một thư mục con cho mỗi nhóm tool, xem [tools/README.md](tools/README.md).
- Proposal: §9 (Tool và MCP, Guardrail và policy), §8. Tóm tắt: [../docs/architecture/overview.md](../docs/architecture/overview.md).