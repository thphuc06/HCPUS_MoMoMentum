# Kế hoạch

> **Kế hoạch hiện hành (2026-11-21)**: [master-plan.md](master-plan.md) chia dự án thành 6 phase, mỗi phase một file trong [phases/](phases/). Bảng 3 tuần dưới đây là bản theo proposal §15, giữ để tra ngược; thứ tự việc lấy theo master-plan.

## Kế hoạch 3 tuần (theo proposal)

Nguồn: proposal §15. **Giả định đội nộp bài trước chung kết 11/12/2026; hạn nộp chính xác cần xác nhận** ([open-questions](../requirements/open-questions.md)). Hôm nay (2026-11-21) là ngày đầu tuần 1.

| Tuần | Ngày | Mục tiêu | Việc chính (theo proposal) |
|---|---|---|---|
| 1 | 21–27/11 | Nền chạy được từ đầu đến cuối | Dựng nền hạ tầng bằng CDK (proposal ghi "triển khai khung FAST"; đã chốt chỉ tham khảo FAST); schema Aurora; bộ sinh dữ liệu 3 persona; tool nhóm `ledger` (tên qua Gateway: `ledger___<tên tool>`, proposal viết `ledger.*`); router và đường nhanh; màn hình khai báo; màn hình hũ; kiểm tra tính năng theo Region |
| 2 | 28/11–4/12 | Ba tính năng lõi | F1 dự báo và Monte Carlo; F2 what-if có streaming; F3 kiểm tra trước khi quẹt; verifier và luật suitability; memory; bảng "Vì sao" |
| 3 | 5–10/12 | Hoàn thiện và đóng gói | F4, F5, F6 (ảnh chụp); bộ 50 câu đánh giá; sửa lỗi; quay video; slide 10 trang; README |

## Tiến độ tuần 1 (cập nhật 2026-11-21)

Mốc ngày không đổi. Hôm nay đã làm xong các việc **kiểm tra** (bảy ghi chú đọc tài liệu và bảy spike chạy thật, tài nguyên thử đã xóa; xem [research/README.md](../research/README.md)); chưa có code sản phẩm.

**Đã xong hôm nay (kiểm tra, không phải sản phẩm)**

- Kiểm tính năng AgentCore/Bedrock theo Region: thành phần AgentCore có ở `ap-southeast-1` (**[đọc tài liệu]**, [agentcore.md](../research/agentcore.md)); model nào gọi được ngay và quota ([spike-bedrock-models.md](../research/spike-bedrock-models.md)). **Region triển khai vẫn chưa chốt.**
- Trình duyệt gọi thẳng Runtime qua SSE, deploy bằng zip không Docker, cold start, phiên V1/V2 ([spike-agentcore-runtime-cors.md](../research/spike-agentcore-runtime-cors.md)).
- Danh tính xuống tool bằng interceptor + Cedar, token xác nhận do server cấp, tên tool `___`, độ trễ Gateway ([spike-agentcore-gateway-identity.md](../research/spike-agentcore-gateway-identity.md)).
- Aurora qua Data API: độ trễ, RLS, pgvector, auto-pause ([spike-aurora-data-api.md](../research/spike-aurora-data-api.md)).
- Strands + AG-UI chạy local: khối UI, structured output, interrupt/resume ([spike-strands-agui-local.md](../research/spike-strands-agui-local.md)).
- Backtest dự báo, Monte Carlo, PELT, LP trên dữ liệu tổng hợp ([spike-ml-forecasting.md](../research/spike-ml-forecasting.md)).
- Stack frontend dựng thử và đã chốt ([ADR-0001](../decisions/0001-frontend-stack.md), [spike-frontend-stack.md](../research/spike-frontend-stack.md)).
- Tài liệu kiến trúc, yêu cầu và ghi chú AgentCore đã đồng bộ với các kết quả này ([overview.md](../architecture/overview.md)).

**Còn lại trong tuần 1**

- Chủ dự án chốt: cơ chế xác nhận trước khi ghi, bộ model, Chronos-2 vào MVP hay không (đang là đề xuất; [open-questions](../requirements/open-questions.md)), Region triển khai, danh tính deploy không dùng root.
- Dựng nền hạ tầng bằng CDK (Cognito, Runtime V2, Gateway + interceptor + Cedar, Aurora min 0,5 ACU, Lambda tool, HTTP API).
- Schema Aurora kèm role `yofina_app`, RLS, hàm đọc plpgsql; bộ sinh dữ liệu 3 persona.
- Tool `ledger` đọc và ghi, router và đường nhanh; màn hình khai báo và hũ; REST API (đề xuất) cho màn hình không cần LLM.
- **Kiểm tra còn dở**: nối frontend thật với Runtime thật (gồm interrupt/resume qua Runtime), CORS từ domain thật và Safari/iPhone, Amplify Hosting, hành vi Strands `MCPClient` khi Cedar từ chối, Sonnet 4.6 làm planner nhiều bước, ảnh chụp thật, mô hình dự báo trên dữ liệu không do cùng bộ sinh tạo ra (danh sách đầy đủ: [overview.md](../architecture/overview.md#chưa-kiểm-chứng)).

## Chia vai

Proposal đề xuất 3 người: (1) agent và harness; (2) dữ liệu, ML và batch; (3) frontend và demo. Nếu đội 2 người: gộp vai frontend vào người lo agent và cắt F6. **Chưa có tên người cụ thể** — đội 2 hay 3 người vẫn là câu hỏi mở.

| Vai | Thư mục chính |
|---|---|
| Agent và harness | `agent/`, `gateway/` |
| Dữ liệu, ML, batch | `db/`, `data/`, `ml/`, `pipelines/`, `knowledge-base/` |
| Frontend và demo | `frontend/`, [demo-script.md](demo-script.md) |
| Chung | `infra-cdk/`, `evals/`, `tests/` (cần thống nhất) |

## Thứ tự ưu tiên khi thiếu thời gian (§13)

Làm lát dọc F1 → F2 → F3 trước. Sao kê PDF, bản tin, bảng vận hành là phần mở rộng. Chronos-2 "nếu kịp, không thì mở rộng" (số đo đề xuất để ngoài MVP, chưa chốt).

Việc kế tiếp cụ thể xem [../../HANDOFF.md](../../HANDOFF.md). Kịch bản demo: [demo-script.md](demo-script.md).
