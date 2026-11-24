# Thiết kế bộ nhớ dài hạn (AgentCore Memory) và quyền riêng tư — phase 5, luồng B

Viết ngày 24/11/2026 bởi worker `p5-memory` (Kiro, Claude Opus 5.5). Chưa deploy, chưa gọi AgentCore thật: mọi kiểm tra là unit test với
client giả và với model dịch vụ của botocore 1.44.9 (Stubber kiểm tham số theo đúng shape của API), cộng `cdk synth` cục bộ.

Sửa 24/11 chiều (worker `p5/fix-agent2`, Kiro, Claude Opus 5.5) cho khớp code sau `p5/fix-mem` và `p5/fix-agent2`: 2.2 (ngôn ngữ, đề xuất override), 2.4 (chỉ ghi câu người dùng), 2.5 (đọc hết sở thích, khử trùng, đã nối Analyst và người viết), 2.10 (tóm tắt `FULL_SESSION`, dấu thời gian, `ListSessions`), mục 3.

**Sửa 25/11 (worker `p5/fix-agent3`, Kiro, Claude Opus 5.5): sửa gốc chiến lược bộ nhớ.** Mục 0 (luồng mới), 1 (nguồn), 2.2 (built-in with
overrides, bỏ tóm tắt phiên), 2.4 (chính sách ghi), 2.5 (khối prompt có cấu trúc, chỉ dẫn trung tính), 2.10 (`GET /memory` khử trùng, mẩu
nhãn rỗng), 2.12, 2.13, mục 3. Chủ dự án yêu cầu không chặn câu chữ trong mã (lọc cụm "theo điều bạn đã dặn", verifier bắt câu): lỗi được
sửa ở thiết kế bộ nhớ và prompt.

Mã: `agent/src/yofina_agent/memory.py` (đọc, ghi, chính sách, ý định `memory`, khối prompt), `writer.py` (`MEMORY_GUIDE`), `whatif.py`
(`ANALYST_MEMORY_GUIDE`), `turn.py` (`Turn.memory_block`), `gateway/tools/ledger/yofina_ledger/memory_store.py` (xem, xóa,
`quiet_hours`), `gateway/tools/ledger/yofina_ledger/privacy_rest.py` (REST `/memory*`, `/me/delete-data*`), `infra-cdk/lib/memory.ts`
(Memory, strategy, chỉ dẫn trích xuất, alarm, IAM, route). Hàm chữ dùng chung: `libs/yofina_core/src/yofina_core/memory_text.py`. Hợp
đồng: `libs/yofina_core/src/yofina_core/memory.py`, `privacy.py`, `contracts/rest/openapi.yaml`, migration `0053`.

## 0. Luồng bộ nhớ (sau 25/11)

| Bước | Làm gì | Ở đâu | Vì sao |
|---|---|---|---|
| Ghi gì | Chỉ câu của người dùng, đã che PII, tên người khác, số tiền; chỉ lượt đã qua Guardrail đầu vào; không ghi lượt hỏi đáp thuần (tra cứu, what-if, kiểm tra trước khi chi, chống chịu, cú sốc, thói quen, biểu phí), ngoài phạm vi, nạp tệp, chuyển tiền, câu "bạn nhớ gì về mình", câu có dấu hiệu tấn công prompt | `memory.skip_reason`, `AgentMemory.ingest_request` (sau `RUN_FINISHED`, `IngestData`) | 2.4 |
| Trích gì | Strategy sở thích và strategy sự thật, "built-in with overrides" cho bước trích xuất: chỉ điều người dùng KHẲNG ĐỊNH về bản thân (sở thích; hoàn cảnh, kế hoạch), bỏ câu hỏi và what-if, không số tiền hay số tài khoản, không tên người khác, sự thật không lặp sở thích, viết tiếng Việt; giữ chữ giới hạn thời gian của người dùng, câu đổi ý hay rút lại viết thành lời khẳng định đầy đủ về cùng một điều, lý do từ chối đề xuất là lời khẳng định (P0-3). Hợp nhất giữ mặc định. Không còn tóm tắt phiên | `infra-cdk/lib/memory.ts` (`USER_PREFERENCE_EXTRACTION_PROMPT`, `SEMANTIC_EXTRACTION_PROMPT`, `CHANGE_AND_SCOPE_RULES`) | 2.2 |
| Đọc gì | Mọi sở thích (`ListMemoryRecords`) và tối đa 3 sự thật liên quan tới câu hỏi (`RetrieveMemoryRecords`), song song với router, hạn 1,2 giây; khử trùng sở thích với sự thật | `AgentMemory.recall` | 2.5 |
| Dùng ở bước nào | Người viết câu trả lời (các việc trong `MEMORY_TASKS`) và Analyst của what-if, dưới dạng khối JSON có cấu trúc (`so_thich[{noi_dung, hu, ngay_ghi}]`, `dieu_da_ke[{noi_dung, ngay_ghi}]`); `hu` là hũ thật do mã đối chiếu tên. Chỉ dẫn cách dùng nêu mục đích, lý do, giới hạn, không câu mẫu, và chỉ đi kèm khi khối khác rỗng (system prompt không nói về bộ nhớ). Không vào router (đọc song song), không vào bản gọn (không thành căn cứ số tiền). Ý định `memory` kể lại bản ghi; bản tin đọc `quiet_hours` | `MemoryContext.prompt_block` (`PROMPT_NOTICE`), `Turn.memory_block`, `writer.MEMORY_GUIDE`, `whatif.ANALYST_MEMORY_GUIDE` | 2.5 |
| Hiển thị, xóa | `GET /memory` cùng hàm khử trùng với agent, bỏ mẩu nhãn rỗng; `DELETE /memory*`, "Xóa dữ liệu của tôi" | `memory_store.py` | 2.10 |
| Đánh giá | Ca DÙNG nạp bản ghi trước bằng `BatchCreateMemoryRecords`, ca GHI chờ đúng bản ghi mong đợi; chấm hành vi (trạng thái `GET /memory`, hũ của phương án, judge cho việc gán điều không có) | `evals/run.py`, `evals/golden/phase5.jsonl` | 2.14 |

## 1. Nguồn đã tra (24/11/2026; tra lại và bổ sung 25/11/2026)

