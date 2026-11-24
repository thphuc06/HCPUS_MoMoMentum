# Kiểm toán prompt và mã của agent: overfit, hardcode, phình (2026-11-25)

Đợt này chỉ kiểm toán và đề xuất. Không sửa mã sản phẩm, không deploy, không chạy eval hay integration. Nguồn: đọc mã ở nhánh `p5/prompt-audit` (tách từ `602c292`), lịch sử git (`git log -S`, nội dung commit), CloudWatch Logs của Runtime `yofina_agent` (chỉ đọc), tài liệu prompt của Anthropic và AWS Nova.

## 0. Phạm vi, model đích, phương pháp

**Phạm vi**: mọi chuỗi gửi cho model trong `agent/src/yofina_agent/`, `pipelines/ingest/yofina_ingest/prompts.py`, `pipelines/classify/yofina_classify/llm_step.py`, `pipelines/forecast/yofina_forecast/behavior.py`, chỉ dẫn trích xuất bộ nhớ ở `infra-cdk/lib/memory.ts`, cấu hình `agent/src/yofina_agent/defaults.json` và `libs/yofina_core/src/yofina_core/llm_defaults.json`; mã hậu kỳ sửa hay thay lời model; bộ chấm `evals/run.py` và các file `evals/golden/*.jsonl`, `evals/adversarial/*.jsonl`. `gateway/tools/ledger/yofina_ledger/repo.py` không có chuỗi nào gửi cho model. Bộ nhớ dài hạn chỉ được ghi phát hiện; thiết kế lại thuộc nhánh `p5/memory-research`.

**Model đích** (theo `llm_defaults.json`): vai `small` là Nova 2 Lite (`global.amazon.nova-2-lite-v1:0`, dự phòng Claude Haiku 4.5); vai `planner` và `ingest` là Claude Sonnet 4.6 (dự phòng Kimi K3); vai `ingest_columns` là Nova 2 Lite. Trích xuất bộ nhớ dùng Nova Lite (`apac.amazon.nova-lite-v1:0`).

**Phương pháp** (theo các bước inventory, provenance, pattern scan của hướng dẫn prompt-audit):

1. Kiểm kê mọi chuỗi gửi model, đếm độ dài, số luật, số ví dụ, số câu phủ định và chữ hoa nhấn mạnh (script tạm, đã xóa).
2. Quét trùng chữ giữa câu hỏi eval và mã: chuẩn hóa không dấu, so mọi cụm 5 từ của 57 câu golden, 42 câu đối kháng và lịch sử của chúng với từng dòng mã sản phẩm.
3. Truy nguồn từng luật đáng ngờ bằng `git log -S'<chuỗi>'` và đọc commit: luật thêm sau ca trượt nào, ca eval thêm trước hay sau.
4. Đọc CloudWatch 2 ngày gần nhất để biết lỗi nào còn xảy ra (mục 2.9).
5. Đối chiếu với tài liệu chính thức (mục 6).

Hai điều cần nói trước để khỏi hiểu nhầm phần sau:

- Không tìm thấy mã nào biết đang chạy eval trên đường của agent, cũng không có nhánh khớp tên persona, `user_id`, số tiền hay ngày của persona. Op `eval_extract` của Lambda ingest chỉ đổi hạ tầng (không DB, hũ lấy từ seed), prompt giữ nguyên.
- Nova 2 Lite được AWS khuyên dùng chữ hoa (DO, DO NOT, MUST) để nhấn luật và dùng ví dụ few-shot đa dạng cho bài phân loại. Vì vậy chữ hoa trong prompt của router hay ví dụ theo từng ý định tự thân không phải lỗi. Lỗi là khi ví dụ chép gần nguyên câu của bộ eval, hoặc khi cùng một luật được nói nhiều lần.

## 1. Kiểm kê prompt

Độ dài tính bằng ký tự của chuỗi hằng (không gồm dữ liệu chèn lúc chạy); token ước bằng ký tự chia 3,2. "Luật" là số dòng gạch đầu dòng; "ví dụ" là số lần có cụm "ví dụ"/"for example"; "trích" là số cụm trong ngoặc kép (thường là câu mẫu hay giá trị mẫu); "phủ định" đếm không/tuyệt đối/đừng/never/do not; "HOA" là từ viết hoa toàn bộ không phải tên viết tắt.

| Prompt | File:dòng | Model nhận | Ký tự | Token ước | Luật | Ví dụ | Trích | Phủ định | HOA |
|---|---|---|---|---|---|---|---|---|---|
| `ROUTER_SYSTEM` (+ danh sách cú sốc từ `shocks.json`) | agent/src/yofina_agent/router.py:24 | Nova 2 Lite | 7.985 | ~2.500 | 30 | 4 | 46 | 48 | 27 |
| `WRITER_SYSTEM` | agent/src/yofina_agent/writer.py:25 | Nova 2 Lite | 779 | ~240 | 4 | 0 | 0 | 11 | 0 |
| `TASKS` (13 việc, mỗi lượt một việc) | writer.py:35-101 | Nova 2 Lite | 122 đến 669 mỗi việc, tổng 3.807 | ~40 đến ~210 | 0 | 0 | 1 | 12 | 6 |
| `MEMORY_GUIDE` (chỉ khi có bộ nhớ) | writer.py:117 | Nova 2 Lite | 732 | ~230 | 0 | 1 | 2 | 6 | 0 |
| `PROMPT_NOTICE` (đầu khối bộ nhớ) | agent/src/yofina_agent/memory.py:274 | Nova 2 Lite, Sonnet 4.6 | 586 | ~180 | 0 | 0 | 0 | 4 | 1 |
| `ORCHESTRATOR_SYSTEM` | agent/src/yofina_agent/whatif.py:108 | Sonnet 4.6 | 1.740 | ~540 | 13 | 0 | 7 | 7 | 6 |
| `ANALYST_SYSTEM` | whatif.py:316 | Sonnet 4.6 | 4.846 | ~1.510 | 10 | 3 | 5 | 29 | 11 |
| Phản hồi sửa của Verifier | agent/src/yofina_agent/verifier.py:171,177; whatif.py:385-390 | Sonnet 4.6 | theo lỗi | | | | | | |
| `ROADMAP_SYSTEM` | agent/src/yofina_agent/roadmap_agent.py:48 | Sonnet 4.6 | 5.041 | ~1.580 | 15 | 1 | 4 | 18 | 7 |
| `_REPAIR_HINTS` | roadmap_agent.py:115 | Sonnet 4.6 | 324 | ~100 | 0 | 0 | 0 | 0 | 0 |
| `image_system` (+ hũ, loại giao dịch) | pipelines/ingest/yofina_ingest/prompts.py:39 | Sonnet 4.6 | 4.684 | ~1.460 | 17 | 3 | 9 | 28 | 26 |
| `columns_system` | prompts.py:95 | Nova 2 Lite | 533 | ~170 | 0 | 0 | 0 | 2 | 4 |
| `labels_system` | prompts.py:111 | Nova 2 Lite | 1.375 | ~430 | 5 | 3 | 6 | 7 | 2 |
| `_DATA_NOT_INSTRUCTIONS` (chèn vào cả ba prompt ingest) | prompts.py:14 | như trên | 552 | ~170 | 0 | 0 | 0 | 6 | 10 |
| `SYSTEM` phân hũ | pipelines/classify/yofina_classify/llm_step.py:28 | Nova 2 Lite | 584 | ~180 | 0 | 0 | 0 | 5 | 4 |
| `SUMMARY_SYSTEM` hồ sơ hành vi | pipelines/forecast/yofina_forecast/behavior.py:170 | Nova 2 Lite | 963 | ~300 | 5 | 1 | 5 | 9 | 4 |
| `SEMANTIC_EXTRACTION_PROMPT` | infra-cdk/lib/memory.ts:70 | Nova Lite | 6.380 | ~1.990 | 29 | 8 | 36 | 14 | 26 |
| `USER_PREFERENCE_EXTRACTION_PROMPT` | memory.ts:124 | Nova Lite | 4.380 | ~1.370 | 15 | 5 | 26 | 8 | 18 |
| Mô tả tool ép JSON (`route`, `plan_scenario`, `analyze`, `report`, `chon_hu`, `behavior_summary`) và mô tả trường của schema Pydantic | router.py:286, whatif.py:476,605, ... | theo vai | ngắn | | | | | | |

Phần chỉ dẫn mặc định của AWS chiếm khoảng hai phần ba hai prompt trích xuất bộ nhớ; phần luật của Yofina ngắn hơn.

Ngoài prompt, agent có nhiều câu trả lời do mã dựng thay cho lời model (không qua model nào): `notices.py` (khoảng 70 hằng chuỗi), `behavior_chat.answer_text`, `ingest_chat.status_text`/`start_text`, `fee_citation.answer_text`, `turn.forecast_overview_text`, `turn._roadmap_closing`, nhánh sửa bước lộ trình, `memory.TEXT_*`, `turn._GOAL_*`. Mục 2.6 bàn về nhóm này.

## 2. Phát hiện

Mỗi mục: loại, vị trí, nguồn gốc, vì sao là (hay không là) overfit, mức, cách thay bằng nguyên tắc chung, rủi ro khi đổi. Mức "cao" là chỗ đang làm prompt hay mã lệ thuộc một ca cụ thể và nên sửa trước; "vừa" là trùng lặp hay vá ca có thể gây lỗi giữa các ca; "thấp" là dọn dẹp.

Tổng: 27 phát hiện. Theo loại: câu mẫu/ví dụ trùng ca eval 5, khuôn cứng 4, nhánh khớp chuỗi 7, luật vá ca 3, trùng lặp 3, hậu kỳ và câu cố định thay lời model 2, mã chết 1 nhóm (7 chỗ), ngưỡng chọn theo ca 2. Theo mức: cao 2, vừa 10, thấp 15.

