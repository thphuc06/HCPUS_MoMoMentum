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

**Lộ trình lập trực tiếp trong chat phải đầy đủ (chủ dự án yêu cầu 24/11, worker `p5-roadmap-quality`).** Lúc demo cảnh 4, để agent lập lộ trình ngay trước mặt người xem thay vì chỉ mở bản seed: 2–3 giai đoạn, 4–6 bước, mỗi bước là hành động cụ thể (số tiền, hũ nguồn → hũ đích hoặc hạn), kiểm luật song song. Điều kiện để đưa vào kịch bản demo: lượt lập lộ trình xong trong khoảng 30 giây và trong lúc chờ khung chat hiện từng chặng (đọc dữ liệu → phác thảo → phân bổ → kiểm luật → lưu; agent đã phát các bước `roadmap_<chặng>`); lời kết nói rõ đây là bản đề xuất, bản nào đang dùng, và có lối sang trang Lộ trình để so sánh. Bản seed v3 "hành vi thay đổi" giữ làm đường dự phòng của cảnh 4. Worker deploy đo thời gian thật của lượt này và ghi lại; cập nhật `docs/plan/demo-script.md` khi đạt.

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

### Quyết định hợp đồng phase 5

Viết ngày 2026-11-24 bởi worker `p5-contracts` (Kiro, Claude Opus 5.5) làm "Bước 0 — hợp đồng" của "Kế hoạch thực hiện". Sáu luồng sau đọc mục này cùng [contracts/README.md](../../../contracts/README.md) mục "Phase 5 (F7, RAG, quyền riêng tư, trace)". Mọi mục dưới đây là lựa chọn tự quyết khi file phase chưa nói rõ; **lệch so với file phase** được đánh dấu. Migration `0053`, tool và route mới **chưa chạy trên Aurora, chưa deploy**. Tài liệu đã tra (24/11): AgentCore Memory (memory-strategies, built-in-strategies, user-preference-memory-strategy, memory-organization, API `CreateEvent`, `ListMemoryRecords`, `MemoryRecordSummary`, `DeleteMemoryRecord`, `BatchDeleteMemoryRecords`, `BatchCreateMemoryRecords`, `DeleteEvent`), README pgvector (hybrid search với full-text và Reciprocal Rank Fusion), PostgreSQL 16 "Tables and Indexes" của full-text search (cột tsvector sinh STORED, chỉ mục GIN).

**Dữ liệu**

