# Yofina Foresight — chỉ mục cho AI agent

Trợ lý tài chính "Hũ nhìn trước" cho MoMo Tech Contest 2026: dự báo từng hũ chi tiêu cạn ngày nào (tính cả nợ nhỏ), tự đổi lộ trình khi hành vi lệch. Dự án đang ở giai đoạn scaffold, chưa có code tính năng. Chi tiết nằm ở `docs/`; file này chỉ trỏ đường.

Tài liệu viết tiếng Việt, thuật ngữ kỹ thuật giữ tiếng Anh.

## Thói quen làm việc

1. **Đầu phiên** đọc [HANDOFF.md](HANDOFF.md) trước: nó cho biết đang ở đâu và việc kế tiếp, đỡ phải đoán.
2. **Tra tài liệu trên internet trước khi code hoặc cấu hình.** Đọc tài liệu chính thức của bên cung cấp (AWS, AgentCore, Bedrock, Strands, CDK, Next.js, AG-UI, thư viện ML…) để làm đúng hướng dẫn hiện hành, vì các dịch vụ này đổi nhanh. Với kỹ thuật nêu trong proposal (Chronos-2, conformal prediction, PELT/CUSUM/ADWIN, ECOD, Croston/TSB, Monte Carlo, LP phân bổ, ReasoningBank, Mem0, AG-UI, Cedar policy, Automated Reasoning…) thì tìm thêm paper/bài tham khảo. Điểm bắt đầu: [docs/references/links.md](docs/references/links.md); ghi chú đáng giữ lưu vào [docs/research/](docs/research/README.md).
3. **Sau mỗi lần thêm/sửa**, thêm một entry vào [docs/ai-log/](docs/ai-log/README.md) (template ở đó), để người sau biết đã đổi gì và vì sao.
4. **Cuối phiên** cập nhật [HANDOFF.md](HANDOFF.md) (ghi đè phần trạng thái; ai-log mới là lịch sử).
5. Thao tác tạo/sửa/xóa tài nguyên AWS thật (tốn tiền, khó hoàn tác) thì hỏi chủ dự án trước; đọc/tra cứu thì cứ làm.

## Cần gì → đọc file nào

| Cần gì | Đọc |
|---|---|
| Hiểu sản phẩm, tính năng F1–F7, FR/NFR, stack, rủi ro, kế hoạch (không phải mở PDF) | [docs/proposal/proposal-summary.md](docs/proposal/proposal-summary.md) |
| Bản gốc proposal | [docs/proposal/Proposal-Yofina-Foresight.pdf](docs/proposal/Proposal-Yofina-Foresight.pdf) |
| Thư mục nào chứa gì; FAST (chỉ tham khảo, không kéo về) | [docs/architecture/project-structure.md](docs/architecture/project-structure.md) |
| Kiến trúc AWS, ba nhịp chạy, harness 6 tầng, danh mục tool, bảng dữ liệu | [docs/architecture/overview.md](docs/architecture/overview.md) |
| FR/NFR, MVP vs mở rộng | [docs/requirements/requirements.md](docs/requirements/requirements.md) |
| Bối cảnh thị trường, pain point; quy tắc nghiệp vụ (BC/BR), FR chi tiết, NFR đo được, tiêu chí nghiệm thu (AC) | [docs/ba/README.md](docs/ba/README.md) |
| Câu hỏi chưa chốt (Region, hạn nộp, Chronos-2…) | [docs/requirements/open-questions.md](docs/requirements/open-questions.md) |
| Ghi lại một quyết định kiến trúc | [docs/decisions/README.md](docs/decisions/README.md) |
| Cách dùng và best practice từng phần stack (AgentCore, Strands/AG-UI, Bedrock, hạ tầng, ML, generative UI, frontend) | [docs/research/README.md](docs/research/README.md) |
| Link nguồn theo chủ đề | [docs/references/links.md](docs/references/links.md) |
| Kế hoạch tổng 6 phase, quyết định áp dụng cho mọi phase, file plan từng phase | [docs/plan/master-plan.md](docs/plan/master-plan.md), [docs/plan/phases/](docs/plan/phases/) |
| Kế hoạch 3 tuần theo proposal, chia vai, kịch bản demo | [docs/plan/README.md](docs/plan/README.md) |
| Tài nguyên AWS đã tạo (tên, stack, phase) | [docs/aws-resources.md](docs/aws-resources.md) |
| Mục lục toàn bộ tài liệu | [docs/README.md](docs/README.md) |

