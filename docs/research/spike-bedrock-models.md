# Spike: gọi model Bedrock thật (2026-11-21)

Chạy thử thật để kiểm các khẳng định trong [bedrock.md](bedrock.md). Script, dữ liệu thô và README cách chạy lại nằm ở `spikes/bedrock-models/`. Mọi lời gọi chỉ là `Converse`/`ConverseStream`/`InvokeModel` và các API đọc (`List*`, Service Quotas, Pricing). `CountTokens` thử nhưng không chạy được với profile `global.`. Không tạo/sửa/xóa tài nguyên, không xin tăng quota. Dữ liệu thử (giao dịch, ảnh, tên người nhận) hoàn toàn hư cấu. Không ghi account ID.

Quy ước: **[Đo]** là số đo thật trong spike này; **[Suy luận]** là suy ra từ số đo hoặc từ tài liệu, chưa kiểm.

## 0. Tóm tắt

- **Chủ dự án không xin tăng quota được, nhưng vẫn đủ model để chạy MVP ngay hôm nay.** Quota bằng 0 biểu hiện là `AccessDeniedException` (HTTP 403) "… is not available for this account", không phải `ThrottlingException`. Claude 5.x, Opus 4.7+, Fable, Sonnet 5 đều bị chặn như vậy ở cả `ap-southeast-1` và `us-east-1`.
- **Dùng được ngay (đã gọi thật):** Claude Haiku 4.5, Sonnet 4.6, Opus 4.6; Nova Micro/Lite/Pro, Nova 2 Lite; **Kimi K3 và K3.1 ngay tại Singapore** (K3: 10M TPM, có ảnh, tool use ép buộc và structured output đều đúng 14/14 trên bộ thử); ở `us-east-1` có thêm nhiều model open-weight quota 100 RPM (Qwen3-Next-80B, Qwen3-VL-235B, Mistral Large 3, DeepSeek V3.2, gpt-oss-120b, Kimi K2.5, GLM 4.7, Gemma 3).
- **Họ GPT-6/5.x báo quota > 0 nhưng vẫn `AccessDenied` khi gọi**: đừng tin riêng cột quota.
- **RPM thực của Claude 4.x là 10 mỗi model** (mỗi model một xô riêng). Một lượt what-if kiểu Yofina (router Haiku + planner Sonnet hai vòng + diễn giải Haiku) tốn 2 call Haiku + 2 call Sonnet, đo được 6,3 giây/lượt; ba lượt liền nhau (6 + 6 call trong khoảng 19 giây) không bị throttle. Đủ cho demo một người, không đủ khi nhiều người/agent cùng dùng; xem mục 9.
- **Embedding tiếng Việt không dấu**: ngưỡng cosine 0,97 của proposal **không hợp lý** để gom "cùng nghĩa" (mục 6).

## 1. Quota bằng 0 biểu hiện thế nào

**Cách thử:** `01_quota_zero.py` gọi `converse` (maxTokens 20, tắt retry của boto3) tới profile ID lấy từ `ListInferenceProfiles`; `01b_other_models.py` thử thêm các model khác.

**Kết quả [Đo]**

| Model (profile ID) | `ap-southeast-1` | `us-east-1` |
|---|---|---|
| `global.anthropic.claude-haiku-5-5` | **AccessDeniedException, HTTP 403**, 0,24 giây | cùng lỗi, 0,95 giây |
| `global.anthropic.claude-sonnet-5-5` | cùng lỗi, 0,11 giây | cùng lỗi, 0,34 giây |
| `global.anthropic.claude-sonnet-5` và in-region `anthropic.claude-sonnet-5` | cùng lỗi | không thử |
| `global.anthropic.claude-opus-5-5`, `global.anthropic.claude-fable-5-2` | cùng lỗi | không thử |
| `global.anthropic.claude-haiku-4-5-20251001-v1:0`, `global.anthropic.claude-sonnet-4-6` | gọi được (0,5-0,65 giây) | gọi được |
| `global.anthropic.claude-opus-4-6-v1` | gọi được (1,3 giây; không đo thêm vì đắt, RPM 5) | không thử |

Thông điệp nguyên văn (không có account ID, chỉ nêu ID model gốc chứ không phải profile): `anthropic.claude-haiku-5-5 is not available for this account. You can explore other available models on Amazon Bedrock. For additional access options, contact AWS Sales at https://aws.amazon.com/contact-us/sales-support/`. Trả về trong dưới 1 giây, không retry được.

Phân biệt với giới hạn RPM: model đang có quota nhưng gọi quá nhanh trả `ThrottlingException: Too many requests, please wait before trying again.` (HTTP 429), gặp khi một agent khác dùng chung quota Haiku 4.5 cùng lúc với script này.

**Kết luận:** bedrock.md đoán đúng một nửa. Lỗi hiện tại là `AccessDeniedException`, nên chuỗi dự phòng trong code phải bắt cả `AccessDeniedException` (không chỉ `ThrottlingException`) khi chuyển Sonnet 5.5 → Sonnet 4.6. Cùng hiện tượng ở hai Region, khớp với suy đoán "tài khoản bị hạn chế, không phải do Region".

## 2. Model nào dùng được ngay

### 2a. Quota áp dụng (Service Quotas, chỉ đọc) [Đo]

`07_quotas.py`, `07b_join.py` liệt kê toàn bộ quota dịch vụ `bedrock` (525 dòng ở Singapore, 1.111 dòng ở `us-east-1`), ghép với `ListFoundationModels`/`ListInferenceProfiles`. Dưới đây chỉ giữ model có quota token > 0 (đầy đủ trong `results_07_table.txt`). "Đã gọi" ghi kết quả gọi thật.

**`ap-southeast-1`**

