# Kiểm toán phase 4 so với spec (25/11/2026)

Người làm: sub-agent kiểm toán (Kiro), chỉ đọc, theo brief "Spec" của skill `code-review` (đối chiếu code HIỆN TẠI với spec, không dùng diff). Không chạy test, eval, không gọi AWS.

## Câu hỏi

Code hiện tại có làm đúng [phase-4-chong-chiu-lo-trinh.md](../plan/phases/phase-4-chong-chiu-lo-trinh.md) (9 tiêu chí, bảng đóng phase, các mục "để sau") không; lệch nào chưa được ghi ở [phase 6](../plan/phases/phase-6-danh-gia-dong-goi.md) mục 0, 3, 7, [ba/13](../ba/13-tien-do-technical.md) hoặc [HANDOFF](../../HANDOFF.md)?

## Kết luận ngắn

Phase 4 đạt phần lớn spec: LP có nới một vòng và đúng hai lựa chọn, điểm chống chịu có bốn thành phần với câu giải thích dựng bằng code, cú sốc tính cả nghĩa vụ Trả sau, đường "nghi" (CUSUM) và "xác nhận" (PELT) đều có. Ba lệch đã biết (mã thô ở So với bản cũ, `period_end`, tỷ lệ hỏi 17,4%) đều có thật và đã vào phase 6 (E1, E5, E7). Có ba lệch spec chưa ai ghi: "Giữ bản cũ" không hỏi lý do; không có đường "dự báo đổi nhẹ thì cập nhật số trong lộ trình cũ"; con số lý do của lộ trình seed `minh` không lấy từ sổ cái. [đã đọc tài liệu]

## Phát hiện

### P4-01. Màn So với bản cũ (L3) hiện mã thô ở "Loại bước" và "Giai đoạn" (bug, đã theo dõi E1)

- Spec: "so với bản cũ, "Dùng bản mới" / "Giữ bản cũ"" (phase 4, dòng 70); phase 4 dòng 143: "màn So với bản cũ (L3) ghi "Loại bước" và "Giai đoạn" bằng mã thô (sửa ở `roadmap_logic.py`)".
- Code: `gateway/tools/ledger/yofina_ledger/roadmap_logic.py:595-596` gọi `add("Loại bước", ostep["kind"], step["kind"])` và `add("Giai đoạn", old_phase, phase)`, tức chuỗi thô kiểu `set_aside`, `cut_spending`, `on_dinh_thang_nay`, `xay_quy_du_phong` (mã có trong `data/personas/roadmaps/minh.json`). Frontend `frontend/src/features/roadmap/RoadmapDiff.tsx:31-32` in nguyên `field.label` và `before → after`. [đã đọc tài liệu]
- Cỡ: chỉ sửa backend. Cần một bảng nhãn cho `kind` (sáu giá trị) và lấy `title` của giai đoạn thay cho `phase_id` (giai đoạn đã có `title` trong `plan`). Khoảng 1–1,5 giờ, đúng ước của E1. Hiện trên cảnh 4. [suy luận]

### P4-02. Kỳ lộ trình bắt đầu từ hôm nay, không theo ngày lương (bug, đã theo dõi E5)

- Spec: phase 4 dòng 144: "`period_end` của lộ trình tính theo ngày hôm nay, chưa theo ngày lương (agent chưa có ngày lương từ tool)".
- Code: `pipelines/forecast/yofina_forecast/allocation.py:371` đặt `period_start=today.isoformat()`. Agent dựng `period_end = payday_in_month(period_start.day, …)` (`agent/src/yofina_agent/roadmap_agent.py:477`) và `_add_month` (dòng 851-853), tức dùng ngày-trong-tháng của HÔM NAY làm "ngày lương". `minh` có `payday_day` 5 (`data/personas/specs/minh.json:6`), ngày mô phỏng 21/11, nên kỳ ra 21/11 → 21/xx thay vì theo mốc ngày 05. [đã đọc tài liệu]
- Ghi chú về chỗ sửa: E5 ghi "agent lộ trình, tool hồ sơ", nhưng Lambda forecast đã đọc hồ sơ (`allocation.py:176` lấy `monthly_salary_vnd` từ `ctx.meta["profile"]`) và `yofina_core.clock.next_payday` có sẵn (`clock.py:66`). Có thể sửa gọn ngay ở `allocation.py:371` mà không cần tool mới. Việc này đổi nghĩa `period_start` trong kết quả `optimize_allocation`, nên phải sửa test hợp đồng đi kèm. [suy luận: chưa kiểm hồ sơ trong `ctx.meta` có `payday_day`]

