# Amazon Bedrock cho Yofina Foresight: model, Guardrails, Knowledge Bases, Data Automation

Ghi chú nghiên cứu ngày 2026-11-21 để các phiên code sau làm theo, khỏi tra lại. Danh mục model, Region và giá đổi rất nhanh: trước khi chốt cấu hình, chạy lại các lệnh kiểm ở mục 5.

Quy ước nguồn gốc của từng khẳng định:
- **[Doc]** đã đọc trong tài liệu AWS chính thức hiện hành.
- **[API]** đã gọi API chỉ-đọc kiểm trên tài khoản dự án (`ListFoundationModels`, `ListInferenceProfiles`, `GetFoundationModelAvailability`, Service Quotas, Pricing, các lệnh `List*` rỗng). Không tạo, sửa, xóa gì, không gọi model.
- **[Giá]** lấy từ AWS Price List API (vùng `ap-southeast-1`) hoặc trang giá Bedrock.
- **[Blog]** blog hoặc trang bên thứ ba.
- **[Suy đoán]** của người viết, cần chạy thử.

Không ghi account ID trong file này.

## 1. Câu hỏi cần trả lời

1. Chọn model nào cho 4 vai: LLM lớn, LLM nhỏ, đa phương thức đọc ảnh tiếng Việt, embedding tiếng Việt; ID là gì, có ở Singapore không, có phải qua cross-region inference không, dữ liệu được xử lý ở đâu, xin quyền thế nào, giá ra sao.
2. Converse API: tool use, streaming, structured output, prompt caching, quota và throttling.
3. Guardrails: lọc vào/ra, che PII (STK, SĐT, tên) tiếng Việt, chặn khuyến nghị mã chứng khoán, prompt attack, gắn vào Strands, độ trễ, chi phí, có ở Singapore không.
4. Automated Reasoning checks có khả thi không.
5. Knowledge Bases: vector store nào, hybrid search, chunking, metadata filter, rerank, đồng bộ; cấu hình rẻ nhất cho 3 kho nhỏ.
6. Bedrock Data Automation (BDA) so với LLM đa phương thức đọc ảnh/PDF.
7. Chi phí một lượt what-if và cách đặt cảnh báo ngân sách.

## 2. Kết luận ngắn

1. **Ở Singapore, mọi Claude đời mới chỉ gọi được qua cross-region profile `global.*`** (không có in-region, không có geo `apac.`). Hệ quả: prompt và câu trả lời có thể được xử lý ở bất kỳ Region thương mại nào. Ngoại lệ duy nhất: Claude Sonnet 5 (đời cũ hơn) có in-region ở Singapore, giá cao hơn khoảng 10%. [API][Doc]
2. **CHẶN TIẾN ĐỘ: quota token của tài khoản dự án bằng 0** cho Claude Sonnet 5.5, Haiku 5.5, Fable 5.x, Opus 4.7 trở lên, Sonnet 5 (cả `ap-southeast-1` lẫn `us-east-1`); mặc định của AWS là 6M TPM (Sonnet 5.5) và 10M TPM (Haiku 5.5). Chỉ Sonnet 4.6 (6M TPM) và Haiku 4.5 (5M TPM) đang dùng được, và RPM của chúng chỉ 10. Phải xin tăng quota ngay tuần 1 (thao tác ghi, cần chủ dự án duyệt). [API]
   **[Đã chạy thử 2026-11-21]** Xác nhận, kèm bổ sung: gọi Haiku 5.5, Sonnet 5.5, Sonnet 5, Opus 5.5, Fable 5.2 đều trả **`AccessDeniedException` (HTTP 403) "… is not available for this account"** (không phải `ThrottlingException`), ở cả hai Region; chuỗi dự phòng phải bắt lỗi này. Tuy nhiên "chỉ Sonnet 4.6 và Haiku 4.5 dùng được" là **sai/thiếu**: còn gọi được Opus 4.6, Nova Micro/Lite/Pro, Nova 2 Lite, **Kimi K3/K3.1 ở Singapore**, và ở `us-east-1` các model open-weight (Qwen3, Mistral Large 3, DeepSeek V3.2, gpt-oss, Kimi K2.5, Gemma 3...) với quota 100 RPM. Ngược lại họ GPT-6/5.x báo quota > 0 nhưng vẫn `AccessDenied`. Bảng quota đầy đủ và bảng "vai → model dùng được ngay": [spike-bedrock-models.md](spike-bedrock-models.md) mục 2 và 8.
3. Bộ model đề xuất: **Sonnet 5.5** cho lập kế hoạch, **Haiku 5.5** cho router, diễn giải, phân loại và đọc ảnh, **Cohere Embed Multilingual v3** (in-region Singapore) hoặc **Cohere Embed v4** (global) cho embedding. Phương án dự phòng khi quota 5.5 chưa về: Sonnet 4.6 và Haiku 4.5 (đắt hơn Haiku 5.5 gấp 10 lần).
4. **Guardrails có ở Singapore, tiếng Việt được "Optimized and supported"** cho content filter, prompt attack, denied topics và PII (tầng Standard). Bắt buộc dùng guardrail profile `apac.guardrail.v1:0` (xử lý trong các Region châu Á–Thái Bình Dương). Không có loại PII riêng của Việt Nam (STK ngân hàng, CCCD): phải viết regex (regex miễn phí).
5. **Guardrails không kiểm tool result, tham số tool call và định nghĩa tool.** Proposal ghi "che PII trước khi vào LLM" cho agent dùng nhiều tool thì phần che PII trong kết quả tool và nội dung ảnh/PDF nạp vào phải do code tự làm (hoặc gọi `ApplyGuardrail` riêng trên văn bản đã trích).
6. **Automated Reasoning checks không khả thi**: chỉ tiếng Anh (Mỹ), không có ở Singapore, không hỗ trợ streaming, chỉ chế độ detect. Giữ luật suitability bằng Python; ghi "mở rộng, chưa làm" như proposal đã đặt.
7. **Knowledge Bases: khuyến nghị Managed KB** (có ở Singapore): hybrid search và rerank luôn bật, miễn phí embedding/rerank/parsing, tính $5/GB/tháng lưu trữ + $1/1.000 lượt Retrieve (chừng vài cent mỗi tháng cho 3 kho nhỏ). Chunking theo điều khoản: tách sẵn mỗi điều khoản thành một tệp và chọn "No chunking".
8. **Proposal ghi "S3 Vectors hybrid search" là đúng với API S3 Vectors gọi trực tiếp (BM25 + vector, RRF), nhưng KB tự quản lý (customer-managed) dùng S3 Vectors thì chỉ semantic**; hybrid trong KB chỉ có với Aurora (RDS), OpenSearch Serverless, MongoDB. OpenSearch Serverless có giá sàn vài trăm USD/tháng: không dùng.
9. **BDA không liệt kê tiếng Việt** trong ngôn ngữ đầu vào của tài liệu (chỉ Anh, Đức, Tây Ban Nha, Pháp, Ý, Bồ Đào Nha), tại Singapore phải qua profile `global.data-automation-v1`, và đắt hơn LLM đọc trực tiếp khoảng hai bậc. Claude trên Bedrock nhận PDF trực tiếp (tối đa 100 trang mỗi request). Đề xuất bỏ BDA khỏi MVP và cả F6 mở rộng, dùng Haiku 5.5/Sonnet 5.5 đọc ảnh và PDF.
10. Claude 5.x **bật adaptive thinking mặc định** và tính tiền token suy nghĩ như token output: phải tắt (Haiku 5.5: `thinking.type="disabled"`) hoặc hạ `effort` (Sonnet 5.5: `between_tools` + effort thấp) cho router và diễn giải, nếu không chi phí và độ trễ tăng.
11. Sonnet 5.5 và Opus 5.5 **từ chối `tool_choice` ép buộc** (chỉ `auto`/`none`): Strands tự chuyển sang structured output gốc của Bedrock. Schema Pydantic cho structured output gốc không được có `minimum`, `maxLength`, v.v. (lỗi 400); lần đầu dùng schema mới mất đến khoảng 90 giây để biên dịch grammar.
   **[Đã chạy thử 2026-11-21]** Với Haiku 4.5 và Sonnet 4.6: `toolChoice` ép tool **chạy được** (14/14 ô đúng ở Sonnet 4.6, 12/14 ở Haiku 4.5) và `outputConfig.textFormat` cũng chạy; lần đầu với schema `IntentResult` chỉ chậm thêm 2-3 giây, **không** thấy "90 giây" (chưa thử schema lớn, chưa thử Claude 5.x). Nova **không** hỗ trợ `outputConfig`; Kimi K3 hỗ trợ cả hai (14/14). Chi tiết: [spike-bedrock-models.md](spike-bedrock-models.md) mục 3.
