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
