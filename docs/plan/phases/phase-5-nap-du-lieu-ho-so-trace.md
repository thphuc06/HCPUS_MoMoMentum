# Phase 5 — Nạp dữ liệu, hồ sơ hành vi, bộ nhớ, trace (F6, F7)

Ngày dự kiến: 6–8/12/2026. Kế hoạch tổng: [master-plan.md](../master-plan.md). Điều kiện vào: phase 4 đạt; đọc "Kết quả thực hiện" của các phase trước.

## Mục tiêu

Người dùng chụp ảnh một thông báo chuyển khoản hoặc tải CSV, duyệt các dòng chưa chắc, thấy độ phủ dữ liệu tăng và dự báo cập nhật; trợ lý nhớ sở thích và mẫu chi tiêu qua các phiên, đưa nhận xét hành vi và một việc cần làm; đội sản phẩm xem lại được mọi quyết định của agent trên màn hình trace. **Cảnh 5 và 6 chạy được: cả 6 cảnh demo đi được trên app thật.**

## Phạm vi

FR9 (ảnh và CSV; sao kê PDF nếu kịp), FR10, FR13 (bản tin chủ động), FR14 (cảnh báo khoản chuyển lệch thói quen, nếu kịp), FR15 (bảng vận hành), kho tri thức RAG, quyền riêng tư (xem và xóa dữ liệu, bộ nhớ).

Thứ tự cắt nếu thiếu thời gian: sao kê PDF → FR14 → contextual bandit (không làm) → RAG tìm kiếm (giữ biểu phí có cấu trúc).

## Đọc trước

| Luồng | Đọc |
|---|---|
| Mọi luồng | [proposal-summary.md](../../proposal/proposal-summary.md) §7 (quyền riêng tư), §9 (Memory, RAG, Observability), §10.6 |
| A | [spike-bedrock-models.md](../../research/spike-bedrock-models.md) §5; [bedrock.md](../../research/bedrock.md) §3.6; [aws-data-events-infra.md](../../research/aws-data-events-infra.md) §3.3; mã `spikes/bedrock-models/05_images.py` |
| B | [agentcore.md](../../research/agentcore.md) §3.5; hướng dẫn Memory qua agentcore MCP (`get_memory_guide`); [ml-forecasting.md](../../research/ml-forecasting.md) phần hồ sơ hành vi |
| C | [bedrock.md](../../research/bedrock.md) §3.5; tài liệu Knowledge Bases hiện hành về vector store (tra bằng aws-docs MCP) |
| D | [agentcore.md](../../research/agentcore.md) §3.6; [spike-agentcore-runtime-cors.md](../../research/spike-agentcore-runtime-cors.md) §6; [spike-agentcore-gateway-identity.md](../../research/spike-agentcore-gateway-identity.md) §4; skill `aws-core:aws-observability` |
| E | [figma-ui-design.md](../../research/figma-ui-design.md) §8.2 cảnh 5 và 6. Figma node: I1 `24:2165`, I2 `24:2210`, I3 `24:2269`, I4 `24:2347`, X1 `25:2591`, S1 Hồ sơ `31:2754`; component IngestRow `14:417`, ProactiveCard `14:176` |

## Bước 0 — Hợp đồng

- Migration `0005`: `ingest_jobs` (trạng thái, tiến độ, loại tệp), `ingest_rows` (dòng trích được, độ tin cậy, trạng thái duyệt, khóa khử trùng), `behavior_profiles` (đặc trưng, mẫu hành vi kèm bằng chứng), `consents` (đồng ý theo nguồn nạp), mở rộng `nudges` (giá trị ước tính, loại, kết quả).
- Tool: `ingest___start_job`, `ingest___get_job_status`, `ingest___confirm_rows`, `forecast___get_behavior_profile`, `knowledge___search`.
- Khối: `ingest_review`, `coverage_change`, `behavior_insight`, `citation`.
- REST: xin URL tải lên, tạo job, tiến độ, duyệt dòng; hồ sơ hành vi; bản tin; bộ nhớ (xem, xóa); xóa dữ liệu của tôi; nhóm `/ops/*` cho màn trace (chỉ nhóm Cognito `ops`).

