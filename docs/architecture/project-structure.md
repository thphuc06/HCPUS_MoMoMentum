# Cấu trúc thư mục dự án

Scaffold ngày 2026-11-21. Chỉ có thư mục và README mô tả; chưa có code. Khung FAST của AWS **chỉ dùng để tham khảo**, không kéo về (xem mục cuối).

## Cây thư mục

```
c:\moMo
├── CLAUDE.md                  chỉ mục cho AI agent
├── HANDOFF.md                 ảnh chụp trạng thái hiện tại (ghi đè cuối mỗi phiên)
├── README.md
├── .gitignore
├── docs/
│   ├── README.md              chỉ mục tài liệu
│   ├── proposal/              PDF gốc + proposal-summary.md
│   ├── architecture/          project-structure.md (file này), overview.md
│   ├── requirements/          requirements.md, open-questions.md
│   ├── decisions/             ADR (README + template)
│   ├── references/            links.md, aws-tooling.md
│   ├── research/              ghi chú tra cứu internet
│   ├── plan/                  kế hoạch 3 tuần, chia vai, kịch bản demo
│   └── ai-log/                nhật ký thay đổi của AI (YYYY-MM.md)
├── frontend/                  web app (F1–F7 giao diện, khối UI theo type)
├── infra-cdk/                 AWS CDK (hạ tầng)
├── agent/                     agent Strands: harness L0–L5
├── gateway/
│   ├── policies/              luật Cedar cho AgentCore Policy
│   └── tools/                 Lambda tool sau AgentCore Gateway (MCP)
│       ├── ledger/            ledger.*
│       ├── forecast/          forecast.*
│       ├── planner/           planner.*
│       ├── knowledge/         knowledge.*
│       ├── ingest/            ingest.*
│       └── audit/             audit.*
├── ml/                        mô hình dự báo, change point, outlier, tối ưu
├── pipelines/
│   ├── event/                 phân hũ tự động, cập nhật tức thời
│   ├── nightly/               batch 02:00 (F1, F4, F7)
│   └── weekly/                backtest, hiệu chỉnh, đánh giá, đồng bộ KB
├── db/
│   ├── schema/                schema Aurora PostgreSQL
│   └── migrations/
├── data/
│   └── personas/              bộ sinh dữ liệu tổng hợp 3 persona
├── knowledge-base/            biểu phí, kiến thức tài chính, luật suitability (RAG)
├── evals/                     bộ câu chuẩn, evaluator tự viết
├── spikes/                    bản thử đã chạy 2026-11-21 (không phải code sản phẩm); kết quả ở docs/research/spike-*.md
├── scripts/                   script triển khai/tiện ích
└── tests/
    ├── unit/
    └── integration/
```

## FAST chỉ để tham khảo

**Quyết định của chủ dự án (2026-11-21)**: không kéo hay copy FAST vào repo, và không dùng frontend của nó. Code tự viết theo tài liệu chính thức của từng dịch vụ/thư viện (thói quen số 2 trong [CLAUDE.md](../../CLAUDE.md)); FAST là một ví dụ để xem cách AWS nối Runtime, Gateway, Identity, Memory và Cognito bằng CDK khi cần. Điều này khác với proposal §8 và §14 ("khởi đầu từ khung FAST").

Hệ quả cho tên thư mục: `agent/` thay cho `patterns/yofina-agent/` (tên `patterns/` chỉ có nghĩa khi dùng FAST). `infra-cdk/`, `gateway/tools/`, `gateway/policies/` giữ nguyên vì tự chúng đã rõ nghĩa.

Phần dưới là ghi chú về layout của FAST, giữ lại để biết tìm gì ở đâu khi tham khảo.

**Đã kiểm chứng (2026-11-21)**: đọc trang repo chính thức [awslabs/fullstack-solution-template-for-agentcore](https://github.com/awslabs/fullstack-solution-template-for-agentcore) (README và danh sách thư mục `main`, `gateway/`, `patterns/`). Layout của FAST ở root:

- Thư mục: `frontend/`, `infra-cdk/`, `infra-terraform/`, `patterns/`, `gateway/`, `tools/`, `scripts/`, `test-scripts/`, `tests/` (có `unit/`, `integration/`), `docs/`, `docker/`, `vibe-context/`, `.mkdocs/`, `.github/` (và `.amazonq`, `.kiro`).
- File root: `README.md`, `pyproject.toml`, `Makefile`, `ruff.toml`, `requirements-dev.txt`, `.gitignore`, `CHANGELOG.md`, `VERSION`, `LICENSE` (Apache-2.0)…
- `patterns/` chứa: `agui-strands-agent`, `agui-langgraph-agent`, `strands-single-agent`, `langgraph-single-agent`, `claude-agent-sdk-single-agent`, `claude-agent-sdk-multi-agent`, `utils`.
- `gateway/` chứa `policies/` (ví dụ `policy.cedar`) và `tools/` (ví dụ `sample_tool/`); `infra-cdk/` chứa `bin/`, `lib/`, `lambdas/` và `config.yaml`; `frontend/` là React + TypeScript + Vite (Tailwind, shadcn/ui).
- FAST tự mô tả là **proof-of-value**, không phải giải pháp production.

**Chưa kiểm chứng**: nội dung bên trong các pattern AG-UI (chưa mở), cách dựng một tool trong `gateway/tools/` (README FAST trỏ sang `docs/GATEWAY.md`, chưa đọc), và bài AWS ML Blog về AG-UI/FAST (nội dung tải về bị cắt, chưa đọc được phần nói về FAST). Layout FAST có thể đã đổi so với lúc tra cứu.

### Tham khảo phần nào của FAST cho phần nào của repo

| Phần của repo này | Xem trong FAST |
|---|---|
| `infra-cdk/` | `infra-cdk/` (cách dựng Runtime, Gateway, Identity, Memory, Cognito bằng CDK) |
| `agent/` | `patterns/agui-strands-agent/` (Strands + AG-UI) |
| `gateway/tools/<nhóm>/` | `gateway/tools/sample_tool/` (Lambda làm target của Gateway) |
| `gateway/policies/` | `gateway/policies/` (ví dụ luật Cedar) |
| `frontend/` | Không copy frontend của FAST (React + Vite). Stack chọn theo tiêu chí "đẹp nhất", chưa chốt — xem [open-questions](../requirements/open-questions.md) |

## Quy ước

- Mỗi thư mục code cấp cao có README ngắn: chứa gì, ứng với mục/tính năng nào của proposal.
- Thư mục rỗng giữ lại bằng `.gitkeep` nếu cần (hiện README đã làm việc đó ở thư mục cấp cao).
- Thêm thư mục cấp cao mới → cập nhật cây trên, [README.md](../../README.md) và [CLAUDE.md](../../CLAUDE.md).
