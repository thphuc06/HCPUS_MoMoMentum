# gateway/tools/forecast/

Tool `forecast___*` (target `forecast`): `get_forecast`, `run_scenario` (Monte Carlo), `stress_test`, `affordability_check` (engine tất định), `get_resilience_score`, `get_behavior_profile`. Đều không ghi dữ liệu. Proposal §9, §10.1, §10.2, §10.4; FR3, FR5, FR6, FR7.

Monte Carlo numpy có tương quan (5.000 đường khoảng 76 ms); truy vấn kiểm tra trước khi quẹt qua Data API p95 khoảng 113 ms; StatsForecast cần Lambda container: [spike-ml-forecasting.md](../../../docs/research/spike-ml-forecasting.md), [spike-aurora-data-api.md](../../../docs/research/spike-aurora-data-api.md).
