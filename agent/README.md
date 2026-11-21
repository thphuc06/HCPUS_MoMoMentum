# agent/

Agent Strands chạy trên AgentCore Runtime: harness 6 tầng L0–L5 (cổng vào, Intent Router, Orchestrator, 4 specialist: Analyst / Simulation / Roadmap / Ingestion, Verifier, Composer), schema Pydantic (`IntentResult`, `Plan`, `Analysis`, `ScenarioSpec`, `ScenarioResult`, `Roadmap`, `Verdict`), luồng thứ tự cố định (kiểm tra trước khi quẹt) viết bằng code tuần tự có timeout cho bước LLM, không dùng Graph của Strands, cấu hình Memory, giao thức AG-UI qua SSE.

- Proposal: §9 (agentic harness, agent, memory, RAG, guardrail, hợp đồng đầu ra), §10.1 (F2), §10.2 (F3), §10.5 (F5), §10.6 (F6), §12.
- Tool agent gọi nằm ở [../gateway/tools/](../gateway/tools/README.md), không viết logic số trong agent.
- Tự viết theo tài liệu chính thức của Strands và AgentCore; pattern `agui-strands-agent` của FAST chỉ để tham khảo, không copy về.
- Đóng gói zip (không Docker), Runtime V2; tool phát khối UI bằng `ACTIVITY_SNAPSHOT`; luôn đặt `limits` và `structured_output_attempts`. Mẫu code chạy được và bẫy đã gặp: [spike-strands-agui-local.md](../docs/research/spike-strands-agui-local.md), [spike-agentcore-runtime-cors.md](../docs/research/spike-agentcore-runtime-cors.md).
- Bộ model (đề xuất, chưa chốt): [spike-bedrock-models.md](../docs/research/spike-bedrock-models.md); tổng hợp ở [overview.md](../docs/architecture/overview.md).