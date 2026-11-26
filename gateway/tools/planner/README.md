# gateway/tools/planner/

Tool `planner___*` (target `planner`): `optimize_allocation` (quy hoạch tuyến tính bằng `scipy.optimize.linprog`, không dùng PuLP), `check_suitability` (rule engine), `save_roadmap` / `get_roadmap`, `schedule_nudge` (ghi một dòng bảng `nudges`, đi qua cùng luồng token xác nhận; không dùng EventBridge Scheduler như proposal ghi, xem `yofina_core.wallet`). Proposal §9, §10.5; FR8, FR12.

LP: sàn cứng qua biến elastic với mức phạt theo ưu tiên, khoảng 1 ms ([spike-ml-forecasting.md](../../../docs/research/spike-ml-forecasting.md) mục 8). Sàn tính từ mức nền bền của người dùng (`yofina_core.spend_baseline`, xem `pipelines/forecast/README.md`).

Luật `obligations_first` (`yofina_planner.engine._essential_covered`): nghĩa vụ thiết yếu đến hạn từ ngày mai tới hết ngày lương kế (cửa sổ chung `yofina_core.schedule.due_before_payday`, gồm khoản đúng ngày lương, trả bằng số dư trước khi lương về; BR-22) phải còn được phủ sau khi trừ khoản đề xuất.