12. Prompt caching: Sonnet 5.5 và Haiku 5.5 chỉ cần tối thiểu **512 token** mỗi điểm cache (Haiku 4.5 cần 4.096), tối đa 4 điểm, TTL 5 phút hoặc 1 giờ, đọc cache chỉ tính 5% (Sonnet 5.5) đến 10% (Haiku 5.5) giá input.
   **[Đã chạy thử 2026-11-21]** Xác nhận ngưỡng của đời 4.x: Haiku 4.5 cache được ở ~4.131 token, không cache ở ~3.875 (ngưỡng 4.096); Sonnet 4.6 cache ở ~1.054, không ở ~977 (ngưỡng 1.024); đọc cache báo đúng `cacheReadInputTokens`. Nova (Lite, Pro, 2 Lite) cache được ở ≥ 1,4K token. Kimi K3 và các model open-weight **không cache** trên Converse (lỗi `AccessDeniedException` gây nhầm khi gửi `cachePoint`). Ngưỡng 512 của Claude 5.x chưa kiểm (không gọi được). Xem [spike-bedrock-models.md](spike-bedrock-models.md) mục 4.
13. Chi phí một lượt what-if (router Haiku 5.5 + planner Sonnet 5.5 hai vòng + diễn giải Haiku 5.5 + guardrail + một lần Retrieve) ước khoảng **0,02–0,03 USD** (Sonnet 5.5 chiếm khoảng 87%). [Suy đoán trên giá thật, xem mục 3.7]
14. Cảnh báo ngân sách: AWS Budgets chậm hàng giờ và Claude tính tiền qua AWS Marketplace (hiện ở Cost Explorer dưới tên nhà cung cấp, không phải "Amazon Bedrock"); cần thêm trần token theo ngày ở tầng ứng dụng.

### Bảng vai → model đề xuất (Region gọi: `ap-southeast-1`)

| Vai | Đề xuất (ID dùng trong code) | Dự phòng | In-region ở SG? | Qua CRIS? | Giá /1M token (vào / ra) | Ghi chú |
|---|---|---|---|---|---|---|
| LLM lớn: orchestrator, planner, roadmap, analyst | `global.anthropic.claude-sonnet-5-5` | `global.anthropic.claude-sonnet-4-6` (quota đang dùng được); nâng cấp: `global.anthropic.claude-opus-5-5` ($4/$20), `global.anthropic.claude-fable-5-2` ($8/$40) | Không | Chỉ `global.` | $2 / $10 (cache ghi 5 phút $2,5; 1 giờ $4; đọc $0,10) | Ngữ cảnh 1M, ra tối đa 128K. Thinking bật mặc định |
| LLM nhỏ: router, diễn giải 2 câu, composer, phân loại giao dịch bước 3 | `global.anthropic.claude-haiku-5-5` | `global.anthropic.claude-haiku-4-5-20251001-v1:0` ($1/$5), `global.amazon.nova-2-lite-v1:0`, `apac.amazon.nova-lite-v1:0` | Không | Chỉ `global.` (Nova v1 có `apac.`) | $0,10 / $0,50 (cache ghi $0,125; đọc $0,01). Prompt trên 100K token tính giá cao hơn ($0,50/$2,50) | Rẻ nhất trong nhóm có thể tin cậy. Tắt thinking |
| Đa phương thức đọc ảnh thông báo chuyển khoản | `global.anthropic.claude-haiku-5-5` (nhận ảnh), ca khó: Sonnet 5.5 | Nova 2 Lite (ảnh, video, tài liệu), `apac.amazon.nova-pro-v1:0` | Không | Như trên | Như trên | Chưa thử chất lượng tiếng Việt trên ảnh thật (mục 5) |
| Embedding đa ngôn ngữ (phân loại bước 2, kho tri thức nếu tự quản) | `cohere.embed-multilingual-v3` (1024 chiều, 512 token, có `vi`) | `global.cohere.embed-v4:0` (256/512/1024/1536 chiều, ngữ cảnh 128K) | **Có** (v3) | v3 không; v4 chỉ `global.` | $0,10 (v3); $0,12 (v4) | Quota 20 RPM, 300K TPM, v3 không tăng được. Titan Text Embeddings V2 và Nova Multimodal Embeddings **không có** trong danh sách model của Singapore |
| Embedding cho Managed KB | Mặc định "MANAGED" (miễn phí) | Cohere (qua `embeddingModelType: CUSTOM`, 1024 chiều) | Có | Không | Không tính | Chất lượng tiếng Việt của embedding mặc định chưa tìm được tài liệu, phải thử |

Nguồn bảng: [API] ListFoundationModels/ListInferenceProfiles/Pricing; [Doc] model card của từng model.

**[Đã chạy thử 2026-11-21] Dùng được ngay hôm nay khi chưa có quota 5.5** (đã gọi thật, xem [spike-bedrock-models.md](spike-bedrock-models.md) mục 8): LLM lớn: `global.anthropic.claude-sonnet-4-6` ($3/$15; 10 RPM) hoặc `global.moonshotai.kimi-k3` ở Singapore (10M TPM, không cache, không nhận `temperature`); LLM nhỏ: `global.anthropic.claude-haiku-4-5-20251001-v1:0` (10 RPM) hoặc Nova 2 Lite/Nova Pro (20-25 RPM; ở `us-east-1` Nova Lite/Micro 200 RPM); đa phương thức: Sonnet 4.6 hoặc Kimi K3 (ảnh dựng thử đúng 3/3; Haiku 4.5 tự thêm dấu sai vào nội dung không dấu); embedding: `cohere.embed-multilingual-v3` / Embed v4 (20 RPM) hoặc Titan Text Embeddings V2 ở `us-east-1` (có trong `us-east-1`, **không** có ở Singapore: "model identifier is invalid").

## 3. Chi tiết

### 3.1. Chọn model, Region, cross-region inference, quyền truy cập

**Đã gọi API kiểm (Singapore):** `ListFoundationModels` trả 41 model, gồm Claude Opus 4.5–5.5, Sonnet 4.5/4.6/5/5.5, Haiku 4.5/5.5, Fable 5/5.1/5.2, Nova Micro/Lite/Pro/2 Lite, Cohere Embed v4, Embed English/Multilingual v3, và model OpenAI/xAI/Kimi/GLM. Chỉ có Sonnet 5 báo `ON_DEMAND` (in-region); tất cả Claude khác báo `INFERENCE_PROFILE`. Không có Titan Embed, Nova Multimodal Embeddings, Cohere Rerank trong danh sách này. Ở `us-east-1` thì có 128 model, gồm cả Titan Embed v2 và Nova Multimodal Embeddings.

**Profile hệ thống ở Singapore (`ListInferenceProfiles`):**
- Claude (Haiku 4.5, Haiku 5.5, Sonnet 4.6, Sonnet 5, Sonnet 5.5, Opus, Fable): chỉ có `global.…`. Không có `apac.…` cho Claude đời 4.x trở lên (chỉ còn lại profile `apac.` của Claude 3/3.5 cũ).
- Nova v1 (Micro, Lite, Pro): có `apac.amazon.nova-*-v1:0`, đích đến gồm `ap-southeast-1`, `ap-southeast-2`, `ap-northeast-1/2/3`, `ap-south-1`. Đây là lựa chọn duy nhất giữ dữ liệu trong châu Á–Thái Bình Dương cho LLM gọi từ Singapore.
- Nova 2 Lite: chỉ `global.amazon.nova-2-lite-v1:0` ở Singapore (geo có `us`, `eu`, `jp`).
- Cohere Embed v4: `global.cohere.embed-v4:0`. Embed Multilingual v3: in-region.

**Model card xác nhận** (Haiku 5.5, Sonnet 5.5, Fable 5.2, Opus 5.5, Haiku 4.5): hàng `ap-southeast-1` là In-Region không, Geo không, Global có. Geo của Haiku 5.5 là `us`, `ca`, `eu`, `au`, `jp` (nguồn phải là Region trong khu vực đó, Singapore không dùng được). Sonnet 5: In-Region có ở Singapore, geo là `us`, `eu`, `au`, `in`.

**Hệ quả nơi xử lý dữ liệu:**
- Global: "Bedrock routes your request to a supported commercial Region worldwide"; prompt và đầu ra có thể rời Singapore. Vùng đích của profile Haiku 4.5 gồm Mỹ, châu Âu, Trung Đông, châu Phi, châu Á–Thái Bình Dương. Nếu đích đến là Region phải opt-in, prompt/đầu ra có thể được lưu ở đó để phát hiện lạm dụng. Dữ liệu lưu của bạn (cấu hình, log) vẫn ở Region nguồn.
- Không phụ phí cross-region; giá tính theo Region nguồn; với một số model giá global còn thấp hơn geo. Giá Sonnet 5 in-region ở Singapore là $2,2/$11 so với $2/$10 của global (cao hơn 10%). [Giá]
- Muốn giữ trong châu Á–Thái Bình Dương: dùng Nova v1 qua `apac.`; hoặc đổi Region gốc sang Tokyo (`jp.anthropic.claude-haiku-5-5`) hoặc Sydney (`au.…`), nhưng khi đó Guardrails, KB, AgentCore phải chạy ở đó (chưa kiểm AgentCore). Quyết định này liên quan trực tiếp phần "Quyền riêng tư" §7 của proposal ("Region ngoài Việt Nam cần đánh giá theo Luật Bảo vệ dữ liệu cá nhân"). Bản demo chỉ dùng dữ liệu tổng hợp nên rủi ro thấp, nhưng nên ghi rõ trong tài liệu nộp.
- IAM/SCP: quyền cần cấp cho cả profile lẫn model gốc ở các Region đích; SCP chặn Region nào thì profile global/geo có thể lỗi. Chưa kiểm cú pháp IAM chính xác trong phiên này, dùng skill `aws-core:amazon-bedrock` và tài liệu "inference-profiles" khi viết CDK. [Doc, chưa chạy thử]

