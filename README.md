# Yofina Foresight

Trợ lý tài chính **"Hũ nhìn trước"** cho **MoMo Tech Contest 2026** (tên tạm). Dự báo từng hũ chi tiêu cạn vào ngày nào, tính cả nợ nhỏ (Ví Trả Sau, vay, hóa đơn định kỳ), mô phỏng "nếu thì", kiểm tra trước khi quẹt, và tự đổi lộ trình khi hành vi lệch khỏi dự báo.

Nguyên tắc: LLM không tự tính số — mọi con số đến từ engine tất định hoặc mô hình dự báo qua tool; mọi thay đổi số dư cần người dùng xác nhận; mỗi gợi ý có bảng "Vì sao" và `trace_id`.

Stack: Strands Agents trên Amazon Bedrock AgentCore, Bedrock, Aurora PostgreSQL, Lambda, CDK; frontend React + Vite, shadcn/ui, Recharts, giao thức AG-UI. Code tự viết theo tài liệu chính thức; khung FAST của AWS chỉ để tham khảo.

**Trạng thái** (2026-11-21, tuần 1 trong kế hoạch 3 tuần): đã có cấu trúc dự án, ghi chú nghiên cứu, bảy bản thử đã chạy thật và thiết kế giao diện trong Figma. Chưa có code sản phẩm. Xem [HANDOFF.md](HANDOFF.md).

## Liên kết

| | |
|---|---|
| **Prototype bấm được** (6 cảnh demo, bắt đầu từ màn Đăng nhập) | [Mở prototype trên Figma](https://www.figma.com/proto/l9vWyORNRjDqiEOXqpbzYm/Yofina-Foresight-UI-demo?page-id=2%3A3&node-id=31-2715&starting-point-node-id=31%3A2715&scaling=scale-down&hide-ui=1) |
| File thiết kế Figma (Foundations, Components, Screens) | [Yofina Foresight — UI demo](https://www.figma.com/design/l9vWyORNRjDqiEOXqpbzYm) |
| Kịch bản bấm từng bước, bảng màu, danh mục component | [docs/research/figma-ui-design.md](docs/research/figma-ui-design.md) |
| Kịch bản demo 6 cảnh | [docs/plan/demo-script.md](docs/plan/demo-script.md) |
| Proposal (PDF) và bản tóm tắt | [PDF](docs/proposal/Proposal-Yofina-Foresight.pdf) · [tóm tắt](docs/proposal/proposal-summary.md) |
| Kiến trúc đã đối chiếu với kết quả chạy thử | [docs/architecture/overview.md](docs/architecture/overview.md) |
| Kết quả các bản thử (spike) và ghi chú nghiên cứu | [docs/research/README.md](docs/research/README.md) |
| Ảnh màn hình bản thử frontend | [docs/research/assets/frontend-spike/](docs/research/assets/frontend-spike/) |
| Quyết định kiến trúc (ADR) | [docs/decisions/README.md](docs/decisions/README.md) |
| Câu hỏi mở và việc chưa kiểm chứng | [docs/requirements/open-questions.md](docs/requirements/open-questions.md) |
| Kế hoạch 3 tuần | [docs/plan/README.md](docs/plan/README.md) |

Prototype là các màn hình tĩnh nối với nhau trong Figma, chưa phải app chạy thật; dữ liệu là hư cấu.

## Cây thư mục

```
.
├── CLAUDE.md            chỉ mục cho AI agent
├── HANDOFF.md           trạng thái hiện tại, việc kế tiếp
├── docs/                tài liệu (proposal, architecture, requirements, decisions,
│                        references, research, plan, ai-log) — bắt đầu ở docs/README.md
├── frontend/            web app
├── infra-cdk/           AWS CDK
├── agent/               agent Strands (harness L0–L5)
├── gateway/
│   ├── policies/        luật Cedar
│   └── tools/           Lambda tool: ledger, forecast, planner, knowledge, ingest, audit
├── ml/                  mô hình dự báo, change point, outlier, tối ưu
├── pipelines/           event/, nightly/, weekly/
├── db/                  schema/, migrations/
├── data/personas/       dữ liệu tổng hợp 3 persona
├── knowledge-base/      kho tri thức RAG
├── evals/               bộ câu chuẩn, evaluator
├── spikes/              bản thử đã chạy (không phải code sản phẩm)
├── scripts/
└── tests/               unit/, integration/
```

Giải thích từng thư mục: [docs/architecture/project-structure.md](docs/architecture/project-structure.md).

## Tài liệu

- Mục lục: [docs/README.md](docs/README.md)
- Tóm tắt proposal: [docs/proposal/proposal-summary.md](docs/proposal/proposal-summary.md) (PDF gốc cùng thư mục)
- Kiến trúc: [docs/architecture/overview.md](docs/architecture/overview.md)
- Kế hoạch 3 tuần: [docs/plan/README.md](docs/plan/README.md)
- Câu hỏi mở: [docs/requirements/open-questions.md](docs/requirements/open-questions.md)
