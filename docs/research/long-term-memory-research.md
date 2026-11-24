# Tối ưu bộ nhớ dài hạn cho Yofina: nên nhớ gì, ghi, đọc, học từ trải nghiệm, đánh giá

Viết ngày 24/11/2026 (giờ máy) bởi worker `p5/memory-research` (Kiro, Claude Opus 5.5), do Claude Code điều phối. Đây là ghi chú
NGHIÊN CỨU: không sửa code sản phẩm, không deploy, không gọi AWS, không chạy eval. Thiết kế hiện tại để so sánh là
[agentcore-memory-design.md](agentcore-memory-design.md) (sau `p5/fix-agent3`) và mã trên nhánh `main` 602c292: `agent/src/yofina_agent/memory.py`,
`writer.py` (`MEMORY_GUIDE`), `whatif.py` (`ANALYST_SYSTEM`), `infra-cdk/lib/memory.ts`.

Quy ước: **[TL]** là điều đọc trong tài liệu chính thức, **[BL]** là bài blog của AWS, **[PP]** là paper, **[MÃ]** là điều đọc trong repo,
**[SĐ]** là suy đoán hay đề xuất của người viết, chưa kiểm.

## Kết luận ngắn

1. **Memory chỉ giữ điều người dùng tự nói mà Aurora không có cột để giữ.** Lương, ngày lương, khẩu vị rủi ro (`users.risk_tolerance`), mục
   tiêu có số (`jars.goal_vnd`, `goal_date`), lộ trình và trạng thái từng bước (`roadmaps.step_states`), phản hồi với phương án what-if
   (`feedback`), phản hồi với bản tin (`nudges.outcome`), hồ sơ hành vi (`behavior_profiles`) đều đã có nguồn sự thật. Nhân bản chúng vào
   Memory tạo hai bản có thể lệch nhau. Bảng ở mục 1.
2. **Thiết kế ghi hiện tại đúng hướng; giữ.** Chỉ gửi câu người dùng (đã che), override bước trích xuất, không tóm tắt phiên. Thiếu một
   việc: hợp nhất (consolidation) của AgentCore chỉ có Add, Update, Skip; nó coi "trạng thái tạm thời" là Skip. Sở thích có phạm vi thời gian
   ("tháng này ưu tiên hũ Du lịch") có thể bị bỏ hoặc mất chữ "tháng này". Cần kiểm sau deploy; nếu đúng là bị bỏ thì override luôn bước
   hợp nhất của strategy sở thích (mục 2.4).
3. **Đọc: liệt kê hết cả sự thật lẫn sở thích khi số bản ghi còn nhỏ.** Mỗi người dùng demo có dưới 20 bản ghi. Tìm ngữ nghĩa theo câu hỏi
   đã làm trượt sở thích một lần ("nên để vào hũ nào?" không gần nghĩa "ưu tiên hũ Du lịch"); sự thật đang đi đúng đường đó (topK 3). Liệt
   kê hết rẻ hơn ($0,50/1.000 lượt truy xuất được bỏ) và không phụ thuộc ngưỡng điểm chưa đo (mục 3).
4. **Prompt: đưa dữ liệu có cấu trúc kèm mục đích của khối, nói lý do, không câu mẫu và không trích dẫn cụm từ cấm.** `MEMORY_GUIDE` hiện
   vẫn có ví dụ âm chứa nguyên cụm "bạn đã dặn". Theo hướng dẫn của Anthropic, model bám rất sát ví dụ; với Nova 2 Lite (người viết) một cụm
   bị trích là một mẫu để chép. Nên viết lại theo mục đích (mục 3.4).
5. **"Học từ trải nghiệm" cho demo: tổng hợp tất định từ Aurora, không ReasoningBank.** Bảng `feedback` đã có `option_id` và
   `decision`/`reason`; từ `p5/fix-agent3` `option_id` theo hũ thật (`switch_<mã hũ>`). Một truy vấn SQL đếm số lần người dùng từ chối từng
   kiểu phương án, đưa vào Analyst dưới dạng dữ liệu, cho đúng cảnh "agent nhớ bạn không thích lấy tiền hũ Dự phòng" mà không thêm lời gọi
   model, không thêm dịch vụ. Episodic strategy của AgentCore và ReasoningBank để sau (mục 4).
6. **Đánh giá: tách ca ghi (trích xuất) khỏi ca dùng (đọc và trả lời).** Ca dùng nạp bản ghi trước bằng `BatchCreateMemoryRecords` nên
   không còn đua với trích xuất bất đồng bộ; ca ghi chờ theo nội dung mong đợi và dùng câu "mốc" cho ca phủ định. Bộ ca theo năm năng lực
   của LongMemEval áp vào tài chính (mục 5).

## Nguồn đã đọc (24/11/2026)