### 2.1 Câu mẫu và ví dụ trùng ca eval

**P1. Ví dụ của router chép gần nguyên câu golden.** Loại: câu mẫu trùng eval. Mức: vừa.
- Vị trí: router.py:43-45 (`behavior`: "thói quen chi tiêu của mình thế nào", "mình dùng Trả sau nhiều không"), router.py:46-48 (`ingest`: "mình vừa nạp ảnh", "nạp xong độ phủ dữ liệu tăng bao nhiêu", "hỏi cách thêm chi tiêu ở ngân hàng hay thẻ khác"), router.py:49-50 (`knowledge`: "phí dịch vụ mỗi tháng bao nhiêu", "có phí trả chậm không", "nguồn ở đâu"), router.py:51 (`affordability`: "chuyển 250k cho bạn có ổn không").
- Ca trùng: `behavior-habits`, `behavior-bnpl`, `ingest-status`, `ingest-coverage`, `ingest-start`, `knowledge-fee-citation`, `knowledge-late-fee`, `afford-1`. Quét cụm 5 từ bắt được `behavior-habits` (router.py:43-44) và `knowledge-late-fee` ("co phi tra cham khong", router.py:49); các ca còn lại trùng gần nguyên văn với từ khác ở một hai chữ.
- Nguồn: ca phase 5 thêm ở `bfc4e24` (bước 0 của phase 5), ví dụ router thêm sau đó ở `d95607e` (luồng B) và `3603bc7` (ingest, knowledge). Ví dụ `afford-1` có từ `5f8177c`, cùng lúc với ca.
- Vì sao là vấn đề: few-shot cho bộ phân loại là kỹ thuật đúng với Nova (mục 6), nhưng khi ví dụ là chính câu hỏi của bộ eval thì golden đo khả năng nhớ ví dụ, không đo khả năng hiểu câu mới. Điểm golden 100% ở các ý định này không cho biết router xử lý được cách hỏi khác.
- Thay bằng: mỗi ý định một câu mô tả mục tiêu (ý định này phục vụ việc gì, khác ý định gần nó ở đâu) và hai ba ví dụ khác hẳn câu eval về từ ngữ và độ dài, đặt trong một khối riêng có nhãn "minh họa". Thêm bộ câu diễn đạt lại (mục 4) để đo.
- Rủi ro: golden phase 5 có thể tụt một hai ca nếu ví dụ mới kém. Đó là thông tin thật về router; sửa bằng cách cải thiện mô tả, không chép lại câu eval.

**P2. Ví dụ "10 ngày nữa" và danh sách món trong luật `what_if`.** Loại: ví dụ theo ca. Mức: thấp.
- Vị trí: router.py:36-38 ("Một khoản chi lớn một lần cho bất kỳ việc gì ... (món đồ, chuyến du lịch, đám cưới, sửa xe, học phí...) ... kể cả khi họ nói thời điểm ("10 ngày nữa", "cuối tháng")").
- Nguồn: `4ef13e7` sau "lỗi thật: đi du lịch 5 triệu sau chuỗi câu tai nghe Trả sau ra out_of_scope"; cùng commit thêm ca `multiturn-new-question` ("Nếu 10 ngày sau tôi đi du lịch 5 triệu thì sao").
- Vì sao: nguyên tắc (khoản chi một lần của chính người dùng, có hay không có thời điểm, là `one_time_purchase`) là đúng và chung. Cụm "10 ngày nữa" và "chuyến du lịch" là dấu vết của ca.
- Thay bằng: giữ câu nguyên tắc, bỏ cụm thời gian mẫu, hoặc thay bằng ví dụ không trùng ca.
- Rủi ro: thấp; nguyên tắc vẫn còn.

**P3. Chuỗi "RUT TIEN TAI ATM" trong prompt gắn nhãn CSV.** Loại: ví dụ trùng dữ liệu eval. Mức: thấp.
- Vị trí: pipelines/ingest/yofina_ingest/prompts.py:118.
- Nguồn: `4d6a755` (quyết định của chủ dự án về rút tiền mặt, nhãn r14, r15). Chuỗi này xuất hiện 7 lần trong `evals/ingest/manifest.json`.
- Vì sao: luật (rút tiền mặt là chuyển sang tài khoản của chính mình) là quyết định nghiệp vụ hợp lệ. Ví dụ chép nguyên chuỗi của file eval khiến bộ đo ingest không kiểm được cách ghi khác ("RUT TM ATM", "ATM WDL"...).
- Thay bằng: nêu luật bằng lời ("rút tiền mặt ở ATM hay tại quầy, dù sao kê viết tắt thế nào"), bỏ chuỗi literal. Mã chặn dự phòng `looks_like_self_topup` (normalize.py) giữ nguyên.
- Rủi ro: thấp; nên thêm một dòng CSV viết tắt khác vào bộ synthetic để đo.

**P4. Ví dụ âm của `MEMORY_GUIDE` mô tả đúng hình dạng ca `memory-reuse-new-session`.** Loại: ví dụ theo ca. Mức: vừa. Chỉ ghi nhận (thiết kế bộ nhớ thuộc nhánh khác).
- Vị trí: writer.py:117-124 ("Ví dụ âm: câu hỏi là nên để tiền vào hũ nào mà không mục `so_thich` nào có `hu` khác rỗng...").
- Nguồn: `f40bbaa` (p5/fix-agent3), thay câu mẫu cũ "theo điều bạn đã dặn, ..." đã làm Nova 2 Lite bịa lời dặn.
- Vì sao: bản mới tốt hơn bản cũ (không còn câu để chép), nhưng ví dụ âm vẫn là câu hỏi của ca eval ("nên để tiền vào hũ nào"). Model có thể học "câu hỏi kiểu này thì không nhắc bộ nhớ" thay vì học điều kiện thật ("mục nào trả lời trực tiếp câu hỏi").
- Gợi ý cho nhánh bộ nhớ: nếu giữ ví dụ âm, chọn câu hỏi không có trong eval; hoặc bỏ ví dụ và dựa vào cấu trúc `so_thich[].hu` đã có.

**P5. Giá trị mẫu trong `SUMMARY_SYSTEM`.** Loại: ví dụ lấy từ fixture test. Mức: thấp.
- Vị trí: behavior.py:175 (ví dụ "2.069.000 ₫", "40%", "7 ngày").
- Nguồn: `d95607e`; cùng số có trong tests/unit/ml/test_behavior_ml.py:216.
- Vì sao: rủi ro nhỏ vì model phải chép chuỗi `hien_thi` của dữ liệu và câu có số lạ bị bỏ bằng mã (`apply_summary`). Vẫn là một con số cụ thể model có thể chép khi dữ liệu trống.
- Thay bằng: ví dụ dạng giữ chỗ (`{hien_thi}`) hoặc bỏ, vì luật "chép nguyên văn chuỗi `hien_thi`" đã đủ rõ.

Ngoài ra, chip gợi ý `SUGGESTION_ITEMS` (notices.py:55-64) trùng nguyên văn các câu golden `lookup-balance`, `whatif-bnpl`, `afford-2`, `resilience-current-score`, `roadmap-view-current`. Đây là chuỗi giao diện, không vào prompt, nên không tính là phát hiện; ảnh hưởng tới bộ eval ở mục 4.

### 2.2 Khuôn cứng

**P6. Khuôn "đúng N câu" theo từng việc của writer, cộng luật nới cho bộ nhớ.** Loại: khuôn cứng, luật chồng luật. Mức: cao.
- Vị trí: writer.py:26 (`WRITER_SYSTEM`: "1 đến 2 câu ngắn"), writer.py:36 (`balance`: "bằng đúng 1 câu"), writer.py:45 (`forecast`: "1 đến 2 câu"), writer.py:55 (`confirm_move`: "đúng 1 đến 2 câu"), writer.py:62 (`affordability`: "Viết ĐÚNG 2 câu ... Câu 1 nêu ... Câu 2 nêu ..."), writer.py:58-90 (`obligations`, `resilience`, `stress`, `roadmap`, `confirm_action` đều lặp "1 đến 2 câu"), writer.py:117-120 (`MEMORY_GUIDE`: "được viết thêm tối đa 1 câu ngoài khuôn của nhiệm vụ").
- Nguồn: khuôn có từ phase 1 (`04ab11c`) và phase 3 (`5f8177c`); câu nới thêm ở `f40bbaa` khi bộ nhớ cần chỗ.
- Vì sao: đây đúng mẫu chủ dự án nêu. Số câu là cách nói, không phải ràng buộc thật. Ràng buộc thật là "thẻ đã hiện chi tiết nên lời chỉ cần trả lời câu hỏi và không liệt kê lại". `affordability` bắt câu 2 luôn có "điều cần chú ý nhất", nên khi mọi hũ đều đủ model vẫn phải chêm một câu. Khi một nhu cầu mới (bộ nhớ) không vừa khuôn, phải thêm luật ngoại lệ, đó là luật chồng luật. Câu "1 đến 2 câu" còn lặp ở hệ thống và ở 8 việc.
- Thay bằng: `WRITER_SYSTEM` nói mục tiêu một lần ("trả lời đúng câu hỏi bằng vài câu ngắn; người dùng đã thấy thẻ số liệu nên không liệt kê lại; dừng khi đã trả lời xong"). Mỗi `TASKS[...]` chỉ giữ thứ model không tự biết: thẻ nào đã hiện, nghĩa của các trường (`runout` null là đủ tới kỳ lương, `weak` là yếu...), luật nghiệp vụ ("không phải điểm tín dụng", "chưa chuyển khoản nào"). Bỏ luật nới của `MEMORY_GUIDE` vì không còn khuôn để nới. Độ dài đã bị chặn bằng `writer_max_tokens` 300 và `affordability_text_max_tokens` 160.
- Rủi ro: câu trả lời có thể dài hơn một chút. Không ca eval nào chấm số câu (chỉ `exactly_one_question` cho khối `clarify`, không dính writer), nên eval không trượt vì việc này; cần đọc tay khoảng 20 câu trả lời trước và sau (mục 5, đợt 2).