**Cách "xin quyền model" hiện nay** [Doc `model-access.html`]:
- Phần lớn model bật sẵn; lần gọi đầu của một model bên thứ ba tự khởi động việc đăng ký Marketplace trong nền (tối đa 15 phút, trong lúc đó lệnh gọi có thể thành công rồi lỗi `AccessDeniedException`). Vai IAM thực hiện lần gọi đầu cần `aws-marketplace:Subscribe`, `Unsubscribe`, `ViewSubscriptions`; tài khoản cần phương thức thanh toán hợp lệ.
- Model Anthropic **trước Opus 4.7** phải điền form dùng lần đầu (`PutUseCaseForModelAccess`, một lần cho tài khoản hoặc tài khoản quản lý của Organization); kiểm bằng `GetFoundationModelAvailability` (`agreementAvailability`).
- Trạng thái đã gọi kiểm cho tài khoản dự án: Sonnet 5.5, Haiku 5.5, Haiku 4.5, Nova Lite, Nova 2 Lite, Cohere Embed Multilingual v3, Embed v4 đều `authorizationStatus: AUTHORIZED`, `entitlementAvailability: AVAILABLE`, `regionAvailability: AVAILABLE`. **Nhưng "AUTHORIZED" chưa đủ để gọi được: quota token bằng 0** (xem mục 3.2).
- Claude tính tiền qua AWS Marketplace, hiện ở hóa đơn và Cost Explorer dưới tên nhà cung cấp. Việc "xin quyền" thực tế còn lại: xin tăng quota và đảm bảo vai thực thi (execution role của AgentCore Runtime) có quyền Marketplace nếu nó là bên gọi đầu tiên; an toàn hơn là gọi thử lần đầu từ quản trị viên.

**Giá** [Giá, Price List API `ap-southeast-1`, USD/1M token, bản global, tiêu chuẩn]:

| Model | Input | Output | Cache ghi 5 phút | Cache ghi 1 giờ | Cache đọc |
|---|---|---|---|---|---|
| Haiku 5.5 | 0,10 | 0,50 | 0,125 | 0,20 | 0,01 |
| Sonnet 5.5 | 2,00 | 10,00 | 2,50 | 4,00 | 0,10 |
| Opus 5.5 | 4,00 | 20,00 | 5,00 | 8,00 | 0,20 |
| Fable 5.2 | 8,00 | 40,00 | 10,00 | 16,00 | 0,20 (số lạ, kiểm lại) |
| Haiku 4.5 | 1,00 | 5,00 | 1,25 | 2,00 | 0,10 |
| Cohere Embed Multilingual v3 | 0,10 | | | | |
| Cohere Embed v4 | 0,12 | | | | |

Nova (Pricing API, hai dòng giá cho vài model nên không rõ dòng nào là global): Nova Lite v1 khoảng $0,04 vào / $0,32 ra mỗi 1M; Nova 2 Lite khoảng $0,2–0,4 vào / $3,4 ra. Tức Haiku 5.5 còn rẻ hơn Nova 2 Lite ở phía output. Trang giá nói giá đọc cache Sonnet 5.5 giảm 50% từ 2026-10-07. Có các bậc dịch vụ Priority, Flex, Reserved; model card cho thấy Sonnet 5.5 và Haiku 5.5 chỉ hỗ trợ Standard.

### 3.2. Converse API

**Cách gọi chuẩn của dự án** (Strands dùng Converse/ConverseStream của `bedrock-runtime`):

```python
from strands.models import BedrockModel
planner = BedrockModel(
    model_id="global.anthropic.claude-sonnet-5-5",   # ví dụ của chính tài liệu Strands
    region_name="ap-southeast-1",
    additional_request_fields={"thinking": {"type": "between_tools"}},  # Sonnet 5.5: tắt suy nghĩ ban đầu
    # cache_config=CacheConfig(strategy="auto"),      # import và tên có thể đổi, kiểm tài liệu Strands
)
router = BedrockModel(
    model_id="global.anthropic.claude-haiku-5-5",
    region_name="ap-southeast-1",
    additional_request_fields={"thinking": {"type": "disabled"}},       # Haiku 5.5
)
```
Nguồn: tham số `BedrockModel` [Doc, Strands `amazon-bedrock`]; giá trị `thinking` [Doc `claude-messages-adaptive-thinking`]. Hạ chi phí hơn nữa bằng `output_config.effort` (`low`, `medium`, `high`; `xhigh` và `max` không dùng được khi tắt thinking, lỗi 400).

**Thinking** [Doc]: từ Claude 5, không gửi trường `thinking` nghĩa là adaptive thinking bật, token suy nghĩ tính như output. Bảng chuẩn: Sonnet 5.5 không cho `"disabled"` (400), chỉ `"between_tools"` (tắt suy nghĩ lúc đầu ở effort ≤ high); Haiku 5.5 cho `"disabled"` (effort ≤ high); Fable 5.2 và Opus 5.5 không tắt được. `max_tokens` giới hạn cứng tổng thinking + chữ trả lời: đặt đủ lớn. Khối thinking gắn với model, tiền tố hội thoại và (Sonnet 5.5, Haiku 5.5) cả tài khoản: phát lại đúng nguyên văn, nếu không lỗi 400.

**Tool use** [Doc model card]: Sonnet 5.5 hỗ trợ tool calling phía client nhưng `tool_choice` chỉ có `auto` và `none`; có thêm "tool search" phía server. Thêm `strict: true` vào định nghĩa tool để ép tham số khớp schema.

**Streaming**: `ConverseStream`. Với Guardrails có hai chế độ (xem mục 3.3).

**Structured output** [Doc `structured-output.html`]:
- Converse: `outputConfig.textFormat` (JSON Schema Draft 2020-12 tập con). InvokeModel Claude: `output_config.format`.
- Mọi `object` phải có `additionalProperties: false`, nếu không lỗi 400.
- Không hỗ trợ: schema đệ quy, `$ref` ngoài, `minimum/maximum/multipleOf`, `minLength/maxLength`, `minItems` khác 0 hoặc 1. Pydantic `Field(ge=…, max_length=…)` sinh ra đúng các từ khóa này, nên sẽ lỗi nếu đi đường structured output gốc: để các ràng buộc ở bước kiểm bằng code.
- Tối đa 12 thuộc tính tùy chọn (đếm cả lồng nhau) và 16 thuộc tính kiểu hợp (`anyOf` hoặc `["string","null"]`). Cách lách: liệt kê vào `required` và cho phép `null`.
- Biên dịch grammar lần đầu có thể mất đến khoảng 90 giây, lưu cache 24 giờ cho cùng schema cùng tài khoản. Đặt read timeout của client ít nhất 120 giây và "gọi làm nóng" các schema `IntentResult`, `Plan`, `ScenarioSpec`, `Roadmap` ngay sau khi triển khai.
- Không dùng chung với citations của Anthropic. Phải đặt `maxTokens` đủ để JSON không bị cắt.
- Strands [Doc `structured-output-behavior`]: mặc định ép tool call; tài liệu nói Strands không ép model từ chối tool call ép buộc như Opus 5.5 và Sonnet 5.5, và với Haiku 5.5 (bỏ qua thinking khi bị ép) cũng không ép; thay vào đó yêu cầu nhà cung cấp trả đúng schema (structured output gốc). Vì vậy kiểm thử `IntentResult` trên đúng model dùng thật.

**Prompt caching** [Doc `prompt-caching.html`; Giá]:

| Model | Tối thiểu token mỗi điểm | Tối đa điểm | TTL | Trường |
|---|---|---|---|---|
| Sonnet 5.5, Haiku 5.5, Opus 5.5, Fable 5.2 | 512 | 4 | 5 phút, 1 giờ | `system`, `messages`, `tools` |
| Sonnet 5, Sonnet 4.6 | 1.024 | 4 | 5 phút, 1 giờ | như trên |
| Haiku 4.5 | 4.096 | 4 | 5 phút, 1 giờ | như trên |
| Nova 2 Lite, Nova v1 | 1K | 4 | 5 phút | `system`, `messages` |