| Chủ đề | Nguồn | Điều dùng |
|---|---|---|
| Best practice | [best-practices](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/best-practices.html) | Mã hóa mặc định bằng khóa AWS sở hữu; chống memory poisoning bằng "sanitize the user input data with guardrails prior to persistence to memory"; least privilege với điều kiện IAM |
| Namespace | [specify-long-term-memory-organization](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/specify-long-term-memory-organization.html) | Dạng chuẩn có `/` đầu và cuối, dùng cùng giá trị ở strategy, `namespace`/`namespacePath` khi đọc, và condition key IAM |
| Strategy | [memory-strategies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-strategies.html), [built-in-strategies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/built-in-strategies.html), [long-term-configuring-built-in-strategies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-configuring-built-in-strategies.html), [user-preference-memory-strategy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/user-preference-memory-strategy.html), [summary-strategy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/summary-strategy.html) | Mỗi strategy là chỉ dẫn + output schema; "Built-in overrides: ... Allows modification of prompts while still using AgentCore managed extraction pipeline ... Lower cost for storage than built-ins"; sở thích trả JSON `{context, preference, categories}` |
| Prompt dựng sẵn (tra lại 25/11) | [memory-system-prompt](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-system-prompt.html), [memory-user-prompt](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-user-prompt.html), [memory-summary-prompt](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-summary-prompt.html) | Sự thật: "Extract information from BOTH user messages AND JSON payloads. Use assistant messages only as supporting context"; khối `<language_requirement>` nằm trong phần CHỈ DẪN. Sở thích: cho suy ra sở thích ngầm từ "repeated inquiries"; khối `<language_requirement>` nằm trong phần OUTPUT SCHEMA (không sửa được) |
| Override | [memory-custom-strategy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-custom-strategy.html) | Sự thật và sở thích override được bước Extraction và Consolidation, tóm tắt chỉ Consolidation; "We strongly recommend you use the built-in strategies instructions as a starting point"; "The content of `appendToPrompt` replaces the default instructions"; "Do not modify schemas in prompts"; cần `memoryExecutionRoleArn`; "LLM usage for extraction and consolidation will be charged separately" |
| Dung lượng Bedrock | [bedrock-capacity](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-capacity.html) | Gọi model trong tài khoản, ăn quota Bedrock của tài khoản; "If Amazon Bedrock calls are throttled due to quota limits, memory ingestion operations might fail" |
| Quyền của execution role | [AmazonBedrockAgentCoreMemoryBedrockModelInferenceExecutionRolePolicy](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonBedrockAgentCoreMemoryBedrockModelInferenceExecutionRolePolicy.html) | Policy mẫu của AWS cho phép `bedrock:InvokeModel*` trên `foundation-model/*` VÀ `inference-profile/*`: inference profile dùng được làm `modelId`. Dự án cấp hẹp hơn (đúng một model) |
| API override | [CustomConfigurationInput](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_CustomConfigurationInput.html), [SemanticOverrideExtractionConfigurationInput](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_SemanticOverrideExtractionConfigurationInput.html), [UpdateMemory](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_UpdateMemory.html) | `appendToPrompt` 1..30000 ký tự, `modelId` bắt buộc; UpdateMemory có `addMemoryStrategies`, `deleteMemoryStrategies`, `modifyMemoryStrategies` (sửa cấu hình, không đổi loại) |
| CloudFormation | [AWS::BedrockAgentCore::Memory](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrockagentcore-memory.html), [CustomMemoryStrategy](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-bedrockagentcore-memory-custommemorystrategy.html) | `MemoryStrategies`, `MemoryExecutionRoleArn`, `Description`: "Update requires: No interruption"; chỉ `Name` và `EncryptionKeyArn` là "Replacement" |
| Ghi không lưu event | [long-term-ingest-data](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-ingest-data.html), [API IngestData](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_IngestData.html) | "Your application already retains the raw interactions": đúng trường hợp của Yofina; ví dụ gửi cả `USER` lẫn `ASSISTANT` nhưng không khuyên phải gửi lời trợ lý; fan-out tới mọi strategy trừ self-managed; "records typically appear within seconds to minutes"; `clientToken` chống ghi trùng |
| Đọc | [long-term-retrieve-records](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-retrieve-records.html), [API RetrieveMemoryRecords](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_RetrieveMemoryRecords.html), [API ListMemoryRecords](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_ListMemoryRecords.html) | Cần `namespace` hoặc `namespacePath`; `topK` tối đa 100; điểm là độ tương đồng cosine, không phải phần trăm |
| Xóa | [long-term-delete-memory-records](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-delete-memory-records.html), API `DeleteMemoryRecord`, `BatchDeleteMemoryRecords`, `GetMemoryRecord` | `BatchDeleteMemoryRecords` tối đa 100; `namespace` của Get/Delete "used for IAM condition key authorization" |
| Theo dõi | [long-term-redrive](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-redrive.html), [observability-memory-metrics](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-memory-metrics.html), [Metrics Insights alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch-metrics-insights-alarms.html) | Metric `FailedExtraction` (chiều StrategyId, Resource, StrategyType); strategy override có thêm họ lỗi `CUSTOM_MODEL_BEDROCK_*`; redrive bằng `ListMemoryExtractionJobs` + `StartMemoryExtractionJob` |
| IAM | [Service Authorization Reference: Amazon Bedrock AgentCore](https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonbedrockagentcore.html) | `IngestData`: điều kiện `actorId`, `sessionId`; `Retrieve`/`ListMemoryRecords`: `namespace`, `namespacePath`, `strategyId`; `Get`/`Delete`/`BatchDeleteMemoryRecords`: `namespace` |
| Vùng | [agentcore-regions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html), [bedrock.md](bedrock.md) mục 2 | AgentCore Memory có ở Asia Pacific (Singapore); bảng vùng không tách riêng override. Nova Lite v1 gọi từ Singapore qua `apac.amazon.nova-lite-v1:0` (điểm đến trong châu Á - Thái Bình Dương), đã gọi thử 21/11 |
| CDK | `aws-cdk-lib` 2.278.0, `aws-bedrockagentcore` (đọc `.d.ts`/`.js` trong `node_modules`) | L2 `Memory`; strategy có `customExtraction` render thành `customMemoryStrategy` với `semanticOverride`/`userPreferenceOverride`; L2 lấy `modelId` bằng `Arn.split(model.modelArn)` và cấp `bedrock:InvokeModel*` cho execution role qua `strategy.grant(role)`; L2 luôn tạo một execution role |
| Bản ghi tự tạo | [API MemoryRecordCreateInput](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_MemoryRecordCreateInput.html) | `memoryStrategyId` là tùy chọn: `BatchCreateMemoryRecords` dùng được mà không cần strategy self-managed |
| Giá | [AgentCore pricing](https://aws.amazon.com/bedrock/agentcore/pricing/) (tra 25/11), docs/research/agentcore.md §3.8 | Truy xuất dài hạn $0,50/1.000 lượt; lưu bản ghi built-in $0,75/1.000 bản ghi/tháng, "With built-in with override extraction strategies, long-term storage cost would be lower at $0.25 per 1,000 memories stored. However, you may incur additional charges for model usage in your account"; không phí theo giờ |

## 2. Quyết định

### 2.1 Một Memory, namespace theo actor

- MỘT Memory `yofina_memory` (`infra-cdk/lib/memory.ts`, stack `YofinaAgent`). Người dùng tách bằng namespace; `actorId` luôn là `sub`
  của JWT đã được Runtime xác minh (`Identity.sub`) hoặc claim `sub` của authorizer HTTP API (ledger). Không đường nào đọc người dùng từ
  payload, query hay chữ người dùng (test: `test_luot_binh_thuong_doc_va_ghi_theo_sub_cua_jwt_khong_theo_payload`,
  `test_sub_chi_tu_jwt_khong_tu_query`).
- **LỆCH chuỗi namespace so với đề bài** (`/users/{actorId}/preferences/`, `/users/{actorId}/summaries/{sessionId}/`): theo đúng hợp đồng
  đã có trên nhánh (`yofina_core.memory.MEMORY_NAMESPACE_TEMPLATES`): `/yofina/users/{actorId}/preferences/`, `/yofina/users/{actorId}/facts/`,
  `/yofina/users/{actorId}/sessions/{sessionId}/`. Lý do: luật của đợt là code theo hợp đồng, không tự đổi; hợp đồng vẫn đúng best practice
  (`/` đầu và cuối, theo actor). Từ 25/11 chỉ hai namespace đầu còn strategy ghi vào; `sessions/` giữ trong hợp đồng để xem và xóa bản ghi
  tóm tắt cũ. Hai loại `behavior/` và `lessons/` của hợp đồng chưa có strategy (xem 2.8). Test Python đối chiếu chuỗi của CDK với hợp đồng
  (`test_namespace_cua_cdk_khop_yofina_core`).
- Mọi bản ghi đọc về, trả ra hay sắp xóa đều được kiểm lại `kind_of_namespace(ns, sub)`: namespace không thuộc người gọi thì bỏ, kể cả khi
  lọc phía dịch vụ sai (test có bản ghi "rò" của người khác).

### 2.2 Strategy: sở thích và sự thật "built-in with overrides", bỏ tóm tắt phiên (sửa 25/11)

**Trước 25/11** có ba strategy dựng sẵn không override (sở thích, sự thật, tóm tắt phiên). Kiểm lại Runtime v23 (file phase 5, mục "Kiểm
lại sau sửa lần 2") cho thấy ba lỗ hổng ở bước trích xuất, không sửa được ở phía đọc:

1. Câu what-if "Nếu mua tai nghe 1,2 triệu bằng Trả sau thì sao?" thành sự thật "Người dùng đang cân nhắc mua tai nghe với giá [số tiền]
   bằng hình thức Trả sau." Chỉ dẫn mặc định của strategy sự thật trích cả "implicit personal details ... shared in natural conversation",
   và chỉ dẫn mặc định của strategy sở thích cho suy ra sở thích từ "repeated inquiries": với một ứng dụng mà gần như mọi câu là câu hỏi,
   hai điều đó biến câu hỏi thành "điều về người dùng".
2. Một câu "ưu tiên để dành cho hũ Du lịch" thành hai bản ghi (sở thích và sự thật trùng ý), vì chỉ dẫn mặc định của strategy sự thật
   tính cả "preferences".
3. Bản ghi tiếng Anh: chỉ dẫn mặc định để model tự đoán ngôn ngữ chính; strategy sự thật có lúc viết tiếng Anh. Với sở thích, bản tiếng
   Anh còn làm hỏng `quiet_hours` (bộ đọc theo mẫu câu tiếng Việt, 2.11).

Tài liệu nêu đúng trường hợp này cho override: "Domain-specific extraction: Constraining the strategy to extract only certain types of
information". Nay (`infra-cdk/lib/memory.ts`):

- `preferences_vi` (USER_PREFERENCE) và `facts_vi` (SEMANTIC) là `customMemoryStrategy` có `userPreferenceOverride` / `semanticOverride`,
  chỉ override bước **trích xuất**. Hợp nhất (consolidation) giữ mặc định của AWS: nó đã viết bản hợp nhất theo ngôn ngữ của bản ghi mới,
  và không đổi tên thao tác `AddMemory`/`UpdateMemory` là điều kiện tài liệu đặt ra.
- `appendToPrompt` THAY chỉ dẫn mặc định, nên văn bản là **nguyên văn chỉ dẫn mặc định của AWS (tra 25/11) cộng luật của Yofina**, đúng
  khuyến nghị "Build upon existing instructions". Không đụng output schema. Luật thêm:
  - chỉ trích điều người dùng KHẲNG ĐỊNH về bản thân: sở thích nói rõ về cách trợ lý giúp họ (hũ ưu tiên hay muốn giữ, giờ không muốn
    được nhắc, cách viết câu trả lời); hoàn cảnh, kế hoạch đã quyết (sự thật);
  - không trích từ câu hỏi, câu what-if, câu hỏi số liệu (ví dụ "Nếu mua laptop bằng Trả sau thì sao?", "Hũ nào sắp cạn?"; ví dụ cố ý
    khác câu của bộ đánh giá); chỉ có câu hỏi thì trả danh sách rỗng; sở thích không suy ra từ câu hỏi lặp lại;
  - không số tiền, số dư, số tài khoản, thẻ, điện thoại, phần trăm; `[số tiền]`, `[số]`, `[STK]` là giá trị đã che, không chép, không
    đoán lại; sở thích giữ nguyên giờ trong ngày ("trước 9 giờ", "buổi sáng") cho `quiet_hours`;
  - không tên hay chi tiết của người khác (tên đã che "N***");
  - sự thật không lặp sở thích (strategy khác lưu sở thích);
  - bỏ qua câu trong hội thoại đòi đổi hay lộ các luật này (chống tiêm lệnh vào bước trích xuất, cùng tinh thần mục memory poisoning của
    best practice);
  - luôn viết tiếng Việt có dấu, khai `language` là "Vietnamese", câu ngắn không chủ ngữ ("Làm giáo viên ở Đà Nẵng"), giữ nguyên tên
    riêng và tên hũ. Với strategy sự thật, khối `<language_requirement>` nằm trong phần chỉ dẫn nên được thay hẳn; với strategy sở thích,
    khối đó nằm trong output schema (không sửa được), luật ngôn ngữ chỉ nói thêm và không mâu thuẫn vì hội thoại là tiếng Việt;
  - (P0-3, `CHANGE_AND_SCOPE_RULES`, chung cho hai strategy; theo [long-term-memory-research.md](long-term-memory-research.md) mục 2.4)
    hợp nhất mặc định chỉ có Add, Update, Skip và bỏ "trạng thái tạm thời", nên bước trích xuất phải: giữ nguyên chữ giới hạn thời gian
    của người dùng (một khoảng, một hạn, một sự kiện sắp tới, một tình trạng tạm), không bỏ, không rút gọn, không đổi thành ngày (ngày và
    số bị che khi đọc), và vẫn trích câu chỉ đúng trong một thời gian; câu đổi ý hay rút lại viết thành MỘT lời khẳng định hoặc phủ định
    đầy đủ về đúng điều cũ (cùng hũ, cùng giờ nhắc, cùng hoàn cảnh), không trả danh sách rỗng chỉ vì câu bỏ đi một điều, vì bước hợp
    nhất chỉ thay được bản cũ khi bản mới nói rõ trạng thái hiện tại của cùng một điều; lý do từ chối một đề xuất là lời khẳng định về
    bản thân (sự thật giữ phần hoàn cảnh, sở thích giữ phần muốn giữ hay ưu tiên), còn việc từ chối thì ứng dụng tự lưu (`feedback`).
    Chỉ nêu nguyên tắc và lý do, không ví dụ (test CDK: không chứa chữ của bộ đánh giá). `cdk synth YofinaAgent` trước và sau: cùng
    logical id của Memory, chỉ `MemoryStrategies` đổi, tên strategy và namespace giữ nguyên, nên lần cập nhật là `modifyMemoryStrategies`
    tại chỗ.
- **Model**: `apac.amazon.nova-lite-v1:0` (`EXTRACTION_MODEL_ID`, đổi được qua prop `extractionModelId`). Lý do: (1) override gọi model
  TRONG tài khoản và ăn quota Bedrock của tài khoản; throttle thì lượt trích xuất thất bại ("Amazon Bedrock capacity for built-in with
  overrides strategies"). Model nhỏ của agent là Nova 2 Lite `global.` (20 RPM ở Singapore, agent tự giới hạn 18) và Claude chỉ khoảng
  10 RPM, nên dùng chung là tranh quota; Nova Lite v1 là xô quota riêng (20 RPM). (2) Gọi được từ Singapore qua profile `apac.`, dữ liệu
  ở lại châu Á - Thái Bình Dương ([bedrock.md](bedrock.md) mục 2). (3) Rẻ nhất trong nhóm đã gọi được. Rủi ro: chất lượng làm theo chỉ dẫn
  dài và đúng JSON schema của Nova Lite v1 chưa đo (mục 3).
- **Có ở `ap-southeast-1` không**: AgentCore Memory có ở Singapore; bảng vùng không tách riêng override; policy mẫu của AWS cho execution
  role cho phép `inference-profile/*`, nên profile dùng được làm `modelId`. Chưa gọi sống (không deploy trong đợt này).
- **Execution role**: L2 `Memory` luôn tạo role `ServiceRole` (trust `bedrock-agentcore.amazonaws.com`, điều kiện `aws:SourceAccount`) và
  gắn vào `memoryExecutionRoleArn` (trước đây role rỗng). Role nay chỉ có `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream`
  trên đúng profile `apac.amazon.nova-lite-v1:0` của vùng và tài khoản, và `foundation-model/amazon.nova-lite-v1:0` ở mọi vùng (vùng
  đích của profile), cùng mẫu với Runtime (`agent-stack.ts`); không quyền dữ liệu Memory (test CDK). Không dùng
  `MemoryStrategy.usingSemantic({customExtraction})` của L2: L2 lấy `modelId` bằng `Arn.split(model.modelArn)`, ARN của profile có account
  (token khi synth không có credential) và id có dấu `:` (`...-v1:0`), nên id tách bằng token mất đuôi `:0`. `ExtractionOverrideStrategy`
  trong `memory.ts` render `modelId` là chuỗi literal và cấp quyền như trên.
- **Chi phí theo lượt**: mỗi lượt được ghi (sau chính sách 2.4, chỉ lượt nói điều về bản thân) gây hai lần gọi trích xuất (sở thích, sự
  thật), mỗi lần khoảng 2.000–3.000 token vào (chỉ dẫn 5.300 và 7.300 ký tự, khoảng 1.300–1.800 token, cộng output schema và hội thoại của phiên) và vài chục tới 200 token ra. Với
  Nova Lite ở Singapore (khoảng $0,081 vào, $0,324 ra mỗi 1M token, Price List 21/11 trong [bedrock.md](bedrock.md)): khoảng $0,0003 mỗi lần,
  dưới $0,001 mỗi lượt được ghi, khoảng $0,6 cho 1.000 lượt được ghi. Lưu bản ghi giảm từ $0,75 xuống $0,25 mỗi 1.000 bản ghi mỗi tháng
  (trang giá). Bỏ tóm tắt phiên bớt một lượt trích của dịch vụ mỗi lượt và các bản ghi tóm tắt (mỗi phiên hai bản).
- **Bỏ tóm tắt phiên**: agent không đọc tóm tắt (`RECALL_KINDS` chỉ có sở thích, sự thật), nó tốn lượt trích, sinh mẩu "Thời điểm: ," cùng
  số liệu chép từ lời trợ lý, và mỗi phiên ra hai bản ghi (`BASE` và `FULL_SESSION`). Bản ghi tóm tắt cũ vẫn xem và xóa được.
- **Cập nhật tại chỗ, không thay Memory**: tài liệu CloudFormation ghi `MemoryStrategies`, `MemoryExecutionRoleArn`, `Description` là
  "No interruption", chỉ `Name` và `EncryptionKeyArn` là "Replacement". So template trước và sau bằng script tạm (cùng construct id
  `LongTermMemory` như `YofinaAgent`): logical id của Memory, role và hai tham số SSM giữ nguyên; Memory chỉ đổi `Description`,
  `MemoryStrategies`; thêm một `AWS::IAM::Policy` cho role. Tên strategy mới (`preferences_vi`, `facts_vi`) khác tên cũ để lần cập nhật là
  xóa strategy cũ và thêm strategy mới (UpdateMemory không đổi được loại strategy bằng `modifyMemoryStrategies`), tránh trùng tên trong
  cùng một lần cập nhật. Chưa chạy `cdk diff YofinaAgent` với tài khoản (synth cả app cần zip Lambda đã build; worktree không có).

Không chọn self-managed strategy: phải tự dựng hàng đợi, S3, Lambda trích xuất và tự lo output schema, nhiều việc hơn hẳn cho cùng mục
tiêu; override đủ cho "chỉ trích một số loại thông tin" theo tài liệu.

### 2.3 Trích xuất: `IngestData`, không lưu event ngắn hạn

- Ứng dụng đã lưu lượt thô ở Aurora (`turn_blocks`) và frontend gửi lịch sử theo từng lượt, nên không cần bộ nhớ ngắn hạn của AgentCore.
  Agent gọi `IngestData`, đúng trường hợp tài liệu nêu.
- Đã kiểm: boto3/botocore **1.44.9** (bản ghim trong `uv.lock`, nằm trong zip agent: `scripts/agent_build_zip.py` GIỮ boto3) có
  `IngestData` và mọi API dùng ở đây; tham số khớp model dịch vụ (Stubber). `IngestData` đã chạy sống ở ap-southeast-1 (log
  `memory_ingested` trên Runtime v23). `sessionId` là id hội thoại (băm thành id hợp lệ nếu có ký tự lạ).
- `clientToken` = băm của (`sub`, `trace_id`): ghi lại cùng lượt không ra bản ghi trùng.
- Hạn event để 7 ngày (mức thấp nhất CDK nhận) phòng khi sau này có event; agent không tạo event.
- Trích xuất là bất đồng bộ (tài liệu: "seconds to minutes"): không dựa vào bản ghi mới trong cùng phiên. Ý định `memory` trả lời "đã ghi
  nhận, việc lưu cần ít phút". Log Runtime v23 (24/11 16:34:47 ghi câu sở thích, 16:35:19 câu hỏi phiên mới) cho thấy chỉ cách nhau 32
  giây: bộ đánh giá phải chờ đúng bản ghi (2.14).

### 2.4 Đưa gì vào Memory, chống đầu độc bộ nhớ

Chỉ MỘT đoạn chữ của một lượt: câu của người dùng (đã che PII ở L0), vai `USER`. **Sửa ở p5/fix-mem (24/11):** bản đầu gửi cả lời trả lời
bằng chữ của trợ lý; lời đó đọc số từ sổ cái và hồ sơ hành vi ("cuối tuần bạn chi 37% tổng chi", "47 ngày"), nên strategy sự thật và tóm
tắt chép các số đó thành "điều về người dùng" (golden `memory-recall` trượt NumericGrounding). Nay `AgentMemory.ingest_request` chỉ gửi
câu người dùng.

**Xét lại 25/11: có gửi lời trợ lý đã che số làm ngữ cảnh không?** Không. Chỉ dẫn mặc định cho phép ("use assistant messages only as
supporting context") và ví dụ `IngestData` có vai `ASSISTANT`, nhưng tài liệu không khuyên phải gửi. Câu hỏi hay lời khẳng định phân biệt
được ngay trên câu người dùng, và chỉ dẫn trích xuất mới dặn bỏ câu hỏi. Lời trợ lý của Yofina mang trạng thái hũ và kết luận do hệ thống
tính ("hũ Nghĩa vụ chuyển sang hụt"); che số vẫn để lại các kết luận đó cho strategy chép thành "điều về người dùng", đúng lỗi đã thấy.

Trước khi gửi, câu đi qua `sanitize_for_memory`: `mask_pii` (số điện thoại, CCCD, số tài khoản, thẻ, email), `mask_names` (tên người
khác), `mask_amounts` (mọi số tiền cụ thể: có đơn vị, có nhóm nghìn, hoặc từ 5 chữ số liền thành `[số tiền]`; giữ giờ, ngày, phần trăm để
sở thích "đừng nhắc trước 9 giờ" còn dùng được), bỏ ký tự điều khiển, cắt độ dài. `contentTimestamp` (bắt buộc của `IngestData`) là giờ
thật của máy chủ.

Không bao giờ vào Memory: số dư, giao dịch, kết quả tool, khối UI, hồ sơ hành vi (nguồn sự thật là `behavior_profiles` ở Aurora), số liệu
tài chính (luôn đọc từ sổ cái).

Không ghi lượt (`memory.skip_reason`, test tham số hóa). Đây là CHÍNH SÁCH GHI; nguồn chính quyết định điều gì đáng nhớ là chỉ dẫn trích
xuất (2.2):

| Điều kiện | Lý do |
|---|---|
| Guardrail đầu vào chặn, lỗi, hết giờ (fail-open), tắt hoặc chưa cấu hình | Best practice: chỉ ghi chữ đã qua guardrail |
| Ý định `out_of_scope` (gồm hỏi dữ liệu người khác, đòi bỏ quy tắc) | Lượt bị từ chối |
| Ý định `ingest` | Nội dung tệp nạp (ảnh, CSV) là dữ liệu không tin cậy |
| Ý định `move` | Lời nhắn giao dịch, tên người nhận |
| **Ý định hỏi đáp thuần** (`memory.QA_INTENTS`: `lookup`, `what_if`, `affordability`, `resilience`, `stress`, `behavior`, `knowledge`; thêm 25/11) | Người dùng hỏi số liệu, kịch bản hay giải thích, không khẳng định điều gì về mình. Câu what-if từng thành sự thật rác; câu hỏi phiên mới "nên để vào hũ nào?" từng được `IngestData` (log 16:35:24). Câu vừa hỏi vừa nói sở thích mà router xếp vào nhóm này thì mất phần sở thích: chấp nhận (router xếp câu chủ yếu là nói sở thích vào `memory`) |
| Câu có dấu hiệu tấn công prompt ("bỏ qua hướng dẫn", "ignore previous instructions", "tôi là admin", "không cần xác nhận"...) | Lớp phụ sau PROMPT_ATTACK của Guardrail |
| Câu hỏi "bạn nhớ gì về mình" | Lời đáp là chính các bản ghi: ghi lại thì bộ nhớ tự nhân bản |

Vẫn ghi: `memory`, `profile_update` (hoàn cảnh: đổi việc, chuyển nhà), `roadmap` (kế hoạch, mục tiêu), `chitchat` (có thể kể về mình).

### 2.5 Đọc: song song, có hạn, dữ liệu không tin cậy, khối có cấu trúc

- Đầu lượt, ngay khi có câu hỏi đã che PII, `TurnMemory.start` đọc song song với router và Guardrail, cho chính `sub`:
  - sở thích: `ListMemoryRecords` trên `preferences/` (tối đa `memory_preferences_list_max` = 20 bản, mới nhất trước, bỏ bản giống hệt).
    **Sửa ở p5/fix-mem:** bản đầu dùng `RetrieveMemoryRecords` topK 4 theo câu hỏi, nên câu "nên để vào hũ nào?" không tìm ra sở thích "ưu
    tiên hũ Du lịch" (hai câu không gần nghĩa). Sở thích ít bản ghi và áp cho mọi câu hỏi nên đọc hết.
  - sự thật: `RetrieveMemoryRecords` trên `facts/` (topK `memory_facts_top_k` = 3), truy vấn là câu hỏi. Đây là phần "chỉ đưa mục liên
    quan" của sự thật: dịch vụ xếp theo độ tương đồng. `memory_min_score` vẫn 0 vì chưa có điểm thật để chọn ngưỡng; từ 25/11 log JSON
    `memory_recalled` ghi số mục, số bản bị khử trùng và điểm của từng sự thật (không ghi chữ) để chỉnh ngưỡng theo số đo.
  Tóm tắt phiên không đọc. Hạn `memory_retrieve_timeout_seconds` = 1,2 giây. Chậm hoặc lỗi: ngữ cảnh rỗng `degraded`, log
  `memory_degraded`, lượt chạy bình thường.
- Bản ghi đọc về là DỮ LIỆU KHÔNG TIN CẬY: kiểm namespace, `sanitize_recalled` (bỏ dấu thời gian Unix và mẩu nhãn rỗng nó để lại, che lại
  PII, tên, số tiền, rồi thay MỌI con số còn lại trừ giờ trong ngày bằng `[số]`, bỏ `<` `>` để không đóng được thẻ prompt), cắt 300 ký tự
  mỗi bản ghi, 1.200 ký tự tổng.
- **Khử trùng giữa hai loại** (`memory.dedupe_items`, từ 25/11 gọi `yofina_core.memory_text.dedupe_by_meaning`, cùng hàm với
  `GET /memory`): hai bản ghi là cùng ý nếu tập từ (chữ thường, CÒN dấu, bỏ từ đệm như "người dùng", "muốn", "vào") có hệ số Dice ≥ 0,8;
  giữ bản `preference`. Còn dấu để "buổi tối" không trùng "buổi sáng". Không khử trùng được hai bản khác ngôn ngữ. Chỉ dẫn trích xuất mới
  ("sự thật không lặp sở thích") giảm trùng ngay từ nguồn; khử trùng khi đọc giữ cho bản ghi cũ.
- **Khối prompt có cấu trúc (sửa 25/11).** Ca trượt `memory-reuse-new-session` trên Runtime v23: câu hỏi phiên mới "Tháng này còn dư một
  ít, mình nên để vào hũ nào?", Nova 2 Lite trả "Theo điều bạn đã dặn, hãy cân nhắc đưa vào hũ Dự phòng." Chẩn đoán (kiểm bằng log
  Runtime và mã):
  - (a) Đúng một phần, chưa chứng minh được: câu sở thích được `IngestData` lúc 16:34:47, câu hỏi lúc 16:35:19 (32 giây sau); runner dừng
    ở bản ghi mới đầu tiên (31,2 giây), nên không biết sở thích Du lịch đã trích xong chưa. Bộ nhớ chắc chắn đã có sự thật rác từ hai lượt
    what-if (16:33:06, 16:33:56); lượt `memory-recall` lúc 16:35:46 liệt kê cả sở thích Du lịch lẫn sự thật rác đó.
  - (b) Đúng: `MEMORY_GUIDE` cũ có câu mẫu "(ví dụ: theo điều bạn đã dặn, ...)" kèm điều kiện "nếu người dùng hỏi nên để ... vào hũ nào
    ... và <bo_nho_nguoi_dung> có sở thích về một hũ". Câu trả lời chép đúng câu mẫu và tự điền một hũ có trong danh sách số dư. Dù sở
    thích Du lịch có hay chưa có trong khối, chỉ dẫn này cho model nhỏ một câu để chép mà không bắt nó kiểm vế sau; khối cũ là các dòng
    chữ "- Sở thích: ...", không nói sở thích nào thuộc hũ nào.
  - (e) Đúng: sở thích chỉ vào bước viết câu như một câu chêm.
  Sửa: `MemoryContext.prompt_block` (qua `Turn.memory_block`) dựng khối gồm câu báo `PROMPT_NOTICE` rồi JSON
  `{"so_thich": [{"noi_dung", "hu", "ngay_ghi"}], "dieu_da_ke": [{"noi_dung", "ngay_ghi"}]}`:
  - `noi_dung`: chữ đã làm sạch của bản ghi;
  - `hu`: tên các hũ THẬT của người dùng mà sở thích nhắc tới (`memory.jars_mentioned`: so không dấu theo nguyên cụm với tên hũ đã đọc
    trong lượt, từ danh sách hũ hoặc bản gọn của tra cứu số dư); rỗng nghĩa là sở thích không nói về hũ nào; vắng khóa khi lượt chưa đọc
    hũ nào. Mã đối chiếu, model không phải đoán sở thích nói về hũ nào;
  - `ngay_ghi`: ngày ghi theo NGÀY MÔ PHỎNG (`memory.recorded_on`: ngày thật của `createdAt` cộng độ lệch giữa ngày mô phỏng hôm nay và
    ngày thật hôm nay, theo múi giờ ứng dụng); câu báo nói nó chỉ để biết mục cũ hay mới, không phải số liệu để nhắc lại.
  `PROMPT_NOTICE` nói rõ các mục là điều CHÍNH người dùng tự nói, không bao giờ là căn cứ cho con số hay ngày. Khối không vào bản gọn nên
  không thành căn cứ số tiền (`allowed_amounts`), và NumericGrounding của Verifier không lấy số từ bộ nhớ.
- **Chỉ dẫn dùng bộ nhớ: mục đích, lý do, giới hạn; không câu mẫu (P0-1, [long-term-memory-research.md](long-term-memory-research.md)
  mục 3.4).** Hai chỉ dẫn chỉ đi kèm khi khối khác rỗng, đặt ngay sau khối; `WRITER_SYSTEM` và `ANALYST_SYSTEM` không còn câu nào về bộ
  nhớ, nên lượt không có bộ nhớ không mang chỉ dẫn thừa (test). Người viết (`writer.MEMORY_GUIDE`, chỉ cho `MEMORY_TASKS`): mục đích của
  khối (người dùng không phải nhắc lại), khi nào một mục đáng dùng (nó làm câu trả lời cho câu hỏi đang hỏi khác đi), hũ nêu theo mục
  phải nằm trong `hu` của mục, được thêm tối đa một câu ngoài khuôn; lý do (gán điều chưa nói hay nhắc mục không liên quan làm mất niềm
  tin, nên điều gì trình bày là của người dùng phải có trong khối, gợi ý tự rút từ dữ liệu là gợi ý của trợ lý); mục có thời hạn xét cùng
  `ngay_ghi`; không căn cứ số. Analyst (`whatif.ANALYST_MEMORY_GUIDE`): cân mục liên quan khi chọn phương án, chọn hũ, chọn phương án gợi
  ý và cho người dùng thấy điều đó; bỏ kết luận đặt sẵn của bản cũ (hũ nào không được chọn) để model tự cân; mục có thời hạn so `ngay_ghi`
  với `<ngay_hom_nay>`; luật số liệu và luật phù hợp vẫn thắng. `PROMPT_NOTICE` (trong khối) mô tả nguồn, các trường, chỗ số đã bỏ. Bỏ ví
  dụ âm có cụm trong ngoặc kép của bản trước: với model nhỏ, cụm bị trích là một mẫu để chép (Runtime v23). Test: không prompt nào chứa
  cụm gán lời cho người dùng; chỉ dẫn bộ nhớ không ví dụ, không ngoặc kép, không tên hũ mẫu.
- **Bước quyết định.** Bộ nhớ vào Analyst (what-if: chọn phương án, hũ bị lấy tiền) và người viết. Không đưa vào router: đọc song song với
  router là để không chậm thêm tới 1,2 giây mỗi lượt, và sở thích không đổi ý định của câu. Không đưa vào bản gọn (`compact`) của tool: bản
  gọn là căn cứ số tiền. Câu "nên để vào hũ nào?" là ý định tra cứu số dư, không có bước quyết định nào khác ngoài người viết; dữ liệu có
  cấu trúc (`hu`) là thứ cho câu trả lời "diễn đạt từ dữ liệu".
- Đo: unit test với LLM giả và đọc prompt (`tests/unit/agent/test_memory_wiring.py`: khối của ca `memory-reuse-new-session` có
  `{"noi_dung": "Ưu tiên để dành tiền cho hũ Du lịch.", "hu": ["Du lịch"], "ngay_ghi": "21/11/2026"}`; ca chỉ có sở thích không về hũ và
  sự thật rác có `hu` rỗng; hũ không có thật không bị gắn). Chất lượng câu trả lời của model thật chỉ đo được bằng eval sau deploy.
- Ngoài ra bộ nhớ dùng ở ý định `memory` ("bạn nhớ gì về mình" liệt kê điều đã nhớ) và ở bản tin qua `quiet_hours`.

### 2.6 Ghi: sau khi trả lời

`schedule_remember` chạy SAU `RUN_FINISHED` (tác vụ nền giữ tham chiếu trong `_BACKGROUND`), hạn 5 giây, lỗi chỉ log (`memory_degraded`
op `ingest`), không bao giờ làm hỏng hay làm chậm lượt (test).

### 2.7 Ý định `memory`

Thêm ý định `memory` vào `schemas.Intent`, `wallet.INTENTS` (chuyển khỏi `PHASE5_INTENTS` theo lưu ý của worker hợp đồng; `AUDIT_INTENTS`
nay viết tường minh theo thứ tự của 0053 để không phụ thuộc luồng nào đã cài) và một luật trong prompt router (nói sở thích về cách hỗ trợ
chính mình, hoặc hỏi trợ lý nhớ gì; khai lương, nghĩa vụ vẫn là `profile_update`; hỏi về người khác là `out_of_scope`; không hỏi lại).
Lời đáp là chuỗi cố định (không gọi model); danh sách điều đã nhớ là chữ của chính người dùng đã làm sạch và vẫn qua Guardrail đầu ra.

### 2.8 Bài học của agent: để sau

`BatchCreateMemoryRecords` dùng được không cần pipeline self-managed (`memoryStrategyId` tùy chọn), nhưng bài học phải được TÓM TẮT từ
bảng `feedback` bởi một bước batch (không phải trong lượt chat): việc đó nằm ở batch đêm (luồng p5-behavior), cần thêm quyền
`BatchCreateMemoryRecords` cho role batch và một quy ước nội dung (không số tiền). Để sau; namespace `/yofina/users/{actorId}/lessons/` đã có
trong hợp đồng và REST đã liệt kê, xóa được loại này.

### 2.9 IAM tối thiểu

| Role | Quyền | Tài nguyên |
|---|---|---|
| Runtime `yofina-agent-runtime` | `IngestData`, `RetrieveMemoryRecords`, `ListMemoryRecords` | ĐÚNG ARN của Memory (`memory.memoryArn`, cùng stack) |
| Execution role của Memory (L2 tạo, trust `bedrock-agentcore.amazonaws.com` + `aws:SourceAccount`; thêm 25/11) | `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` | Đúng `inference-profile/apac.amazon.nova-lite-v1:0` của vùng và tài khoản, `foundation-model/amazon.nova-lite-v1:0` (mọi vùng, vùng đích của profile) |
| Lambda `yofina-ledger` | `ListMemoryRecords`, `GetMemoryRecord`, `DeleteMemoryRecord`, `BatchDeleteMemoryRecords`, `ListSessions`, `ListEvents`, `DeleteEvent` | `memory/yofina_memory-*` (theo tên: YofinaTools deploy TRƯỚC YofinaAgent nên không đọc được ARN lúc deploy; tên Memory là duy nhất trong vùng nên mẫu khớp đúng một Memory) |
| Lambda `yofina-ledger` | `s3:ListBucket` (điều kiện `s3:prefix` = `u/*`), `s3:DeleteObject` trên `bucket/u/*` | bucket nạp `yofina-ingest-<account>-<region>` (tên cố định của YofinaIngest); không Get/Put |
| Lambda `yofina-ledger` | `ssm:GetParameter` | đúng một tham số `/yofina/memory/id` (YofinaAgent ghi; ledger đọc lúc chạy, chưa có thì coi Memory chưa cấu hình) |

Condition key namespace: KHÔNG dùng để tách người dùng. Một role (Runtime hay Lambda) phục vụ mọi người dùng, còn điều kiện IAM so với giá
trị tĩnh trong policy, không có biến nào gắn với `sub` của người dùng cuối (người dùng cuối không phải IAM principal). Một điều kiện kiểu
`/yofina/users/*` không thêm gì vì mọi bản ghi đều nằm dưới đó, và có hại: `GetMemoryRecord` lúc kiểm quyền sở hữu chưa biết namespace
nên không gửi `namespace` (điều kiện vắng khóa thì từ chối). Vì vậy namespace được ÉP TRONG MÃ (dựng từ `sub`, kiểm lại mọi bản ghi) và có
test; IAM giới hạn hành động và tài nguyên. `DeleteMemoryRecord` và `BatchDeleteMemoryRecords` vẫn gửi `namespace` đúng của bản ghi để sau này
thêm điều kiện được ngay.

Mã hóa: khóa do AWS sở hữu và quản lý (mặc định; không `encryptionKeyArn`). Không đưa dữ liệu nhạy cảm vào metadata (không dùng metadata).

### 2.10 REST và "Xóa dữ liệu của tôi"

- `GET /memory` (liệt kê theo `namespacePath` = gốc của người gọi, hoặc theo `kind`; mới nhất trước; `cursor` là `nextToken`). Chữ hiển thị
  (`memory_store.display_text`): chữ chính lấy bằng `yofina_core.memory_text.record_text` (cùng hàm với agent; sở thích lấy `preference`
  của JSON); tóm tắt XML thành "chủ đề: nội dung"; tóm tắt cả phiên (markdown) bỏ `#`, `**` TRƯỚC khi bỏ dấu thời gian (để "**Thời điểm:**
  <epoch>" được nhận là dấu thời gian); bỏ dấu thời gian Unix (`yofina_core.pii.strip_epoch_timestamps`), che PII và tên, rồi bỏ mẩu nhãn
  rỗng (`drop_empty_labels`, 25/11). **Sửa ở p5/fix-mem:** chỉ hiện bản `FULL_SESSION` của mỗi phiên (xóa hết vẫn xóa cả hai loại).
  **Dấu thời gian (p5/fix-mem rồi p5/fix-agent2):** một dãy 10 hoặc 13 chữ số là dấu thời gian (`is_epoch_at`) khi giá trị rơi vào
  2000–2100, có ngữ cảnh thời gian và không có từ khóa tài khoản, thẻ, ngân hàng đứng trước.
- **Khử trùng (25/11):** `list_records` gọi `dedupe_by_meaning` trên trang vừa đọc: sở thích và sự thật trùng ý chỉ hiện một lần, giữ bản
  sở thích, thứ tự mới nhất trước giữ nguyên. Kiểm lại Runtime v23 thấy `GET /memory` liệt kê cả "Ưu tiên để dành tiền cho hũ Du lịch" lẫn
  "Người dùng muốn ưu tiên để dành tiền cho hũ Du lịch." trong khi câu kể của agent đã khử. Hệ quả có chủ ý: "Xóa hết" vẫn xóa cả bản bị ẩn
  (`clear` liệt kê thẳng, không khử trùng); xóa từng bản đang hiện thì bản bị ẩn (nếu có) hiện ra ở lần xem sau và xóa tiếp được.
  Khử trùng chỉ trong một trang (mặc định 50 bản ghi).
- **Mẩu nhãn rỗng (25/11):** `drop_empty_labels` bỏ câu có nhãn ngắn ở đầu câu hoặc đầu dòng mà không còn giá trị (ngay sau dấu hai chấm
  là dấu câu, hoặc chỉ một cụm đơn vị trong ngoặc): "Thời điểm: , ước tính khoảng 24/11/2026 (UTC)." và "Thời điểm: (mili giây)." biến
  mất; nhãn đứng cuối dòng ("Tóm tắt:") là tiêu đề, giữ. Dấu câu thừa (". .", dấu câu đầu dòng) chỉ được dọn trên dòng có mẩu như vậy.
- `DELETE /memory/{record_id}` (`GetMemoryRecord`, kiểm namespace, rồi `DeleteMemoryRecord` kèm namespace; của người khác trả 404 như không
  có), `DELETE /memory` (liệt kê hết rồi `BatchDeleteMemoryRecords` theo lô 100; `ListSessions` → `ListEvents` → `DeleteEvent`;
  idempotent; lỗi từng phần vào `failed`). **Sửa ở p5/fix-mem:** `ListSessions` ném `ResourceNotFoundException` khi người dùng chưa từng
  có sự kiện ngắn hạn; nay coi là 0 sự kiện. Memory lỗi hoặc chưa cấu hình: 503 `MEMORY_UNAVAILABLE`.
- `POST /me/delete-data/confirmations` cấp token `delete_my_data` (theo mẫu `/ingest/confirmations`, cùng khóa HMAC và bảng `jti`), kèm bản
  xem trước. `POST /me/delete-data`: thiếu token 428; kiểm và tiêu token; rồi S3 (mọi object dưới `u/<sub>/`), Memory, Aurora
  (`app_delete_user_data` và chốt dòng `data_deletions` trong CÙNG một transaction; câu chốt dùng `finished_at = CAST(:fin AS timestamptz)`,
  sửa ở p5/fix-mem). Tiến độ ghi vào `data_deletions` sau MỖI bước. Đang có lần `running` còn hạn thuê (`privacy_deletion_lease_seconds` =
  120) thì trả lần đó; quá hạn thì lần sau nhận lại đúng dòng đó và làm tiếp. `partial` và `failed` đều chạy lại được tới `done`.

### 2.11 `quiet_hours` cho cổng bản tin

`yofina_ledger.memory_store.quiet_hours(sub, *, store=None) -> QuietHours` (Lambda ledger, nơi có `proactive.py`): đọc bản ghi SỞ THÍCH của
chính `sub` bằng `ListMemoryRecords` (không tốn lượt truy xuất semantic), tìm câu có ý "đừng nhắc" và rút khung giờ (`buổi sáng`, `trước 9
giờ`, `sau 22h`, `từ 22 giờ đến 7 giờ`, ...; khung buổi trong `memory_defaults.json`). Bộ đọc theo mẫu câu tiếng Việt: chỉ dẫn trích xuất mới
(2.2) buộc sở thích viết tiếng Việt và giữ nguyên giờ trong ngày. `QuietHours.contains(giờ)` xử lý khung vắt qua nửa đêm. Không bao giờ
ném lỗi.

### 2.12 Quan sát

- Alarm `yofina-memory-failed-extraction` vào topic SNS cảnh báo sẵn có (`/yofina/sns/alert-topic-arn`). Metric có ba chiều và strategy id
  không có trong CloudFormation, nên alarm dùng truy vấn Metrics Insights `SELECT SUM(FailedExtraction) FROM "AWS/Bedrock-AgentCore" WHERE
  Resource = '<ARN Memory>'` (một alarm phủ mọi strategy; `treatMissingData` = notBreaching). Với strategy override có thêm lỗi gọi model
  trong tài khoản (`CUSTOM_MODEL_BEDROCK_*`, ví dụ throttle hoặc thiếu quyền của execution role). Xử lý: `ListMemoryExtractionJobs` rồi
  `StartMemoryExtractionJob`.
- Log JSON: `memory_degraded` (op `retrieve` hoặc `ingest`), `memory_write_skipped` (lý do, gồm `qa_intent:<ý định>`), `memory_ingested`,
  `memory_recalled` (số sở thích, số sự thật, số bản bị khử trùng, điểm của sự thật; 25/11), `memory_foreign_record`; ledger:
  `memory_api_error`, `memory_foreign_record_dropped`, `memory_cleared`, `data_deletion_*`.

### 2.13 Chi phí

Theo lượt dùng, không theo giờ: mỗi lượt chat 1 `RetrieveMemoryRecords` (sự thật, $0,50/1.000 lượt truy xuất) cộng 1 `ListMemoryRecords` (sở thích; trang giá không nêu riêng);
`IngestData` chỉ cho lượt được ghi (2.4); mỗi lượt được ghi gây 2 lần gọi Nova Lite trong tài khoản, dưới $0,001 (2.2); lưu bản ghi
override $0,25/1.000 bản ghi/tháng (trước $0,75). Trang giá chưa nêu riêng giá của `IngestData` (chưa kiểm Billing). `quiet_hours` và REST
dùng `ListMemoryRecords`.

### 2.14 Bộ đánh giá: ca dùng lại bộ nhớ (25/11)

`evals/run.py`, ca có `prior_sessions` (`memory-reuse-new-session`): trước ca xóa bộ nhớ của tài khoản (`DELETE /memory`, kết quả ở
`memory_clear`), chạy phiên trước, rồi chờ tới khi `GET /memory` có bản ghi SỞ THÍCH nhắc mọi hũ của `expect_memory_used`
(`expected_preference_seen`) hoặc hết `--memory-wait` giây; `memory_wait` ghi `waiting_for`, `outcome` (`seen` hay `timeout`),
`new_records`, `waited_s`. Bản cũ dừng ở bản ghi mới đầu tiên, có thể là bản ghi của lượt what-if chạy trước. Tiêu chí chấm không đổi:
hết giờ chờ không làm ca đạt hay trượt thay cho câu trả lời.

**Bộ ca bộ nhớ (P0-2, theo [long-term-memory-research.md](long-term-memory-research.md) mục 5).** Sáu ca golden phase 5 (ba ca cũ, ba ca
mới), mỗi ca chạy một lần. Mọi ca có `seed_memory`, `prior_sessions` hay `expect_memory_records` bắt đầu bằng `DELETE /memory`.

| Ca | Loại | Năng lực | Chấm (hành vi) |
|---|---|---|---|
| `memory-state-preference` | GHI | Ghi sở thích, giữ chữ giới hạn thời gian (P0-3) | Không gọi tool ghi; `expect_memory_records`: có sở thích nhắc hũ Du lịch và giữ chữ giới hạn của câu, có sở thích về giờ nhắc (`memory_after.outcome` `seen` hay `timeout`) |
| `memory-reuse-new-session` | GHI rồi DÙNG | Tiêu chí 5, đầu cuối | Như trước: phiên mới nhắc hũ, không hỏi lại |
| `memory-recall` | DÙNG (nạp sẵn) | Kể lại | Câu trả lời nhắc hũ của bản đã nạp; nạp hỏng thì trượt |
| `memory-knowledge-update` | Nạp bản cũ, GHI đổi ý, DÙNG | Knowledge update, rút lại | Bản đã nạp bị bước hợp nhất thay (`expect_seed_superseded`: không còn hoặc đã đổi nội dung); phiên mới dùng hũ mới, không hỏi lại |
| `memory-forget-no-invent` | DÙNG (nạp, xóa qua REST) | Quên, abstention | Bản đã xóa không còn trước câu hỏi; judge (model khác, `--judge-role`, mặc định `planner`) không thấy câu trả lời gán cho người dùng điều không có trong bộ nhớ hay điều đã xóa |
| `memory-whatif-protect-jar` | DÙNG (nạp sẵn) | Nhiều phiên, đường Analyst | Không phương án nào lấy tiền hũ người dùng muốn giữ (`option_id` dựng theo hũ, `from_jar` của khối xác nhận); NumericGrounding như mọi ca |

- Nạp: `MemorySeeder` gọi `BatchCreateMemoryRecords` vào namespace của `sub` tài khoản chạy eval (đọc từ access token), nội dung giống bản
  strategy tạo (sở thích là JSON `{context, preference, categories}`, đối chiếu một bản thật 24/11; sự thật là chữ thường), kèm id
  strategy đọc bằng `GetMemory` để bước hợp nhất của strategy đó coi bản ghi là của mình, `recordExpirySpecification` 1 ngày; chờ bản
  ghi hiện ở `GET /memory` (`memory_ready`); dọn bằng `DELETE /memory` sau ca. Danh tính chạy eval cần
  `bedrock-agentcore:BatchCreateMemoryRecords` và `bedrock-agentcore-control:GetMemory` trên Memory; Runtime và Lambda không có quyền
  ghi bản ghi.
- Judge chỉ ở ca cần phân biệt "gợi ý của trợ lý" với "gán cho người dùng" (không làm được bằng mã mà không so câu chữ); một lời gọi qua
  `yofina_core.llm` (giới hạn tốc độ, trần ngày), verdict lưu trong kết quả để `--score-only` chấm lại. Ca còn lại chấm bằng mã.
- Chưa chạy trên Runtime: người điều phối chạy một lần sau deploy. Chưa biết bản ghi tạo bằng Batch API kèm `memoryStrategyId` có được
  bước hợp nhất xét cùng bản ghi mới không (mục 7 của ghi chú nghiên cứu); `memory_state.with_strategy_id` ghi bản đã nạp có kèm id
  hay không, để đọc kết quả `ban_cu_con_nguyen` cho đúng.

## 3. Chưa kiểm, rủi ro, việc cho người khác

1. **Chưa deploy, chưa chạy thật** (theo luật của đợt): override ở ap-southeast-1 với `apac.amazon.nova-lite-v1:0`; chất lượng trích xuất
   của Nova Lite v1 với chỉ dẫn dài (đúng JSON schema, đúng luật "bỏ câu hỏi", tiếng Việt có dấu); độ trễ trích xuất. Sau deploy cần: xem
   `FailedExtraction` và `ListMemoryExtractionJobs`, nói một sở thích rồi đọc `GET /memory` (tiếng Việt, không có bản sự thật trùng), hỏi
   một câu what-if (không ra bản ghi), rồi chạy các ca golden bộ nhớ (mục 2.14). Nếu Nova Lite v1 không giữ được JSON schema thì đổi
   `extractionModelId` (ví dụ Nova Pro `apac.`) và chấp nhận chi phí cao hơn.
2. **Bản ghi của strategy cũ**: lần cập nhật xóa ba strategy cũ và thêm hai strategy mới. Tài liệu không nói bản ghi của strategy đã xóa
   còn hay mất; namespace giữ nguyên nên nếu còn, agent và REST vẫn đọc, xóa được. Theo file phase 5, sau các lần kiểm 24/11 bộ nhớ của các tài khoản
   demo đã được dọn về 0, nên không mất dữ liệu cần giữ. Bản ghi tiếng Anh cũ (nếu còn) vẫn đi qua câu dặn "luôn trả lời bằng tiếng Việt".
3. **Lambda ledger** dùng boto3 ghim (`--keep-boto`, `LEDGER_BUILD_COMMAND`); zip phải build lại để có `yofina_core/memory_text.py`.
4. Thứ tự deploy: `YofinaTools` (ledger) và `YofinaAgent` (Memory, Runtime) đều cần build lại; `YofinaAgent` tạo thêm một IAM policy
   cho execution role trước khi cập nhật Memory (CDK `applyBefore`). Chưa chạy `cdk diff YofinaAgent` với tài khoản (mục 2.2).
5. `memory_min_score` = 0: chưa có điểm thật để chọn ngưỡng; xem log `memory_recalled` sau deploy.
6. Câu vừa nói sở thích vừa hỏi số liệu mà router xếp vào ý định hỏi đáp thì không được ghi (2.4).
7. Frontend không đổi; hợp đồng REST không đổi (khử trùng chỉ bớt bản ghi trong danh sách).