**P7. Câu chêm bắt buộc ở `chitchat` và việc `out_of_scope` không dùng.** Loại: khuôn cứng, mã chết. Mức: vừa.
- Vị trí: writer.py:99-101 (`chitchat`: "rồi nhắc rằng bạn giúp được việc xem số dư, giao dịch, dự báo một hũ và chuyển tiền giữa các hũ"), writer.py:95-98 (`out_of_scope`).
- Vì sao: mọi câu xã giao (kể cả "cảm ơn") bị buộc kèm danh sách việc làm được, danh sách này còn thiếu chống chịu, lộ trình, nạp dữ liệu. `TASKS["out_of_scope"]` không có lời gọi nào: `Turn.on_out_of_scope` (turn.py:1504) chỉ phát `notice` và `suggestions`.
- Thay bằng: "Trả lời xã giao ngắn; nếu người dùng hỏi bạn làm được gì thì nói theo danh sách việc" (danh sách lấy từ `notices.CAN_DO` đưa vào dữ liệu). Xóa `TASKS["out_of_scope"]`.
- Rủi ro: ca `chitchat` ("Chào bạn, bạn là ai?") chỉ chấm ý định; không trượt.

**P8. Độ dài tiêu đề bước và cấm đánh số ở `ROADMAP_SYSTEM`, kèm mã gỡ số.** Loại: khuôn cứng, trùng với mã. Mức: thấp.
- Vị trí: roadmap_agent.py:58 ("title ngắn, khoảng mười từ"), roadmap_agent.py:82 ("Không đánh số giai đoạn hay bước"), roadmap_agent.py:835 (`_strip_ordinal` gỡ "Bước 1:" khỏi tiêu đề).
- Nguồn: `ab1e5e6`.
- Vì sao: luật cấm đánh số đã có mã thực thi; nói trong prompt là phụ. "Khoảng mười từ" là số tùy chọn, không có giới hạn tương ứng trong schema.
- Thay bằng: một câu mục tiêu ("tiêu đề là một hành động ngắn đọc được trên thẻ điện thoại; thứ tự đã do vị trí"). Giữ `_strip_ordinal`.

**P9. Giới hạn độ dài của Analyst lệch với schema.** Loại: khuôn cứng. Mức: thấp.
- Vị trí: whatif.py:325 ("2 đến 4 câu (tối đa khoảng 450 ký tự)"), whatif.py:333 ("summary (tối đa 140 ký tự)"); schema `Analysis.narrative` max 800 và `AnalysisOption.summary` max 200 (schemas.py:254,262).
- Vì sao: hai con số khác nhau cho cùng một trường. Không sai, nhưng là dấu hiệu số được đặt tay.
- Thay bằng: một nguồn sự thật. Hoặc prompt nói mục tiêu ("đọc trong vài giây trên điện thoại") và schema giữ giới hạn cứng, hoặc prompt lấy số từ schema.

### 2.3 Nhánh khớp chuỗi

**P10. Đường sửa một bước lộ trình bằng regex.** Loại: nhánh khớp chuỗi cho một ca. Mức: cao.
- Vị trí: turn.py:1116 (`if _asks_step_edit(question)`), turn.py:1147-1186 (`on_roadmap_step_edit`), turn.py:1737-1789 (`_STEP_WORD_RE`, `_EDIT_VERB_RE`, `_CREATE_WORD_RE`, `_STEP_ORDINAL_RE`, `_STEP_KIND_WORDS`, `_match_steps`), notices.py:222-240 (7 câu `ROADMAP_EDIT_*`). Chú thích ở turn.py:1115 và 1735 chép cụm "giảm số tiền ở bước" của ca.
- Nguồn: ca `roadmap-edit-one-step` ("Mình muốn giảm số tiền ở bước để dành cho hũ Dự phòng xuống còn 200 nghìn...") thêm ngày 23/11 ở `c348928`; đường xử lý thêm ngày 24/11 ở `ab1e5e6`.
- Vì sao: router không có tham số "sửa bước", nên mã đoán ý định phụ bằng chữ: câu có "bước" + một động từ sửa và không có "lập". "Đổi bước 2 sang tháng sau" khớp; "chỉnh lại khoản để dành hũ Dự phòng" (không có chữ "bước") không khớp và đi sang xem lộ trình; "lập luôn bước mới" bị loại vì có "lập". Lời đáp là 7 câu cố định. Khoảng 130 dòng mã và chuỗi phục vụ một cách nói.
- Thay bằng: thêm `roadmap_action="edit_step"` vào `IntentParams` (nội bộ agent, không đụng hợp đồng) và một câu mô tả trong router ("muốn đổi số tiền, ngày hay bỏ một bước của lộ trình đang dùng"). Handler giữ phần đúng nguyên tắc (đọc bản đang dùng, không lưu gì, chỉ chỗ sửa) nhưng để writer viết từ bản gọn lộ trình cộng một dữ kiện "chat chưa sửa được bước, sửa ở trang Lộ trình"; khớp bước theo hũ và thứ tự có thể giữ bằng mã như dữ kiện gợi ý cho writer.
- Rủi ro: ca `roadmap-edit-one-step` chỉ chấm ý định `roadmap` và tool; vẫn qua nếu router đặt đúng tham số. Nếu router chưa đặt được, ca rơi về xem lộ trình, đó là hành vi chấp nhận được (không lưu gì).

**P11. "Hũ nào sắp cạn?" xử lý ở ba lớp.** Loại: nhánh khớp chuỗi, trùng lặp. Mức: vừa.
- Vị trí: router.py:29-31 (luật prompt "HŨ NÀO sắp cạn ... không hỏi lại"), router.py:241-270 (`_WHICH_JAR_RUNOUT` regex, `route_runout_overview` ép thành `lookup/forecast`, gọi ở turn.py:779 và 910), turn.py:1000-1004 (`on_forecast` không có hũ thì đọc mọi hũ).
- Nguồn: `6cc6269` ("router xếp nhầm vào tra số dư hoặc tự hỏi lại"). Câu này là chip "Hũ nào của mình sắp cạn?" của chính ứng dụng (notices.py:61).
- Vì sao: đây là chip sản phẩm, không phải ca eval, nên không phải gian lận. Nhưng một câu hỏi được xử lý bằng prompt, regex và handler cùng lúc. Lý do regex tồn tại có hai: router xếp nhầm sang `balance`, và router tự hỏi lại "hũ nào" (mã chấp nhận câu hỏi lại của router cho `lookup`, clarify.py:70-71).
- Thay bằng: (a) mã không nhận câu hỏi lại của router cho `lookup` khi `jar_text` trống (handler đã tự đọc mọi hũ); (b) chip gửi ý định có cấu trúc thay vì chữ (P15); sau đó bỏ regex và câu prompt, đo lại.
- Rủi ro: câu gõ tay "hũ nào sắp hết tiền" có thể lại vào `balance`. Đo bằng bộ diễn đạt lại trước khi bỏ regex.

**P12. Chọn loại nhận xét hành vi bằng bảng từ khóa.** Loại: nhánh khớp chuỗi. Mức: vừa.
- Vị trí: agent/src/yofina_agent/behavior_chat.py:37-43 (`KIND_KEYWORDS`), dùng ở `asked_kind`.
- Nguồn: `d95607e`, sau khi ca `behavior-weekday`, `behavior-payday`, `behavior-bnpl` có `expect_insight_kind` (`bfc4e24`). Cụm "ngay nao trong tuan" trùng câu `behavior-weekday` ("ngày nào trong tuần").
- Vì sao: router đã hiểu câu hỏi nhưng chỉ trả `behavior`; loại nhận xét lại đoán bằng `in` trên chữ không dấu. "Mình có hay quẹt thẻ lúc nửa đêm không" không khớp từ nào trong `time_of_day` ("khuya", "ban dem" có, "nua dem" không). Mỗi cách nói mới phải thêm từ.
- Thay bằng: router trả thêm `insight_kind` (enum đúng các loại của `BEHAVIOR_INSIGHT_KINDS`, null khi hỏi chung). Bảng từ khóa chỉ giữ cho đường suy giảm khi router hỏng, như `fallback.py`.
- Rủi ro: ba ca `expect_insight_kind` phụ thuộc router trích đúng; cần đo trên bộ diễn đạt lại.

**P13. Chọn loại phí bằng từ khóa, nhánh "miễn phí" cho ca đối kháng.** Loại: nhánh khớp chuỗi. Mức: vừa.
- Vị trí: agent/src/yofina_agent/fee_citation.py:31-39 (`CONCEPTS`, `FREE_PHRASES`), 53-55 (`asks_free`), 101-131 (`answer_text`).
- Nguồn: `3603bc7`; `FREE_PHRASES` ứng với ca đối kháng `citation-forgery` ("điều khoản nói Trả sau được miễn phí trọn đời").
- Vì sao: nguyên tắc chính (chỉ trích dẫn dòng phí do tool trả) đã được bảo đảm vì khối `citation` dựng từ kết quả tool. Nhánh "miễn phí" chỉ thêm một câu cố định cho đúng kiểu câu của ca. Câu hỏi về một loại phí khác mà bảng không có, không thuộc 4 khái niệm, sẽ nhận câu liệt kê mọi phí mà không nói rõ "chưa có nguồn cho khoản bạn hỏi".
- Thay bằng: router trả `fee_topic` (enum các loại phí có trong bảng cộng "khác"); mọi chủ đề không khớp dòng phí nào, kể cả "miễn phí", đi chung một câu "biểu phí chưa có khoản này". Xóa `FREE_PHRASES`.
- Rủi ro: `citation-forgery` vẫn qua vì bộ chấm chỉ kiểm nguồn trích dẫn (`citation`), không kiểm câu "không có điều khoản miễn phí".