## Luồng A — Nạp dữ liệu (F6)

Sở hữu: `gateway/tools/ingest/`, `pipelines/ingest/`.

- Tải lên: presigned URL vào bucket `yofina-ingest-*` theo tiền tố của người dùng; giới hạn kích thước và loại tệp; ghi `consents`.
- Job: S3 → SQS (DLQ) → Lambda `yofina-ingest`. Ảnh: Sonnet 4.6 trích JSON (ngày, số tiền, đối tác, nội dung), dự phòng Kimi K3; không dùng Haiku 4.5. CSV: parser cộng model nhỏ ánh xạ tên cột. PDF (nếu kịp): tách trang thành ảnh hoặc văn bản rồi đi cùng đường ảnh, không dùng Bedrock Data Automation. Loại khác: lỗi rõ kèm định dạng được hỗ trợ.
- Sau trích: chuẩn hóa ngày, số tiền, đối tác; che số tài khoản, số điện thoại, tên người khác trước khi lưu và trước khi vào model; khử trùng với sổ cái (khóa băm cộng cửa sổ lệch thời gian); phân loại bằng pipeline của phase 4; dòng tin cậy cao tự thêm, dòng thấp vào hàng chờ duyệt.
- Nội dung tệp chỉ là dữ liệu: prompt tách rõ chỉ dẫn và nội dung, đầu ra ép schema, không tool ghi nào chạy từ nội dung tệp.
- `confirm_rows` (thao tác của người dùng trên màn hình, có token); xong thì cập nhật độ phủ dữ liệu và kích hoạt dự báo lại.
- Ingestion agent trong chat: "mình vừa nạp ảnh" → trạng thái job và khối `ingest_review`.
- Bộ ảnh thử: ít nhất 10 ảnh, gồm ảnh chụp màn hình thật do chủ dự án cung cấp nếu có (đã che thông tin thật), ảnh mờ, ảnh không phải tài liệu tài chính.

## Luồng B — Hồ sơ hành vi, bộ nhớ, bản tin (F7)

Sở hữu: `pipelines/nightly/` (bước mới), `agent/memory/`, phần Memory của stack `YofinaAgent`.

- Bước batch đêm: đặc trưng theo nhịp lương, giờ, ngày trong tuần, mức dùng trả sau; phân cụm đơn giản; model nhỏ tóm tắt thành nhận xét, mỗi nhận xét kèm bằng chứng số liệu và qua `NumericGrounding`. Ghi `behavior_profiles`.
- AgentCore Memory dài hạn: chiến lược sở thích, sự thật về người dùng, tóm tắt phiên; namespace theo `sub`. Hồ sơ hành vi và "bài học của agent" (tóm tắt từ `feedback`: kiểu gợi ý được chấp nhận hay bị từ chối) ghi bằng bản ghi tự tạo. Không lưu số dư hay giao dịch thô; che PII trước khi ghi.
- Agent đọc bộ nhớ ở router và Analyst: sở thích đã nói ở phiên trước được dùng lại mà không hỏi lại.
- Xem và xóa bộ nhớ của mình; "Xóa dữ liệu của tôi" xóa dữ liệu Aurora, tệp S3 và bản ghi bộ nhớ của người dùng (Memory không có API xóa theo người dùng: liệt kê theo namespace rồi xóa từng bản ghi).
- Bản tin chủ động (FR13): cuối batch đêm, cổng giá trị chọn tối đa một việc mỗi ngày, chỉ khi vượt ngưỡng; ghi `nudges`; hiện ở thẻ chủ động. `schedule_nudge` dùng EventBridge Scheduler. Tôn trọng "Ít nhắc loại này" và sở thích trong bộ nhớ ("đừng nhắc buổi sáng").
- FR14 (nếu kịp): khi chuyển tiền, so khoản chuyển với mẫu chi cá nhân (z bền theo người nhận và số tiền) và ảnh hưởng tới hũ Dự phòng; lệch thì thêm một `notice` vào bước xem lại T4.