1. **Một migration `0053_phase5.sql`** (file phase đánh số cũ `0005`): một transaction, tách bằng `-- @@`, viết lại được (DROP CONSTRAINT IF EXISTS trước mỗi ADD CONSTRAINT), RLS `ENABLE` + `FORCE`, không sửa 0001 tới 0052. Đã chạy thật trên PostgreSQL 16 cục bộ (pgserver, pgvector 0.6.2) bằng một test tạm (đã xóa, xem báo cáo): chạy lại được, RLS, quyền, truy xuất lai, bản tin, ops, xóa dữ liệu. Toàn bộ `tests/local_pg` chạy với 0053: 4 test của `test_classify_flow.py` và `test_roadmap_flow.py` đỏ, và đỏ y hệt khi bỏ 0053 (lỗi có từ trước, không liên quan).
2. **`behavior_profiles`: một dòng mỗi (người dùng, ngày mô phỏng)**, ghi đè khi tính lại (như `resilience_scores`). Đặc trưng, nhóm, nhận xét, việc cần làm là jsonb có hình dạng `BehaviorProfileData` (một nguồn cho bảng, tool, REST, khối), vì chúng chỉ được đọc cả cụm. "Phiên bản" là `config_version` của bộ tính (không đánh số phiên bản như lộ trình: hồ sơ là dữ liệu dẫn xuất, không có chuyện "giữ bản cũ"). CHECK của DB khóa hai trạng thái: sẵn sàng thì có ít nhất một nhận xét và việc cần làm; chưa sẵn sàng thì không có. `RESET_DELETES` phải thêm bảng này (file ở `gateway/tools/ledger/`, luồng p5-behavior).
3. **Kho tri thức `kb_documents`, `kb_chunks` là dữ liệu dùng chung: không có `user_id`, không RLS, `yofina_app` chỉ SELECT, nạp bằng secret MASTER** (như `tx_type_map`, `fee_schedules` của 0005 và cách nạp `db/seed`). Lý do: nội dung là tài liệu công khai mô phỏng giống nhau với mọi người dùng nên RLS theo người dùng vô nghĩa; không cho role ứng dụng ghi để một Lambda bị chèn lệnh (prompt injection qua tệp nạp) không đầu độc được kho trích dẫn; script đồng bộ do người vận hành chạy (luồng p5-rag, dùng lại ở batch tuần). Mỗi tài liệu một phiên bản `active` (chỉ mục duy nhất một phần), bản cũ `retired` để còn đọc lại trích dẫn cũ. Tên cột văn bản là `body` (không đặt `text` để khỏi nhầm với kiểu `text` trong plpgsql).
4. **Truy xuất lai tự viết trên Aurora, không Bedrock Knowledge Bases ở bước hợp đồng** (BỔ SUNG: file phase để luồng C quyết). Hàm `app_kb_search` hợp nhất hai danh sách bằng Reciprocal Rank Fusion: vector (pgvector `<=>` cosine, HNSW `m = 16`, `ef_construction = 64` như 0052) và từ khóa (`tsv` = `to_tsvector('simple', app_fold_text(heading + body))`, cột sinh STORED, chỉ mục GIN; câu hỏi cũng bỏ dấu rồi nối các từ bằng HOẶC vì câu hỏi tự nhiên dài, đòi đủ mọi từ thì gần như không khớp). Điểm = tổng `1/(60 + hạng)` chia cho `2/61` để về 0..1 (`yofina_core.knowledge.rrf_score`, cùng công thức, test kiểm). Lọc trước khi xếp hạng: tài liệu `active`, còn hiệu lực ở hôm nay mô phỏng, đúng kho, đúng sản phẩm hoặc không gắn sản phẩm. Lý do: Aurora và Cohere embed đã có (không phí theo giờ, không OpenSearch Serverless); cấu hình `simple` vì Postgres không có từ điển tiếng Việt; `app_fold_text` của 0050 là IMMUTABLE nên dùng được trong cột sinh. Nếu p5-rag chọn Bedrock Knowledge Bases với S3 Vectors thì giữ nguyên hợp đồng tool (`knowledge___search` trả cùng `KnowledgeSearchData`) và bỏ hai bảng; đó là quyết định của luồng.
5. **`nudges` mở rộng, không bảng mới** (đúng file phase): thêm `value_vnd` (giá trị ước tính, số nguyên VND, vắng khi loại đó không đo bằng tiền), `gate_reason` (hạng, điểm, ngưỡng, số ứng viên, đã hạ bậc chưa), `title`, `body`, `outcome` (acted, dismissed, snoozed, less_like_this), `outcome_at`. Bản tin của cổng là `source = system`, tối đa MỘT mỗi (người dùng, ngày mô phỏng), DB bảo đảm bằng chỉ mục duy nhất một phần. CHECK `fire_on > created_app_date` của 0010 (ràng buộc bảng không tên) được tìm theo định nghĩa trong khối `DO` rồi thay bằng `nudges_fire_on_check` cho phép bản tin hiện ngay trong ngày tạo. "Ít nhắc loại này" không có bảng sở thích riêng: cổng đếm `less_like_this` theo loại bằng `app_nudge_outcome_stats` (YAGNI).
6. **Ba loại bản tin mới (`roadmap_proposed`, `resilience_drop`, `behavior_insight`) chỉ cổng sinh được, KHÔNG vào `wallet.NUDGE_KINDS`** (tập mà `schedule_nudge` nhận): người dùng và agent không tự lên lịch được chúng. `wallet.ALL_NUDGE_KINDS` là tập của cột `kind`; `wallet.NUDGE_GATE_ORDER` là thứ tự ưu tiên theo đề xuất của Học (hũ thiết yếu sắp cạn, nghĩa vụ trong 3 ngày, lộ trình mới chờ chọn, hỏi gộp, điểm tụt nhóm), thêm `behavior_insight` cuối cùng.
7. **`data_deletions` không có khóa ngoại tới `users`** (dòng nhật ký phải còn sau khi `users` của người đó bị xóa), RLS theo `user_id` (đăng nhập lại cùng tài khoản Cognito vẫn đọc được nhật ký của mình), `yofina_app` SELECT, INSERT, UPDATE, không DELETE, tối đa một lần `running` mỗi người dùng. Chỉ chứa trạng thái và số lượng từng bước (s3, memory, aurora), không chứa dữ liệu đã xóa. Không bị đặt lại demo xóa.
8. **"Xóa dữ liệu của tôi" xóa cả `audit_events`** (LỆCH thiết kế 0001: "bản ghi sống lâu hơn người dùng"). Lý do: tiêu chí 9 đòi Aurora không còn bản ghi của người đó, và bản ghi lượt có nhãn dữ liệu đã dùng của chính họ; quyền xóa của proposal §7 thắng. Cách làm: hàm `app_delete_user_data` (SECURITY DEFINER, chủ hàm là MASTER vượt RLS như `app_list_forecast_users` của 0009) đếm rồi xóa ở MỌI bảng `public` có cột `user_id` (duyệt `information_schema`, nên bảng của phase sau cũng bị xóa), xóa `users` (CASCADE), kiểm không còn dòng nào (còn thì `RAISE`, cả transaction lùi). Hàm chỉ chạy khi có dòng `data_deletions` `running` của chính người đó, mà Lambda chỉ tạo sau khi kiểm token xác nhận: gọi trực tiếp với `user_id` khác không xóa được ai. Cognito không bị xóa (đăng nhập lại là tài khoản trắng).
9. **Bảng vận hành đọc `audit_events` của mọi người dùng qua bốn hàm SECURITY DEFINER chỉ trả cột đã chọn** (`app_ops_list_traces`, `app_ops_get_trace`, `app_ops_summary`, `app_ops_model_calls_by_day`), không qua role DB mới. Lý do: RLS của `audit_events` theo từng người dùng nên `yofina_app` không tự đọc chéo được; thêm role thì phải thêm secret và Lambda; hàm giới hạn đúng cột cần (không `user_id`, không `conversation_id`, không câu hỏi hay câu trả lời vì chúng không nằm ở `audit_events`). Người dùng hiện bằng `user_ref` = 12 ký tự hex đầu của sha256(`sub`), đủ để gom các lượt của cùng một người, không đảo ngược được nếu không biết `sub`. Quyền nhóm Cognito `ops` do Lambda kiểm TRƯỚC khi gọi (DB không biết JWT). Không đọc CloudWatch Transaction Search.
10. **Lần gọi tool nằm trong `step_timings` có sẵn, không thêm cột** (BỔ SUNG): bước có `step` là tên đầy đủ `<target>___<tool>` là một lần gọi tool, kèm `status` (`ok`, `error`, `denied`) và `code` tùy chọn ở `TraceStep` và ở `items` của `record_turn` (mở rộng tương thích ngược). Lý do: thêm tham số cấp trên cho `record_turn` làm lệch `_ARG_KEYS` của Lambda ledger đang chạy; pattern `^[a-z][a-z0-9_]{0,39}$` sẵn có đã nhận tên tool (tên dài nhất `forecast___get_behavior_profile`, 31 ký tự). Agent cần ghi các bước này (luồng p5-ops và người điều phối gỡ khi ghép `turn.py`).
11. **`audit_events.intent` nới thành mười bốn giá trị** (`wallet.AUDIT_INTENTS`), như 0052 đã làm với ba ý định phase 4, để `audit___record_turn` không vỡ ở lượt có ý định mới.

