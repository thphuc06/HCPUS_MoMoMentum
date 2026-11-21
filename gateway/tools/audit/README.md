# gateway/tools/audit/

Tool `audit___*` (target `audit`): `get_trace` — dữ liệu cho bảng "Vì sao" (trace_id, dữ liệu đã dùng, luật đã kiểm). Đọc log, bảng `audit_events`. Proposal §9; FR11. `trace_id` do client sinh qua `traceparent` ([spike-agentcore-runtime-cors.md](../../../docs/research/spike-agentcore-runtime-cors.md) mục 6).