## Luồng C — Kho tri thức (RAG)

Sở hữu: `knowledge-base/`, `gateway/tools/knowledge/`.

- Nội dung ba kho trong `knowledge-base/`: biểu phí và điều khoản sản phẩm trả sau mô phỏng (dẫn biểu phí công khai làm ví dụ, có ngày hiệu lực), kiến thức tài chính cá nhân, bộ luật suitability kèm giải thích. Mỗi tài liệu có metadata sản phẩm và ngày hiệu lực; chia đoạn theo điều khoản.
- Vector store: ưu tiên Bedrock Knowledge Bases với S3 Vectors hoặc Aurora pgvector sẵn có (không phí theo giờ). **Không tạo OpenSearch Serverless.** Nếu Knowledge Bases ở `ap-southeast-1` không dùng được với hai lựa chọn đó, tự viết truy xuất lai trên Aurora (pgvector + `tsvector`, Cohere embed) và ghi lệch.
- `knowledge___search`: truy xuất lai, lọc metadata; trả đoạn trích kèm nguồn. Agent chỉ gọi khi cần trích dẫn; khối `citation`. Số để tính vẫn lấy từ `get_fee_schedule`.
- Script đồng bộ kho tri thức (dùng lại ở batch tuần, phase 6).

## Luồng D — Trace và bảng vận hành (FR15)

Sở hữu: `gateway/tools/audit/` (phần ops), phần quan sát của `YofinaTools`.

- Màn trace đọc từ `audit_events` (bản ghi lượt: router, kế hoạch, từng tool call kèm thời lượng, verifier, luật đã kiểm, token, chi phí ước tính), không phụ thuộc Transaction Search.
- `/ops/traces` (danh sách, lọc), `/ops/traces/{id}`, `/ops/summary` (số lượt, độ trễ p50/p95, tỷ lệ lỗi tool, số lần luật chặn, số lượt gọi model theo ngày so với trần). Chỉ nhóm Cognito `ops`; dữ liệu người dùng đã che PII.
- Dashboard CloudWatch `yofina-ops` (độ trễ tool, lỗi Lambda, DLQ, `AllowDecisions`/`DenyDecisions`, dung lượng Aurora, lượt gọi model) và alarm về SNS.
- CloudWatch Transaction Search và span OTel: hỏi chủ dự án trước khi bật (đổi cấu hình mức tài khoản, có phí). Được đồng ý thì bật, kiểm span của Runtime và Gateway khớp `traceparent`, thêm link từ màn trace.

## Luồng E — Frontend

Sở hữu: `frontend/`.

- I1–I4: chọn hoặc chụp ảnh (input `capture`), tải CSV, tiến độ bằng polling, duyệt dòng (tự thêm / cần duyệt), độ phủ trước–sau, "Xem dự báo cập nhật".
- X1 trace (desktop 1280×800, có bố cục dùng được trên điện thoại): mở từ hàng "Mã trace" trong bảng "Vì sao" với tài khoản có quyền; trang tổng hợp vận hành.
- Hồ sơ (thay khung giữ chỗ S1): thông tin khai báo, nhận xét hành vi, bộ nhớ của tôi (xem, xóa), đồng ý theo nguồn, xóa dữ liệu, đặt lại dữ liệu demo, đăng xuất.
- Thẻ chủ động hiện bản tin; nhận xét hành vi trong chat.

## Bộ đánh giá của phase