- Anthropic: chỉ có explicit caching; yêu cầu không có điểm cache thì không được cache. Hai cách: (a) đặt `cachePoint` trong Converse: `{"cachePoint": {"type": "default"}}`, thêm `"ttl": "1h"` cho TTL 1 giờ; (b) "automatic caching": một `cache_control: {"type": "ephemeral"}` ở cấp cao nhất qua `additionalModelRequestFields` (Haiku 4.5, Sonnet 4.6, Sonnet 5, Sonnet 5.5, Haiku 5.5, Opus 5…).
- Thứ tự cache là `tools` → `system` → `messages`. Đặt điểm cache sau định nghĩa tool, sau system prompt, và (tùy chọn) sau tài liệu tham chiếu. Lookback chỉ khoảng 20 khối nội dung trước điểm cache. Mục cache TTL dài phải đứng trước mục TTL ngắn. Đừng đặt ngày giờ, tên người dùng, số dư vào phần đầu prompt: cắt đứt cache.
- Với model chỉ hỗ trợ TTL 5 phút, gửi `ttl` có thể gây `ValidationException`.
- Giá: ghi cache 5 phút bằng 1,25 lần input, 1 giờ bằng 2 lần, đọc cache bằng 0,05 lần (Sonnet 5.5: 0,10 so với 2,00) hoặc 0,10 lần (Haiku 5.5: 0,01 so với 0,10). Đọc cache không tính vào quota. 1 giờ phù hợp khi người dùng chat cách nhau hơn 5 phút.
- Cache nằm trên máy xử lý yêu cầu; với CRIS "có lúc nhu cầu cao dẫn đến ghi cache nhiều hơn" nên tỷ lệ trúng không đảm bảo. Đo bằng trường `usage` trong phản hồi (số token đọc/ghi cache).
- Strands: `cache_config` với chiến lược `auto` (hoặc `anthropic`) tự thêm điểm cache cuối system prompt trên mỗi request [Doc]. Nếu system prompt đổi mỗi lượt, tắt bằng `system_prompt_ttl=False`.
- Gợi ý cho dự án: tách rõ phần tĩnh (vai trò, schema, mô tả tool, luật suitability tóm tắt, ví dụ few-shot) lên đầu và nhớ rằng router (Haiku 5.5) và planner (Sonnet 5.5) mỗi bên có cache riêng; prompt router khó vượt 512 token nếu chỉ vài dòng, cần cộng cả định nghĩa tool và ví dụ.

**Quota và throttling** [API, Service Quotas `ap-southeast-1`, giá trị áp dụng cho tài khoản]:
- Token mỗi phút, cross-region global: Sonnet 5.5 = **0**, Haiku 5.5 = **0**, Fable 5/5.1/5.2 = 0, Opus 4.7/4.8/5/5.5 = 0, Sonnet 5 = 0 (cả in-region lẫn global). Mặc định AWS cho các model đó (xem `ListAWSDefaultServiceQuotas`): Sonnet 5.5 6.000.000, Haiku 5.5 10.000.000. Cùng giá trị 0 ở `us-east-1`: tài khoản bị hạn chế, không phải do Region. Có thể do tài khoản mới hoặc chính sách thanh toán (tài liệu nói quota phụ thuộc "lịch sử thanh toán", Region, duyệt tăng quota).
- Còn dùng được: Haiku 4.5 (5.000.000 TPM, **10 RPM**), Sonnet 4.6 (6.000.000 TPM, **10 RPM**), Opus 4.5/4.6 (khoảng 2–3M TPM, 5 RPM). Hàng RPM cho nhóm 5.5 không xuất hiện trong danh sách; chưa rõ giới hạn RPM sau khi tăng TPM.
- Khác: Nova 2 Lite global 20 RPM, 8M TPM; Cohere Embed Multilingual và Embed v4 đều 20 RPM, 300K TPM (v3 không tăng được; v4 tăng được).
- Hành động: mở Service Quotas, xin tăng cho `L-31AB82D0` (Sonnet 5.5 global TPM) và `L-F26CA8D1` (Haiku 5.5 global TPM), đồng thời xin RPM; có thể cần ticket Support. Việc này là thao tác ghi: hỏi chủ dự án trước. Chạy một lệnh Converse nhỏ sau khi quota được nâng để xác nhận (mục 5).
  **[Đã chạy thử 2026-11-21]** Lỗi thật khi quota = 0 là `AccessDeniedException` (xem kết luận 2). Chủ dự án báo không xin tăng quota được: dùng bảng "dùng được ngay hôm nay" ở trên. RPM thực của Haiku 4.5 và Sonnet 4.6 đúng 10 mỗi model (hai xô riêng); một lượt what-if (2 call Haiku + 2 call Sonnet) đo 6,3 giây, ba lượt liền nhau không bị throttle. Nova ở Singapore: 20 RPM (Micro/Lite/2 Lite), 25 RPM (Pro), mặc định AWS là 400-2.000 RPM; ở `us-east-1`: Nova Lite/Micro 200 RPM và các model open-weight 100 RPM. Embedding ở Singapore vẫn 20 RPM nhưng một lời gọi Cohere nhận được cả 43 chuỗi (tài liệu Cohere ghi tối đa 96).
- Xử lý throttling: `ThrottlingException`/`ServiceUnavailableException` → retry với backoff lũy thừa có jitter (boto3 `retries={"mode":"adaptive","max_attempts":8}`), giới hạn số vòng agent mỗi lượt (proposal đã có), và chuỗi dự phòng Sonnet 5.5 → Sonnet 4.6, Haiku 5.5 → Haiku 4.5. Cache đọc không tính vào quota nên cache tốt cũng giảm throttling. Với embedding RPM 20, gom nhiều chuỗi vào một request (Cohere nhận tối đa vài chục chuỗi mỗi lần, con số chính xác cần tra) và lưu embedding theo băm văn bản.

### 3.3. Guardrails

**Có ở Singapore, tiếng Việt được hỗ trợ.** [API: `ListGuardrails` ở `ap-southeast-1` chạy được; Doc: danh sách Region của safeguard tier có Singapore]. [Doc `guardrails-supported-languages.html`]: Vietnamese = "Optimized and supported" cho (a) content filters và prompt attacks (tầng Standard), (b) denied topics (Standard), (c) sensitive information filters (PII). Không hỗ trợ tiếng Việt: word filters (chỉ Anh/Pháp/Tây Ban Nha). Tầng Classic chỉ Anh/Pháp/Tây Ban Nha: **dùng Standard**.

**Standard tier dùng cross-region:** phải gắn guardrail profile. Từ Singapore: `apac.guardrail.v1:0` (ARN `arn:aws:bedrock:ap-southeast-1:<account>:guardrail-profile/apac.guardrail.v1:0`), đích gồm `ap-south-1`, `ap-northeast-1/2/3`, `ap-southeast-1/2`. Dữ liệu guardrail ở trong châu Á–Thái Bình Dương (khác với model global). Không phụ phí cross-region. Cấu hình guardrail vẫn nằm ở Region nguồn. [Doc `guardrails-cross-region*.html`]

**Contextual grounding check:** Standard tier chỉ có ở một số Region không gồm Singapore (yêu cầu sai Region lỗi validation); Classic chỉ tiếng Anh/Pháp/Tây Ban Nha. Không dùng cho Yofina (tiếng Việt, Singapore); "số khớp tool" đã có evaluator `NumericGrounding` riêng.

**Cấu hình đề xuất cho guardrail đầu vào + đầu ra:**

| Chính sách | Cấu hình | Ghi chú |
|---|---|---|
| Content filter | Hate, Insults, Sexual, Violence, Misconduct: HIGH hoặc MEDIUM, vào và ra | Giá $0,15 / 1.000 text unit |
| Prompt attack (jailbreak, injection, prompt leakage Standard) | Chỉ đầu vào; bắt buộc đánh dấu nội dung người dùng bằng `guardContent` | Không kiểm tool result và định nghĩa tool |
| Denied topics | "Khuyến nghị mã cổ phiếu, quỹ cụ thể hoặc tiền mã hóa": vào và ra | Tối đa 30 topic; ≤ 5 câu mẫu, mỗi câu ≤ 100 ký tự; định nghĩa ≤ 1.000 ký tự ở Standard (trang denied topics nói 200 ký tự, trang tiers nói 1.000 cho Standard: tin trang tiers, kiểm lại khi tạo). $0,15 / 1.000 text unit |
| PII (sensitive information) | Mask: `NAME`, `PHONE`, `EMAIL`, `ADDRESS`, `CREDIT_DEBIT_CARD_NUMBER`, `USERNAME`, `PASSWORD`; kèm regex | $0,10 / 1.000 text unit. Regex và word filter miễn phí |

