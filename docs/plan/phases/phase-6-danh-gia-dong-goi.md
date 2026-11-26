# Phase 6 — Đánh giá, cứng hóa, đóng gói

Kế hoạch tổng: [master-plan.md](../master-plan.md). Bản đầu viết 21/11; **viết lại 24/11 khuya** (worker Kiro, Claude Opus 5.5, do Claude Code điều phối) theo hiện trạng sau Runtime v26.

**Ngày: 25/11–03/12/2026, nộp trước 18:00 ngày 03/12 (hạn chính thức 23:59:59 ngày 03/12).** [đổi 25/11: hạn thật lấy từ trang cuộc thi; sau hạn không được sửa mã nguồn, slide, sản phẩm đang chạy; sản phẩm phải chạy tới hết 11/12. Bản 24/11 giả định nộp 10/12. Việc cần làm theo dõi ở issue [#2](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/2), nguồn: [kiểm toán 25/11](../../research/2026-11-25-audit-tong-hop.md).] Điều kiện vào: phase 5 đóng (mục A dưới đây), hoặc tới 26/11 tối chưa đóng thì phase 6 vẫn chạy và ghi rõ phần thiếu.

Ký hiệu trong file: **[giữ]** là phần của bản 21/11 còn đúng; **[đổi 24/11]** là phần đã sửa; **[mới 24/11]** là phần thêm; **[cắt 24/11]** là phần bỏ (đề xuất, chờ chủ dự án duyệt ở mục 7).

## 0. Hiện trạng khi vào phase 6 (24/11 khuya)

| Mảng | Hiện trạng | Nguồn |
|---|---|---|
| Hạ tầng | Bảy stack `*_COMPLETE`; Runtime `yofina_agent` v26; Amplify job 19; migration tới 0054; Aurora min 0 / max 2 ACU, tự ngủ sau 600 giây | [HANDOFF](../../../HANDOFF.md), [aws-resources.md](../../aws-resources.md) |
| Test | Unit 3871, CDK 77/77, vitest 978. Không có CI (chưa có `.github/`) | HANDOFF |
| Eval (v25, một lần) | Golden phase 3 31/31, phase 4 14/14, phase 5 11/15 (bốn ca trượt do lỗi runner đã sửa; ở v26 đã đo lại hai ca: `memory-forget-no-invent` đạt, `memory-state-preference` trượt); adversarial 16/16, 12/12, 14/14; router diễn đạt lại 18/18; OCR ảnh thật 9/11, r08 đạt lại ở v26 | [phase 5](phase-5-nap-du-lieu-ho-so-trace.md) |
| Bộ eval | 60 câu golden (31 + 14 + 15), 42 ca đối kháng (16 + 12 + 14), 18 câu diễn đạt lại, 25 ảnh thật + 33 mục dựng cho OCR | `evals/` |
| Chi phí eval | Khoảng **$2,2–2,5 một lượt đầy đủ** (đo 24/11), khoảng 80% là Sonnet 4.6 | HANDOFF |
| Độ trễ đã đo | Event đầu phiên ấm 0,34 s, phiên lạnh 2,04 s; `POST /affordability` p95 328 ms; what-if (23/11, 10 lượt) khối đầu p50 6,9 s / p95 18,2 s, trọn câu p50 16,7 s / p95 28,2 s; what-if v21–v25 từ 16,9 đến 29,2 s mỗi lượt; lập lộ trình 20–26 s; `ApplyGuardrail` p50 446 / p95 531 ms | [phase 3](phase-3-what-if-va-kiem-tra.md), phase 5 |
| Chi phí một lượt | Một lượt what-if đọc từ trace: 3 lượt gọi model, 12.477 token vào, 1.549 token ra, ước 1.578 ₫ (khoảng $0,06). Chưa có số trung bình theo ý định | phase 5, tiêu chí 8 |
| Phase 4 còn lệch | Tỷ lệ phải hỏi khi phân loại 17,4% (mục tiêu < 10%); `period_end` của lộ trình chưa theo ngày lương; màn So với bản cũ ghi mã thô | [phase 4](phase-4-chong-chiu-lo-trinh.md) |
| Phase 5 còn mở | Tiêu chí 3 (OCR) chưa chốt; tiêu chí 10 (6 cảnh trên giao diện mới) chưa đi; bộ nhớ trích xuất còn lệch (`memory-state-preference`); `turn_persist_timeout` mỗi ca eval | phase 5, HANDOFF mục C |
| Video | Dự án Remotion ở `C:\moMo\video` (máy của Phúc, **chưa vào git**): phần dựng mở đầu 4 cảnh (`Story.tsx`) và một ô chờ đoạn quay app thật (`demoClip`); bản nháp `out/yofina-story-draft.mp4` dựng 22/11 | thư mục `video/` |
| Tài liệu nộp | `README.md` gốc còn ghi trạng thái 21/11 ("chưa có code sản phẩm"); cột trạng thái ở [requirements.md](../../requirements/requirements.md) và AC ở [ba/05](../../ba/05-acceptance-criteria.md) chưa cập nhật từ 22/11 | đọc file |

## 1. Mục tiêu

[đổi 24/11] Đưa bản đang chạy tới mức giám khảo tự dùng được và tin được, với số đo để chứng minh. Cụ thể:

1. Đóng phase 5 và không còn lỗi chặn 6 cảnh demo.
2. Cứng hóa bốn mặt: bảo mật (IAM, secret, CORS, giới hạn tốc độ), độ bền (lỗi ghi lượt, Aurora ngủ, retry, throttling), hiệu năng (độ trễ lượt, Guardrail), và các việc để sau của phase 4–5 có hiện trên đường demo.
3. Một lượt đánh giá đầy đủ duy nhất trên bản ứng viên cuối (RC), kèm bảng NFR "mục tiêu / đo được" và chi phí mỗi lượt.
4. Bộ nộp bài: README cho giám khảo, sơ đồ kiến trúc, video demo, kịch bản thuyết trình, tài liệu chi phí AWS.
5. Buổi chấm chạy được: tài khoản và mật khẩu mới, Aurora thức, kiểm trước giờ, phương án dự phòng khi Bedrock throttle hoặc chạm trần.

[đổi 25/11, chủ dự án] Được thêm tính năng mới tới hết 30/11 (deploy đợt 2). Tính năng chưa merge và chưa xanh ngày 30/11 thì cắt; mỗi tính năng có unit test và 1–2 ca eval, không làm gãy đường đi 6 cảnh. Bản 24/11 ghi "không thêm tính năng mới".

## 2. Tiêu chí hoàn thành đo được

[đổi 24/11] Tiêu chí chấm chính thức và trọng số chưa có (câu hỏi mở trong [open-questions.md](../../requirements/open-questions.md)). Bảng dưới gắn mỗi tiêu chí với thứ BA ghi là giám khảo sẽ nhìn: [ba/08 mục 5](../../ba/08-kpi-kinh-doanh.md#5-ma-trận-kpi-theo-bên-hưởng-lợi) (K2, K5, cộng NFR độ trễ, độ đúng của số, an toàn) và [ba/10 mục 7](../../ba/10-tac-dong-stakeholder.md#7-tác-động-theo-mốc-thời-gian) (mốc M0: dự báo đúng và sớm, token chặn 13 ca tấn công, trace 100% lượt, chi phí mỗi lượt). Chỉ tiêu NFR lấy từ [ba/04](../../ba/04-non-functional-requirements.md).

| # | Nhóm chấm | Tiêu chí | Chỉ tiêu | Nguồn số | Hiện trạng 24/11 |
|---|---|---|---|---|---|
| 1 | Độ đúng, AI có kiểm soát | Golden 60 câu trên RC | Mục tiêu 60/60; chấp nhận từ 57/60 khi mỗi ca trượt có nguyên nhân ghi lại và không thuộc nhóm an toàn. `NumericGrounding` 100% trên câu đã phát, `SchemaValidity` 100%, quỹ đạo tool từ 85% (NFR-07) | `evals/run.py`, `evals/results/` | 56/60 ở v25 (bốn ca do runner) |
| 2 | An toàn | Đối kháng trên RC | 100% đạt: 0 gợi ý vi phạm luật lọt ra, 0 lượt ghi không có token, 0 rò dữ liệu người khác, 0 PII trong câu trả lời và bộ nhớ (NFR-20, 22, 25, 26, 33) | như trên | 42/42 ở v25 |
| 3 | Độ đúng | Router diễn đạt lại | Từ 17/18 | `evals/paraphrase/run_router.py` | 18/18 |
| 4 | F6 | OCR ảnh thật (tiêu chí 3 phase 5) | Đủ 4 trường từ 90% trên ảnh đọc được, đo ở lượt RC | `scripts/eval_ingest.py --set real` | 9/11 ở v25; r08 đạt ở v26 nên dự kiến 10/11 |
| 5 | Độ trễ | Event đầu (NFR-01) | Phiên ấm < 1,5 s; phiên lạnh ≤ 3 s nếu chủ dự án nới (Q2) | `scripts/measure_latency.py`, 10 lượt mỗi loại | 0,34 s / 2,04 s |
| 6 | Độ trễ | Kiểm tra trước khi chi (NFR-02) | p95 < 2 s | `scripts/measure_phase3.py` hoặc integration test | 328 ms |
| 7 | Độ trễ | What-if (NFR-03) | Theo Q1. Đề xuất: khối số liệu đầu tiên p95 ≤ 8 s, trọn câu p95 ≤ 20 s, ghi rõ trọn câu chưa đạt 8 s của proposal kèm phân rã thời gian | `step_timings` trong `audit_events` của lượt RC | khối đầu p95 18,2 s, trọn câu p95 28,2 s: **chưa đạt** |
| 8 | Chi phí | Chi phí mỗi lượt (NFR-37, KPI §6, E-04) | Có số trung bình và p95 theo từng ý định. Ngưỡng cảnh báo đề xuất: what-if ≤ 2.500 ₫, lượt tra cứu ≤ 300 ₫ | `audit_events` (token, chi phí ước tính), bảng `yofina-usage`, Cost Explorer | chỉ có một lượt what-if (1.578 ₫) |
| 9 | Độ bền | Tỷ lệ lỗi tool | < 1% lần gọi tool có `status: error` trong lượt RC (không tính `denied` của ca đối kháng); 0 `verifier_fallback`; 0 `turn_persist_timeout` | `/ops/summary`, log Runtime | `turn_persist_timeout` có ở mọi ca eval |
| 10 | Giải thích | Trace 100% lượt (NFR-31) | Số lượt của runner bằng số dòng `audit_events` của lượt RC | đếm `audit_events` theo khoảng giờ chạy | chưa đếm; bị `turn_persist_timeout` đe dọa |
| 11 | Độ bền | Ép lỗi (NFR-15, 17) | Bốn bài: model bị chặn (trần về 0 qua SSM), tool quá thời gian, Gateway từ chối, luồng SSE đứt. Mỗi bài ra thẻ số liệu hoặc thông báo rõ, không màn trắng, không treo | test tay + `tests/integration/` | đã có ở phase 3 (trần về 0), chưa làm lại trên v26 |
| 12 | Bảo mật | Rà cấu hình (NFR-21, 23, 24) | IAM không có `*` thừa ở hành động và tài nguyên (ngoại lệ ghi lý do); quét repo và lịch sử git không ra account ID, ARN có account, khóa, mật khẩu, email; Gateway `ENFORCE`; mọi bảng có `user_id` bật RLS `FORCE`; S3 chặn public | mục B | chưa làm |
| 13 | Quyền riêng tư | Xóa và công bố (NFR-28, 29, 30) | "Xóa dữ liệu của tôi" < 1 phút; màn Giới thiệu và README nói model có thể xử lý ngoài Singapore; 100% câu trả lời có nhãn AI | test tay, soát giao diện | xóa 991 ms; công bố và nhãn chưa soát |
| 14 | Dự báo (K5) | Báo trước khi hũ cạn | Trung vị số ngày báo trước và tỷ lệ báo đúng trên 3 persona có trong báo cáo (mục tiêu K5: ≥ 7 ngày, ≥ 70%) | backtest chạy máy, không gọi model | chưa đo |
| 15 | Demo | Tổng duyệt | 6 cảnh, 3 lần liên tiếp, mỗi lần ≤ 3 phút 30 giây, tài khoản vừa đặt lại, không lỗi; chủ dự án chạy được một lần trên Safari iPhone [giữ] | bấm giờ, ảnh chụp | chưa đi trên giao diện mới |
| 16 | Trình bày | Bộ nộp bài | README giám khảo, sơ đồ, video ≤ 3 phút, slide outline, demo-runbook, tài liệu chi phí có trong repo (video ở link ngoài nếu Q13 chọn vậy); tài liệu trạng thái (HANDOFF, requirements, AC, open-questions, aws-resources) khớp bản RC | soát | chưa làm |
| 17 | Vận hành | Sẵn sàng buổi chấm (NFR-18, 43) | Checklist trước giờ chạy xanh; 3 phiên song song không lỗi; mật khẩu demo đã đổi; tài nguyên khớp `aws-resources.md`; chi phí thực đã ghi | mục J | chưa làm |

## 3. Phạm vi

**Làm**: đóng phase 5, cứng hóa, việc để sau có hiện trên demo, đợt 5 của kiểm toán prompt, một lượt eval cuối, đo NFR, tài liệu nộp, video, vận hành buổi chấm.

**Cắt hoặc hoãn** [cắt 24/11, chờ duyệt ở mục 7]:

| Mục trong bản 21/11 | Đề xuất | Lý do |
|---|---|---|
| Step Functions `yofina-weekly` (backtest, hiệu chỉnh ACI, eval rút gọn hằng tuần) | Cắt (Q11). Thay bằng backtest chạy tay trên máy cho báo cáo K5 | Không nằm trên đường demo nào; eval hằng tuần tốn tiền model mà không ai đọc trong thời gian chấm |
| Đồng bộ kho tri thức | Bỏ | RAG đã cắt 24/11 |
| AgentCore Evaluations online | Cắt | Tốn tiền theo lượt chấm; màn trace tự làm và evaluator bằng code đã đủ |
| Viết bộ eval tới 50 golden + 50 đối kháng | Golden giữ 60. Đối kháng thêm 8 ca để đủ 50 như KPI proposal §6 (Q10) | Golden đã vượt 50 |
| Đo độ trễ 30 lượt mỗi loại từ trình duyệt | Lấy độ trễ phía server từ lượt RC; trình duyệt chỉ đo event đầu (10 lượt mỗi loại) | Mỗi lượt what-if tốn khoảng $0,06; 30 lượt mỗi loại là thêm vài USD mà không thêm thông tin |
| Giao diện tối theo frame Figma | Chỉ soát các màn đã có chế độ tối, không làm frame mới | Đã có chế độ tối từ đợt UI round 1 |
| WAF (proposal §8) | Không thêm, ghi lệch | Có phí theo tháng; JWT, throttle của HTTP API, trần lượt gọi và trần theo người dùng (B4) đủ cho bản demo |
| Kiểm toán prompt đợt 7, 8 | Hoãn tới sau cuộc thi (Q7) | Xem mục F |

## 4. Các luồng việc

Mỗi luồng sở hữu một tập file riêng để chạy song song; mỗi việc một worker trong worktree `C:\moMo-wt\p6-<việc>`, nhánh `p6/<việc>`, chỉ chạy unit test trong lúc làm. Người điều phối review, merge, chạy unit cả bộ. **Một luồng deploy tại một thời điểm**, gom theo ba đợt (mục 8): đợt 1 ngày 28/11, đợt 2 ngày 2/12, RC ngày 4/12. Sau mỗi đợt deploy chỉ chạy vài ca `--only` của phần vừa đổi, mỗi ca một lần. [mới 24/11]

Chỗ hai luồng chạm cùng file: `agent/src/yofina_agent/turn.py` (C1 sửa phần ghi lượt, D2 sửa phần what-if, E3 sửa đọc số), `router.py` (E3, E4, F1). Gom E3, E4, F1 cho cùng một worker `p6-agent-polish`; C1 và D2 sửa khác hàm, người điều phối gỡ xung đột khi merge.

Ước công tính bằng giờ làm của một worker hoặc một người, chưa gồm thời gian deploy.

### Luồng A — Đóng phase 5 [mới 24/11]

| ID | Việc | File / khu vực | Đầu ra | Cách kiểm | Ước công |
|---|---|---|---|---|---|
| A1 | Học đi lại 6 cảnh trên giao diện mới với `giamkhao1` vừa đặt lại, bấm giờ từng cảnh; làm luôn việc 2–5 của HANDOFF mục B (chứng từ ngoại tệ, hỏi tỷ giá, bộ nhớ hai phiên, biểu đồ chi tiêu) | app trên Amplify; ghi vào mục "Kiểm sau" của file phase 5 | Bảng đạt/lỗi kèm ảnh và giờ; danh sách chỗ khó tìm, chữ dài, thông tin lặp | Người điều phối đọc bảng và tự đi lại cảnh có lỗi | 3 |
| A2 | Sửa lỗi chặn cảnh do A1 tìm ra (nếu có) | theo lỗi | Nhánh sửa, vào đợt deploy 1 | Đi lại đúng cảnh đó | 2–6 |
| A3 | Bộ nhớ `memory-state-preference`: đo 3 lượt `IngestData` trực tiếp (không qua eval) với câu có sở thích kèm "tháng này"; nếu vẫn mất chữ thời hạn hoặc sự thật chép nguyên câu thì làm theo Q8 (đổi model trích xuất của `facts_vi`, hoặc override bước hợp nhất P1-6) | `infra-cdk/lib/memory.ts`, `agent/src/yofina_agent/memory.py`, script tạm ngoài repo | Bảng 3 lượt trước và sau; Memory cập nhật tại chỗ, giữ id | Ca `memory-state-preference` `--only` một lần sau đợt deploy 1 | 4 |
| A4 | Chốt tiêu chí 3 OCR theo Q9: ghi r12 (ảnh mờ) là giới hạn đã biết, số chính thức lấy ở lượt RC | file phase 5 | Dòng tiêu chí 3 có quyết định | — | 0,5 |
| A5 | Điền bảng đóng phase 5 (10 tiêu chí), tick open-questions, ghi HANDOFF | `docs/plan/phases/phase-5-*.md`, HANDOFF | Phase 5 đóng | Người điều phối soát | 1 |

### Luồng B — Bảo mật [đổi 24/11, gộp từ luồng C cũ]

| ID | Việc | File / khu vực | Đầu ra | Cách kiểm | Ước công |
|---|---|---|---|---|---|
| B1 | Rà IAM tối thiểu: đọc template sau `cdk synth` của bảy stack, liệt kê mọi statement có `*` ở `Action` hoặc `Resource`; chạy IAM Access Analyzer `ValidatePolicy` (API chỉ đọc, không cần tạo analyzer) trên từng policy; sửa chỗ thừa, chỗ nào phải giữ `*` (X-Ray, `PutMetricData`, log) thì ghi lý do | `infra-cdk/lib/*.ts`, `docs/research/security-review.md` (mới) | Bảng role → quyền → lý do; diff CDK chỉ thu hẹp quyền | `cdk diff` không có replace; unit CDK; gọi lại vài ca `--only` sau deploy | 4 |
| B2 | Quét bí mật: script quét cây làm việc và `git log -p` tìm dãy 12 chữ số dạng account ID, `arn:aws:` có account, `AKIA`, `aws_secret`, mẫu mật khẩu, email; chạy trước mỗi commit nộp bài. Báo cáo kết quả lịch sử git cho Q5 | `scripts/scan_repo.py` (mới), `tests/unit/` | Danh sách phát hiện (không in giá trị, chỉ file và dòng) | Chạy trên `main`; thêm một chuỗi giả vào test để chắc script bắt được | 3 |
| B3 | CORS: HTTP API bỏ `http://localhost:5173` khỏi bản deploy cuối (chuyển vào context dev `extraCorsOrigins`); bucket nạp chỉ cho origin Amplify; ghi rằng Runtime trả `Access-Control-Allow-Origin: *` (AgentCore quản, lượt gọi vẫn cần JWT) | `infra-cdk/lib/tools-stack.ts`, `ingest-stack.ts`, `infra-cdk/README.md` | Diff CORS; ghi chú ở security-review | `curl` preflight từ origin lạ bị từ chối ở HTTP API và S3 | 1,5 |
| B4 | Giới hạn theo người dùng: trần lượt chat mỗi tài khoản mỗi ngày và trần lượt nạp tệp mỗi ngày (đếm ở `yofina-usage` với khóa riêng theo băm `sub`); chạm trần thì báo rõ và vẫn cho xem số liệu. Throttle riêng cho route nặng (`POST /demo/reset`, `POST /ingest/uploads`). Số trần trong SSM/cấu hình (Q6) | `agent/src/yofina_agent/quota.py` (mới, một dòng gọi ở `turn.py`), `pipelines/ingest/`, `infra-cdk/lib/tools-stack.ts` | Một tài khoản không làm cạn trần chung 400 lượt Sonnet của mọi người | Unit test; integration: đặt trần 2 cho tài khoản thử, lượt thứ 3 nhận thông báo | 4 |
| B5 | Guardrail lỗi phải có người thấy: metric và alarm `guardrail_error` về SNS (giữ fail-open theo Q3) | `agent/src/yofina_agent/` (log EMF), `infra-cdk/lib/agent-stack.ts` | Alarm `yofina-guardrail-error` | Ép lỗi bằng guardrail id sai trên tài khoản thử, alarm chuyển `ALARM` | 2 |
| B6 | Test cấu hình chạy tay (không vào CI vì cần AWS): Gateway có interceptor và policy engine `ENFORCE`; mọi bảng `public` có `user_id` bật RLS `ENABLE` + `FORCE`; Lambda tool không đọc được secret master; hai bucket chặn public; Cognito tắt tự đăng ký | `tests/config/` (mới) | Test đỏ khi cấu hình lệch | Chạy một lần sau RC, ghi kết quả | 3 |
| B7 | Đọc lại mã theo checklist bảo mật (nhập liệu ở biên tin cậy, SQL có tham số, nội dung tệp chỉ là dữ liệu, không log PII), ghi phát hiện mức cao/vừa/thấp; mức cao sửa trước đợt 2 | toàn repo, `docs/research/security-review.md` | Bảng phát hiện và trạng thái | Người điều phối duyệt từng phát hiện mức cao | 4 |

### Luồng C — Lỗi và độ bền [đổi 24/11]

| ID | Việc | File / khu vực | Đầu ra | Cách kiểm | Ước công |
|---|---|---|---|---|---|
| C1 | `turn_persist_timeout`: ghi thời lượng từng việc ghi (lưu hội thoại qua `save_turn`, bản ghi lượt qua `audit___record_turn`) vào log; đọc log Runtime và `yofina-ledger` của lượt v25–v26 để tìm việc nào quá 3 giây (`turn_blocks_timeout_seconds`, `turn_record_timeout_seconds`); sửa nguyên nhân (gọi Gateway lạnh, Aurora, hay chờ tuần tự), không chỉ nâng timeout. Bản ghi lượt hỏng thì thử lại một lần trong nền | `agent/src/yofina_agent/turn.py` (hàm ghi lượt), `defaults.json` | 0 `turn_persist_timeout` trên 5 lượt thử; NFR-31 không bị hở | Log Runtime sau đợt 1; đếm `audit_events` khớp số lượt | 4 |
| C2 | Aurora ngủ: lời gọi đầu khi cụm vừa thức gặp `DatabaseResumingException` hoặc `57P01` (lần 500 ở `/demo/reset`, lần 503 hết giờ 30 giây khi seed). Thêm `57P01` vào nhóm lỗi tạm thời được retry có giãn nhịp trong client Data API; frontend hiện "đang khởi động, thử lại" thay vì lỗi chung khi gặp 503 | `libs/yofina_core/src/yofina_core/` (client DB), `frontend/` (trạng thái lỗi) | Lời gọi đầu sau khi ngủ thành công hoặc báo rõ | Unit test với lỗi giả; để Aurora ngủ (min 0) rồi gọi `/overview` và `/demo/reset` | 3 |
| C3 | Throttling và chạy song song: 3 tài khoản chat cùng lúc (mỗi phiên một microVM, bộ giới hạn tốc độ nằm trong từng tiến trình nên không chia chung quota 10 request/phút của Claude). Đọc `InvocationThrottles` của `AWS/Bedrock` và log fallback; nếu throttle làm hỏng lượt thì giảm `rpm` mỗi phiên hoặc rẽ sớm sang Kimi K3 | `libs/yofina_core/src/yofina_core/llm_defaults.json`, script tạm | Bảng: số lượt, số throttle, số lượt rẽ dự phòng, lượt nào hỏng | 3 phiên × 3 lượt (khoảng $0,5), một lần | 3 |
| C4 | Ép lỗi trên RC (tiêu chí 11): trần model về 0 qua SSM `/yofina/llm/*` rồi trả lại; tool quá thời gian (biến môi trường timeout thấp trên tài khoản thử); Gateway từ chối (gọi tool với `user_id` người khác); SSE đứt (ngắt mạng giữa lượt trên trình duyệt) | SSM (ghi, hỏi trước), trình duyệt | Bảng bài thử → kết quả trên màn hình | Chụp màn hình từng bài | 3 |
| C5 | Xác nhận sau RC: bốn DLQ 0 tin, `FailedExtraction` của Memory 0, log Lambda 0 `ERROR` trong giờ chạy eval | CloudWatch (chỉ đọc) | Dòng trong eval-report | — | 0,5 |

### Luồng D — Hiệu năng [đổi 24/11]

| ID | Việc | File / khu vực | Đầu ra | Cách kiểm | Ước công |
|---|---|---|---|---|---|
| D1 | Phân rã độ trễ what-if và lộ trình từ `step_timings` của các lượt đã chạy (không gọi model mới): router, guardrail vào/ra, từng tool, analyst, verifier, composer, khoảng trống không thuộc bước nào (phase 3 thấy khoảng 5 s, nghi bộ giới hạn tốc độ) | `scripts/measure_latency.py` (thêm chế độ đọc `/ops/traces`), `docs/research/latency-breakdown.md` (mới) | Bảng p50/p95 từng bước; chỗ chiếm nhiều nhất | Số khớp `/ops/traces/{id}` | 3 |
| D2 | Giảm độ trễ theo D1, ưu tiên: (a) khoảng chờ của bộ giới hạn tốc độ khi lượt chỉ có 3–4 lời gọi; (b) vòng sửa của Verifier do `source_jar_covers` (5 lần trong lượt eval v25, mỗi lần thêm một lượt Analyst khoảng 8–10 s): đưa số dư hũ nguồn vào ngữ cảnh Analyst trước khi đề xuất để ít phải sửa; (c) phát khối `forecast_timeline` và thẻ số liệu ngay khi tool trả, trước lời Analyst; (d) làm nóng phiên Runtime khi mở màn chat (NFR-01). Không cắt luật an toàn | `agent/src/yofina_agent/whatif.py`, `libs/yofina_core/src/yofina_core/llm.py`, `frontend/` (làm nóng) | Độ trễ what-if giảm, đo lại 3 lượt (khoảng $0,2) | `--only whatif-bnpl whatif-bnpl2` sau đợt 2 | 8 |
| D3 | Guardrail p50 446 ms (> 400 ms): theo Q3. Nếu giữ lọc đầu ra thì ghi lệch; nếu đổi thì chỉ bỏ lọc đầu ra cho đoạn chữ đã qua `NumericGrounding` và luật suitability, giữ lọc đầu vào | `agent/src/yofina_agent/` (guardrail) | Quyết định ghi trong file này | Adversarial phase 3 `--only` các ca chủ đề cấm | 1–2 |
| D4 | `GET /cashflow`: phần tách khoản cố định và Trả sau đang cộng bằng mã với khoảng 10 truy vấn; chuyển thành một hàm SQL bằng migration `0055` | `db/migrations/0055_*.sql`, `gateway/tools/ledger/yofina_ledger/` (cashflow) | Một lời gọi Data API; số không đổi | local_pg so số trước và sau trên `minh`; đo p95 từ Lambda | 3 |
| D5 | Kích thước bundle frontend: tách chunk biểu đồ và chat nếu bundle chính > 500 KB nén; ghi số [giữ] | `frontend/vite.config.*` | Số trước và sau | `npm.cmd run build` | 1,5 |

### Luồng E — Việc để sau của phase 4–5 đáng làm trước demo [mới 24/11]

Chọn theo một câu hỏi: lỗi có hiện trên 6 cảnh hoặc trên thao tác giám khảo dễ thử không.

| ID | Việc | Có hiện trên demo | File / khu vực | Đầu ra | Cách kiểm | Ước công |
|---|---|---|---|---|---|---|
| E1 | Màn So với bản cũ (L3) ghi "Loại bước", "Giai đoạn" bằng mã thô (`set_aside`, `phase_id`) | Cảnh 4 | `gateway/tools/ledger/yofina_ledger/roadmap_logic.py` | Nhãn tiếng Việt | Unit; mở màn trên Amplify | 1,5 |
| E2 | Lambda sinh lại lộ trình bỏ bản đề xuất đang chờ mà không nói gì: ghi lý do vào bản mới | Cảnh 4 (dải "Có phiên bản mới") | `pipelines/roadmap/` | Bản mới có lý do "thay bản đề xuất trước" | Unit | 2 |
| E3 | Bộ đọc số `router._code_params` đọc "1200 USD" thành 1.200 ₫ khi router không trích `currency`; agent chưa truyền `date` cho `get_exchange_rate` | Giám khảo dễ thử câu ngoại tệ | `agent/src/yofina_agent/router.py`, nơi gọi tool tỷ giá | Số ngoại tệ không bao giờ thành VND thô; tỷ giá theo ngày mô phỏng | Unit; `--only` một câu tỷ giá | 2 |
| E4 | Tiện ích ngày chưa đọc "trong 6 tháng"; luật dự phòng không nhận hũ tên chứa "mua" ("Mua xe") | Câu what-if mục tiêu | `router.py`, tiện ích ngày, luật dự phòng | Hai ca unit mới | Unit | 2 |
| E5 | `period_end` của lộ trình theo ngày hôm nay thay vì ngày lương | Cảnh 4 (kỳ của lộ trình) | agent lộ trình, tool hồ sơ | Kỳ lộ trình khớp kỳ lương | Unit; golden lộ trình `--only` một ca | 3 |
| E6 | Ghi chú duyệt nhãn của 25 ảnh thật bị hỏng dấu (`?`) từ commit a70b9a3 | Không (tài liệu dữ liệu) | `evals/ingest/manifest.json` | Ghi chú đọc được | `--check-manifest` | 1 |
| E7 | Tỷ lệ phải hỏi khi phân loại 17,4% (NFR-14 < 10%): thử hai hướng đã ghi ở phase 4 (bỏ token mẫu QR khỏi chuỗi embedding; giảm trọng số lịch sử khi ghi chú rõ) trên bộ `evals/classification` | Không trực tiếp; là một NFR chưa đạt trong bảng | `pipelines/classify/`, `evals/classification/` | Số mới; nếu không xuống dưới 10% thì ghi lệch | `run_eval.py` (gọi embedding, chi phí nhỏ) | 4, làm nếu còn thời gian |
| E8 | `numeric_ungrounded` 2 lần ở v25 (câu bị bỏ, ca vẫn đạt) | Không | — | Theo dõi ở lượt RC, không sửa trước | log RC | 0 |
| — | **Để sau cuộc thi**: bộ nhớ vào bước lập lộ trình, học từ `feedback` (P1-5), P2 của nghiên cứu bộ nhớ, Transaction Search (Q4) | Ngoài 6 cảnh | — | — | — | — |

### Luồng F — Kiểm toán prompt đợt 5, 7, 8 [mới 24/11]

Nguồn: [prompt-overfit-audit.md](../../research/prompt-overfit-audit.md) mục 2.3, 2.4, 2.6 và bảng mục 5.

| ID | Đợt | Đề xuất | Lý do | File | Cách kiểm | Ước công |
|---|---|---|---|---|---|---|
| F1 | 5 (P17, P18): bỏ câu router.py:80-81 lặp ý luật ghép câu cụt; đo rồi quyết giữ hay bỏ `spending_confirm_request`; bỏ luật chữ hoa của mô phỏng gộp | **Làm**, trong đợt 1 | Nhỏ (bỏ 5–40 dòng), đúng nguyên tắc "không vá cho vừa ca"; ca đo đã có (`multiturn-new-question`) | `router.py`, `turn.py`, `notices.py`, `whatif.py` | `--only multiturn-new-question` + 18 câu diễn đạt lại (router, rẻ) | 2 |
| F2 | 7 (P15, P11b, P27): chip mang `id` và ý định có cấu trúc | **Hoãn** tới sau cuộc thi (Q7) | Đụng hợp đồng khối `clarify`/`suggestions` và frontend; chip "Mất việc 2 tháng" là đường của cảnh 3, đổi trước demo là rủi ro lớn hơn lợi ích; hành vi hiện tại đúng | — | — | — |
| F3 | 8 (P24, P23): writer viết các câu đang dựng bằng mã; gom hàm dựng nhãn phương án | **Không làm** trước demo | P24 thêm lượt gọi model, ngược với NFR độ trễ và chi phí (tiêu chí 7, 8); P23 tác giả kiểm toán ghi "không gấp" | — | — | — |

### Luồng G — Giao diện và tổng duyệt [đổi 24/11, từ luồng D cũ]

| ID | Việc | File / khu vực | Đầu ra | Cách kiểm | Ước công |
|---|---|---|---|---|---|
| G1 | Sửa các ghi nhận của A1 về chữ dài, thông tin lặp, chỗ khó tìm (theo luật §9, §10 ở [ui-design-review.md](../../research/ui-design-review.md)) | `frontend/` | Nhánh `p6/ui` vào đợt 1 hoặc 2 | vitest; đi lại màn bị sửa | 4–8 |
| G2 | Soát: không còn chữ "MoMo", "Ví Trả Sau", "FinHealth" trên giao diện; mọi màn có nhãn "Ví mô phỏng · ngày mô phỏng"; câu trả lời của trợ lý có nhãn AI (NFR-30); màn Giới thiệu/Quyền riêng tư nói model có thể xử lý ngoài Singapore (NFR-29) [giữ, thêm NFR-29] | `frontend/` | Danh sách soát | `grep` trên `frontend/src` và đi app | 2 |
| G3 | A11y tối thiểu: tương phản chữ AA ở chế độ sáng, vùng chạm ≥ 44 px, nhãn cho nút biểu tượng, `prefers-reduced-motion` tắt chuyển động cảnh 1–4 [giữ] | `frontend/` | Danh sách sửa | Công cụ đo tương phản; vitest | 3 |
| G4 | Điện thoại thật: chủ dự án mở app trên Safari iPhone một lần (bàn phím che ô nhập, vuốt sheet, vùng an toàn) [giữ] | — | Ghi nhận lỗi | Chủ dự án | 1 |
| G5 | Tổng duyệt: 6 cảnh, 3 lần liên tiếp, bấm giờ; chụp ảnh từng cảnh vào `docs/plan/assets/demo/` làm slide và làm phương án dự phòng [giữ] | — | Bảng giờ, ảnh | Tiêu chí 15 | 3 |

### Luồng H — Đánh giá cuối

Chi tiết ở mục 5. Sở hữu `evals/`, `scripts/measure_*`, `docs/research/eval-report.md`, `docs/research/backtest-final.md`.

| ID | Việc | File | Đầu ra | Ước công |
|---|---|---|---|---|
| H1 | Thêm 8 ca đối kháng cho đủ 50 nếu Q10 đồng ý: chọn nhóm còn mỏng (moi system prompt, đòi dữ liệu người khác qua chat, chèn chỉ dẫn qua câu nói để đầu độc bộ nhớ, ép ghi qua câu giả làm chip, khuyên vay để tiêu, ngoại tệ đổi số) | `evals/adversarial/phase6.jsonl` (mới) | 8 ca, chưa chạy tới RC | 2 |
| H2 | Báo cáo backtest K5 chạy trên máy (không gọi model): số ngày báo trước và tỷ lệ báo đúng trên 3 persona, định nghĩa "đúng" theo E-02 (±3 ngày); pinball so với seasonal naive và độ phủ khoảng 80% lấy lại từ [backtest-phase-2.md](../../research/backtest-phase-2.md) | `scripts/ml_backtest.py` (thêm chỉ số), `docs/research/backtest-final.md` | Báo cáo | 4 |
| H3 | Script tổng hợp sau lượt RC: đọc `audit_events` (qua `/ops/traces`), `/ops/summary`, `yofina-usage`, log Runtime, ra bảng độ trễ, chi phí, lỗi theo ý định | `scripts/eval_summary.py` (mới) | Bảng cho eval-report | 3 |
| H4 | Chạy lượt RC và viết `docs/research/eval-report.md` | `evals/`, docs | Báo cáo | 4 (gồm thời gian chạy) |

### Luồng I — Đóng gói nộp bài [đổi 24/11, từ luồng E cũ]

| ID | Việc | File / khu vực | Đầu ra | Cách kiểm | Ước công |
|---|---|---|---|---|---|
| I1 | README cho giám khảo: sản phẩm làm gì (3 câu), link app, cách nhận tài khoản (trong form nộp bài, không ghi mật khẩu), 6 cảnh kèm thao tác bấm, thứ thật và thứ mô phỏng (ví mô phỏng, ngày mô phỏng 21/11, Trả sau mô phỏng), số đo chính (tiêu chí 1–10), thiết kế an toàn (token xác nhận, Cedar, RLS, Guardrail, luật suitability), giới hạn đã biết, cách deploy lại, sơ đồ thư mục | `README.md` | README mới | Một người chưa đọc repo làm theo được cảnh 1–3 | 4 |
| I2 | Sơ đồ kiến trúc theo bản đang chạy (không SageMaker, không Knowledge Bases/OpenSearch, không WAF, không batch tuần; có Memory override, ingest, classify, roadmap-regen): Mermaid trong repo cho GitHub, bản ảnh cho slide; cập nhật [overview.md](../../architecture/overview.md) (nhãn [đề xuất] thành [đã chạy] chỗ đã làm, ghi lệch cuối) | `docs/architecture/overview.md`, `docs/architecture/diagram.md` (mới) | Sơ đồ ba nhịp và harness L0–L5 | So từng hộp với `aws-resources.md` | 4 |
| I3 | Video demo ≤ 3 phút: quay màn hình app thật 6 cảnh sau RC (khổ 390×844, tài khoản vừa đặt lại); đưa đoạn quay vào ô `demoClip` của dự án Remotion; soát số trong phần dựng mở đầu khớp số engine của `minh` (hũ Ăn uống cạn 23/11, lương 05/12); dựng bản cuối. Remotion miễn phí cho cá nhân và công ty tới 3 người ([License & Pricing](https://www.remotion.dev/docs/license/pricing.md)) | `C:\moMo\video` (theo Q13), `docs/plan/demo-script.md` | mp4 cuối, link | Xem hết một lần, bấm giờ | 6 |
| I4 | Kịch bản thuyết trình và dàn ý slide 10 trang với số đo thật (K2, K5, K4 kèm RCT, K9 dạng hòa vốn theo E-03; xung đột phí chậm trả theo F-02) | `docs/plan/pitch-script.md`, `docs/plan/slide-outline.md` (mới) | Dàn ý, lời nói theo thời lượng | Chủ dự án duyệt | 4 |
| I5 | Tài liệu chi phí AWS: chi phí thực theo dịch vụ từ Cost Explorer (lọc tag `project=yofina`, có ghi phí ngoài tag như Bedrock nếu không gắn tag được); chi phí mỗi lượt theo ý định (tiêu chí 8); chi phí một lượt eval; dự phóng theo người dùng theo [ba/08 mục 4](../../ba/08-kpi-kinh-doanh.md#4-dự-phóng-chi-phí-vận-hành) và chi phí theo gói ở [ba/06 mục 5.1](../../ba/06-mo-hinh-kinh-doanh.md#51-chi-phí-theo-từng-tính-năng) | `docs/research/cost-report.md` (mới) | Báo cáo, cho phép chốt K6, K7 (E-04) | Số khớp Cost Explorer ngày chốt | 3 |
| I6 | Đồng bộ tài liệu trạng thái: cột trạng thái [requirements.md](../../requirements/requirements.md), trạng thái AC ở [ba/05](../../ba/05-acceptance-criteria.md) và NFR ở [ba/04](../../ba/04-non-functional-requirements.md), tick [open-questions.md](../../requirements/open-questions.md), đối chiếu [aws-resources.md](../../aws-resources.md) với tài khoản (liệt kê theo tag, chỉ đọc) | các file trên | Tài liệu khớp RC | `grep` trạng thái cũ | 3 |
| I7 | `docs/plan/demo-runbook.md`: thao tác bấm cho video và cho buổi chấm, việc trước khi quay, phương án khi lỗi (mục J); `docs/plan/teardown.md`: thứ tự hủy stack sau cuộc thi (không chạy) [giữ] | docs | Hai file | Người điều phối đọc khô | 2 |

### Luồng J — Vận hành buổi demo [mới 24/11]

| ID | Việc | File / khu vực | Đầu ra | Cách kiểm | Ước công |
|---|---|---|---|---|---|
| J1 | Script kiểm trước giờ, chỉ đọc trừ bước đặt lại: Runtime `READY`, sáu target Gateway `READY`, Aurora `available` và min ACU, HTTP API trả 200 ở `/overview` cho từng tài khoản demo, bốn DLQ 0, `yofina-usage` hôm nay còn bao nhiêu so với trần, alarm không `ALARM`; rồi đặt lại 6 tài khoản và mở một lượt chat ngắn để làm nóng | `scripts/preflight.py` (mới) | Một bảng xanh/đỏ | Chạy trước tổng duyệt và trước giờ chấm | 3 |
| J2 | Đổi mật khẩu 6 tài khoản demo (đã lộ trong lịch sử chat 23/11): sinh mới, cập nhật secret `yofina-demo-accounts` và Cognito; gửi giám khảo qua kênh nộp bài, không vào repo (Q12) | `scripts/create_demo_users.py` (nếu cần cờ đổi mật khẩu) | Mật khẩu mới | Đăng nhập thử từng tài khoản | 1 |
| J3 | Aurora 0,5 ACU trong khung chấm: `uv run scripts/cdk.py deploy YofinaData --require-approval never -c dbMinAcu=0.5`, hết khung thì trả về `-c dbMinAcu=0` (Q12) | `YofinaData` | Aurora không ngủ | `describe-db-clusters` | 0,5 |
| J4 | Phương án khi Bedrock throttle hoặc chạm trần: (1) chuỗi dự phòng Sonnet → Kimi K3 và thẻ số liệu tất định đã có, ghi vào runbook để người trình bày biết màn hình sẽ trông thế nào; (2) không chạy eval trong ngày chấm; (3) trần ngày đã kiểm ở J1, có lệnh nâng trần tạm qua SSM `/yofina/llm/*` (ghi, cần chủ dự án) kèm ghi lại; (4) tài khoản dự phòng `giamkhao2`, `giamkhao3`; (5) video quay sẵn và ảnh từng cảnh của G5 khi mạng hoặc dịch vụ hỏng | `docs/plan/demo-runbook.md` | Mục "Khi có sự cố" | Diễn tập một lần ở 8/12 với trần Sonnet về 0 trên tài khoản thử | 2 |
| J5 | Theo dõi trong khung chấm: dashboard `yofina-ops`, alarm về SNS `yofina-alerts`, người trực đọc `/ops/summary` mỗi ngày | — | Ghi chú mỗi ngày | — | 0,5/ngày |

### Luồng K — Agent như người tư vấn: lập luận hiện dần và kết luận có chính kiến [mới 24/11, chủ dự án duyệt]

Lý do: người dùng hiện thấy chủ yếu thẻ (artifact) và dòng tiến độ gọi tool; phần suy luận của agent (Analyst cân phương án, Verifier chặn, sửa lại; planner chọn bước lộ trình; cá nhân hóa theo bộ nhớ và hồ sơ hành vi) không lộ ra, nên trải nghiệm giống đọc báo cáo hơn là nói chuyện với người tư vấn. Chủ dự án muốn hiện được lập luận. Nguyên tắc giữ nguyên: số chỉ từ dữ liệu, mọi con số trong lập luận qua NumericGrounding; KHÔNG hiện suy nghĩ thô của model (chuỗi suy nghĩ nội bộ), chỉ hiện lập luận có cấu trúc mà model trả về như dữ liệu; không câu mẫu, không vá cho ca eval; luật ít chữ (§9 ui-design-review).

| ID | Việc | File / khu vực | Đầu ra | Cách kiểm | Ước công |
|---|---|---|---|---|---|
| K1 | Lập luận có cấu trúc: Analyst (what-if, kiểm tra trước khi chi) và planner lộ trình trả thêm danh sách bước lập luận ngắn (điều đã thấy từ kết quả tool → vì sao → ảnh hưởng tới quyết định), mỗi bước trỏ tới tool/luật làm căn cứ; Verifier chặn bước có số không có căn cứ. Phát dần qua sự kiện AG-UI cùng dòng tiến độ tool đang có, không thêm lượt gọi model (lấy từ chính lời gọi Analyst/planner, cân nhắc tách hiện theo từng chặng của luồng mã) | `agent/src/yofina_agent/whatif.py`, `roadmap_agent.py`, `turn.py` (phát sự kiện), hợp đồng sự kiện/khối nếu cần (`contracts/`) | Lập luận 2–5 bước hiện dần trong lượt what-if, affordability, lộ trình | Unit với LLM giả; xem trực tiếp trên app; `--only` 2–3 ca what-if/lộ trình một lần | 8 |
| K2 | Kết luận có chính kiến, cá nhân hóa: một câu chốt nên làm gì và vì sao, dựa trên phương án đã kiểm, bộ nhớ (sở thích) và hồ sơ hành vi (ví dụ thói quen chi dồn đầu kỳ) khi liên quan; không nhắc điều người dùng chưa nói | Analyst/writer, `writer.py` (chỉ phần dữ liệu đưa vào), `behavior_profiles` qua tool có sẵn | Câu kết luận trên thẻ phương án/lộ trình | Như K1 | 4 |
| K3 | Giao diện: lập luận hiện dần như lời người tư vấn trong khung chat; khi có kết luận thì thu gọn thành "Xem cách mình cân nhắc" (Disclosure); tôn trọng giảm chuyển động; trình đọc màn hình đọc được | `frontend/src/chat/` | Khung chat mới | vitest; xem trên app | 4 |
| K4 | Gợi ý hỏi tiếp theo đúng tình huống (ví dụ hoãn thêm, đổi số tiền) dựng từ phương án và dữ liệu, không câu cố định | agent + chip chat | 1–3 gợi ý sau thẻ | Xem trên app | 3 (tùy chọn, làm nếu kịp) |

K làm song song với D2 (độ trễ what-if): lập luận hiện dần làm 20–30 giây chờ thành lúc đọc agent suy nghĩ, nhưng không thay việc giảm độ trễ thật. K1 chạm `turn.py` cùng C1, D2: người điều phối gỡ xung đột khi merge.

## 5. Kế hoạch đánh giá cuối

[đổi 24/11] Thay cho luồng A và một phần luồng C của bản 21/11.

### 5.1 Một lượt đầy đủ duy nhất ở RC

- **Khi nào**: 4/12, sau deploy RC, khi unit xanh và vài ca `--only` của đợt 2 đã đạt. Không chạy ngày chấm.
- **Gồm**: golden phase 3, 4, 5 (60 câu); đối kháng phase 3, 4, 5 cộng phase 6 nếu H1 làm (42 hoặc 50 ca); router diễn đạt lại (18 câu); OCR ảnh thật (25 mục). OCR bộ dựng (33 mục) chỉ chạy nếu luồng nào sửa `pipelines/ingest/` sau 24/11.
- **Chi phí**: khoảng $2,2–2,5 như lượt đo 24/11, cộng khoảng $0,2 nếu có 8 ca đối kháng mới. Trước khi chạy, đọc số lượt Sonnet của ngày 24/11 trong `yofina-usage` để ước số lượt của lượt RC; nếu vượt phần còn lại của trần 400 lượt Sonnet thì chia hai ngày (4/12 và 5/12), không nâng trần.
- **Điều kiện chạy**: Aurora 0,5 ACU trong giờ chạy (tránh nhiễu `57P01`); đặt lại `minh` trước mỗi bộ; xóa bộ nhớ `minh` trước golden và đối kháng phase 5; `--min-interval 25`; mỗi ca chạy một lần.
- **Sau lượt RC**: không có lượt đầy đủ thứ hai. Ca đỏ được phân loại (lỗi agent, lỗi runner, lỗi judge, biến thiên model). Lỗi chặn demo thì sửa, deploy, và chỉ chạy lại đúng các ca liên quan bằng `--only`, mỗi ca một lần. Lỗi không chặn demo thì ghi vào eval-report và "Giới hạn đã biết" của README.
- **Ngân sách model cả phase 6**: lượt RC khoảng $2,5; các lượt `--only` sau ba đợt deploy khoảng $2–3; C3 và D2 khoảng $0,7; tổng dưới $7, chưa kể Aurora.

### 5.2 Đo thêm ngoài golden và đối kháng

| Chỉ số | Cách lấy | Nguồn |
|---|---|---|
| Độ trễ phía server p50/p95 theo ý định (lookup, forecast, what_if, affordability, roadmap, stress, ingest, memory) và theo bước | Gom `step_timings` của mọi lượt trong khoảng giờ chạy RC | `audit_events` qua `/ops/traces/{id}`, `/ops/summary` |
| Độ trễ phía client của lượt what-if và lộ trình | Thời gian cả lượt runner đã ghi | `evals/results/*.jsonl` |
| Event đầu, phiên ấm và lạnh | 10 lượt mỗi loại bằng câu tra cứu (đường Nova 2 Lite, rẻ) | `scripts/measure_latency.py` |
| `POST /affordability` p95 | 10 lượt, phiên ấm | `scripts/measure_phase3.py` |
| Chi phí mỗi lượt theo ý định (trung bình, p95), số lượt gọi model mỗi lượt, token vào/ra | Từ bản ghi lượt; đối chiếu tổng với lượt gọi theo model trong ngày | `audit_events`, bảng `yofina-usage`, metric `InputTokenCount`, `OutputTokenCount` của `AWS/Bedrock` |
| Tỷ lệ lỗi tool, số lần luật chặn, lượt gọi model so với trần | Một lần gọi sau RC | `/ops/summary` |
| `verifier_retry`, `verifier_fallback`, `numeric_ungrounded`, `turn_persist_timeout`, `guardrail_error` | Logs Insights trên log group Runtime trong giờ chạy | CloudWatch Logs |
| Throttle của Bedrock | `InvocationThrottles` theo `ModelId` trong giờ chạy | CloudWatch `AWS/Bedrock` |
| DLQ, `FailedExtraction`, lỗi Lambda | Một lần đọc | CloudWatch |
| Trace 100% | Số lượt runner gửi so với số `audit_events` trong khoảng giờ chạy | `audit_events`, `evals/results/` |
| K5 (báo trước khi cạn) | Backtest trên máy (H2) | `scripts/ml_backtest.py` |
| Chi phí AWS thực | Cost Explorer theo dịch vụ, tag `project=yofina`, tới ngày chốt (mỗi lời gọi API Cost Explorer có phí nhỏ, gọi ít) | Cost Explorer |

### 5.3 Báo cáo

`docs/research/eval-report.md`: tỷ lệ đạt theo bộ và theo nhóm, từng ca trượt và nguyên nhân, bảng NFR "mục tiêu / đo được / ghi chú" (tiêu chí 5–10), chi phí lượt RC và chi phí mỗi lượt theo ý định. Số trong slide và README lấy từ báo cáo này, không lấy từ nơi khác.

## 6. Rủi ro

| Rủi ro | Mức | Cách xử lý |
|---|---|---|
| What-if trọn câu p95 28 s, xa mục tiêu 8 s; giám khảo thấy chậm ở cảnh 2 | Cao | D1–D2; khối số liệu hiện trước; Q1 chốt cách báo cáo trung thực |
| Một giám khảo dùng hết trần chung 400 lượt Sonnet/ngày, các giám khảo khác chỉ còn thẻ số liệu | Vừa | B4 (trần theo người dùng); J1 kiểm trần mỗi sáng |
| Bedrock throttle khi nhiều giám khảo dùng cùng lúc (Claude 10 request/phút, giới hạn tốc độ theo từng phiên) | Vừa | C3 đo trước; chuỗi dự phòng Kimi K3; J4 |
| Aurora ngủ hoặc vừa thức làm lời gọi đầu lỗi | Vừa | J3 (0,5 ACU trong khung chấm); C2 (retry `57P01`) |
| Sửa ở đợt 2 làm hỏng cảnh đã chạy, mà lượt eval đầy đủ chỉ có một | Vừa | Code freeze 3/12; đợt 2 chỉ gồm việc đã có ca `--only` đo được; tổng duyệt G5 sau RC |
| Bản ghi lượt mất do `turn_persist_timeout`, làm hở "100% lượt có trace" | Vừa | C1 trước đợt 1 |
| Bộ nhớ trích xuất lệch ngay trên sân khấu (mất "tháng này", sự thật chép nguyên câu) | Vừa | A3; kịch bản demo dùng câu đã đo ổn; màn Bộ nhớ của tôi cho xem và xóa |
| Lịch sử git public còn số tài khoản 8 chữ số từ ghi chú nhãn cũ | Vừa | Q5 |
| Mật khẩu demo đã lộ | Cao nếu không đổi | J2 trước khi gửi giám khảo |
| Video và slide làm dồn cuối | Vừa | Quay ngay sau RC (5/12), dựng 6/12, còn 4 ngày đệm |
| Một người đi cảnh (Học) bận, A1 trễ | Vừa | Người điều phối tự đi cảnh bằng trình duyệt nếu tới 26/11 chưa có kết quả |
| Hạn nộp hoặc định dạng nộp khác giả định | Vừa | Q14 hỏi sớm; lịch giữ 1 ngày đệm trước hạn |

## 7. Quyết định cần chủ dự án chốt

Hạn trả lời đề xuất: 26/11 cho Q1–Q9 (ảnh hưởng đợt 1), 2/12 cho phần còn lại.

**Đã chốt 24/11 (chủ dự án): Q1–Q9 theo đúng cột "Đề xuất".** Q10–Q15 còn chờ.

| # | Câu hỏi | Đề xuất |
|---|---|---|
| Q1 | NFR-03 (what-if p95 < 8 s) chưa đạt (trọn câu p95 28,2 s). Giữ chỉ tiêu và báo "chưa đạt", hay tách thành "khối số liệu đầu tiên p95 ≤ 8 s" và "trọn câu p95 ≤ 20 s"? | Tách hai chỉ tiêu. Proposal §12 đã mô tả "khối dòng thời gian hiện ở khoảng giây thứ 2, văn bản kết thúc trước giây thứ 8", tức điều người dùng cảm nhận là khối đến trước. Báo cáo ghi rõ cả hai số và phân rã D1 |
| Q2 | NFR-01: nới lượt đầu phiên lạnh lên 3 s? | Nới lên 3 s, cộng làm nóng phiên khi mở màn chat (D2d) |
| Q3 | Guardrail: chấp nhận p50 446 ms hay bỏ lọc đầu ra cho chữ đã qua `NumericGrounding` và luật suitability? Giữ fail-open hay đổi fail-closed? | Giữ lọc đầu ra (an toàn là phần giám khảo nhìn, 0,4 s nhỏ so với 16 s của lượt what-if); giữ fail-open để demo không gãy, thêm alarm B5 |
| Q4 | Bật CloudWatch Transaction Search? | Không bật. Màn trace đọc `audit_events` đã đủ cho cảnh 6; tránh đổi cấu hình mức tài khoản và phí span |
| Q5 | Viết lại lịch sử git để xóa số tài khoản cũ trong ghi chú nhãn? | Nếu số đó là của người thật (từ ảnh thật) thì viết lại một lần trước 3/12 (`git filter-repo`, force push, chủ dự án tự làm, các worktree phải tạo lại). Nếu là số mẫu thì để nguyên và ghi lý do. B2 báo đủ vị trí để quyết |
| Q6 | Thêm trần theo người dùng (B4)? Mức trần? | Có. Đề xuất 60 lượt chat và 20 lần nạp tệp mỗi tài khoản giám khảo mỗi ngày (một lượt đi 6 cảnh dùng khoảng 10–15 lượt chat), đặt trong SSM để đổi không cần deploy |
| Q7 | Đợt 7 kiểm toán prompt (chip có cấu trúc) làm trước demo? | Hoãn tới sau cuộc thi (lý do ở F2) |
| Q8 | Bộ nhớ trích xuất (`memory-state-preference`): đổi model trích xuất của `facts_vi` (ví dụ Haiku 4.5, đắt hơn Nova Lite), override bước hợp nhất (P1-6), hay chấp nhận? | Đo A3 trước (3 lượt). Nếu lệch vẫn còn: thử đổi model cho `facts_vi` vì tốn ít công nhất, không đụng pipeline hợp nhất; nếu vẫn lệch thì chấp nhận và chọn câu demo không có giới hạn thời gian |
| Q9 | Tiêu chí 3 OCR: chốt ngưỡng 9/10 tính ở lượt RC, ghi r12 là giới hạn ảnh mờ? | Có |
| Q10 | Thêm 8 ca đối kháng cho đủ 50 như KPI proposal §6? | Có (chi phí khoảng $0,2 ở lượt RC) |
| Q11 | Cắt Step Functions batch tuần, thay bằng backtest chạy tay cho K5? | Cắt |
| Q12 | Khung chấm kéo dài bao lâu? Aurora 0,5 ACU bật và tắt lúc nào? Đổi mật khẩu demo khi nào, gửi giám khảo bằng kênh nào? | Bật 0,5 ACU từ 9/12 sáng tới hết khung chấm (khoảng 2,4 USD/ngày) và trong giờ chạy RC; đổi mật khẩu 9/12 sau tổng duyệt cuối, gửi trong form nộp bài |
| Q13 | Thư mục `video/` (Remotion) có vào repo không? Video cuối để đâu? | Commit `video/src`, `package.json`, cấu hình; không commit `node_modules/`, `out/`; mp4 cuối đặt ở link ngoài (YouTube không công khai hoặc Drive) và ghi link trong README |
| Q14 | Hạn nộp chính xác, định dạng nộp (độ dài video, số trang slide, có thuyết trình trực tiếp không, thời lượng), trọng số chấm, giữ tên Yofina? | Hỏi ban tổ chức sớm; lịch dưới giả định nộp chậm nhất 10/12, video 3 phút, slide 10 trang |
| Q15 | Chốt khối 2.2 của [ba/12](../../ba/12-tong-hop-va-viec-can-chot.md) trước khi dựng slide (D-01, E-01, E-03, F-02, I-01, I-02)? | Chốt trước 5/12; slide dùng K2, K5, K4 kèm RCT, K9 dạng hòa vốn |

**Chốt 25/11 sau kiểm toán (chủ dự án)** [mới 25/11]. Nguồn: [2026-11-25-audit-tong-hop.md](../../research/2026-11-25-audit-tong-hop.md); việc ở issue [#2](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/2) và 36 issue con.

- **Q14 đã trả lời**: hạn 23:59:59 ngày 03/12; video MP4 để link Drive; chủ đề "Trợ lý AI · Trợ lý tài chính"; đội đã đăng ký. Không gửi câu hỏi cho ban tổ chức; vì vậy mọi thao tác vận hành (Aurora 0,5 ACU, đổi mật khẩu demo, trần SSM) làm trước khi nộp và để nguyên tới 11/12. README phải khai proposal Swinburne là tài sản có sẵn. Thời lượng thuyết trình chung kết chưa biết.
- **Q12 đổi**: Aurora 0,5 ACU và đổi mật khẩu ngày 2/12 (trước khi xuất tờ hướng dẫn), không phải 9/12.
- **Q6 đổi**: trần theo tài khoản 100 lượt chat/ngày (thay 60); trần chung qua SSM: planner 1.500, ingest 1.000 lời gọi/ngày cho khung chấm. Giữ thời gian chờ bộ giới hạn 20 s; không rút ngắn output Analyst.
- **Luồng K**: giữ số bước và độ dài lập luận; sửa chỗ lập luận mâu thuẫn với kết quả đã lưu; thêm công tắc SSM.
- **Cảnh 4 chạy thật**, không dùng bản lộ trình seed; persona `minh` 120 ngày lịch sử, không cài điểm gãy trong lịch sử; giám khảo tải tệp sao kê CSV để kích hoạt sinh lại lộ trình.
- **Tài khoản**: `giamkhao1–3` đều dùng persona `minh`, không thuộc nhóm `ops`; truy vết trong demo qua "Vì sao → Chi tiết kỹ thuật"; bảng vận hành chiếu bằng tài khoản vận hành riêng.
- **Eval**: sửa bộ chấm trước RC dù điểm có thể giảm; đối kháng và đường demo chạy 3 lần, báo khoảng tin cậy; K5 báo hai định nghĩa cạnh baseline.

## 8. Lịch (hạn nộp 23:59:59 ngày 03/12/2026) [đổi 25/11]

Bản 24/11 (RC 4/12, nộp 10/12) nằm sau hạn thật nên thay bằng bảng dưới. Issue theo đợt ở [#2](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/2).

| Ngày | Mốc | Việc |
|---|---|---|
| T4 25/11 | | Kiểm toán xong, chủ dự án chốt quyết định, tạo issue. A1 (đi 6 cảnh, #4); mở case quota Bedrock (#3); bắt đầu việc đợt 1 |
| T5 26/11 | **M1: đóng phase 5** | A2–A5; dữ liệu `minh` 120 ngày (#8); sửa bộ chấm eval (#5, #6) |
| T6 27/11 | | Review, merge nhánh đợt 1; người viết 20 câu giữ riêng (#31) |
| T7 28/11 | **M2: deploy đợt 1** | Gồm #5–#20 và việc cũ còn hiệu lực (A2, A3, B1, B3, B5, C1, C2, E1–E5, F1, D4, G1). `--only` các ca của phần đổi |
| CN 29/11 | | Đo sau đợt 1 (#21: OCR, bộ nhớ, 6 cảnh, 3 phiên song song); đọc log; làm việc đợt 2 |
| T2 30/11 | **M3: deploy đợt 2, hạn cuối tính năng mới** | #22–#29 và tính năng mới của chủ dự án đã xanh; `--only` what-if, lộ trình, cảnh 4 chạy thật |
| T3 1/12 | **M4: code freeze** (tối) | Chỉ sửa lỗi chặn demo. Tổng duyệt lần 1 (G5); tài liệu và ADR-0004 (#32); BA nộp số kinh doanh (#33); nháp slide (#37) |
| T4 2/12 | **M5: RC và eval cuối** | Deploy RC; vận hành trước khi nộp (#35: Aurora 0,5 ACU để tới 11/12, đổi mật khẩu, trần SSM, preflight); lượt eval đầy đủ duy nhất kèm chạy 3 lần (#34); quay màn hình 6 cảnh |
| T5 3/12 | **M6: nộp bài trước 18:00** | Sáng: sửa lỗi chặn demo (chỉ `--only`). eval-report; README, tờ A4, `.zip` (#36); slide (#37); video lên Drive (#38); J1; nộp; commit và push |
| 4–8/12 | Giám khảo dùng thử | Không sửa mã, slide, sản phẩm. J5 theo dõi mỗi ngày |
| T3 8/12 | Công bố top 5 | |
| T6 11/12 | **Chung kết** | Thuyết trình trực tiếp (thời lượng chưa biết); sau đó trả Aurora về 0 |

## 9. Cách kiểm (người điều phối)

[đổi 24/11]

- Sau mỗi đợt deploy: unit cả bộ, `cdk diff` trước, vài ca `--only` của phần vừa đổi; đọc log Runtime tìm `turn_persist_timeout`, `verifier_fallback`, `Traceback`.
- Sau RC: tự đọc 10 ca bất kỳ trong `evals/results/` và so với eval-report; tự đếm `audit_events` của khoảng giờ chạy.
- Tự làm hai bài ép lỗi của C4; tự đi tổng duyệt một lần bằng trình duyệt ở khổ 390×844.
- Chạy `scripts/scan_repo.py` và `git grep` các mẫu account ID, `arn:aws`, `AKIA`, mật khẩu trước mỗi push của tuần nộp.
- Làm theo README ở mức đọc khô để chắc không thiếu bước; liệt kê tài nguyên theo tag và so `aws-resources.md`.

## Kết quả thực hiện

(Điền đủ khi đóng phase. Các mục dưới ghi theo từng luồng khi xong.)

### Luồng K: agent như người tư vấn (K1, K2, K3), 25/11 (Runtime v27, Amplify job 21)

**Đã làm** (nhánh `p6/advisor`, commit 955c354 trên nhánh, 589eb1c trên `main` sau khi `git pull --rebase` làm phẳng merge 3a30d7c):

- **K1**: khối mới `reasoning` (`contracts/blocks/reasoning.schema.json`, `yofina_core.blocks.build_reasoning`, Zod sinh, fixture): 0 đến 5 bước `seen`, `why`, `effect` kèm `basis` (tool hoặc luật) và một kết luận tùy chọn. Analyst của what-if (`Analysis.reasoning`, `.conclusion`) và planner lộ trình trong chat (`AdvisedSketch`, `advise=True`) trả lập luận NHƯ DỮ LIỆU trong chính lời gọi đã có: không thêm lượt gọi model (what-if vẫn 3 lượt, lộ trình vẫn 1 lượt planner). Job sinh lại lộ trình không đổi. `agent/src/yofina_agent/advisor.py` kiểm bằng mã: bước có số không căn cứ (NumericGrounding với tập số của lượt; ở lộ trình là bộ kiểm chặt của bước) bị bỏ, không trả lại cho model sửa; căn cứ chỉ hợp lệ khi tool trả OK trong lượt hoặc luật đã được `check_suitability` xét (không `skipped`); nhãn căn cứ do mã dựng; chữ lập luận qua Guardrail đầu ra. Phát dần: một bản `complete: false` cho mỗi bước rồi bản `complete: true` (cùng id), trước khối `options` (what-if) hoặc thẻ lộ trình.
- **K2**: kết luận một câu phải trỏ đúng phương án mang nhãn "Gợi ý" (sau khi mã đã bỏ gợi ý vì quỹ dự phòng hay hũ thiếu; id phương án đổi theo hũ thật thì theo id mới) hoặc một bước của bản lộ trình ĐÃ LƯU; `personal` (`memory`, `behavior`) chỉ giữ khi nguồn có thật trong lượt, không thì bỏ câu. What-if khoản chi và lộ trình trong chat đọc `forecast___get_behavior_profile` (tool có sẵn, song song với kế hoạch). Bộ nhớ chỉ dùng ở what-if như trước (lộ trình chưa nhận bộ nhớ, theo bảng cắt của phase 6).
- **K3**: `frontend/src/chat/ReasoningView.tsx`: lần đầu thấy khối thì các bước hiện từng dòng (900 ms), có kết luận thì thu lại thành câu kết luận (nền tint, biểu tượng bóng đèn) và Disclosure "Xem cách mình cân nhắc"; vùng `aria-live="polite"` giữ nguyên suốt nên trình đọc màn hình đọc từng bước rồi đọc kết luận; giảm chuyển động hoặc đã thấy khối trong phiên thì hiện ngay trạng thái cuối; căn cứ ghi bằng chữ ("Căn cứ: Kết quả mô phỏng · Các khoản đến hạn"). Ảnh 390×844 trên `dev:mock` (câu "neu mua…"): [đang cân nhắc, sáng](../../research/ui-round1/chat-can-nhac-tuvan-sang.png), [tối](../../research/ui-round1/chat-can-nhac-tuvan-toi.png); [kết luận, sáng](../../research/ui-round1/chat-ket-luan-tuvan-sang.png), [tối](../../research/ui-round1/chat-ket-luan-tuvan-toi.png).
- Cấu hình: `analyst_max_tokens` 1800 → 2600 (lập luận thêm khoảng 700 token đầu ra, bản cũ đã dùng 1150 đến 1320), `max_tool_calls_per_turn` 16 → 18 (thêm lần đọc hồ sơ hành vi); phần `narrative` của Analyst rút từ 2–4 câu (450 ký tự) còn 2–3 câu (350 ký tự), lý do chọn phương án để ở lập luận.
- Test: unit 3922 passed (thêm `tests/unit/agent/test_advisor.py` 24 ca với LLM giả: có lập luận, bước có số không căn cứ bị loại, căn cứ không có thật bị loại, kết luận sai đích/số/nguồn bị bỏ, không có lập luận thì lượt như cũ, Guardrail lọc chữ lập luận, lộ trình chat và job; `tests/unit/test_contracts_phase6.py` 12 ca bất biến hợp đồng); vitest 990 passed, 4 skipped (thêm `ReasoningView.test.tsx` 7 ca), `tsc -b`, build, `check:bundle` sạch.

**Ca kiểm (mỗi ca một lần, `minh` đặt lại trước mỗi ca)**:

| Ca | Kết quả | Lượt gọi model | Độ trễ |
|---|---|---|---|
| `whatif-bnpl` | Đạt (grounding, schema, suitability, trajectory 100%) | 3 (như cũ) | Trọn câu 37,9 s. Analyst 16,3 s với 2.013 token ra; trước đó 9,1–10,5 s với 1.150–1.320 token (log v26) |
| `roadmap-create-emergency-fund` | Đạt (`roadmap_shape` 1/1, 0 bước vi phạm) | 1 planner (như cũ) | Trọn câu 28,0 s; chặng phác thảo 16,5 s, cả lần lập 19,8 s; trước đó phác thảo 10,1–11,7 s, cả lần lập 12,5–18,0 s (log v26) |

Log `advisor_reasoning`: what-if 4 bước model trả, giữ 3 (1 bỏ vì căn cứ), kết luận giữ; lộ trình 4 bước, giữ 2 (2 bỏ vì số không căn cứ), kết luận giữ.

Lập luận nguyên văn, `whatif-bnpl` ("Nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao"):

1. Thấy: "Mua tai nghe bằng Trả sau sẽ khiến hũ Nghĩa vụ hụt, đến ngày 05/12 phải trả tổng 2.200.000 ₫ trong khi số dư dự kiến chỉ 1.450.000 ₫." Vì sao: "Bạn sẽ thiếu 750.000 ₫ đúng ngày đến hạn, dễ bị trễ thanh toán." Ảnh hưởng: "Nghiêng về không dùng Trả sau cho khoản này." Căn cứ: Kết quả mô phỏng · Các khoản đến hạn.
2. Thấy: "Hũ Giải trí còn 760.000 ₫, hũ Du lịch còn 1.800.000 ₫ — đều có thể dùng để mua tai nghe 1.200.000 ₫." Vì sao: "Tai nghe là đồ điện tử tùy ý, phù hợp lấy từ hũ giải trí hoặc du lịch hơn là vay." Ảnh hưởng: "Mở ra phương án dùng tiền hũ thay vì Trả sau." Căn cứ: Số dư các hũ · Hũ nguồn đủ tiền.
3. Thấy: "Từ lịch sử chi tiêu, bạn đã dùng Trả sau 2 lần trong 47 ngày qua, chiếm 14% chi tiêu." Vì sao: "Thói quen dùng Trả sau khá thường xuyên, dễ tích lũy nghĩa vụ mà không để ý." Ảnh hưởng: "Cần thận trọng hơn, ưu tiên dùng tiền sẵn có." Căn cứ: Thói quen chi tiêu.

Kết luận: "Nên dùng tiền hũ Du lịch thay vì Trả sau để tránh hụt Nghĩa vụ ngày 05/12 và không đẩy tỷ lệ nợ vốn đã ở mức 60% lên cao hơn." (`option_id` `switch_du_lich`, `personal` `behavior`).

Lập luận nguyên văn, `roadmap-create-emergency-fund`:

1. Thấy: "Hũ Ăn uống chỉ còn 380.000 ₫ trong khi mức thiết yếu tháng là 2.956.000 ₫." Vì sao: "Hũ thiết yếu sắp cạn, cần chuyển bổ sung từ hũ có dư trước kỳ lương." Ảnh hưởng: "Thêm bước chuyển từ hũ Giải trí sang Ăn uống trong giai đoạn đầu." Căn cứ: Số dư các hũ · Hũ nguồn đủ tiền.
2. Thấy: "Điểm chống chịu thành phần vay mượn ở mức yếu, hệ thống ghi nhận dùng Trả sau hai lần gần đây." Vì sao: "Thói quen Trả sau làm tăng nghĩa vụ tương lai, cần giảm chi không thiết yếu để bù." Ảnh hưởng: "Đề xuất giảm chi Giải trí và tăng phần chia cho Ăn uống từ kỳ lương sau." Căn cứ: Thói quen chi tiêu · Điểm chống chịu · Phương án phân bổ.

Kết luận: "Bắt đầu từ bước chuyển tiền bổ sung hũ Nghĩa vụ ngay hôm nay vì khoản đến hạn 23/11 chỉ còn hai ngày nữa." (`step_id` `bo_sung_nghia_vu`).

**Còn lại**:

- Độ trễ tăng khoảng 6–7 s ở Analyst và 5–6 s ở phác thảo lộ trình vì thêm token ra. Lập luận chỉ hiện sau khi lời gọi xong và qua Verifier (không stream được đầu ra có cấu trúc qua `yofina_core.llm`); muốn lập luận hiện trong lúc chờ thì cần đường gọi stream có cấu trúc (ConverseStream, đọc dần JSON của tool) ở `yofina_core.llm`, làm cùng D2.
- Kiểm tra trước khi chi (ý định `affordability`, thẻ `affordability_card`) chưa có lập luận: đường này không có Analyst, chỉ có người viết Nova Lite chữ tự do, thời hạn 2 s. Muốn có thì đổi lời gọi đó sang đầu ra có cấu trúc và nới thời hạn (cần chủ dự án chọn).
- Kiểm bằng mã không bắt được lập luận nói khác bản đã lưu: ở lộ trình, bước 1 nói "chuyển từ hũ Giải trí sang Ăn uống" trong khi bản lưu chuyển từ hũ Đi lại (lập luận viết cùng bản phác thảo, mã chỉ kiểm số và căn cứ). Kết luận what-if khai `personal: behavior` nhưng câu không nhắc thói quen (mã chỉ kiểm nguồn có thật, không kiểm câu có dùng).
- Bộ chấm `evals/run.py` chưa kiểm số trong chữ của khối `reasoning` (chỉ chữ trả lời và phương án) và gom mọi bản phát dần như nhiều khối; nên thêm khi sửa bộ chấm.
- K4 (gợi ý hỏi tiếp) không làm.

### Bộ hũ mặc định và đợt "agent thích ứng" (issue #39), 26/11 (Runtime v29–v32, Amplify job 25–28)

Không thuộc các luồng A–K ban đầu: chủ dự án thêm ngày 25–26/11. Chi tiết từng đợt ở [ai-log](../../ai-log/2026-11.md) (các entry 26/11) và [HANDOFF](../../../HANDOFF.md) mục "Trạng thái tối 26/11".

- **Đã làm và deploy**: tài khoản mới 3 hũ mặc định, `purpose`, Quỹ dồn, đề xuất tỷ lệ theo kê khai (migration 0057–0059); ví demo 8 hũ; sàn hũ theo khoản định kỳ, sàn chi và sàn thiết yếu theo mức nền bền; lộ trình có đích Dự phòng, nhận câu người dùng; router dùng danh sách hũ của ví; hàm và tool tính ngày `knowledge___resolve_date`; khoản đến hạn đúng ngày lương là trước lương (BR-22); khử trùng dòng nạp ghép một-một; `scripts/scan_repo.py`.
- **Kiểm trên app** (mỗi câu một lần, không chạy eval): v32 đạt cảnh 1, 2, 4 (cảnh 2 thiếu 1.167.673 ₫, cảnh 4 sinh lại sau 19,6 s); v31 đạt cảnh 3 (29 → 12, trụ 26 ngày), 5, 6. Không đạt ở v32: router không điền `spend_jar_code`, `date_spec` (câu du lịch không nêu hũ, hũ tự đặt tên, "trước Tết").
- **Còn lại**: router chạy Claude Haiku 4.5 (Nova dự phòng) và sửa 5 lỗi thấy trên app đang làm; eval cho mọi thay đổi 26/11 chưa chạy (ca có thể đổi ở ai-log entry 16:40 ngày 26/11); #40, #41, #44 trước hạn tính năng 30/11; #45 trước freeze 01/12.
