# Router chạy Claude Haiku 4.5, Nova 2 Lite dự phòng: cấu hình, rà prompt, đường lùi của harness, đo lại (2026-11-26)

Issue [#39](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/39). Nhánh `int/router-measure`, nối tiếp phép đo QQ (commit `7c83d36`). Quyết định của chủ dự án ngày 26/11: router dùng Haiku 4.5, Nova 2 Lite làm dự phòng, qua một vai riêng; không ép prompt để qua các câu còn trượt; chấp nhận sai sót của model khi harness lùi an toàn.

Phân biệt: **đã chạy thử** là hai lượt đo bằng Bedrock thật (QQ và lượt này, mục "Đo") và test đơn vị; **đã đọc tài liệu** là giới hạn prompt cache; **suy đoán** được ghi rõ ở mục "Giới hạn đã biết".

## Kết luận ngắn

- Router gọi vai `router` trong `llm_defaults.json`: Haiku 4.5 (8 rpm, trần 2.000 lượt/ngày, `prompt_cache` bật) rồi Nova 2 Lite (18 rpm, 2.000 lượt/ngày). Vai `small` không đổi. `router_max_tokens` từ 400 lên 800.
- Đo lại 24 câu của QQ bằng cấu hình thật của nhánh: Haiku trả lời cả 24 câu, JSON hợp lệ ngay lần đầu 24/24, không lời gọi nào chạm trần token. Sau harness, 19/24 câu đúng mọi trường. Model thô đúng 17/24. Trung bình 0,00365 USD/lượt có cache và 0,01427 USD/lượt không cache. Lượt đo tiêu 0,0875 USD.
- Năm câu còn trượt đều do model, và harness xử lý an toàn: hoặc ra đúng hũ, hoặc hỏi lại đúng một câu, hoặc đi đúng đường cũ. Lượt đo còn lộ hai lỗi của harness. Cờ `keep_previous` do model tự đặt làm what-if gộp ngầm khoản cũ: đã sửa. Luật đọc chữ của câu đang chờ đọc "các hũ ra sao" thành hũ "ra": chưa sửa, vì nằm ngoài các file được giao.
- IAM không đổi. Quyền gọi model của Runtime dựng từ tập model id của mọi vai, mà Haiku đã có trong tập đó. Chỉ cần deploy Runtime.

## Cấu hình vai router

| Mục | Giá trị | Lý do |
|---|---|---|
| Model chính | `global.anthropic.claude-haiku-4-5-20251001-v1:0`, 8 rpm | QQ đo: Nova gần như không điền được `spend_jar_code`, `answers_pending`, `date_spec`. Giữ 8 rpm như Haiku dự phòng của vai `small`, vì quota 10 RPM của tài khoản dùng chung với Memory |
| Dự phòng | `global.amazon.nova-2-lite-v1:0`, 18 rpm | Cơ chế dự phòng sẵn có: throttle, `AccessDenied`, lỗi tạm thời, hoặc phải chờ quá `rate_limit_max_wait_seconds` (20 s) ở cửa sổ tốc độ |
| Trần ngày | 2.000 lượt mỗi model | Bằng mức đang đặt. Bộ đếm ngày và cửa sổ tốc độ tính theo model id, nên Haiku của router dùng chung chỗ với Haiku của `small`. Trần lớn nhất theo model không đổi, nên bảng vận hành (`ops-dashboard.ts`, `ops.py`) không đổi |
| `prompt_cache` | Bật cho Haiku, tắt cho Nova | `cachePoint` sau schema tool và sau system, không đặt trong `messages` |
| `router_max_tokens` | 800 (`agent/src/yofina_agent/defaults.json`) | Lời gọi hợp lệ dài nhất đo được: 306 token ở QQ, 336 token ở lượt này. Câu chào chạm 400 ở QQ |
| `reject_truncated` | Bật cho router | Kết quả bị cắt ở trần token không được nhận dù vẫn khớp schema, mà được thử lại. Các vai khác giữ hành vi cũ |

Prompt cache với Claude Haiku 4.5 trên Bedrock nhận `cachePoint` ở `system`, `messages` và `tools`. Mỗi điểm cache cần tối thiểu 4.096 token, tối đa 4 điểm, TTL 5 phút hoặc 1 giờ ([Bedrock prompt caching](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html), truy cập 26/11/2026). Tiền tố của router là schema rồi system, khoảng 12.000 token, nên được cache. Phần đổi theo lượt nằm ở tin người dùng: `<ngay_hom_nay>`, `<hu_cua_vi>`, `<lich_su>`, `<cau_moi>`. Nova 2 Lite chỉ nhận `cachePoint` ở `system` và `messages`, nên tắt. Ở lượt đo, lời gọi đầu ghi 12.473 token vào cache, 23 lời gọi sau đều đọc cache (trung bình 11.953 token).

**IAM và thứ tự deploy.** `agent-stack.ts` dựng `InvokeConfiguredModels` từ tập model id của mọi vai. Tập này trước và sau giống nhau, đã kiểm bằng mã. Các stack khác (classify, forecast, ingest, roadmap-regen) đọc vai theo tên và không đọc vai `router`. SSM `/yofina/llm/*` đã được phép. Vì vậy không cần `cdk deploy`. Chỉ cần đóng lại Runtime (`uv run scripts/agent_deploy.py`), vì `llm_defaults.json` và mã router nằm trong gói đó. Nếu SSM `/yofina/llm/roles` đang có giá trị, giá trị đó chỉ thay các vai được nêu, vai `router` vẫn lấy mặc định. Ghi đè trần dùng `/yofina/llm/daily_cap_router`. Test tích hợp suy giảm (`tests/integration/test_degraded_live.py`, `test_agent_runtime.py`) và `scripts/agent_run_local.py --cap-router` đã chặn cả vai này.

## Rà lời nhắc router (theo nguyên tắc, không theo câu trượt)

Đo cùng cách cho mọi bản: system cộng schema (JSON có khoảng trắng). Phần rà đưa tổng từ 20.110 xuống 19.871 ký tự. Trường mới `spend_jar_named` (mục "Đường lùi") đưa tổng lên 20.178 ký tự, và lượt đo chạy trên bản này. Số 19.142 của QQ đếm theo cách khác.

| Thay đổi | Lý do |
|---|---|
| Câu mở đầu nêu ngoại lệ reply của chitchat. Bỏ câu "trường chép chữ…/trường mã…" | Mâu thuẫn: câu cũ "Không trả lời nội dung" đi ngược với reply. Câu bỏ đi lặp lại mô tả của `params` trong schema |
| Nghĩa của bốn thẻ trong tin người dùng, ba nhãn dòng của lịch sử, và việc nội dung thẻ là dữ liệu được gom vào một đoạn đứng trước danh sách ý định | Trước đây các ý này nằm sai chỗ, rải ở quy tắc loại chi, quy tắc lộ trình, quy tắc câu trả lời và dòng cuối. `<ngay_hom_nay>` chỉ được giải thích trong quy tắc lộ trình |
| Quy tắc `tx_type`/`spend_jar_code` và quy tắc `answers_pending` chỉ còn trỏ tới mô tả của trường | Lặp: nghĩa của các trường này đã nằm ở mô tả trường từ `7c83d36`, quy tắc cũ định nghĩa lại lần hai |
| Nghĩa của `jar_text` nằm ở mô tả trường, thêm "hũ được hỏi (lookup)". Quy tắc hệ thống chỉ còn `from_jar_text`/`to_jar_text` | Mô tả cũ thiếu cách dùng ở lookup. Phần còn lại lặp |
| Bỏ câu mẫu trong quy tắc mục tiêu lộ trình | Câu mẫu chép lời người dùng, trái quy tắc "không câu mẫu" |
| Phần hỏi lại: bỏ chỉ dẫn hỏi `funding_source`, nêu đúng các ô mà mã dùng câu hỏi của router (`amount`, `jar` khi chuyển hũ, `other`), thêm "hũ trả không phải lý do hỏi lại" | Mâu thuẫn với mã: `clarify.resolve_clarify` luôn thay câu hỏi đó bằng một câu hỏi hũ trả chung (V4). Router lại có `spend_jar_code` để tự chọn hũ |
| `reply` giới hạn một hoặc hai câu, tối đa 400 ký tự (bằng `maxLength` của schema). Câu hỏi "làm được gì" để `reply` null | Câu chào của QQ chạm trần token. Danh sách việc làm được là dữ liệu sản phẩm (`notices.CAN_DO`, writer viết), router không có danh sách đó |
| `days_back` chuyển về nhóm tham số. `reply` và `confidence` thành nhóm "Trường ngoài params" | Chỉ dẫn đặt sai chỗ: các dòng này từng nằm dưới phần hỏi lại |
| Mô tả đặc tả ngày: `start_of`/`end_of` chỉ nhận `period` (bắt buộc) và `period_offset`, không nhận `day`, `month`, `year` | Mơ hồ: câu cũ chỉ nói "cần period". Model thêm `month` thì `dates.parse_spec` báo `PARAMS_INVALID` |
| Số tiền dạng "45 nghìn": không đổi lời nhắc | Lời nhắc không sai. "45 nghin" đọc thành 450.000 là lỗi của Nova, Haiku đọc đúng 19/19 ở cả hai lượt. Việc này để mã kiểm (mục dưới) |
| `jar_text` ghi tên hũ model đã chọn: không ép thêm chữ | Xử lý bằng dữ liệu: trường `spend_jar_named` (mục dưới) |

## Đường lùi của harness

Model quyết phần theo nghĩa. Mã kiểm phần kiểm được bằng dữ liệu. `router.checked_route` chạy trong `route()`, nên lượt chat và eval thấy cùng một kết quả.

| Router trả | Mã làm | Test |
|---|---|---|
| `spend_jar_code` ngoài danh sách hũ, hũ hệ thống, tên thay cho mã, hoặc không phải chuỗi | Coi như null. Lùi về loại chi, rồi hỏi một câu với chip là mọi hũ (đã có) | `test_router_spend_jar.py` |
| `jar_text` là tên hũ model chọn, kèm `spend_jar_named` false | Bỏ bản chép khi chữ đọc ra đúng hũ model chọn. Lượt hiện "Tính theo hũ X". Cờ true hoặc trống, hoặc chữ chỉ hũ khác, thì giữ chữ như cũ (**mới**) | `test_router_harness.py` |
| Số tiền VND không có trong hội thoại | Lấy số duy nhất mã đọc được ở câu mới. Câu có nhiều số thì bỏ và hỏi đúng một câu. Không đọc được số nào (số viết bằng chữ) thì giữ (**mới**) | `test_router_harness.py` |
| `keep_previous` khi Yofina không hỏi giữ hay bỏ | Bỏ cờ. What-if hỏi một câu, không gộp ngầm (**mới**, thấy ở lượt đo) | `test_router_harness.py`, `test_whatif_bundle.py` |
| `date_spec` sai dạng, ngày đã qua, năm Tết ngoài bảng, chưa khai ngày lương | Hỏi hạn đúng một câu, có lời của phép tính đứng trước, chip là ngày mã đọc được (đã có). Đặc tả không phải đối tượng thì bỏ, lùi về cách đọc trọn cụm bằng mã | `test_goal_date.py` |
| `answers_pending` sai kiểu hoặc trống | Không ghép (chip vẫn ghép). Cờ true sai trên yêu cầu ghi mới thì ô router đọc từ câu mới vẫn thắng, và vẫn chỉ ra khối xác nhận | `test_clarify_merge.py`, `test_router_harness.py` |
| `memory_action` ngoài hai giá trị | Lùi về cách đoán bằng chữ (đã có). Giá trị hợp lệ nhưng sai nghĩa: xem "Giới hạn đã biết" | `test_memory.py` |
| JSON sai schema, hoặc bị cắt ở trần token (**mới**) cả hai lần | `StructuredOutputError`, rồi luật dự phòng, rồi khối `notice` suy giảm bằng chuỗi sản phẩm, không lộ mã lỗi thô | `test_turn.py`, `test_router_harness.py` |

## Đo

Script: `C:\moMo-wt\logs\RT\scripts\measure.py`, chép từ script của QQ. Script dùng `load_settings` thật (vai `router`) và `router_max_tokens` thật. Bộ đếm ngày nằm trong bộ nhớ, không SSM, không Runtime, chỉ gọi Bedrock cho router. Hai câu cách nhau 8,5 s để Haiku không chạm cửa sổ 8 lượt/phút. Mỗi câu chạy một lần. Trần riêng của lượt là 0,15 USD. Ước tính in trước là 0,085 USD, thực tế tiêu 0,0875 USD qua 24 lời gọi. Độ trễ lấy theo `metrics.latencyMs` của Bedrock, như QQ. Đầu ra thô nằm ở `C:\moMo-wt\logs\RT\raw\rt_router.jsonl`, `report_rt_router.json` và `replay_final_harness.json`, ngoài repo.

Cột "model" chấm đầu ra thô của lời gọi được nhận. Cột "harness" chấm kết quả sau `checked_route` và sau `merge_pending` với câu đang chờ đọc từ lịch sử. Lượt đo chạy trước commit sửa `keep_previous`. Phát lại đầu ra thô qua harness cuối cho cùng điểm, chỉ khác `keep_previous` của C2 bị bỏ.

| | Nova gốc (QQ) | Nova bản sửa (QQ) | Haiku bản sửa (QQ, cache) | Router RT: model | Router RT: harness |
|---|---|---|---|---|---|
| intent | 23/24 | 23/24 | 24/24 | 24/24 | 24/24 |
| spend_jar_code | 2/8 | 3/8 | 8/8 | 6/8 | 6/8 (hũ cuối của lượt: 7/8) |
| answers_pending | 0/4 | 0/4 | 3/4 | 2/4 | 2/4 |
| date_spec (tính ra đúng ngày) | 0/7 | 0/7 | 6/7 | 7/7 | 7/7 |
| amount_vnd | 18/19 | 18/19 | 19/19 | 19/19 | 19/19 |
| jar_text | 9/11 | 9/11 | 8/11 | 8/11 | 10/11 |
| Câu đúng mọi trường | 8/24 | 8/24 | 19/24 | 17/24 | 19/24 |
| Có dấu / không dấu | 4/12, 4/12 | 4/12, 4/12 | 10/12, 9/12 | 8/12, 9/12 | 8/12, 11/12 |
| JSON hợp lệ ngay lần đầu | 24/24 | 24/24 | 23/24 | 24/24 | |
| Lời gọi bị cắt ở trần token | 0 | 0 | 2/25 (trần 400) | 0/24 (trần 800) | |
| p50 / p95 (ms) | 1014 / 1389 | 989 / 1479 | 1467 / 4076 | 1362 / 3247 | |
| Token vào / ra mỗi lượt | 6746 / 116 | 7034 / 91 | 13532 / 229 | 13230 / 209 (ra tối đa 336) | |
| USD/lượt có cache | 0,0032 | 0,0032 | 0,0038 | 0,00365 (0,00304 khi cache đã nóng) | |
| USD/lượt không cache | 0,0032 | 0,0032 | 0,0147 | 0,01427 | |

"Hũ cuối của lượt" tính bằng `clarify.infer_pay_jar` và `resolve_clarify`, chạy offline trên kết quả harness. S1 đến S5 và S7 ra đúng hũ. Ở S4, hũ suy từ loại chi `entertainment` ra Giải trí. S6 hỏi một câu. S8 hỏi một câu, đúng như mong đợi vì câu không nói tiền dùng vào việc gì.

### Câu còn trượt và phân loại

| Câu | Trượt | Phân loại | Lượt xử lý thế nào |
|---|---|---|---|
| S4 (vé concert, what-if) | `spend_jar_code` null, router tự hỏi hũ | Do model | Mã bỏ câu hỏi của router. Hũ suy từ loại chi `entertainment` ra Giải trí, lượt hiện "Tính theo hũ Giải trí" |
| S6 (Đà Lạt, ví có Quỹ Đà Lạt) | `spend_jar_code` null, router tự hỏi hũ | Do model (coi Du lịch và Quỹ Đà Lạt hợp ngang nhau) | Hỏi đúng một câu (`PAY_QUESTION`), chip là mọi hũ cộng Trả sau |
| S7 (người dùng nêu hũ Chi hằng ngày) | `jar_text` null dù `spend_jar_named` true | Do model | Tính đúng hũ Chi hằng ngày theo `spend_jar_code`. Lượt hiện thêm dòng "Tính theo hũ Chi hằng ngày", thừa nhưng không sai |
| C3 (yêu cầu mới ngắn sau câu hỏi số tiền) | `answers_pending` null thay vì false | Do model | Cờ trống nên không ghép, lượt tra số dư đúng |
| C4 (trả lời hạn "trước Tết năm 2027") | `answers_pending` null | Do model | Router tự ghép đủ: lập mới, 8 triệu có trong lịch sử, đặc tả hạn đúng. Mã bỏ câu hỏi hũ router đặt cho lộ trình, handler lộ trình hỏi hũ của mục tiêu |
| S1, C1 | `jar_text` của model (S1 ghi tên hũ đã chọn, C1 không chép chữ) | Do model, harness đã sửa | S1: `spend_jar_named` false nên mã bỏ bản chép, lượt hiện "Tính theo hũ Du lịch". C1: `merge_pending` đọc "giai tri" từ câu trả lời |
| C2 (trả lời "tầm 2 triệu rưỡi") | Không trượt theo điểm. Model đặt `keep_previous` true, harness mang `jar_text` "ra" | Do harness | `keep_previous`: đã sửa (commit `5831f6c`). `jar_text` "ra": `fallback._jar_phrase` đọc "các hũ ra sao" của câu đang chờ thành hũ "ra", nên lượt sẽ hỏi về hũ "ra". Chưa sửa vì `fallback.py` ngoài phạm vi được giao, xem "Giới hạn đã biết" |

So với QQ, `spend_jar_code` giảm từ 8/8 xuống 6/8 (S4, S6) và `answers_pending` từ 3/4 xuống 2/4 (C4). Không đo lại để tìm nguyên nhân, theo quy tắc không lặp sửa rồi đo. Mỗi câu chạy một lần nên lệch 1 đến 2 câu có thể là nhiễu. Cũng có thể do lời nhắc hệ thống không còn nhắc lại nghĩa của hai trường này (mục "Giới hạn đã biết"). `date_spec` tăng từ 6/7 lên 7/7: D1 "hai tháng nữa" nay là `today` cộng 2 tháng.

## Giới hạn đã biết

- **Chưa tách được nhiễu với ảnh hưởng của việc bỏ chỗ lặp** ở S4, S6 (`spend_jar_code`) và C4 (`answers_pending`). Muốn kiểm thì đo riêng ba câu, mỗi câu vài lần, ở bản có và bản không có câu nhắc lại trong lời nhắc hệ thống (khoảng 0,02 USD). Harness đã xử lý an toàn cả ba câu.
- **`fallback._jar_phrase` đọc "các hũ ra sao" thành hũ "ra"** khi mã đọc lại câu đang chờ (`router._code_params`). Câu trả lời cho câu hỏi số tiền vì vậy mang `jar_text` "ra", và lượt hỏi về một hũ người dùng không hề nêu. Đó vẫn là một câu hỏi và không ghi gì, nhưng là câu hỏi sai. Cần sửa ở `fallback.py`: không coi chữ sau "các hũ" là tên hũ.
- **`memory_action` hợp lệ nhưng sai nghĩa** không kiểm được bằng dữ liệu. Câu hỏi bị xếp "state" thì lượt trả lời "đã ghi nhận" và gửi câu đó vào AgentCore Memory. Bước trích xuất (Haiku, chỉ lấy lời khẳng định) là lớp chặn thứ hai. Hai câu M1, M2 đúng ở cả hai lượt.
- **Chờ tốc độ.** Cửa sổ 8 lượt/phút của Haiku đầy thì router chờ tới 20 s (`rate_limit_max_wait_seconds`, dùng chung mọi vai) rồi mới rơi về Nova. Bộ đếm này theo từng tiến trình, nên nhiều microVM có thể cùng vượt quota 10 RPM của tài khoản. Khi đó Bedrock throttle và router rơi về Nova ngay. Chưa đo trên Runtime.
- **Chi phí.** Không cache, một lượt đắt gấp 4,5 lần Nova (0,0143 so với 0,0032 USD). Cache chỉ giữ 5 phút. Lượt đầu sau khi cache nguội ghi lại khoảng 12.500 token (0,0176 USD). Đi qua suy luận liên vùng (`global.`) thì có thể ghi cache nhiều hơn.
- **Vai khác chưa bật `reject_truncated`.** Vai nạp ảnh và vai phân loại vẫn nhận kết quả bị cắt nếu kết quả đó khớp schema. Cần đo riêng trước khi bật.
- Mô tả đặc tả ngày dùng chung với Orchestrator và planner lộ trình (Sonnet). Câu sửa về `start_of`/`end_of` chưa được đo ở hai vai đó.
- Kết quả trên chỉ là 24 câu, mỗi câu một lần, chưa phải eval. Lượt eval cuối (#34) sẽ đo trên Runtime.
