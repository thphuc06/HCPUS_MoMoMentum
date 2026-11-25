# Kiểm toán độ trễ, chi phí và quota của lượt agent trên AWS (2026-11-25)

Người viết: worker Kiro (Claude Opus 5.5), một trong 9 luồng kiểm toán song song của phase 6. Chỉ đọc mã, tài liệu và số liệu AWS bằng lệnh chỉ đọc (Service Quotas, CloudWatch metrics, CloudWatch Logs Insights, Price List, `list-inference-profiles`). Không gọi Runtime, không chạy eval, không ghi tài nguyên nào.

Ký hiệu: **[đã đọc tài liệu]** là điều đọc từ tài liệu chính thức; **[đã chạy thử]** là số tự lấy hôm nay bằng lệnh chỉ đọc (hoặc trích lại phép đo đã ghi trong repo, có nêu nguồn); **[suy luận]** là điều rút ra từ hai loại trên, chưa kiểm trực tiếp.

Không lặp lại nội dung đã có ở [bedrock.md](bedrock.md) (bảng prompt caching, cách đặt `cachePoint`), [spike-bedrock-models.md](spike-bedrock-models.md) (ngưỡng cache đã đo, quota 21/11), [agentcore.md](agentcore.md) (vòng đời phiên, job nền), [strands-agui.md](strands-agui.md). Ghi chú này chỉ thêm số đo mới, phân rã độ trễ theo mã và các lỗi tìm thấy.

## Câu hỏi

1. Một lượt what-if, lập lộ trình, kiểm tra trước khi chi gồm bao nhiêu lời gọi model và tool nối tiếp nhau, model nào, thời gian đi đâu?
2. Cách sửa nào giảm độ trễ (thật và cảm nhận) nhiều nhất so với công và rủi ro?
3. Rủi ro quota Bedrock trong buổi chấm; mã xử lý throttle thế nào; cần xin hoặc đổi gì?
4. Chi phí mỗi lượt và mỗi lượt eval; cách rẻ nhất để giảm phần Sonnet 4.6?
5. Có cho giám khảo xem trace từng lượt được không; còn thiếu gì?

## Kết luận ngắn

- **What-if chậm vì Analyst (Sonnet 4.6) phải viết khoảng 2.000 token ra.** Độ trễ một lời gọi Sonnet gần như tỷ lệ với số token ra: khoảng 0,3 s cộng 7–9 ms mỗi token (bảng 1.1). Ở phiên ấm, lượt what-if có lập luận (luồng K) mất khoảng 21 s phía server, trong đó Analyst 15,5 s (74%). Con số 37,9 s của ca eval là phiên lạnh: thêm khoảng 8 s khởi động tiến trình và MCP, cộng Lambda lạnh. [đã chạy thử]
- **Prompt caching gần như không giảm độ trễ** ở cỡ prompt hiện tại (TTFT nhỏ), nhưng giảm khoảng một phần năm chi phí Sonnet. Hiện không lời gọi nào dùng cache (`CacheReadInputTokenCount` = 0). [đã chạy thử, suy luận]
- **Cách nhanh và an toàn nhất để demo "cảm thấy nhanh"**: (1) rút token ra của Analyst bằng prompt (khoảng −3 s); (2) song song hóa bốn đoạn đang chạy tuần tự (khoảng −1,5 đến −2 s); (3) đưa phần ghi lượt ra sau `RUN_FINISHED`; (4) nếu còn thời gian thì stream từng bước lập luận (khối đầu sau khoảng 4 s, bước lập luận đầu sau khoảng 5–6 s thay vì phải chờ 19 s). Các tùy chọn của AWS (latency-optimized, Priority tier, Reserved, giữ microVM chạy sẵn) đều không dùng được cho Sonnet 4.6 ở Singapore hoặc không đáng làm. [đã đọc tài liệu]
- **Quota là rủi ro thật khi chấm**: Sonnet 4.6 chỉ 10 RPM cho cả tài khoản, đã có 9 lần throttle ngày 23/11, chưa từng gửi yêu cầu tăng (quota ghi `Adjustable: true`). Mã có lỗi: lần gọi bị throttle vẫn tính vào trần 4 lượt gọi mỗi lượt hội thoại, nên khi Sonnet nghẽn, Analyst có thể bị chặn trước khi kịp rẽ sang Kimi K3 và lượt what-if mất phần giải thích. [đã chạy thử, đã đọc mã]
- **Chi phí**: một lượt what-if có lập luận khoảng $0,060 (khoảng 1.600 ₫), riêng token ra của Analyst khoảng một nửa. Ba thay đổi rẻ (Orchestrator ra khỏi Sonnet, cache prompt hệ thống, rút token ra) ước giảm khoảng 35%. Ngoài tiền model, mỗi lượt eval còn tốn khoảng $0,5–1 bộ nhớ Runtime vì mỗi ca để lại một phiên ngồi chờ 15 phút. [suy luận từ số đo]
- **Trace cho giám khảo đã có** (bảng "Vì sao", `/ops/traces/{id}`); AgentCore Observability chỉ có metric dịch vụ vì chưa có ADOT và Transaction Search (Q4 đã chọn không bật). Thiếu: model và token theo từng bước, lần rẽ dự phòng, thời gian ghi lượt và khởi động lạnh. [đã đọc mã, đã chạy thử]