### P4-03. Tỷ lệ phải hỏi khi phân loại 17,4%, và thêm 43% vào "Xem lại" (gap so với NFR, đã theo dõi E7, T-03)

- Spec: "6. Phân loại trên bộ kiểm thử: đúng từ 90%, dưới 10% giao dịch phải hỏi" (phase 4, dòng 85).
- Số trong `evals/classification/results/classification-live-2026-11-23.json` (đọc bằng PowerShell) [đã chạy thử]:
  - Tập kiểm (n=167): `ask_rate` 0,1737 (khoảng 29 giao dịch), `review_rate` 0,4311, `accuracy_assigned` 0,9203, `correct_end_to_end` 0,7605, `silent_error_rate` 0,018. Cờ `test_meets_ask_rate` false.
  - Toàn bộ 334 dòng: `ask_rate` 0,1976.
  - Theo nhóm trên tập kiểm: `unseen_qr` n=54, hỏi 22,2% (khoảng 12 ca); `note_only` n=28, hỏi 28,6% (khoảng 8); `person_no_note` n=17, hỏi 29,4%, đúng 66,7% trên phần đã gán; `known_qr` hỏi 3,4%; `mapped_type` 0%.
- Nhận xét: con số giám khảo nên thấy là khoảng 60% giao dịch cần người dùng chạm vào (hỏi cộng xem lại), và 76% đúng tính trên toàn bộ. Con số 92% chỉ tính trên phần tự gán. Hai hướng giảm ghi ở E7 nhắm đúng `unseen_qr` (token mẫu QR) và `note_only` (trọng số lịch sử). Ngưỡng hiện tại `auto_min_confidence` 0,91, `review_min_confidence` 0,65, `small_one_off_max_vnd` 50.000. [suy luận]

### P4-04. "Giữ bản cũ" (từ chối cả bản mới) không hỏi lý do (gap, chưa theo dõi)

- Spec: "Từ chối toàn bộ: hỏi một câu lý do, ghi lại." (phase 4, dòng 61).
- Code: `contracts/rest/openapi.yaml:3798` `RoadmapVersionDecisionRequest` chỉ có `decision` (`adopt`, `keep_previous`), `additionalProperties: false`. Frontend `frontend/src/api/roadmapSchemas.ts:76-78` là `z.strictObject({decision})`. Nút "Giữ bản cũ" gọi thẳng `decide('keep_previous')` (`frontend/src/pages/RoadmapComparePage.tsx:57`). Từ chối TỪNG bước thì có ô lý do (`RoadmapStepDialogs.tsx:26-45`). [đã đọc tài liệu]
- Cỡ: đổi hợp đồng REST, sinh lại Zod, sửa ledger và màn L3, khoảng nửa ngày. Phase 6 "không thêm tính năng", và giám khảo khó thấy chỗ thiếu này. Đề xuất ghi là lệch, không sửa. [suy luận]

### P4-05. Không có đường "dự báo đổi nhẹ thì cập nhật số trong lộ trình cũ"; số trong lộ trình đứng yên từ lúc lưu (gap, chưa theo dõi)

- Spec: "Dự báo đổi nhẹ chưa tới ngưỡng: cập nhật số trong lộ trình cũ, giữ cấu trúc." (phase 4, dòng 61).
- Code: mã lý do `forecast_drift` chỉ được khai báo (`libs/yofina_core/src/yofina_core/roadmap.py:58`, `wallet.py:275,308`, `roadmap_logic.py:131`, nhãn ở `agent/src/yofina_agent/notices.py:184`). Không chỗ nào sinh ra nó. Lambda sinh lại chỉ nghe `roadmap.regeneration_requested`, `behavior.changed` và `profile.updated` (`pipelines/roadmap/yofina_roadmap/events.py:13-15`, `infra-cdk/lib/roadmap-regen.ts:161-173`), không nghe `forecast.updated`. Khi đọc, `basis` là ảnh chụp lúc lưu (`roadmap_logic.py:415` `"basis": plan["basis"]`), và trong `frontend/src/features/roadmap/` không có chỗ nào hiện `basis` hay thời điểm tính. [đã đọc tài liệu]
- Ảnh hưởng: nếu giám khảo chuyển tiền rồi mở lộ trình thì "số trước/sau" của bước có thể lệch với số dư hũ, và màn không ghi số tính lúc nào. Tiền vẫn an toàn vì hành động của bước được server tính lại bản xem trước lúc bấm (quyết định 15 của phase 4). [suy luận]
- Cỡ: làm đúng spec thì cần một tính năng mới (M–L). Cách nhỏ hơn (S) là hiện "Số tính ngày …" từ `basis.computed_at`, vì trường này đã có trong khối. [suy luận]

