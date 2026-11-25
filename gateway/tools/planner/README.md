# gateway/tools/planner/

Tool `planner___*` (target `planner`): `optimize_allocation` (quy hoạch tuyến tính bằng `scipy.optimize.linprog`, không dùng PuLP), `check_suitability` (rule engine), `save_roadmap` / `get_roadmap`, `schedule_nudge` (ghi một dòng bảng `nudges`, đi qua cùng luồng token xác nhận; không dùng EventBridge Scheduler như proposal ghi, xem `yofina_core.wallet`). Proposal §9, §10.5; FR8, FR12.

LP: sàn cứng qua biến elastic với mức phạt theo ưu tiên, khoảng 1 ms ([spike-ml-forecasting.md](../../../docs/research/spike-ml-forecasting.md) mục 8).
