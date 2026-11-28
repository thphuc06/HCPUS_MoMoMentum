# Ghi chú tra cứu (research)

Nơi lưu kết quả tra cứu internet đáng giữ lại, để phiên sau không phải tra lại. Điểm bắt đầu cho nguồn: [../references/links.md](../references/links.md); công cụ tra AWS: [../references/aws-tooling.md](../references/aws-tooling.md).

## Khi nào ghi

- Tra tài liệu chính thức của dịch vụ/thư viện (AWS, AgentCore, Bedrock, Strands, CDK, Next.js, AG-UI, thư viện ML…) và rút ra cách làm hiện hành, giới hạn, tham số, lưu ý Region.
- Tra paper/bài tham khảo cho kỹ thuật trong proposal: Chronos-2, conformal prediction, PELT/CUSUM/ADWIN, ECOD, Croston/TSB, Monte Carlo, LP phân bổ, ReasoningBank, Mem0, AG-UI, Cedar policy, Automated Reasoning…
- Kết quả kiểm tra tính năng theo Region (việc tuần 1).

## Quy ước

- Một file mỗi chủ đề: `YYYY-MM-DD-chu-de.md` hoặc `chu-de.md` nếu sống lâu. Ví dụ `agentcore-region-availability.md`, `chronos-2-on-cpu.md`.
- Mỗi ghi chú có: câu hỏi cần trả lời, kết luận ngắn, nguồn (URL + ngày truy cập), điều chưa chắc.
- Phân biệt rõ: điều đã đọc trong tài liệu / điều đã chạy thử / điều suy đoán.
- Quyết định rút ra từ research → viết [ADR](../decisions/README.md). Nguồn mới đáng nhớ → thêm vào links.md.
- Nhớ ghi entry [ai-log](../ai-log/README.md) khi thêm ghi chú.

## Danh sách

Bảy ghi chú dưới đây do subagent (Claude Sonnet 5.5) viết ngày 2026-11-21 từ việc **đọc tài liệu**; chưa có gì được chạy thử. Mỗi file có mục "Kết luận ngắn", "Khuyến nghị cho Yofina" (kèm chỗ proposal cần chỉnh) và "Điều chưa chắc". Đọc phần kết luận trước khi code phần tương ứng; tên API và phiên bản nên đối chiếu lại tài liệu gốc lúc viết code.