| Model | TPM / RPM áp dụng (mặc định AWS) | Đã gọi? |
|---|---|---|
| Claude Haiku 4.5 (global) | 5M / **10** (10.000) | Có |
| Claude Sonnet 4.6 (global) | 6M / **10** | Có |
| Claude Sonnet 4.5, Sonnet 4.5 1M ctx, Opus 4.5, Opus 4.6 (global) | 5M/10, 1M/1, 2M/5, 3M/5 | Chỉ Opus 4.6 (gọi được) |
| Amazon Nova Micro, Lite (cross-region `apac.`) | 400K / **20** (400) | Có |
| Amazon Nova Pro (`apac.`) | 2M / **25** (500) | Có |
| Amazon Nova 2 Lite, Nova 2 Omni (global) | 8M / **20** (2.000) | Nova 2 Lite có |
| Amazon Nova 2 Pro Preview (global) | 1M / 1 | Không |
| **Moonshot Kimi K3 (global)** | **10M** / không có dòng RPM | **Có, gọi được** |
| Moonshot Kimi K3.1 (global) | 1M / không có dòng RPM | **Có, gọi được** |
| OpenAI GPT-6 Luna 4M, GPT-6 Sol 2M, GPT-6.1 Sol 2M, GPT-6.1 Terra 4M (global) | quota > 0 | **Có, nhưng AccessDenied "not available for this account"** |
| OpenAI GPT-6.2 Astra/Sol, GPT 5.5, GPT 5.4 | không có dòng quota | AccessDenied như trên |
| Cohere Embed Multilingual v3, English v3, Embed v4 (global) | 300K / **20** | Multilingual v3, v4, English v3 có |
| Titan Text Embeddings V2 | quota 300K / 60 có dòng | **Không gọi được**: `ValidationException: The provided model identifier is invalid` (không có trong Singapore) |
| Quota = 0: Claude Haiku 5.5, Sonnet 5.5, Sonnet 5, Opus 4.7/4.8/5/5.5, Fable 5/5.1/5.2, GPT-5.6 (Luna/Sol/Terra), GPT-6 Astra, Grok 4.6/4.7, GLM 5.3 | 0 | Claude: AccessDenied như mục 1 |

**`us-east-1`** (khác Singapore ở chỗ có nhiều model on-demand)