## 1. Ngân sách độ trễ theo ý định

### 1.1 Số đo mới (chỉ đọc, 22–25/11)

**Độ trễ một lời gọi Sonnet 4.6 theo số token ra** (Logs Insights trên log group Runtime `yofina_agent`, sự kiện `llm_call` vai `planner`, 3 ngày, outcome `ok`) [đã chạy thử]:

| Token ra (nhóm) | Số lời gọi | p50 | p90 | Token vào TB | Token ra TB | Ứng với |
|---|---|---|---|---|---|---|
| 0–249 | 177 | 1,27 s | 1,49 s | 2.573 | 130 | Orchestrator, các lời gọi ngắn |
| 1.000–1.249 | 124 | 8,65 s | 9,50 s | 4.653 | 1.159 | Analyst trước luồng K, phác thảo lộ trình |
| 1.250–1.499 | 69 | 10,06 s | 10,74 s | 5.251 | 1.336 | như trên |
| 1.750–2.249 | 5 | 15,5–16,3 s | | 5.372–8.076 | 1.916–2.032 | Analyst có lập luận (luồng K) |

Hai điểm (130 token, 1,27 s) và (1.159 token, 8,65 s) cho khoảng 0,3 s cố định cộng 7,2 ms mỗi token ra; từ 1.159 lên 2.032 token là 8,8 ms mỗi token. Tức tốc độ sinh khoảng 110–140 token/s, còn phần đọc prompt chỉ vài trăm ms. [suy luận từ số đo]

Toàn tài khoản (`AWS/Bedrock`, 3 ngày): Sonnet 4.6 722 lời gọi, token vào TB 4.087, ra TB 625, `InvocationLatency` p50 3,2 s, p90 9,9 s; `CacheReadInputTokenCount` và `CacheWriteInputTokenCount` không có điểm dữ liệu nào với cả Sonnet, Nova 2 Lite, Haiku 4.5. Nova 2 Lite 1.746 lời gọi, p50 0,93 s, `TimeToFirstToken` p50 0,58 s. Sonnet không có `TimeToFirstToken` vì mã gọi `Converse` không stream. [đã chạy thử]

**Lambda tool** (dòng `REPORT`, 3 ngày) [đã chạy thử]: `yofina-forecast` 1.686 lần, p50 105 ms, p95 522 ms, 92 lần khởi động lạnh, `Init Duration` TB 2,45 s (1.769 MB). `yofina-ledger` 14.723 lần, p50 82 ms, p95 2,42 s, 180 lần lạnh, TB 0,82 s.

### 1.2 What-if: chuỗi lời gọi theo mã và thời gian đo

Dựng lại từ log hai lượt có lập luận (luồng K): phiên trình duyệt ấm ngày 25/11 (có `warmup` khi mở khung chat) và ca eval `whatif-bnpl` 24/11 (phiên mới, không làm nóng). Mốc tính từ sự kiện `invocation` của lượt. [đã chạy thử]

| # | Bước | Model / đích | Tuần tự hay song song | Mã | Phiên ấm 25/11 | Ca eval lạnh 24/11 |
|---|---|---|---|---|---|---|
| 0 | Nạp cấu hình, client, bộ nhớ, trước router | — | tuần tự | `app.py` `rt.deps()`, `turn.ensure_llm` | ~0 s | **3,7 s** |
| 1 | Router + Guardrail vào (song song) + đọc bộ nhớ (song song) | Nova 2 Lite (vai `small`) | router tuần tự | `turn.py:767-770`, `router.py:255-273` | 1,0 s | 1,05 s |
| 2 | Mở phiên MCP tới Gateway + `get_jar_balances` | Gateway → Lambda ledger | tuần tự, sau router | `whatif.py:452`, `tools.py:232-241` | 0,6 s | **4,9 s** (4,3 s trước request HTTP đầu tiên) |
| 3 | Orchestrator dựng `ScenarioSpec` | Sonnet 4.6 (vai `planner`), 2.607 vào / 128 ra | tuần tự | `whatif.py:459, 508-532` | 1,1 s | 1,1 s |
| 4 | `list_scenarios` (gộp khoản trước) | Lambda forecast | tuần tự | `whatif.py:466`, `bundle_with_previous` | 0,3 s | (không chạy) |
| 5 | Nhóm 0: `get_obligations`, `get_fee_schedule`/`get_forecast`; nhóm 1: `run_scenario`; song song với `get_behavior_profile` | Lambda ledger, forecast | hai nhóm nối tiếp | `whatif.py:482-484, 565-585` | 0,8 s | **4,2 s** (Lambda lạnh) |
| — | **Khối số liệu đầu tiên** (`forecast_timeline`, `obligation_impact`) | | | | **~3,8 s** | ~15 s |
| 6 | Analyst | Sonnet 4.6, 6.233 vào / 1.961 ra | tuần tự | `whatif.py:657-690` | **15,5 s** | **16,3 s** (6.921 / 2.013) |
| 7 | Verifier: NumericGrounding (mã) + 3 lần `check_suitability` song song | Lambda ledger | song song | `whatif.py:927-975` | 0,4 s | 2,6 s (một instance lạnh) |
| 7b | Vòng sửa khi `source_jar_covers` trượt (khoảng 6% lượt) | Sonnet 4.6, khoảng 5.440 / 920–1.090 | tuần tự | `whatif.py:619-647` | +5,5–6,2 s (đo ở phiên 23/11) | |
| 8 | Composer: Guardrail ra, `_prepare_action` từng phương án **lần lượt** | Bedrock Guardrail, Lambda | tuần tự | `whatif.py:978-1063`, vòng lặp `1027-1031` | 0,9–1,1 s | 0,8 s |
| 9 | Ghi lượt: `save_turn` + `record_turn` (song song, trần 3 s), **trước** `RUN_FINISHED` | Gateway → Lambda | tuần tự với lượt | `turn.py:656-676, 714-739` | 0,3 s | 0,5 s |
| | **Tổng phía server** | | | | **~21 s** | **~35,3 s** (runner đo 37,9 s) |

