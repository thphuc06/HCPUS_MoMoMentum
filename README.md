# Yofina Foresight

Trợ lý tài chính **"Hũ nhìn trước"** cho **MoMo Tech Contest 2026**, chủ đề **Trợ lý AI · Trợ lý tài chính**. Người dùng là người trẻ 18–30 tuổi nhận lương theo tháng và có dùng mua trước trả sau. Yofina dự báo từng hũ chi tiêu sẽ cạn vào ngày nào (tính cả Ví Trả Sau, khoản vay, hóa đơn định kỳ), cho hỏi "nếu thì" bằng chat, kiểm tra trước khi chi, và tự đề xuất lộ trình mới khi chi tiêu lệch khỏi thói quen.

> **Bản nháp bộ nộp (issue #36).** Số đo ở mục "Số đo chính" là bản trước lượt eval RC; **cập nhật sau lượt eval RC 2/12/2026**.

## Dùng thử

| | |
|---|---|
| App (web, ưu tiên điện thoại) | https://main.dcrwn4u7vqklo.amplifyapp.com |
| Tài khoản dùng thử | `giamkhao1`, `giamkhao2`, `giamkhao3` (cùng persona Minh). Mật khẩu gửi trong form nộp bài |
| Hướng dẫn 1 trang | [docs/submission/huong-dan-a4.md](docs/submission/huong-dan-a4.md) |
| Tệp mẫu | `/samples/minh_sao_ke_2_tuan.csv` (cảnh 4), `/samples/minh_bien_lai_1.png` (cảnh 5) trên cùng miền app |
| Kịch bản 6 cảnh | [docs/plan/demo-script.md](docs/plan/demo-script.md) |

Ví là **ví mô phỏng**: dữ liệu là persona tổng hợp, sản phẩm trả sau là "Trả sau (mô phỏng)" lấy biểu phí công khai làm ví dụ. Ngày trong app là ngày mô phỏng (neo 21/11/2026 sau khi bấm "Đặt lại dữ liệu"). Không có giao dịch thật nào.

## Sản phẩm làm gì

| # | Tính năng | Người dùng thấy | Phần AI |
|---|---|---|---|
| F1 | Dự báo theo hũ | Dòng thời gian 30 ngày, ngày cạn dự kiến, khả năng hụt trước kỳ lương | Mô hình chi tiêu theo lịch lương (hurdle) và Monte Carlo 10.000 đường mỗi đêm |
| F2 | Hỏi "nếu thì" | Gõ "nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau", thấy đường số dư trước và sau, tổng chi phí gồm phí, 2–3 phương án | LLM dựng đặc tả kịch bản, engine tính, LLM giải thích; bộ kiểm số và luật suitability chặn câu sai |
| F3 | Kiểm tra trước khi chi | Đủ / sát / hụt cho một khoản chi | Engine tất định quyết định, model nhỏ viết hai câu |
| F4 | Điểm chống chịu | Điểm 0–100, 4 thành phần, nút cú sốc ("Mất việc 2 tháng") | Chỉ số tính từ hành vi, stress test trên dự báo |
| F5 | Lộ trình thích ứng | Lộ trình theo giai đoạn, duyệt từng bước, "So với bản cũ" khi có bản mới | PELT phát hiện chi tiêu đổi mức, planner soạn nháp, LP chia tiền, luật suitability kiểm |
| F6 | Nạp dữ liệu ngoài ví | Tải ảnh chứng từ hoặc sao kê CSV, duyệt dòng; thông tin cá nhân bị che | Model đa phương thức đọc ảnh; che PII trước mọi lời gọi model sau đó; gợi ý hũ cho từng dòng |
| F7 | Hồ sơ hành vi, bản tin | Nhận xét thói quen kèm bằng chứng, tối đa một việc nên làm mỗi ngày; bộ nhớ sở thích xem và xóa được | Batch đêm rút mẫu hành vi; AgentCore Memory |

Nguyên tắc: **LLM không tự tính số**. Mọi con số đến từ engine tất định hoặc mô hình dự báo qua tool. Mọi thay đổi số dư cần người dùng bấm xác nhận (token dùng một lần do server cấp, [ADR-0002](docs/decisions/0002-xac-nhan-truoc-khi-ghi.md)). Mỗi câu trả lời có bảng "Vì sao" (dữ liệu đã dùng, luật đã kiểm, trace từng bước).

## Công nghệ

- **Agent**: Strands Agents (Python) trên Amazon Bedrock AgentCore Runtime, giao thức AG-UI qua SSE. Mã điều khiển thứ tự lượt; LLM chỉ hiểu ý định, dựng kịch bản, giải thích ([agent/README.md](agent/README.md)).
- **Tool**: Lambda Python sau AgentCore Gateway (MCP), luật Cedar cho từng tool, interceptor ghi đè `user_id` từ JWT.
- **Model (Amazon Bedrock)**: xem mục "Công cụ AI đã dùng". Bedrock Guardrails lọc đầu vào và đầu ra.
- **Dữ liệu**: Aurora PostgreSQL Serverless v2 (Data API, Row Level Security, pgvector), DynamoDB, S3.
- **Nền và sự kiện**: EventBridge, SQS, Step Functions (batch đêm 02:00), API Gateway HTTP API, Cognito.
- **ML**: numpy, scipy, ruptures trong Lambda zip ([ml/README.md](ml/README.md)).
- **Frontend**: React 19 + Vite, Tailwind 4, shadcn/ui, Recharts, `@ag-ui/client`, Zod; host trên Amplify Hosting ([ADR-0001](docs/decisions/0001-frontend-stack.md)).
- **Hạ tầng**: AWS CDK (TypeScript), bảy stack ở `ap-southeast-1`; CI GitHub Actions chạy offline (pytest, vitest, CDK, hợp đồng, gitleaks).

Kiến trúc: [docs/architecture/overview.md](docs/architecture/overview.md). Chỗ khác proposal và lý do: [ADR-0004](docs/decisions/0004-lech-so-voi-proposal.md).

## Chạy cục bộ

Cần Python 3.13 với [uv](https://docs.astral.sh/uv/), Node 22.22 trở lên. Trên Windows dùng `npm.cmd` và đặt `$env:PYTHONIOENCODING='utf-8'`.

```bash
uv sync                                                   # workspace Python (libs/*, agent, ml)
uv run pytest tests/unit libs/yofina_core/tests -q        # unit, không gọi AWS
cd frontend && npm ci && npm run dev:mock                 # giao diện với máy chủ giả, không cần backend
cd frontend && npm test                                   # vitest
npm ci --prefix infra-cdk && npm test --prefix infra-cdk  # test CDK
```

Chạy với backend thật cần một tài khoản AWS đã deploy (mục dưới), rồi `uv run scripts/print_env.py frontend --write` và `npm run dev` trong `frontend/`. Danh sách script: [scripts/README.md](scripts/README.md).

## Deploy lại

Thứ tự stack, cấu hình, đóng gói Lambda và bẫy đã gặp: [infra-cdk/README.md](infra-cdk/README.md) (các mục "Synth, diff, deploy", "Migrator", "Tài khoản demo và mật khẩu", "Frontend và biến môi trường", "Đóng gói Lambda / Runtime không Docker"). Tài khoản AWS mới cần bootstrap CDK ở `ap-southeast-1` một lần. Thứ tự tóm tắt:

```bash
npm ci --prefix infra-cdk
uv run scripts/cdk.py deploy YofinaFoundation --require-approval never
uv run scripts/cdk.py deploy YofinaData YofinaIdentity YofinaFrontend --concurrency 3 --require-approval never
uv run scripts/migrate.py && uv run scripts/migrate.py --seed       # migration Aurora, rồi bảng tra
# đóng zip Lambda ledger, forecast, classify, roadmap, ingest (lệnh ở infra-cdk/README.md và scripts/README.md)
uv run scripts/cdk.py deploy YofinaTools --require-approval never
uv run scripts/cdk.py deploy YofinaIngest --require-approval never
uv run scripts/agent_deploy.py                                       # zip agent, Gateway, Cedar, Runtime; chờ READY
uv run scripts/create_demo_users.py && uv run scripts/seed_demo.py   # tài khoản demo, nạp persona
uv run scripts/print_env.py frontend --write
npm run build --prefix frontend && uv run scripts/deploy_frontend.py frontend/dist
```

Luôn `uv run scripts/cdk.py diff <Stack>` trước khi deploy. Đóng `.zip` mã nguồn cho bộ nộp: `uv run python scripts/make_submission_zip.py --out ..\yofina-source.zip` (quét bí mật trước, chỉ nén tệp đã commit).

## Số đo chính (trước RC, cập nhật sau lượt eval RC 2/12)

Mọi số ML là trên **dữ liệu tổng hợp** do đội viết bộ sinh. Bộ chấm eval đã được sửa sau các số dưới đây (không còn tự coi số do model viết là có căn cứ, issue #5, #6), nên số RC có thể thấp hơn.

| Hạng mục | Số | Nguồn |
|---|---|---|
| Eval trên Runtime v25 (24/11) | Golden phase 3 31/31, phase 4 14/14; đối kháng 16/16, 12/12, 14/14; router diễn đạt lại 18/18; OCR ảnh thật 9/11 | [HANDOFF.md](HANDOFF.md) "Số đo mới nhất" |
| Dự báo so với seasonal naive | Pinball 0,62 và 0,60 lần (hai họ bộ sinh, seed giữ ra ngoài) | [backtest-phase-2.md](docs/research/backtest-phase-2.md) |
| Độ phủ dải 80% số dư 30 ngày | 0,80 ở hũ dày và hũ thưa (lịch sử đủ); hũ dày ở 120 ngày lịch sử sau CQR 0,798, mỗi đuôi khoảng 10%; % chỉ hiện từ 47 ngày (hũ dày) và 120 ngày (hũ thưa) | [backtest-final.md](docs/research/backtest-final.md) |
| Phân hũ tự động | Đúng 92% trên dòng tự gán; 17,4% phải hỏi (mục tiêu dưới 10%) | [ba/13](docs/ba/13-tien-do-technical.md) |
| Độ trễ what-if (23/11, 10 lượt) | Khối số liệu đầu p50 6,9 s / p95 18,2 s; trọn câu p50 16,7 s / p95 28,2 s (mục tiêu proposal 8 s: chưa đạt) | [phase 3](docs/plan/phases/phase-3-what-if-va-kiem-tra.md) tiêu chí 9 |
| Kiểm tra trước khi chi | REST p95 282 ms; qua chat p50 6,3 s | như trên |
| Xác nhận trước khi ghi | 13 ca tấn công token (bịa, đổi tham số, dùng lại, của người khác, hết hạn) đều bị chặn | [ADR-0002](docs/decisions/0002-xac-nhan-truoc-khi-ghi.md) |
| Chi phí | Một lượt what-if khoảng 0,06 USD (khoảng 1.600 ₫); một lượt eval đầy đủ 2,2–2,5 USD | [kiểm toán độ trễ, chi phí](docs/research/2026-11-25-audit-agent-aws-latency.md), HANDOFF |
| Unit test | 4.079 passed, 4 skipped (25/11, nhánh `p6/docs`; 2 test Zod cần `npm install` ở gốc repo, 2 test cần Pillow) | `uv run pytest tests/unit libs/yofina_core/tests` |

## Giới hạn đã biết

Danh sách từ kiểm toán 25/11 ([tổng hợp](docs/research/2026-11-25-audit-tong-hop.md), mục "Ghi là giới hạn đã biết") cộng các giới hạn của bản demo:

- Dữ liệu là tổng hợp; chưa có dữ liệu thật để kiểm mô hình. Ví và sản phẩm trả sau là mô phỏng.
- What-if chậm hơn mục tiêu 8 giây của proposal (số ở bảng trên). Quota Claude của tài khoản là 10 request/phút mỗi model, nên nhiều người dùng cùng lúc có thể bị chờ hoặc chuyển sang model dự phòng.
- Lần gọi đầu sau khi Aurora ngủ chậm 15–20 giây (khi cấu hình tối thiểu 0 ACU).
- Dữ liệu có thể được xử lý ngoài Singapore: các model gọi qua inference profile `global.`.
- Dải dự báo của hũ thưa vẫn lệch về đuôi dưới ở lịch sử ngắn; CQR chỉ áp cho hũ dày. Persona `lan` chỉ có 47 ngày lịch sử nên hũ thưa không hiện %.
- Phương án của what-if có thể mất nút hành động mà không báo khi bước dựng xác nhận lỗi. Verifier có tối đa 2 vòng sửa nhưng trần 4 lượt gọi model mỗi lượt chỉ cho 1 vòng.
- Chưa có dòng phạt trễ hạn Trả sau (chưa có nguồn công khai), nên "phạt nếu trễ" không hiện.
- Lộ trình đã lưu không tự cập nhật số khi dự báo đổi nhẹ; bước lộ trình chưa dùng bộ nhớ; "Kiểm tra trước khi chi" chưa có phần lập luận.
- Nạp lại cùng chứng từ ngoại tệ bằng một ảnh khác không bị đánh dấu trùng.
- Lịch sử chat gửi từ trình duyệt không đi qua Guardrail; judge LLM của ca bộ nhớ chưa đối chiếu với nhãn người.
- Trace chưa ghi model và token của từng bước; Lambda sinh lại lộ trình gần như không log khi chạy thành công.
- Dải "sát" của kiểm tra trước khi chi gần như không xảy ra (hai ngưỡng bằng 0, chờ chốt nghiệp vụ C-02).
- Chưa làm: cảnh báo khoản chuyển lệch thói quen (FR14), sao kê PDF, đánh giá online bằng AgentCore Evaluations. Đã cắt có lý do: RAG, Chronos-2, WAF, batch tuần ([ADR-0004](docs/decisions/0004-lech-so-voi-proposal.md)).

## Tài sản có sẵn

Khai theo thể lệ (Điều 12.5, 28.1). Phần không liệt kê ở đây được làm trong thời gian cuộc thi; commit đầu tiên của repo lúc 10:15 ngày 21/11/2026.

| Tài sản | Có từ trước | Dùng thế nào |
|---|---|---|
| Proposal Swinburne (đề xuất có trước cuộc thi) | Có | Proposal Yofina dùng lại khoảng một nửa nền kỹ thuật của nó ở mức thiết kế: pipeline phân loại hũ 3 bước, lộ trình thích ứng, suitability và Cedar, audit trail với `trace_id`, số chỉ lấy từ SQL, cổng khởi đầu lạnh. Bảng giữ/đổi/bỏ ở [proposal-summary §16](docs/proposal/proposal-summary.md#16-kế-thừa-từ-swinburne-và-câu-hỏi-mở-16) |
| Proposal Yofina Foresight ([PDF](docs/proposal/Proposal-Yofina-Foresight.pdf), bản nháp 20/11/2026) | Viết trước commit đầu tiên | Spec của sản phẩm; tóm tắt ở [proposal-summary.md](docs/proposal/proposal-summary.md) |
| Khung FAST (Fullstack AgentCore Solution Template), mẫu công khai của AWS | Có | Chỉ đọc để tham khảo, không chép mã ([project-structure.md](docs/architecture/project-structure.md)) |

## Thư viện mã nguồn mở

Phiên bản đọc từ `uv.lock`, `frontend/package.json`, `infra-cdk/package.json` ngày 25/11/2026.

| Phần | Thư viện chính |
|---|---|
| Agent | `strands-agents` 1.65.0, `ag-ui-protocol` 1.0.0, `mcp` 2.3.0, `fastapi` 0.165.0, `uvicorn` 0.54.0, `boto3` 1.44.9 |
| Lõi dùng chung | `pydantic` 2.14.4, `tzdata` |
| ML, dự báo | `numpy` 2.5.5, `scipy` 1.18.1, `ruptures` 1.1.10 |
| Lambda | `pyyaml` 6.0.4, `boto3`/`botocore` 1.44.9 (ghim trong zip ledger) |
| Test, công cụ Python | `pytest` 9.2.0, `ruff` 0.17.6, `jsonschema` 4.26.0, `openapi-spec-validator` 0.9.0, `httpx` 0.28.1, `pycognito` 2024.5.1, `awscrt` |
| Frontend | `react` 19.3.1, `react-dom`, `react-router` 8.5.2, `@ag-ui/client` 1.0.5, `zod` 4.6.7, `recharts` 3.11.0, `tailwindcss` 4.3.5, `shadcn` 4.23.0, `@base-ui/react` 1.9.0, `lucide-react`, `amazon-cognito-identity-js` 6.3.22, `@fontsource-variable/plus-jakarta-sans` |
| Frontend (dev) | `vite` 8.3.8, `typescript` 7.0.2, `vitest` 5.1.1, `@testing-library/react`, `jsdom`, `oxlint` |
| Hạ tầng | `aws-cdk-lib` 2.278.0, `constructs` 10.8.1, `aws-cdk` 2.1149.0, `typescript` 5.9.3, `tsx` |
| Chỉ dùng để so sánh trên máy dev (không deploy) | `statsforecast` (backtest), `pgserver` và `psycopg` (test SQL cục bộ), `pillow` (sinh ảnh mẫu) |

Danh sách đầy đủ kèm phụ thuộc gián tiếp: `uv.lock`, `frontend/package-lock.json`, `infra-cdk/package-lock.json`.

## Công cụ AI đã dùng

**Trong sản phẩm** (Amazon Bedrock, `ap-southeast-1`; cấu hình ở `libs/yofina_core/src/yofina_core/llm_defaults.json`, `infra-cdk/lib/memory.ts`):

| Vai | Model chính → dự phòng | Việc |
|---|---|---|
| `planner` | Claude Sonnet 4.6 → Kimi K3 | Dựng kịch bản what-if, Analyst, soạn nháp lộ trình |
| `small` | Amazon Nova 2 Lite → Claude Haiku 4.5 | Router ý định, viết câu trả lời, câu giải thích ngắn |
| `ingest` | Claude Sonnet 4.6 → Kimi K3 | Đọc ảnh chứng từ |
| `ingest_columns` | Amazon Nova 2 Lite → Claude Haiku 4.5 | Ánh xạ cột CSV lạ, gợi ý hũ cho dòng nạp |
| `embedding` | Cohere Embed Multilingual v3 | Phân loại giao dịch bằng láng giềng gần (pgvector) |
| Bộ nhớ (AgentCore Memory) | Claude Haiku 4.5 | Trích xuất và hợp nhất sở thích, sự thật người dùng tự kể |
| An toàn | Amazon Bedrock Guardrails | Lọc chủ đề cấm và prompt injection ở đầu vào, đầu ra |

**Khi làm sản phẩm**: Claude Code (Anthropic; model Claude Opus 5.5, Claude Sonnet 5.5, Claude Fable 5.2) điều phối, viết mã, tài liệu và review; Kiro CLI (AWS; model Claude Opus 5.5) chạy các worker song song theo issue; Codex (OpenAI, `gpt-6.2-sol`) viết mã và test cho luồng agent và frontend của phase 4 (ngày 23/11); Figma MCP cho thiết kế giao diện. Mỗi thay đổi do AI làm có một mục trong [docs/ai-log/](docs/ai-log/README.md) (ai làm, đổi gì, vì sao, đã kiểm gì).

## Nguồn dữ liệu

Khai theo thể lệ Điều 12.4.

| Dữ liệu | Nguồn, phạm vi, căn cứ |
|---|---|
| Persona và sổ cái demo (Minh, Lan, Khoa, Vy) | Bộ sinh dữ liệu tổng hợp tự viết (`data/personas/`), tất định theo seed; mọi tên, số tài khoản, số điện thoại là hư cấu |
| Ảnh và CSV mẫu cho cảnh 4, 5 | Dựng bằng mã (`data/personas/samples/`), dữ liệu hư cấu, có ghi chú "dữ liệu hư cấu" trên ảnh |
| Bộ thử OCR | 33 tệp tổng hợp tự dựng (trong repo) và **25 ảnh tải từ web công khai** (ảnh minh họa trong bài hướng dẫn công khai trên mytour.vn; 24 ảnh trên CDN `gcs.tripi.vn`, 1 ảnh trên `cdn11.dienmaycholon.vn`). Ảnh web chỉ lưu trên máy để đánh giá nội bộ, không commit, không nằm trong `.zip`; bản quyền thuộc trang nguồn. Danh sách URL và nhãn: `evals/ingest/manifest.json` |
| Biểu phí trả sau | Phí dịch vụ 33.000 ₫ mỗi tháng có giao dịch, từ trang công khai https://www.momo.vn/vi-tra-sau (ghi nhận 31/03/2026), dùng làm ví dụ cho sản phẩm mô phỏng (`db/seed/fee_schedules.sql`) |
| Tỷ giá ngoại tệ | Tỷ giá bán công bố của Vietcombank theo ngày, endpoint JSON công khai mà trang "Tỷ giá" của ngân hàng dùng (`libs/yofina_core/src/yofina_core/fx.py`); dùng để quy đổi chứng từ ngoại tệ sang VND, người dùng duyệt lại |
| Số liệu thị trường trong proposal và slide | Nguồn công khai ghi ở [docs/references/links.md](docs/references/links.md) và [proposal-summary §2](docs/proposal/proposal-summary.md#2-vấn-đề-và-số-liệu-2) |

## Cây thư mục

```
.
├── agent/               agent Strands (router, what-if, lộ trình, writer), chạy trên AgentCore Runtime
├── gateway/
│   ├── tools/           Lambda tool: ledger, forecast, planner, knowledge, ingest, audit
│   ├── policies/        luật Cedar, một file mỗi tool
│   └── interceptor/     ghi đè user_id từ JWT
├── libs/yofina_core/    gói Python dùng chung (khối UI, tiền, đồng hồ mô phỏng, xác nhận, LLM, PII)
├── ml/                  dự báo, Monte Carlo, hiệu chỉnh, phát hiện đổi hành vi, LP
├── pipelines/           forecast (đêm và sự kiện), classify, ingest, roadmap; weekly đã cắt
├── frontend/            web app React + Vite
├── infra-cdk/           AWS CDK, bảy stack
├── contracts/           JSON Schema khối UI, schema tool, OpenAPI, fixture
├── db/                  migration và seed Aurora
├── data/personas/       bộ sinh persona tổng hợp, tệp mẫu
├── evals/               bộ golden, đối kháng, OCR, phân loại; bộ chấm
├── scripts/             deploy, seed, đo, đóng gói
├── tests/               unit/, integration/, local_pg/
├── spikes/              bản thử ngày 21/11 (không phải mã sản phẩm)
├── knowledge-base/      chỉ còn README (RAG đã cắt)
└── docs/                tài liệu, bắt đầu ở docs/README.md
```

## Tài liệu

| | |
|---|---|
| Mục lục tài liệu | [docs/README.md](docs/README.md) |
| Proposal (PDF) và tóm tắt | [PDF](docs/proposal/Proposal-Yofina-Foresight.pdf) · [tóm tắt](docs/proposal/proposal-summary.md) |
| Kiến trúc | [docs/architecture/overview.md](docs/architecture/overview.md) |
| Quyết định kiến trúc (ADR) | [docs/decisions/README.md](docs/decisions/README.md) |
| Yêu cầu, trạng thái FR | [docs/requirements/requirements.md](docs/requirements/requirements.md), [docs/ba/](docs/ba/README.md) |
| Thiết kế giao diện (Figma) | [Yofina Foresight — UI demo](https://www.figma.com/design/l9vWyORNRjDqiEOXqpbzYm), ghi chú ở [figma-ui-design.md](docs/research/figma-ui-design.md) |
| Trạng thái hiện tại | [HANDOFF.md](HANDOFF.md) |
