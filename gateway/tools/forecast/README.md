# gateway/tools/forecast/

Tool `forecast___*` (target `forecast` của AgentCore Gateway). **Phase 2 có một tool: `get_forecast`** ([contracts/tools/forecast.json](../../../contracts/tools/forecast.json), kết quả `GetForecastResult` ở [forecast.results.schema.json](../../../contracts/tools/forecast.results.schema.json)). Các tool còn lại của đề bài (`run_scenario`, `stress_test`, `affordability_check`, `get_resilience_score`, `get_behavior_profile`) là việc của phase 3 trở đi. Không tool nào ghi dữ liệu người dùng. Proposal §9, §10.1, §10.2, §10.4; FR3.

Mã của tool không nằm riêng ở đây: nó dùng chung **một zip** với batch và consumer sự kiện, ở [pipelines/forecast/](../../../pipelines/forecast/README.md) (`handler_tool.py` và `yofina_forecast/tool.py`), vì ba Lambda cần cùng lõi pipeline (dựng đầu vào, engine, ghi bảng). Thư mục này chỉ ghi hợp đồng của tool.

## `forecast___get_forecast {jar}`

- **Đường đi**: agent (Runtime) -> Gateway (JWT, interceptor ghi đè `user_id` bằng `sub`, Cedar `get_forecast.cedar`, kiểm schema) -> Lambda `yofina-forecast` (target `forecast`).
- **Kết quả**: `{status: "OK", as_of, app_date, data}` với `data` là ĐÚNG `data` của khối `forecast_timeline` (đường P10/P50/P90 số dư 30 ngày, mốc nghĩa vụ và lương, ngày cạn, `p_shortfall` chỉ khi đủ tin cậy, nhóm tin cậy, độ phủ, `computed_at`, `stale`). Agent bọc bằng `build_forecast_timeline_from_data` (không tính lại) nên chat và màn Chi tiết hũ cùng số; bản gọn cho model viết câu do agent dựng (`compact_forecast`).
- **Cùng mã dựng với REST**: Lambda này dùng `WalletReads.forecast_block_or_none` của ledger (đóng gói kèm `yofina_ledger`), nên `GET /forecasts/{jar_code}` và tool trả cùng một khối. Test: `tests/integration/test_forecast_pipeline.py::test_tool_forecast_qua_gateway_cung_so_voi_rest_va_khop_hop_dong`.
- **Độ tươi**: chưa có dự báo cho hũ, hoặc `computed_at` quá `forecast_freshness_seconds` (3.600 giây mặc định), hoặc ngày mô phỏng đã sang ngày khác -> tool chạy `Pipeline.run_user(trigger = read)` rồi đọc lại. Nhiều lượt gọi dồn dập không gây bão tính lại: lần chạy `read` bị bỏ qua nếu vừa có lần chạy trẻ hơn `forecast_recompute_guard_seconds` (20 giây). Không tính được mà còn bản cũ thì trả bản cũ với `stale: true`; không có gì thì `FORECAST_UNAVAILABLE`.
- **Mã lỗi** (lỗi nghiệp vụ là kết quả thành công của Lambda, dạng `{status: "ERROR", code, message}`): `JAR_NOT_FOUND`, `PROFILE_INCOMPLETE`, `FORECAST_UNAVAILABLE` (kể cả hũ hệ thống), `PARAMS_INVALID`, `UNAUTHENTICATED` (thiếu `user_id`).
- **An toàn**: `user_id` luôn do interceptor ghi đè từ JWT (client gửi `user_id` của người khác vẫn nhận dự báo của chính mình; có test). IAM của Lambda: Data API trên cluster, `secretsmanager:GetSecretValue` CHỈ trên secret của role `yofina_app` (không master), `events:PutEvents` trên `yofina-bus` (phát `forecast.updated` khi tính lại).

## `forecast___run_scenario` và `forecast___list_scenarios` (gộp kịch bản trong một cuộc chat)

- `run_scenario {scenario, conversation_id?, with_scenarios?}`: `with_scenarios` là các kịch bản người dùng VẪN GIỮ (tối đa 4; chỉ `one_time_purchase`, `recurring_expense`, `bnpl_purchase`; cả bó tối đa một `bnpl_purchase`), áp trước `scenario`. Kết quả thêm `bundle` và `bundle_total_vnd`; dòng `scenarios` lưu `conversation_id` và `bundle` (migration 0051). Chi tiết luật và mã lỗi: [contracts/README.md](../../../contracts/README.md) (mục "Gộp kịch bản trong một cuộc chat"); mã: `pipelines/forecast/yofina_forecast/scenario.py` (`apply_bundle`).
- `list_scenarios {conversation_id, limit?}`: các kịch bản đã chạy trong cuộc chat (mới nhất trước, `limit` 1 đến 10, mặc định 5), hàm DB `app_list_conversation_scenarios` (RLS: chỉ của chính người dùng). Chỉ đọc. Cedar [`list_scenarios.cedar`](../../policies/list_scenarios.cedar).

## Cedar

[`gateway/policies/get_forecast.cedar`](../../policies/get_forecast.cedar): `action == AgentCore::Action::"forecast___get_forecast"`, điều kiện `context.input has user_id && context.input.user_id == principal.id`; engine vẫn `ENFORCE`. Stack `YofinaAgent` đọc mọi file của `contracts/tools/forecast.json` như với `ledger.json` (thiếu file là synth lỗi).

## Số đo

Xem mục "Số đo" của [pipelines/forecast/README.md](../../../pipelines/forecast/README.md#số-đo-lambda-arm64-aurora-thật): khởi động nguội, thời gian tính một người dùng bảy hũ, memory size đã chọn.