Đếm lời gọi: model 3 (router, Orchestrator, Analyst), 4 nếu có vòng sửa (trần `max_model_calls_per_turn` = 4); tool 10–12. Verifier là mã, không phải LLM, nên câu hỏi "model nhỏ cho verifier" không áp dụng. [đã đọc mã]

Hai phiên khác đáng ghi: phiên trình duyệt 23/11 (trước luồng K) có 2/2 lượt what-if "tai nghe Trả sau" phải sửa một vòng, tổng 21,6–23,2 s; Analyst lần đầu 9,5–9,6 s (khoảng 1.150 token ra) và lần sửa 5,5–6,2 s. 12 lần `verifier_retry` trong 3 ngày, tất cả do `source_jar_covers`. [đã chạy thử]

### 1.3 Lập lộ trình trong chat

Router (Nova, khoảng 1 s) → đọc ngữ cảnh song song (`get_jar_balances`, `get_obligations`, `get_resilience_score`, `get_roadmap`, `optimize_allocation`, `get_behavior_profile`) → phác thảo (Sonnet, tối đa `roadmap_draft_max_tokens` 3.000) → có thể tối ưu lần hai → kiểm suitability từng bước (song song) → có thể sửa (Sonnet) → lưu (`roadmap_agent.py:1096-1530`). Sự kiện `roadmap_stage` 12 lần trong 3 ngày [đã chạy thử]: tổng p50 14,1 s / p90 19,6 s; `draft` p50 10,6 s, tối đa 16,5 s (ca có lập luận); `suitability` p50 2,7 s / p90 4,2 s; `context` p50 0,46 s / p90 3,4 s (Lambda lạnh); `save` 0,45 s. Một hoặc hai lời gọi Sonnet, cũng bị giới hạn bởi token ra.

### 1.4 Kiểm tra trước khi chi

- REST `POST /affordability`: không model, p95 328 ms (phase 3).
- Qua chat (`turn.py:1387-1423`): router (Nova) → `get_jar_balances` nếu câu có hũ → `affordability_check` → người viết Nova 2 Lite trong thời hạn 2 s → ghi lượt. Phiên ấm 25/11 [đã chạy thử]: 3,6 s từ `invocation` tới lúc ghi lượt xong (router 1,0 s, MCP + hũ 0,6 s, tool 0,4 s, người viết 0,8 s, ghi lượt 0,3 s). Không có Sonnet.

### 1.5 Vì sao 17–38 s

- 17 s: what-if trước luồng K, phiên ấm, không vòng sửa (Analyst khoảng 9,5 s).
- 21–24 s: như trên nhưng có vòng sửa `source_jar_covers` (+6 s), hoặc lượt có lập luận ở phiên ấm.
- 28–38 s: lượt có lập luận ở phiên eval lạnh: khoảng 8 s khởi động (bước 0 và 2), Lambda lạnh 2–4 s, Analyst 16 s.

Proposal §12 đặt "văn bản xong trước giây thứ 8". Với Sonnet 4.6 viết khoảng 1.600 trở lên token tiếng Việt, mục tiêu này không đạt được nếu không đổi model; tách hai chỉ tiêu như Q1 là đúng hướng. [suy luận]

## 2. Các cách sửa, xếp hạng

Xếp theo (độ trễ hoặc chi phí giảm được) chia cho (công × rủi ro). "S" là dưới nửa ngày.