### P4-06. Con số trong lý do của lộ trình seed `minh` không lấy từ sổ cái (gap, liên quan mục do sub-agent khác lo)

- Phần "lộ trình seed đổi hành vi trên tài khoản demo" do sub-agent khác lo. Ở đây chỉ ghi chuyện con số.
- `data/personas/roadmaps/minh.json:3` ghi rõ: "các con số mức chi hằng tuần (520.000 và 810.000 đồng mỗi tuần của Ăn uống …) là dữ liệu seed theo bảng số Figma L1, KHÔNG tính từ sổ cái"; `old_weekly_vnd` 520000, `new_weekly_vnd` 810000 ở dòng 15-16. Khi chạy tiêu chí 3, script đo mức cũ của hũ `an_uong` của `minh` từ sổ cái là 435.000 ₫ mỗi tuần (phase 4, dòng 157: "Hai tuần cuối của hũ đã đạt 2.0 lần mức cũ (435,000 VND mỗi tuần)"). [đã đọc tài liệu]
- Ảnh hưởng: lý do "Chi Ăn uống mỗi tuần tăng từ 520.000 ₫ lên 810.000 ₫" có thể lệch với số chi Ăn uống mà giám khảo thấy ở màn Thói quen hoặc màn dự báo. Bộ đọc đo theo cửa sổ khác có thể cho số khác, nên mức lệch thật cần kiểm trên app. [suy luận]
- Cỡ: S–M. Hoặc lúc nạp seed thì tính old/new từ chuỗi tuần của sổ cái (`yofina_forecast.change.spending_series`), hoặc chỉnh dữ liệu giao dịch của `minh` cho khớp 520.000/810.000.

### P4-07. Lambda sinh lại bỏ bản đề xuất đang chờ mà không ghi lý do (bug nhỏ, đã theo dõi E2)

- `pipelines/roadmap/` không có chỗ nào ghi "thay bản đề xuất trước" (git grep `discard|thay bản` không có kết quả). Đường chat đã nói việc này (`agent/src/yofina_agent/turn.py:1180`, `notices.py:189`). [đã đọc tài liệu]

### P4-08. Lambda sinh lại gần như không log khi chạy thành công (improvement, chưa theo dõi ở phase 6)

- Phase 4 dòng 196: "`yofina-roadmap-regen` không ghi dòng log ứng dụng nào (chỉ có START, END, REPORT)". Code chỉ có `log.warning` (`pipelines/roadmap/handler.py:34`, `yofina_roadmap/runner.py:139,148`). Ảnh hưởng tới vận hành buổi demo (luồng J): khi lộ trình không hiện thì khó tìm nguyên nhân. S. [đã đọc tài liệu]

### Mục đã kiểm, không có lệch