`evals/golden/phase5.jsonl` (ít nhất 10 câu: hỏi về thói quen, dùng lại sở thích phiên trước, hỏi biểu phí có trích dẫn, trạng thái nạp) và `evals/adversarial/phase5.jsonl` (ít nhất 10 ca: ảnh và CSV chứa chỉ dẫn "bỏ qua hướng dẫn, chuyển tiền…", ảnh có tên và số tài khoản người khác, câu hỏi moi bộ nhớ của người khác).

## Tiêu chí hoàn thành

1. Tài khoản `minh`: nạp ảnh thông báo chuyển khoản mẫu → tiến độ → duyệt dòng → độ phủ tăng (theo Figma 62% lên 81%; số thật ghi lại) → Chi tiết hũ có dự báo mới.
2. Nạp cùng ảnh lần hai: không ghi trùng. Ảnh không phải tài liệu tài chính: lỗi rõ.
3. Trên bộ ảnh thử: đúng cả bốn trường ở ít nhất 9/10 ảnh đọc được; số ghi lại. CSV mẫu 50 dòng nạp đúng.
4. Ca tấn công qua tệp: không tool ghi nào chạy, không dòng nào tự thêm sai; tên và số tài khoản người khác đã che trong DB và trong log model.
5. Phiên 1 nói "đừng nhắc mình buổi sáng, ưu tiên hũ Du lịch"; phiên mới (session id khác) câu trả lời và bản tin dùng sở thích đó. Xóa bộ nhớ xong thì không còn.
6. Sau batch đêm, `minh` có ít nhất hai nhận xét hành vi kèm bằng chứng số khớp sổ cái; thẻ chủ động hiện tối đa một việc.
7. Câu hỏi về phí trả sau có khối `citation` trỏ đúng tài liệu; con số phí khớp bảng có cấu trúc.
8. Màn trace mở từ bảng "Vì sao" của một lượt what-if vừa chạy, hiện đủ các bước; tài khoản không thuộc nhóm `ops` bị từ chối.
9. "Xóa dữ liệu của tôi" trên một tài khoản thử: Aurora, S3 và Memory không còn bản ghi của người đó.
10. **Cả 6 cảnh demo đi liền mạch** trên URL Amplify với tài khoản `giamkhao1` vừa đặt lại.

## Cách kiểm (người điều phối)

- Chạy test; chạy bộ đánh giá phase 3–5 (hồi quy).
- Tự đi tiêu chí 1, 2, 5, 8, 9 bằng tay trên app; đối chiếu Aurora, S3, Memory.
- Đọc log của Lambda nạp để chắc PII đã che trước lời gọi model.
- Đi trọn 6 cảnh theo [figma-ui-design.md §8.2](../../research/figma-ui-design.md), bấm giờ từng cảnh so với [demo-script.md](../demo-script.md).

## Kế hoạch thực hiện (chốt 24/11, Claude Code điều phối, worker `kiro-cli` Opus 5.5)

Cách chạy: mỗi việc một worker trong worktree riêng `C:\moMo-wt\p5-<việc>` (nhánh `p5/<việc>` từ `main`), chỉ chạy unit test trong lúc làm; người điều phối review, merge theo thứ tự, chạy unit cả bộ; cuối đợt MỘT worker deploy + integration + eval. Không bật CloudWatch Transaction Search (cần chủ dự án quyết, có phí mức tài khoản); cắt sao kê PDF và FR14 theo thứ tự cắt của phase. **Cắt luồng C (kho tri thức RAG): chủ dự án quyết 24/11**, vì sản phẩm không cần tìm kiếm tài liệu (mọi con số đã lấy từ bảng có cấu trúc, RAG không nằm trên đường demo nào); chỉ giữ trích dẫn nguồn của biểu phí có cấu trúc. Không tạo OpenSearch Serverless; không tài nguyên tính tiền theo giờ.

