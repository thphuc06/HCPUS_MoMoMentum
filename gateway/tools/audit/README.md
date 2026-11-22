# gateway/tools/audit/

Tool `audit___*` (target `audit`, chạy chung Lambda `yofina-ledger`): `record_turn` (agent ghi bản ghi lượt cuối mỗi lượt, `yofina_audit/record.py`) và `get_trace` — dữ liệu cho bảng "Vì sao" (trace_id, dữ liệu đã dùng, luật đã kiểm). Đọc log, bảng `audit_events`. Proposal §9; FR11. `trace_id` do client sinh qua `traceparent` ([spike-agentcore-runtime-cors.md](../../../docs/research/spike-agentcore-runtime-cors.md) mục 6).
