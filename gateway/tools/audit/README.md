# gateway/tools/audit/

Tool `audit___*` (target `audit`, chạy chung Lambda `yofina-ledger`): `record_turn` (agent ghi bản ghi lượt cuối mỗi lượt, `yofina_audit/record.py`) và `get_trace` — dữ liệu cho bảng "Vì sao" (trace_id, dữ liệu đã dùng, luật đã kiểm). Đọc log, bảng `audit_events`. Proposal §9; FR11. `trace_id` do client sinh qua `traceparent` ([spike-agentcore-runtime-cors.md](../../../docs/research/spike-agentcore-runtime-cors.md) mục 6).

- `record.py`: kiểm bản ghi lượt; `intent` thuộc `wallet.AUDIT_INTENTS` (gồm bốn ý định phase 5); bước có `step` là tên đầy đủ của tool (`<target>___<tool>`) là một lần gọi tool, kèm `status` (`ok`, `error`, `denied`) và `code` khi lỗi.
- `trace.py`: dựng `TraceData` (khối `explain` + chi tiết) cho `GET /traces/{trace_id}` và `audit___get_trace` của chính người gọi.
- `ops_view.py` (phase 5, FR15): dựng `OpsTraceSummary`, `OpsTraceDetail`, `OpsSummaryResponse` cho bảng vận hành `/ops/*` (chỉ nhóm Cognito `ops`) từ dòng của các hàm `app_ops_*` (migration 0053): tách lần gọi tool từ `step_timings`, che PII bằng `yofina_core.pii` ở mọi chữ tự do, chi phí ước tính `est_cost_vnd` theo bảng giá trong `yofina_ledger/ops_defaults.json`. Phần đọc DB, bộ đếm `yofina-usage` và kiểm nhóm nằm ở `gateway/tools/ledger/yofina_ledger/ops.py`, `ops_rest.py`; dashboard `yofina-ops` và alarm ở `infra-cdk/lib/ops-dashboard.ts`.