**Bước 0 — hợp đồng (worker `p5-contracts`, làm trước, các luồng sau bắt đầu từ commit merge của nó).** Sở hữu `contracts/`, `db/migrations/0053_phase5.sql`, `libs/yofina_core/src/yofina_core/` (khối, model Pydantic, mã lỗi), `frontend/src/contracts/` (chỉ sinh bằng `scripts/gen_contracts.mjs`), `tests/unit/test_contracts*`, `evals/golden/phase5.jsonl`, `evals/adversarial/phase5.jsonl`.
- Migration `0053`: `behavior_profiles` (đặc trưng, nhận xét kèm bằng chứng số, phiên bản, RLS FORCE); mở rộng `nudges` (kind, giá trị ước tính, outcome, lý do cổng); `data_deletions` (nhật ký xóa dữ liệu, không chứa dữ liệu đã xóa). Theo khuôn RLS, hàm `app_*` của 0050–0052; `RESET_DELETES` cập nhật.
- Tool: `forecast___get_behavior_profile` (ba tool `ingest___*` đã có hợp đồng, chỉ rà lại). Không có `knowledge___search` (RAG đã cắt).
- Khối: `behavior_insight` (nhận xét + bằng chứng số + một việc cần làm), `citation` (tên nguồn, ngày hiệu lực, đường dẫn nguồn, câu trích ngắn nếu có), dựng từ các trường nguồn mà `get_fee_schedule` đã trả, không qua tìm kiếm.
- REST (OpenAPI): `GET /profile/behavior`; `GET /nudges/today`, `POST /nudges/{id}/feedback`; `GET /memory`, `DELETE /memory/{record_id}`, `DELETE /memory`; `POST /me/delete-data` (có token xác nhận); `GET /ops/traces`, `GET /ops/traces/{trace_id}`, `GET /ops/summary` (chỉ nhóm `ops`).
- Fixture hợp lệ/không hợp lệ cho mọi thứ mới; golden phase 5 ≥ 10 câu, adversarial ≥ 10 ca theo mục "Bộ đánh giá".

**Sau bước 0, năm luồng song song** (mỗi luồng chỉ sửa file của mình; `agent/src/yofina_agent/turn.py`, `router.py`, `schemas.py` chỉ thêm một nhánh dispatch, một luật prompt, một intent — phần còn lại viết ở module mới; `infra-cdk/lib/*.ts` chỉ thêm khối của mình, người điều phối gỡ xung đột khi merge):