- **Denied topic cần định nghĩa khẳng định, không phủ định** [Doc best practices]: không viết "mọi nội dung trừ…" hoặc "chặn tất cả…". Gợi ý (chưa thử): "Câu hỏi hoặc lời khuyên mua, bán, giữ một mã cổ phiếu, chứng chỉ quỹ hoặc tiền mã hóa cụ thể, có tên hoặc mã cụ thể" cùng 5 câu mẫu tiếng Việt như "Nên mua cổ phiếu VNM không?". Phần "tỷ lệ theo nhóm tài sản" vẫn được phép vì định nghĩa chỉ nhắm mã/tên cụ thể. Thứ tự topic có thể làm kết quả khác nhau: kiểm bằng bộ test 50 câu đối kháng trong proposal. Thêm luật Python chặn từ khóa mã chứng khoán làm lớp thứ hai.
- **PII ở Việt Nam:** danh sách PII có sẵn gồm tên, địa chỉ, email, SĐT, tên đăng nhập, mật khẩu, số thẻ, IBAN, SWIFT, PIN và các loại riêng của Mỹ/Canada/Anh/Ấn Độ; **không có STK ngân hàng Việt Nam hay CCCD/CMND**. Nên dùng regex tùy chỉnh (độ dài ≤ 500 ký tự mỗi regex). Gợi ý để thử, chưa kiểm: SĐT `(?:\+84|0)(?:3|5|7|8|9)\d{8}\b`; CCCD `\b\d{12}\b`; STK `\b\d{8,16}\b` (dễ trùng số tiền thô như 1200000000: chuẩn hóa số tiền có dấu chấm trước, và chỉ bật mask STK ở luồng nạp sao kê/ảnh). Tên người trong tiếng Việt (viết hoa, 2–4 âm tiết) do ML ngữ cảnh nhận ra: cần đo độ phủ trên dữ liệu thật.
- **Hành vi mask:** "Mask" thay bằng nhãn kiểu `{NAME}`; có thể "Block". Streaming chế độ async **không hỗ trợ mask PII** [Doc `guardrails-streaming.html`].
- **Giới hạn quan trọng** [Doc `guardrails-use-converse-api.html`, `guardrails-sensitive-filters.html`]: guardrail trong `guardrailConfig` **không đánh giá** `toolResult`, `toolSpec` (mô tả và schema), `toolUse.input`; chỉ đánh giá text, system prompt, `guardContent`. Hệ quả cho Yofina:
  1. Kết quả tool (số dư, giao dịch, tên đối tác) không bị che. Che PII (tên người nhận, STK) ngay trong Lambda tool trước khi trả về, như proposal dự định ở bước chuẩn hóa.
  2. Prompt injection gián tiếp qua nội dung KB hoặc ảnh/PDF nạp vào không bị prompt-attack filter bắt (KB Retrieve cũng không áp guardrail lên đoạn truy xuất). Ngoài ra "Guardrails are applied only to the input and the generated response… not applied to references retrieved from Knowledge Bases". Coi nội dung truy xuất và OCR là dữ liệu không tin cậy; chạy `ApplyGuardrail` riêng trên văn bản trích từ ảnh.
  3. Khi đã có một khối `guardContent` trong messages thì **chỉ** `guardContent` được đánh giá, mọi khối khác bị bỏ qua. Dùng `guardContent` bọc tin nhắn mới nhất của người dùng, hoặc `guardrail_latest_message=True` của Strands.
- **Gắn vào Strands** [Doc Strands `amazon-bedrock`]:

```python
BedrockModel(
    model_id="global.anthropic.claude-haiku-5-5",
    guardrail_id="<id>", guardrail_version="1",
    guardrail_trace="enabled",
    guardrail_stream_processing_mode="sync",   # "async" không mask được PII
    guardrail_latest_message=True,              # chỉ đánh giá tin nhắn người dùng mới nhất
    guardrail_redact_input=True,
)
```
  Mỗi `BedrockModel` có guardrail sẽ chạy guardrail trên mỗi lời gọi model; với agents-as-tools nên gắn ở lớp L0 (router) và L5 (composer) hoặc gọi `ApplyGuardrail` tường minh một lần ở đầu lượt và một lần ở cuối, tránh trả phí và độ trễ lặp lại ở planner/specialist.
- **Độ trễ:** tài liệu không đưa số. Chế độ sync buffer đầu ra đến khi quét xong nên làm chậm ký tự đầu (NFR đặt dưới 1,5 giây); chế độ async không làm chậm nhưng nội dung xấu có thể lọt vài đoạn đầu và mất khả năng mask. Chưa tìm được số đo: phải đo trên tiếng Việt thật (mục 5). Phương án giữ NFR: chạy `ApplyGuardrail` (INPUT) song song với router; stream đầu ra async rồi quét lại bản trọn câu trước khi đóng gói khối cuối; hoặc để sync chỉ cho đoạn văn composer ngắn.
- **Quota guardrail ở Singapore** [API]: `ApplyGuardrail` 100 request/giây (tăng được); khoảng 25 text unit/giây cho denied topics Standard; kích thước đầu vào policy tối đa 1.000 text unit (tăng được); regex tối đa 500 ký tự. 1 text unit tối đa 1.000 ký tự [kiến thức chung, chưa đọc lại trong phiên này].
- **Chi phí** [Giá, `ap-southeast-1`, trang giá]: content filter $0,15, denied topics $0,15, PII $0,10, contextual grounding $0,10, Automated Reasoning $0,17 (mỗi 1.000 text unit; theo trang giá, mục AR tính theo policy); regex/word filter miễn phí; image content filter $0,00075 mỗi ảnh. Một lượt có đầu vào 300 ký tự (1 text unit) và đầu ra 1.200 ký tự (2 text unit) đi qua cả 3 chính sách tốn khoảng $0,0012.

### 3.4. Automated Reasoning checks

**Là gì** [Doc `guardrails-automated-reasoning-checks.html`]: một thành phần của Guardrails dùng suy luận hình thức để kiểm một câu trả lời có mâu thuẫn với "policy" (tập luật logic và biến) hay không, trả về kết quả giải thích được (VALID, INVALID, TRANSLATION_AMBIGUOUS, …). Chỉ chế độ detect (trả phát hiện và phản hồi, không tự chặn).

**Tạo policy từ tài liệu:** tải tài liệu nguồn (≤ 5 MB và ≤ 50.000 ký tự) lên → AR trích luật logic và lược đồ biến, kèm báo cáo độ trung thành (fidelity report) → viết test (kịch bản sinh tự động và QnA) → lưu phiên bản bất biến → gắn vào guardrail → tích hợp qua `Converse`, `InvokeModel` hoặc `ApplyGuardrail`. Lưu ý: dịch ngôn ngữ tự nhiên sang logic dùng foundation model, nên chất lượng phụ thuộc mô tả biến.

**Ngôn ngữ và Region:** **chỉ English (US)**. GA ở `us-east-1`, `us-west-2`, `us-east-2`, `eu-central-1`, `eu-west-1`, `eu-west-3`, `ap-southeast-2` (Sydney); **không có Singapore**. Xử lý chéo Region trong địa lý của nơi gửi yêu cầu (từ Sydney thì ở Úc). Không hỗ trợ streaming, không phát hiện off-topic, không chống prompt injection. Giới hạn: hay trả `TOO_COMPLEX` với phép toán phi tuyến; độ trễ tăng theo số biến. [API] `ListAutomatedReasoningPolicies` ở Singapore trả `AccessDeniedException: Your account is not authorized to invoke this API operation`, khớp với việc chưa có ở Region này (hoặc tài khoản chưa được cấp).

**Khả thi cho hackathon?** Không. Vì (1) tiếng Anh, trong khi Composer và luật nội bộ viết tiếng Việt; (2) không ở Singapore; (3) không stream; (4) thêm độ trễ vào ngân sách 8 giây; (5) luật suitability của dự án vốn đã là Python tất định (kiểm được 100%, rẻ, trong suốt). Đề xuất: bỏ khỏi sơ đồ L4 của bản nộp hoặc ghi rõ "hướng mở rộng: dịch bộ luật sang tiếng Anh, tạo policy ở `ap-southeast-2` hoặc `us-east-1`, chạy `ApplyGuardrail` ngoại tuyến để đối chiếu với verifier Python". Nếu muốn có thứ demo, làm một policy nhỏ (3–5 luật, tiếng Anh) ở `us-east-1` để minh họa, không đưa vào đường chạy chính.

### 3.5. Knowledge Bases

**Hai loại KB hiện có** [Doc `kb-build-managed.html`]:

| | Managed KB (khuyến nghị) | Customer-managed KB |
|---|---|---|
| Vector store | Bedrock lo trọn gói | Bạn chọn và vận hành: OpenSearch Serverless, Aurora PostgreSQL (pgvector), S3 Vectors, MongoDB, Neptune Analytics, Pinecone, Redis… |
| Tìm kiếm | **Luôn hybrid** (từ khóa + ngữ nghĩa); không có semantic-only | Tùy store: hybrid chỉ với RDS/Aurora, OpenSearch Serverless, MongoDB (cần trường text lọc được); còn lại semantic |
| Rerank | Mặc định bật, mô hình do dịch vụ quản lý, miễn phí; chỉ với embedding "MANAGED"; hoặc `CUSTOM`, `NONE` | Chọn model rerank của Bedrock |
| Embedding | Mặc định miễn phí; hoặc chọn model Bedrock float32 1024 chiều | Chọn tùy ý |
| Chunking | Mặc định (≈300 token), cố định kích thước, **không chunk** | Mặc định, cố định, phân cấp, ngữ nghĩa, không chunk, Lambda tùy biến |
| Metadata filter | `equals`, `notEquals`, so sánh số, `in`, `notIn`; **không** `startsWith`, `stringContains` | Tùy store (S3 Vectors cũng không có hai toán tử trên) |
| Region | Có `ap-southeast-1` | Có |
| Tích hợp Gateway | Có (target KB của AgentCore Gateway; chỉ xác thực IAM) | Không |
| API | `Retrieve` với `managedSearchConfiguration`; `AgenticRetrieveStream` (nhiều bước, trả lời có trích dẫn) | `Retrieve`, `RetrieveAndGenerate` với `vectorSearchConfiguration` |