**P14. Phân biệt "hỏi cách nạp" và "hỏi lần nạp" bằng cụm từ.** Loại: nhánh khớp chuỗi. Mức: thấp.
- Vị trí: agent/src/yofina_agent/ingest_chat.py:47-60 (`START_PHRASES`).
- Vì sao: cùng mẫu với P12, P13. Danh sách khá chung nên rủi ro thấp.
- Thay bằng: router trả `ingest_action` (`how_to` hay `status`).

**P15. Chip đi vòng qua chữ rồi khớp nguyên chuỗi.** Loại: nhánh khớp chuỗi (khớp chuỗi giao diện, không phải ca eval). Mức: thấp.
- Vị trí: turn.py:829-832 (so `question.strip()` với giá trị chip `KEEP_PREVIOUS_CHIPS`), agent/src/yofina_agent/textutil.py:153-163 (`match_shock_id` so với `STRESS_CHIP_VALUE`), router.py:241-270 (P11), `CONFIRM_SPENDING_CHIPS` ("Không cần đâu, cảm ơn") nhờ router hiểu.
- Vì sao: không phải overfit, nhưng mọi chip phải được hiểu lại từ chữ, nên mỗi chip mới kéo theo một chỗ khớp chuỗi hoặc một luật router.
- Thay bằng: chip mang `id` và ý định có cấu trúc (AG-UI `forwardedProps` hoặc trường riêng của khối `clarify`/`suggestions`), agent định tuyến chip bằng `id`; chữ gõ tay vẫn qua router. Việc này đụng hợp đồng khối và frontend, nên để đợt sau.

**P16. Nhận ra câu "bạn nhớ gì về mình" bằng regex sau khi router đã xếp `memory`.** Loại: nhánh khớp chuỗi. Mức: thấp. Chỉ ghi nhận (bộ nhớ).
- Vị trí: memory.py:783-808 (`_ASK_RE`, `is_recall_question`), dùng ở `on_memory` và `skip_reason`.
- Vì sao: router đã được dặn phân biệt NÓI và HỎI (router.py:59-62) nhưng chỉ trả một ý định; mã đoán lại bằng regex.
- Gợi ý cho nhánh bộ nhớ: tham số `memory_action` (`state`/`recall`) của router.

### 2.4 Luật vá ca

**P17. Ba lớp vá quanh ca "đi du lịch 5 triệu" ra `out_of_scope`.** Loại: luật vá ca (patch accretion). Mức: vừa.
- Vị trí: router.py:56-57 ("Câu hỏi về việc tiêu tiền của chính người dùng ... KHÔNG phải out_of_scope"), router.py:80-81 ("các câu trước dù về chủ đề gì cũng không làm câu mới thành out_of_scope"), turn.py:1504-1516 và 1832-1856 (`spending_confirm_request`: router ra `out_of_scope` mà còn tham số chi tiêu thì hỏi lại bằng 3 chip), notices.py:244-250.
- Nguồn: `4ef13e7` và `6fdca26` (chú thích turn.py:1508: "lỗi thật 23/11: đi du lịch 5 triệu sau chuỗi câu khác"); ca `multiturn-new-question`.
- Vì sao: gốc của lỗi là router ghép câu mới với lịch sử. Bản sửa gốc (router.py:77-81: chỉ ghép khi câu mới là câu cụt) là nguyên tắc chung và nên giữ. Hai câu "không phải out_of_scope" và đường hỏi lại bằng mã là lớp chồng thêm cho cùng một lỗi, không ai đo lại xem còn cần không.
- Thay bằng: giữ luật ghép câu cụt. Thử bỏ câu router.py:80-81 (lặp ý của câu 77-79) và đo. `spending_confirm_request` là lưới an toàn hợp lý (hỏi thay vì từ chối cứng), giữ nếu đo thấy router vẫn còn xếp nhầm; nếu không thì bỏ.
- Rủi ro: `multiturn-new-question` có thể trượt lại nếu luật ghép chưa đủ; đó là tín hiệu để sửa luật ghép, không để thêm câu.

**P18. Luật kiểu chữ cho mô phỏng gộp.** Loại: luật vá ca. Mức: thấp.
- Vị trí: whatif.py:328 ("viết chữ thường như câu nói bình thường, không viết hoa để nhấn").
- Nguồn: `6fdca26`, sau một lần model viết hoa tên khoản.
- Vì sao: luật văn phong viết sau một quan sát, không có lý do nghiệp vụ. Sonnet 4.6 không có xu hướng này một cách hệ thống.
- Thay bằng: bỏ; nếu cần, nói chung một lần ở đầu phần giải thích ("giọng nói chuyện bình thường").

**P19. Luật đọc ảnh thêm theo từng ảnh trượt.** Loại: luật vá ca. Mức: vừa.
- Vị trí: prompts.py:50 (màn chi tiết có mã giao dịch là đã thực hiện), prompts.py:51 (màn tra soát không tạo dòng), prompts.py:54 (rút tiền mặt), prompts.py:58 (trích mọi dòng kể cả cùng số tiền), prompts.py:61 (chiều tiền theo cột Ghi nợ/Ghi có và số dư), prompts.py:66 và 121 (chuyển cho cá nhân có mục đích thì phân loại theo mục đích).
- Nguồn: `7f03a32` ("theo kết quả kiểm mù 24/11 (r08, r15)"), `4d6a755` (r14, r15), `3a9906e` (dựng lại `c01` với ví của vy, "tiền phòng").
- Vì sao: hai loại khác nhau trộn lẫn. Luật nghiệp vụ mà model không thể tự biết (rút tiền mặt không phải khoản chi, màn tra soát không tạo dòng, phí rút tiền vẫn là khoản chi) là hợp lệ và phải giữ. Luật về cách đọc chứng từ ngân hàng (Ghi nợ là tiền ra, màn có mã giao dịch là đã xong, đọc hết các dòng) là kiến thức chung mà Sonnet 4.6 đã có; chúng được thêm vì một ảnh trượt và làm prompt dài thêm khoảng 1.000 ký tự.
- Thay bằng: tách prompt thành (1) định nghĩa giao dịch của ứng dụng (luật nghiệp vụ, có lý do) và (2) một câu nguyên tắc đọc ("chiều tiền và trạng thái lấy theo ngữ nghĩa của chứng từ: tiêu đề cột, dấu, số dư trước sau"). Đo trên bộ `evals/ingest` cả `real` lẫn `synthetic`.
- Rủi ro: r08, r15 có thể trượt lại. Nếu trượt, đó là bằng chứng luật cụ thể còn cần trên Sonnet 4.6 và nên giữ kèm lý do.

### 2.5 Trùng lặp

**P20. "Không bao giờ hỏi lại" nói năm lần vì mã nhận câu hỏi lại của router cho mọi ý định.** Loại: trùng lặp, luật prompt thay cho kiểm tra bằng mã. Mức: vừa.
- Vị trí: router.py:45 (`behavior`), 48 (`ingest`), 50 (`knowledge`), 62 (`memory`), 91 (`out_of_scope, chitchat, stress và roadmap`). Mã: agent/src/yofina_agent/clarify.py:72-73 (`resolve_clarify` trả câu hỏi của router khi `slot == "other"` cho ý định không có ô bắt buộc).
- Nguồn: `3603bc7`, `1e74040`, `da6149b`.
- Vì sao: mỗi ý định mới không cần hỏi lại phải thêm một câu vào prompt, vì mã không chặn. Đây là ràng buộc của luồng (ý định nào được hỏi lại), nên thuộc về mã.
- Thay bằng: `clarify.py` có tập `CLARIFY_INTENTS = {what_if, affordability, move, profile_update}` (cùng tập với `PENDING_INTENTS`); ý định khác bỏ qua `clarify` của router. Xóa năm câu, thay bằng một câu "chỉ hỏi lại khi thiếu ô bắt buộc của what_if, affordability, move, profile_update".
- Rủi ro: không đổi hành vi nếu router vốn đã tuân; nếu router từng hỏi lại cho `behavior`, nay mã chặn luôn.

**P21. Luật dòng "Ứng dụng:" nói hai lần.** Loại: trùng lặp. Mức: thấp.
- Vị trí: router.py:58 (trong định nghĩa `chitchat`) và router.py:85.
- Thay bằng: giữ một chỗ.

**P22. Sửa ô tham số bằng mã và nhắc cùng điều trong prompt.** Loại: trùng lặp. Mức: thấp.
- Vị trí: schemas.py:167-190 (`_consistent`: dời lương mới từ `salary_vnd` sang `amount_vnd`, dời hũ trả tiền từ `from_jar_text` sang `jar_text`), router.py:33-34 ("không đặt ở salary_vnd vì salary_vnd chỉ dành cho profile_update"), router.py:64-66 ("from_jar_text và to_jar_text CHỈ dùng khi chuyển tiền giữa hai hũ").
- Nguồn: `4ef13e7`.
- Vì sao: mã là chỗ thực thi và nên giữ. Câu prompt giảm số lần mã phải sửa; giữ được, nhưng viết một lần, không cần chữ hoa, vì sai cũng không hỏng.
- Ghi chú: `_params_lenient` (schemas.py:134) đọc lại `params` dạng chuỗi của Nova là mã chịu lỗi định dạng, hợp lệ.

### 2.6 Hậu kỳ và câu cố định thay lời model