**Ý định, tool, khối**

12. **Bốn ý định mới `behavior`, `knowledge`, `ingest`, `memory` khai ở `wallet.PHASE5_INTENTS`, CHƯA vào `wallet.INTENTS`** (BỔ SUNG). Lý do: `agent/.../schemas.py` `Intent` là danh sách gõ tay và `tests/unit/agent/test_schemas.py` so nó với `INTENTS`; hợp đồng không được sửa `agent/`. Mỗi luồng khi thêm "một intent" vào `schemas.py` thì chuyển đúng ý định đó từ `PHASE5_INTENTS` sang `INTENTS` cùng lúc. `memory` là để người dùng NÓI một sở thích ("đừng nhắc mình buổi sáng") hoặc hỏi trợ lý nhớ gì: nếu không, router dễ xếp câu đó vào `profile_update` và gọi `update_profile`. `audit/yofina_audit/record.py` đang kiểm `intent in INTENTS`: luồng p5-ops đổi sang `AUDIT_INTENTS`.
13. **`forecast___get_behavior_profile` trả cả hồ sơ, `ready` sai không phải lỗi** (không thêm mã lỗi kiểu "chưa có hồ sơ"). Lý do: màn Hồ sơ và agent đều cần nói "cần thêm N ngày" thay vì hiện lỗi; mô tả tool cấm bịa nhận xét khi `ready` sai. Lọc `insight_kind`, `jar` chỉ bớt `insights`. Mọi số trong câu nhận xét có trong `evidence` (fixture kiểm bằng test, batch đêm kiểm bằng `NumericGrounding`).
14. **Khối `behavior_insight` là MỘT nhận xét cộng MỘT việc cần làm**, việc cần làm là của cả hồ sơ (`next_step`) và có `action` tùy chọn cùng hình dạng `RoadmapStepAction` (`move_between_jars`, `save_jars`, `schedule_nudge`): bấm vào đi luồng xác nhận sẵn có, không đường ghi mới (ADR-0002). `$defs` của file khối cũng là hình dạng hồ sơ (một nguồn, như `ResilienceScoreData` nằm trong file khối của nó).
15. **`knowledge___search` trả `hits[].citation` đúng hình dạng `CitationItem` của khối `citation`**, nên agent chuyển nguyên, LLM không viết đoạn trích hay đường dẫn. Số để tính phí vẫn chỉ từ `get_fee_schedule` (mô tả tool nói rõ); fixture biểu phí dùng cùng nguồn và ngày hiệu lực với `db/seed/fee_schedules.sql`. Không có kết quả là OK với `hits` rỗng; không tính được embedding thì vẫn OK với `degraded` và chỉ kết quả từ khóa. Tài liệu tự biên soạn (kiến thức, luật suitability) chưa có đường dẫn công khai: fixture dùng miền dành riêng `kb.yofina.invalid`; p5-rag chọn đường dẫn thật (ví dụ tệp trong `knowledge-base/` của repo).
16. **`proactive_card` mở rộng tương thích ngược thay vì khối mới cho bản tin**: thêm ba `kind`, ba nút (`open_roadmap`, `open_resilience`, `open_profile`) và `nudge_id`. Lý do: file `proactive_card` đã ghi "phase 4-5 cổng nhắc dùng cùng khối" và frontend đã có view.