**Giá** [trang giá Bedrock qua WebFetch tóm tắt, chưa đối chiếu Price List]: Managed KB lưu chỉ mục $5/GB dữ liệu thô/tháng; Retrieve chuẩn $1/1.000 lời gọi; `AgenticRetrieve` $4/1.000 cộng $1/1.000 Retrieve nền; phân tích, embedding và rerank do dịch vụ quản lý: $0. Quota mặc định: 600 Retrieve/phút/KB (burst 25/giây), 300 AgenticRetrieveStream/phút/tài khoản, câu truy vấn ≤ 10.000 ký tự, 10.000 KB mỗi Region, 200 nguồn dữ liệu mỗi KB. [Doc `kb-managed-quotas.html`]

**Chi phí các vector store tự quản lý** (cho phương án B/C):
- **S3 Vectors** [Blog/tìm kiếm, giá `us-east-1` và Tokyo, không tìm được giá Singapore]: khoảng $0,06–0,066/GB-tháng lưu, $0,20–0,22/GB tải lên, khoảng $2,5–2,7 mỗi triệu truy vấn. Với vài nghìn vector là vài cent. Hỗ trợ `ENHANCED` index có hybrid riêng (xem dưới). Singapore: API `s3vectors` trả lời được ở `ap-southeast-1` [API].
- **OpenSearch Serverless** [Giá `ap-southeast-1`]: $0,283/OCU-giờ cho cả indexing và search; không ngủ về 0; tối thiểu khoảng 2 OCU ≈ $410/tháng (4 OCU khi bật dự phòng ≈ $830, suy ra từ giá giờ), lưu trữ $0,36/GB-tháng. **Quá đắt cho 3 kho nhỏ, loại.**
- **Aurora PostgreSQL + pgvector:** dự án đã có Aurora Serverless v2 (chi phí chung); KB customer-managed có hybrid với RDS. Có thể tự làm hybrid ngay trong Postgres (`tsvector` cấu hình `simple` + `pgvector`, cộng điểm theo RRF) mà không cần KB: một dịch vụ, một DB, lọc metadata bằng SQL.

**S3 Vectors hybrid trực tiếp** [Doc `s3-vectors-hybrid-search.html`, `…configuring-full-text-search.html`]: cần chỉ mục chế độ `ENHANCED`; khai báo tối đa 10 khóa metadata `textSearchConfigurations`; `PutVectors` ghi vector cùng văn bản; `QueryVectors` truyền đồng thời vector truy vấn và `queryTexts` (≤ 1.024 ký tự mỗi chuỗi) để hybrid (BM25 + vector, hợp nhất RRF). Bộ phân tích mặc định tách theo ranh giới từ Unicode, hạ chữ thường, "chạy ở hầu hết ngôn ngữ"; 10 bộ phân tích riêng ngôn ngữ không có tiếng Việt (Anh, Pháp, Tây Ban Nha, Bồ Đào Nha, Ý, Đức, Hà Lan, Trung, Nhật, Hàn): dùng bộ mặc định. Tiếng Việt viết cách âm tiết nên BM25 theo âm tiết vẫn bắt được tên sản phẩm và số liệu nhưng không dấu/có dấu sẽ không khớp nhau (chuẩn hóa văn bản trước khi lập chỉ mục và truy vấn, [suy đoán]). Giới hạn: không đổi cấu hình phân tích sau khi tạo; top-K tối đa 10.000.

**Chunking theo điều khoản:** không có chiến lược "theo điều khoản" dựng sẵn. Cách làm: biên dịch tài liệu nguồn thành một tệp Markdown/văn bản cho **mỗi điều khoản** (ví dụ `bnpl_fee_2026-11-01_dieu-5.md`), đặt chunking = **No chunking** (mỗi tài liệu là một chunk), kèm `.metadata.json`. Hạn chế đã biết: không chunk thì không có số trang trong trích dẫn; ngữ cảnh mở rộng cho bảng/hình chỉ áp khi có chunking. Với customer-managed còn có Lambda chuyển đổi tùy biến.

**Metadata và hiệu lực:** mỗi tệp `X.ext` đi kèm `X.ext.metadata.json` với `metadataAttributes`, ví dụ `{"product":"bnpl","kho":"fee","effective_from":20261101,"effective_to":99991231,"doc_type":"fee_schedule"}`. Lọc theo ngày hiệu lực bằng số (yyyymmdd) với `lessThanOrEquals`/`greaterThan` (toán tử `startsWith` không dùng được). Bộ lọc: tối đa 5 điều kiện mỗi nhóm, một cấp lồng (`andAll`, `orAll`). Với KB tự quản lý, trường lọc có thể nằm dưới `vectorSearchConfiguration.filter`; với Managed KB tài liệu chỉ nói dùng `managedSearchConfiguration` thay cho `vectorSearchConfiguration` và hai toán tử không được hỗ trợ: **chưa tìm được ví dụ cú pháp đặt `filter` trong `managedSearchConfiguration`**, thử trên KB thật.

**Đồng bộ:** `StartIngestionJob` cho nguồn S3 (tham số `knowledgeBaseId`, `dataSourceId`); theo dõi bằng `GetIngestionJob`; Managed KB có lịch `syncSchedule` và xóa có bảo vệ (`deletionProtectionConfiguration`). Đồng bộ hợp với batch tuần ("Chủ nhật đồng bộ kho tri thức"); khi biểu phí thay đổi, tăng phiên bản tệp và ghi `effective_to` cho bản cũ thay vì xóa.

**Khuyến nghị cấu hình rẻ nhất chạy được cho 3 kho nhỏ (biểu phí, kiến thức tài chính, luật suitability):**
- **A (chọn mặc định): một Managed KB, ba nguồn dữ liệu S3 (hoặc một bucket ba tiền tố)**, embedding mặc định "MANAGED", rerank mặc định, metadata `kho` ∈ {`fee`, `knowledge`, `suitability`} và lọc `equals` theo kho. Ước chi phí: dưới 0,1 GB dữ liệu thô ≈ dưới $0,5/tháng lưu chỉ mục + $1 mỗi 1.000 Retrieve (một lượt có gọi `knowledge.search` ≈ $0,001). Ưu điểm: không hạ tầng, hybrid và rerank miễn phí, gắn được vào Gateway. Rủi ro: không điều khiển được chunking ngoài ba chế độ (đã giải quyết bằng tách tệp), chất lượng embedding/rerank tiếng Việt chưa có số liệu, chưa kiểm cú pháp bộ lọc.
- **B (nếu A truy xuất tiếng Việt kém):** S3 Vectors `ENHANCED` + Cohere Embed Multilingual v3 tự nạp bằng một Lambda (chunk theo điều khoản, hybrid BM25 + vector trong cùng truy vấn). Chi phí vẫn vài cent. Code nhiều hơn: tự embed, tự đồng bộ, không có rerank sẵn (tự gọi Cohere Rerank qua Bedrock nếu có ở Region; Rerank không có trong danh sách model Singapore [API]).
- **C:** pgvector và tsvector trong Aurora (không thêm dịch vụ). Hợp nếu muốn một nơi cho cả `transactions` embedding và kho tri thức.
- Cả ba kho có thể là 3 KB riêng, nhưng một KB với metadata `kho` rẻ và gọn hơn (giới hạn 10.000 KB mỗi Region không phải vấn đề).

**API Retrieve (Managed KB), ví dụ tối thiểu** [Doc `kb-test-retrieve.html`]:

```json
{ "retrievalQuery": {"text": "Phí dịch vụ Ví Trả Sau mỗi tháng là bao nhiêu"},
  "retrievalConfiguration": {"managedSearchConfiguration": {"rerankingModelType": "MANAGED"}} }
```
Lưu ý quan trọng với kiến trúc proposal: "số để tính không đi qua RAG" là hợp lý; KB chỉ trả câu trích để giải thích, và không bị guardrail kiểm (xem 3.3).

### 3.6. Bedrock Data Automation (BDA) so với LLM đa phương thức

**Cách làm với BDA (sao kê PDF):** tạo blueprint (tập trường cần lấy: ngày, mô tả, số tiền, số dư, kèm danh sách/bảng; mỗi trường có hướng dẫn và kiểu trích `explicit` hoặc `inferred`) gắn vào một project; gọi `InvokeDataAutomationAsync` (S3 đầu vào/đầu ra, `dataAutomationProfileArn`) rồi theo dõi trạng thái, đọc JSON ở S3. [Doc `bda-*.html`]

**Giới hạn và Region** [Doc `bda-limits.html`, `bda-cris.html`]:
- Có ở Singapore. Bắt buộc cross-region; **từ Singapore chỉ có profile `global.data-automation-v1`** (opt-in, phải ghi ARN này trong IAM; dữ liệu có thể xử lý ở mọi Region thương mại; dữ liệu lưu vẫn ở Region nguồn).
- **Ngôn ngữ đầu vào tài liệu: English, German, Spanish, French, Italian, Portuguese. Tiếng Việt không có trong danh sách.** Hướng dẫn trong blueprint có thể viết bằng các ngôn ngữ được hỗ trợ.
- Tệp: PDF, TIFF, JPEG, PNG (DOC/DOCX chỉ async); async tối đa 500 MB, 3.000 trang khi bật splitter; sync 10 trang, 50 MB; ảnh 5 MB (JPEG/PNG); PDF không có mật khẩu; chữ tối thiểu cao 15 pixel; không hỗ trợ chữ dọc. Blueprint tối đa 100 trường lá, 30 trường lá kiểu danh sách, mô tả trường ≤ 600 ký tự, 40 blueprint mỗi project.
- Quota ở tài khoản: 5 job document đồng thời (tăng được), 1.800 job mở.