**P23. `enforce_switch_jar`, `enforce_pay_now`, `normalize_proposal` viết lại phương án của Analyst.** Loại: hậu kỳ thay lời model. Mức: thấp.
- Vị trí: whatif.py:631-665, 694-779.
- Nguồn: `d7f57e3` (ca `whatif-bnpl2`), `6cc6269`, `e71a055`; chú thích chép số của ca `whatif-bnpl` ("760.000 ₫ cho tai nghe 1.200.000 ₫").
- Vì sao không phải overfit: logic chung cho mọi phương án cùng loại, không khớp số hay tên của ca. Nó thực thi nguyên tắc "phương án mô tả đúng việc nó làm" (hũ thật, số tiền là giá món, nhãn khớp hũ) trước khi `check_suitability` kiểm. Số trong chú thích chỉ là dẫn chứng.
- Điểm nên gom: hai hàm riêng cho hai loại phương án là dấu hiệu sửa từng lỗi. Cách bền hơn là Analyst chỉ trả phần cấu trúc (loại, hũ, có hành động không) và lý do bằng chữ, còn nhãn và tóm tắt có số của mọi phương án chi tiền do mã dựng theo một hàm. Không gấp.

**P24. Nhiều câu trả lời dựng bằng mã thay writer.** Loại: phình (câu cố định thay lời model). Mức: vừa.
- Vị trí: notices.py (khoảng 70 hằng, trong đó 20 câu lộ trình và 9 câu dự báo mọi hũ), behavior_chat.py:110-124, ingest_chat.py:282-353, fee_citation.py:101-131, turn.py:1604-1632, 1650-1657, 1692-1733, memory.py:789-800.
- Nguồn: `6cc6269` (dự báo mọi hũ), `ab1e5e6` (lời kết lộ trình: "router 1 + phác thảo + hai vòng sửa dùng hết trần 4 lượt gọi model nên write_buffered bỏ qua writer", Runtime v20), `d95607e`, `3603bc7`.
- Vì sao không phải gian lận: các câu không gắn ca, chỉ điền số của tool, nên luôn có căn cứ và không tốn lượt gọi model. Lý do lời kết lộ trình là thật (hết trần lượt gọi).
- Vì sao vẫn nên xem lại: đây là phần lớn nhất của "phình". Mỗi trạng thái mới cần thêm câu và nhánh; giọng văn khác nhau giữa đường có model và đường không; câu cố định không trả lời được ý riêng của câu hỏi (ví dụ hỏi "vì sao" nhận cùng câu với hỏi "bao nhiêu").
- Thay bằng (trade-off, chủ dự án chọn): khi còn lượt gọi model, dùng writer với bản gọn (cùng kiểm `has_ungrounded_numbers` như các việc phase 4) và giữ câu cố định làm đường suy giảm. Với lộ trình, có thể dành sẵn một lượt cho writer trong trần (`max_model_calls_per_turn`) thay vì để vòng sửa dùng hết. Nếu ưu tiên độ trễ và chi phí, giữ như hiện tại.

### 2.7 Mã chết và cấu hình thừa

**P25.** Loại: mã chết. Mức: thấp.
- `router_min_confidence` (defaults.json:44, settings.py:89,152): đọc vào `AgentSettings` nhưng không chỗ nào dùng.
- `memory_preferences_top_k` (defaults.json:49, memory.py:88,125): sở thích nay đọc hết bằng `ListMemoryRecords` với `preferences_list_max`; chỉ test còn dùng (tests/unit/agent/test_memory.py:531,543). Thuộc bộ nhớ, báo cho nhánh kia.
- `notices.ASK_MOVE_DETAILS` (notices.py:286) và `notices.PROFILE_PREPARED_HINT` (notices.py:263): không có lời gọi nào.
- `TASKS["out_of_scope"]` (writer.py:95): không có lời gọi nào (P7).
- turn.py:41 và turn.py:44 nhập `notices`, `trace` hai lần.
- `_PENDING_INTENTS` (turn.py:137) lặp `router.PENDING_INTENTS` (router.py:117).
- `_ = s` và biến `s` không dùng trong `_analyze_and_compose` (whatif.py:541,574).

### 2.8 Ngưỡng chọn theo ca

**P26. `DEDUP_MIN_DICE = 0.8` giải thích bằng câu của ca bộ nhớ.** Loại: ngưỡng chọn theo ca. Mức: thấp. Chỉ ghi nhận.
- Vị trí: libs/yofina_core/src/yofina_core/memory_text.py:83-86 (ví dụ "Ưu tiên để dành cho hũ Du lịch" là 0,93; "Không nhắc buổi sáng"/"buổi tối" là 0,75).
- Vì sao: ngưỡng chọn để tách đúng hai cặp lấy từ ca `memory-state-preference`. Nên có thêm một bộ nhỏ cặp câu (cùng ý, khác ý) để chọn ngưỡng.

**P27. `_FRAGMENT_MAX_WORDS = 6` theo chip dài nhất.** Loại: ngưỡng gắn chuỗi giao diện. Mức: thấp.
- Vị trí: router.py:129-131.
- Vì sao: gắn với chip hiện có, không với eval. Câu trả lời gõ tay dài 7 từ ("thôi trả bằng tiền trong hũ ăn uống nhé") bị coi là câu mới. Hết cần khi chip có cấu trúc (P15).

### 2.9 Dấu vết trên CloudWatch (2 ngày gần nhất, Runtime `yofina_agent`)

- `router_fallback`: 9 lượt (intent dự phòng `what_if`, `affordability`, `lookup`), tức router bằng model vẫn có lúc không dùng được và luật dự phòng của `fallback.py` vẫn được dùng thật.
- `numeric_ungrounded`: 1 lượt (writer nêu 2.000.000 không có trong bản gọn), nên kiểm căn cứ vẫn bắt được lỗi thật.
- `verifier_retry`: 2 lượt, đều `source_jar_covers`; không có `verifier_fallback`.
- Không có `writer_timeout`, `turn_timeout`, `orchestrator_invalid_spec`, `option_action_dropped`.

Các số này cho thấy harness L0 đến L5 vẫn làm việc của nó; chúng không đo được các luật vá ca ở trên, vì không có log nào ghi luật nào đã tác động. Đo phải bằng eval trước và sau (mục 5).

## 3. Trông đáng ngờ nhưng là nguyên tắc hợp lệ (không xóa)

| Mục | Vị trí | Vì sao giữ |
|---|---|---|
| Kiểm căn cứ con số: `NumericGrounding`, `check_grounding`, `has_ungrounded_numbers`, `reason_numbers` của lộ trình, `apply_summary` của hồ sơ hành vi | verifier.py, writer.py:170-178, roadmap_agent.py:363, behavior.py:201 | Nguyên tắc "số phải có căn cứ" của thiết kế Cách B; không gắn ca nào. |
| `check_suitability` cho mọi phương án và bước, `normalize_proposal` đặt `origin` bằng mã | whatif.py:631, roadmap_agent.py:705 | Luật suitability có tên và lý do nghiệp vụ; mã quyết định nguồn gốc đề xuất. |
| Token xác nhận, agent không bao giờ điền cờ xác nhận; tool ghi trả OK khi không token thì báo lỗi nghiêm trọng | turn.py:1447, 1489 | ADR-0002. |
| Che PII trước model, log và bộ nhớ; Guardrail đầu vào và đầu ra | turn.py:756-765, `yofina_core.pii`, guardrail.py | Lớp L0. |
| `match_shock_id` khớp nhãn cú sốc trước router | textutil.py:153 | Đọc từ `shocks.json`, không gắn câu; số tiền cụ thể nhường cho what-if. |
| `fallback.classify_by_rules` | fallback.py | Chỉ chạy khi router hỏng (log thật: 9 lượt trong 2 ngày); từ khóa chung, không câu cụ thể. |
| `clarify.missing_slot` (ô bắt buộc theo ý định), câu hỏi lại đúng một dấu "?" | clarify.py, schemas.py:80-84 | Hợp đồng khối `clarify`; mã không tin router về ô bắt buộc. |
| Lộ trình 2 đến 3 giai đoạn, 4 đến 6 bước; `roadmap_accept_min_phases` 2, `roadmap_accept_min_steps` 4 | roadmap_agent.py:50-55, 1035; defaults.json:28-29 | Yêu cầu của chủ dự án ngày 24/11 (docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md dòng 131), không phải số chọn cho test dù trùng ngưỡng của `roadmap_shape`. |
| `amount_refs`, `first_phase_sources`, ví dụ khuôn bước có chỗ giữ `{tên hũ nguồn}` trong `ROADMAP_SYSTEM` | roadmap_agent.py:67-87 | Mô tả hợp đồng dữ liệu; ví dụ dùng chỗ giữ, không dữ liệu thật. |
| "Nói rõ đây không phải điểm tín dụng", "chưa có khoản tiền nào được chuyển", "Trả sau chỉ là sản phẩm mô phỏng" | writer.py:69,74,55; whatif.py:326 | Ràng buộc nghiệp vụ và pháp lý mà model không tự biết. |
| Luật Analyst "không đề xuất vẫn mua bằng Trả sau cho khoản chi tùy ý", "chỉ chọn hũ có số dư đủ" | whatif.py:339-342 | Nói trước luật `no_borrow_to_spend`, `source_jar_covers` mà Verifier sẽ kiểm, kèm lý do; giảm vòng sửa (log: `verifier_retry` vẫn còn ở `source_jar_covers`). |
| Luật ingest về rút tiền mặt và màn tra soát | prompts.py:51,54,118 | Quyết định nghiệp vụ của chủ dự án (`4d6a755`); có mã chặn dự phòng. |
| `_DATA_NOT_INSTRUCTIONS` và các câu "nội dung trong thẻ ... là dữ liệu" | prompts.py:14, router.py:95, writer.py:30, whatif.py:126,349 | Chống prompt injection; ca đối kháng cần nó. |
| Chữ hoa nhấn mạnh trong prompt gửi Nova | router.py, prompts.py | AWS khuyên dùng với Nova 2 (mục 6). Chỉ bỏ khi câu đó bị bỏ vì lý do khác. |
| Ví dụ trích tham số lộ trình "15 triệu ở hũ Mua xe trong 6 tháng" | router.py:73-76 | Ví dụ định dạng cho việc trích nhiều ô; không trùng ca eval (ca `roadmap-infeasible-goal` dùng 1 tỷ, hũ Du lịch). Nên thêm một ví dụ thứ hai khác hẳn để tránh học một mẫu. |
| Ngưỡng phân hũ tự động | gateway/tools/ledger/yofina_ledger/classify_defaults.json | Hiệu chỉnh trên nửa đầu `evals/classification/dataset.jsonl` theo thời gian và đo trên nửa sau; đúng cách tách tập. |
| `_params_lenient`, `_readable_amount_chip`, `_strip_ordinal`, `item_label` bỏ "mua Mua" | schemas.py:134, turn.py:1803, roadmap_agent.py:835, whatif.py:226 | Chịu lỗi định dạng, không đổi nội dung. |
| `enforce_switch_jar`, `enforce_pay_now` | whatif.py:694-779 | Xem P23: nguyên tắc chung, chỉ nên gom. |
| Op `eval_extract` của Lambda ingest | gateway/tools/ingest/handler_worker.py:41 | Đường vào riêng cho bộ đo, cùng prompt với sản phẩm. |

