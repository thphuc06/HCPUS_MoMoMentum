# Yofina Foresight

Trợ lý tài chính **"Hũ nhìn trước"** cho **MoMo Tech Contest 2026** (tên tạm). Dự báo từng hũ chi tiêu cạn vào ngày nào, tính cả nợ nhỏ (Ví Trả Sau, vay, hóa đơn định kỳ), mô phỏng "nếu thì", kiểm tra trước khi quẹt, và tự đổi lộ trình khi hành vi lệch khỏi dự báo.

Nguyên tắc: LLM không tự tính số — mọi con số đến từ engine tất định hoặc mô hình dự báo qua tool; mọi thay đổi số dư cần người dùng xác nhận; mỗi gợi ý có bảng "Vì sao" và `trace_id`.

Stack: Strands Agents trên Amazon Bedrock AgentCore, Bedrock, Aurora PostgreSQL, Lambda, CDK; frontend web (AG-UI). Code tự viết theo tài liệu chính thức; khung FAST của AWS chỉ để tham khảo.

**Trạng thái**: giai đoạn scaffold (2026-11-21, tuần 1 trong kế hoạch 3 tuần). Chưa có code tính năng. Xem [HANDOFF.md](HANDOFF.md).

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