- LP (tiêu chí 4, 8): `ml/yofina_ml/allocation.py:345-388` có `optimal`, `relaxed` (nới một vòng) và `infeasible`. Khi HiGHS lỗi thì ném `RuntimeError` (dòng 249-250). Lỗi này được `pipelines/forecast/yofina_forecast/tool.py:195` bắt, và ledger đổi thành `FORECAST_UNAVAILABLE` (`forecast_client.py:97-106`). Test phủ ca vô nghiệm, ca nới và ca ưu tiên (`tests/unit/pipeline/test_allocation.py:94,112,123,132,145,308,323`). Frontend hiện `alternatives` khi `infeasible` (`Roadmap.tsx:78-82`). [đã đọc tài liệu]
- Điểm chống chịu giải thích được: mẫu câu nằm trong cấu hình (`resilience_defaults.json:48,66,90,108`), code điền vào; dòng "không phải điểm tín dụng" hiện ở `ResilienceScore.tsx:20`. Cửa sổ 30 ngày khớp nhãn "hằng tháng" (`settings.py:83`). [đã đọc tài liệu]
- Cú sốc và nợ Trả sau: nghĩa vụ `bnpl` nằm ở bảng `obligations` (`db/migrations/0005_wallet.sql:39,65`). Điểm và cú sốc đều đọc các nghĩa vụ đang hoạt động (`pipelines/forecast/yofina_forecast/resilience.py:198,236`; `stress.py:121-129`), nên Borrow và cú sốc có tính Trả sau. [đã đọc tài liệu]
- Ngưỡng phát hiện đổi hành vi: lấy từ tham số (`min_abs_change_vnd`, `min_weeks_total`, `dedupe_days` ở `ml/yofina_ml/change.py:45-64`); `detail` ghi tỷ lệ báo nhầm (`pipelines/forecast/yofina_forecast/change.py:450`). Độ nhạy (cần khoảng 3 lần mức cũ) và docstring `--factor` mặc định 2 (`scripts/inject_behavior_shift.py:19`) thuộc phần PELT/CUSUM recall do sub-agent khác lo. [đã đọc tài liệu]
- Golden phase 4 có 14 dòng, đối kháng phase 4 có 12 dòng (spec đòi từ 12 và từ 10). Ca sửa một bước đã có nhánh riêng (`turn.py:1116-1117`). Cổng nhắc có "Ít nhắc loại này" (`frontend/src/features/overview/useProactiveActions.ts:15,69`). Số chưa phân loại hiện ở Tổng quan và màn Nhìn trước (`TodoList.tsx:56`, `ForesightPage.tsx:35`). [đã chạy thử, đã đọc tài liệu]
- Mục do sub-agent khác lo, chỉ nêu tên: lộ trình seed đổi hành vi trên tài khoản demo (giám khảo không tự kích được sinh lại), lập luận luồng K lệch trên lộ trình, thiếu hũ "Khác", recall PELT/CUSUM, độ trễ Analyst, bộ chấm eval.

## Điều chưa chắc

- P4-02: chưa kiểm `ctx.meta["profile"]` của Lambda forecast có `payday_day` (chỉ thấy `monthly_salary_vnd`). Nếu không có thì phải thêm vào hàm đọc ngữ cảnh.
- P4-05, P4-06: chưa mở app để xem số lộ trình và số chi Ăn uống của `minh` lệch nhau bao nhiêu sau khi đặt lại; 435.000 ₫ là số script in ra ngày 24/11.
- Chưa kiểm cú sốc "mất việc" có tính phí trễ hạn Trả sau không; chỉ kiểm khoản đến hạn vẫn nằm trong dự báo.
- `MAX_DIFF_CHANGES` 30 (`roadmap_logic.py:52`): `counts` đếm sau khi cắt danh sách (dòng 619-620). Với lộ trình nhỏ thì không ảnh hưởng.
- Không chạy unit test hay eval (`uv` không có trên máy).

## Nguồn đã tra

- `docs/plan/phases/phase-4-chong-chiu-lo-trinh.md` (toàn bộ), `docs/plan/phases/phase-6-danh-gia-dong-goi.md` mục 0, luồng E, mục 7, `docs/ba/13-tien-do-technical.md`, `HANDOFF.md` (git grep).
- Code: `gateway/tools/ledger/yofina_ledger/{roadmap_logic,roadmap_service,roadmap_seed,forecast_client,proactive}.py`, `pipelines/forecast/yofina_forecast/{allocation,resilience,stress,change,tool,settings}.py`, `ml/yofina_ml/{allocation,resilience,stress,change}.py`, `agent/src/yofina_agent/{roadmap_agent,turn,notices}.py`, `pipelines/roadmap/`, `infra-cdk/lib/roadmap-regen.ts`, `contracts/rest/openapi.yaml`, `frontend/src/{api/roadmapSchemas.ts,features/roadmap,features/resilience,pages}`, `data/personas/{roadmaps/minh.json,specs/minh.json}`, `libs/yofina_core/src/yofina_core/{shocks,resilience_defaults}.json`, `evals/{golden,adversarial}/phase4.jsonl`, `evals/classification/results/classification-live-2026-11-23.json`.
