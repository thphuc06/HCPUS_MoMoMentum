# Kiểm toán phase 3 (what-if, kiểm tra trước khi chi): đối chiếu spec với code hiện tại

Ngày 2026-11-25. Người làm: sub-agent kiểm toán (Kiro), chỉ đọc. Cách làm: nhánh Spec của skill `code-review` (thiếu hoặc làm dở, làm ngoài yêu cầu, làm rồi nhưng sai), so code ở `main` hiện tại với [phase-3-what-if-va-kiem-tra.md](../plan/phases/phase-3-what-if-va-kiem-tra.md). Không có diff, không chạy test, không gọi AWS.

## Câu hỏi

Sau khi phase 3 đóng (23/11) và phase 4, 5 chồng thêm code, tiêu chí và các việc để sau của phase 3 đã được làm chưa? Những chỗ nào vẫn hở mà phase 6 chưa theo dõi?

## Kết luận ngắn

Phần lõi của phase 3 khớp spec. Các lỗi tìm thấy khi đi cảnh 2 ngày 23/11 đã được sửa trong code, và bản sửa suitability phía Lambda cũng đã có. Vẫn còn bốn việc để sau không ai nhận: F9 (golden không chấm `kind`, nên tiêu chí 10 chưa có bằng chứng), F7 (ngưỡng cạn của kiểm tra trước khi chi lấy mặc định của mã), số đo của đường kiểm tra trước khi chi qua chat, và F4 (phương án mất hành động mà không báo). Không thấy đường nào vượt được luật suitability. [đã đọc tài liệu]

## Phát hiện

### P3-01. Golden không chấm `kind` của kịch bản, nên tiêu chí 10 được ghi "Đạt" mà chưa có bằng chứng (F9 chưa làm)

- Spec: "10. Sáu loại kịch bản FR5 đều có ít nhất một câu golden đạt." và mục để sau "**F9.** Golden không khẳng định `kind` của `run_scenario` (`evals/run.py:188`), nên "mỗi loại đạt" chưa chứng minh được."
- Code: `evals/run.py:117` chỉ thêm `"kind"` vào `CASE_KEYS`, tức là runner chấp nhận khóa này. Tìm mọi chỗ dùng `kind` trong `evals/run.py` thì không có bộ chấm nào so `kind` của ca với `scenario.kind` mà agent gửi cho `run_scenario`. Các dòng 485–1650 là của bộ nhớ, lộ trình và nhận xét hành vi. Cả file cũng không nhắc tới `run_scenario`. [đã chạy thử: `Select-String evals/run.py`]
- `evals/golden/phase3.jsonl` có 10/31 ca mang `kind` (ví dụ dòng 30 `"kind": "bnpl_purchase"`). Hiện các khóa này chỉ để ghi chú. [đã chạy thử]
- Ảnh hưởng: [ba/13](../ba/13-tien-do-technical.md) dòng FR5 ghi "đủ 6 loại kịch bản" và con số này sẽ lên slide. Một ca `whatif-income` qua trọn vẫn đạt nếu router dựng nhầm `one_time_purchase`. [suy luận]
- Phase 6 chưa theo dõi việc này: mục 0, 3, 4E và 7 không có. [đã đọc tài liệu]

### P3-02. Kiểm tra trước khi chi lấy ngưỡng cạn từ mặc định của mã, không từ cấu hình (F7 chưa làm)

- Spec: "Ngưỡng đủ/sát/hụt để trong cấu hình." và "**F7.** `afford.py:308` lấy `runout_balance_threshold_vnd` từ mặc định của mã (0), không từ cấu hình".
- Code: dòng lỗi nay nằm ở `pipelines/forecast/yofina_forecast/afford.py:336`: `runout_thr = MLParams().runout_balance_threshold_vnd`. Hai ngưỡng bên cạnh thì đọc từ cấu hình (`self.s.affordability_short_p50_floor_vnd` và `self.s.affordability_tight_p10_floor_vnd` ở dòng 334–335). Ở đường dự báo, giá trị này đọc từ cấu hình theo người dùng: `stress.py:153` dùng `MLParams.from_extra(built.inputs.config.extra)` và `ml/yofina_ml/forecast.py:179` dùng `ctx.prm`. [đã chạy thử: `git grep runout_balance_threshold_vnd`]
- Ảnh hưởng: con số "cạn sớm N ngày" trên `affordability_card` có thể khác ngày cạn trên `forecast_timeline` của cùng hũ khi cấu hình khác 0. Việc này dính trực tiếp với T-02 (định nghĩa dải "sát" theo BR-36 là "cạn sớm hơn N ngày"). [suy luận]
- Phase 6 chưa theo dõi việc này. T-02 chỉ nói về hai ngưỡng sàn.