## Code nằm ở đâu

| Thư mục | Chứa |
|---|---|
| `contracts/` | Hợp đồng: JSON Schema khối UI, schema tool Gateway, OpenAPI, fixtures; [README](contracts/README.md) nói quy ước (tiền là số nguyên VND, id khối, versioning) |
| `libs/yofina_core/` | Gói Python dùng chung (khối UI, tiền, `app_today`, config, xác nhận, client DB, `llm`); workspace uv ở gốc repo (`uv sync`, `uv run pytest`) |
| `frontend/` | Web app, khối UI theo `type`; `src/contracts/` là Zod sinh từ `contracts/` (không sửa tay) |
| `infra-cdk/` | AWS CDK |
| `agent/` | Agent Strands, harness L0–L5 |
| `gateway/tools/{ledger,forecast,planner,knowledge,ingest,audit}/` | Lambda tool sau AgentCore Gateway |
| `gateway/policies/` | Luật Cedar |
| `ml/`, `pipelines/{event,nightly,weekly}/` | Mô hình ML; pipeline sự kiện, đêm, tuần |
| `spikes/` | Bản thử đã chạy (không phải code sản phẩm); kết quả ở `docs/research/spike-*.md` |
| `db/`, `data/personas/`, `knowledge-base/`, `evals/`, `scripts/`, `tests/` | Schema, dữ liệu synthetic, kho tri thức RAG, đánh giá, script, test |

Mỗi thư mục có README ngắn nói nó ứng với mục/tính năng nào của proposal.

## Công cụ AWS

Máy có sẵn MCP server và skill cho AWS; chi tiết và trạng thái từng cái ở [docs/references/aws-tooling.md](docs/references/aws-tooling.md). Mỗi phiên nên tự kiểm lại cái nào đang dùng được.

| Việc | Dùng |
|---|---|
| Tra tài liệu AWS chính thức (cách ưu tiên cho thói quen số 2) | `aws-docs` MCP (`mcp__aws-docs__*`) |
| Tra và thao tác Amazon Bedrock AgentCore (Runtime, Memory, Gateway, Policy, Identity) | `agentcore` MCP (`mcp__agentcore__*`) |
| Gọi AWS API, kiểm tính năng theo Region | AWS MCP connector (`mcp__claude_ai_AWS_MCP__aws___*`), ưu tiên hơn AWS CLI qua Bash |
| CDK, Lambda/Step Functions/EventBridge, Bedrock, SQS, CloudWatch, IAM, chi phí… | Skill `aws-core:*` (gọi trước khi làm phần đó) |

## Agent skills

### Issue tracker

Issue và spec nằm ở GitHub Issues của `thphuc06/HCPUS_MoMoMentum`, thao tác bằng `gh` CLI. Xem `docs/agents/issue-tracker.md`.

### Triage labels

Dùng năm nhãn mặc định: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Xem `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` ở gốc repo (tạo khi chốt thuật ngữ đầu tiên), ADR ở `docs/decisions/` (không dùng `docs/adr/`). Xem `docs/agents/domain.md`.

### Nơi ghi tài liệu (dùng file sẵn có, không tạo file riêng cùng mục đích)

| Skill muốn ghi | Ghi vào |
|---|---|
| Handoff (`/handoff`) | [HANDOFF.md](HANDOFF.md), ghi đè phần trạng thái; không ghi ra thư mục tạm |
| ADR (`/domain-modeling`, `/grill-with-docs`, `/improve-codebase-architecture`) | [docs/decisions/](docs/decisions/README.md) theo template và bảng danh sách ở đó |
| Ghi chú tra cứu (`/research`) | [docs/research/](docs/research/README.md), thêm dòng vào bảng danh sách |
| Câu hỏi chưa chốt | [docs/requirements/open-questions.md](docs/requirements/open-questions.md) |
| Yêu cầu bị từ chối (`/triage`, thay cho `.out-of-scope/`) | Issue đóng với nhãn `wontfix`; đổi phạm vi thì sửa mục "MVP và mở rộng" ở [requirements.md](docs/requirements/requirements.md) |
| Lịch sử thay đổi | [docs/ai-log/](docs/ai-log/README.md), như thói quen số 3 |