**REST**

17. **Mười một thao tác mới, đều Bearer JWT**; `GET /profile/behavior` do `forecast` (cùng Lambda với tool đọc bảng), còn lại do `ledger`. Phản hồi bản tin và xóa bộ nhớ KHÔNG qua token (không đổi số dư, như `POST /feedback`); "Xóa dữ liệu của tôi" ĐI QUA token vì không hoàn tác được.
18. **Token xóa dữ liệu dùng endpoint riêng `POST /me/delete-data/confirmations`** (BỔ SUNG: file phase chỉ nêu `/me/delete-data` "có token xác nhận"), theo đúng mẫu `/ingest/confirmations`: tool `delete_my_data` (`PrivacyToolName`) không vào `ToolName`, `ACTION_TOOLS` hay `GENERIC_ACTION_TOOLS`, nên `POST /confirmations` và `POST /actions` của ledger không nhận nó và test `openapi.test.ts` của frontend (so `TOOL_NAMES` với `ToolName`) không đổi. Cùng khóa HMAC và bảng `jti`; `ConfirmationResponse.tool` thêm `PrivacyToolName` vào `anyOf`. `params` chỉ có `scope: all` (`normalize_delete_my_data`, idempotent). Đang có lần xóa `running` thì trả lần đó; `partial` khi S3 hoặc Memory lỗi sau khi Aurora đã xóa (gọi lại với token mới để làm tiếp).
19. **`DELETE` là method mới của hợp đồng** (`DELETE /memory`, `DELETE /memory/{record_id}` đúng như kế hoạch). CORS của HTTP API chung hiện chỉ cho GET, POST, OPTIONS (lý do phase 5 F6 chọn `POST /ingest/rows/{row_id}/jar`): luồng p5-memory thêm `DELETE` vào `allowMethods` ở `tools-stack.ts`. Vẫn không có PATCH.
20. **`/ops/*` đánh dấu `x-required-group: ops`**, 403 `FORBIDDEN` cho người không thuộc nhóm (không thêm mã lỗi). Chi phí ước tính `est_cost_vnd` là số nguyên VND do Lambda tính từ `token_usage` và bảng giá trong cấu hình (hợp đồng không có bảng giá). Ngày của `model_calls_by_day` theo UTC thời điểm thật (trần gọi model tính theo ngày thật, không theo ngày mô phỏng).
21. **Bộ nhớ: không có `MemoryRecord.namespace` trên dây** (namespace chứa `sub`); `kind` suy từ namespace bằng `yofina_core.memory.kind_of_namespace`, trả None cho namespace không thuộc người gọi nên Lambda bỏ bản ghi đó dù lọc phía dịch vụ sai. Namespace có `/` đầu và cuối theo khuyến nghị của AgentCore (tránh trùng tiền tố giữa người dùng). Không có API xóa theo người dùng: liệt kê theo `namespacePath` rồi `BatchDeleteMemoryRecords` (tối đa 100 mỗi lần), sự kiện ngắn hạn bằng `ListSessions`, `ListEvents`, `DeleteEvent`. Xóa một bản ghi: đọc, kiểm namespace, rồi `DeleteMemoryRecord` kèm `namespace` (dùng cho điều kiện IAM).
22. **Mã lỗi mới, thêm cuối**: `MEMORY_RECORD_NOT_FOUND` (404; của người khác cũng như không có), `MEMORY_UNAVAILABLE` (503). Không thêm mã cho hồ sơ chưa sẵn sàng (mục 13) hay cho lần xóa đang chạy (mục 18).