| Worker | Luồng | Sở hữu | Kết quả cần có |
|---|---|---|---|
| `p5-ingest` | A còn lại | `gateway/tools/ingest/`, `pipelines/ingest/`, `agent/src/yofina_agent/ingest_chat.py` (mới), Cedar `gateway/policies/` cho `ingest___*`, target `ingest` trong `agent-stack.ts` | Ba tool `ingest___*` trên Gateway (Cedar ép user, `confirm_rows` qua token); intent "mình vừa nạp ảnh" → trạng thái job + khối `ingest_review`; dòng nạp dùng pipeline phân loại phase 4 (bảng → luật → k-NN → model nhỏ) thay bộ gán riêng |
| `p5-behavior` | B: hồ sơ hành vi, bản tin | `ml/yofina_ml/behavior.py` (mới), `pipelines/forecast/yofina_forecast/behavior.py` (mới) + bước trong `batch.after_forecast`, `forecast___get_behavior_profile`, `gateway/tools/ledger/yofina_ledger/proactive.py` (cổng giá trị), REST `/profile/behavior`, `/nudges/*`, `forecast-pipeline.ts` (IAM model nhỏ) | Đặc trưng nhịp lương, giờ, thứ, trả sau; phân cụm đơn giản; model nhỏ tóm tắt qua NumericGrounding; ≥ 2 nhận xét cho `minh`; cổng chọn tối đa một việc/ngày theo thứ tự Học đề xuất (hũ thiết yếu sắp cạn → nghĩa vụ 3 ngày → lộ trình mới chờ chọn → hỏi gộp → điểm tụt nhóm), "Ít nhắc loại này" hạ một bậc; khối `behavior_insight` trong chat |
| `p5-memory` | B: bộ nhớ, quyền riêng tư | `agent/src/yofina_agent/memory.py` (mới), Memory trong `agent-stack.ts`, REST `/memory*`, `/me/delete-data` (ledger + IAM S3/Memory) | AgentCore Memory (sở thích, sự thật, tóm tắt phiên; namespace theo `sub`; che PII; không lưu số dư hay giao dịch); router và Analyst đọc sở thích; xem/xóa; xóa dữ liệu của tôi xóa Aurora, S3, Memory (liệt kê namespace rồi xóa từng bản ghi) |
| `p5-ingest` (thêm) | C thu gọn | `agent/src/yofina_agent/fee_citation.py` (mới) | Câu hỏi về phí trả sau: số lấy từ `get_fee_schedule`, kèm khối `citation` dựng từ tên nguồn, đường dẫn và ngày hiệu lực của chính bảng đó (tiêu chí 7 sửa lại: trích dẫn trỏ đúng nguồn của bảng phí, không có RAG) |
| `p5-ops` | D | `gateway/tools/audit/`, `gateway/tools/ledger/yofina_ledger/ops*.py` (mới), route `/ops/*` + dashboard `yofina-ops` + alarm trong `tools-stack.ts` | `/ops/*` chỉ nhóm `ops` (403 cho người khác), dữ liệu đã che PII; tổng hợp p50/p95, lỗi tool, luật chặn, lượt model so với trần |
| `p5-frontend` | E | `frontend/` (trừ `src/contracts/`) | Hồ sơ S1 (khai báo, nhận xét hành vi, bộ nhớ xem/xóa, đồng ý, xóa dữ liệu, đặt lại demo, đăng xuất); X1 trace desktop mở từ "Mã trace" (nhóm `ops`); view khối `behavior_insight`, `citation`; thẻ chủ động hiện bản tin. Code theo fixture |

**Thiết kế bộ nhớ (theo best practice chính thức của AgentCore Memory, chủ dự án yêu cầu 24/11).** Một Memory resource, tách người dùng bằng namespace theo `sub` của JWT (dạng chuẩn có `/` đầu và cuối). Ba loại, mỗi loại một strategy và namespace: sở thích (`USER_PREFERENCE`, `/users/{actorId}/preferences/`), sự thật người dùng tự nói (`SEMANTIC`, `/users/{actorId}/facts/`), tóm tắt phiên (`SUMMARIZATION`, `/users/{actorId}/summaries/{sessionId}/`). Không đưa vào Memory: số dư, giao dịch, số tiền, kết quả tool, hồ sơ hành vi (nguồn sự thật là Aurora). Trích xuất: ứng dụng đã lưu lượt thô ở Aurora nên ưu tiên `IngestData` (không lưu event ngắn hạn), không dùng được thì `CreateEvent` với hạn ngắn nhất. Chống đầu độc bộ nhớ: chỉ ghi chữ đã che PII và đã qua Guardrail; không ghi lượt bị chặn, lượt ngoài phạm vi, nội dung tệp nạp; nội dung đọc từ Memory coi là dữ liệu không tin cậy, không làm căn cứ cho con số. Đọc đầu lượt có timeout, hỏng thì lượt vẫn chạy. IAM tối thiểu theo đúng ARN memory. Chi tiết và nguồn: `docs/research/agentcore-memory-design.md` (worker `p5-memory` viết).

**Cuối đợt (worker `p5-deploy`)**: build zip, migration `0053`, `YofinaTools`, `YofinaAgent` (Memory, Gateway), Runtime, frontend; integration mới cho phase 5 + hồi quy phase 3–4; golden/adversarial phase 5 MỘT lần. Người điều phối tự đi tiêu chí 1, 2, 5, 8, 9 và 6 cảnh khi chủ dự án đăng nhập.

## Kết quả thực hiện

