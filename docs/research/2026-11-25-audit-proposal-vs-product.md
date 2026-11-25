# Kiểm toán: proposal so với sản phẩm đang có (25/11/2026)

Viết ngày 2026-11-25 bởi một sub-agent kiểm toán (Kiro, Claude Opus 5.5), chỉ đọc, theo brief "Spec" của skill `code-review` (đối chiếu mã hiện có trên đĩa với spec, không phải một diff). Mã đọc ở `main` 865fba9 (Runtime v27, Amplify job 21 theo [HANDOFF](../../HANDOFF.md)).

Nhãn mỗi khẳng định:

- **[đã chạy thử]**: đã chạy lệnh trên repo (`git grep`, đọc file mã, đọc JSON bằng Python) và thấy kết quả. Không gọi AWS, không chạy eval, không deploy.
- **[đã đọc tài liệu]**: chỉ đọc tài liệu trong repo (phase, BA, HANDOFF, research).
- **[suy luận]**: rút ra từ hai loại trên, chưa kiểm trực tiếp.

Spec theo thứ tự ưu tiên: [proposal-summary.md](../proposal/proposal-summary.md), [requirements.md](../requirements/requirements.md), [overview.md](../architecture/overview.md), [ba/03](../ba/03-functional-requirements.md), [ba/04](../ba/04-non-functional-requirements.md), [ba/05](../ba/05-acceptance-criteria.md), [open-questions.md](../requirements/open-questions.md), [ADR](../decisions/README.md). Đối chiếu việc đã theo dõi với [phase 6](../plan/phases/phase-6-danh-gia-dong-goi.md) và [ba/13](../ba/13-tien-do-technical.md) (T-01 đến T-07). Mức ảnh hưởng tới giám khảo theo giả định BA: [ba/08 mục 5](../ba/08-kpi-kinh-doanh.md#5-ma-trận-kpi-theo-bên-hưởng-lợi) (K2, K5, NFR độ trễ, độ đúng của số, an toàn) và [ba/10 mục 7](../ba/10-tac-dong-stakeholder.md#7-tác-động-theo-mốc-thời-gian) (M0: dự báo đúng và sớm, token chặn 13 ca, trace 100%, chi phí mỗi lượt).

## Câu hỏi

1. Mỗi tính năng F1–F7 và FR1–FR15 đã làm, làm một phần hay chưa làm? Cột trạng thái ở requirements.md và ba/13 có khớp mã không?
2. Lời hứa nào trong proposal giám khảo có thể tự kiểm trên app mà sản phẩm hôm nay không giữ, hoặc chỉ giữ ở dạng yếu hơn?
3. Thành phần kiến trúc nào trong overview/proposal bị thiếu, chỉ là vỏ, hay khác trong `infra-cdk/` và `agent/`? Chỗ lệch có ADR không?
4. NFR nào trong ba/04 chưa đo, hoặc đo rồi mà trượt?
5. Câu hỏi mở nào còn chặn việc đóng gói (README cho giám khảo, Region, hạn nộp)?

## Kết luận ngắn

- Bảy tính năng đều có mã thật chạy trên AWS; không tính năng MVP nào là vỏ rỗng. Chỗ yếu nằm ở **độ trễ của cảnh 2**, ở **cách cảnh 4 chứng minh "tự đổi lộ trình khi hành vi lệch"** (trên tài khoản demo là dữ liệu seed), và ở **tài liệu cho người ngoài đọc** (README gốc, CLAUDE.md, requirements.md, overview.md còn ghi trạng thái 21/11). [đã chạy thử]
- Lệch kiến trúc so với proposal phần lớn đã được ghi lại (open-questions, file phase, HANDOFF), nhưng chỉ có 3 ADR, trong khi chính [decisions/README.md](../decisions/README.md) yêu cầu viết ADR khi "chọn dịch vụ thay thế điều proposal ghi; đổi hướng so với proposal". [đã đọc tài liệu]
- Ba số đo NFR được báo "Đạt" trên đường khác với đường giám khảo dùng (NFR-01 đo `RUN_STARTED` của bản lát dọc phase 1; NFR-02 đo REST, không đo qua chat). [đã chạy thử]
- Hạn nộp chính xác, trọng số chấm và tên sản phẩm vẫn chưa có câu trả lời; đây là ba câu chặn README, video và slide. [đã đọc tài liệu]

## Bảng F1–F7

| F | Proposal hứa | Mã hiện có | Đánh giá | Bằng chứng |
|---|---|---|---|---|
| F1 Dự báo theo hũ | Dòng thời gian 30 ngày, ngày cạn, xác suất hụt; batch đêm, cập nhật khi có giao dịch | Hurdle + khởi đầu lạnh (`ml/yofina_ml/forecast.py:4`, `:93`), Monte Carlo, Step Functions `yofina-nightly` lúc 02:00, consumer sự kiện | **Làm**. Yếu hơn: Chronos-2 ngoài MVP (đã chốt 21/11); hiệu chỉnh conformal mỗi tuần bị cắt theo Q11 (chưa chốt); K5 (báo trước bao nhiêu ngày) chưa đo | [đã chạy thử] `pipelines/forecast/yofina_forecast/batch.py`, `pipelines/nightly/README.md` |
| F2 What-if | Ít nhất 6 loại kịch bản; khối số liệu ở khoảng giây thứ 2, văn bản xong trước giây thứ 8 (§12) | Đủ 6 loại (`agent/src/yofina_agent/whatif.py:77-79`); khối số liệu phát trước văn bản | **Làm, độ trễ trượt xa**: khối đầu p50 6,9 s / p95 18,2 s; trọn câu p95 28,2 s; một mẫu 37,9 s sau luồng K | [đã chạy thử] mã; [đã đọc tài liệu] [phase 3 dòng 114](../plan/phases/phase-3-what-if-va-kiem-tra.md), HANDOFF |
| F3 Kiểm tra trước khi quẹt | Xanh / vàng (cạn sớm N ngày) / đỏ; tín dụng có tổng chi phí và khoản hụt tháng sau; dưới 2 s | Engine tất định `pipelines/forecast/yofina_forecast/afford.py` | **Một phần**: vàng gần như không bao giờ xảy ra vì hai ngưỡng bằng 0 (`settings.py:77`, `:79`); qua chat trọn lượt p50 6,3 s (REST 282 ms) | [đã chạy thử]; T-02 |
| F4 Điểm chống chịu | 0–100, 4 thành phần Save/Spend/Borrow/Plan, 3 cú sốc | `libs/yofina_core/src/yofina_core/resilience.py:136-147`; `shocks.json:8,19,31` ("Mất việc 2 tháng", "Tiền trọ tăng", "Ốm một tuần") | **Làm** | [đã chạy thử] |
| F5 Lộ trình thích ứng | Phiên bản mới khi hành vi đổi; LP; suitability phủ quyết; duyệt từng bước | Roadmap agent (`roadmap_agent.py`), LP `scipy linprog`, 7 luật suitability, PELT xác nhận → `behavior.changed` → Lambda `yofina-roadmap-regen` | **Làm, chứng minh trên demo yếu hơn**: trên `minh`/`giamkhao1`/`giamkhao2`, bản "sinh lại do hành vi" là seed (`data/personas/roadmaps/README.md:3,14`); dấu hiệu seed chặn bản sinh lại thật; đường thật chỉ đo trên `lan` bằng script | [đã chạy thử] `pipelines/forecast/yofina_forecast/change.py`, `pipelines/roadmap/README.md`; [đã đọc tài liệu] [phase 4 dòng 157](../plan/phases/phase-4-chong-chiu-lo-trinh.md) |
| F6 Nạp dữ liệu ngoài ví | Ảnh, CSV; điểm độ phủ tăng; PDF là mở rộng | `pipelines/ingest/`, `yofina_core.ingest.coverage_ratio` (`ingest.py:202`), khối `coverage_change` | **Làm (MVP một phần như kế hoạch)**; OCR ảnh thật 9/11 | [đã chạy thử]; T-05 |
| F7 Hồ sơ hành vi, bản tin | Nhận xét thói quen + một việc cần làm; bộ nhớ dài hạn; cổng giá trị | `behavior.compute_and_store` và `run_nudge_gate` trong batch đêm (`batch.py:101-121`); AgentCore Memory hai strategy override | **Làm**. Yếu hơn: "bài học của agent" từ `feedback` (ReasoningBank) chưa làm; bước lộ trình chưa đọc bộ nhớ (đã ghi "để sau cuộc thi") | [đã chạy thử]; HANDOFF mục C |

## Bảng FR1–FR15: trạng thái trong tài liệu so với mã

Cột "requirements.md" là [requirements.md dòng 11–25](../requirements/requirements.md); "ba/03" là bảng Tổng quan; "ba/13" là mục 2.

| FR | requirements.md | ba/03 | ba/13 | Mã (kiểm toán) | Lệch |
|---|---|---|---|---|---|
| FR1 | chưa làm | ✅ | ✅ | Làm (hũ hệ thống "Tiền vào khác", xác nhận lương, `YOFINA_SALARY_DEVIATION_ASK_PERCENT` ở `infra-cdk/lib/tools-stack.ts`) | requirements.md sai |
| FR2 | chưa làm | ◐ | ◐ | Một phần: đủ 4 bước (`pipelines/classify/README.md`); luật "khoản nhỏ một lần vào hũ Khác, không hỏi" không bao giờ chạy (PV-09) | requirements.md sai |
| FR3 | chưa làm | ✅ | ✅ | Làm | requirements.md sai |
| FR4 | chưa làm | ✅ | ✅ | Làm (`update_profile` có `obligation` upsert/delete) | requirements.md sai |
| FR5 | chưa làm | ✅ (golden 30/30) | ✅ (31/31) | Làm; NFR-03 trượt | requirements.md sai; ba/03 và ba/13 khác số ca |
| FR6 | chưa làm | ◐ | ◐ | Một phần (T-02) | requirements.md sai |
| FR7 | chưa làm | ✅ | ✅ | Làm | requirements.md sai |
| FR8 | chưa làm | ✅ | ✅ | Làm; sinh lại do hành vi chỉ chạy thật trên `lan` (AC-FR8-02 ghi đúng) | requirements.md sai |
| FR9 | chưa làm | ◐ | ◐ | Một phần (OCR) | requirements.md sai |
| FR10 | chưa làm | ◐ | ◐ | Một phần | requirements.md sai |
| FR11 | chưa làm | ✅ | ✅ | Làm | requirements.md sai |
| FR12 | chưa làm | ✅ | ✅ | Gần đủ: AC-FR12-03 "một phần", AC-FR12-04 "chờ kiểm (thiếu cho sửa hồ sơ, `save_jars`, nghĩa vụ)", AC-FR12-07 "chưa làm" ([ba/05 dòng 146](../ba/05-acceptance-criteria.md)) | requirements.md sai; ✅ ở ba/03, ba/13 lạc quan hơn ba/05, nên là ◐ |
| FR13 | — | ◐ | ◐ | Làm (cổng tối đa một dòng `nudges` mỗi ngày); chưa kiểm trên app | requirements.md chưa ghi |
| FR14 | — | ⏳ | ⏳ | Không có mã (`git grep` không ra) | Khớp |
| FR15 | — | ◐ | ◐ | Làm (`app_ops_summary` trong `0053_phase5.sql:403` đếm lượt, lỗi tool, luật `fail`, token; dashboard `ops-dashboard.ts`) | requirements.md chưa ghi |

Tất cả [đã chạy thử] trừ cột tài liệu [đã đọc tài liệu].

## Phát hiện

### (a) Yêu cầu thiếu hoặc chỉ làm một phần

**PV-01. "Tự đổi lộ trình khi hành vi lệch" trên tài khoản demo là dữ liệu seed.** Proposal §1: "tự đổi lộ trình khi hành vi người dùng lệch khỏi dự báo"; §15 cảnh 4: "Lộ trình sinh lại". Mã của đường thật có đủ (CUSUM ở đường sự kiện, PELT trong batch, `behavior.changed`, Lambda sinh lại) [đã chạy thử]. Nhưng trên `minh`, `giamkhao1`, `giamkhao2`, lộ trình v3 lý do `behavior_changed` và dấu hiệu `confirmed` là seed nạp nguyên từ `data/personas/roadmaps/minh.json` (README dòng 3, 14: "để batch đêm không dựng thêm dấu hiệu thứ hai... và không sinh lại lộ trình trước cảnh 4") [đã chạy thử]. Phase 4 ghi rõ không kiểm được trên `minh` và đã kiểm trên `lan` bằng `scripts/inject_behavior_shift.py` qua đường nạp CSV ([phase 4 dòng 157, 175–177](../plan/phases/phase-4-chong-chiu-lo-trinh.md)) [đã đọc tài liệu]. Giám khảo không tự kích hoạt được việc này trong một phiên: cần hai tuần chi tiêu mới, và đường duy nhất ghi được giao dịch quá khứ là nạp CSV [suy luận từ docstring của script]. Phase 6 và T-0x không ghi đây là rủi ro trình bày. Cách xử lý không cần tính năng mới: README và video nói rõ v3 là seed, thêm một đoạn video (hoặc mục README) chạy đường thật trên `lan`/`khoa`.

**PV-02. Khối số liệu đầu tiên của what-if chờ một lượt gọi Sonnet.** Proposal §12: "Khối dòng thời gian hiện ở khoảng giây thứ 2, văn bản kết thúc trước giây thứ 8". Đo được: khối đầu p50 6,9 s / p95 18,2 s ([phase 3 dòng 114](../plan/phases/phase-3-what-if-va-kiem-tra.md)) [đã đọc tài liệu]. Trong mã, `run_what_if` gọi `_orchestrate` (vai `planner`, Sonnet 4.6) trước khi lập kế hoạch đọc tool và chạy `run_scenario` (`whatif.py:460`, `:508-532`); `deterministic_spec` dựng được kịch bản từ tham số router nhưng chỉ dùng khi model lỗi (`whatif.py:529`) [đã chạy thử]. Ba tool đọc (`get_obligations`, `get_fee_schedule`, `get_forecast`) cũng chỉ chạy sau khi có spec [đã chạy thử]. Phase 6 D2 liệt kê bốn hướng (bộ giới hạn tốc độ, vòng sửa Verifier, phát khối trước Analyst, làm nóng phiên) nhưng không có hướng "bỏ lượt Orchestrator khỏi đường tới khối đầu" [đã đọc tài liệu]. Hướng đề xuất (để D1 đo trước): khi router đã trích đủ tham số của một trong sáu loại thì dùng spec do mã dựng từ tham số đó (vẫn đúng nguyên tắc "LLM hiểu ý, mã tính"), và chạy ba tool đọc song song với Orchestrator [suy luận; mức giảm chưa đo].

**PV-03. Luật "khoản nhỏ một lần vào hũ Khác, không hỏi" không bao giờ chạy.** Proposal §10.3: "khoản nhỏ một lần vào hũ 'Khác', không hỏi". `_is_small_one_off` đòi `small_one_off_jar_code in ctx.jars` (`pipelines/classify/yofina_classify/pipeline.py:271-278`); mã hũ là `khac` (`gateway/tools/ledger/yofina_ledger/classify_defaults.json:107-111`), trong khi `db/seed/jar_templates.sql:7-13` chỉ có 7 hũ, không có `khac`, và không persona nào có hũ này (`git grep` trong `data/personas` không ra) [đã chạy thử]. Đây là một phần nguyên nhân của tỷ lệ phải hỏi 17,4% (NFR-14 < 10%) [suy luận, chưa đo phần đóng góp]. T-03 và E7 có nhắc BR-18 nhưng không nhắc việc hũ không tồn tại [đã đọc tài liệu].

**PV-04. Không có CI.** Proposal §14: "AWS CDK, khởi đầu từ khung FAST — GitHub Actions cho CI — MVP". Repo không có `.github/` (`Test-Path .github` ra `False`) [đã chạy thử]. Phase 6 mục 0 ghi "Không có CI" nhưng không có việc nào thêm CI [đã đọc tài liệu]. Unit (3922), vitest (990), CDK (77) chạy không cần AWS theo README các gói, nên một workflow chạy ba bộ này là việc dưới nửa ngày [suy luận]. Với repo public, đây là bằng chứng chất lượng giám khảo thấy ngay.

**PV-05. Prompt caching chưa làm và không có trong ba/04.** Proposal §5 NFR chi phí: "prompt caching cho phần lặp"; phase 3 dòng 52: "Prompt đầu ổn định để cache (Sonnet cache từ khoảng 1.024 token)". `git grep -i cache` trong `libs/yofina_core/src/yofina_core` và `agent/src/yofina_agent` không có `cachePoint` hay tương đương [đã chạy thử]. Sonnet 4.6 chiếm khoảng 80% chi phí một lượt eval (HANDOFF) [đã đọc tài liệu]. ba/04 không có dòng NFR nào cho caching nên thiếu này không hiện trong bảng NFR.

### (b) Hành vi ngoài yêu cầu (scope creep)

**PV-06. Luồng K (khối `reasoning`) thêm trong phase 6, trong khi phase 6 ghi "Không thêm tính năng mới" (dòng 35).** Chủ dự án đã duyệt nên không phải lỗi quy trình [đã đọc tài liệu]. Hệ quả đo được: what-if `whatif-bnpl` trọn câu 37,9 s (Analyst 16,3 s so với 9,1–10,5 s trước đó); lập luận lộ trình nói "chuyển từ hũ Giải trí" trong khi bản đã lưu chuyển từ hũ Đi lại; bộ chấm `evals/run.py` chưa kiểm số trong khối `reasoning` (file phase 6, mục "Còn lại" của luồng K) [đã đọc tài liệu]. Đã theo dõi ở HANDOFF, nhưng cần quyết trước 28/11 có giữ khối này trên cảnh 2 và 4 hay không.

### (c) Có vẻ đã làm nhưng làm hoặc báo cáo chưa đúng

**PV-07. F3 "vàng" gần như không xảy ra.** Proposal §10.2: "vàng (sát: cạn sớm N ngày)". `afford.py:9-12` xếp vàng khi P10 dưới `affordability_tight_p10_floor_vnd`, ngưỡng này và ngưỡng hụt đều bằng 0 (`pipelines/forecast/yofina_forecast/settings.py:77`, `:79`) [đã chạy thử]. Đã theo dõi: T-02, chờ C-02.

**PV-08. NFR-01 và NFR-02 báo "Đạt" trên đường khác đường giám khảo dùng.** Proposal NFR: "Ký tự đầu tiên dưới 1,5 giây". Số 0,34 s / 2,04 s ở ba/04 dòng 18 và phase 6 tiêu chí 5 là thời gian tới `RUN_STARTED` của bản lát dọc phase 1 ([spike-vertical-slice.md dòng 98](spike-vertical-slice.md)), trước khi có router, Guardrail và luồng what-if [đã chạy thử `git grep`]. `scripts/measure_phase3.py` đã đo được `t_first_text_ms` và khối đầu (dòng 133–135) nhưng ba/04 không dùng [đã chạy thử]. NFR-02 (p95 282 ms) đo `POST /affordability`; qua chat, kiểm tra trước khi chi trọn lượt p50 6,3 s ([phase 3 dòng 114](../plan/phases/phase-3-what-if-va-kiem-tra.md)) [đã đọc tài liệu]. Phase 6 tiêu chí 5 vẫn đo "event đầu". Đề xuất ở lượt RC báo thêm "chữ đầu" và "khối đầu" theo ý định, lấy từ chính lượt đo đã định.

**PV-09. Tài khoản dự phòng `giamkhao3` là persona khác.** `data/personas/accounts.json`: `giamkhao3` → `vy`; `data/personas/roadmaps/` chỉ có `minh.json` [đã chạy thử]. Phase 6 J4 (dòng 194) ghi "tài khoản dự phòng `giamkhao2`, `giamkhao3`" [đã đọc tài liệu]. Trên `giamkhao3` cảnh 1 ra số khác (không phải "Ăn uống cạn ngày 23") và cảnh 4 không có lộ trình seed [suy luận từ dữ liệu seed]. Sửa runbook hoặc ánh xạ; README phải nói `giamkhao3` là persona khác.

### Tài liệu cũ (doc-stale)

**PV-10. Cửa vào repo còn ghi trạng thái 21/11.** `README.md:9`: "Chưa có code sản phẩm"; `CLAUDE.md:3`: "Dự án đang ở giai đoạn scaffold, chưa có code tính năng" (cả bản đã commit lẫn bản đang sửa dở trên máy) [đã chạy thử]. README đã có việc I1; CLAUDE.md không nằm trong danh sách I6 [đã đọc tài liệu].

**PV-11. requirements.md, overview.md, README các gói.** requirements.md dòng 11–25: mọi FR "chưa làm" hoặc "—" (dòng 5 tự nhận chưa cập nhật). overview.md dòng 65 "Chưa chạy `cdk deploy` nào"; dòng 207 "4 Strands Agent: Analyst, Simulation, Roadmap, Ingestion"; dòng 222 còn `knowledge___search`; dòng 245–247 ghi `resilience_scores`, `roadmaps`, `scenarios/nudges/feedback` là "dự kiến" dù đã có ở 0052, 0053. `pipelines/classify/README.md` và `infra-cdk/lib/classify.ts:114` ghi "CHƯA nối vào stack nào" nhưng `tools-stack.ts:202` đã nối và aws-resources.md ghi đã deploy; `pipelines/roadmap/README.md:47,77` ghi "Chưa deploy"; `gateway/tools/planner/README.md:3` ghi `schedule_nudge` dùng EventBridge Scheduler, mã ghi bảng `nudges` (`yofina_core/wallet.py:65`) [đã chạy thử]. FR12 mang ✅ ở ba/03 và ba/13 trong khi ba/05 ghi AC-FR12-03 "một phần", AC-FR12-04 "chờ kiểm", AC-FR12-07 "chưa làm" [đã đọc tài liệu]. requirements.md và overview.md đã có việc I6, I2; README các gói và trạng thái FR12 thì chưa.

## Lệch kiến trúc (câu hỏi 3)

| Thành phần (proposal/overview) | Hiện có | Ghi ở đâu | ADR |
|---|---|---|---|
| Harness L2 Orchestrator agents-as-tools, L3 "4 Strands Agent" | Mã điều khiển thứ tự; LLM chỉ dựng `ScenarioSpec`, Analyst, planner lộ trình, writer (`turn.py:7-25`, `whatif.py:1-20`); Simulation là engine, không phải agent; đọc ảnh nằm trong Lambda nạp | Docstring `turn.py`, research strands-agui | Không |
| Graph của Strands cho F3 | Code tuần tự có thời hạn | overview "Bỏ và hoãn" | Không |
| Bedrock Knowledge Bases, `knowledge.search` (RAG) | Cắt 24/11; `contracts/tools/knowledge.json` chỉ còn `get_fee_schedule`, `get_exchange_rate` | [phase 5 dòng 109](../plan/phases/phase-5-nap-du-lieu-ho-so-trace.md), HANDOFF | Không |
| Chronos-2, SageMaker | Không có (chỉ nhắc ở `ml/README.md`) | open-questions (chốt 21/11) | Không |
| Bedrock Data Automation, Automated Reasoning | Không có | open-questions (chốt 21/11) | Không |
| WAF | Không có (`git grep wafv2`/`CfnWebACL` không ra) | phase 6 dòng 75, "chờ duyệt ở mục 7" nhưng mục 7 không có câu hỏi nào về WAF | Không |
| Batch tuần (backtest, ACI, eval, đồng bộ KB) | `pipelines/weekly/` chỉ có `.gitkeep` | phase 6 Q11 (chưa chốt) | Không |
| AgentCore Evaluations online | Không có | phase 6 dòng 71, cũng không có câu hỏi ở mục 7 | Không |
| Memory: tóm tắt phiên, chiến lược custom cho hành vi, ReasoningBank | Chỉ `preferences_vi`, `facts_vi`; hồ sơ hành vi ở Aurora (`behavior_profiles`) | HANDOFF "Quyết định đã chốt" 24/11 | Không |
| OTel span mỗi lượt | Trace dựng từ `audit_events.step_timings`; Transaction Search tắt | phase 6 Q4 (chốt) | Không |
| Cedar cho tool ghi theo cờ xác nhận | Token dùng một lần do server cấp, Cedar `ENFORCE` là lớp phụ (`agent-stack.ts:42`) | — | ADR-0002 |
| Next.js | React + Vite | — | ADR-0001 |
| Guardrails, Budgets, EventBridge/SQS/Step Functions đêm, mã hóa | Có (`guardrail.ts`, `foundation-stack.ts:71`, `forecast-pipeline.ts`, `storageEncrypted: true` ở `data-stack.ts:54`, SQS/S3 managed) | aws-resources.md | — |
| CloudTrail, KMS khóa riêng | Không tạo trail hay khóa riêng; dùng khóa do AWS quản | — | Không |

Mọi dòng [đã chạy thử] cho cột "Hiện có", [đã đọc tài liệu] cho cột "Ghi ở đâu". **PV-12** (kết luận của bảng): lệch đều đã ghi ở đâu đó, nhưng rải ở năm loại file và chỉ hai dòng có ADR. Một ADR gộp "Lệch so với proposal" trỏ tới từng nơi sẽ là câu trả lời sẵn khi giám khảo hỏi "sao không có RAG/Chronos-2/WAF" [suy luận].

## NFR chưa đo hoặc trượt (câu hỏi 4)

| NFR (ba/04) | Tình trạng | Theo dõi ở |
|---|---|---|
| NFR-01 ký tự đầu < 1,5 s | Số hiện có là `RUN_STARTED` của phase 1 (PV-08) | Không |
| NFR-02 kiểm tra trước khi quẹt < 2 s | Chỉ đo REST; qua chat p50 6,3 s (PV-08) | Không |
| NFR-03 what-if p95 < 8 s | Trượt: 28,2 s; mẫu 37,9 s sau luồng K | Phase 6 Q1, D1, D2 |
| NFR-04 Tổng quan p95 < 300 ms | Chưa đo | Không |
| NFR-06 batch đêm xong trước 06:00 | ba/04 ghi "chưa ghi số"; `pipelines/nightly/README.md` có số 4 s cho 6 tài khoản nhưng đo trước khi thêm bước chống chịu, PELT, hồ sơ hành vi (có gọi model) | Không |
| NFR-07 số khớp tool 100% | 91,7% ở golden phase 5; chữ trong khối `reasoning` chưa chấm | Phase 6 tiêu chí 1, HANDOFF |
| NFR-08 LLM không tự tính | Chưa đo | Không |
| NFR-12 / K5 báo trước khi cạn | Chưa đo; là KPI ba/08 xếp cho giám khảo | Phase 6 H2 |
| NFR-14 phải hỏi < 10% | Trượt 17,4% (PV-03) | T-03, E7 |
| NFR-17, 23, 24, 29, 30, 41, 42, 43 | Chưa kiểm hoặc chỉ đề xuất; NFR-29 (công bố xử lý ngoài Singapore): `git grep Singapore frontend/src` không ra | Phase 6 B, C3, G2, G3 |
| NFR-31 trace 100% | Một phần; `turn_persist_timeout` ở mọi ca eval | Phase 6 C1 |
| NFR-33 đối kháng 50 câu | 42 câu | Phase 6 H1 (Q10 chưa chốt) |
| NFR-37 chi phí mỗi lượt | Một mẫu (1.578 ₫) | Phase 6 tiêu chí 8, I5 |
| (proposal) prompt caching | Không có dòng NFR, không có mã (PV-05) | Không |
| (ngoài bảng) `ApplyGuardrail` 400 ms | p50 446 ms | Phase 6 Q3 (chốt giữ) |

## Câu hỏi mở chặn đóng gói (câu hỏi 5)

- **Hạn nộp chính xác, định dạng nộp, trọng số chấm** ([open-questions dòng 7](../requirements/open-questions.md); phase 6 Q14): chưa trả lời. Chặn độ dài video, số trang slide, lịch RC. [đã đọc tài liệu]
- **Giữ tên Yofina** (dòng 16): chưa trả lời. Chặn tiêu đề README, video, slide.
- **Công bố dữ liệu xử lý ngoài Singapore** (dòng 50, C-09, NFR-29): chưa trả lời. Chặn mục quyền riêng tư của README và màn Giới thiệu.
- **Mở app MoMo kiểm lại** (dòng 17): chưa làm; proposal §13 ghi "Kiểm tra app trước khi chốt slide", và slide so sánh với MoMo dựa vào việc này.
- **Tên miền Amplify trong repo public** (dòng 100): chưa trả lời; README cho giám khảo cần link app.
- Region đã chốt (`ap-southeast-1`, 21/11), không chặn.
- Nhiều dòng ở mục "Rút ra từ nghiên cứu" (dòng 51–100) đã có câu trả lời trong mã nhưng chưa tick (ví dụ tên tool, danh tính xuống tool, xác nhận). Đã có việc I6.

## Điều chưa chắc

- Mức giảm độ trễ khi bỏ lượt Orchestrator khỏi đường tới khối đầu (PV-02) chưa đo; cần `step_timings` của D1. [suy luận]
- Phần đóng góp của luật "hũ Khác" vào tỷ lệ hỏi 17,4% chưa đo; chạy `evals/classification` với và không có hũ `khac` 0% sẽ trả lời (gọi embedding, rẻ). [suy luận]
- Prompt hệ thống của Analyst và Orchestrator có vượt ngưỡng 1.024 token để Sonnet cache được không: chưa đếm. [suy luận]
- Không đọc log Runtime hay Step Functions trên AWS; mọi nhận xét về hành vi chạy thật lấy từ tài liệu phase và HANDOFF.
- Không mở app trên trình duyệt; nhãn "Do AI tạo" thấy trong mã (`frontend/src/chat/MessageList.tsx:132`, `ChatSheet.tsx:115`), chưa soát 100% câu trả lời.
- Không chạy unit test (máy không có `uv` trong PATH của phiên này); không khẳng định nào ở đây cần test để chứng minh.

## Nguồn đã tra

Tài liệu trong repo (đọc ngày 25/11/2026): `docs/proposal/proposal-summary.md`, `docs/requirements/requirements.md`, `docs/requirements/open-questions.md`, `docs/architecture/overview.md`, `docs/ba/03-functional-requirements.md`, `docs/ba/04-non-functional-requirements.md`, `docs/ba/05-acceptance-criteria.md`, `docs/ba/08-kpi-kinh-doanh.md` mục 5, `docs/ba/10-tac-dong-stakeholder.md` mục 7, `docs/ba/13-tien-do-technical.md`, `docs/decisions/0001`–`0003` và README, `docs/plan/phases/phase-3-*.md`, `phase-4-*.md`, `phase-5-*.md`, `phase-6-*.md`, `docs/research/spike-vertical-slice.md`, `docs/aws-resources.md`, `HANDOFF.md`, `CLAUDE.md`, `README.md`.

Mã đã đọc: `agent/src/yofina_agent/turn.py`, `whatif.py`; `pipelines/forecast/yofina_forecast/batch.py`, `change.py`, `afford.py`, `settings.py`, `resilience.py`; `pipelines/classify/README.md`, `yofina_classify/pipeline.py`; `pipelines/roadmap/README.md`; `pipelines/nightly/README.md`, `pipelines/event/README.md`; `gateway/tools/ledger/yofina_ledger/classify_defaults.json`; `gateway/tools/planner/rules/`; `gateway/policies/`; `contracts/tools/*.json`; `libs/yofina_core/src/yofina_core/shocks.json`, `resilience.py`, `llm_defaults.json`; `infra-cdk/lib/tools-stack.ts`, `agent-stack.ts`, `ops-dashboard.ts`, `classify.ts`, `data-stack.ts`, `foundation-stack.ts`; `db/seed/jar_templates.sql`; `db/migrations/0053_phase5.sql`; `data/personas/accounts.json`, `data/personas/roadmaps/README.md`; `scripts/inject_behavior_shift.py`, `scripts/measure_phase3.py`; `frontend/src` (grep).

Không tra nguồn ngoài; câu hỏi của bài kiểm toán này chỉ cần đối chiếu nội bộ.