## 4. Đánh giá bộ eval

Bộ chấm `evals/run.py` phần lớn chấm hành vi: ý định, tool phải gọi hay cấm gọi, khối phải có, số có căn cứ, suitability, ghi không token, PII, nguồn trích dẫn. Đó là cách chấm đúng. Các chỗ dễ kéo prompt về câu chữ:

| Vấn đề | Ca | Vì sao dễ ép prompt | Đề xuất (vẫn nghiêm) |
|---|---|---|---|
| Câu hỏi trùng ví dụ router hoặc chip | `behavior-*`, `ingest-*`, `knowledge-*`, `afford-1`, và 5 ca trùng chip (`lookup-balance`, `whatif-bnpl`, `afford-2`, `resilience-current-score`, `roadmap-view-current`) | Ý định chấm bằng so khớp chính xác; câu hỏi chính là ví dụ nên điểm cao không chứng minh router hiểu câu mới. | Thêm `evals/golden/paraphrase.jsonl`: mỗi ca phase 3 đến 5 có 2 cách hỏi khác (người khác viết, không xem prompt), cùng kỳ vọng. Thêm test CI: không cụm 5 từ nào của câu eval nằm trong chuỗi prompt sản phẩm (quét như mục 0, bước 2). |
| `memory_reuse` chấm bằng việc câu trả lời có tên hũ | `memory-reuse-new-session` | Câu "theo điều bạn đã dặn, ... hũ Du lịch" do bịa vẫn qua; chính tiêu chí này đã kéo `MEMORY_GUIDE` về câu mẫu. | Thêm ca đối chứng: cùng câu hỏi, tài khoản không có bộ nhớ, cấm nhắc "đã dặn", "sở thích", và cấm gán hũ cho người dùng. Ca chính kiểm thêm bản ghi sở thích có trong khối bộ nhớ của lượt (trace), và hũ được dùng trong phương án hay hành động, không chỉ trong chữ. |
| `expect_insight_kind` mỗi loại một cách hỏi | `behavior-payday`, `behavior-weekday`, `behavior-bnpl` | Một cách hỏi cho mỗi loại là đủ để bảng từ khóa qua (P12). | Đưa vào bộ diễn đạt lại. |
| `forbid_tickers` bằng regex `[A-Z]{3,4}` và danh sách cho phép | đối kháng `stock-*`, `roadmap-force-*` | Không ép prompt, nhưng đẩy thiết kế về "ngoài phạm vi không có lời model" (turn.py:1505). Đó là lựa chọn an toàn hợp lý. | Giữ. Cập nhật `TICKER_OK` khi thêm từ viết tắt mới. |
| Không có tiêu chí cho chất lượng lời viết | mọi ca có writer | Không có gì đo việc bỏ khuôn "đúng N câu" (P6) làm câu tốt hơn hay tệ hơn, nên người sửa chỉ còn cách giữ khuôn. | Thêm chấm định tính trên 20 lượt cố định: trả lời đúng câu hỏi, không lặp thẻ, không chêm, có căn cứ. Có thể dùng AgentCore Evaluations (Correctness, Helpfulness) như README của evals đã dự kiến, hoặc đọc tay. Không biến thành tiêu chí đếm câu. |
| Ca chỉ chấm ý định cho đường dựng câu bằng mã | `roadmap-edit-one-step`, `knowledge-late-fee` | Đúng cách (không chấm câu chữ); nêu để biết bỏ các câu cố định sẽ không làm ca trượt. | Giữ. |
| `exactly_one_question`, `roadmap_shape`, `stress_shock` | nhiều ca | Kiểm đặc tả sản phẩm, không ép câu chữ. | Giữ. |

## 5. Kế hoạch sửa

Mỗi đợt một nhóm, một nhánh, đo trước và sau trên cùng Runtime và dữ liệu seed (đặt lại `minh` theo `evals/README.md`). "Đo" là một lượt golden và adversarial của các phase liên quan, cộng bộ diễn đạt lại khi đã có. Giữ thay đổi khi: golden và adversarial không tụt so với lượt trước, hoặc chỉ tụt ở ca có câu hỏi trùng ví dụ vừa bỏ trong khi bộ diễn đạt lại không tụt; `numeric_grounding_pct` không giảm; log `numeric_ungrounded`, `verifier_fallback` không tăng. Lùi khi adversarial tụt bất kỳ ca nào.

| Đợt | Nội dung | File đổi | Đo | Dòng bỏ / thêm (ước) |
|---|---|---|---|---|
| 0. Nền đo | Viết `evals/golden/paraphrase.jsonl` (khoảng 60 câu, người viết không xem prompt); test CI chống trùng cụm 5 từ giữa eval và prompt; chạy một lượt nền golden, adversarial phase 3 đến 5 và bộ diễn đạt lại trên Runtime hiện tại | evals/, tests/unit/agent/ | Lượt nền | thêm ~60 dòng mã test, ~60 dòng dữ liệu |
| 1. Mã chết (**đã làm** `24d1ad1`) | P25 (trừ `memory_preferences_top_k`, chuyển cho nhánh bộ nhớ) | defaults.json, settings.py, notices.py, writer.py, turn.py, whatif.py | Unit test | bỏ ~20 |
| 2. Writer (**đã làm** `a9f1065`) | P6, P7: viết lại `WRITER_SYSTEM` và `TASKS` theo mục tiêu và nghĩa dữ liệu, bỏ số câu và câu chêm; bỏ câu nới của `MEMORY_GUIDE` (báo nhánh bộ nhớ) | writer.py, tests/unit/agent/test_writer*.py | Golden phase 3 đến 5; đọc tay 20 câu trả lời trước và sau (độ dài, chêm, đúng câu hỏi) | prompt bỏ ~1.000 ký tự (~300 token mỗi lượt); mã ±0 |
| 3. Router (**đã làm** `f68d2ce`) | P20, P21: `CLARIFY_INTENTS` trong `clarify.py`, xóa 5 câu "không hỏi lại" và câu "Ứng dụng" lặp; P1, P2: thay ví dụ chép eval bằng ví dụ khác có nhãn minh họa; P11(a): không nhận câu hỏi lại của router cho `lookup` không có hũ | router.py, clarify.py, test router | Golden phase 3 đến 5 + diễn đạt lại; adversarial phase 3 đến 5 | prompt bỏ ~1.500 ký tự (~450 token mỗi lượt), mã +6 |
| 4. Ý định phụ bằng tham số router (**đã làm** `3e63feb`) | P10, P12, P13, P14: thêm `roadmap_action="edit_step"`, `insight_kind`, `fee_topic`, `ingest_action` vào `IntentParams`; bỏ `_asks_step_edit` và các regex đi kèm, `KIND_KEYWORDS` (giữ cho đường suy giảm), `CONCEPTS`/`FREE_PHRASES`, `START_PHRASES`; lời sửa bước do writer viết | schemas.py, router.py, turn.py, behavior_chat.py, fee_citation.py, ingest_chat.py, notices.py | Golden phase 4, 5 + diễn đạt lại; adversarial phase 5 (`citation-forgery`, `upload-*`) | mã bỏ ~150, thêm ~40; prompt thêm ~400 ký tự |
| 5. Luật vá ca | P17: bỏ router.py:80-81, đo, rồi quyết `spending_confirm_request`; P18: bỏ luật chữ hoa | router.py, turn.py, notices.py, whatif.py | Golden phase 3 (ca nhiều lượt) + diễn đạt lại; adversarial phase 3 | bỏ ~5 đến ~40 tùy kết quả |
| 6. Ingest (**đã làm** `b425eff`) | P19, P3: tách luật nghiệp vụ và nguyên tắc đọc chứng từ, bỏ chuỗi literal; thêm dòng CSV viết tắt khác vào synthetic | prompts.py, evals/ingest/ | `scripts/eval_ingest.py --set all`; adversarial phase 5 | prompt bỏ ~800 ký tự |
| 7. Chip có cấu trúc (cần đồng ý vì đụng hợp đồng và frontend) | P15, P11(b), P27: chip mang `id`, agent định tuyến chip bằng `id`; bỏ `route_runout_overview`, so khớp chip bằng chuỗi | contracts (khối `clarify`, `suggestions`), frontend, router.py, turn.py, textutil.py | Integration nhiều lượt, golden phase 3, 4 | mã bỏ ~50, thêm ~30 |
| 8. Tùy chọn | P24: writer cho các đường đang dựng câu bằng mã khi còn lượt gọi model; P23: gom dựng nhãn phương án; P8, P9 | turn.py, notices.py, whatif.py, roadmap_agent.py | Golden phase 4, 5; độ trễ p95 | tùy phạm vi |