### P3-03. Đường kiểm tra trước khi chi qua chat không có p95 và không có thời điểm hiện thẻ

- Spec: "**F3 trong chat**: hàm tuần tự: `affordability_check` → phát `affordability_card` ngay → model nhỏ viết hai câu trong thời hạn 2 giây". Tiêu chí 9 chỉ yêu cầu đo p95 của `POST /affordability`.
- Đã đo: REST p50 191 / p95 282 ms. Qua chat thì chỉ có "kiểm tra qua chat tổng p50 6,3 s" (bảng đóng phase, tiêu chí 9). Không có p95, và thời điểm khối `affordability_card` cũng không được ghi lại, dù `scripts/measure_phase3.py:15` có đo ("thời điểm khối `affordability_card` và tổng"). [đã đọc tài liệu]
- Thời hạn 2 giây cho phần lời đã cài: `agent/src/yofina_agent/defaults.json:40` `"affordability_text_timeout_seconds": 2.0`. [đã chạy thử]
- Phase 6 luồng D (D1, D2) chỉ phân rã what-if và lộ trình, không có đường này. Giám khảo dễ hỏi "chuyển 250 nghìn có ổn không" ngay trong chat, chứ không chỉ ở màn chuyển tiền. [đã đọc tài liệu]

### P3-04. Phương án mất hành động mà không báo; khối `confirm` ẩn sẵn mất trạng thái khi tải lại (F4 chưa làm)

- Spec: "**F4.** ... `_prepare_action` lỗi thì phương án mất `action` im lặng và UI ghi "Chỉ để cân nhắc"."
- Code: `agent/src/yofina_agent/whatif.py:1152-1153`: "Lỗi thì bỏ hành động (phương án vẫn để cân nhắc)". `frontend/src/blocks/phase3Views.tsx:110` hiện "Chỉ để cân nhắc, không thay đổi số dư." khi không có xác nhận. Không có `notice` nào báo rằng hành động không chuẩn bị được. [đã chạy thử: `git grep`]
- Ảnh hưởng: ở cảnh 2, nếu `move_between_jars` (gọi không token) lỗi thì nút "Chọn" biến mất mà người xem không biết vì sao. Xác suất thấp. [suy luận]
- Phase 6 chưa theo dõi việc này.

### P3-05. Spec cho Verifier "tối đa 2 vòng" nhưng trần lượt model chỉ cho 1 vòng sửa (F6)

- Spec L4: "Sai thì trả lỗi có cấu trúc cho Analyst sửa, tối đa 2 vòng". Tiêu chí 9: "lượt gọi model mỗi lượt what-if không quá 4".
- Code: `agent/src/yofina_agent/defaults.json:4` `"max_model_calls_per_turn": 4`, `:38` `"verifier_max_rounds": 2`. `whatif.py:17-18` ghi rõ "mặc định trần 4, nên tối đa 1 lần sửa". Đây là mâu thuẫn bên trong spec, và code chọn tiêu chí 9. [đã chạy thử]
- Đã theo dõi: `docs/requirements/open-questions.md:99`.

### P3-06. "Phạt nếu trễ" của Trả sau không bao giờ hiện vì biểu phí không có dòng phạt

- Spec luồng A: "Nguồn là tín dụng: tổng chi phí thật (gốc + phí + phạt nếu trễ)".
- Hợp đồng đúng nguyên tắc không bịa số: `contracts/blocks/obligation_impact.schema.json:91-92` có `late_penalty_vnd` "CHỈ khi biểu phí có nguồn cho khoản này". Engine có truyền `late_fee` (`afford.py:588`, `scenario.py:137, 305, 920`). Nhưng seed `db/seed/fee_schedules.sql:13` chỉ có `monthly_service_fee` 33.000 cho `bnpl_sim`, không có dòng phạt trễ, nên trường này luôn vắng trên demo. [đã chạy thử]
- Đã theo dõi một phần: T-07 (BR-74 đến 76, chi phí trả sau minh bạch) ở ba/13 §4.

### Đã kiểm, không còn là lỗ hổng