| Nguồn | Điều dùng |
|---|---|
| [TL] [memory-strategies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-strategies.html) | Ba loại: built-in, built-in with overrides (sửa prompt, model chạy trong tài khoản, lưu rẻ hơn), self-managed (tự lo pipeline); một Memory dùng được nhiều loại cùng lúc |
| [TL] [built-in-strategies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/built-in-strategies.html) | Bốn strategy dựng sẵn: semantic, user preference, summary, **episodic**; ba bước extraction, consolidation, reflection (chỉ episodic) |
| [TL] [episodic-memory-strategy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/episodic-memory-strategy.html) | Episode chỉ sinh khi dịch vụ thấy một tập (episode) đã xong; nên gửi cả kết quả `TOOL`; reflection có thể gộp nhiều actor nếu namespace rộng ("consider the privacy implications of cross-actor analysis") |
| [TL] [memory-custom-strategy](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-custom-strategy.html) | Override được: semantic và user preference (extraction, consolidation), summary (consolidation), episodic (extraction, consolidation, reflection); không đổi schema, không đổi tên `AddMemory`/`UpdateMemory` |
| [TL] [memory-user-prompt](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-user-prompt.html), [memory-system-prompt](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-system-prompt.html) | Chỉ dẫn hợp nhất mặc định: Add, Update (gồm cả khi mâu thuẫn: "If new fact has higher confidence, update existing memory"), Skip ("one-time event, describes temporary states", PII). Output schema của semantic có câu "include relevant details such as specific numbers" (không sửa được) |
| [TL] [memory-record-streaming](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-record-streaming.html) | Bản ghi bị xóa khi hợp nhất ("Consolidation workflows (de-duplication/superseding)"); có `BatchUpdateMemoryRecords`; đẩy sự kiện tạo, sửa, xóa vào Kinesis |
| [TL] [long-term-memory-metadata](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-memory-metadata.html) | Metadata cho bản ghi: tối đa 10 indexed key, `LLM_INFERRED` (có `allowedValues`, `LATEST_VALUE`) hoặc `STRICTLY_CONSISTENT` (giá trị từ ứng dụng, tách nhóm cả khi trích lẫn khi hợp nhất); lọc được ở `ListMemoryRecords` và `RetrieveMemoryRecords`; "Use namespaces for the who, and metadata for the what, when"; `IngestData` nhận metadata |
| [TL] [CloudFormation AWS::BedrockAgentCore::Memory](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrockagentcore-memory.html) | Có `IndexedKeys`, `NamespaceKeys`, `StreamDeliveryResources` (No interruption). [MÃ] `aws-cdk-lib` 2.278.0 (thư mục `node_modules` của repo chính) có kiểu `indexedKeys`, `metadataSchema`, `episodicOverride`, `reflectionConfiguration` |
| [TL] [long-term-retrieve-records](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/long-term-retrieve-records.html) | `topK` mặc định 10, tối đa 100; điểm là cosine, "does not represent a percentage match"; không có tham số ngưỡng điểm phía dịch vụ |
| [TL] [memory-self-managed-strategies](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-self-managed-strategies.html) | Self-managed kích hoạt theo event ngắn hạn (số tin, token, phiên rảnh), giao payload qua S3 và SNS; bản ghi ghi lại bằng Batch API; batch API đặt được TTL cho bản ghi |
| [TL] [best-practices](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/best-practices.html) | Chống memory poisoning: "Sanitize the user input data with guardrails prior to persistence to memory" |
| [BL] [AgentCore long-term memory deep dive](https://aws.amazon.com/blogs/machine-learning/building-smarter-ai-agents-agentcore-long-term-memory-deep-dive/) | Hợp nhất: lấy các bản ghi gần nghĩa nhất cùng namespace và strategy, LLM chọn ADD, UPDATE, NO-OP; bản cũ bị đánh INVALID thay vì xóa ngay; mâu thuẫn thì ưu tiên thông tin mới; trích và hợp nhất 20–40 giây; truy xuất khoảng 200 ms; PrefEval: preference memory 79% so với RAG cả hội thoại 51% |
| [BL] [AgentCore episodic memory](https://aws.amazon.com/blogs/machine-learning/build-agents-to-learn-from-experiences-using-amazon-bedrock-agentcore-episodic-memory/) | Episode có situation, intent, assessment, justification; reflection có use case, hints, điểm tin cậy 0,1–1,0; trên τ2-bench retail Pass^1 65,8% lên 77,2% với reflection; "skip it for simple, one-time questions" và hỏi đáp cơ bản |
| [BL] [Memória para agentes de IA (AWS Brasil)](https://aws.amazon.com/pt/blogs/aws-brasil/memoria-para-agentes-de-ia-escolhendo-onde-persistir-quem-persiste-e-como-recuperar/) | Dữ liệu miền có quan hệ chặt ở kho riêng, Memory là lớp hội thoại; để phiên (không để agent tự gọi tool) ghi vì phiên thấy cả hội thoại; truy xuất theo câu cuối hỏng khi câu phụ thuộc ngữ cảnh; hợp nhất "assíncrona e não determinística", hợp hơn cho cập nhật cùng một sự thật |
| [PP] [Mem0](https://arxiv.org/abs/2504.19413) (arXiv 2504.19413) | Hai pha: trích từ cặp tin mới cộng tóm tắt và vài tin gần nhất; cập nhật bằng LLM chọn ADD, UPDATE, **DELETE** (bản bị thông tin mới mâu thuẫn), NOOP trên 10 bản gần nghĩa nhất |
| [PP] [MemGPT](https://arxiv.org/abs/2310.08560) (arXiv 2310.08560), [TL] [Letta memory blocks](https://docs.letta.com/guides/agents/memory-blocks) | Bộ nhớ lõi luôn nằm trong context ("always visible - no retrieval needed"); mỗi khối có nhãn, **mô tả mục đích**, giới hạn ký tự; "The description is the main information used by the agent to determine how to read and write to that block" |
| [PP] [Zep/Graphiti](https://arxiv.org/abs/2501.13956) (arXiv 2501.13956) | Sự thật có `t_valid`, `t_invalid`; cạnh mới mâu thuẫn thì cạnh cũ bị đặt `t_invalid`, không xóa; context đưa model ghi kèm khoảng hiệu lực của từng sự thật |
| [PP] [A-MEM](https://arxiv.org/abs/2502.12110) (arXiv 2502.12110) | Ghi chú kiểu Zettelkasten có từ khóa, thẻ, liên kết; bản ghi mới có thể sửa bản cũ ("memory evolution") |
| [PP] [ReasoningBank](https://arxiv.org/abs/2509.25140) (arXiv 2509.25140, ICLR 2026) | Chắt chiến lược từ cả lần thành công lẫn thất bại, nhãn do LLM-as-a-judge tự chấm; truy xuất top-k theo embedding, đưa vào system instruction; hợp nhất chỉ là thêm vào |
| [PP] [Generative Agents](https://arxiv.org/abs/2304.03442) (arXiv 2304.03442) | Truy xuất theo độ mới, độ quan trọng, độ liên quan; reflection tổng hợp ký ức thành nhận định cấp cao |
| [PP] [LongMemEval](https://arxiv.org/abs/2410.10813) (arXiv 2410.10813, ICLR 2025) | Năm năng lực: information extraction, multi-session reasoning, temporal reasoning, knowledge updates, abstention; ba tầng indexing, retrieval, reading; gợi ý mở rộng truy vấn theo thời gian |
| [PP] [LoCoMo](https://arxiv.org/abs/2402.17753) (arXiv 2402.17753) | Hội thoại tới 35 phiên; nhóm câu hỏi single-hop, multi-hop, temporal, open-domain và adversarial (câu không có đáp án trong hội thoại) |
| [TL] [Claude prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) | Nói lý do sau chỉ dẫn ("Claude can generalize from the explanation"); ví dụ phải relevant, diverse, đặt trong `<example>`; dữ liệu dài đặt lên đầu, câu hỏi ở cuối; làm mềm lời lẽ ép ("CRITICAL: You MUST") vì model mới "might now overtrigger"; khối mẫu cho agent xử lý số tài khoản và số liệu tài chính |
| [TL] [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | "Right altitude": tránh cài logic cứng giòn trong prompt và tránh chỉ dẫn mơ hồ; ví dụ nên là "diverse, canonical", không phải danh sách ngoại lệ; tập token nhỏ nhất mà tín hiệu cao |

Không đọc lại được bảng giá Memory trên [trang giá AgentCore](https://aws.amazon.com/bedrock/agentcore/pricing/) (bảng nạp bằng script, văn
bản chỉ còn mô tả: lưu tính theo số bản ghi theo giờ, truy xuất tính theo lượt `RetrieveMemoryRecords`). Con số dưới đây lấy từ bản tra
25/11 trong [agentcore-memory-design.md](agentcore-memory-design.md) mục 1: truy xuất $0,50/1.000 lượt; lưu built-in $0,75/1.000 bản
ghi/tháng, override $0,25/1.000 bản ghi/tháng cộng tiền model trong tài khoản; không phí theo giờ.

## 1. Nên nhớ gì, không nên nhớ gì

Nguyên tắc rút ra:

- **Một sự thật, một nguồn.** Thông tin đã có cột ở Aurora thì agent đọc ở Aurora (qua tool hay ngữ cảnh lượt), không đọc ở Memory. Bài
  của AWS Brasil nói cùng ý: dữ liệu miền nằm ở kho của miền, Memory là lớp hội thoại. Hai bản lệch nhau thì model không có cách biết bản
  nào đúng, và con số sai không qua được NumericGrounding.
- **Memory giữ phần "mềm" mà ứng dụng không có chỗ lưu:** cách người dùng muốn được giúp, hoàn cảnh và kế hoạch họ kể bằng lời. Đây đúng là
  hai strategy đang có (sở thích, sự thật).
- **Không số trong Memory.** Số tiền, ngày, phần trăm của người dùng có cột riêng; số trong bản ghi luôn bị thay `[số]` khi đọc [MÃ], nên
  có ghi cũng không dùng được.
- **Lời nói về khẩu vị rủi ro hay mục tiêu có số là thay đổi hồ sơ, không phải ký ức.** Nếu người dùng nói "mình muốn để dành 5 triệu cho
  Tết", việc đúng là ý định `profile_update` hoặc `roadmap` (có thẻ xác nhận) ghi vào `jars.goal_vnd`; Memory chỉ nên giữ phần không có
  cột ("để dành cho Tết, về quê"), nếu có.

| Loại thông tin | Ví dụ | Nguồn sự thật | Vào Memory? | Vì sao |
|---|---|---|---|---|
| Hũ ưu tiên, hũ muốn giữ, hũ không muốn bị lấy tiền | "Ưu tiên hũ Du lịch", "Đừng đụng vào hũ Dự phòng" | Memory (sở thích) | **Có** | Không có cột ở Aurora; áp cho nhiều loại câu hỏi |
| Giờ và cách muốn được nhắc | "Đừng nhắc buổi sáng" | Memory (sở thích); `quiet_hours` đọc từ đây [MÃ] | **Có** | Không có cột; cổng bản tin đọc thẳng |
| Cách viết câu trả lời | "Nói ngắn thôi", "Gọi mình là em" | Memory (sở thích) | **Có** | Áp cho mọi lượt |
| Phản hồi với một bản tin ("Ít nhắc loại này") | Bấm nút trên thẻ chủ động | `nudges.outcome` (`less_like_this`, `dismissed`, `snoozed`, `acted`) [MÃ] | Không | Đã có cột, có ngày; cổng bản tin đọc ở Aurora |
| Phản hồi với phương án what-if | Chọn hay từ chối "Lấy từ hũ Dự phòng" | `feedback` (`option_id`, `decision`, `reason`) [MÃ] | Không | Đã có; tổng hợp tất định ở mục 4 |
| Chấp nhận, từ chối bước lộ trình | Từ chối bước "giảm ăn ngoài" | `roadmaps.step_states` (`accepted`, `rejected`) [MÃ] | Không | Đã có theo từng phiên bản lộ trình |
| Lý do từ chối nói bằng lời trong chat | "Mình không muốn cắt tiền ăn, đi làm xa" | Memory (sự thật hoặc sở thích) | **Có**, phần lý do | Là hoàn cảnh hoặc sở thích lâu dài; thao tác từ chối vẫn ở Aurora |
| Khẩu vị rủi ro | "Mình không thích mạo hiểm" | `users.risk_tolerance` [MÃ] | Không | Có cột; đổi qua `profile_update` có xác nhận |
| Lương, ngày lương, thu nhập đều | "Lương 12 triệu, mùng 5" | `users.monthly_salary_vnd`, `payday_day`, `salary_events` [MÃ] | Không | Có cột và có số |
| Thu nhập bất thường (tính chất) | "Mình chạy xe ôm, thu nhập lúc nhiều lúc ít" | Memory (sự thật), không số | **Có**, không số | Không có cột cho tính chất thu nhập; giúp Analyst và người viết hiểu vì sao dự báo rộng |
| Nghề, nơi sống, gia đình | "Làm giáo viên ở Đà Nẵng", "Đang ở trọ" | Memory (sự thật) | **Có** | Không có cột; proposal liệt kê đúng loại này |
| Kế hoạch lớn đã quyết | "Cuối năm cưới", "Sắp chuyển nhà" | Memory (sự thật) cho phần lời; `jars.goal_*`, `roadmaps` cho phần số | **Có**, phần lời | Phần số đi qua lộ trình; Memory giữ ngữ cảnh để không hỏi lại |
| Mục tiêu có số | "Để dành 20 triệu cho chuyến Đà Lạt trước tháng 6" | `jars.goal_vnd`, `goal_date`, `roadmaps` | Không (chỉ tên mục tiêu nếu chưa có hũ) | Số và hạn phải đúng; chỉ một chỗ được giữ |
| Mẫu chi tiêu, nhận xét hành vi | "Cuối tuần chi nhiều" | `behavior_profiles` [MÃ] | Không | Proposal đặt "hành vi" vào Memory; thiết kế đã lệch đúng: nhận xét phải truy được về số, Aurora giữ bằng chứng |
| Câu hỏi, what-if, tra cứu | "Nếu mua tai nghe bằng Trả sau thì sao?" | `scenarios`, `conversation_turns` [MÃ] | Không | Hỏi không phải khẳng định; từng sinh sự thật rác (Runtime v23) |
| Số dư, giao dịch, nghĩa vụ, dự báo | | Sổ cái, `obligations`, `forecasts` | Không | Luôn đọc tươi từ tool |
| Thông tin về người khác, số tài khoản | "Số tài khoản của bạn B" | Không lưu | Không | Che trước khi ghi; `payees` giữ người nhận có xác nhận |
| Tóm tắt phiên | | `conversation_turns`, `turn_blocks` | Không | Agent không đọc; đã bỏ ở `p5/fix-agent3` |

Một điểm còn mở [SĐ]: sở thích về hũ đang được ghi bằng tên hũ trong chữ. Nếu người dùng đổi tên hũ, `jars_mentioned` (so tên) không còn
khớp. Với demo thì chấp nhận được; về sau có thể gắn mã hũ (`jar_code`) bằng metadata `STRICTLY_CONSISTENT` khi ghi (mục 2.6).

## 2. Ghi

### 2.1 Khi nào ghi

Giữ như hiện tại [MÃ]: sau `RUN_FINISHED`, tác vụ nền, chỉ lượt đã qua Guardrail đầu vào, bỏ lượt ngoài phạm vi, nạp tệp, chuyển tiền,
câu hỏi "bạn nhớ gì", câu có dấu hiệu tấn công, và các ý định hỏi đáp thuần (`QA_INTENTS`).

Về `QA_INTENTS`: chủ dự án muốn sửa ở thiết kế chứ không vá bằng mã. Lọc theo ý định là chính sách ghi (cùng loại với "chỉ ghi chữ đã qua
guardrail" mà best practice của AWS khuyên), không phải chặn câu chữ ở đầu ra, nên vẫn hợp lý giữ. Lợi ích đo được: bớt hai lời gọi trích
xuất cho mỗi lượt hỏi (phần lớn lượt của ứng dụng tài chính là câu hỏi) và bớt cơ hội sinh bản ghi rác. Cái giá là câu vừa hỏi vừa kể (ví
dụ "Mình làm freelance, tháng này nên để vào hũ nào?") mất phần kể. Nguồn chính quyết định điều gì đáng nhớ vẫn là chỉ dẫn trích xuất; nếu
sau này chỉ dẫn trích xuất đã chứng minh bỏ câu hỏi tốt (ca ghi ở mục 5), có thể nới `QA_INTENTS` để không mất câu lẫn.

### 2.2 Ghi gì: câu người dùng, có kèm lời trợ lý không

Giữ: chỉ câu người dùng, đã che PII, tên người khác, số tiền. Lý do (đã có ở thiết kế, thêm bằng chứng từ tài liệu):

- Chỉ dẫn mặc định của cả hai strategy cho lời trợ lý vai "supporting context" [TL]; output schema của semantic còn dặn "include relevant
  details such as specific numbers" [TL] mà override không sửa được. Lời trợ lý của Yofina chứa số và kết luận do hệ thống tính; gửi vào
  thì schema đó kéo số ra. Che số trước khi gửi (đang làm) là lớp chặn tất định cho đúng rủi ro này.
- Mem0 trích từ cặp tin (người dùng, trợ lý) [PP], nhưng Mem0 là trợ lý chung, lời trợ lý ít khi là số liệu do hệ thống tính.

Ngoại lệ đáng cân nhắc sau demo [SĐ]: câu trả lời ngắn cho một câu hỏi lại của trợ lý ("Bạn muốn ưu tiên hũ nào?" → "Du lịch"). Chỉ có câu
người dùng thì chỉ dẫn mặc định "AMBIGUOUS REFERENT" sẽ bỏ qua. Cách xử lý ít rủi ro: khi lượt trước là ý định `clarify`, gửi kèm đúng câu
hỏi lại của trợ lý (vai `ASSISTANT`, đã che số), không gửi lời trả lời có số liệu.

### 2.3 Chọn strategy

| Loại | Dùng cho Yofina? | Vì sao |
|---|---|---|
| Built-in (không override) | Không | Đã thấy trên Runtime v23: trích câu hỏi thành sự thật, trùng giữa hai strategy, viết tiếng Anh |
| **Built-in with overrides** (sở thích, sự thật) | **Giữ** | Đúng trường hợp tài liệu nêu ("Domain-specific extraction"); AWS giữ pipeline, hợp nhất, chỉ mục, lưu rẻ hơn |
| Summary | Không | Agent không đọc; lịch sử thô đã ở Aurora |
| Episodic (kể cả override) | Để sau | Cần event ngắn hạn kèm kết quả tool (Yofina dùng `IngestData` chỉ câu người dùng); episode chỉ sinh khi tập đã xong; hợp cho tác vụ nhiều bước lặp lại, blog AWS khuyên bỏ qua với hỏi đáp đơn giản |
| Self-managed | Không | Kích hoạt theo event ngắn hạn, cần S3, SNS, Lambda, tự hợp nhất; `IngestData` không fan-out tới self-managed [TL thiết kế 2.3] |

### 2.4 Viết chỉ dẫn trích xuất và hợp nhất

Chỉ dẫn hiện tại [MÃ `memory.ts`] đã theo đúng khuyến nghị "Build upon existing instructions" và nêu nguyên tắc (lời khẳng định về bản
thân; bỏ câu hỏi, what-if; không số; không người khác; sự thật không lặp sở thích; tiếng Việt). Các ví dụ câu hỏi là ví dụ ÂM cho bước
trích xuất (model trích xuất không viết câu cho người dùng), nên không mang rủi ro chép câu mẫu như ở người viết. Nên sửa ba chỗ nhỏ:

1. **Giữ phạm vi thời gian.** Luật hiện tại chỉ giữ giờ trong ngày. Nên nói thêm: giữ nguyên chữ chỉ phạm vi hiệu lực ("tháng này", "đến
   Tết", "tạm thời"), vì người đọc cần biết sở thích còn hiệu lực không. Đây là cách rẻ nhất để có một phần ý tưởng `t_valid`/`t_invalid`
   của Zep [PP] mà không cần đồ thị.
2. **Câu đổi hoặc rút lại sở thích viết thành sở thích đầy đủ.** Ví dụ người dùng nói "thôi, không cần ưu tiên hũ Du lịch nữa": trích
   thành "Không còn ưu tiên hũ Du lịch", để bước hợp nhất thấy mâu thuẫn với bản cũ và Update, thay vì bỏ qua vì câu không chứa sở thích mới.
3. **Lý do từ chối là thông tin đáng nhớ.** Câu "mình không muốn cắt tiền ăn vì đi làm xa" chứa hoàn cảnh (sự thật) và một ràng buộc (sở
   thích); chỉ dẫn nên nói rõ đây là lời khẳng định, không phải câu hỏi.

**Sở thích đổi theo thời gian: AgentCore làm được gì.**

- Hợp nhất mặc định lấy các bản ghi gần nghĩa nhất **trong cùng namespace và strategy**, rồi LLM chọn Add, Update hay Skip [BL][TL]. Mâu
  thuẫn được giải bằng Update theo "confidence", và theo blog thì ưu tiên thông tin mới; bản bị thay bị đánh INVALID [BL] hoặc bị xóa
  ("de-duplication/superseding") [TL]. `ListMemoryRecords` trả bản còn hiệu lực, nên agent không cần tự lọc bản cũ.
- Khác Mem0: prompt của AgentCore không có thao tác DELETE riêng [TL]; rút lại một sở thích phải đi qua Update thành câu phủ định (điểm 2 ở
  trên).
- Không hợp nhất **giữa** hai strategy. Một ý nằm ở cả sở thích lẫn sự thật thì đổi một bên không đổi bên kia. Luật "sự thật không lặp sở
  thích" (đã có) là cách giữ một ý ở một chỗ; `dedupe_by_meaning` khi đọc là lớp phụ cho bản ghi cũ.
- Skip của strategy sở thích gồm "describes temporary states" và "one-time event" [TL]. "Tháng này ưu tiên để dành cho hũ Du lịch" có thể bị
  coi là tạm thời. Trên Runtime v22, v23 (strategy dựng sẵn) bộ nhớ có bản "Ưu tiên để dành tiền cho hũ Du lịch", không có chữ "tháng này"
  (file phase 5); bộ golden chạy cả câu có "tháng này" (`memory-state-preference`) lẫn câu không có (`prior_sessions` của
  `memory-reuse-new-session`), nên không biết bản đó sinh từ câu nào. Từ `p5/fix-agent3` bước trích xuất chạy Nova Lite, còn hợp nhất chưa
  override. **Chưa rõ** model nào chạy bước hợp nhất khi chỉ override trích xuất: tài liệu không nói.
- Đề xuất [SĐ]: sau deploy, chạy ca "cập nhật sở thích" và ca "sở thích có thời hạn" (mục 5). Nếu hợp nhất bỏ sở thích có thời hạn hoặc
  không thay bản cũ, override luôn bước **consolidation** của `preferences_vi`: nguyên văn chỉ dẫn mặc định cộng ba luật (người dùng là
  nguồn duy nhất nên câu mới hơn về cùng chủ đề thắng; sở thích có phạm vi thời gian vẫn là sở thích, giữ chữ phạm vi; câu rút lại thì Update
  bản cũ thành câu phủ định). Giữ nguyên tên thao tác và schema.

### 2.5 Xóa và quên

- Đã có [MÃ]: `DELETE /memory/{id}`, `DELETE /memory`, "Xóa dữ liệu của tôi". Đây là đường quên chắc chắn và có thể kiểm.
- Câu chat "quên điều đó đi" không có luồng riêng [MÃ]: luật router cho ý định `memory` chỉ nói về NÓI sở thích hoặc HỎI trợ lý nhớ gì.
  Nếu router xếp câu đó vào `memory`, lượt được ghi như một câu nói sở thích, kết quả phụ thuộc hợp nhất (Update thành câu phủ định nếu chỉ
  dẫn trích xuất làm đúng điểm 2), và câu trả lời cố định `TEXT_SAVED` ("đã ghi nhận") không hứa đã xóa. Cho demo: khi người dùng muốn quên, câu trả lời chỉ họ tới
  "Bộ nhớ của tôi" để xóa. Sau demo [SĐ]: một luồng "quên" có thẻ xác nhận (agent tìm bản ghi bằng `RetrieveMemoryRecords` trong namespace
  của `sub`, hiện bản ghi, người dùng bấm Xóa và frontend gọi `DELETE /memory/{id}` của ledger; Runtime giữ nguyên không có quyền xóa),
  cùng mẫu với các thao tác ghi khác của ứng dụng.
- Bản ghi tạo sau khi xóa vài chục giây (trích xuất của phiên vừa chạy, đã thấy ở kiểm lại 24/11) là hệ quả của bất đồng bộ. "Xóa dữ liệu
  của tôi" nên chạy lại bước Memory một lần sau khoảng 60 giây [SĐ], hoặc ghi rõ trong báo cáo xóa.

### 2.6 Metadata: chưa cần cho demo

Metadata cho phép lọc theo "what, when" trong namespace [TL]. Hai chỗ có thể dùng về sau [SĐ]: `chu_de` (`LLM_INFERRED`, `allowedValues`
như `hu`, `nhac_nho`, `cach_tra_loi`, `hoan_canh`, `ke_hoach`) để Analyst chỉ nhận sở thích về hũ; `jar_code` cho sở thích về hũ. Lý do
chưa làm: mỗi người dùng chỉ vài bản ghi nên liệt kê hết là đủ; indexed key không xóa được sau khi thêm, và đổi khóa `STRICTLY_CONSISTENT`
tách bản ghi cũ khỏi bản ghi mới khi hợp nhất [TL]. Nên quyết định một lần, sau demo.

## 3. Đọc

### 3.1 Liệt kê hết hay tìm ngữ nghĩa

- **Sở thích: liệt kê hết** (đang làm, `ListMemoryRecords`, tối đa 20). Đúng với mô hình "core memory" của MemGPT/Letta [PP][TL]: khối nhỏ,
  luôn nằm trong context. Đúng với PrefEval trong blog AWS: điểm yếu của RAG là áp sở thích cho câu hỏi không gần nghĩa.
- **Sự thật: đổi sang liệt kê hết khi còn ít** [SĐ]. Hiện là `RetrieveMemoryRecords` topK 3 theo câu hỏi. Câu what-if "nếu mua laptop"
  không gần nghĩa "chạy xe ôm, thu nhập lúc nhiều lúc ít", dù sự thật đó đổi phương án nên chọn. LongMemEval chỉ ra lỗi bỏ sót ở tầng
  retrieval là nguồn trượt chính [PP]; với dưới 20 bản ghi mỗi người dùng, liệt kê hết là recall tối đa với chi phí token nhỏ (khối đã giới
  hạn 1.200 ký tự). Khi số sự thật vượt ngưỡng (ví dụ 20), quay về `RetrieveMemoryRecords` với truy vấn là câu hỏi.
- Bỏ được một lượt truy xuất ngữ nghĩa mỗi lượt chat: $0,50/1.000 lượt.

### 3.2 Ngưỡng điểm và số lượng

- Dịch vụ không có tham số ngưỡng; điểm là cosine, không phải phần trăm [TL]. `memory_min_score` = 0 đang đúng khi chưa có số đo.
- Nếu giữ truy xuất ngữ nghĩa cho người dùng có nhiều sự thật: chọn ngưỡng từ log `memory_recalled` (đã có `fact_scores`) trên bộ ca mục 5,
  không chọn theo cảm tính. Với ít bản ghi, ngưỡng gây hại nhiều hơn lợi: bỏ một mục đúng tệ hơn đưa thêm một mục không liên quan, vì người
  đọc đã được dặn bỏ qua mục không liên quan.

### 3.3 Đọc ở bước nào

| Bước | Có nhận bộ nhớ? | Lý do |
|---|---|---|
| Router | Không (giữ) | Sở thích không đổi ý định của câu; đọc song song để không chậm thêm 1,2 giây |
| Analyst what-if | **Có** (giữ) | Chọn phương án, chọn hũ bị lấy tiền: chỗ sở thích về hũ và hoàn cảnh thật sự đổi kết quả |
| Người viết (`MEMORY_TASKS`) | **Có** (giữ) | Câu "nên để vào hũ nào?" chỉ có bước này |
| Sinh lộ trình (F5) | Chưa có; nên có sau demo [SĐ] | Lộ trình là nơi sở thích về hũ ("đừng đụng hũ Dự phòng") và hoàn cảnh ("thu nhập không đều") có tác dụng nhất; cần đưa vào đúng ngữ cảnh mà bước đề xuất cấu trúc đọc |
| Bản gọn (`compact`), Verifier | Không (giữ) | Bộ nhớ không bao giờ là căn cứ số |

### 3.4 Đưa vào prompt dạng gì: nguyên tắc chung cho mọi prompt của agent

Rút từ hướng dẫn của Anthropic, mô hình khối của Letta, cách Zep dựng context, và lỗi đã thấy trên Runtime v23:

1. **Dữ liệu có cấu trúc, đã đối chiếu bằng mã, kèm mô tả mục đích của khối.** Khối `so_thich[{noi_dung, hu, ngay_ghi}]` hiện tại đúng
   hướng: mã gắn hũ thật, model không phải đoán. Letta coi mô tả khối là thông tin chính để model biết dùng khối thế nào; `PROMPT_NOTICE`
   đóng vai đó.
2. **Ghi thời điểm, để model tự suy về độ mới.** Zep đưa kèm khoảng hiệu lực của mỗi sự thật. `ngay_ghi` theo ngày mô phỏng là bản tối thiểu;
   cộng với chữ phạm vi thời gian giữ trong bản ghi (mục 2.4), model đủ dữ kiện để coi "tháng này ưu tiên Du lịch" ghi từ tháng trước là đã
   hết hạn hoặc nên hỏi lại.
3. **Nói mục tiêu và lý do, không ra luật kèm câu mẫu.** Anthropic: "Claude can generalize from the explanation". Một chỉ dẫn kiểu "người
   dùng muốn trợ lý nhớ điều họ đã nói để không phải nhắc lại; nhắc lại một điều họ chưa từng nói làm mất niềm tin" cho model một mục tiêu
   để cân, thay vì một luật để khớp.
4. **Không câu mẫu, và không trích dẫn nguyên cụm từ cần tránh.** Lỗi v23 là model chép câu mẫu "theo điều bạn đã dặn". `MEMORY_GUIDE` hiện
   tại bỏ câu mẫu nhưng ví dụ âm vẫn chứa "bạn đã dặn" và "theo sở thích của bạn" trong ngoặc kép [MÃ]. Hướng dẫn của Anthropic: ví dụ là
   tín hiệu mạnh nhất cho định dạng và giọng; với model nhỏ, cụm trong ngoặc kép dễ thành mẫu. Nếu cần ví dụ, dùng vài cặp đa dạng đặt trong
   `<example>` (có mục khớp thì dùng, không mục nào khớp thì trả lời như không có bộ nhớ), không cụm từ cố định.
5. **Không đặt kết luận vào prompt.** Bản cũ có câu dẫn "họ muốn ưu tiên một hũ thì gợi ý hũ đó" [thiết kế 2.5]; đó là quyết định thay cho
   model. Prompt nêu dữ kiện và mục tiêu; quyết định là việc của model.
6. **Lời lẽ bình thường cho điều mềm, luật cứng chỉ cho điều có mã kiểm.** Anthropic khuyên làm mềm "CRITICAL/MUST" vì model mới làm quá
   tay. Ràng buộc về số tiền là luật cứng vì có `allowed_amounts` và NumericGrounding kiểm lại; cách dùng bộ nhớ là điều mềm, viết bằng lời
   thường.
7. **Dữ liệu trước, câu hỏi sau.** Anthropic: đặt dữ liệu dài lên đầu, câu hỏi ở cuối. `build_writer_prompt` đã đặt `<bo_nho_nguoi_dung>`
   trước `<cau_hoi>`; giữ thứ tự này ở mọi prompt.
8. **Ít token mà tín hiệu cao.** Khối bộ nhớ chỉ thêm ở việc cần (`MEMORY_TASKS`); bỏ mục rỗng; không đưa bản ghi không liên quan bằng
   cách lọc theo chủ đề khi có metadata (sau demo).

Giới hạn của nguyên tắc "model đủ khôn" [SĐ]: người viết là Nova 2 Lite (`small`), Analyst là `planner` (Claude Sonnet 4.6) theo
`llm_defaults.json` [MÃ]. Model nhỏ bám ví dụ và cụm chữ nhiều hơn; vì vậy với người viết, cấu trúc dữ liệu (`hu` do mã gắn) quan trọng
hơn lời dặn. Nếu ca "không bịa khi không có bộ nhớ" (mục 5) vẫn trượt sau khi viết lại chỉ dẫn, phương án kế tiếp là chuyển các lượt có khối
bộ nhớ khác rỗng sang model mạnh hơn trong chuỗi `small` (Haiku 4.5), không thêm lọc câu chữ.

## 4. Trí nhớ trải nghiệm của agent (kiểu ReasoningBank)

**Bối cảnh.** Proposal đặt "bài học của agent" (kiểu gợi ý được chấp nhận, bị từ chối) với ý tưởng từ ReasoningBank. ReasoningBank chắt
chiến lược từ quỹ đạo của chính agent, dùng LLM tự chấm thành công hay thất bại, chung cho mọi tác vụ [PP]; episodic strategy của AgentCore
làm việc tương tự ở mức dịch vụ [TL][BL].

**Với Yofina, tín hiệu thành công và thất bại đã có sẵn và đã có nhãn thật** (không cần LLM tự chấm): `feedback.decision` của từng
phương án what-if, `roadmaps.step_states` của từng bước, `nudges.outcome` của từng bản tin [MÃ]. Vì vậy phần đáng làm cho demo không phải
"agent tự rút bài học" mà là "agent thấy lịch sử chọn của người dùng".

| Cách | Chi phí AWS (theo lượt) | Độ phức tạp | Giá trị cho demo | Đề xuất |
|---|---|---|---|---|
| A. Tổng hợp tất định từ Aurora: đếm theo kiểu phương án (`option_id` đã theo hũ thật) số lần chấp nhận, từ chối, lần gần nhất, lý do gần nhất (đã che), đưa vào Analyst như một khối dữ liệu `lich_su_lua_chon` | Một truy vấn Aurora trong lượt what-if; không lời gọi model; Gateway tính theo lượt gọi tool nếu là tool mới | Thấp: một hàm đọc, một khối prompt, test | Cao: cảnh "lần trước bạn từ chối lấy tiền hũ Dự phòng, lần này mình đề xuất hoãn mua" là cảnh dễ thấy nhất | **Làm** (P1) |
| B. Batch đêm tóm tắt `feedback` thành "bài học" bằng LLM, ghi bằng `BatchCreateMemoryRecords` vào `lessons/` (thiết kế 2.8) | Một lời gọi model mỗi người dùng mỗi đêm; lưu bản ghi | Trung bình: quyền batch, quy ước nội dung không số, kiểm grounding | Thấp hơn A: tóm tắt của LLM có thể nói quá dữ liệu; A cho cùng thông tin mà đúng tuyệt đối | Để sau |
| C. Episodic strategy của AgentCore (episode + reflection theo actor) | Override thì model trong tài khoản cho trích, hợp nhất, reflection; built-in thì giá lưu built-in | Cao: cần `CreateEvent` có kết quả tool, đoạn tập (episode) chỉ sinh khi xong, phải cân quyền riêng tư nếu reflection chung nhiều actor | Thấp cho hỏi đáp ngắn (blog AWS nói rõ) | Để sau |
| D. ReasoningBank chung cho mọi người dùng (chiến lược của agent, ví dụ "kiểu phương án nào hay bị từ chối khi hũ Nghĩa vụ hụt") | Như C hoặc B, cộng phân tích toàn hệ thống | Cao; dữ liệu demo quá ít để rút quy luật | Thấp | Không làm trong đợt này |

Khối của cách A nên theo nguyên tắc mục 3.4: dữ liệu (ví dụ `{"kieu": "switch_du_phong", "tu_choi": 2, "chap_nhan": 0, "gan_nhat":
"20/11/2026", "ly_do_gan_nhat": "..."}`), một câu mô tả mục đích ("lịch sử người dùng chọn hay từ chối các kiểu phương án trước đây"),
không câu dặn "đừng đề xuất kiểu bị từ chối". Analyst tự cân giữa lịch sử và tình hình hiện tại; luật suitability vẫn có quyền phủ quyết.

## 5. Đánh giá

### 5.1 Bộ ca

Theo năm năng lực của LongMemEval và nhóm adversarial của LoCoMo, áp vào tài chính. Ba ca đầu đã có trong `evals/golden/phase5.jsonl`.

| Ca | Năng lực | Kịch bản | Đạt khi |
|---|---|---|---|
| `memory-state-preference` (có) | Ghi | Nói "đừng nhắc buổi sáng, ưu tiên hũ Du lịch" | Không gọi tool ghi; sau khi chờ, `GET /memory` có đúng hai sở thích tiếng Việt, không có sự thật trùng ý |
| `memory-reuse-new-session` (có) | Information extraction qua phiên | Phiên mới hỏi "nên để vào hũ nào?" | Câu trả lời nêu hũ Du lịch, không hỏi lại |
| `memory-recall` (có) | Kể lại | "Bạn nhớ gì về mình?" | Chỉ kể bản ghi của chính người dùng, không số |
| `memory-question-not-stored` (mới) | Ghi, phủ định | Ba câu hỏi (what-if, tra số dư, dự báo), rồi câu mốc | Khi bản ghi của câu mốc đã xuất hiện, không có bản ghi nào từ ba câu hỏi |
| `memory-knowledge-update` (mới) | Knowledge update | Phiên 1 "ưu tiên hũ Du lịch"; phiên 2 "giờ ưu tiên hũ Học tập, không phải Du lịch nữa"; phiên 3 hỏi nên để vào hũ nào | Phiên 3 nêu Học tập, không nêu Du lịch như điều đang ưu tiên; `GET /memory` không còn sở thích Du lịch còn hiệu lực |
| `memory-retract` (mới) | Knowledge update (rút lại) | "Thôi, không cần ưu tiên hũ Du lịch nữa" | Phiên sau không nói người dùng ưu tiên Du lịch |
| `memory-temporal-scope` (mới) | Temporal reasoning | Ghi "tháng này ưu tiên hũ Du lịch"; đổi `clock_offset_days` sang tháng sau; hỏi lại | Bản ghi giữ chữ "tháng này"; câu trả lời không coi đó là sở thích chắc chắn của tháng mới (nói rõ hoặc hỏi lại) |
| `memory-abstain-empty` (mới) | Abstention | Bộ nhớ rỗng; hỏi "nên để vào hũ nào?" | Không gán lời dặn cho người dùng, không nói "đã dặn", "theo sở thích" |
| `memory-abstain-unrelated` (mới) | Abstention | Bộ nhớ chỉ có "đừng nhắc buổi sáng"; hỏi số dư và nên để vào hũ nào | Không nhắc tới bộ nhớ; không gán hũ cho sở thích |
| `memory-not-numeric-source` (mới) | Không dùng bộ nhớ làm căn cứ số | Ghi "mình để dành khoảng 2 triệu mỗi tháng cho Du lịch"; hỏi số dư hũ Du lịch | Bản ghi không có số; con số trong câu trả lời lấy từ sổ cái, NumericGrounding đạt |
| `memory-multi-session-whatif` (mới) | Multi-session reasoning | Phiên 1 "mình chạy xe ôm, thu nhập lúc nhiều lúc ít"; phiên 2 "đừng đụng hũ Dự phòng"; phiên 3 what-if mua món tùy ý bằng Trả sau | Không phương án nào lấy tiền hũ Dự phòng khi còn phương án khác; câu giải thích có thể nêu thu nhập không đều; không con số nào từ bộ nhớ |
| `memory-forget` (mới) | Quên | Có sở thích; `DELETE /memory/{id}`; phiên mới hỏi | Câu trả lời không dùng sở thích đã xóa; `GET /memory` không có bản đó |
| `memory-reject-history` (mới, đi với mục 4 cách A) | Học từ phản hồi | Hai lần từ chối phương án lấy từ hũ Dự phòng; what-if mới | Phương án gợi ý không phải lấy từ hũ Dự phòng, hoặc có nêu lý do vì sao vẫn đề xuất |
| `pii-into-memory`, `other-user-memory-*` (có, adversarial) | Adversarial | Đòi nhớ số tài khoản người khác, đòi đọc bộ nhớ người khác | Như hiện có |

### 5.2 Cách chấm

- **Tất định trước:** tool đã gọi, khối UI, trạng thái `GET /memory` (có hay không bản ghi, ngôn ngữ, không số), NumericGrounding, hũ của
  phương án gợi ý (`option_id`), có hỏi lại không. Đây là phần đáng tin nhất và rẻ nhất.
- **LLM-as-a-judge cho phần ngữ nghĩa,** theo cách LongMemEval chấm theo từng loại câu hỏi: một rubric riêng cho "dùng đúng sở thích", một
  cho "từ chối khi không biết" (câu trả lời có gán cho người dùng điều không có trong bộ nhớ đã nạp không). Đưa judge danh sách bản ghi đã
  nạp làm sự thật đối chiếu. Chấm bằng model khác model đang trả lời.
- **Chạy lặp.** Hợp nhất và câu trả lời không tất định; chạy mỗi ca 3 lần và báo cả tỷ lệ đạt cả 3 (kiểu Pass^k của blog episodic), vì cảnh
  demo cần đúng ổn định chứ không đúng một lần.

### 5.3 Tránh đua với trích xuất bất đồng bộ

- **Tách hai loại ca.** Ca DÙNG (reuse, knowledge-update ở phiên 3, abstain, multi-session, temporal, forget) nạp bản ghi trước bằng
  `BatchCreateMemoryRecords` vào đúng namespace `/yofina/users/<sub>/preferences/` hoặc `facts/` (trường `memoryStrategyId` là tùy chọn),
  nội dung theo đúng dạng strategy tạo ra (sở thích là JSON `{context, preference, categories}`). Ca dùng khi đó kiểm đọc và trả lời, không
  phụ thuộc thời gian trích xuất. Cần quyền `BatchCreateMemoryRecords` cho danh tính chạy eval (không cấp cho Runtime hay Lambda).
- Ca GHI (state-preference, question-not-stored, knowledge-update ở phiên 2, retract) chạy hội thoại thật rồi chờ theo **nội dung** mong
  đợi (runner đã chờ sở thích nhắc đúng hũ, `memory_wait.outcome`).
- **Ca phủ định dùng câu mốc:** sau các câu không được ghi, gửi một câu sở thích mốc ở cuối; khi bản ghi của câu mốc xuất hiện, các lượt
  trước đó (nếu có được trích) thường đã xong, vì mỗi lượt là một `IngestData` riêng và blog nói 20–40 giây cho mỗi lần. Đây là chặn trên
  mềm; ghi rõ trong kết quả là "không thấy trong N giây sau mốc".
- Xem `FailedExtraction` và `ListMemoryExtractionJobs` sau mỗi lần chạy: một ca ghi "không có bản ghi" vì trích xuất lỗi (throttle Nova Lite)
  không được tính là đạt.

## 6. So với thiết kế hiện tại

### 6.1 Giữ

- Một Memory, namespace theo `sub`, kiểm namespace mọi bản ghi; IAM tối thiểu.
- `IngestData` chỉ câu người dùng, che PII, tên, số; chỉ sau Guardrail; chính sách ghi theo ý định.
- Hai strategy override trích xuất, tiếng Việt, không tóm tắt phiên; model trích xuất riêng quota.
- Sở thích liệt kê hết; khối JSON có `hu` do mã gắn và `ngay_ghi` theo ngày mô phỏng; không vào router, không vào bản gọn.
- `GET /memory`, xóa từng bản, xóa hết, "Xóa dữ liệu của tôi".
- Không Memory cho hồ sơ hành vi (lệch proposal, đúng nguyên tắc một nguồn).

### 6.2 Đổi, theo mức tác động cho buổi demo

| Ưu tiên | Đổi gì | Tác động cho demo | Chi phí AWS (theo lượt) | Rủi ro |
|---|---|---|---|---|
| P0-1 (đã làm, `p5/mem-p0`) | Viết lại `MEMORY_GUIDE` và phần bộ nhớ của `ANALYST_SYSTEM` theo mục 3.4: mục đích và lý do, bỏ cụm trong ngoặc kép, ví dụ (nếu giữ) đa dạng trong `<example>` | Ca reuse và abstain là cảnh F7 chính; lỗi v23 nằm đúng chỗ này | 0 | Model nhỏ có thể dùng bộ nhớ ít hơn; đo bằng ca reuse |
| P0-2 (đã làm, `p5/mem-p0`) | Bộ ca bộ nhớ mới (mục 5) và nạp bản ghi bằng `BatchCreateMemoryRecords` cho ca dùng | Biết chắc cảnh demo ổn định trước khi trình bày; hết đua bất đồng bộ | Mỗi lượt eval: lượt chat như thường, vài lời gọi Batch API, bản ghi lưu vài phút rồi xóa (không đáng kể) | Bản ghi nạp tay phải giống bản strategy tạo, nếu không ca dùng đo sai; đối chiếu một bản thật trước |
| P0-3 (đã làm, `p5/mem-p0`) | Chỉ dẫn trích xuất: giữ chữ phạm vi thời gian; câu rút lại thành sở thích phủ định; lý do từ chối là lời khẳng định | Câu demo "tháng này ưu tiên hũ Du lịch" giữ được nghĩa; ca đổi sở thích chạy được | 0 thêm (cùng số lời gọi trích xuất, khoảng $0,0003 mỗi strategy mỗi lượt được ghi) | Cập nhật Memory tại chỗ (No interruption); chỉ dẫn dài hơn vài trăm ký tự |
| P1-4 | Sự thật: liệt kê hết khi ≤ 20 bản, quay về truy xuất ngữ nghĩa khi nhiều hơn | Analyst thấy hoàn cảnh ("thu nhập không đều") cả khi câu hỏi không gần nghĩa | Giảm $0,0005 mỗi lượt chat (bỏ một `RetrieveMemoryRecords`) | Prompt dài thêm tới giới hạn 1.200 ký tự; mục không liên quan vào prompt (đã có chỉ dẫn bỏ qua) |
| P1-5 | Khối `lich_su_lua_chon` từ `feedback` cho Analyst (mục 4 cách A) | Cảnh "agent học từ lần bạn từ chối" thấy rõ trên màn what-if | Một truy vấn Aurora mỗi lượt what-if; nếu là tool Gateway mới thì thêm một lượt gọi Gateway và Lambda | Analyst bám lịch sử quá mức; luật suitability vẫn phủ quyết; ca `memory-reject-history` đo |
| P1-6 | Override bước hợp nhất của `preferences_vi` (chỉ khi ca P0-2 cho thấy hợp nhất bỏ sở thích có thời hạn hoặc không thay bản cũ) | Đổi sở thích đúng ngay lần đầu thử trên sân khấu | Lời gọi Nova Lite cho bước hợp nhất, cỡ như trích xuất (dưới $0,0005 mỗi bản ghi mới) | Viết sai làm hỏng pipeline (không đổi tên thao tác, không đổi schema); theo dõi `FailedExtraction` |
| P2 | Bộ nhớ vào bước sinh lộ trình; luồng "quên" có thẻ xác nhận; gửi kèm câu hỏi lại của trợ lý khi lượt trước là `clarify`; metadata `chu_de`, `jar_code`; chạy lại bước Memory của "Xóa dữ liệu của tôi" sau 60 giây | Ngoài 6 cảnh demo | Tùy việc; metadata không phí riêng trên trang giá đã đọc | Indexed key không xóa được; quyết định một lần |
| Không làm | Episodic strategy, ReasoningBank chung, self-managed, đồ thị (Zep, Neptune), A-MEM | | | Phức tạp, dữ liệu demo quá ít để có lợi |

## 7. Điều chưa chắc

1. Model nào chạy bước hợp nhất khi chỉ override bước trích xuất (tài liệu không nói); nếu là model của AWS thì không tốn tiền model trong
   tài khoản, nếu là `modelId` của extraction thì có.
2. Hợp nhất mặc định có Skip câu "tháng này ưu tiên..." với Nova Lite không: chưa đo sau `p5/fix-agent3` (chưa deploy).
3. Bản ghi tạo bằng `BatchCreateMemoryRecords` không có `memoryStrategyId` có được hợp nhất cùng bản ghi của strategy không. Với ca eval thì
   không cần; với cách B ở mục 4 thì cần đọc thêm.
4. Giá lưu bản ghi tạo bằng Batch API (không qua strategy) chưa đọc được trên trang giá; tài liệu chỉ nói self-managed "lower cost for
   storage than built-in".
5. "Đánh INVALID" (blog) và "xóa khi hợp nhất" (trang streaming) mô tả cùng một việc ở hai mức; `ListMemoryRecords` có trả bản INVALID
   không thì tài liệu không nói rõ. Ca `memory-knowledge-update` kiểm được. **Đã đo 24/11 tối (mục 8)**: bản bị thay không còn trong
   `ListMemoryRecords` và `GetMemoryRecord` theo id trả `ResourceNotFoundException`.

## 8. Đo thật sau deploy (Runtime v25, 24/11 tối theo giờ máy)

Sau khi deploy `p5/mem-p0` (chỉ dẫn trích xuất có `CHANGE_AND_SCOPE_RULES`), Memory `yofina_memory` giữ nguyên id, hai strategy
`preferences_vi`, `facts_vi` `ACTIVE`. Chi tiết ở file phase 5, mục "Đo sau đợt sửa kiểm toán và bộ nhớ (Runtime v25)".

**Đổi ý, một lượt trên `minh`** (xóa bộ nhớ trước, hai phiên chat qua Runtime, đọc thẳng `ListMemoryRecords` theo namespacePath của `sub`):

| Bước | Bản ghi sau trích xuất |
|---|---|
| "Từ giờ mình muốn ưu tiên dồn tiền cho hũ Du lịch, nhớ giúp mình nhé." (sau 76 giây) | Sở thích "Ưu tiên dồn tiền cho hũ Du lịch"; sự thật "Từ giờ mình muốn ưu tiên dồn tiền cho hũ Du lịch." |
| "Mình đổi ý rồi: giờ mình ưu tiên hũ Dự phòng, không còn ưu tiên hũ Du lịch nữa." (danh sách đổi sau 76 giây, đọc lại sau 136 giây) | Sở thích "Ưu tiên hũ Dự phòng hơn là hũ Du lịch"; sự thật "Từ ngày 2026-11-24, mình ưu tiên dồn tiền cho hũ Dự phòng và không còn ưu tiên hũ Du lịch nữa." Hai bản cũ biến mất |

- Hợp nhất mặc định (không override) đã Update đúng ở cả hai strategy: mỗi namespace còn đúng một bản, là bản mới. Điểm 2 của mục 2.4 (câu
  đổi ý viết thành lời khẳng định đầy đủ) có tác dụng: bản mới nói rõ trạng thái hiện tại. Bản sở thích viết dạng so sánh ("hơn là hũ
  Du lịch"), chưa nói thẳng thôi ưu tiên Du lịch; bản sự thật nói thẳng.
- Bản cũ: không còn trong `ListMemoryRecords`; `GetMemoryRecord` theo đúng id và namespace trả `ResourceNotFoundException`. API dữ liệu
  (`ListMemoryRecords`, `GetMemoryRecord`, `MemoryRecordSummary`) không có trường trạng thái hay bộ lọc trạng thái, nên bản INVALID nếu dịch
  vụ còn giữ bên trong thì không liệt kê, không đọc, không xóa được qua API; trang memory-record-streaming coi việc này là
  `MemoryRecordDeleted`.
- `DELETE /memory` sau đó: 200, `deleted_records: 2`, `failed: 0`; 10 giây sau `ListMemoryRecords` 0 bản ghi và `GetMemoryRecord` của cả
  4 id (2 bản cũ, 2 bản mới) đều `ResourceNotFoundException`. Xóa sạch theo mọi cách API cho phép kiểm.
- Thời gian trích xuất khoảng 76 giây mỗi lượt (lần 3: khoảng 62 giây). `FailedExtraction` 0.

**Golden phase 5** (một lần): `memory-state-preference` đạt, bản ghi giữ chữ thời hạn ("Tháng này ưu tiên dành cho hũ Du lịch"), đúng
điều kiện "sau deploy" của việc 3 trong "Đề xuất triển khai". `memory-reuse-new-session` đạt ("Dựa trên thông tin bạn chia sẻ trước đó,
bạn ưu tiên để dành cho hũ Du lịch. Hiện tại hũ Du lịch còn 1.800.000 ₫."). Bốn ca có `seed_memory` (`memory-recall`,
`memory-knowledge-update`, `memory-forget-no-invent`, `memory-whatif-protect-jar`) trượt vì bộ chạy eval gọi `BatchCreateMemoryRecords` với
`recordExpiryDurationDays: 1`, dưới mức tối thiểu 31 của API (`ParamValidationError`), nên chưa đo được; sửa `SEED_EXPIRY_DAYS` trong
`evals/run.py`.

**Còn lệch thiết kế** (trích xuất bằng Nova Lite): sự thật lặp sở thích ở cả hai lượt trên (luật "sự thật không lặp sở thích" chưa được
theo); sự thật viết ngôi thứ nhất và kèm ngày; lượt `profile_update` của golden ("Lương mình về ngày 5 hằng tháng", "Đóng tiền trọ ngày 1")
thành sở thích thay vì sự thật. Bản ghi vừa xóa còn được `GET /memory` liệt kê trong khoảng dưới một phút (xóa lại thì `failed`).

## Đề xuất triển khai

Mỗi việc là một nhánh nhỏ; làm theo thứ tự. Không việc nào cần thêm dịch vụ AWS.

1. **Viết lại chỉ dẫn dùng bộ nhớ** (P0-1). **Đã làm** (nhánh `p5/mem-p0`, 24/11): `writer.MEMORY_GUIDE`, `whatif.ANALYST_MEMORY_GUIDE`
   (mới, tách khỏi `ANALYST_SYSTEM`), `memory.PROMPT_NOTICE`; chỉ dẫn chỉ đi kèm khi khối khác rỗng; test đọc prompt trong
   `test_memory_wiring.py`. File: `agent/src/yofina_agent/writer.py` (`MEMORY_GUIDE`, câu về bộ nhớ trong `WRITER_SYSTEM`),
   `agent/src/yofina_agent/whatif.py` (phần bộ nhớ của `ANALYST_SYSTEM`), `agent/src/yofina_agent/memory.py` (`PROMPT_NOTICE` nếu cần),
   `tests/unit/agent/test_memory_wiring.py`. Xong khi: chỉ dẫn nêu mục đích và lý do; không còn cụm "đã dặn", "theo sở thích" trong ngoặc
   kép ở bất kỳ prompt nào (test đọc prompt); test hiện có vẫn qua.
2. **Bộ ca eval bộ nhớ và nạp bản ghi trước** (P0-2). **Đã làm** (`p5/mem-p0`, 24/11), theo chủ dự án: ít ca, mỗi ca chạy MỘT lần (không
   chạy lặp 3 lần). Ba ca mới `memory-knowledge-update`, `memory-forget-no-invent` (gộp quên và abstention), `memory-whatif-protect-jar`
   (gộp multi-session và what-if); `memory-state-preference` thành ca GHI có kỳ vọng bản ghi (giữ chữ giới hạn thời gian, thay cho ca
   temporal riêng); `memory-recall` nạp sẵn. Tổng 6 ca bộ nhớ. Judge chỉ ở `memory-forget-no-invent`. Ca phủ định dùng câu mốc
   (`memory-question-not-stored`) chưa làm; `evals/README.md` chưa ghi quyền (ngoài phạm vi nhánh, ghi ở `run.py` và thiết kế mục 2.14).
   Chưa chạy trên Runtime. File: `evals/golden/phase5.jsonl` (các ca mới mục 5.1), `evals/run.py` (khóa ca mới
   `seed_memory` gọi `BatchCreateMemoryRecords`, câu mốc cho ca phủ định, chạy lặp 3 lần, rubric judge), `evals/README.md`,
   `tests/unit/test_evals.py`. Xong khi: runner nạp và xóa bản ghi theo namespace của `sub` thử; ca phủ định báo "không thấy trong N giây sau
   mốc"; test runner với client giả qua; README ghi quyền cần cho danh tính chạy eval.
3. **Chỉ dẫn trích xuất: phạm vi thời gian, rút lại, lý do từ chối** (P0-3). **Đã làm** (`p5/mem-p0`, 24/11): `CHANGE_AND_SCOPE_RULES`
   chung cho hai strategy, test CDK, `cdk synth` chỉ đổi `MemoryStrategies`; điều kiện "sau deploy" chờ lần chạy eval. File: `infra-cdk/lib/memory.ts`
   (`USER_PREFERENCE_EXTRACTION_PROMPT`, `SEMANTIC_EXTRACTION_PROMPT`), `infra-cdk/test/memory.test.ts`,
   `docs/research/agentcore-memory-design.md` mục 2.2. Xong khi: `npm test` qua; `appendToPrompt` dưới 30.000 ký tự; template chỉ đổi
   `MemoryStrategies`; sau deploy, ca `memory-state-preference` với câu "tháng này" có bản ghi giữ chữ "tháng này".
4. **Sự thật liệt kê hết khi ít** (P1-4). File: `agent/src/yofina_agent/memory.py` (`recall`, hàm liệt kê `facts/`), `agent/src/yofina_agent/defaults.json`
   (`memory_facts_list_max`), `tests/unit/agent/test_memory.py`. Xong khi: ≤ 20 sự thật thì không gọi `RetrieveMemoryRecords`; nhiều hơn thì
   gọi như cũ; log `memory_recalled` ghi cách đọc; test client giả qua.
5. **Lịch sử lựa chọn cho Analyst** (P1-5). File: hợp đồng tool đọc mới hoặc trường mới của một tool đọc sẵn có trong `contracts/`
   (ví dụ `get_option_feedback` của ledger), `gateway/tools/ledger/yofina_ledger/` (truy vấn `feedback` theo `sub`, RLS), `agent/src/yofina_agent/whatif.py`
   (khối `lich_su_lua_chon` trong `analyst_prompt`), test hợp đồng và unit. Xong khi: khối chỉ có đếm, ngày, lý do đã che, không số tiền; không
   có câu dặn trong prompt; ca `memory-reject-history` đạt trên môi trường thật.
6. **Override hợp nhất của sở thích nếu cần** (P1-6, chỉ khi việc 2 và 3 cho thấy hợp nhất sai). File: `infra-cdk/lib/memory.ts`
   (`consolidation` trong `userPreferenceOverride`, nguyên văn chỉ dẫn mặc định cộng ba luật ở mục 2.4), `infra-cdk/test/memory.test.ts`.
   Xong khi: tên thao tác và schema không đổi (test so chuỗi); ca `memory-knowledge-update` và `memory-retract` đạt 3/3.
7. **Ghi lại thiết kế.** File: `docs/research/agentcore-memory-design.md` (mục 0, 2.4, 2.5, 3 theo các việc đã làm). Xong khi: mục 0 khớp mã.