**Giá** [Giá, `ap-southeast-1`]: tài liệu: chuẩn $0,01/trang, tùy biến theo blueprint $0,04/trang (+ $0,0005 mỗi trường mỗi trang theo dòng "AddOnFields"); ảnh: chuẩn $0,003, tùy biến $0,005.

**LLM đa phương thức đọc trực tiếp:**
- Ảnh: Claude nhận ảnh qua khối `image` của Converse; Bedrock không giới hạn số và kích cỡ ảnh nhưng Claude có giới hạn riêng (ví dụ 8000×8000 px) [Doc `inference-api-restrictions.html`].
- PDF: Converse khối `document`: tối đa 5 tài liệu mỗi request; với Claude 4 trở lên không áp trần 4,5 MB cho PDF; Claude tối đa 100 trang PDF mỗi request. PDF dạng văn bản: nên trích văn bản bằng thư viện (miễn phí) rồi mới đưa LLM; PDF quét: đưa nguyên PDF cho Claude.
- Chi phí ước: một trang sao kê khoảng 1.500–3.000 token vào + 1.000–1.500 token JSON ra: Haiku 5.5 khoảng $0,0008–0,0015 mỗi trang so với $0,04 của BDA tùy biến (chênh khoảng 30–50 lần). [Suy đoán trên giá thật]
- Độ tin cậy trích xuất: không có điểm tin cậy từng trường như BDA; bù bằng kiểm tất định (số dư đầu + phát sinh = số dư cuối, tổng các dòng, định dạng ngày) và để LLM tự gán `confidence` kèm lý do; dòng không khớp đưa vào hàng chờ xác nhận như thiết kế F6.

**Kết luận mục 3.6:** cho MVP (ảnh thông báo + CSV): dùng Haiku 5.5 đọc ảnh, structured output theo schema `ExtractedTransactions`. Cho sao kê PDF (phần mở rộng): vẫn dùng Claude đọc PDF trực tiếp, trừ khi thử nghiệm cho thấy BDA đọc tiếng Việt chấp nhận được (chưa kiểm, và tài liệu không liệt kê). Sửa dòng "Tài liệu: Bedrock Data Automation" trong §8 và nhánh "PDF → BDA" trong §10.6.

### 3.7. Chi phí một lượt what-if và cảnh báo ngân sách

**Giả định (suy đoán, chỉnh sau khi có trace thật):** router Haiku 5.5: 1.500 token tĩnh (đọc cache) + 300 token mới, ra 150; planner Sonnet 5.5 chạy hai vòng: vòng 1: 4.000 token tĩnh (đọc cache) + 1.000 mới, ra 800 (gồm suy nghĩ); vòng 2: 5.000 đọc cache + 2.000 token kết quả tool mới, ra 500; diễn giải Haiku 5.5: 1.000 đọc cache + 1.000 mới, ra 400; guardrail 3 text unit qua 3 chính sách; 1 lần Retrieve.

| Thành phần | Tính | USD |
|---|---|---|
| Router (Haiku 5.5) | 1.500×0,01 + 300×0,10 + 150×0,50 (đơn vị: /1M) | 0,00012 |
| Planner vòng 1 (Sonnet 5.5) | 4.000×0,10 + 1.000×2 + 800×10 | 0,0104 |
| Planner vòng 2 (Sonnet 5.5) | 5.000×0,10 + 2.000×2 + 500×10 | 0,0095 |
| Diễn giải (Haiku 5.5) | 1.000×0,01 + 1.000×0,10 + 400×0,50 | 0,00031 |
| Guardrail | 3 text unit × ($0,15+$0,15+$0,10)/1.000 | 0,0012 |
| Knowledge Base Retrieve | $1/1.000 | 0,001 |
| **Tổng** | | **≈ 0,023** |

Khoảng 0,02–0,03 USD/lượt (≈ 570 VND ở tỷ giá 25.000 đ/USD), 1.000 lượt ≈ 23 USD. Planner chiếm khoảng 87%; đổi planner sang Fable 5.2 nhân khoảng 4 (≈ $0,09); Opus 5.5 nhân 2. Đòn bẩy giảm: giảm đầu ra thinking (`effort` thấp), cache đúng cách (lần ghi cache đầu có giá 1,25×), rút gọn kết quả tool trả về LLM, bỏ guardrail khỏi vòng planner. F3 "kiểm tra trước khi quẹt" chỉ dùng Haiku 5.5 viết hai câu ≈ $0,0005 mỗi lượt (không cần guardrail denied topics ở bước này vì chỉ diễn giải số).

**Đặt cảnh báo ngân sách (không đặt thật trong phiên này, chỉ ghi cách làm):**
1. **AWS Budgets** loại cost budget theo tháng, ngưỡng 50/80/100% thực tế và 100% dự báo, gửi email/SNS. Claude tính tiền qua Marketplace: lọc theo tên nhà cung cấp/dịch vụ của Claude trong Cost Explorer, không phải "Amazon Bedrock" [Doc model card, mục Pricing]; kiểm bộ lọc trước khi tin số.
2. **Application inference profile** (có hỗ trợ cho Converse, và model card ghi có cho Sonnet 5.5, Haiku 5.5) gắn thẻ `app=yofina`, `env=hackathon`; kích hoạt "cost allocation tags" (mất tới 24 giờ, không hồi tố). Chi tiết nhỏ nhất là theo ngày theo loại sử dụng; muốn token từng lượt dùng nhật ký gọi model kết hợp metadata theo request. [Doc `cost-mgmt-application-inference-profiles.html`] Lưu ý: dùng profile ứng dụng thì ID trong code là ARN profile thay cho `global.…`; cần kiểm profile ứng dụng được tạo trên profile global (chưa kiểm).
3. **CloudWatch**: số liệu `InputTokenCount`/`OutputTokenCount` theo `ModelId` trong namespace `AWS/Bedrock` (kiến thức chung, chưa kiểm trong phiên này) cùng alarm; dashboard chi phí/lượt theo proposal §9.
4. **Trần ứng dụng (quan trọng vì Budgets chậm)**: bộ đếm token/USD theo người dùng và theo ngày (DynamoDB hoặc Aurora), chặn mềm tại ngưỡng, và chuỗi dự phòng sang mô hình rẻ hơn; đưa vào "ngân sách lượt" của orchestrator.

## 4. Khuyến nghị cho Yofina, chỗ proposal cần chỉnh

| Chỗ trong proposal | Chỉnh |
|---|---|
| §8–§9: "LLM lớn / LLM nhỏ" chưa gọi tên | Ghi `global.anthropic.claude-sonnet-5-5` và `global.anthropic.claude-haiku-5-5`; dự phòng Sonnet 4.6 và Haiku 4.5 (quota hiện dùng được); đa phương thức: Haiku 5.5 (ca khó Sonnet 5.5); embedding: Cohere Embed Multilingual v3 (in-region) |
| §7 Quyền riêng tư (Region ngoài Việt Nam) | Nêu rõ: tại Singapore, Claude 5.x chỉ chạy qua profile global, prompt có thể được xử lý ở Region khác; Guardrails chạy trong châu Á–Thái Bình Dương (`apac.guardrail.v1:0`); dữ liệu demo là tổng hợp. Nếu cần giữ trong khu vực: Nova v1 `apac.`, hoặc đổi Region gốc sang Tokyo/Sydney |
| §11 "S3 Vectors hybrid search" | Hybrid chỉ có khi gọi thẳng API S3 Vectors (`ENHANCED`), hoặc dùng Managed KB. KB tự quản lý + S3 Vectors là semantic-only. Chọn Managed KB làm mặc định |
| §9 Guardrail #1 "che thông tin định danh trước khi vào LLM" | Guardrails không kiểm tool result/tool args/nội dung KB; che PII ở tầng Lambda tool và bước nạp dữ liệu; thêm regex Việt Nam (SĐT, CCCD, STK) vì không có loại PII Việt Nam dựng sẵn |
| §9 Guardrail #4 và L4 "Automated Reasoning checks" | Giữ nhãn "mở rộng" nhưng ghi rõ không khả thi hiện nay: chỉ tiếng Anh, không có Singapore, không stream. Verifier Python là đường chính |
| §8 bảng "Tài liệu: Bedrock Data Automation", §10.6 nhánh "PDF → BDA" | BDA không liệt kê tiếng Việt, qua profile global, đắt hơn khoảng 30–50 lần; đổi thành "Claude đọc PDF/ảnh trực tiếp (structured output)" và kiểm tất định số dư |
| §5 NFR độ trễ (ký tự đầu < 1,5 giây) | Guardrail sync có thể làm chậm; thiết kế `ApplyGuardrail` song song và đo thật |
| §5 NFR chi phí | Thêm: tắt/hạ thinking của Claude 5.x, trần token theo ngày, ước lượng 0,02–0,03 USD/lượt what-if |
| §13/§15 rủi ro và kế hoạch tuần 1 | Thêm việc "xin tăng quota Bedrock (Sonnet 5.5, Haiku 5.5, RPM, Cohere Embed)" là việc đầu tuần 1 vì có thể mất nhiều ngày; điều kiện chặn demo nếu chậm |
| §9 RAG "chia đoạn theo điều khoản" | Làm bằng cách tách tệp theo điều khoản + No chunking + metadata `product`, `effective_from`, `effective_to` (số yyyymmdd) |