| # | Cách | Giảm độ trễ | Giảm chi phí | Công | Rủi ro | Nguồn | Đã có trong kế hoạch |
|---|---|---|---|---|---|---|---|
| F1 | **Rút token ra của Analyst bằng prompt**: lập luận 2–3 bước (prompt đang ghi 2–4, log cho thấy model trả 4), `narrative` 1–2 câu, `follow_ups` tối đa 2. Giữ trần schema như cũ, vì Analyst chạy `max_attempts=1` (`whatif.py:683`), siết schema là đổi lỗi nhỏ thành lượt suy giảm | khoảng −300 đến −400 token, **−2,5 đến −3,5 s** | khoảng −$0,005/lượt | S | Thấp; đo 3 ca `--only` | §1.1 | D2 (một phần), K "còn lại" |
| F2 | **Song song hóa**: (a) khởi động `ensure_jars` (mở MCP) cùng lúc với router và Guardrail; (b) chạy `list_scenarios` và `get_obligations` cùng lúc với Orchestrator (hai tool này không phụ thuộc spec); (c) `_prepare_action` dùng `asyncio.gather` thay vòng lặp; (d) Guardrail ra chạy cùng lúc với (c) | **−1,5 đến −2 s** (0,6 + 0,6 + 0,2–0,7 + 0,4) | 0 | S | Thấp (thêm một lần đọc hũ ở lượt chitchat/ngoài phạm vi; vẫn dưới trần 18 tool) | `whatif.py:452, 466, 1027-1031`; `turn.py:770` | D2 nói chung, chưa có mục cụ thể |
| F3 | **Ghi lượt sau `RUN_FINISHED`**: chạy `persist` như một tác vụ nền (giống `schedule_remember`), nới thời hạn lên khoảng 10 s, frontend thử lại một lần khi `/ops/traces/{id}` trả 404 | −0,3 s thường gặp, **−3 s** ở lượt chạm timeout (17 lần trong 2 ngày); ít mất bản ghi lượt hơn (NFR-31) | 0 | S | Thấp; tác vụ nền vài giây nằm trong thời hạn idle 15 phút | `turn.py:654-676`; [runtime-long-run](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-long-run.html) | C1 (C1 tìm nguyên nhân; đây là đổi thứ tự) |
| F4 | **Orchestrator ra khỏi Sonnet**: dùng `deterministic_spec` khi tham số router đủ (đã có cho Trả sau, mua một lần, chuyển hũ, đổi lương, `whatif.py:130-156`), không đủ thì gọi vai `small` (Nova 2 Lite, dự phòng Sonnet). Nova 2 Lite đạt 14/14 bài ép tool ở spike | −0,1 đến −1,1 s | −$0,008/lượt; **số lời gọi Sonnet mỗi what-if từ 2 xuống 1** (gấp đôi sức chứa quota) | S | Vừa: cần 9 ca `what_if` golden `--only` (khoảng $0,4) | §1.2; spike-bedrock-models §3 | Không |
| F5 | **Ít vòng sửa Verifier hơn**: đưa vào `<danh_sach_hu>` cờ do mã tính "đủ cho khoản này" (số dư ≥ số tiền kịch bản) bên cạnh `balance_text`; quy tắc chung, không vá cho ca | tránh **+5,5 đến +6,2 s** ở khoảng 6% lượt (nhiều hơn ở câu demo cảnh 2) | tránh +$0,03 mỗi lần sửa | S | Thấp | §1.2 | D2(b) |
| F6 | **Prompt caching**: thêm `cachePoint` sau `system` (tiền tố gồm tool ép + system) cho Analyst, Orchestrator, phác thảo lộ trình; bật theo cờ từng model trong `llm_defaults.json` (như cờ `temperature`), vì Kimi K3 trả `ValidationException` với `cachePoint` (spike §4) mà `ValidationException` không nằm trong `FALLBACK_ERROR_CODES` (`llm.py:66-76`). Ghi `cacheRead/WriteInputTokens` vào `llm_call` | ~0 (TTFT đã nhỏ) | khoảng **−$0,008/what-if**, khoảng −15 đến −20% tiền Sonnet của một lượt eval | S | Thấp | [prompt-caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html); model card Sonnet 4.6 | Không (spike/bedrock.md chỉ ghi khả năng) |
| F7 | **Stream từng bước lập luận** (D2c): thêm đường `ConverseStream` có ép tool vào `yofina_core.llm` (giữ chuỗi dự phòng, trần, đếm lượt), cộng dần `contentBlockDelta.delta.toolUse.input` (chuỗi JSON từng phần), mỗi khi một phần tử của `reasoning` khép lại thì mã kiểm số và căn cứ của bước đó rồi phát lại khối `reasoning` `complete:false` (frontend đã nhận bản phát dần, `ReasoningView.tsx`). Bước dựa trên luật thì chờ tới khi `check_suitability` xong. `reasoning` là trường đầu của `Analysis` (`schemas.py:299`) | Cảm nhận: bước lập luận đầu sau khoảng **5–6 s** thay vì 19 s; tổng không đổi | 0 | M (1–1,5 ngày) | Vừa: vòng sửa có thể ra lập luận khác bản đã hiện, cần thay khối cùng id | [ToolUseBlockDelta](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolUseBlockDelta.html); [AG-UI ActivitySnapshot/Delta](https://docs.ag-ui.com/concepts/events) | D2(c), K "còn lại" |
| F8 | **Làm nóng trước mỗi ca eval** (gửi `forwardedProps.warmup` cho session mới) hoặc báo độ trễ RC tách phiên ấm và lạnh | Số đo RC phản ánh đúng demo (bỏ khoảng 8 s lạnh) | 0 | S | Không | `evals/run.py:251-283` | Không (mục 5.2 phase 6 lấy độ trễ từ lượt RC) |
| F9 | Aurora 0,5 ACU trong khung chấm | tránh khoảng 15 s (hơn 30 s nếu ngủ quá 24 giờ) ở lời gọi đầu | +khoảng $2,4/ngày | S | Không | [auto-pause](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html) | J3, Q12 |
| F10 | Làm ấm Lambda trong khung chấm: script J1 gọi vài tool song song; provisioned concurrency chỉ khi thấy lạnh trên đường demo | tránh 0,8–2,5 s khi gặp instance lạnh | PC khoảng $1–2/ngày | S (script) / M (PC đổi target Gateway sang alias) | Thấp / Vừa | §1.1 Lambda | J1 (một phần) |

**Không khuyến nghị trước demo** [đã đọc tài liệu]:

- *Latency-optimized inference*: chỉ có cho Claude 3.5 Haiku, Nova Pro, Llama 3.1 405B/70B ở `us-east-1/2`, `us-west-2`, đang preview.
- *Priority tier*: model card Sonnet 4.6 ghi Priority và Flex **không hỗ trợ** (chỉ Standard và Reserved). Nova 2 Lite có SKU priority (+75% giá) nhưng router chỉ khoảng 1 s, không đáng.
- *Reserved tier*: tối thiểu 100.000 TPM vào và 10.000 TPM ra, cam kết 1–3 tháng, phải liên hệ account team.
- *Runtime chạy sẵn*: microVM của AgentCore không có provisioned concurrency; loại Instances (EC2) là quá tay. Làm nóng phiên khi mở khung chat đã có (`ChatProvider.tsx:79-105`, `app.py` `warm()`); phiên ấm cho event đầu 0,34 s.
- *Analyst chạy Haiku 4.5*: có thể nhanh hơn nhưng chưa đo chất lượng tiếng Việt và luật; xô Haiku còn dùng chung với Memory. Chỉ thử sau cuộc thi.
- *Chia Analyst thành hai lời gọi song song* (phương án và lập luận): nhanh hơn vài giây nhưng thêm một lời gọi Sonnet mỗi lượt (xấu cho quota) và làm lập luận dễ lệch phương án hơn (lỗi đã biết của luồng K).

Cộng F1, F2, F3, F5 (và F4 nếu đạt eval), một lượt what-if có lập luận ở phiên ấm ước còn khoảng 14–16 s, khối số liệu đầu khoảng 2,5–3 s; thêm F7 thì người dùng thấy bước lập luận đầu khoảng giây thứ 5–6. [suy luận]

## 3. Quota và throttling trong buổi chấm

### 3.1 Quota đang áp dụng (`ap-southeast-1`, Service Quotas, 25/11) [đã chạy thử]

| Quota | Giá trị | Adjustable | Ai dùng chung |
|---|---|---|---|
| Global cross-region RPM, Claude Sonnet 4.6 (`L-F6E116D7`) | **10** | có | Orchestrator, Analyst, phác thảo lộ trình (agent); OCR ảnh (Lambda ingest); Lambda sinh lại lộ trình; mọi lượt eval |
| Global TPM, Sonnet 4.6 | 6.000.000 | có | |
| Global RPM, Claude Haiku 4.5 (`L-E5084BBA`) | **10** | có | Trích xuất và hợp nhất của Memory (2–4 lời gọi mỗi lượt được ghi); model dự phòng của vai `small`, `ingest_columns` |
| Global RPM, Claude Sonnet 4.5 (`L-DB84CE56`) | 10 | có | Chưa dùng (xô riêng) |
| Global RPM, Nova 2 Lite (`L-D5F39C2F`) | **20** | có | Router, người viết, phân loại, `ingest_columns` |
| Global TPM, Kimi K3 | 10.000.000 | có | Dự phòng của `planner`, `ingest`; không có dòng RPM |

Lịch sử yêu cầu tăng quota của dịch vụ `bedrock`: **rỗng** (chưa từng gửi). `AWS/Bedrock` `InvocationThrottles`: Sonnet 4.6 **9 lần** trong ngày bắt đầu 23/11 11:32 (+07), Kimi K3 4 lần gọi cùng khoảng (đường dự phòng đã chạy); Haiku 4.5 239 lần ngày 20/11. Chỉ Sonnet 4.6 có hồ sơ suy luận `global.` ở Singapore (không có `apac.`). [đã chạy thử]

### 3.2 Mã xử lý throttle thế nào [đã đọc mã]

- Mỗi tiến trình (mỗi microVM, tức mỗi phiên) có bộ giới hạn cửa sổ trượt: Sonnet 8/phút, Nova 18, Haiku 8 (`llm_defaults.json`). Hết chỗ thì **ngủ tới 20 s** (`rate_limit_max_wait_seconds`) rồi mới rẽ sang model kế (`llm.py:650-672`). Bộ đếm này không chia giữa các phiên, nên hai, ba giám khảo cùng lúc vẫn có thể vượt 10 RPM của tài khoản.
- Bedrock trả `ThrottlingException` (cả `AccessDeniedException`, `ModelTimeoutException`...) thì rẽ sang model kế: Sonnet → Kimi K3, Nova → Haiku 4.5 (`llm.py:66-76, 721-765`; `metered_model.py:88-145`). Hết chuỗi thì `AllModelsFailed`, lượt bật `llm_down` và chỉ còn khối số liệu tất định cùng notice.
- **Lỗi AG-03**: `TurnScope.begin_call` chạy **trước** khi chờ bộ giới hạn và trước khi gửi (`llm.py:653, 667`); lần gọi bị throttle cũng được ghi là một bản ghi (`record(... outcome=code)`). Trần mỗi lượt là 4. Kịch bản khi Sonnet nghẽn: router (1), Orchestrator Sonnet bị throttle (2) → Kimi (3), Analyst Sonnet bị throttle (4) → Kimi bị chặn bởi `turn_limit` (`llm.py:401-409`). `ModelBudgetExceeded` không bị bắt trong vòng dự phòng, `_call_analyst` trả `None`, lượt what-if chỉ còn khối số liệu. Không có unit test cho tổ hợp throttle + dự phòng + trần lượt (`libs/yofina_core/tests/test_llm.py:359-365` chỉ kiểm trần đơn).
- Lỗi phụ: ở vòng sửa, nếu Analyst lần hai trả `None` (`whatif.py:628-630`) thì lượt bỏ luôn các phương án đã qua kiểm của vòng một thay vì đi `_compose_degraded` để cứu phương án.
- Kimi K3 "luôn suy nghĩ" (spike), nên Analyst trên Kimi sẽ chậm hơn Sonnet; `run_timeout_seconds` là 60 s. Kimi không nhận `cachePoint` (xem F6).

### 3.3 Sức chứa [suy luận]

Một what-if tốn 2 lời gọi Sonnet (3 nếu có vòng sửa), lộ trình 1–2, mỗi ảnh nạp 1 (Lambda). Với 10 RPM: tối đa khoảng 5 what-if mỗi phút cho cả tài khoản. Một giám khảo đi 6 cảnh dùng khoảng 6–8 lời gọi Sonnet trải trong vài phút, không vượt. Ba giám khảo bấm cảnh 2 trong cùng một phút là 6–9 lời gọi, cộng một ảnh nạp là chạm trần. F4 hạ còn 1 lời gọi Sonnet mỗi what-if.

### 3.4 Nên xin hoặc đổi gì trước khi chấm

1. **Chủ dự án gửi yêu cầu tăng quota** (ghi AWS, miễn phí, có thể bị từ chối): Sonnet 4.6 global RPM 10 → 30 trở lên; Haiku 4.5 10 → 20; Nova 2 Lite 20 → 40. Gửi trước 28/11 để kịp. Spike 21/11 ghi "không xin tăng quota được" nhưng Service Quotas cho thấy chưa có yêu cầu nào; nên thử.
2. Sửa AG-03: chỉ gọi `begin_call` khi thật sự gửi và không tính lần bị throttle vào trần lượt (lần bị throttle không mất tiền), thêm test cho kịch bản ở 3.2. Công S.
3. Hạ `rate_limit_max_wait_seconds` từ 20 xuống khoảng 4 qua SSM `/yofina/llm/rate_limit_max_wait_seconds` trong khung chấm (không cần deploy): nghẽn cục bộ thì rẽ Kimi ngay thay vì ngủ 20 s.
4. F4 (Orchestrator ra khỏi Sonnet) cho gấp đôi số what-if mỗi phút.
5. Cân nhắc thêm Sonnet 4.5 (xô 10 RPM riêng, có cache) làm model thứ hai của vai `planner` trước Kimi K3. Cần gọi thử và cập nhật IAM (agent-stack đọc `llm_defaults.json` lúc synth); chưa kiểm chất lượng nên để chủ dự án quyết.
6. Như J4: không chạy eval, không nạp lô ảnh trong khung chấm; theo dõi `InvocationThrottles` (chưa có trên dashboard, xem mục 5).

## 4. Chi phí mỗi lượt và mỗi lượt eval

Giá (Price List, `ap-southeast-1`, global) [đã chạy thử]: Nova 2 Lite $0,41 vào / $3,39 ra / $0,1025 đọc cache mỗi 1M token; Runtime v2 $0,1276/vCPU-giờ, **$0,0169/GB-giờ**; Gateway $0,000005 mỗi lần gọi. Sonnet 4.6 $3 / $15, ghi cache $3,75, đọc cache $0,30 mỗi 1M (spike §4, Price List).

**What-if có lập luận, phiên ấm 25/11** (token đo được) [suy luận từ số đo]:

| Phần | Token vào / ra | USD |
|---|---|---|
| Router (Nova 2 Lite) | 4.951 / 101 | 0,0024 |
| Orchestrator (Sonnet) | 2.607 / 128 | 0,0097 |
| Analyst (Sonnet) | 6.233 / 1.961 | 0,0481 (riêng token ra 0,0294) |
| Gateway (khoảng 14 lần), Runtime CPU trong lượt | | < 0,001 |
| **Tổng** | | **khoảng $0,060** (khoảng 1.600 ₫ theo tỷ giá mà trace dùng) |

Lượt có vòng sửa (23/11) khoảng $0,071; vòng sửa đắt ngang lần Analyst đầu. Sau F1 + F4 + F6 ước khoảng $0,039 (−35%). Kiểm tra trước khi chi qua chat khoảng $0,003 (chỉ Nova).

**Một lượt eval đầy đủ**: tiền model khoảng $2,2–2,5 (HANDOFF; khoảng 80% Sonnet). Phần Sonnet gồm khoảng 52% tiền token vào (TB 3.824 vào, 719 ra mỗi lời gọi trong log Runtime 3 ngày), nên cache prompt hệ thống có tác dụng thật lên chi phí. Ba thay đổi rẻ nhất, không đụng chất lượng: F6 (cache, khoảng −15 đến −20% tiền Sonnet; tỷ lệ trúng cache giảm khi suy luận toàn cầu định tuyến sang máy khác, theo tài liệu), F4 (bỏ một lời gọi Sonnet mỗi ca what-if), F1 (ít token ra hơn). [suy luận]

**Tiền Runtime bị bỏ sót trong ước tính eval** [đã chạy thử, suy luận]: `MemoryUsed-GBHours` toàn Runtime 33–156 GB-giờ/ngày (21–24/11). Buổi tối 24/11 có 32–39 phiên hoạt động cùng lúc và 12–28 GB-giờ mỗi giờ, tức khoảng 0,6–0,8 GB mỗi phiên, phiên tắt sau khoảng 15 phút ngồi không. Mỗi ca eval mở một phiên mới (`evals/run.py:251-252`) rồi để nó chờ hết 15 phút, nên một lượt eval tốn thêm khoảng $0,5–1 tiền bộ nhớ. Cách giảm: runner gọi `StopRuntimeSession` (HTTPS kèm bearer token cho Runtime dùng JWT) ngay sau mỗi ca **không** có bộ nhớ (ca bộ nhớ cần tác vụ ghi nền chạy xong). Phụ: `/ping` trả `time_of_last_update` = giờ hiện tại ở mỗi lần ping (`app.py:123`); tài liệu cảnh báo cách này có thể làm phiên không bao giờ hết hạn idle. Số đo hiện chưa cho thấy phiên bị giữ tới 8 giờ, nhưng nên bỏ trường này cho đúng hướng dẫn (một dòng).

## 5. Observability: trace cho giám khảo

Đã có [đã đọc mã]:

- Mỗi lượt một bản ghi `audit_events` do mã dựng: `step_timings` (router, guardrail vào/ra, orchestrator, analyst, verifier, composer, từng lần gọi tool kèm ms và `status`), token theo model, `model_calls`, chi phí ước tính, luật đã kiểm, nguồn dữ liệu. Xem qua `/ops/traces/{id}`, `/ops/summary` và bảng "Vì sao" (cảnh 6). Đủ để cho giám khảo xem trace từng lượt.
- Dashboard `yofina-ops`: độ trễ Lambda tool, lỗi Lambda, DLQ, quyết định Cedar, ACU Aurora, `AWS/Bedrock Invocations` so với trần, lỗi và độ trễ REST (`ops-dashboard.ts:190-247`).

AgentCore Observability [đã đọc tài liệu, đã chạy thử]: metric dịch vụ đã có sẵn trong namespace `AWS/Bedrock-AgentCore` (Invocations, Latency, Sessions, ActiveSessionCount, MemoryUsed-GBHours, CPUUsed-vCPUHours, Throttles, SystemErrors, UserErrors; metric của Gateway và Policy). Span và dashboard theo phiên/trace cần ADOT trong mã agent và bật CloudWatch Transaction Search. Agent hiện không có gói ADOT (`agent/pyproject.toml`), đích trace segment của X-Ray vẫn là `XRay` (Transaction Search chưa bật), model invocation logging của Bedrock chưa cấu hình. Q4 đã chọn không bật; giữ nguyên.

Còn thiếu (đều nhỏ):

1. `step_timings` không ghi model và token ra của từng bước, nên trace chưa tự giải thích được "Analyst 16 s vì viết 2.000 token". Có sẵn `CallRecord` trong `TurnScope` (`llm.py:380-387`), chỉ cần gắn vào bước.
2. Lần rẽ dự phòng (Sonnet bị throttle → Kimi) chỉ nằm trong log, không lên trace hay bảng "Vì sao".
3. `duration_ms` tính trước khi ghi lượt và sau khi nạp cấu hình (`turn.py:678-705`), nên thấp hơn thời gian client thấy khoảng 1–3 s (phase 3: server p50 13,8 s, client p50 16,7 s).
4. Dashboard thiếu `InvocationThrottles` và `InvocationLatency` theo model, `Latency` và `ActiveSessionCount` của Runtime. Thêm 2–3 widget, không phí.

## 6. Khuyến nghị cho Yofina (thứ tự làm)

Đợt deploy 1 (28/11):

1. F3 (ghi lượt sau `RUN_FINISHED`) cùng C1; AG-03 (trần lượt và throttle) cùng test; bỏ `time_of_last_update` ở `/ping`.
2. F2 (song song hóa bốn chỗ) và F5 (cờ "đủ tiền" theo hũ), vì đều là mã nhỏ và không đổi hành vi.
3. F1 (rút token ra) bằng prompt; đo lại `whatif-bnpl`, `whatif-bnpl2`, `roadmap-create-emergency-fund` mỗi ca một lần.
4. F6 (cache) có cờ theo model và có test "Kimi không nhận `cachePoint`".
5. Chủ dự án gửi yêu cầu tăng quota (mục 3.4).

Đợt deploy 2 (2/12), nếu đợt 1 ổn: F4 (Orchestrator ra khỏi Sonnet, cần 9 ca `what_if` `--only`), F7 (stream lập luận) chỉ khi còn ít nhất 1,5 ngày trước code freeze 3/12. Trước lượt RC: F8 (làm nóng trước mỗi ca hoặc báo tách ấm/lạnh); runner gọi `StopRuntimeSession` sau ca không có bộ nhớ. Khung chấm: F9, F10 (script J1), `rate_limit_max_wait_seconds` = 4.

## 7. Điều chưa chắc

- Hệ số 7–9 ms mỗi token ra đo trên Sonnet 4.6 qua hồ sơ toàn cầu trong 3 ngày; tốc độ có thể đổi theo tải của vùng được định tuyến tới. Mẫu luồng K mới có 5 lời gọi.
- Khoảng 4,3 s trước request HTTP đầu tiên ở ca eval lạnh: suy ra là import `strands.tools.mcp`/`mcp` lần đầu cộng tạo client Guardrail, vì phiên đã làm nóng (`warm()` import sẵn các gói này) chỉ mất 0,6 s. Chưa đo từng phần.
- Phần chi phí Runtime của một lượt eval ($0,5–1) suy ra từ metric theo giờ; giờ đó có thể có cả lượt dùng khác ngoài eval.
- Tỷ lệ trúng cache khi dùng hồ sơ `global.`: tài liệu nói yêu cầu đi vùng khác thì ghi cache mới; chưa đo.
- Chưa biết yêu cầu tăng quota được duyệt nhanh hay không, và có bị từ chối với tài khoản chi tiêu thấp không.
- `eager_input_streaming` (fine-grained tool streaming) được Anthropic ghi là hỗ trợ trên Bedrock cho Sonnet 4.6, nhưng chưa thấy cách đặt qua Converse; F7 không cần nó vì luồng thường vẫn trả từng giá trị trọn vẹn.
- Chất lượng Kimi K3 và Sonnet 4.5 làm Analyst khi rẽ dự phòng chưa được eval.

## 8. Nguồn (truy cập 2026-11-25)

Tài liệu chính thức:

- Amazon Bedrock, Prompt caching for faster model inference: https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html
- Amazon Bedrock, model card Claude Sonnet 4.6 (cache 1.024 token, TTL 5 phút/1 giờ; Priority, Flex không hỗ trợ; chỉ có Global ở `ap-southeast-1`): https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-4-6.html
- Amazon Bedrock, Optimize model inference for latency: https://docs.aws.amazon.com/bedrock/latest/userguide/latency-optimized-inference.html
- Amazon Bedrock, Service tiers: https://docs.aws.amazon.com/bedrock/latest/userguide/service-tiers-inference.html
- Amazon Bedrock API, ToolUseBlockDelta: https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolUseBlockDelta.html
- AgentCore, Handle asynchronous and long running agents (ping `HealthyBusy`, cảnh báo `time_of_last_update`): https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-long-run.html
- AgentCore, lifecycle settings (idle 900 s, maxLifetime 28.800 s): https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-lifecycle-settings.html
- AgentCore, Stop a running session: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-stop-session.html
- AgentCore, Add observability (Transaction Search, ADOT): https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html
- AgentCore pricing (Runtime v2 tính bộ nhớ suốt phiên, kể cả lúc ngồi không): https://aws.amazon.com/bedrock/agentcore/pricing/
- Aurora Serverless v2 auto-pause (resume khoảng 15 s, hơn 30 s sau 24 giờ): https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html
- AG-UI, Events (ActivitySnapshot, ActivityDelta): https://docs.ag-ui.com/concepts/events
- Anthropic, Fine-grained tool streaming: https://platform.claude.com/docs/en/agents-and-tools/tool-use/fine-grained-tool-streaming

Số liệu tự lấy (chỉ đọc, `ap-southeast-1`, 25/11):

- Service Quotas `bedrock`, `bedrock-agentcore`; `list-requested-service-quota-change-history` (rỗng).
- CloudWatch `AWS/Bedrock` (Invocations, InvocationThrottles, InvocationLatency, TimeToFirstToken, token, cache token) và `AWS/Bedrock-AgentCore` (ActiveSessionCount, MemoryUsed-GBHours, CPUUsed-vCPUHours).
- CloudWatch Logs Insights trên log group Runtime `yofina_agent` (sự kiện `llm_call`, `roadmap_stage`, `verifier_retry`, `turn_persist_timeout`...) và `/aws/lambda/yofina-forecast`, `/aws/lambda/yofina-ledger` (dòng `REPORT`).
- AWS Price List API: `AmazonBedrockAgentCore`, `AmazonBedrock` (Nova 2 Lite).
- `aws bedrock list-inference-profiles`, `get-model-invocation-logging-configuration`; `aws xray get-trace-segment-destination`.

Mã đã đọc: `agent/src/yofina_agent/{turn,whatif,router,roadmap_agent,tools,app,metered_model,schemas}.py`, `agent/src/yofina_agent/defaults.json`, `libs/yofina_core/src/yofina_core/{llm.py,llm_defaults.json}`, `infra-cdk/lib/{agent-stack,data-stack,ops-dashboard}.ts`, `frontend/src/chat/{session.ts,ChatProvider.tsx}`, `evals/run.py`, `scripts/measure_phase3.py`.