- Bản sửa suitability phía Lambda (mục "Kiểm sau" thứ ba) đã có: `gateway/tools/ledger/yofina_ledger/phase3.py:44` có `adds_scenario_obligation`, và dòng 127–128 chỉ cộng `item_cost_vnd` khi phương án thật sự thêm nghĩa vụ. [đã đọc tài liệu]
- Thẻ "Sau: Đủ, khả năng hụt 0%" đi cùng số dư thấp nhất âm (lỗi khi đi cảnh 2) đã sửa: `pipelines/forecast/yofina_forecast/scenario.py:636-646`. `_status` trả `short` khi hũ cạn trước hoặc đúng ngày lương, và `_p` bỏ xác suất trong trường hợp đó (`minh` có `payday_day` 5, hạn Trả sau 05/12). [đã đọc tài liệu]
- Router làm mất `amount_vnd` sau khi hỏi hũ, và chip gửi "250000": commit `af21e04` sửa, có golden `multiturn-clarify-jar-keeps-amount` (`evals/golden/phase3.jsonl:31`). [đã chạy thử: `git log`]
- Phương án "Dùng hũ Dự phòng" ghi "Đủ" sai: commit `19d79d3` và `e71a055`, cộng thêm luật `emergency_not_for_discretionary` (`5b675c7`). [đã chạy thử: `git log`]
- Luật suitability trên đường kiểm tra trước khi chi: hũ thay thế chỉ lấy từ hũ `spending` (`afford.py:298`), nên hũ Dự phòng không được gợi ý. Phương án đổi hũ và Trả sau chỉ được thêm khi `evaluate` trả ok, với `origin="recommendation"` (`afford.py:700-708`, `731-749`). [đã đọc tài liệu]
- Làm nóng phiên: `agent/src/yofina_agent/app.py:7` (`forwardedProps.warmup`), có test ở frontend `app.test.tsx:143`. [đã chạy thử: `git grep`]

## Điều chưa chắc

- Phương án "Hoãn tới kỳ lương" vẫn ghi "Hụt" (đi cảnh 2, mục 4): trạng thái tính bằng `jar_check(amount_vnd=amount, pay_date=payday, ...)` ở `afford.py:786`. Tôi chưa tìm thấy commit nào nhắc tới lỗi này và chưa chạy được để biết nó còn không. Khả năng là đúng toán (hũ Hóa đơn đã âm trước kỳ lương vì hóa đơn 26/11) nhưng nhãn làm người đọc khó hiểu. [suy luận]
- Luật `emergency_not_for_discretionary` ở mức `warn` ghi "hệ thống không gợi ý nó là phương án tốt nhất". Chưa kiểm trong `whatif.py` xem phương án dính `warn` này có bị gỡ `recommended` bằng mã không. Lần kiểm 24/11 trên Runtime nói là không còn được khuyên (ba/13 T-01). [đã đọc tài liệu]
- Bộ nhớ ngắn hạn theo phiên bằng AgentCore Memory (spec luồng B) không làm ở phase 3 (lệch đã ghi). Chưa kiểm phase 5 có thay thế đủ không.
- Các mảng do sub-agent khác phụ trách nên không xét ở đây: bộ chấm `NumericGrounding` của eval (kể cả F8), lập luận của luồng K, độ trễ Analyst và khoảng chờ trước tool của Orchestrator, quota Bedrock, dải vàng F3 (T-02), nợ Trả sau mất trên tài khoản không có hũ Nghĩa vụ.

## Nguồn đã tra

- `docs/plan/phases/phase-3-what-if-va-kiem-tra.md` (tiêu chí, bảng đóng phase, kiểm sau, F4 đến F10, quyết định hợp đồng 1 đến 18).
- `docs/plan/phases/phase-6-danh-gia-dong-goi.md` mục 0, 3, 4D, 4E, 7; `docs/ba/13-tien-do-technical.md` §2, §4, §4a; `docs/requirements/open-questions.md:99`.
- Code: `agent/src/yofina_agent/{whatif.py,defaults.json,app.py}`, `gateway/tools/ledger/yofina_ledger/phase3.py`, `gateway/tools/planner/rules/emergency_not_for_discretionary.yaml`, `pipelines/forecast/yofina_forecast/{afford.py,scenario.py}`, `frontend/src/features/forecast/ForecastBlock.tsx`, `frontend/src/blocks/phase3Views.tsx`, `contracts/blocks/obligation_impact.schema.json`, `db/seed/fee_schedules.sql`, `evals/run.py`, `evals/golden/phase3.jsonl`, `scripts/measure_phase3.py`.
- `git log --since=2026-11-23` (207 commit), lọc theo từ khóa what-if, afford, clarify, chip.