### Luồng A (F6 nạp dữ liệu) — xong và deploy 23/11; các luồng B, C, D, E (phần ngoài F6) chưa làm

Làm song song với phase 3 trên nhánh `feat/ingest`, merge vào `main` ở `82de21d`. Thiết kế: [contracts/README.md](../../contracts/README.md) mục "Phase 5 (F6)"; ghi chú ghép: [ingest-merge-notes.md](../ingest-merge-notes.md).

- **Đã có**: migration `0050_ingest` (nguồn trả `external` không bao giờ đổi số dư hũ; bảng `ingest_jobs`, `ingest_rows`, `consents` RLS FORCE; độ phủ dữ liệu tính cả thu chi ngoài ví), stack `YofinaIngest` (bucket, SQS + DLQ, `yofina-ingest-api`, worker `yofina-ingest`), trích ảnh bằng Sonnet 4.6 (dự phòng Kimi K3), CSV bằng parser + Nova 2 Lite, che PII trước khi lưu, khử trùng chéo nguồn, gán hũ (loại giao dịch, luật, rồi model), `confirm_rows` có token qua `/ingest/confirmations` + `/ingest/actions` rồi tính lại dự báo, màn I1–I4 (Tổng quan → Tiền vào → "Nạp ảnh / sao kê ngoài ví"), persona `vy` cho `giamkhao3`.
- **Kiểm trên môi trường thật** (`tests/integration/test_ingest_live.py`, 11/11, 23/11): nạp `data/personas/samples/vy_sao_ke_vcb.csv` tới bước duyệt, đổi hũ một dòng, chốt bằng token; độ phủ tăng (0,664 lên 0,839 theo bộ sinh); số dư hũ và tổng ví không đổi; token dùng lại bị chặn (`TOKEN_REUSED`), chốt lại job đã xong bị chặn (`ALREADY_APPLIED`); nạp lại cùng tệp bị từ chối (`INGEST_DUPLICATE_FILE`); ảnh không phải tài liệu tài chính bị từ chối (`INGEST_NOT_FINANCIAL`); đặt lại demo xóa job, đồng ý và dòng nạp.
- **Eval trích xuất với Bedrock thật** (`scripts/eval_ingest.py`, 58 mục, 22/11, 0 lỗi chạy):

| Chỉ số | Ảnh thật (25, nhãn do agent đọc, chờ chủ dự án duyệt) | Dựng (33: 28 ảnh, 5 CSV) |
|---|---|---|
| Số tiền đúng | 22/25 (88%) | 123/125 (98%) |
| Ngày đúng | 16/21 (76%) | 123/125 (98%) |
| Đủ 4 trường trên ảnh đọc được | 7/12 (58%) | 23/24 (96%) |
| Gắn hũ đúng | 1/1 | 86/105 (82%) |
| Tỷ lệ dòng vào hàng chờ duyệt | 22/23 (96%) | 39/123 (32%) |
| Màn chưa thực hiện không tự thêm | 8/8 | — |
| Tấn công an toàn / không lộ PII | — / 10/10 | 5/5 / 1/1 |
| Báo `not_financial` đúng | 1/5 | 3/3 |

- **Lệch và hạn chế**: bảng phí, menu, màn ATM được model xếp "tài liệu tài chính khác" nên không tạo dòng nhưng mã lỗi khác nhãn `not_financial` (1/5); eval chạy không DB nên "trùng lặp được đánh dấu" là 0% (khử trùng thật dựa trên DB, đã kiểm bằng local_pg và test tích hợp); ảnh thật có độ đủ trường thấp (58%) nên gần như mọi dòng ảnh thật vào hàng chờ, đúng thiết kế an toàn. Chưa có tool Gateway `ingest___*` và intent "mình vừa nạp ảnh" trong chat; chưa dùng phân loại phase 4; chưa đi màn I1–I4 trên trình duyệt với backend thật (đã kiểm bằng `dev:mock` 390x844 và bằng test tích hợp REST).