| Model | TPM / RPM áp dụng | Đã gọi? |
|---|---|---|
| Claude Haiku 4.5, Sonnet 4.5/4.6 (cross-region và global) | 5-6M / **10** (cùng Singapore) | Có |
| Nova Micro, Lite (cross-region) | 8M / **200**; on-demand 4M / 100 | Có |
| Nova Pro (cross-region) | 2M / 25; on-demand 1M / 13 | Có |
| Nova 2 Lite | 8M / 20 | Có |
| **Open-weight on-demand**: DeepSeek V3.2, gpt-oss-120b/20b, Qwen3 32B / Next 80B / **VL 235B**, Mistral Large 3, Ministral 3/8/14B, Kimi K2.5, GLM 4.7 / 4.7 Flash / 5, MiniMax M2.5, Gemma 3 4B/12B/**27B**, Nemotron Super/Nano | **100M TPM / 100 RPM** (mặc định 10.000 RPM) | Có (mục 2b) |
| Llama 3.x/4 | 600K / 8 | Maverick gọi được nhưng không nhận `toolChoice` ép tool; Scout và Llama 3.3 70B: `ResourceNotFoundException` "marked by provider as Legacy" |
| Kimi K3 | 10M (cross-region 20M) | Có |
| Cohere Embed Multilingual v3, v4; Titan Text Embeddings V2 (300K/60); Nova 2 Multimodal Embeddings (RPM 20) | | Có cả bốn |
| Quota = 0: Claude Sonnet 5.5, Haiku 5.5, Opus 4.7+, Fable, Sonnet 5; GPT-5.6, GPT-6 Astra, Grok, GLM 5.3 | 0 | |
| GPT-6 Luna / Sol, 6.1 Terra | quota > 0 | AccessDenied như ở Singapore |

### 2b. Gọi thử từng ứng viên [Đo]

Prompt tiếng Việt: "Giải thích ngắn gọn trong đúng 2 câu: 'hũ ăn uống' trong quản lý chi tiêu cá nhân là gì?". `ConverseStream`, 3 lần lấy trung vị; "TTFT" là thời gian tới đoạn **chữ** đầu tiên (model có suy nghĩ thì token suy nghĩ đến sớm hơn, ghi riêng).

Hai bộ số. (A) `02_latency.py`, `maxTokens` 100, độ dài ra ép bằng nhau, nên so sánh được: Singapore.

| Model (Singapore) | TTFT (giây) | Tổng stream | Tổng `Converse` |
|---|---|---|---|
| Haiku 4.5 | 0,91 (3 lần: 4,02 / 0,91 / 0,64; lần đầu sau throttle) | 1,61 | 2,02 |
| Sonnet 4.6 | 0,61 | 1,82 | 1,84 |
| Nova Micro | 0,32 | 0,80 | 0,71 |
| Nova Lite | 0,36 | 0,75 | 0,73 |
| Nova Pro | 0,41 | 1,22 | 1,14 |
| Nova 2 Lite | 0,53 | 0,95 | 1,01 |

Lặp ở `us-east-1`: Haiku 4.5 0,88 / 1,49 / 1,53; Sonnet 4.6 0,92 / 2,12 / 2,16; Nova 2 Lite 0,75 / 1,43 / 1,20. Tức Singapore không chậm hơn `us-east-1` (client chạy ở Việt Nam; cả hai đều đi qua profile global nên khác biệt chủ yếu do đường mạng).

(B) `08_probe.py`, `maxTokens` 300, độ dài ra tự nhiên (khác nhau giữa model nên cột "Tổng" chỉ để tham khảo), cùng bộ thử tool use một câu và structured output.

| Model | Region | TTFT chữ | TTFT bất kỳ | Tổng | Token ra | Nhận xét tiếng Việt (một prompt ngắn, đánh giá thô) |
|---|---|---|---|---|---|---|
| Haiku 4.5 | SG | 0,38 | | 1,54 | ~175 | Tốt, hơi dài dòng, hay dùng tiêu đề Markdown |
| Sonnet 4.6 | SG | 0,57 | | 2,65 | ~170 | Tốt nhất, chính xác, nhắc đúng phương pháp "6 chiếc hũ" |
| Nova Pro | SG | 0,41 | | 1,48 | ~96 | Tốt, ngắn gọn |
| Nova Lite | SG | 0,33 | | 0,85 | ~100 | Tốt |
| Nova 2 Lite | SG | 0,66 | | 1,21 | ~90 | Tốt |
| **Kimi K3** | SG | 1,71 | 0,68 | 1,78 | 300 (bị cắt vì suy nghĩ tính vào `maxTokens`) | Tốt; **luôn suy nghĩ**, tách `reasoningContent` |
| Kimi K3.1 | SG | 1,89 | 1,07 | 1,92 | 300 (như trên) | Tốt |
| Qwen3-Next-80B | US | 0,65 | | 1,39 | ~70 | Tốt, gọn |
| Qwen3-32B | US | 0,66 | | 2,03 | ~63 | Tốt |
| Qwen3-VL-235B | US | 0,75 | | 1,60 | ~71 | Tốt |
| Mistral Large 3 | US | 0,70 | | 1,66 | ~73 | Tốt (có thêm chi tiết "10-15%" tự bịa) |
| DeepSeek V3.2 | US | 0,76 | | 2,31 | ~97 | Tốt |
| gpt-oss-120b | US | 0,89 | 0,69 | 1,78 | ~183 | Tốt, có suy nghĩ ngắn |
| gpt-oss-20b | US | 3,29 | 1,54 | 3,09 | 300 | Suy nghĩ dài, có lần trả rỗng trong 300 token |
| Kimi K2.5 | US | 1,04 | | 3,10 | ~150 | Tốt |
| GLM 4.7 | US | 0,77 | | 1,51 | ~70 | Khá (dùng từ lạ: "người mua sắm") |
| Gemma 3 27B | US | 0,65 | | 1,59 | ~92 | Khá |
| Gemma 3 12B | US | 0,67 | | 2,65 | ~86 | Đúng nhưng nông |
| Nemotron Super 120B | US | 0,71 | | 1,19 | ~88 | **Lẫn từ Pháp** ("dépenses") và từ sai |
| Ministral 14B | US | 0,65 | | 2,47 | ~111 | **Kém**: có câu vô nghĩa, lẫn ký tự lạ |
| GLM 4.7 Flash | US | 0,61 | | 0,81 | ~78 | **Sai nội dung** (nói về bia, rượu) |
| MiniMax M2.5 | US | 5,11 | 2,41 | 5,89 | 300 | Chậm do suy nghĩ |
| Nova Micro/Lite/Pro, Nova 2 Lite | US | 0,56-0,69 | | 1,19-1,63 | | Như Singapore |

**Kết luận:** Haiku 4.5/Sonnet 4.6 và Nova gọi được ngay với TTFT dưới 1 giây. Kimi K3 là ứng viên "LLM lớn" thay thế duy nhất đã gọi được tại Singapore ngoài họ Claude 4.x; ở `us-east-1` có thêm các model open-weight quota 100 RPM (đủ tiếng Việt: Qwen3-Next-80B, Mistral Large 3, DeepSeek V3.2, gpt-oss-120b, Kimi K2.5). Không nên dùng Ministral 14B, GLM 4.7 Flash, Nemotron Super cho văn bản tiếng Việt hướng người dùng.

### 2c. Mô phỏng một lượt what-if [Đo]

`10_flow.py` (Singapore): router Haiku 4.5 ép tool `report_intent` → planner Sonnet 4.6 vòng 1 (gọi tool giả `simulate_purchase`) → vòng 2 (đọc kết quả tool) → diễn giải Haiku 4.5 stream. Ba lượt liền nhau:

| Lượt | Router | Planner vòng 1 | Planner vòng 2 | Diễn giải: TTFT / tổng | Cả lượt |
|---|---|---|---|---|---|
| 1 | 0,87 | 1,21 | 3,25 | 0,45 / 1,05 | 6,38 giây |
| 2 | 0,67 | 1,26 | 3,27 | 0,71 / 1,08 | 6,29 giây |
| 3 | 0,75 | 1,31 | 3,06 | 0,42 / 1,25 | 6,37 giây |

Không có lỗi throttle trong cả 12 call (log retry rỗng). Tức khoảng 6,3 giây/lượt, nằm trong ngân sách 8 giây của proposal khi chưa tính guardrail và truy xuất KB. Vòng 2 của Sonnet 4.6 (3,1-3,3 giây) là phần chậm nhất vì phải viết câu trả lời.

## 3. Tool use và structured output

**Cách thử:** `03_tooluse.py`: schema `IntentResult` (intent ∈ {what_if_purchase, jar_balance, spending_summary, forecast_depletion, investment_advice, other}, params {amount_vnd, item, payment_method, jar}, confidence, needs_clarification, clarification_question), hệ thống prompt ngắn, 5 câu tiếng Việt: "nếu mua tai nghe 1,2 triệu bằng ví trả sau thì sao", "hũ ăn uống còn bao nhiêu", "nên mua cổ phiếu nào", "cuối tháng hũ giải trí có cạn không", "mua cái đó thì sao" (mơ hồ). Hai chế độ: (a) `toolConfig` + `toolChoice: {tool: {name}}` ép một tool; (b) `outputConfig.textFormat` (JSON Schema, structured output gốc của Converse). Chấm 14 ô: 5 intent, 2 tham số (số tiền, phương thức trả), 2 hũ, 5 cờ `needs_clarification`. Lưu ý: một số ô chấm "cờ hỏi lại" và "forecast_depletion" có thể bàn cãi (Haiku gán `jar_balance` cho "cuối tháng hũ giải trí có cạn không" là chấp nhận được); đọc con số như chỉ báo tương đối.

| Model | Region | (a) ép tool: đúng/14, trung vị | (b) structured output gốc |
|---|---|---|---|
| Haiku 4.5 | SG | 12/14, 1,06 giây | Chạy: 12/14, 0,75 giây (một lần 3,1-3,3 giây là lần biên dịch grammar đầu) |
| Sonnet 4.6 | SG | **14/14**, 1,24 giây | Chạy: **14/14**, 0,97 giây |
| Nova Pro | SG | 14/14, 0,66 giây | **Không hỗ trợ**: `ValidationException: This model doesn't support the outputConfig field` |
| Nova 2 Lite | SG | 14/14, 0,92 giây | Không hỗ trợ (như trên) |
| Nova Lite | SG | 12/14, 0,76 giây (sai "vi tra sau" mất dấu, cờ hỏi lại) | Không hỗ trợ |
| **Kimi K3** | SG | **14/14**, 2,29 giây | Chạy: **14/14**, 2,39 giây |
| Qwen3-Next-80B | US | 14/14, 1,42 giây | Chấp nhận `outputConfig`, JSON hợp lệ nhưng phân loại tệ hơn: 11/14 |
| Qwen3-VL-235B | US | 14/14, 1,78 giây | 9/14 |
| Kimi K2.5 | US | 14/14, 1,44 giây | 11/14 |
| GLM 4.7 | US | 14/14, 2,02 giây | 11/14 |
| gpt-oss-120b | US | 14/14, 1,39 giây | **Hỏng**: chỉ 1/5 phản hồi parse được JSON (có tiền tố chữ "personal" trước `{`) |
| DeepSeek V3.2 | US | 13/14, 1,64 giây (một lần 6,3 giây) | 11/14, chậm 7 giây |
| Mistral Large 3 | US | 13/14, 1,23 giây | 9/14 |
| Qwen3-32B | US | 13/14, 0,91 giây | 8/14 |
| Nemotron Super | US | 12/14, 1,21 giây | 9/14 |
| Llama 4 Maverick | US | **Không nhận** `toolChoice` ép tool | Không hỗ trợ `outputConfig` |

Kimi K3 không cho `temperature` (`ValidationException`), phải bỏ trường này. Với Kimi K3, tool ép buộc không tôn trọng `required` (bỏ trường `null`); structured output gốc thì điền đủ trường.

**Kết luận cho Yofina**
- Với Haiku 4.5, Sonnet 4.6, Nova (trừ structured output gốc) và Kimi K3, **ép tool để lấy JSON theo schema chạy được**; đây là đường mặc định an toàn. Structured output gốc chạy với Claude 4.x và Kimi K3, **không** chạy với Nova.
- Với model open-weight, `outputConfig` được chấp nhận nhưng chất lượng phân loại thấp hơn rõ so với ép tool (8-11/14 so với 13-14/14): với mô hình mở nên ép tool, không dùng `outputConfig`.
- Ghi chú "lần đầu biên dịch grammar mất đến khoảng 90 giây" trong bedrock.md **không tái hiện** với Haiku 4.5/Sonnet 4.6: lần đầu chỉ chậm thêm 2-3 giây với schema `IntentResult` đơn giản. Có thể chỉ đúng với schema lớn hơn hoặc với Claude 5.x; chưa thử.
- Chưa thử: schema có `minimum`/`maxLength` (để xem lỗi 400 như ghi chú) và các schema `Plan`, `Roadmap`.

## 4. Prompt caching

**Cách thử:** `04_caching.py`: system prompt tiếng Việt dài (nhiều đoạn quy tắc/ví dụ khác nhau), `{"cachePoint": {"type": "default"}}` ngay sau system, gọi 2 lần liền, đọc `usage.cacheWriteInputTokens` và `cacheReadInputTokens`. Mỗi cỡ prompt dùng nonce riêng để không dính cache của lần chạy trước. Độ dài prefix suy ra từ `usage` (CountTokens không dùng được với profile global).

| Model | Prefix system (token) | Lần 1 | Lần 2 | Cache? |
|---|---|---|---|---|
| Haiku 4.5 (SG) | ~3.875 | ghi 0, vào 3.898 | đọc 0 | **Không** |
| Haiku 4.5 (SG) | ~4.131 | ghi 4.131 | **đọc 4.131** | **Có** |
| Haiku 4.5 (SG) | ~4.298 / ~4.465 / ~4.540 / ~6.787 | ghi tương ứng | đọc tương ứng | Có |
| Sonnet 4.6 (SG, US) | ~977 | ghi 0 | đọc 0 | **Không** |
| Sonnet 4.6 (SG) | ~1.054 (US ~1.055) | ghi 1.054 | **đọc 1.054** | **Có** |
| Sonnet 4.6 (SG) | ~1.974 | ghi 1.974 | đọc 1.974 | Có |
| Nova Lite, Nova Pro (`apac.`, SG; Nova Lite cả US) | ~2.395 | ghi 2.395 | đọc 2.395 | Có |
| Nova 2 Lite (SG) | ~1.455 | ghi 1.455 | đọc 1.455 | Có |
| Kimi K3 (SG) | | `ValidationException: This model doesn't support the cachePoint field` | | Không hỗ trợ |
| Qwen3-Next-80B, DeepSeek V3.2, gpt-oss-120b, Mistral Large 3, Kimi K2.5 (US) | | `AccessDeniedException: You invoked an unsupported model or your request did not allow prompt caching` (HTTP 403) | | Không hỗ trợ |

**Ngưỡng tối thiểu quan sát được:** Haiku 4.5 nằm giữa ~3.875 (không cache) và ~4.131 (cache) token, **khớp con số 4.096 trong tài liệu**; Sonnet 4.6 nằm giữa ~977 và ~1.054, **khớp 1.024**. Prefix là phần system (không tính câu hỏi user 23 token). Giá cache cùng bảng giá (Price List): Haiku 4.5 ghi $1,25, đọc $0,10; Sonnet 4.6 ghi $3,75, đọc $0,30 mỗi 1M token (giá read = 0,1 × input).

**Kết luận:** với Haiku 4.5, router nhỏ vài trăm token sẽ **không bao giờ cache được** (cần ≥ 4.096 token); chỉ planner Sonnet 4.6 với system + định nghĩa tool ≥ 1.024 token mới có lợi. Nova cache được ở cỡ ≥ 1,4K token, không đo ngưỡng. Mô hình open-weight và Kimi K3 trên Converse **không cache**: lỗi `AccessDeniedException` khi gửi `cachePoint` rất dễ nhầm với lỗi quyền truy cập, cần bắt riêng. Bảng giá Price List có dòng "cache read/write" cho Kimi K3 qua endpoint `bedrock-mantle` (khác Converse): chưa thử.

## 5. Đọc ảnh thông báo chuyển khoản tiếng Việt

**Cách thử:** `05_make_images.py` vẽ 3 ảnh PNG 720×960 bằng Pillow (font Segoe UI, có dấu): kiểu MoMo (1.250.000đ, "tien tro thang 11" không dấu, người nhận "NGUYỄN THỊ HOÀI THƯƠNG"), kiểu ngân hàng ("-85.000 VND", "CK tien com trua + ca phe", "TRẦN ĐỨC MINH", giờ có giây), kiểu ví thương mại ("₫2.399.000", "Thanh toán đơn hàng #DH5521 - tai nghe", "Công ty TNHH Điện Máy Hoa Sen", phương thức trả sau). Ground truth trong `images/truth.json`. `05_images.py` gửi ảnh qua khối `image` của Converse, yêu cầu JSON `{amount_vnd, time, counterparty, note}`, chấm: số tiền khớp tuyệt đối; thời gian khớp `YYYY-MM-DD HH:MM`; tên khớp có dấu / khớp sau khi bỏ dấu; nội dung khớp nguyên văn (không phân biệt hoa thường). Mỗi model 3 ảnh = 3 phép thử, **mẫu rất nhỏ**.

| Model | Region | Số tiền | Thời gian | Tên: có dấu / bỏ dấu | Nội dung | Ghi chú |
|---|---|---|---|---|---|---|
| Sonnet 4.6 | SG | 3/3 | 3/3 | 3/3 / 3/3 | 3/3 | Hoàn hảo, giữ nguyên "tien tro" không dấu; 1,6 giây |
| Haiku 4.5 | SG | 3/3 | 3/3 | 3/3 / 3/3 | **1/3** | **Tự "sửa" nội dung không dấu thành có dấu sai**: `tiền trो thang 11` (lẫn ký tự Devanagari), `CK tiền com trưa + ca phê`; 1,2 giây |
| Nova Pro | SG | 3/3 | 3/3 | 0/3 / 3/3 | 3/3 | Mất dấu ở tên (2/3 ảnh), một lỗi "Diện" thay "Điện"; 1,1 giây |
| Nova 2 Lite | SG | 3/3 | 3/3 | 2/3 / 3/3 | 2/3 | Một lỗi "THƯỢNG" thay "THƯƠNG", "tại nghe"; 1,2 giây |
| Nova Lite | SG | 3/3 | 3/3 | 0/3 / 2/3 | 2/3 | Đọc dấu kém ("Nói dung", "dôn hàng", "tái nghê"); 1,0 giây |
| **Kimi K3** | SG | 3/3 | 3/3 | 3/3 / 3/3 | 3/3 | Hoàn hảo; 2,0 giây |
| Kimi K3.1 | SG | 3/3 | 3/3 | 3/3 / 3/3 | 3/3 | Hoàn hảo; 1,5 giây |
| Qwen3-VL-235B | US | 3/3 | 3/3 | 3/3 / 3/3 | 3/3 | Hoàn hảo; 1,8 giây |
| Mistral Large 3 | US | 3/3 | 3/3 | 3/3 / 3/3 | 3/3 | Hoàn hảo; 1,1 giây |
| Kimi K2.5 | US | 3/3 | 3/3 | 3/3 / 3/3 | 3/3 | Hoàn hảo; 1,6 giây |
| Gemma 3 27B | US | 3/3 | 3/3 | 3/3 / 3/3 | 3/3 | Hoàn hảo; 2,0 giây |
| Ministral 14B | US | 3/3 | 3/3 | 2/3 / 3/3 | 1/3 | Sai dấu nội dung |
| Llama 4 Maverick | US | 2/3 | 2/3 | 1/3 / 2/3 | 1/3 | 1 lần lỗi "Legacy"; kém ổn định |

**Kết luận và giới hạn:** số tiền và thời gian đúng ở mọi model có thể gọi (trừ lỗi Llama); khác biệt nằm ở dấu tiếng Việt. Ảnh thử là **ảnh dựng sạch, sắc nét**, không phải ảnh chụp màn hình thật có nén, nghiêng, chữ nhỏ, giao diện dark mode: kết quả cho thấy "đọc được", chưa chứng minh độ chính xác thực tế. Điểm đáng chú ý: Haiku 4.5 (model dự phòng của Haiku 5.5) **tự thêm dấu sai** vào nội dung chuyển khoản không dấu: nếu nội dung đi vào bước phân loại hũ, nên hạ bước này xuống Sonnet 4.6 hoặc Kimi K3/Qwen3-VL, hoặc yêu cầu "giữ nguyên ký tự, không sửa chính tả".

## 6. Embedding tiếng Việt không dấu

**Cách thử:** `06_embeddings.py`, `06b_nova_embed.py`: 43 chuỗi giao dịch hư cấu thuộc 6 hũ (ăn uống, hóa đơn, di chuyển, giải trí, tiền trọ, mua sắm), 14 "khái niệm", mỗi khái niệm 3-4 biến thể (có dấu, không dấu, viết tắt như `ck tien nuoc t11`, `cf highland`, `nf t11`). Nhúng bằng `InvokeModel`; một lời gọi Cohere gửi cả 43 chuỗi (giới hạn 96 chuỗi mỗi request ghi trong tài liệu Cohere; 43 chạy được). Ba biến thể tiền xử lý: `raw`, `stripped` (bỏ dấu, `đ` → `d`), `normalized` (bỏ dấu + chữ thường + mở rộng 8 từ viết tắt tự soạn `ck, t11, cf, tt, hd, ts, gr, nf`). Chỉ số: cosine trung bình cặp **cùng khái niệm**, cặp **cùng hũ khác khái niệm**, cặp **khác hũ**; độ chính xác láng giềng gần nhất (1-NN leave-one-out) theo hũ; ngưỡng tốt nhất. Ghi chú: tập chuỗi nhỏ, các chuỗi "điện/nước/trọ" cùng khuôn "… tháng 11" nên cố ý khó.

| Model (Region) | Tiền xử lý | Cùng khái niệm (TB, min) | Cùng hũ khác khái niệm | Khác hũ (TB, max) | 1-NN theo hũ | Ngưỡng tốt nhất (độ chính xác cân bằng) |
|---|---|---|---|---|---|---|
| Cohere Embed Multilingual v3 (SG), `search_document` | raw | 0,824 (0,65) | 0,720 | 0,705 (**0,977**) | 81,4% | 0,80 (82,3%) |
| | stripped | 0,911 (0,81) | 0,743 | 0,735 (0,977) | 83,7% | 0,81 (95,2%) |
| | normalized | 0,936 (0,81) | 0,746 | 0,737 (0,979) | 93,0% | 0,81 (95,2%) |
| Cohere v3, `classification` | raw / normalized | 0,678 / 0,877 | 0,452 / 0,495 | 0,433 / 0,481 | 79,1% / 90,7% | 0,57 / 0,605 |
| Cohere Embed v4 (SG, `global.`) | raw | 0,618 (0,26) | 0,377 | 0,334 (0,920) | 83,7% | 0,475 (92,1%) |
| | stripped | 0,755 (0,49) | 0,404 | 0,357 (0,920) | 90,7% | 0,49 (95,5%) |
| | normalized | 0,832 (0,49) | 0,417 | 0,358 (0,929) | 93,0% | 0,49 (95,6%) |
| Titan Text Embeddings V2 (**chỉ `us-east-1`**) | raw | 0,519 (0,08) | 0,156 | 0,112 (0,819) | 81,4% | 0,30 (92,9%) |
| | stripped | 0,676 (0,32) | 0,178 | 0,123 (0,819) | 93,0% | 0,315 (96,4%) |
| | normalized | 0,769 (0,36) | 0,203 | 0,133 (0,867) | **97,7%** | 0,35 (96,9%) |
| Nova 2 Multimodal Embeddings (`us-east-1`), `GENERIC_INDEX` | raw | 0,837 (0,67) | 0,714 | 0,693 (0,976) | 79,1% | 0,76 (82,0%) |
| | normalized | 0,929 (0,77) | 0,738 | 0,705 (0,983) | 93,0% | 0,77 (94,0%) |

Cặp đáng chú ý (Cohere v3 raw / Cohere v4 raw / Titan raw): `tiền nước tháng 11` với `ck tien nuoc t11`: 0,69 / 0,53 / 0,34; `highlands coffee` với `cf highland`: 0,84 / 0,53 / 0,54; `tiền trọ tháng 11` với `tien tro t11`: 0,67 / 0,52 / 0,35; `tiền điện tháng 11` với `tiền nước tháng 11` (khác khái niệm, cùng hũ hóa đơn): 0,88 / 0,82 / 0,73. Lỗi 1-NN gần như luôn là cặp "điện/nước/trọ cùng khuôn `ck tien X thang 11`" (cosine tới 0,977 ở Cohere v3, 0,92 ở v4, 0,82 ở Titan). `input_type` `search_document` và `classification` của Cohere v4 cho **kết quả giống hệt** (có vẻ bị bỏ qua).

**Nhận xét ngưỡng 0,97 trong proposal:** không hợp lý để gom "cùng nghĩa".
1. Không cặp biến thể thật nào (có dấu ↔ không dấu ↔ viết tắt) đạt 0,97 ở dạng `raw`; tối đa 0,962 (Cohere v3). Sau khi bỏ dấu, chỉ những cặp **trở thành giống hệt** mới đạt 1,0 (20% cặp cùng khái niệm); các cặp viết tắt (`ck`, `t11`, `cf`) vẫn dưới 0,97 trừ khi mở rộng viết tắt trước.
2. Ngược lại, cặp **khác hũ** cũng vượt 0,97: Cohere v3 raw 0,977 (`ck tien dien thang 11` ↔ `ck tien tro thang 11`), Nova 2 Multimodal 0,983 sau chuẩn hóa (`chuyen khoan tien nuoc thang 11` ↔ `chuyen khoan tien tro thang 11`). Cosine bị khuôn câu chi phối, tức 0,97 sẽ gộp nhầm "tiền điện/nước" với "tiền trọ".
3. Mỗi model có thang cosine khác hẳn nhau (khác hũ trung bình 0,71 ở Cohere v3, 0,33 ở v4, 0,11 ở Titan): một ngưỡng tuyệt đối không dùng được chung; ngưỡng tách tốt nhất đo được là 0,80-0,81 (v3), 0,49 (v4), 0,30-0,35 (Titan), 0,76-0,77 (Nova).
- **Đề xuất [Suy luận từ số đo]:** (a) chuẩn hóa trước (bỏ dấu, chữ thường, từ điển viết tắt) rồi so khớp **chuỗi chính xác** cho dedupe, đó mới là chỗ "0,97/1,0" đúng nghĩa; (b) dùng embedding cho phân loại bằng kNN hoặc có biên (khoảng cách tới hũ gần nhất so với hũ thứ hai) và hiệu chỉnh ngưỡng theo model trên tập nhãn thật; (c) chuẩn hóa tăng 1-NN từ ~81-84% lên 93% (Cohere v3/v4) và 97,7% (Titan v2, chỉ `us-east-1`); (d) Cohere v4 và Titan có biên rộng hơn Cohere v3 (độ chênh cùng khái niệm so với khác hũ: 0,28 / 0,41 so với 0,12). Trên tập nhỏ này v3 ở Singapore không kém nhiều sau chuẩn hóa nhưng biên hẹp nên ngưỡng nhạy hơn.

## 7. Guardrails

Bỏ qua theo yêu cầu (tạo guardrail là tạo tài nguyên).

## 8. Vai → model dùng được ngay hôm nay

Tất cả đã gọi thật. RPM là quota áp dụng cho tài khoản (mục 2a). "SG" = `ap-southeast-1`.

| Vai | Phương án chính ngay hôm nay | Phương án thay/dự phòng | RPM / TPM thực | Giá (/1M token vào / ra, Price List) | Chú ý |
|---|---|---|---|---|---|
| **LLM lớn (planner)** | **Sonnet 4.6** `global.anthropic.claude-sonnet-4-6` (SG): ép tool 14/14, structured output 14/14, cache ≥ 1.024 token | **Kimi K3** `global.moonshotai.kimi-k3` (SG, quota 10M TPM, không có dòng RPM; tool 14/14, structured output 14/14, ảnh tốt; **không cache, luôn suy nghĩ, không nhận `temperature`**); Opus 4.6 (RPM 5); `us-east-1`: Mistral Large 3, Qwen3-Next-80B, DeepSeek V3.2 | Sonnet 4.6: 6M / **10**; Kimi K3: 10M / không rõ | Sonnet 4.6 $3 / $15; Kimi K3 (global) $3 / $15; Mistral Large 3 $0,5 / $1,5; Qwen3-Next $0,14 / $1,2; DeepSeek V3.2 $0,62 / $1,85 | Chưa thử chất lượng lập kế hoạch nhiều bước, chỉ thử chọn tool và trích tham số |
| **LLM nhỏ nhanh (router, diễn giải, phân loại)** | **Haiku 4.5** `global.anthropic.claude-haiku-4-5-20251001-v1:0` (SG): ép tool 12/14, TTFT 0,4-0,9 giây | **Nova 2 Lite** (SG, 8M / **20** RPM: tool 14/14, 0,5-0,7 giây, cache được, không có structured output gốc); Nova Pro (SG, **25** RPM, tool 14/14); `us-east-1`: Nova Lite/Micro **200** RPM, Qwen3-32B/gpt-oss-120b **100** RPM | Haiku 4.5: 5M / **10**; Nova 2 Lite: 8M / 20; Nova Lite/Micro SG: 400K / 20 | Haiku 4.5 $1 / $5; Nova Lite SG $0,081 / $0,324; Nova Pro SG $1,08 / $4,32; Qwen3-32B và gpt-oss-120b $0,15 / $0,6 | Haiku 4.5 không cache được prompt ngắn (cần ≥ 4.096 token) |
| **Đa phương thức (đọc ảnh)** | **Sonnet 4.6** (SG; 3/3 mọi trường, 1,6 giây) | **Kimi K3 / K3.1** (SG, 3/3); `us-east-1`: Qwen3-VL-235B, Mistral Large 3, Kimi K2.5, Gemma 3 27B (đều 3/3, 100 RPM); Nova Pro SG (mất dấu ở tên) | như trên | như trên | Tránh Haiku 4.5 cho nội dung không dấu (tự sửa thêm dấu sai); ảnh thử là ảnh dựng sạch |
| **Embedding đa ngôn ngữ** | **Cohere Embed Multilingual v3** `cohere.embed-multilingual-v3` (SG, in-region) hoặc **Embed v4** `global.cohere.embed-v4:0` (SG) | `us-east-1`: **Titan Text Embeddings V2** (nhận 1 chuỗi/lần, 60 RPM, 1-NN 97,7% sau chuẩn hóa), Nova 2 Multimodal Embeddings | Cohere v3, v4: 300K / **20**; Titan v2: 300K / 60 | v3 $0,10; v4 $0,12 | Chuẩn hóa chuỗi trước khi nhúng; gom nhiều chuỗi/lời gọi để tiết kiệm RPM |

**`us-east-1` có tốt hơn Singapore không?** Về **RPM thì có, rõ rệt**: Nova 100-200 RPM (so với 20), mọi model open-weight 100 RPM / 100M TPM, Titan Text Embeddings V2 60 RPM, và có model đa phương thức (Qwen3-VL, Gemma 3, Mistral Large 3) mà Singapore không có. **Claude thì như nhau** (cùng 10 RPM). Đổi lại, dữ liệu xử lý tại Mỹ (cả hai Region đều đi qua profile `global.` với Claude/Nova 2/Kimi) và phải dời toàn bộ Guardrails, KB, AgentCore sang đó nếu muốn đồng bộ Region. Kimi K3 gọi được ở cả hai Region (không phải lợi thế riêng của Singapore). Đề xuất [Suy luận]: giữ Singapore làm Region chính cho demo; chỉ dùng `us-east-1` như đường dự phòng cho router/phân loại nếu bị throttle (cùng boto3, khác `region_name`).

## 9. 10 request/phút có đủ cho demo một người không?

- **Quota đo được:** Haiku 4.5 và Sonnet 4.6 mỗi model **10 RPM, hai xô riêng**. Một lượt what-if = 2 call Haiku + 2 call Sonnet. Tính theo quota: tối đa 5 lượt/phút, tức mỗi 12 giây một lượt; mỗi lượt đo được 6,3 giây, nên người dùng thật (gõ, đọc kết quả giữa các lượt) không thể vượt.
- **Đo thật [Đo]:** ba lượt liền nhau (12 call trong khoảng 19 giây, tương đương tốc độ 19 RPM mỗi model nếu kéo dài) không bị throttle. Có thể xô cho phép burst hoặc đo theo cửa sổ khác; **không đo được cơ chế chính xác** (xem mục 10: một bài đo xả liên tục bị chặn bởi bộ phân loại quyền của phiên chạy nên tôi không chạy). Throttle chỉ xuất hiện khi một agent khác dùng chung quota Haiku 4.5.
- **Kết luận [Suy luận]:** đủ cho demo một người nếu không có agent/tập dev nào khác gọi cùng lúc. Rủi ro: (1) buổi demo có nhiều người xem thao tác song song hoặc chạy bộ test 50 câu đối kháng/eval (hàng trăm call) cùng lúc, (2) retry của chính harness, (3) mỗi lượt có thêm Guardrails/KB/ảnh. Biện pháp rẻ: dùng Nova 2 Lite hoặc Nova Pro (20-25 RPM) cho router/diễn giải để giữ xô Haiku/Sonnet cho planner; chạy eval trên `us-east-1` với model 100 RPM; retry adaptive; bộ đếm lượt/phút ở tầng ứng dụng; cache planner (Sonnet ≥ 1.024 token).
- Embedding (Cohere 20 RPM, 300K TPM): đủ nếu gom batch (một lời gọi nhận cả 43 chuỗi).

## 10. Chi phí và những điều chưa thử được

**Chi phí đã tiêu [Suy luận, chưa đối chiếu Cost Explorer vì hóa đơn chậm hàng giờ]:** tổng token trong mọi file kết quả khoảng 400K token vào + 46K token ra (gồm phần cache ghi/đọc đếm như token vào). Cận trên nếu tính **mọi** token theo giá Sonnet ($3/$15) là khoảng **1,9 USD**; thực tế hầu hết là Nova, Haiku và open-weight giá thấp hơn nhiều, ước **dưới 0,3 USD**. Phần lớn nằm ở thử cache Haiku 4.5 (khoảng 50K token) và các lượt Kimi K3 (suy nghĩ ~300 token/lượt).

**Chưa thử được hoặc chưa làm:**
- **Claude Haiku 5.5, Sonnet 5.5, Sonnet 5, Opus 5.x, Fable**: bị chặn `AccessDenied`; mọi khẳng định về chúng trong bedrock.md (thinking, `tool_choice` ép, 512 token cache, structured output) **vẫn chưa kiểm**.
- **Đo RPM thực bằng cách xả liên tục**: định chạy một script bắn N lời gọi nhỏ liên tiếp (không có trong thư mục spike) nhưng bộ phân loại quyền của phiên chạy chặn, vì có thể làm nghẽn quota đang dùng chung; tôi không tìm đường vòng. Số RPM chỉ lấy từ Service Quotas và từ các lượt chạy có nghỉ.
- **Họ GPT-6/5.x (kể cả những dòng có quota > 0)**: không gọi được; nguyên nhân chưa rõ (có thể điều kiện Marketplace/entitlement). Cần chủ dự án kiểm trong console.
- **Chất lượng lập kế hoạch nhiều bước/phân tích** của Kimi K3, Mistral Large 3, Qwen3-Next, DeepSeek V3.2 (chỉ thử chọn tool và trích tham số).
- **Ảnh thật** (chụp màn hình MoMo/ngân hàng) và PDF sao kê: chỉ thử 3 ảnh dựng sạch.
- **Embedding bộ truy vấn biểu phí** cho Managed KB (embedding "MANAGED") và rerank: không thuộc spike này.
- **Prompt caching của Kimi K3 qua endpoint `bedrock-mantle`**, TTL 1 giờ, "automatic caching" qua `additionalModelRequestFields`: chưa thử.
- **Guardrails**, độ trễ guardrail, PII: bỏ qua theo yêu cầu.
- **IAM/Marketplace**: gọi bằng danh tính đang đăng nhập (không phải execution role AgentCore); chưa kiểm quyền của role triển khai thật. Lưu ý: danh tính đã dùng là gốc tài khoản; không dùng trong sản phẩm.

## 11. File và cách chạy lại

Xem `spikes/bedrock-models/README.md`. Dữ liệu thô: `results_*.json`/`results_*.txt` cùng thư mục (đã che account ID; không chứa khóa truy cập).