| Ghi chú | Dùng khi làm |
|---|---|
| [agentcore.md](agentcore.md) | Runtime, xác thực JWT, Gateway, Policy (Cedar), Memory, Observability, Evaluations; Region và chi phí |
| [strands-agui.md](strands-agui.md) | Agent Strands: structured output, streaming, multi-agent, interrupt/resume; phát event AG-UI |
| [bedrock.md](bedrock.md) | Chọn model, quota, Guardrails, Knowledge Bases, prompt caching |
| [aws-data-events-infra.md](aws-data-events-infra.md) | Aurora + pgvector, Lambda, EventBridge/SQS, Step Functions, CDK, Amplify, Cognito, chi phí, role deploy |
| [ml-forecasting.md](ml-forecasting.md) | Dự báo theo hũ, conformal, Monte Carlo, điểm gãy, phân bổ LP, phân loại giao dịch |
| [agentic-ui-generative-ui.md](agentic-ui-generative-ui.md) | Khối UI từ JSON, hợp đồng khối, luồng xác nhận, UX cho agent |
| [frontend-fintech-ui.md](frontend-fintech-ui.md) | Stack frontend đề xuất, mẫu thiết kế app ngân hàng, biểu đồ, nhận diện |
| [spending-visualization.md](spending-visualization.md) | Biểu đồ chi tiêu (theo hũ, hũ sắp cạn, cuối tuần, Trả sau, so kỳ trước): dữ liệu từ endpoint/tool nào, khoảng trống hợp đồng, khối chat, thư viện, ưu tiên P0/P1/P2; minh họa [spending-visualization-preview.html](spending-visualization-preview.html) |
| [2026-11-26-canh4-pelt.md](2026-11-26-canh4-pelt.md) | Cảnh 4 chạy thật (#22): hệ số tăng chi tối thiểu để PELT xác nhận trên `minh` 120 ngày (2,1 lần, không đổi penalty), độ bền theo lệch ngày, tệp sao kê CSV cho giám khảo và đường phân loại không cần model; đã chạy offline |
| [2026-11-26-hu-khac.md](2026-11-26-hu-khac.md) | Hũ "Khác" 0% (#28): biến thể có hũ `khac` cần 294 lời gọi model nhỏ nên không đo được offline; đường cơ sở tái tạo offline (hỏi 17,37%, đúng 92,03%); luật khoản nhỏ một lần chạm tối đa 2/167 mục hỏi (−1,2 điểm, độ đúng −1,3 điểm), hũ 0% số dư 0 thì không chạy; đề xuất đóng, kèm lệnh đo lại |
| [2026-11-26-do-vi-ba-hu.md](2026-11-26-do-vi-ba-hu.md) | Ví 3 hũ của tài khoản mới (#39), đo offline bằng `scripts/measure_three_jars.py`: phân loại không model hỏi 39,5% (ví 7 hũ 58,1%) nhưng tự gán sai 4,2% do luật theo người nhận, phần có model chưa đo; hũ Chi hằng ngày gộp luôn là hũ dày, dải phủ thừa 0,87 (trượt cổng ở mép trên); PELT trên chuỗi gộp của `minh` cần 2,3 lần (hũ riêng 2,1) và mất độ bền lệch một ngày của tệp cảnh 4; năm khuyến nghị kèm ưu tiên trước 03/12 |
| [2026-11-26-router-model.md](2026-11-26-router-model.md) | Router chạy vai `router` (#39): Haiku 4.5 trước, Nova 2 Lite dự phòng, cache phần tĩnh, `router_max_tokens` 800, IAM không đổi (chỉ deploy Runtime); lý do từng chỗ sửa lời nhắc; bảng đường lùi của harness (`checked_route`: hũ model suy khác hũ người dùng nêu qua `spend_jar_named`, số tiền phải có trong hội thoại, `keep_previous` chỉ khi đã hỏi, kết quả bị cắt thử lại); đo lại 24 câu (19/24 sau harness, 0,00365 USD/lượt có cache, 0,0143 không cache), phân loại câu còn trượt, giới hạn đã biết |
| [eval-report.md](eval-report.md) | Bảng tổng hợp eval đầy đủ theo lượt (commit, Runtime, đạt/tổng từng bộ, ca trượt theo nguyên nhân, tiền); mốc v34 26/11, v36 28/11 |
| [2026-11-26-v33-bugs.md](2026-11-26-v33-bugs.md) | Lỗi thấy trên app sau Runtime v33 (#39): chữ router tự viết phải qua kiểm số; dữ kiện tra cứu thiếu số dư cuối kỳ và số người dùng nói; hũ người dùng tự nêu bị coi là hũ suy; chuyển bù chép giá món thay cho phần thiếu; ngày đã tính chưa vào kiểm tra trước khi chi; phần do model (xếp sai ý định cùng hội thoại, hũ của câu mới) ghi là giới hạn, không vá |

### Kiểm toán toàn dự án sau 5 phase (2026-11-25)

Bắt đầu từ [2026-11-25-audit-tong-hop.md](2026-11-25-audit-tong-hop.md): hạn nộp thật 03/12, ban giám khảo, 31 việc đã gộp (AU-01…31) xếp theo ưu tiên, giới hạn đã biết, việc không làm. Chín ghi chú chi tiết do subagent viết (Kiro CLI điều phối), mỗi ghi chú có bằng chứng file:dòng hoặc số đã chạy:

| Ghi chú | Phạm vi |
|---|---|
| [2026-11-25-audit-phase-1-2.md](2026-11-25-audit-phase-1-2.md) | Phase 1–2 so với file plan |
| [2026-11-25-audit-phase-3.md](2026-11-25-audit-phase-3.md) | Phase 3 (what-if, kiểm tra trước khi chi) |
| [2026-11-25-audit-phase-4.md](2026-11-25-audit-phase-4.md) | Phase 4 (chống chịu, lộ trình, phân hũ) |
| [2026-11-25-audit-phase-5.md](2026-11-25-audit-phase-5.md) | Phase 5 (nạp, hồ sơ, bộ nhớ, trace) và luồng K |
| [2026-11-25-audit-proposal-vs-product.md](2026-11-25-audit-proposal-vs-product.md) | Proposal F1–F7, FR/NFR, kiến trúc so với code |
| [2026-11-25-audit-ml-forecasting.md](2026-11-25-audit-ml-forecasting.md) | Dự báo, hiệu chỉnh, K5 (có số backtest offline) |
| [2026-11-25-audit-agent-aws-latency.md](2026-11-25-audit-agent-aws-latency.md) | Độ trễ, chi phí, quota Bedrock (có số từ log) |
| [2026-11-25-audit-evals-safety.md](2026-11-25-audit-evals-safety.md) | Phương pháp eval, an toàn, bảo mật |
| [2026-11-25-audit-demo-judge.md](2026-11-25-audit-demo-judge.md) | Thể lệ, câu chuyện demo, kinh doanh, bộ nộp |

### Tỷ giá cho chứng từ ngoại tệ khi nạp (2026-11-25)

[ingest-fx-rates.md](ingest-fx-rates.md): so sáu nguồn tỷ giá có VND (Vietcombank JSON theo ngày, Vietcombank XML, NHNN, ExchangeRate-API, fawazahmed0, Frankfurter) theo khóa, giới hạn gọi, điều khoản; chọn tỷ giá bán Vietcombank của ngày giao dịch, lý do, làm tròn, bộ nhớ đệm, xử lý lỗi; Lambda nạp ra internet không cần NAT.

### Kiểm toán prompt tìm overfit (2026-11-25)

[prompt-overfit-audit.md](prompt-overfit-audit.md): kiểm kê mọi prompt gửi model (file:dòng, model, độ dài, số luật), 27 phát hiện câu mẫu trùng ca eval, khuôn "đúng N câu", nhánh khớp chuỗi, luật vá ca, trùng lặp, mã chết (kèm commit và ca liên quan); các mục trông đáng ngờ nhưng hợp lệ; đánh giá bộ chấm eval; kế hoạch sửa theo đợt với cách đo.

### Thiết kế giao diện (Figma, 2026-11-21)

[figma-ui-design.md](figma-ui-design.md): link file Figma, bảng màu (tông hồng–magenta), danh mục component, 40 frame theo luồng demo và ánh xạ màn hình ↔ cảnh demo ↔ tính năng. Frame tĩnh, chưa nối prototype.

### Rà soát thiết kế UI cho demo (2026-11-24)

[ui-design-review.md](ui-design-review.md): nguyên tắc rút từ skill frontend-design, UI UX Pro Max, Vercel Web Interface Guidelines, Apple HIG, Material 3; 15 vấn đề của giao diện hiện tại; bảng màu hồng mới (thay mã `#A50064` trùng logo MoMo) kèm tỷ lệ tương phản đã tính; chữ, khoảng cách, bo góc, bóng, chuyển động; khoảnh khắc chính cho 6 cảnh demo; việc P0/P1/P2. Bản xem trước tĩnh: [ui-design-preview.html](ui-design-preview.html).

### Bộ nhớ dài hạn (2026-11-24)

- [agentcore-memory-design.md](agentcore-memory-design.md): thiết kế AgentCore Memory đang chạy (namespace, strategy override, chính sách ghi, khối prompt, REST xem và xóa, IAM).
- [long-term-memory-research.md](long-term-memory-research.md): nghiên cứu tối ưu bộ nhớ dài hạn cho Yofina (nên nhớ gì so với nguồn sự thật ở Aurora, ghi, hợp nhất khi sở thích đổi, đọc, nguyên tắc đưa bộ nhớ vào prompt, học từ phản hồi, bộ ca eval), kèm đề xuất triển khai P0/P1/P2.

### Kết quả chạy thử (spike, 2026-11-21)

Bảy thử nghiệm đã **chạy thật** (subagent Claude Sonnet 5.5). Chỗ nào spike mâu thuẫn với ghi chú đọc tài liệu thì tin spike; các ghi chú ở trên đã được đánh dấu "[Đã chạy thử 2026-11-21]" tại chỗ. Code thử nằm trong `spikes/<tên>/` (có README chạy lại); đó là bản thử, không phải code sản phẩm.

| Kết quả | Trả lời câu hỏi gì | Code |
|---|---|---|
| [spike-bedrock-models.md](spike-bedrock-models.md) | Model nào gọi được ngay (quota), độ trễ, tool use, caching, đọc ảnh và embedding tiếng Việt | `spikes/bedrock-models/` |
| [spike-strands-agui-local.md](spike-strands-agui-local.md) | Phát khối UI qua AG-UI, structured output, interrupt/resume; có mẫu code chạy được | `spikes/strands-agui-local/` |
| [spike-agentcore-runtime-cors.md](spike-agentcore-runtime-cors.md) | Trình duyệt gọi thẳng Runtime qua SSE (CORS, JWT), deploy không Docker, cold start, phiên | `spikes/agentcore-runtime-cors/` |
| [spike-agentcore-gateway-identity.md](spike-agentcore-gateway-identity.md) | Danh tính người dùng xuống tool, luật Cedar đã chạy, token xác nhận trước khi ghi. Cuối file có mục "Cần sửa trong agentcore.md" (đã áp vào [agentcore.md](agentcore.md) ngày 2026-11-21) | `spikes/agentcore-gateway-identity/` |
| [spike-aurora-data-api.md](spike-aurora-data-api.md) | Độ trễ Data API, RLS, pgvector, auto-pause | `spikes/aurora-data-api/` |
| [spike-ml-forecasting.md](spike-ml-forecasting.md) | Backtest các mô hình dự báo, Chronos-2 trên CPU, Monte Carlo, điểm gãy, LP (dữ liệu tổng hợp) | `spikes/ml-forecasting/` |
| [spike-frontend-stack.md](spike-frontend-stack.md) | Stack frontend dựng được, biểu đồ dự báo, khối từ JSON; ảnh ở [assets/frontend-spike/](assets/frontend-spike/) | `spikes/frontend-stack/` |

Tài nguyên AWS do ba spike tạo đã được xóa; người điều phối đã liệt kê lại trên tài khoản để kiểm (không còn gì mang tên `yofina-spike`).

Các điểm lệch với proposal và quyết định còn chờ rút ra từ bảy ghi chú: [../requirements/open-questions.md](../requirements/open-questions.md#rút-ra-từ-nghiên-cứu-2026-11-21).

Việc tra FAST ngày 2026-11-21 được ghi trong [../architecture/project-structure.md](../architecture/project-structure.md).