## 5. Điều chưa chắc / cần chạy thử

1. **Gọi thử model thật sau khi quota được nâng** (một lệnh `converse` rất nhỏ cho Sonnet 5.5, Haiku 5.5 từ `ap-southeast-1`): xác nhận lỗi hiện tại là gì khi quota 0 (chưa gọi nên không biết là `ThrottlingException` hay `AccessDeniedException`). Giá trị RPM sau khi tăng.
   **[Đã chạy thử 2026-11-21]** Trả lời nửa đầu: `AccessDeniedException` (HTTP 403). Nửa sau (RPM sau khi tăng) vẫn mở: chưa có quota. Xem [spike-bedrock-models.md](spike-bedrock-models.md) mục 1.
2. Chất lượng **đọc ảnh thông báo chuyển khoản tiếng Việt** của Haiku 5.5, Sonnet 5.5, Nova 2 Lite/Nova Pro: cần bộ ảnh mẫu (ảnh chụp màn hình thông báo MoMo/ngân hàng) và đo độ chính xác trường số tiền, người nhận, lời nhắn, ngày giờ.
   **[Đã chạy thử 2026-11-21]** Làm một phần: 3 ảnh dựng sạch (không phải ảnh chụp thật). Số tiền và thời gian đúng 3/3 ở Sonnet 4.6, Haiku 4.5, Nova Pro, Nova 2 Lite, Nova Lite, Kimi K3/K3.1, Qwen3-VL, Mistral Large 3, Gemma 3 27B; khác biệt ở dấu tiếng Việt (Haiku 4.5 sai nội dung không dấu 2/3 ảnh; Nova Lite đọc dấu kém). Haiku 5.5/Sonnet 5.5 chưa thử được. Xem [spike-bedrock-models.md](spike-bedrock-models.md) mục 5.
3. Chất lượng **embedding tiếng Việt**: embedding "MANAGED" của Managed KB (ngôn ngữ chưa tìm được trong tài liệu), Cohere v3 và v4; cần bộ 30–50 truy vấn tiếng Việt về biểu phí. Độ phủ của rerank mặc định cũng chưa rõ.
   **[Đã chạy thử 2026-11-21]** Làm một phần, cho phân loại giao dịch (không phải truy vấn biểu phí, không phải embedding MANAGED): 43 chuỗi/6 hũ; Cohere v3 1-NN 81,4% (raw) → 93% (sau chuẩn hóa bỏ dấu + mở rộng viết tắt); Cohere v4 83,7% → 93%; Titan v2 (chỉ `us-east-1`) 81,4% → 97,7%. Ngưỡng cosine 0,97 của proposal không hợp lý để gom cùng nghĩa (biến thể thật không đạt, cặp khác hũ lại vượt): xem [spike-bedrock-models.md](spike-bedrock-models.md) mục 6.
4. Cú pháp bộ lọc metadata trong `managedSearchConfiguration` (hai toán tử không hỗ trợ đã rõ, nơi đặt `filter` chưa thấy ví dụ).
5. **Độ trễ thêm của Guardrails** với tiếng Việt ở chế độ sync/async và ảnh hưởng lên ký tự đầu; độ chính xác của PII (tên người Việt, STK) và denied topic mã chứng khoán trên bộ test đối kháng 50 câu.
6. Cú pháp IAM/SCP cho profile `global.` và `apac.guardrail.v1:0`; quyền Marketplace của execution role; có tạo được application inference profile trên profile global hay không.
7. Strands: tên import và tham số `CacheConfig`; việc tắt thinking truyền qua `additional_request_fields` có đi đúng vào Converse; hành vi structured output của Haiku 5.5 khi không ép tool.
8. **Giá** [Đã chạy thử 2026-11-21: Price List `AmazonBedrock`, Singapore: Nova Micro $0,047/$0,188, Nova Lite $0,081/$0,324, Nova Pro $1,08/$4,32, Kimi K3 global $3/$15, Claude Haiku 4.5 $1/$5, Sonnet 4.6 $3/$15 mỗi 1M token vào/ra; `us-east-1`: Mistral Large 3 $0,5/$1,5, gpt-oss-120b và Qwen3 32B $0,15/$0,6, DeepSeek V3.2 $0,62/$1,85, Kimi K2.5 $0,6/$3; dòng giá Nova 2 Lite không tìm thấy trong lần tra này]: Nova có hai dòng giá không rõ ngữ cảnh; giá Managed KB ($5/GB, $1/1.000) lấy từ trang giá qua tóm tắt; giá S3 Vectors ở Singapore chưa tìm được; giá đọc cache Fable 5.2 trông bất thường. Giá Automated Reasoning "mỗi policy" hay mỗi text unit chưa rõ. Chạy lại Price List/trang giá chính thức trước khi viết con số vào tài liệu nộp.
9. Quota Guardrails đã lấy từ Service Quotas nhưng đơn vị "text unit" (1.000 ký tự) chưa đọc lại trong phiên này.
10. Titan Text Embeddings V2 không có trong `ListFoundationModels` Singapore dù Price List có dòng giá `APS1`: có thể có nhưng bị ẩn hoặc chưa mở cho tài khoản; không dùng.
11. Phạm vi chưa kiểm: AgentCore (Runtime, Gateway, Memory) ở Singapore và việc nó gọi model qua profile global; việc đó thuộc agent nghiên cứu khác.

Lệnh kiểm gợi ý (chỉ đọc): `ListFoundationModels`, `ListInferenceProfiles(typeEquals=SYSTEM_DEFINED)`, `GetFoundationModelAvailability`, `service-quotas:GetServiceQuota` với mã `L-31AB82D0`, `L-F26CA8D1`, `pricing:GetProducts` (service code `AmazonBedrockFoundationModels` và `AmazonBedrock`, lọc `regionCode`).

## 6. Nguồn (truy cập 2026-11-21)

Tài liệu AWS:
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5-2.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-amazon-nova-multimodal-embeddings.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-cohere-embed-v4.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-cohere-embed-multilingual.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/claude-messages-adaptive-thinking.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/inference-api-restrictions.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-supported-languages.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-tiers.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-cross-region.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-cross-region-support.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-prompt-attack.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-denied-topics.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-streaming.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-use-converse-api.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-automated-reasoning-checks.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/kb-build-managed.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-create.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-regions.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/kb-managed-quotas.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-retrieve.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/kb-test-config.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/kb-chunking.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/kb-gateway-target.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-hybrid-search.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-configuring-full-text-search.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-regions-quotas.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/bda-limits.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/bda-cris.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/cost-mgmt-application-inference-profiles.html
- https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock/index.md (qua AWS MCP search)
- https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock-prompt-caching/index.md (qua AWS MCP search)
- https://strandsagents.com/docs/user-guide/sdk/agents/structured-output-behavior/index.md (qua AWS MCP search)

Giá và trang bên ngoài:
- https://aws.amazon.com/bedrock/pricing/ (qua WebFetch, nội dung bị cắt ở 100.000 ký tự và tóm tắt)
- AWS Price List API (`AmazonBedrockFoundationModels`, `AmazonBedrock`, `AmazonES`), vùng `ap-southeast-1`
- https://docs.cohere.com/docs/cohere-embed (Embed Multilingual v3 có tiếng Việt, 1024 chiều, 512 token; Embed v4: 256/512/1024/1536 chiều, ngữ cảnh 128K)
- Giá S3 Vectors: https://aws.amazon.com/about-aws/whats-new/2026/06/s3-vectors-reduces-query-charges-80-percent-large-indexes và https://dev.classmethod.jp/en/articles/20260616-s3-vectors-query-charges/ (bên thứ ba, giá Tokyo và `us-east-1`)

Lời gọi API chỉ-đọc đã dùng (kết quả ghi ở các mục trên): `bedrock:ListFoundationModels`, `ListInferenceProfiles`, `GetFoundationModel`, `GetFoundationModelAvailability`, `ListGuardrails`, `ListAutomatedReasoningPolicies` (bị từ chối), `bedrock-agent:ListKnowledgeBases`, `s3vectors:ListVectorBuckets`, `bedrock-data-automation:ListBlueprints/ListDataAutomationProjects`, `service-quotas:ListServiceQuotas/ListAWSDefaultServiceQuotas/GetServiceQuota`, `pricing:GetProducts`, và `get_regional_availability`. Cả 4 danh sách `List*` của Guardrails, KB, S3 Vectors, BDA đều trả rỗng: tài khoản chưa có tài nguyên nào.