**Bộ đánh giá**

23. **`evals/golden/phase5.jsonl` 14 câu, `evals/adversarial/phase5.jsonl` 14 ca**, cùng định dạng phase 4 (`intent`, `tools_must`, `tools_forbid`, `blocks_must`, `category`; `attack` và các cờ `forbid_*`). Ca nạp tệp tham chiếu tệp có sẵn bằng `upload_manifest_id` (`s19` PII, `s20` tới `s23` ảnh tấn công, `c04`, `c05` CSV tấn công của `evals/ingest/manifest.json`), không chép bản rõ PII. Trường mới mà `evals/run.py` chưa chấm được liệt kê ở contracts/README mục "Bộ đánh giá"; trường chưa chấm thì runner bỏ qua, các kiểm chung (`confirm_token` do agent tự điền, ghi không xác nhận, NumericGrounding) vẫn chạy.

**Cố ý để cho luồng sau (hợp đồng không làm)**: công thức đặc trưng, phân cụm, mẫu câu và model tóm tắt nhận xét (p5-behavior); ngưỡng và cách tính điểm của cổng giá trị, đọc sở thích "giờ im lặng" từ bộ nhớ (p5-behavior); cấu hình chiến lược AgentCore Memory trong CDK, che PII trước khi ghi sự kiện, đọc bộ nhớ ở router và Analyst (p5-memory); nội dung ba kho, chia đoạn theo điều khoản, script đồng bộ, chọn Knowledge Bases hay hàm `app_kb_search` (p5-rag); bảng giá cho `est_cost_vnd`, dashboard `yofina-ops`, alarm (p5-ops); hai file Cedar `get_behavior_profile.cedar`, `search.cedar` (luồng cài tool; CDK từ chối deploy nếu thiếu); `RESET_DELETES` thêm `behavior_profiles`; `record.py` đổi sang `AUDIT_INTENTS`; CORS thêm `DELETE`; route mới trong `tools-stack.ts`; view của hai khối mới, `REGISTERED_BY_FRONTEND`, hai mã lỗi trong `frontend/src/api/errors.ts` (p5-frontend); chấm các trường eval mới trong `evals/run.py` (p5-deploy). Hợp đồng KHÔNG chạy 0053 trên Aurora, không deploy gì.