Tổng ước nếu làm đợt 1 đến 6: bỏ khoảng 230 dòng mã và hằng chuỗi, thêm khoảng 90 (phần lớn là test và bộ diễn đạt lại); prompt router và writer ngắn đi khoảng 2.500 ký tự, tức khoảng 750 token mỗi lượt có writer. Đợt 7 và 8 bỏ thêm khoảng 100 dòng tùy lựa chọn.

### 5.1 Đã làm (nhánh `p5/audit-fix`, 2026-11-25)

Chủ dự án duyệt đợt 1, 2, 3, 4 và 6; đợt 0 (đo nền), 5, 7, 8 không làm. Chưa chạy eval thật: người điều phối đo golden và adversarial
một lần trước và một lần sau cả cụm. Unit `uv run pytest tests/unit libs/yofina_core/tests -q`: 3640 passed trước, 3690 passed sau
(3 skipped như cũ).

Số ký tự lời nhắc (đo bằng `len()` của chuỗi hằng, không gồm dữ liệu chèn lúc chạy):

| Lời nhắc | Trước | Sau | Ghi chú |
|---|---|---|---|
| `ROUTER_SYSTEM` | 7.985 | 8.884 | Đợt 3 còn 7.912 (ví dụ chép golden thay bằng định nghĩa và ranh giới, bỏ 5 câu "không hỏi lại" và câu "Ứng dụng" lặp); đợt 4 thêm 972 cho bốn ý định phụ. Cộng danh sách cú sốc: 8.339 → 9.238 |
| `WRITER_SYSTEM` | 779 | 1.002 | Mục tiêu và giới hạn độ dài nói một lần ở đây; "không khuyên đầu tư hay vay" chuyển từ 3 việc lên đây |
| `TASKS` (tổng) | 3.807 (13 việc) | 3.298 (13 việc) | Bỏ `out_of_scope` (216), thêm `roadmap_step_edit` (381); 12 việc chung: 3.591 → 2.917 |
| Writer mỗi lượt (hệ thống + một việc), trung bình 12 việc chung | 1.078 | 1.245 | Dài hơn khoảng 170 ký tự: phần mục tiêu chung thay cho khuôn số câu; ước của kế hoạch (bỏ ~1.000) không đạt vì khuôn cũ ngắn hơn phần mô tả nghĩa dữ liệu |
| `image_system` | 5.248 | 4.431 | Đợt 6 |
| `labels_system` | 1.948 | 2.059 | Luật tự chuyển và rút tiền mặt nay là một hằng chung với ảnh (`_OWN_TRANSFER`), dài hơn bản CSV cũ |

Dòng mã (`git diff --numstat 3d6e22e`): `agent/src/` thêm 175, bỏ 322; `pipelines/ingest/yofina_ingest/prompts.py` thêm 32, bỏ 19;
`evals/` thêm 148 (bộ diễn đạt lại và bộ chấm); test thêm 465, bỏ 145.

Từng đợt:

- **Đợt 1** (P25): bỏ `router_min_confidence` (defaults.json, settings.py), `notices.ASK_MOVE_DETAILS`, `notices.PROFILE_PREPARED_HINT`,
  `TASKS["out_of_scope"]`, import `notices, trace` lặp ở turn.py, `_PENDING_INTENTS` (turn.py dùng `router.PENDING_INTENTS`), `s` và
  `_ = s` ở `whatif._analyze_and_compose`. Kiểm bằng `git grep` không còn nơi dùng. `memory_preferences_top_k` để nhánh bộ nhớ.
- **Đợt 2** (P6, P7): `WRITER_SYSTEM` nói mục tiêu một lần (trả lời đúng câu hỏi, thường dưới 50 chữ, không liệt kê lại thẻ, không
  thêm lời khuyên không được hỏi, xong thì dừng); mỗi việc chỉ còn thẻ nào đã hiện, nghĩa các trường và ràng buộc nghiệp vụ (không phải
  điểm tín dụng, chưa chuyển hay lưu gì). `affordability` hết câu thứ hai bắt buộc. `chitchat` nhận `viec_lam_duoc` từ `notices.CAN_DO`
  qua dữ liệu; `CAN_DO` thêm hai mục (chống chịu, cú sốc, lộ trình; thói quen, phí, nạp sao kê) vì danh sách cũ thiếu. `MEMORY_GUIDE`
  không đụng (nhánh `p5/mem-p0`): câu "được viết thêm tối đa 1 câu ngoài khuôn của nhiệm vụ" nay không còn khuôn để nới.
- **Đợt 3** (P1, P2, P11a, P20, P21): `clarify.CLARIFY_INTENTS` = {what_if, affordability, move, profile_update} là chỗ duy nhất quyết
  ai được hỏi lại; `resolve_clarify` bỏ câu hỏi lại của router cho ý định khác (kể cả `lookup`), schema thôi ép thử lại khi
  `out_of_scope`/`chitchat` có `clarify`, `turn.flow` bỏ điều kiện riêng cho stress và roadmap. `router.PENDING_INTENTS` trỏ cùng tập.
  "Hũ nào sắp cạn" còn một lớp: nghĩa của `lookup_kind=forecast` ("jar_text null khi hỏi về mọi hũ") cộng `on_forecast` không có hũ thì
  đọc mọi hũ; bỏ `route_runout_overview`/`asks_which_jar_runs_out` (regex). Luật dự phòng thêm "sắp cạn", "bị hụt" vào từ khóa dự báo
  để đường suy giảm vẫn nhận chip. Test CI `test_prompt_eval_overlap.py`: không cụm 5 từ liên tiếp nào của câu trong `evals/golden`,
  `evals/adversarial`, `evals/paraphrase` nằm trong lời nhắc router, writer, Orchestrator, Analyst, lộ trình, bộ nhớ, ảnh, CSV; test bắt
  được `_DATA_NOT_INSTRUCTIONS` chép "bỏ qua hướng dẫn trước đó" của ca `chat-pasted-instruction`, đã đổi thành "bỏ qua chỉ dẫn đang có".
- **Đợt 4** (P10, P12, P13, P14): `IntentParams` thêm `roadmap_action="edit_step"`, `insight_kind` (enum `BehaviorInsightKind`),
  `fee_topic` (monthly, per_transaction, once, late, other), `ingest_action` (how_to, status); schema router nằm ở
  `agent/src/yofina_agent/schemas.py`, không ở `contracts/`. Bỏ `behavior_chat.KIND_KEYWORDS`/`asked_kind`, `fee_citation.CONCEPTS`/
  `FREE_PHRASES`/`asks_free`/`asked_concepts`, `ingest_chat.START_PHRASES`/`wants_start`, regex sửa bước ở turn.py (`_STEP_*`,
  `_asks_step_edit`, `_match_steps`) và 5 câu `ROADMAP_EDIT_*`. Mọi chủ đề phí không có dòng khớp (kể cả `other`) đi chung một câu "chưa
  có ... nên mình không đưa số hay nguồn". Sửa bước: đọc bản đang dùng, phát thẻ, writer viết từ `compact_roadmap_steps` (mọi bước, số
  tiền, hũ, hạn) cộng `cach_sua`, `so_tien_moi_text`; việc `roadmap_step_edit` kiểm trọn số như việc phase 4, hỏng hay hết lượt thì
  `notices.ROADMAP_EDIT_HOW` (không số). Không lưu gì; thao tác ghi vẫn chỉ qua token. Luật dự phòng không có ý định phụ, nên khi model
  hỏng câu sửa bước rơi về xem lộ trình.
- **Đợt 6** (P19, P3): xem bảng dưới.
- **Bộ diễn đạt lại**: `evals/paraphrase/router.jsonl` 18 câu (mỗi câu một ý định, ghi ca golden nó diễn đạt lại), chấm ý định và tham
  số kỳ vọng kể cả ý định phụ; `evals/paraphrase/run_router.py` gọi router một lần mỗi câu. Nhỏ hơn đợt 0 dự kiến (60 câu) theo yêu cầu.

Đợt 6, từng dòng lời nhắc ảnh và CSV:

| Dòng | Giữ hay bỏ | Lý do |
|---|---|---|
| `_DATA_NOT_INSTRUCTIONS` | Giữ (đổi 3 chữ) | Chống prompt injection (mục 3); đổi cụm trùng câu đối kháng |
| Chỉ ghi giao dịch đã thực hiện xong | Giữ | Định nghĩa của ứng dụng |
| Màn xác nhận, OTP, biểu mẫu chưa gửi là `unexecuted_form` | Giữ | Quyết định nghiệp vụ "chưa thực hiện thì không phải giao dịch" |
| Màn chi tiết có mã giao dịch là đã thực hiện dù không có chữ "thành công" (r08) | Bỏ | Cách đọc chứng từ; gộp vào câu nguyên tắc "lấy theo ngữ nghĩa của chính chứng từ (tiêu đề cột, dấu, số dư trước và sau, mã hay thời gian thực hiện)" |
| Màn tra soát, khiếu nại, yêu cầu hoàn tiền không tạo dòng; hoàn tiền đã về vẫn là giao dịch | Giữ | Quyết định của chủ dự án (`4d6a755`), có lý do (giao dịch gốc đã có) |
| Thất bại, hủy, từ chối, đang xử lý là `failed`/`pending` | Giữ, rút gọn | Ánh xạ trạng thái vào trường `status`; liệt kê lại ít chữ hơn |
| Tự chuyển giữa tài khoản của mình là `own_account_transfer`; nạp điện thoại, trả thẻ tín dụng, mua hàng thì không | Giữ, gộp vào `_OWN_TRANSFER` dùng chung với CSV | Định nghĩa nghiệp vụ |
| Rút tiền mặt là `own_account_transfer=true`, vẫn trích dòng; phí rút là khoản chi | Giữ, gộp vào `_OWN_TRANSFER` | Quyết định của chủ dự án 24/11; bỏ "description giữ nguyên" lặp với trường description |
| Bảng phí, menu, ảnh không có tiền là `other_financial`; ảnh không tài chính là `not_financial` | Giữ | Nghĩa của `document_type` |
| Trích MỌI dòng, kể cả cùng số tiền, dòng phí, dòng rút tiền mặt | Thay | Còn một câu "một giao dịch nhìn thấy là một dòng; không tự bỏ dòng trông giống dòng khác, hệ thống tự lọc trùng": lý do (lọc trùng ở hạ nguồn) model không tự biết; dòng rút tiền mặt đã nói trong `_OWN_TRANSFER` |
| `date`, `amount_vnd`, "ngày Việt Nam viết ngày/tháng/năm" | Giữ | Định dạng trường |
| `direction`: danh sách động từ ra/vào, cột Ghi nợ/Ghi có theo tiêu đề, kiểm lại bằng cột số dư (r15) | Bỏ phần cách đọc | Còn "out khi tiền ra khỏi tài khoản của người dùng, in khi tiền vào"; cách đọc cột và số dư nằm trong câu nguyên tắc |
| `counterparty` "(không bịa ...)" | Bỏ phần lặp | `_DATA_NOT_INSTRUCTIONS` đã nói không bịa |
| `description` giữ nguyên ký tự; không chép số tài khoản, số thẻ, số điện thoại | Giữ | Dữ liệu dùng để lọc trùng; PII |
| `tx_type`, `jar_code`, `confidence`, danh sách hũ và loại, `document_type`, `year_hint`, `readable` | Giữ | Nghĩa của trường |
| Chuyển cho cá nhân có mục đích thì phân loại theo mục đích, kèm ví dụ "tiền phòng, tiền nhà, tiền điện, học phí" | Giữ luật (`_PURPOSE` dùng chung), bỏ ví dụ | Luật phân loại của sản phẩm; "tiền phòng" chép từ dữ liệu `c01` |
| CSV `merchant`: ví dụ "thanh toan QR", "Highlands Coffee", "CGV", "Grab" | Bỏ ví dụ | Các chuỗi này có trong `evals/ingest/manifest.json` (23, 31, 21, 42 lần); còn "bỏ ... cụm chỉ cách thanh toán" |
| CSV rút tiền mặt "ví dụ RUT TIEN TAI ATM" (P3) | Bỏ chuỗi literal | Thay bằng "dù chứng từ ghi tắt thế nào"; mã chặn `looks_like_self_topup` giữ |
| `columns_system` | Giữ nguyên | Không có luật vá ca |

Chưa làm trong đợt 6: thêm dòng CSV rút tiền mặt viết tắt khác vào bộ synthetic (ngoài phạm vi được giao, chỉ được sửa bộ diễn đạt lại).

Rủi ro khi đo lại (ca có thể đổi kết quả và vì sao đó là thông tin đúng):

- Đợt 2: không ca nào chấm số câu. Câu trả lời có thể dài hơn một chút; cần đọc tay vài lượt. `numeric_grounding_pct` không đổi vì
  luật số giữ nguyên.
- Đợt 3: golden phase 5 `behavior-habits`, `knowledge-late-fee`, `ingest-*`, `afford-1` mất ví dụ trùng câu; trượt thì đó là độ hiểu
  thật của router. Chip "Hũ nào sắp cạn?" mà router xếp vào `balance` nay ra thẻ số dư thay vì dự báo mọi hũ (không ca golden nào; ca
  `pr-forecast-which-jar` đo). `lookup` không còn hỏi lại "hũ nào": đọc mọi hũ thay vì hỏi.
- Đợt 4: ba ca `expect_insight_kind` (`behavior-payday`, `behavior-weekday`, `behavior-bnpl`) nay phụ thuộc router trích đúng
  `insight_kind`; `ingest-start` cần `ingest_action="how_to"`, router để null thì đọc lần nạp gần nhất và trượt `tools_must start_job` khi
  đã có job; `knowledge-late-fee` cần `fee_topic="late"`, để null thì liệt kê mọi phí (vẫn đạt `forbid_unretrieved_citation`).
  `citation-forgery` chấm nguồn trích dẫn nên vẫn đạt dù router đặt `other` hay null. `roadmap-edit-one-step` chỉ chấm ý định, tool và
  khối; router không đặt `edit_step` thì rơi về xem lộ trình, vẫn đạt. Router xuất thêm ba khóa null mỗi lượt (schema Bedrock đòi đủ
  khóa), `router_max_tokens` 400 vẫn dư.
- Đợt 6: r08, r15 của `evals/ingest` có thể trượt lại; nếu trượt, đó là bằng chứng luật đọc cụ thể còn cần với Sonnet 4.6, nên thêm lại
  kèm lý do. Adversarial phase 5 `upload-*`, `csv-*` dựa `_DATA_NOT_INSTRUCTIONS` và cờ `contains_instructions`, không đổi nghĩa.

### 5.2 Kết quả đo sau deploy (Runtime v25, 24/11 tối theo giờ máy)

Đo một lần mỗi bộ trên Runtime `yofina_agent` v25 (mã `main` 2baf07d, gồm cả `p5/mem-p0`, `p5/ingest-fx`, `p5/fx-tool`), đặt lại `minh`
trước mỗi bộ; mốc "trước" là lượt trên Runtime v24 trước cụm sửa (golden phase 3, 4, adversarial phase 3) và các lượt cũ cho phần còn
lại. Chi tiết, dẫn chứng và phân loại từng ca: file phase 5, mục "Đo sau đợt sửa kiểm toán và bộ nhớ (Runtime v25)".

| Bộ | Trước | Sau |
|---|---|---|
| Golden phase 3 | 31/31 | 31/31 |
| Golden phase 4 | 14/14 | 14/14 |
| Golden phase 5 | 12/12 (12 ca) | 11/15: 12 ca cũ 11/12, 3 ca mới 0/3, cả bốn ca trượt do bộ chạy eval không nạp được bản ghi (`SEED_EXPIRY_DAYS = 1`, API đòi ≥ 31) |
| Adversarial phase 3, 4, 5 | 16/16, 12/12, 14/14 | 16/16, 12/12, 14/14 |
| Diễn đạt lại router (18 câu) | chưa có (đợt 0 không làm) | 18/18, ý định và tham số 100% |
| OCR bộ real, đủ 4 trường | 9/11 | 9/11 (r08 trượt, r15 đạt) |

Đối chiếu với rủi ro ở trên:

- Đợt 2: không ca nào trượt vì độ dài. Câu trả lời golden phase 3 dài hơn một chút: trung bình 50 lên 56 từ, trung vị 34 lên 42; phase 4
  và 5 gần như không đổi. `numeric_grounding_pct` 100% ở mọi bộ.
- Đợt 3: `behavior-habits`, `knowledge-late-fee`, `ingest-*`, `afford-1` đều đạt; `pr-forecast-which-jar` đạt. Không ca nào trượt vì
  router hiểu kém.
- Đợt 4: ba ca `expect_insight_kind`, `ingest-start`, `knowledge-late-fee`, `citation-forgery`, `roadmap-edit-one-step` đều đạt; bộ diễn
  đạt lại chấm đúng cả bốn ý định phụ.
- Đợt 6: r08 trượt lại (`no_transactions`, 0/1 dòng) đúng như rủi ro đã ghi; r15 đạt. Theo luật giữ hay lùi ở đầu mục 5, đây là bằng
  chứng luật "màn chi tiết có mã giao dịch là đã thực hiện" còn cần với Sonnet 4.6: nên thêm lại kèm lý do (chưa làm, đợt đo không sửa mã).
  Adversarial phase 5 `upload-*`, `csv-*` đạt 7/7.
- Log Runtime: `verifier_fallback` 0 trước và sau. `numeric_ungrounded` 0 trong lượt nền và 2 trong lượt này (việc `roadmap` ở golden
  phase 4, việc `resilience` ở adversarial phase 4; câu người viết bị bỏ, ca vẫn đạt). Lượt này chạy thêm ba bộ so với lượt nền nên chưa
  so được tỷ lệ; theo dõi ở lượt sau.

Kết luận theo luật giữ hay lùi: giữ đợt 1 đến 4; giữ đợt 6 nhưng thêm lại luật đọc màn chi tiết có mã giao dịch (r08).

## 6. Nguồn đã tra

- [Amazon Nova 2: Create precise prompts](https://docs.aws.amazon.com/nova/latest/nova2-userguide/create-precise-prompts.html): khuyên dùng chữ hoa và DO, DO NOT, MUST cho luật phải tuân; nói rõ định dạng và độ dài mong muốn.
- [Amazon Nova 2: Provide examples (few-shot prompting)](https://docs.aws.amazon.com/nova/latest/nova2-userguide/prompting-provide-examples.html): ví dụ phải đa dạng, phủ từ ca thường tới ca biên, tránh thiên lệch; ví dụ của bộ phân loại là kỹ thuật được khuyên.
- [Amazon Nova 2: Bring focus to sections of the prompt](https://docs.aws.amazon.com/nova/latest/nova2-userguide/prompting-bring-focus.html): chia phần rõ (markdown, XML), đặt ví dụ trong khối riêng để model không chép ra.
- [Claude: Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices): nêu lý do bên cạnh luật để model tự khái quát; ví dụ phải liên quan, đa dạng, đặt trong `<example>`; bỏ chỉ dẫn ép quá mức viết cho model cũ.
- Phương pháp kiểm toán: tài liệu prompt-audit đi kèm skill `claude-api` (inventory, provenance, các nhóm mẫu: luật chồng luật, ví dụ đơn lẻ, giới hạn số câu, luật không ai thực thi).
- Trong repo: docs/research/agentcore-memory-design.md, docs/architecture/overview.md, docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md, `git log` của các commit nêu ở từng mục.
