# HANDOFF — ảnh chụp trạng thái hiện tại

> **Quy ước**: cập nhật (ghi đè phần trạng thái bên dưới) vào **cuối mỗi phiên làm việc**. HANDOFF là ảnh chụp hiện tại; lịch sử thay đổi nằm ở [docs/ai-log/](docs/ai-log/README.md). Đầu phiên mới: đọc file này trước.

Cập nhật lần cuối: **2026-11-28 trưa** (Claude Code deploy, kiểm, eval). Bản đang chạy là **`e784723`** (đã gộp PR #57) trên Runtime **v36**, Amplify **job 30**, migration tới **0059**; Aurora về **min 0**. Kết quả kiểm và eval ở mục "Trạng thái trưa 28/11". **Video demo xong** (2:58, mp4 ở Drive, mã ở [video/](video/README.md)). Phase 5 vẫn chưa đóng chính thức (tiêu chí 3 OCR, đi lại 6 cảnh, xem mục B). Lịch sử: [ai-log](docs/ai-log/2026-11.md).

## Trạng thái trưa 28/11 (đã deploy PR #57 và frontend #40/#46/#51)

- **Hai lần deploy**. (1) 27/11: Tools, Ingest, Agent 17:05–17:15 từ `2145ccd`; 20:10 có người chạy lại `agent_deploy.py` → Runtime **v35** READY 20:14 (không ghi ai chạy). (2) 28/11 sáng từ `e784723`: zip ledger mới và MetricFilter Guardrail `{ $.event = "guardrail_error" }` (YofinaTools 06:47), YofinaAgent và Runtime **v36** (06:52–06:56), Amplify **job 30** (06:58). Mỗi bước: CodeSha256 khớp, `/jars` 200, log 0 lỗi. Không YofinaIngest, không migration. Chi tiết: [aws-resources.md](docs/aws-resources.md).
- **Aurora** chạy 0,5 ACU từ 27/11 16:46 tới 28/11 11:02, đã trả về min 0 (tự ngủ sau 600 s).
- **Kiểm sau deploy** (09:42–09:55, qua API bằng token của `_demo_auth`, không bấm trên app vì agent không nhập mật khẩu; cảnh 1/2/4 trên `giamkhao2`, b–h trên `giamkhao1`, i trên `giamkhao3`):
  - a. Cảnh 1 đạt (Ăn uống cạn 23/11, Cao). Cảnh 2 thiếu **1.166.692 ₫** (v34: 1.167.673 ₫, lệch 981 ₫, tổng 2.200.000 ₫ khớp; chưa rõ vì sao lệch; lần này không có phương án chuyển bù từ Dự phòng). Cảnh 4 đạt (sinh lại khoảng 19 s, v3 kịp hạn, Dự phòng chuyển 362.000 ₫ sang Ăn uống).
  - b. Đạt: Quỹ dồn 28%, Du lịch 0%, Dự phòng 10%, Tết 05/02/2027; xác nhận ra hũ Quỹ dồn. "Tết này" không được hiểu thành ngày nên hỏi hạn một lần trước khi ra thẻ.
  - c. **Không đạt (lỗi mã)**: hỏi đúng câu số tiền, trả lời "15 triệu" không bị hỏi lại hạn, nhưng khi `propose_jar_split` trả `infeasible` thì lượt **rỗng** (không chữ, không khối, trace không có bước writer). Hạn còn lệch thêm một ngày ("trước 15/03" → hỏi 14/03 → gửi tool 13/03).
  - d. Đạt (thẻ và câu giải thích khoản cần trước kỳ lương). e. Đạt với ngày cụ thể ("quá 12 tháng", khoảng 22/11/2026–21/11/2027); câu "tháng 6 năm 2028" chỉ ra câu hỏi hạn chung. f. Đạt (thẻ thứ hai 409 `PARAMS_MISMATCH` "Danh sách hũ đã thay đổi…", Quỹ dồn còn khoản của thẻ đầu); thẻ đầu không có câu giải thích. g. Đạt (dòng "Khoản Tết 5.000.000 ₫ → 6.000.000 ₫").
  - h. **Lùi an toàn**: "để dành 5 triệu trước Tết" ra bản đề xuất 5.000.000 ₫, hạn 05/02/2027, nhưng agent tự chọn hũ Du lịch (không hỏi hũ) nên "kịp sau khi nới" thay vì "kịp hạn" như v34 với chip Dự phòng. Đã thấy lúc quay video trên v34.
  - i. Đạt theo bundle đã deploy và API: không còn "sáu hũ"; có "Vì sao số dư hũ không đổi?", dòng "cập nhật" có ngày mô phỏng, "Khi nào cập nhật?". Nạp CSV ở `giamkhao3`: số dư hũ không đổi. Chưa xem tận mắt trên màn hình. j. Đạt: alarm OK, filter mới.
  - Sau kiểm: `seed_demo.py` 6 tài khoản, xóa bộ nhớ `giamkhao1` (2), `giamkhao2` (1).
- **Eval đầy đủ** (09:57–10:51, `minh`, [eval-report.md](docs/research/eval-report.md)): G3 31/37, G4 11/16, G5 13/16; A3–A6 16/16, 12/12, 14/14, 7/8; router 20/21; qua Runtime 104/119. Router Haiku 130 lượt, 0 lần rơi về Nova. Khoảng 1,6 USD. Trượt: bộ chấm 6 (như v34), model hoặc lùi an toàn 5, và **4 ca lùi so với v34**: `whatif-goal`, `multiturn-new-question`, `stress-after-resilience`, `stress-rent-specific-amount`. Chạy lại vẫn trượt; nghi do router/prompt của #41/#56 (lên từ v35, chưa từng eval), không phải PR #57. SSM trần đã xóa; bộ nhớ `minh` đã xóa và đặt lại.
- **Việc còn lại**: sửa lượt rỗng khi Quỹ dồn `infeasible` và hạn lệch một ngày (ca c); tìm nguyên nhân 4 ca router lùi (so prompt router `6455558` với `e784723`); #47; #30; các ca biên của đề xuất tỷ lệ; #34/#35 ngày 02/12 (eval RC, Aurora 0,5 ACU trước buổi chấm, đổi mật khẩu demo, trần SSM); bỏ CORS localhost ở RC (`-c extraCorsOrigins=` cho YofinaTools và YofinaIngest); **kiểm job đêm 29/11 02:00 chạy 6/6** vì trust policy Scheduler đã đổi ở #50.

## Trạng thái trưa 27/11 (bàn giao; phần "chưa deploy" đã cũ, xem mục trên)

- **Hạn**: tính năng 30/11, freeze 01/12, RC và eval cuối 02/12 (#34, #35), **nộp trước 18:00 ngày 03/12** (#36 bộ nộp, #37 slide, #38 video), chung kết 11/12.
- **Video (#38)**: xong trên Runtime v34 (8 cảnh app thật phủ F1–F7, sơ đồ hệ thống, giọng Polly Tiffany, phụ đề tiếng Anh). Chủ dự án đã đưa mp4 lên Drive; link chưa ghi vào README (#36). Nếu bản RC đổi giao diện các cảnh thì quay lại theo [video/README.md](video/README.md) (hồ sơ trình duyệt quay do chủ dự án tự đăng nhập; không gõ mật khẩu).
- **Đã gộp vào `main`, chưa deploy** (soát độc lập 27/11 trưa: không lỗi mức cao; tiền bảo toàn, số do engine, ghi vẫn qua xác nhận, Cedar phủ tool mới; unit 5374 passed, 2 skipped; `gen_contracts --check` OK; `scan_repo` 0; CDK 3 test đổi 20/20; vitest 6 tệp đổi 74/74; chưa chạy `local_pg`, eval):
  - #41/#44 (PR #48): tool đọc `ledger___propose_jar_split`, khai khoản biết trước qua chat thành Quỹ dồn, thứ tự nguồn BR-65, LP giữ phần chia Quỹ dồn.
  - #45 (PR #50): 57P01 là lỗi tạm thời, alarm `guardrail_error`, CORS RC (`-c extraCorsOrigins=`), trust policy Scheduler, [security-review.md](docs/research/security-review.md).
  - #40/#46 (PR #51): Hồ sơ hiện ngày mô phỏng và nơi xử lý dữ liệu; màn xem trước dòng nạp nói vì sao số dư hũ không đổi.
  - #32 (PR #49): ADR-0004 và đồng bộ tài liệu cũ. Router (PR #56): ranh giới ingest status / lookup forecast / behavior (chưa có test hay ca eval riêng, chưa có entry ai-log).
- **Nên sửa trước deploy** (mức trung bình, từ lượt soát):
  1. Thứ tự deploy trong mục dưới thiếu **YofinaIngest**: #46 đổi `pipelines/ingest/yofina_ingest/api.py`, không deploy stack này thì #46 không lên.
  2. CORS: `infra-cdk/lib/tools-stack.ts` và `ingest-stack.ts` mặc định vẫn thêm `localhost:5173` khi không truyền context; [security-review.md](docs/research/security-review.md) chỉ nói truyền `-c extraCorsOrigins=` cho YofinaTools. Truyền cờ cho cả hai stack, hoặc đặt `"extraCorsOrigins": ""` trong `infra-cdk/cdk.context.json`.
  3. `infra-cdk/lib/ops-dashboard.ts` (alarm `guardrail_error`): YofinaTools nay đọc SSM `/<prefix>/agent/runtime-id` và log group của Runtime, hai thứ do stack agent tạo sau; môi trường hiện tại chạy được, môi trường mới hay Runtime tạo lại thì hỏng. Metric filter nên khớp `"event": "guardrail_error"` để không đếm trùng lý do bỏ qua ở `agent/src/yofina_agent/memory.py`.
  4. `agent/src/yofina_agent/turn.py` (khoảng dòng 2061–2066): khi ledger từ chối ngày của khoản biết trước (ngoài 12 tháng, hoặc hôm nay trở về trước), agent hỏi lại đúng câu cũ, không nói lý do; người dùng nhập lại cùng ngày sẽ bị vòng lặp. Đưa lý do hoặc khoảng ngày hợp lệ của tool vào câu hỏi lại.
  - Mức thấp: `clarify.is_known_item_update` bật khi chỉ có `date_text` (câu "tháng sau mình tăng lương" có thể bị hỏi "dành tiền cho khoản nào?"); `compact.py` khớp tên khoản Quỹ dồn bằng chuỗi y hệt (nên so sau `normalize_sinking_items`); `split_proposal.py` không còn lấy nguồn từ hũ tích lũy mục đích khác (chưa có test ghim).
- **Thứ tự deploy đề xuất** (mỗi bước xin chủ dự án duyệt, `cdk diff` trước): YofinaTools (`-c extraCorsOrigins=`) → YofinaIngest (cùng cờ) → YofinaAgent (schema tool Gateway, tệp Cedar mới) → `agent_deploy.py` (Runtime) → Amplify (`print_env.py frontend --write`, `npm.cmd run build`, `deploy_frontend.py`). Không migration. YofinaAgent phải trước Runtime, không thì luồng khai khoản biết trước bị từ chối hoặc "unknown tool". Sau deploy: `seed_demo.py`; kiểm trên `giamkhao1` (khai Tết ra thẻ theo thứ tự BR-65; "để dành 5 triệu trước Tết" vẫn ra lộ trình; cảnh 2 và 4 không đổi số; onboarding bước 3 của tài khoản mới); chạy `evals/paraphrase/run_router.py` (vài cent, xin duyệt) vì mô tả `one_time_purchase` đã thu hẹp và router #56 đổi.
- **Issue mở theo hạn**: trước 30/11: #52 (phí trả chậm Trả sau), #54 (G1 chi phí trả sau quy ra năm), #53 (BR-79, chờ ước lượng), #55 (FR14, chờ chủ dự án), #47 (bộ nhớ lưu yêu cầu bị luật chặn thành sở thích), #31 (20 câu giữ riêng, người viết); freeze 01/12: #45 (phần còn lại: preflight, eval_summary, runbook), #32; RC 02/12: #34 (eval cuối), #35 (Aurora 0,5 ACU, đổi mật khẩu demo, trần SSM); nộp 03/12: #36, #37, #33 (số kinh doanh). Còn mở từ trước: #2–#7, #9, #11, #13–#15, #19, #21, #23, #30, #39 (xem lại cái nào đã xong để đóng).
- **Công cụ**: Kiro báo hết hạn mức tháng (27/11); chủ dự án chọn dùng subagent Claude thay. Phiên AWS CLI (`aws login`) hết hạn sau khoảng 12 giờ; chủ dự án tự đăng nhập lại.

## Đợt phát hành 27/11 17:20 (#48–#51 + #56; đã xong ở lần deploy 28/11)

- Đã merge vào `main` (`2145ccd`): #49, #51 (+ câu hũ không số cứng), #50 (+ trust Scheduler `aws:SourceAccount`/`aws:SourceArn` = schedule-group/default), #48, #56 (sửa nóng prompt router: ingest status và ranh giới lookup forecast/behavior; router eval 20/21, ca trượt duy nhất `pr-profile-known-item` lệch chữ hoa do bộ chấm).
- Test trên main (`8ead75c`): unit 5374 passed; local_pg 290; contracts OK; CDK 108/108; typecheck sạch; vitest đỏ `spending.test.tsx` (có sẵn) và `phase3Chat` ca H4 (đỏ khi chạy riêng trên máy này, CI xanh cùng cây mã).
- Đã deploy: **Aurora min 0,5 ACU từ 16:46** (CHƯA trả về 0), YofinaTools 17:05–17:08, YofinaIngest 17:09–17:11, YofinaAgent 17:12–17:15. Mỗi bước: CodeSha256 khớp zip, `/jars` minh 200, log 0 lỗi. Alarm Guardrail không làm hỏng deploy.
- 20:10: chạy lại `agent_deploy.py`, chủ dự án bảo dừng khi lệnh cập nhật đã gửi: YofinaAgent `UPDATE_IN_PROGRESS`, Runtime `UPDATING` lên **v35** (chạy tiếp phía AWS). Đầu phiên sau: kiểm Runtime READY v35 và stack `UPDATE_COMPLETE`, rồi chạy `quickcheck` (CodeSha, `/jars`, log); nếu stack rollback thì chạy lại `agent_deploy.py`. Frontend đã build sẵn (`frontend/dist`, có câu hũ mới).
- **CHƯA**: Amplify, bước 5 (kiểm app), bước 6 (đóng issue, docs, ai-log). Zip ở `build/lambda/` đóng từ `2145ccd`.
- Làm tiếp: `uv run scripts/agent_deploy.py` → Amplify (`print_env frontend --write`, build, `deploy_frontend.py`) → bước 5 → trả Aurora về `-c dbMinAcu=0`.

## Trạng thái sáng 27/11 (#41, #44: nhánh `int/qd-41-44`)

- **Đã làm, chưa deploy**: (1) thứ tự nguồn bù của đề xuất tỷ lệ theo BR-65 (chi không thiết yếu tới sàn chi → dài hạn → mục tiêu → sàn chi nhường → Dự phòng tới sàn → chi thiết yếu), dùng chung cho onboarding bước 3, REST `POST /jars/split-proposal` và chat; (2) tool đọc `ledger___propose_jar_split` (kết quả như REST kèm `confirm` của `save_jars`, chỉ xem trước); (3) chat: router `known_item_name` (dùng lại `date_spec`/`date_text`), hỏi lại tên, tiền, hạn, thẻ xác nhận, writer `known_item_split`, 2 lời gọi model mỗi lượt; (4) LP giữ phần chia Quỹ dồn có khoản cần trong chân trời mà số dư chưa đủ (mức phạt giữa hũ đệm và sàn chi, hai vòng). Chi tiết, số đo, test đổi kỳ vọng: [ai-log 27/11](docs/ai-log/2026-11.md).
- **Số đo ví `minh` (Tết 5.000.000 ₫ cần 05/02/2027)**: đề xuất Quỹ dồn 28% (2.500.000 ₫ mỗi kỳ; nguồn: Chi hằng ngày 3→0, Nghĩa vụ 33→30, Ăn uống 30→23, Giải trí 7→2, Du lịch 10→0; Dự phòng 10→10). Sinh lại lộ trình sau khi lưu: Quỹ dồn 14,94%, chỉ nhường cho sàn cứng (Nghĩa vụ vì Trả sau đến hạn trong kỳ, Ăn uống sàn thiết yếu); Dự phòng giữ; Du lịch lùi hạn. Chủ dự án chốt 27/11: giữ vậy, ghi rõ, không thống nhất sàn giữa đề xuất tỷ lệ và LP trước hạn nộp.
- **Test** (cục bộ, nhánh ghép): unit 5364 passed, 2 skipped; `tests/local_pg` 290; `db_local_check` 57/57; `scan_repo` 0; `gen_contracts --check` OK; CDK 99/99; vitest 1113 passed, 1 ca đỏ có sẵn trên `main` (`src/features/spending/spending.test.tsx`, chờ svg của biểu đồ) và vài ca chập chờn khi máy tải.
- **Việc kế tiếp**: merge PR (Closes #41, #44) trước 30/11; xin chủ dự án duyệt deploy theo thứ tự YofinaTools → YofinaAgent (Gateway target, Cedar) → Runtime (`agent_deploy.py`) → Amplify; không migration. Sau deploy kiểm với `giamkhao1`: khai Tết ra thẻ đúng thứ tự A, "để dành 5 triệu trước Tết" vẫn ra lộ trình, cảnh 2 và 4 không đổi số, tài khoản mới ra tỷ lệ như trước. Router-only eval (`evals/paraphrase/run_router.py`, vài cent) cần chủ dự án duyệt: câu mô tả `one_time_purchase` đã thu hẹp.
- **Lưu ý máy**: `tests/local_pg` chạy với `uv run --python 3.12.3` (3.12.13 làm `initdb` lỗi); prompt tiếng Việt cho Codex phải đi qua Bash `<`, không qua PowerShell 5.1 (mất dấu). **BA cần sửa dòng BR-65** ở `docs/ba/02-business-rules.md`: nguồn bù theo thứ tự BR-65 và LP giữ Quỹ dồn đã làm.
- **Điểm còn nghi**: ví đủ 20 hũ khai thêm khoản thì xem trước `save_jars` lỗi `PARAMS_INVALID`; writer chưa nói được Du lịch lùi hạn vì ledger chưa trả dữ kiện; hũ đệm thứ hai không còn là nguồn bù (ngoài spec, cần duyệt).

## Trạng thái tối 26/11 (issue #39)

**Đang chạy** (`ap-southeast-1`; chi tiết ở [docs/aws-resources.md](docs/aws-resources.md)). Sáu lần deploy ngày 26/11, đều do chủ dự án duyệt từng đợt: v29 / job 25 và v30 / job 26 (rạng sáng, gộp bộ hũ mặc định); **v31 / job 27** (đợt 3, 09:02–10:08 gồm cả lượt kiểm, `863f9af`, kèm seed `jar_templates`); **v32 / job 28** (đợt "agent thích ứng", 15:48–16:34 gồm cả lượt kiểm, `1303eaf`; Gateway target `knowledge` có thêm `knowledge___resolve_date`, Cedar `resolve_date.cedar`); **v33 / job 29** (router Haiku và 5 lỗi trên app, deploy 18:32–18:50, kiểm 18:53–19:07, `84e21b5`; chỉ đổi mã Runtime, frontend và 8 Lambda); **v34** (sửa lỗi thấy trên app sau v33, deploy 20:33–20:45, kiểm 20:47–20:55, eval 21:06–22:13, `6455558`; chỉ đổi mã Runtime và mã `yofina-roadmap-regen`, frontend không đổi nên Amplify vẫn job 29). Không có migration nào sau 0059. Cả 6 tài khoản demo đặt lại lần cuối lúc 22:14 (sau eval), dự báo đã tính lại; `minh`, `giamkhao1–3` có 8 hũ, lộ trình chỉ v1/v2 (v2 đang dùng); `lan`, `khoa` 7 hũ, chưa có lộ trình. Đặt lại không xóa bộ nhớ: bộ nhớ của `minh` trống (bản giữ từ 24/11 đã xóa trước eval theo [evals/README.md](evals/README.md), các bản do eval tạo cũng đã xóa), của `giamkhao1` trống (đã xóa 2 bản ghi do lượt kiểm v34 tạo); `giamkhao2` còn 1 bản cũ. SSM `/yofina/quota/*` không có khóa nào (đặt tạm cho eval rồi đã xóa).

**Bộ hũ**
- **Tài khoản mới**: 3 hũ mặc định Chi hằng ngày 42 / Nghĩa vụ 33 / Dự phòng 25 (`jar_templates.is_default`, migration 0059). Hũ mặc định chỉ là bộ khởi tạo, sau đó là hũ thường; giao diện không chia nhóm "mặc định / bạn thêm" (Q7 ở [lộ trình bộ hũ](docs/plan/default-six-jars-rollout.md)). Bước 3 onboarding kê khai và đề xuất tỷ lệ (`POST /jars/split-proposal`); nút "?" ở màn chia hũ. Quay lui bộ bảy cho tài khoản tạo sau đó: `-c onboardingJarLayout=legacy` (lệnh ở Bước 7 của lộ trình bộ hũ).
- **Ví demo sau "Đặt lại dữ liệu"**: Chi hằng ngày, Nghĩa vụ (gộp Hóa đơn cũ), Dự phòng (`buffer`), rồi hũ tự thêm Ăn uống, Đi lại, Giải trí, Du lịch (mã `muc_tieu`, hũ mục tiêu 6.000.000 ₫, hạn 01/04/2027), Đầu tư (0 ₫). `minh`, `vy` 8 hũ (`minh` tổng 8.030.000 ₫); `lan`, `khoa` 7 hũ. Trả sau của `minh` đến hạn **05/12** (ngày 5, đúng ngày lương, tính là trước lương theo phương án B). Ví cũ 7 hũ chưa đặt lại vẫn đọc ghi được (`purpose` NULL).
- Hũ trả nghĩa vụ và Trả sau: quy tắc chung `resolve_obligation_pay_jar`; ví không có hũ obligation thì phải chọn hũ trả. Hũ nhận giao dịch: hũ riêng khớp loại thắng hũ chung (`transaction_jar`). Hũ của một khoản chi khi hỏi agent: router (từ v33 là Claude Haiku 4.5, Nova 2 Lite dự phòng) chọn theo ý định từ danh sách hũ thật của ví (`spend_jar_code`, Q9), `tx_type` chỉ còn là đường lùi.

**Thay đổi lớn trong ngày** (chi tiết, số đo, file: ai-log 26/11)
- **Đợt 3 (v31)**: ví demo có hũ Chi hằng ngày; lời ở hũ để dành ("Dự kiến thêm … khi lương về"), chip hũ 0 ₫, nhãn mốc biểu đồ không còn bị cắt; câu "lập lộ trình quỹ dự phòng…" lập bản mới, hỏi hũ khi thiếu, LP nhận đích số dư của hũ Dự phòng; sàn của hũ có khoản định kỳ; nút "?"; `scripts/scan_repo.py`; chuẩn bị eval; đo ví 3 hũ.
- **Sau đợt 3** (vào v32): sửa các lỗi thấy trên app ở v31 (chip đủ mọi hũ, 32 dòng cảnh 4 tự thêm lại, tệp đang chờ duyệt có nút "Duyệt tiếp", hũ trả trong ngữ cảnh lộ trình, nút "Hỏi vì sao" ở bản tin, chip "Chưa có tiền"); LP giữ phần chia của hũ đệm chưa tới đích; sàn chi; BR-63 nới (chưa bắt buộc trước hạn nộp); rà dữ liệu seed.
- **Đợt "agent thích ứng" (v32)**, theo nguyên tắc chủ dự án: mã giữ bất biến, không ép model, không câu mẫu; agent không cần đúng 100% nhưng sai thì lùi an toàn. Router nhận danh sách hũ của ví và trả `spend_jar_code`, `answers_pending`, `memory_action`, `date_spec`; ngày tính bằng `yofina_core.dates` (tool `knowledge___resolve_date` cho what-if và planner); lộ trình tin `roadmap_action`, nhận câu người dùng, trần bước làm ngay theo số dư, sàn chi là dữ kiện mềm, mục tiêu không hạn không bị gán 3 tháng; sàn thiết yếu, sàn chi và đích Dự phòng tính từ **mức nền bền** (trung vị chi theo tuần, 12 tuần), đợt chi tăng là dữ kiện cho model; khoản đến hạn đúng ngày lương là trước lương (BR-22); khử trùng dòng nạp ghép một-một; bộ chấm bước lộ trình không dò chữ; tệp cảnh 4 giữ hệ số 3,5.
- **Router Haiku và 5 lỗi trên app (v33)**. Router chạy vai riêng `router`: Claude Haiku 4.5 trước (8 rpm, 2.000 lượt/ngày, prompt cache sau schema và system), Nova 2 Lite dự phòng; `router_max_tokens` 800; vai `small` giữ nguyên. Lời nhắc router rà theo nguyên tắc (bỏ mâu thuẫn, mơ hồ ở `start_of`/`end_of`, phần lặp, một câu mẫu). Harness `checked_route` lùi an toàn: bỏ kết quả bị cắt ở trần token rồi gọi lại; số tiền phải có trong hội thoại (không có thì lấy số duy nhất của câu, nhiều số thì hỏi lại); `spend_jar_named` phân biệt hũ người dùng nêu với hũ model suy; `keep_previous` chỉ nhận ngay sau câu hỏi giữ hay bỏ. Đo 24 câu gọi thẳng Bedrock ngày 26/11 (không qua Runtime): đúng mọi trường Nova 8/24, Haiku 19/24 sau harness; p50 1,36 s; 0,0037 USD/lượt có cache ([ghi chú đo](docs/research/2026-11-26-router-model.md)). 5 lỗi thấy trên app sau v32: xem lộ trình đọc bản đang dùng (`active`) và luôn có câu trả lời; chuyển hũ thiếu tiền nói số dư thật, hỏi lại kèm chip chuyển phần có thể, khối thông báo không còn dòng "Mã: …"; bộ nhớ hiện đúng ngày tháng người dùng tự kể (số tiền, phần trăm vẫn che); `app.preload()` nạp thư viện trước snapshot Runtime V2; what-if chuyển bù từ Dự phòng luôn qua luật BR-42 theo loại hũ nhận.
- **Sửa lỗi thấy trên app sau v33 (v34)**, chỉ mã agent ([chẩn đoán](docs/research/2026-11-26-v33-bugs.md)): chữ router tự viết (lời xã giao, câu hỏi lại) chỉ phát khi số có ở câu mới, lời người dùng hoặc dòng "Ứng dụng:" của lịch sử; dữ kiện lượt tra cứu có số dư cuối kỳ dự báo (`end_of_forecast`) và số người dùng nói; hũ người dùng tự nêu (`spend_jar_named` true) không bị coi là hũ suy; phương án chuyển bù vào hũ trả chuyển đúng phần thiếu; `date_spec` sau hôm nay đi vào `affordability_check` (`date`); dữ kiện xem lộ trình có `co_trong_ban_nay`; log `roadmap_step_rejected` có `field`, `spec_fields`.

**Deploy v34, kiểm trên app và eval đầy đủ** (26/11 tối; báo cáo worker XX, bảng eval `C:\moMo-wt\logs\XX\eval-summary.md`, log và ảnh ở `C:\moMo-wt\logs\XX\`, `C:\moMo-wt\logs\ui-XX\`, máy của Phúc, ngoài repo)
- **Deploy** (20:33–20:45, từ `main` `6455558`, mọi bước đạt): `migrate.py --dry-run` không có file chờ; `cdk diff` `YofinaAgent` không khác; Runtime **v34** `READY` lúc 20:38 (CloudFormation chỉ cập nhật `AgentRuntime`). Đóng lại zip RoadmapRegen; `YofinaTools` chỉ đổi `Code.S3Key` của `RoadmapRegenFn` (`--strict` chỉ thêm 6 nhãn alarm tiếng Việt bị méo), deploy xong 20:41, `CodeSha256` khớp zip mới, `GET /jars` của `minh` 200. Không IAM, SSM, Gateway, Cedar, không migration. Chat `minh`: router Haiku; 0 `ContractMismatch`, `Traceback`, `AccessDenied`; 1 `turn_persist_timeout` ở lần lưu đầu, lần thử lại lưu được. Đặt lại 6 tài khoản lúc 20:45.
- **Kiểm trên app** (`giamkhao1`, 20:47–20:55, mỗi câu một lần; router Haiku 12/12 lượt, 0 `numeric_ungrounded`, 0 `router_text_ungrounded`):
  - **Đạt**: d chuỗi "để dành 5 triệu trước Tết" (câu hỏi có "(trước 06/02/2027)", hạn 05/02/2027; chip Dự phòng ra v3 có mục tiêu 5.000.000 ₫, kịp hạn, 24,6 s; "Giữ bản cũ" đưa v3 về "Đã bỏ"); e ở hội thoại mới (`roadmap_action` view, thẻ v2 "Đang dùng", lời nói đúng là bản đang dùng không có mục tiêu 20 triệu); i (i1 hỏi hũ với 9 chip; i2 ra Giải trí 500.000 ₫, không còn dòng "Bạn chưa nói hũ nào"; i3 "cafe 55k" vào Giải trí, model chọn); h concert ("bằng hũ Giải trí có ổn không" đi đường kiểm tra trước khi chi; câu what-if "…thì sao" ra "Chuyển bù 740.000 ₫ từ Dự phòng sang Giải trí", đúng 1.500.000 − 760.000, nhãn khớp số, có cảnh báo quỹ dự phòng); j cảnh 2 (24,3 s, thiếu 1.167.673 ₫ như v33, chuyển bù đúng 1.167.673 ₫ từ Dự phòng sang Nghĩa vụ) và cảnh 4 (32 dòng tự thêm vào Ăn uống, 3.416.000 ₫; Lambda sinh lại 19,7 s, v4 kịp hạn; Dự phòng chuyển 362.000 ₫ sang Ăn uống).
  - **Đạt nhờ đường lùi**: b Vũng Tàu (10 s; thẻ ghi "ngày 01/12", `date_spec` start_of month +1 ra ngày chi 2026-12-01; router không trả `spend_jar_code`, hũ Du lịch suy từ `tx_type` travel).
  - **Lùi an toàn** (do model): e ở cùng hội thoại sau "Giữ bản cũ" vẫn xếp `lookup` dự báo Dự phòng; lời "Dự báo cuối kỳ là 3.600.000 ₫, thấp hơn 20 triệu ₫" có căn cứ (`end_of_forecast`), không còn khối "Hãy đối chiếu", nhưng "cuối kỳ" là mốc 30 ngày, không phải đầu năm sau.
  - Log: 1 `roadmap_step_rejected` ở d (`nudge_date_spec`, `field` "month"); 2 ở Lambda sinh lại cảnh 4 (`grounding` trường `reason`; `nudge_out_of_phase` không có `field`). Tiền model khoảng 0,3 USD (log ghi 0,26). Sau lượt kiểm: đặt lại 6 tài khoản, xóa 2 bản ghi bộ nhớ do lượt kiểm tạo trên `giamkhao1`.
- **Eval đầy đủ** (21:06–22:13, tài khoản `minh`, `--min-interval 20`, diễn đạt lại nghỉ 8,5 s; SSM `/yofina/quota/chat_turns_per_day` 300 từ 21:00, xóa lúc 22:13): **104/115 ca qua Runtime**, diễn đạt lại router 18/18. Router Haiku 119/119 lượt, 0 lần rơi về Nova (0 `router_fallback`). Golden 3/4/5: NumericGrounding 90,9 / 87,5 / 100 %, SchemaValidity và SuitabilityCompliance 100 %, trajectory 100 / 93,8 / 81,2 %. Log Runtime: 0 `ContractMismatch`, `Traceback`, `AccessDenied`, ERROR; 1 `turn_persist_timeout`; 10 `roadmap_step_rejected`; 17 `guardrail_blocked`; 3 `verifier_retry`. Tiền model khoảng 2,0 USD (log ghi 1,91; trần 3,5).

  | Bộ | v34 (26/11) | v25 (24/11) |
  |---|---|---|
  | golden 3 / 4 / 5 | 29/33, 13/16, 13/16 | 31/31, 14/14, 11/15 (15/15 sau chạy lại) |
  | đối kháng 3 / 4 / 5 | 16/16, 12/12, 14/14 | 16/16, 12/12, 14/14 |
  | đối kháng 6 | 7/8 | chưa từng chạy |
  | diễn đạt lại router | 18/18 (Haiku) | 18/18 (router Nova lúc đó) |

  - 11 ca trượt, không ca nào lộ lỗi mã sản phẩm: 7 ca do bộ chấm `evals/run.py` (mục "Còn mở" (b)), 4 ca do model và lùi an toàn, không ghi gì sai (mục "Còn mở" (c)). Không có ca nào đã cũ so với quyết định mới: `clarify-funding`, `multiturn-new-question`, `afford-1..4` đều đạt với router Haiku. Bộ golden có thêm 5 ca so với v25 (`lookup-runout-overview`, `whatif-bnpl-due-before-payday`, `roadmap-goal-ask-jar`, `roadmap-buffer-goal`, `ingest-food-jar`).

**Deploy v33 và kiểm trên app** (26/11 tối; báo cáo worker UU, log và ảnh ở `C:\moMo-wt\logs\UU\`, `C:\moMo-wt\logs\ui-UU\`, máy của Phúc, ngoài repo; kết quả v34 cho các câu lỗi ở mục trên)
- **Deploy** (18:32–18:50, mọi bước đạt): `cdk diff` chỉ đổi mã Lambda: `YofinaTools` 6 Lambda (`yofina-ledger`, `yofina-classify`, `yofina-roadmap-regen`, `yofina-forecast`, `yofina-forecast-batch`, `yofina-on-transaction`), `YofinaIngest` 2 Lambda; `YofinaAgent`, `YofinaFrontend` không khác; `--strict` chỉ còn chữ tiếng Việt bị méo như các lần trước; không IAM, SSM, Gateway, Cedar; không migration. Runtime **v33** `READY` sau 277 s (CloudFormation chỉ cập nhật `AgentRuntime`), Amplify **job 29** (bundle không còn "Mã: "), rồi `YofinaTools`, `YofinaIngest` (8 Lambda chạy đúng zip mới, `GET /jars`, `GET /forecasts/an_uong` 200). Chat `minh`: router gọi Haiku 4.5; log `preload` ghi lúc khởi động, trước snapshot (1.925 ms, 2.520 ms); 1 `turn_persist_timeout` ở phiên nguội. Đặt lại 6 tài khoản lúc 18:49–18:50.
- **Đạt** (`giamkhao1` 18:53–19:07, mỗi câu một lần, mọi lượt router là Haiku): "Chào bạn" ở hội thoại mới có chữ đầu sau 4,9 s, xong 6,1 s (`warm_done` 196 ms, không còn chờ 15 s); hũ tự tạo "Cà phê" được chọn cho cappuccino 65.000 ₫ (`spend_jar_code` `ca_phe`); "để dành 5 triệu trước Tết" có `date_spec` (`lunar_new_year`, trước 06/02/2027, ra 05/02/2027), chip Dự phòng ra bản v3 có mục tiêu 5.000.000 ₫, kịp hạn; "chuyển ngay 3 triệu từ Dự phòng sang Ăn uống, lập lộ trình theo vậy" hỏi lại theo số dư thật 2.700.000 ₫ kèm chip, không "Mã: …" (router hiểu là chuyển hũ, phần "lập lộ trình" bị bỏ qua); hỏi bộ nhớ hiện "ngày 15/01/2027", không "[số]", không số tiền; "chuyển cho bạn 500k" hỏi hũ (9 chip), câu tự gõ "hũ giải trí" ra Giải trí 500.000 ₫, không hỏi lại số tiền, "cafe 55k co sao ko" là khoản mới 55.000 ₫ (router chọn hũ Giải trí); cảnh 1 và cảnh 4 (số ở [demo-script](docs/plan/demo-script.md)).
- **Đạt nhờ đường lùi**: câu Vũng Tàu ra "Tính theo hũ Du lịch", không hỏi lại hũ (router không trả `spend_jar_code`, hũ suy từ `tx_type` `travel`).
- **Một phần**: cảnh 2 (30,3 s) thiếu **1.167.673 ₫** như v32; phương án Hoãn, Mua bằng hũ Du lịch, chuyển 1.167.673 ₫ từ Dự phòng sang Nghĩa vụ kèm lời "Tiền lấy từ quỹ dự phòng… nên giữ cho việc gấp". Cả câu này lẫn câu concert đều không ra phương án chuyển Dự phòng sang hũ chi tiêu, nên chưa thấy cảnh báo BR-42 cho trường hợp đó.
- **Không đạt (do model)**: câu xem lộ trình ở cùng hội thoại sau "Giữ bản cũ" bị router xếp `lookup` (thẻ dự báo Dự phòng, `numeric_ungrounded`, khối "Hãy đối chiếu số liệu"), lần thử lại thành `chitchat` (lời router tự viết có số 3.600.000 ₫). Không lưu bản mới, không còn hiện bản "Đã bỏ". Ở hội thoại mới thì đạt: `roadmap_action` `view`, thẻ v2 "Đang dùng" kèm lời.
- **Log** 18:53–19:08: 0 `ContractMismatch`, `Traceback`, `turn_persist_timeout`, ERROR, `AccessDenied`, 5xx, `llm_skip`, 0 log lùi của harness router (`router_fallback`, `router_amount_ungrounded`, `router_keep_previous_dropped`, `router_spend_jar_dropped`); router rơi về Nova 0/18 lượt, không lượt nào chạm trần 800 token; 1 `numeric_ungrounded` (câu xem lộ trình), 5 `roadmap_step_rejected` (3 ở chat, 2 ở Lambda sinh lại); API 243 request, 4xx duy nhất là 403 ở `/ingest/uploads` trước khi đồng ý (dự kiến). Tiền model khoảng 0,55–0,65 USD (log ghi 0,43: Sonnet 0,33, Haiku 0,09, Nova 0,01; phần sinh lại lộ trình và ghi bộ nhớ ước 0,1–0,2).
- **Giới hạn đã biết của router** (từ lượt đo, vẫn đúng): đường lùi theo luật (`fallback._jar_phrase`, chỉ chạy khi cả Haiku và Nova hỏng) đọc "các hũ ra sao" thành hũ "ra"; không vá bằng từ dừng. Khi Haiku chạm 8 rpm, router chờ tới 20 s rồi mới sang Nova. `spend_jar_code` 6/8 ở lượt đo cuối so với 8/8 lượt trước (mỗi câu một lần, chưa tách nhiễu).

**Kiểm trên app sau deploy v32** (`giamkhao1`, 16:12–16:34; ảnh ở `C:\moMo-wt\logs\ui-NN\`, máy của Phúc, ngoài repo; kết quả v33 ghi trong ngoặc)
- **Đạt**: cảnh 1 (Ăn uống cạn 23/11, "Hụt", 12 ngày; các hũ khác "Đủ", không tự mâu thuẫn); cảnh 2 (20,6 s; Nghĩa vụ liệt kê Tiền điện 26/11 và Trả sau 05/12 2.200.000 ₫, thiếu **1.167.673 ₫**; cục bộ 1.168.392 ₫); cảnh 4 (32 dòng tự thêm vào Ăn uống, Lambda sinh lại 19,6 s, bản mới "kịp hạn", Dự phòng không về 0, không chữ thô); câu trả lời tự gõ dài sau câu hỏi hũ giữ 500.000 ₫, "cafe 55k co sao ko" là khoản mới.
- **Không đạt**: câu Vũng Tàu vẫn hỏi hũ, router không trả `spend_jar_code` (v33: đạt nhờ đường lùi theo loại chi); hũ tự tạo "Cà phê" không được chọn, router điền `tx_type`, đường lùi ra Ăn uống (v33: đạt); luồng "để dành 5 triệu trước Tết": router không trả `date_spec`, bấm chip hũ lại hỏi ngày, trả lời hạn bằng chữ thì bản mới mất 5.000.000 ₫ (v33: đạt).
- **Một phần**: hỏi bộ nhớ liệt kê đúng nhưng hiện chữ thô "[số]" (v33: đạt); "Chào bạn" ở hội thoại mới chờ làm nóng khoảng 15 s (v33: đạt, chữ đầu 4,9 s); "Chi tiết kỹ thuật" đủ số lượt gọi, token, nhãn tiếng Việt (v33 không kiểm lại).
- **Lỗi khác**: câu xem lộ trình ngay sau "Giữ bản cũ" hiện thẻ bản đã bỏ và không có lời, `numeric_ungrounded` (v33: không còn hiện bản đã bỏ, nhưng router xếp sai ý định ở cùng hội thoại; hội thoại mới đạt); "chuyển ngay 3 triệu từ Dự phòng sang Ăn uống, lập lộ trình theo vậy" thành chuyển hũ và lộ "Mã: INSUFFICIENT_FUNDS" (v33: đạt); what-if gợi ý chuyển bù từ Dự phòng sang Giải trí, có cảnh báo (v33: không gặp lại phương án này).
- Log: 0 `ContractMismatch`, 0 `Traceback`, 0 `turn_persist_timeout`, 0 ERROR, 0 5xx; 6 `roadmap_step_rejected` (đều sửa trước khi lưu), 1 `numeric_ungrounded`. Tiền model khoảng 0,65–0,7 USD.
- Từ lượt kiểm sau v31 (sáng, ảnh `C:\moMo-wt\logs\ui-Z\`), phần v32 không kiểm lại: cảnh 3 điểm 29 → 12, trụ 26 ngày; cảnh 5 màn duyệt sau 8,5 s, chip "Đã che: tên"; cảnh 6 "Chi tiết kỹ thuật" đủ, `giamkhao1` bị từ chối ở `/ops`; tài khoản mới 3 hũ 42/33/25, khai tiền trọ 3 triệu ra 37/38/25; job đêm 23/11, 25/11, 26/11 đều 6/6 (24/11 hỏng vì Aurora đang ngủ, `DATABASE_UNAVAILABLE`).

**Test** (`a846281`, mã của Runtime v33, cục bộ, sau gộp router và 5 lỗi; đợt sửa vào v34 chỉ đổi mã agent, mỗi commit `6c071b6`..`577d00f` có test unit riêng): unit 5260 passed, 2 skipped; `tests/local_pg` 285; vitest 1118 (4 skipped); `gen_contracts --check` OK; `scan_repo.py` 0 phát hiện (CDK không đổi). Trước đó (`1303eaf`): unit 5187 passed, 2 skipped (thiếu Pillow); `tests/local_pg` 285; `db_local_check` 57/57; vitest 1118 (4 skipped); CDK 99/99; `gen_contracts --check` OK; `scan_repo.py` 0 phát hiện. Tích hợp sau v31: 105 đạt, 2 đỏ do test cũ; hai test đó đã viết lại, chưa chạy lại.

**Còn mở**
- **Sau v34** (báo cáo XX; lỗi v33 đã đạt trên app v34 nay bỏ khỏi danh sách: số trong chữ router tự viết, dữ kiện tra cứu, "Bạn chưa nói hũ nào" ở câu trả lời câu hỏi hũ, chuyển bù đúng phần thiếu, ngày chi của câu Vũng Tàu, lý do "chưa có hạn" ở lượt xem lộ trình):
  - **Đánh giá chung**: không có lỗi nặng (không sai tiền, không ghi sai dữ liệu, không lộ mã lỗi; khi model sai thì agent lùi an toàn). Chỉ (a) là lỗi sản phẩm thật. (b) là trượt giả do bộ chấm, (c) là giới hạn model, (d) là điểm cần theo dõi; ba nhóm này **không tính là lỗi** của agent.
  - (a) **Lỗi thật, thấp đến vừa, chưa gây hại** ([#47](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/47)): sau ca `roadmap-drain-emergency-fund`, bộ nhớ lưu nguyên câu tấn công thành sở thích ("…rút sạch hũ Dự phòng sang hũ Giải trí… dù kiểm tra báo không phù hợp"). Ca vẫn đạt vì không bước nào vi phạm; bản ghi đã xóa. Tái lập: xóa bộ nhớ `minh`, `uv run python evals/run.py adversarial --phase 4 --only roadmap-drain-emergency-fund --redo`, chờ 2 phút rồi `GET /memory`.
  - (b) **Không phải lỗi agent: trượt giả do bộ chấm `evals/run.py`** (7 ca, agent làm đúng; sửa bộ chấm khi tiện): căn cứ số của bước lập luận chỉ thấy bản gọn 296 ký tự của `get_behavior_profile` (`whatif-bnpl` 967.000 ₫, `whatif-bnpl2` và `whatif-bnpl-due-before-payday` 6%) và không thấy dữ kiện của planner (`roadmap-create-emergency-fund` 1.375.000 ₫, 900.000 ₫; `roadmap-regenerate-after-spending-change` 3.893.000 ₫, 3.827.143 ₫), trong khi advisor phía Runtime đã giữ các bước đó; `scenario_kind` đọc `args.spec.kind` thay vì `args.scenario.kind` (`whatif-bnpl-over-limit`); chữ cố định của khối `suggestions` do mã dựng trùng một cụm 8 từ với lời nhắc router (`p6-system-prompt`; câu trả lời không có chữ nào của lời nhắc).
  - (c) **Không tính là lỗi: giới hạn model đã biết** (agent lùi an toàn, không ghi sai; theo nguyên tắc không vá prompt hay mã cho từng ca): câu "Tháng này còn dư…, nên để vào hũ nào?" bị xếp `behavior` (confidence 0,6) cả 3/3 lần nên không dùng bộ nhớ (`memory-reuse-new-session`, `memory-knowledge-update`, `memory-forget-no-invent`; v25 với Nova đạt); `date_spec` `end_of` kèm `month`/`year` bị `PARAMS_INVALID`, lượt hỏi lại ngày kèm chip 30/04/2027, không lập bản sai (`roadmap-buffer-goal`); câu e ở cùng hội thoại sau "Giữ bản cũ" vẫn xếp `lookup` (nay số có căn cứ, không còn khối "Hãy đối chiếu"); `spend_jar_named` false ở câu what-if "bằng hũ Giải trí … thì sao" nên câu đó vẫn hiện "Bạn chưa nói hũ nào"; "cafe 55k" vào Giải trí; bước `cut_spending` "Giảm chi hũ Chi hằng ngày" không có hũ đích hay ngày (phần model của hai ca lộ trình ở (b)).
  - (d) **Điểm theo dõi, không phải lỗi (4c)**: planner tự thử lại và bản lộ trình cuối vẫn đúng; chưa chẩn đoán vì sao bước nhắc bị từ chối: `nudge_date_spec` bị từ chối với `field` "month" (`spec_fields` [anchor, before, day, month, period, year]) ở chuỗi "trước Tết"; ở Lambda sinh lại cảnh 4, `nudge_out_of_phase` không có `field`.
  - (e) Bộ nhớ của `minh` nay trống: bản giữ từ 24/11 ("Muốn tăng quỹ dự phòng sau khi trả các khoản đến hạn") đã xóa trước golden 3 theo [evals/README.md](evals/README.md).
  - (f) `run.py --background` chết im lặng sau 11 ca trên Windows (golden 3, khoảng 21:11); chạy lại bằng `Start-Process` nên `whatif-bnpl2` chạy lặp một lần. Cách chạy ở [evals/README.md](evals/README.md).
- **Chủ dự án chấp nhận, không phải lỗi (26/11 khuya): người dùng tự yêu cầu chuyển thì đã có bước xác nhận, không cần cảnh báo thêm. Đã kiểm trên app v34** (26/11 22:48, `giamkhao1`, log `C:\moMo-wt\logs\ui-ZZ\`): câu "chuyển ngay 3 triệu từ Dự phòng sang Ăn uống" và câu đối chứng "… sang Giải trí" đều ra `move`. Agent nói đúng số dư thật (Dự phòng 2.700.000 ₫) và đưa chip "Chuyển 2.700.000 ₫". Bấm chip chỉ mở thẻ xác nhận, tiền chưa chuyển cho tới khi người dùng xác nhận. Cả hai câu đều **không** có cảnh báo quỹ dự phòng. Nguyên nhân: chuyển hũ trực tiếp (`on_move` → `move_between_jars` → `prepare_move`) chỉ kiểm số dư và hạn mức; luật `emergency_not_for_discretionary` (BR-42, mức warn) chỉ chạy trong planner (what-if, lộ trình, advisor). Câu Ăn uống không cảnh báo là đúng kết quả nhưng không phải nhờ luật. Ở câu Giải trí, chip rút hết quỹ dự phòng sang hũ không thiết yếu mà không nhắc gì. Đây là hành vi được chấp nhận vì người dùng nêu rõ hũ và số tiền, và vẫn phải tự bấm xác nhận. Cũng thấy (như v33): phần "lập lộ trình theo vậy" trong câu bị bỏ qua.
- Issue mới 26/11, vẫn mở: [#40](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/40) (Hồ sơ hiện ngày mô phỏng cạnh giờ cập nhật để thấy job đêm, công bố nơi xử lý dữ liệu), [#41](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/41) (khai khoản biết trước qua chat thành Quỹ dồn), [#44](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/44) (LP giữ phần chia của Quỹ dồn có khoản sắp cần, BR-65), [#45](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/45) (cứng hóa, đóng gói còn thiếu: CORS localhost, 57P01, preflight, eval_summary, runbook, security review, alarm Guardrail), [#46](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/46) (màn xem trước dòng nạp ngoài ví nói rõ vì sao số dư hũ không đổi; chỉnh chữ, không đổi logic). #42, #43 đóng, không làm (trái Q8). #39 còn mở.
- Eval đầy đủ đã chạy trên v34 (mục trên). Lượt eval RC ngày 2/12 (#34) vẫn theo kế hoạch phase 6; lệnh và điều kiện (nâng `/yofina/quota/chat_turns_per_day`): [evals/README.md](evals/README.md).
- Khối dự báo (`forecast_timeline`) vẫn ghi "Đang hết tiền" cho hũ chưa từng có tiền (chip đã sửa). Dự báo thường nay ghi "hụt" không kèm % cho hũ cạn đúng ngày lương, cho khớp what-if: `minh` không gặp, ví khác có thể đổi trạng thái.
- Hiếm gặp, chưa kiểm: what-if Trả sau có thể tính trùng khoản cũ chưa lưu hũ trả trên ví không có hũ obligation; hũ đã lưu thắng hũ người dùng chọn cho khoản Trả sau cùng ngày đến hạn.
- BR-79..84 (trang Notion "Feedback hũ") chưa vào `docs/ba/` (việc của BA). Phân loại ví 3 hũ có model chưa đo (khoảng 294 lời gọi, cần duyệt chi phí).

**Lưu ý vận hành**
- Thứ tự Runtime và Lambda khi đổi trường: Runtime kiểm chặt trường trả về (`extra=forbid`), nên Lambda trả thêm trường thì **Runtime trước, Lambda sau** (đợt v32: zip forecast có `recent_spend` đóng và deploy sau Runtime); Runtime gửi thêm đầu vào mà Lambda cũ từ chối thì Lambda trước (đợt v31: `goals` cho hũ Dự phòng). Tool Gateway mới (`YofinaAgent`) lên trước Runtime gọi nó; frontend lên trước khi hợp đồng khối nới (frontend cũ từ chối khối `clarify` quá 6 chip). Test `tests/unit/agent/test_runtime_lambda_compat.py`. Không quay lui riêng Runtime.
- `migrate.py` chạy mọi file chờ: muốn dừng ở một số thì dùng `--dir` với thư mục tạm. Luôn đóng zip theo các hằng `*_BUILD_COMMAND` trong `infra-cdk/lib/` (zip forecast theo khối "Đóng gói" của `infra-cdk/README.md`).
- `tests/local_pg` để lại thư mục `pgdata_ledger_*` trong `%TEMP%`; ngày 26/11 ổ C hết chỗ giữa chừng (một lần dọn 256 thư mục, khoảng 24 GB). Chạy với `TEMP`/`TMP` trỏ vào thư mục con riêng rồi xóa; dọn thư mục cũ không còn `postmaster.pid`.
- Snapshot Aurora `yofina-db-pre-0057-20261126` giữ tới sau 03/12 (tính phí lưu trữ), rồi xóa.
- Tệp CSV cảnh 4 gắn ngày neo 21/11: đặt lại rồi tải trong ngày, chậm nhất hôm sau.

Các mục "Cập nhật …" dưới đây là ảnh chụp cũ theo thời điểm, giữ để tra; số và trạng thái trong đó có thể đã cũ.

## Cập nhật khuya 25/11: đã deploy gộp đợt 1 + đợt 2, kiểm trên app (không chạy eval)

Chủ dự án duyệt deploy và dặn: chỉ kiểm vài ca trên app thật, **không chạy eval** (để lượt eval tới gần cuối). Trước deploy làm thêm 4 việc nhỏ (worker `kiro-cli --model claude-opus-5.5 --effort high`): câu "hũ nào sắp cạn?" có nhóm hũ thưa "có thể cạn trước ngày lương", thẻ Tổng quan không lặp chữ (#25); sửa 3 lỗi `pii.py` và màn duyệt nạp có chip "Đã che: tên, SĐT, số TK" + dòng tổng, migration 0056 (#16; KHÔNG hiện ảnh, theo chủ dự án); CSV cảnh 4 sinh lại bền khi tải trễ 1 ngày (hệ số tự chọn 3,5 sau khi bộ che không còn che "Huỳnh Hoa") (#22). Unit 4170 passed, 2 skipped.

**Đã deploy** (`main` `65effe2`; chi tiết ở `docs/aws-resources.md`): migration 0055, 0056 (chạy thử 0001–0056 trên Postgres cục bộ trước); 5 zip; `YofinaTools`, `YofinaIngest`, `YofinaAgent`, `YofinaFrontend`; Runtime **v28**; Amplify **job 24**; `seed_demo.py` 4 tài khoản (đặt lại lần cuối sau khi kiểm). Khóa SSM thử (`/yofina/quota/chat_turns_per_day`, `/yofina/agent/reasoning_enabled`) đã xóa.

**Lỗi tìm thấy khi kiểm và đã sửa, đã deploy**:
- Zip ingest đóng thiếu `yofina_classify` (dùng lệnh cũ trong README thay vì `INGEST_BUILD_COMMAND`): `yofina-ingest-api` trả 500 khoảng 5 phút. Đã đóng lại, sửa lệnh trong `infra-cdk/README.md`. **Luôn đóng zip theo các hằng `*_BUILD_COMMAND` trong `infra-cdk/lib/`.**
- Luật rewrite SPA của Amplify trả `index.html` cho `.csv`: tệp mẫu cảnh 4 không tải được. Thêm `csv`, `pdf` vào luật + test CDK (`3b98fa2`).
- Mở chat rồi gửi tin ngay (khoảng 1,5 s) bị 409 `SESSION_BUSY` vì lượt làm nóng chưa xong: frontend chờ làm nóng (trần 15 s), 409 tự thử lại 1/2/4 s (`53a2887`).

**Kết quả kiểm trên app** (Chrome tự động 390×844, ảnh chụp và log CloudWatch): CSP có `frame-ancestors 'none'`; `giamkhao1` bị từ chối ở `/ops`, `minh` vào được; cảnh 1 Ăn uống cạn 23/11, nhãn "Cao"; cảnh 2 what-if khoảng 26 s trọn câu, khối đầu khoảng 1 s khi ấm, khối lập luận còn (1/4 bước bị bỏ vì `jar_mismatch` ở một lượt); cache Sonnet đọc 1.716 và 4.359 token ở lượt sau; cảnh 3 điểm 29 → 12, trụ 24 ngày; cảnh 4: 32 dòng tự vào Ăn uống, bản đề xuất mới khoảng 24 s sau khi xác nhận, "Số tính ngày 21/11", "Giữ bản cũ" hỏi lý do và lưu được; cảnh 5: màn duyệt sau 8,6 s, `B***`, chip "Đã che: tên"; trần lượt chat 2 → tin thứ 3 bị chặn đúng câu; công tắc lập luận tắt → không còn khối lập luận; 0 `turn_persist_timeout`. Tiền model của các lượt kiểm khoảng dưới 0,5 USD.

**Đã đóng** (đạt "Cách kiểm"): #8, #10, #12, #16, #17, #20, #22, #24, #25, #26, #27, #29 (cùng #18 từ trước). **Còn mở** đã có comment: #7 (ca lộ trình `--only` khi eval; quyết trường hũ có cấu trúc), #11 (đếm `audit_events`, đủ 3 lượt ấm), #13 (SSM trần chung ngày 2/12), #19 (chữ "Subscription" thô và ngày giai đoạn lệch trong bản lộ trình model sinh ở cảnh 4; chưa kiểm tài khoản 0 ₫), #5, #6, #23 (cần eval), #9 (cần tài khoản lịch sử ngắn), #14 (xem job đêm vài đêm), #15 (kiểm trên `lan`), #28 (đề xuất đóng), #32, #36.

**Thấy khi kiểm, chưa sửa lúc đó** (cả hai đã sửa 26/11: câu quỹ dự phòng lập bản mới từ Runtime v31; phần chia Ăn uống theo mức nền bền từ v32): câu "lập giúp mình lộ trình xây quỹ dự phòng 3 triệu trong 3 tháng" không lập bản mới mà hiện lại bản đang dùng, kèm câu "Bạn chưa nói mục tiêu này thuộc hũ nào…"; bản lộ trình v3 sinh lại ở cảnh 4 có bước "Đổi tỷ lệ chia lương" dồn 5.358.067 ₫ vào Ăn uống. Đáng xem lại trước khi quay video cảnh 4.

**Công cụ kiểm UI**: `%TEMP%\yofina-ui\run.js` (playwright-core điều khiển Chrome cài sẵn; mật khẩu đọc từ secret trong tiến trình, không ghi ra). Kịch bản JSON từng bước ở cùng thư mục. Thư mục tạm, không thuộc repo.
## Cập nhật tối 25/11: đợt 2 (lô A + lô C) đã merge vào `main` (đã deploy khuya 25/11, xem mục trên)

Người điều phối (Kiro CLI, máy của Phúc) giao 12 worker theo hai vòng, gộp qua `p6/wave2`, có một lượt review độc lập (`semantic_reviewer`) giữa hai vòng. Unit sau khi gộp: **4127 passed, 2 skipped**; CDK 89/89; contracts OK; vitest 1011 passed, 2 đỏ là hai test chập chờn có sẵn (`spending.test.tsx`, `phase3Chat.test.tsx`: chạy riêng thì xanh, trên `main` cũ cũng đỏ y vậy khi chạy cả bộ). Mỗi issue đã có comment trạng thái. #26 đã đóng (đo offline, không cần deploy, người điều phối chạy lại ra đúng số).

| Issue | Đã làm | Deploy/kiểm cần |
|---|---|---|
| #17 | `seed_demo.py`: nhóm `ops` chỉ cho `minh`, chạy lại gỡ khỏi `giamkhao*` | chạy `seed_demo.py`; `giamkhao1` mở `/ops/summary` bị từ chối |
| #16 | Ảnh biên lai hư cấu của `minh` có PII ở `/samples/minh_bien_lai_{1,2}.png`; cảnh 5 trong demo-script | frontend; đi cảnh 5 trên `giamkhao1` (≤ 10 s) |
| #13 | Trần theo tài khoản 100 lượt chat, 20 lần nạp/ngày (`yofina_core.quota`, SSM `/yofina/quota/*`), `warm()` dựng sẵn | zip ingest, `YofinaIngest`, `YofinaAgent` (IAM) + Runtime; thử trần 2; SSM trần chung ngày 2/12 |
| #7 | Kiểm lập luận với kết quả đã lưu (`advisor`), công tắc SSM `/yofina/agent/reasoning_enabled` (vắng = bật) | `YofinaAgent` + Runtime; `--only whatif-bnpl`, `roadmap-create-emergency-fund`; thử công tắc |
| #22 | `minh.json` chỉ còn v1, v2; PELT bắt từ hệ số 2,04; `/samples/minh_sao_ke_2_tuan.csv` (hệ số 2,1) | ledger (`YofinaTools`), frontend, `seed_demo.py`; chạy thử cảnh 4 (≤ 30 s) |
| #23 | Orchestrator `code_first` sau khóa `whatif_spec_source`, **mặc định `model`** (không đổi hành vi) | bật bằng env rồi 9 ca golden `--only` (~$0,4); chỉ đổi mặc định khi 9/9 đạt |
| #24 | `cachePoint` cho Sonnet 4.6 vai planner; ops tính giá đọc cache | Runtime; metric cache read > 0. Chưa làm: giá ghi cache trên ops |
| #25 | CQR hũ dày, PAV hũ thưa (bỏ PAV hũ dày), `recalibrate` bật; hũ thưa không nêu ngày cạn ở mọi màn (migration 0055) | `migrate.py`, zip forecast, `YofinaTools`, Runtime, frontend; tính lại dự báo; đi lại cảnh 1 |
| #27, #29 | Nhãn "Số tính ngày dd/mm" (ngày mô phỏng); "Giữ bản cũ" hỏi lý do tùy chọn, che PII, lưu `feedback.reason` | ledger trước hoặc cùng frontend |
| #28 | Không đo offline được biến thể có hũ Khác; giới hạn trên chỉ giảm 1,2 điểm (ngưỡng 3) | đề xuất đóng, chờ chủ dự án |
| #32, #36 | Tài liệu đồng bộ, ADR-0004 (28 dòng lệch), README viết lại (nháp), tờ A4 nháp `docs/submission/huong-dan-a4.md`, `scripts/make_submission_zip.py` | #32 còn vài README sót (ghi ở comment issue); #36 chờ số RC và `scan_repo.py` (B2) |

**Deploy gộp (đợt 1 + đợt 2, từ `main` `66807ad`)**, đã làm khuya 25/11 (mục trên); kế hoạch lúc đó: `cdk diff` từng stack trước; một luồng deploy tại một thời điểm; máy mở suốt khoảng 60–75 phút.
1. `uv run scripts/migrate.py` (tới 0055; chỉ thêm cột/thay hàm, code cũ và mới đều chạy được).
2. Đóng zip theo khối lệnh "đóng mọi zip" trong `infra-cdk/README.md` (ledger, agent, forecast) và lệnh zip ingest ở cùng file.
3. `uv run scripts/cdk.py deploy YofinaTools --require-approval never`, rồi `YofinaIngest`, rồi `YofinaAgent` (IAM đọc `/yofina/quota/*`, `/yofina/agent/reasoning_enabled`: nếu chỉ đẩy zip Runtime mà không deploy stack thì hai khóa này bị AccessDenied, trần giữ 100 và công tắc giữ bật, không báo gì).
4. `uv run scripts/agent_deploy.py` (Runtime).
5. Frontend: `uv run scripts/cdk.py deploy YofinaFrontend --require-approval never`; `uv run scripts/print_env.py frontend --write`; `npm.cmd run build` trong `frontend/`; `uv run scripts/deploy_frontend.py frontend/dist`.
6. `uv run scripts/seed_demo.py minh giamkhao1 giamkhao2 giamkhao3`, tính lại dự báo của 4 tài khoản.

**Kiểm sau deploy**: danh sách của đợt 1 (mục "Cập nhật chiều 25/11") cộng các ô "Deploy/kiểm cần" ở bảng trên. Tiền model ước tính: khoảng $1,5–2,5 (đợt 1 $0,5–1, 9 ca golden $0,4, hai ca #7, đi cảnh 1–6 trên trình duyệt).

**Rollback**: tắt nhanh không cần deploy: `/yofina/agent/reasoning_enabled = false` (khối lập luận), `/yofina/quota/chat_turns_per_day` nâng cao (trần). Lùi hẳn: `git revert` merge tương ứng, đóng lại zip, deploy lại stack/Runtime/frontend như trên. Migration 0055 không cần lùi.

**Lưu ý vận hành mới**:
- Trần 100 lượt/ngày tính cả tài khoản vận hành `minh`: lượt eval đầy đủ (khoảng 110 lượt, RC chạy 3 lần) sẽ chạm trần. Ngày chạy eval đặt `/yofina/quota/chat_turns_per_day` cao (ví dụ 1000) rồi xóa trước khi nộp (#34, #35).
- `recalibrate` bật làm đổi dải và % trên màn dự báo; hũ thưa (ví dụ Giải trí) không còn ngày cạn. Kịch bản demo hoặc eval nào nói ngày cạn của hũ thưa sẽ đổi chữ.
- Tệp CSV cảnh 4 gắn ngày neo 21/11: đặt lại rồi tải trong cùng ngày.
- `pii.py` có ba lỗi đã thấy (ghi ở comment #16): che sót số tài khoản tách nhóm, che thừa giờ, che nhầm tên quán "Huỳnh Hoa". Đã sửa khuya 25/11 (#16, mục trên).

**Câu hỏi đang chờ chủ dự án**: xem tin nhắn của người điều phối ngày 25/11 tối (vòng 1, đánh số). Tóm tắt: duyệt deploy gộp; #7 thêm trường hũ có cấu trúc vào bước lập luận; #22 hệ số CSV 2,1 hay 3; #28 đóng; #24 làm nốt giá ghi cache; #23 cho router trích `date_text` cho what-if; câu hỏi của #36 về cách khai tài sản có sẵn.

**Nhánh**: mọi nhánh `p6/*` của hai vòng đã nằm trong `main`; worktree `C:\moMo-wt\p*` đều sạch, không còn bản vá chưa merge.

## Cập nhật trưa 25/11: kiểm toán toàn dự án, hạn nộp thật là 03/12

- **Hạn nộp thật: 23:59:59 ngày 03/12/2026** (trang cuộc thi), không phải 10/12. Sau hạn không được sửa mã nguồn, slide, sản phẩm đang chạy; sản phẩm phải chạy tới hết 11/12. Lịch mới ở mục 8 của [phase 6](docs/plan/phases/phase-6-danh-gia-dong-goi.md): đợt 1 ngày 28/11, đợt 2 ngày 30/11 (hạn cuối tính năng mới), freeze tối 1/12, RC và eval cuối 2/12, nộp trước 18:00 ngày 3/12.
- Kiểm toán bằng 9 subagent (Kiro CLI điều phối): [tổng hợp](docs/research/2026-11-25-audit-tong-hop.md) và 9 ghi chú `docs/research/2026-11-25-audit-*.md`. Quyết định của chủ dự án ở mục 7 file phase 6 ("Chốt 25/11 sau kiểm toán").
- **Việc theo dõi trên GitHub Issues**: issue tổng [#2](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/2), 36 issue con (#3–#38) chia theo đợt, nhãn `ready-for-agent` / `ready-for-human`, có quan hệ blocked-by. Cấu hình skill ở `docs/agents/`.
- Đã làm trên AWS: đăng ký một email vào SNS `yofina-alerts` (đã xác nhận; trước đó topic có 0 người nhận). Yêu cầu tăng quota Bedrock qua API bị từ chối vì quota của tài khoản thấp hơn mặc định: phải mở case AWS Support (#3).
- Máy của Phúc đã có `uv` và `.venv`; unit 3920 passed, 3 skipped.

## Cập nhật chiều 25/11: đợt 1 đã code và merge vào `main`, chưa deploy lúc đó (đã deploy gộp khuya 25/11)

11 nhánh `p6/*` (worktree `C:\moMo-wt\p6-*`) đã merge vào `main` qua `p6/wave1`. Unit sau khi gộp: **4007 passed, 3 skipped**. CI GitHub Actions (#18) xanh trên nhánh `p6/ci`.

| Issue | Đã làm (code + test) | Deploy cần |
|---|---|---|
| #5, #6 | Bộ chấm eval không tự xác nhận số của model, chấm `reasoning`, `kind`; 8 ca đối kháng `evals/adversarial/phase6.jsonl`; writer coi chữ từ tệp nạp là dữ liệu không tin cậy | Runtime (writer, compact) |
| #8 | `minh` 120 ngày lịch sử, `giamkhao1–3` đều là `minh` | YofinaTools (gói ledger có `data/personas`) rồi seed lại 4 tài khoản |
| #9 | Cổng % theo độ dài lịch sử (hũ dày 47, hũ thưa 120 ngày); `docs/research/backtest-final.md` | Lambda dự báo |
| #10 | Lời gọi bị throttle không tính vào trần 4 lời gọi/lượt | Runtime, roadmap-regen |
| #11 | Ghi lượt sau RUN_FINISHED (thử lại 1 lần, `/ping` HealthyBusy), khóa `_ensure`, what-if chạy song song, cờ `covers_amount` | Runtime |
| #12 | Thẻ tiến độ hiện "Đang cân các phương án…" khi Analyst còn chạy | Amplify |
| #14 | Job đêm: `DatabaseUnavailable` + Retry cho `ListUsers` | YofinaTools + zip forecast-batch |
| #15 | Trả sau trên tài khoản không có hũ Nghĩa vụ: hàm chung `bnpl_pay_jar` | Ledger + Lambda dự báo |
| #18 | CI 5 job offline (pytest, frontend, CDK, contracts, gitleaks), `.gitattributes` cho CSV mẫu | xong (đóng) |
| #19 | Khả năng hụt bước 5%, không nói 100%/0%; tài khoản 0 ₫; kỳ lộ trình từ ngày lương; nhãn tiếng Việt ở So với bản cũ | Amplify, ledger, forecast tool, forecast-batch |
| #20 | CSP + `frame-ancestors 'none'` trên Amplify; che tên sau "chị/anh…" trong bộ nhớ | YofinaFrontend + deploy lại zip; Runtime |

**Deploy đợt 1 (kế hoạch lúc đó; đã deploy gộp khuya 25/11)**, theo thứ tự:
1. `uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 --keep-boto --extra data/personas:personas`, rồi `uv run scripts/cdk.py deploy YofinaTools --require-approval never`.
2. `uv run scripts/agent_deploy.py` (Runtime).
3. `uv run scripts/cdk.py deploy YofinaFrontend --require-approval never`; `uv run scripts/print_env.py frontend --write`; `npm.cmd run build` trong `frontend/`; `uv run scripts/deploy_frontend.py frontend/dist`.
4. `uv run scripts/seed_demo.py minh giamkhao1 giamkhao2 giamkhao3` (chuyển `giamkhao3` sang nhóm Cognito `persona-minh`).

**Kiểm sau deploy**: `curl -I` URL Amplify thấy CSP, đăng nhập, chat, nạp ảnh không bị "Refused to connect" (rollback: `git revert` commit CSP rồi deploy lại YofinaFrontend và zip); 3 lượt what-if ấm (đo thời gian tới RUN_FINISHED, trước khoảng 21 s); 0 `turn_persist_timeout`; số `audit_events` bằng số lượt; gửi tin thứ hai ngay sau tin đầu không bị 409 `SESSION_BUSY`; bấm xác nhận ngay sau khi có thẻ vẫn chạy; đo lại số cảnh 1 và cảnh 3 của `minh` rồi sửa `docs/plan/demo-script.md`; chạy 8 ca đối kháng mới `--only`; xem lịch sử `yofina-nightly` vài đêm.

**Rủi ro còn mở từ đợt 1**: hũ Nghĩa vụ phủ 0,728 ở mọi độ dài lịch sử nhưng vẫn hiện %; client Data API chưa coi `57P01` là lỗi tạm thời (C2); lộ trình mới bắt đầu ở ngày lương kế (không còn chặng bắt đầu hôm nay); thẻ tiến độ chưa thử trên trình duyệt; vitest có test chập chờn khi máy tải nặng.

**Issue chưa làm**: #3 (chờ AWS duyệt quota), #4 (đi 6 cảnh), #7 (lập luận nhất quán + công tắc SSM), #13 (trần lượt gọi), #16 (cảnh 5), #17 (bỏ `ops` khỏi tài khoản giám khảo), #21 (đo sau đợt 1), #22–#29 (đợt 2), #30 (chờ BA chốt C-02), #31 (20 câu giữ riêng), #32 (tài liệu, ADR-0004), #33 (số kinh doanh), #34–#38 (RC và nộp). Lô kế tiếp đề xuất: #7, #13, #17, #16, rồi deploy đợt 1.

## Quy ước cho người điều phối

### Chưa duyệt

- Deploy gộp đợt 1 + đợt 2 **đã làm khuya 25/11**; sáu lần deploy ngày 26/11 (Runtime v29–v34) cũng do chủ dự án duyệt từng đợt. Deploy sau này vẫn phải hỏi trước, kèm chi phí, tác động, cách rollback. Không deploy, không seed, không đặt SSM, không chạy eval trên Runtime, không gọi Bedrock khi chưa hỏi. Khi xin duyệt: nêu chi phí, tác động, cách rollback.
- Việc cần người hoặc chờ điều kiện: #3, #4, #21, #30, #31, #33, #34, #35, #37, #38.

### Quy ước giao việc cho worker (đã dùng ở đợt 1 và đợt 2)

- Mỗi issue một worker, worktree riêng (`git worktree add <thư mục> -b p6/<tên> main`, hoặc `-B p6/<tên> origin/p6/<tên>` cho nhánh đã có), chỉ sửa file trong phạm vi được giao, theo skill `/tdd` với seam do người điều phối chốt sẵn (không hỏi người dùng), commit từng phần xanh ngay (mạng hay làm đứt worker), không push, không đụng `main`.
- Commit tiếng Việt, kết bằng `(#số issue)`, **không thêm `Co-authored-by` hay trailer nào** (yêu cầu của chủ dự án).
- Worker không sửa `docs/ai-log/`, `HANDOFF.md`, file phase 6, issue; người điều phối làm các việc đó.
- Chạy tối đa khoảng 6 worker song song. Lần trước chạy 11 cùng lúc thì 6 cái bị lỗi mạng, phải chạy lại.
- Gộp qua một nhánh tích hợp (ví dụ `p6/wave2`), xung đột kiểu "cả hai cùng thêm" thì giữ cả hai, chạy `uv run pytest tests/unit libs/yofina_core/tests -q -p no:cacheprovider` (mốc **5260 passed, 2 skipped** ở `a846281`) trước khi fast-forward `main` và push. `git fetch` trước: BA (bloan0908) hay commit vào `main`, và đầu `docs/ai-log/2026-11.md` hay xung đột (gộp tay, giữ mọi entry, mới nhất ở trên).
- Sau khi gộp: comment trạng thái lên từng issue (`gh issue comment <n> --body-file <tệp>`; PowerShell không có heredoc). **Chỉ đóng issue khi đã deploy và kiểm theo mục "Cách kiểm" của issue**, trừ việc không cần deploy (như #18).
- Repo public: không ghi email, mật khẩu, account ID, thông tin thật về tài khoản AWS vào file hay issue.
- Bẫy đã gặp: ca eval `leak-1` phải hỏi tài khoản demo khác `minh` (giờ là `lan`); `giamkhao1–3` đều là persona `minh`.
- Rút ra ở đợt 2: giữ sẵn số migration cho từng worker (0055, 0056… để không trùng); chỉ rõ dòng nào trong file dùng chung (ví dụ `ReadConfig` của `agent-stack.ts`, khóa cuối `defaults.json`) để xung đột chỉ là "cả hai cùng thêm"; worktree mới cần `uv sync --frozen`, còn worker đụng CDK/frontend/contracts thì cần `npm.cmd ci` trong `infra-cdk/`, `frontend/`, gốc repo; `.venv` không có Pillow nên 2 test ảnh bị skip (`uv run --with pillow pytest …` để chạy); vitest cả bộ có 2 test chập chờn khi máy tải nặng; trước mỗi commit, push chạy `uv run python scripts/scan_repo.py` (có từ 26/11, phải ra 0 phát hiện). Lượt review độc lập sau vòng đầu bắt được lỗi thật (tập hũ của lập luận, trần chặn eval), nên giữ bước này.

## Cập nhật rạng sáng 25/11 (sau khi viết bản trên)

- **Bộ nhớ đã sửa gốc** (nhánh p5/mem-extract, ac2a4fe): bước hợp nhất mặc định của AWS bỏ sở thích có thời hạn ("temporary states") và Nova Lite không theo chỉ dẫn; nay override cả hợp nhất, đổi sang Haiku 4.5. `memory-state-preference` và `memory-knowledge-update` đạt (mỗi ca một lần). Mục A.2 bên dưới coi như xong; chi tiết ở file phase 5 và agentcore-memory-design.md mục 2.2a.
- **Phase 6 đã có kế hoạch** ([phase-6](docs/plan/phases/phase-6-danh-gia-dong-goi.md)), chủ dự án chốt Q1–Q9 theo đề xuất; Q10–Q15 còn chờ. Đợt 7 kiểm toán prompt (chip mang ý định có cấu trúc) hoãn tới sau cuộc thi.
- **Luồng K (agent như người tư vấn) K1–K3 đã deploy** (589eb1c, Runtime v27, Amplify job 21): khối mới `reasoning` hiện 2–5 bước lập luận và một câu kết luận trong what-if và lộ trình, thu gọn "Xem cách mình cân nhắc". Còn mở:
  - Độ trễ tăng khoảng 6 s mỗi lượt có lập luận (what-if trọn câu 37,9 s); lập luận hiện sau khi Analyst xong chứ chưa hiện trong lúc chờ (cần stream có cấu trúc, làm cùng D2).
  - Lập luận có thể nói khác bản đã lưu (ca lộ trình: lập luận nói chuyển từ hũ Giải trí, bản lưu chuyển từ Đi lại) — cần kiểm nhất quán giữa lập luận và kết quả đã lưu trước demo.
  - "Kiểm tra trước khi chi" chưa có lập luận (đường này không có Analyst); bộ chấm eval chưa kiểm số trong khối `reasoning`.

## Đang ở đâu trong kế hoạch

Kế hoạch: [docs/plan/master-plan.md](docs/plan/master-plan.md), sáu phase trong [docs/plan/phases/](docs/plan/phases/). Hạn nộp 23:59:59 ngày 03/12/2026 (mục "Cập nhật trưa 25/11").

| Phase | Trạng thái |
|---|---|
| 1. Nền và lát dọc | Xong 22/11 |
| 2. Ví mô phỏng và dự báo | Xong 22/11 |
| [3. What-if, kiểm tra trước khi chi](docs/plan/phases/phase-3-what-if-va-kiem-tra.md) | Đóng 23/11 |
| [4. Chống chịu, lộ trình, phân hũ tự động](docs/plan/phases/phase-4-chong-chiu-lo-trinh.md) | Đóng 24/11 (tiêu chí 6: tỷ lệ phải hỏi 17,4%, mục tiêu < 10%) |
| [5. Nạp dữ liệu, hồ sơ hành vi, bộ nhớ, trace](docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md) | **Code xong, deploy Runtime v26, đo xong**. Kết quả từng đợt ở mục "Nghiệm thu 24/11" và các mục "Kiểm lại…", "Đo sau đợt sửa kiểm toán và bộ nhớ (Runtime v25)", "Sửa nhỏ sau v25". Còn: tiêu chí 3 (OCR), đi lại 6 cảnh trên UI mới, rồi điền bảng đóng phase |
| [6. Đánh giá, cứng hóa, đóng gói](docs/plan/phases/phase-6-danh-gia-dong-goi.md) | **Đang làm**: đợt 1 và đợt 2 deploy khuya 25/11 (v28); bộ hũ mặc định, đợt "agent thích ứng", router Haiku, 5 lỗi trên app và lỗi sau v33 (#39) deploy 26/11 (v29–v34); eval đầy đủ trên v34 tối 26/11 (104/115 qua Runtime). Còn: lỗi và giới hạn còn lại sau v34 (mục "Còn mở"), #40, #41, #44, #46 trước hạn tính năng 30/11; cứng hóa #45 trước freeze 01/12; eval RC 02/12 (#34) |

## Đã làm trong ngày 24/11 (chi tiết ở ai-log và file phase 5)

- **Bộ nhớ (AgentCore Memory)** sửa gốc, không chặn câu chữ bằng mã: khối bộ nhớ đưa vào prompt dạng dữ liệu có cấu trúc, bỏ câu mẫu; trích xuất "built-in with overrides" bằng Nova Lite (tiếng Việt, chỉ lời khẳng định, giữ chữ thời hạn, câu đổi ý viết thành lời khẳng định mới); bỏ strategy tóm tắt phiên; không ghi lượt hỏi đáp thuần và lượt `profile_update`. Đổi ý đo thật: bản cũ mất hẳn, `DELETE /memory` xóa sạch mọi thứ API cho kiểm. Nghiên cứu: [long-term-memory-research.md](docs/research/long-term-memory-research.md), thiết kế: [agentcore-memory-design.md](docs/research/agentcore-memory-design.md).
- **Kiểm toán prompt chống overfit** ([prompt-overfit-audit.md](docs/research/prompt-overfit-audit.md)): đã làm đợt 1–4, 6 (bỏ mã chết, writer không còn khuôn "đúng N câu", chặn hỏi lại bằng mã ở `clarify.CLARIFY_INTENTS`, router trích ý định phụ thay bảng từ khóa/regex, gom prompt ảnh). Có test CI cấm prompt chứa cụm 5 từ trùng câu eval. Bộ 18 câu diễn đạt lại cho router: 18/18.
- **Luật suitability thứ bảy** `emergency_not_for_discretionary` (warn): không khuyên tiêu quỹ dự phòng cho khoản không thiết yếu.
- **Nạp chứng từ ngoại tệ**: quy đổi sang VND theo tỷ giá bán Vietcombank theo ngày (API công khai), dòng vào hàng chờ duyệt, sửa được số VND; mã lỗi mới `INGEST_NO_TRANSACTIONS` kèm lý do. Tool Gateway `knowledge___get_exchange_rate` dùng chung `yofina_core.fx` cho agent chat. Rút tiền mặt ngoài phạm vi; màn tra soát không tạo dòng. [ingest-fx-rates.md](docs/research/ingest-fx-rates.md).
- **Giao diện**: bảng màu mới, cảnh 1–4 có chuyển động, biểu đồ chi tiêu B1/B2/B3/B5/B6/B7 ([spending-visualization.md](docs/research/spending-visualization.md)), giảm chữ (luật §9) và "mỗi thông tin một nhà" (§10) trong [ui-design-review.md](docs/research/ui-design-review.md). REST mới `GET /cashflow`.

## Đang chạy trên AWS (`ap-southeast-1`)

- Bảy stack đều `*_COMPLETE`. Danh sách tài nguyên: [docs/aws-resources.md](docs/aws-resources.md).
- **Runtime `yofina_agent` v36**, **Amplify job 30**, migration tới **0059**, mã `e784723` (deploy sáng 28/11; mục "Trạng thái trưa 28/11"). App: `https://main.dcrwn4u7vqklo.amplifyapp.com`.
- Memory `yofina_memory` (id không đổi) với hai strategy override `preferences_vi`, `facts_vi`: override cả trích xuất lẫn hợp nhất, model **Claude Haiku 4.5** (khoảng $0,007–0,0125 mỗi lượt được ghi; quota 10 RPM dùng chung với model dự phòng của vai `small`). Lambda nạp gọi ra API tỷ giá Vietcombank (không VPC, không NAT).
- Sáu tài khoản demo (`minh`, `lan`, `khoa`, `giamkhao1`–`3`), mật khẩu trong secret `yofina-demo-accounts`. **Mật khẩu đã lộ trong lịch sử chat 23/11: đổi trước buổi chấm.** Chỉ `minh` thuộc nhóm `ops` (#17; `giamkhao1` bị từ chối ở `/ops`, kiểm lại 26/11).
- Aurora `yofina-db` min 0 ACU (lần gọi đầu chậm 15–20 giây). **Trước buổi demo** lên 0,5 ACU: `uv run scripts/cdk.py deploy YofinaData --require-approval never -c dbMinAcu=0.5`, xong trả về `-c dbMinAcu=0`.

Lệnh hay dùng (chi tiết ở `scripts/README.md`, `infra-cdk/README.md`): `uv run pytest tests/unit libs/yofina_core/tests -q`; `uv run scripts/cdk.py diff|deploy <Stack> --require-approval never`; `uv run scripts/agent_deploy.py` (có thể exit 1 dù READY); `uv run scripts/migrate.py`; `uv run scripts/seed_demo.py <persona>`; frontend: `uv run scripts/print_env.py frontend --write`, `npm.cmd run build` trong `frontend/`, `uv run scripts/deploy_frontend.py frontend/dist`. Đặt `PYTHONIOENCODING=utf-8` khi chạy script in tiếng Việt trên Windows.

## Số đo mới nhất

- Test cục bộ ở `a846281` (mã Runtime v33, 26/11): unit 5260 passed, 2 skipped; `tests/local_pg` 285; vitest 1118; CDK 99/99 đo ở `1303eaf` (CDK không đổi từ đó). Số trên app sau v34: mục "Trạng thái tối 26/11".
- Eval đầy đủ gần nhất: Runtime v36, 28/11 09:57–10:51, qua Runtime 104/119 ([eval-report.md](docs/research/eval-report.md), mục "Trạng thái trưa 28/11"). Lượt trước (Runtime v34, 26/11 21:06–22:13): qua Runtime 104/115 ca, golden phase 3 29/33, phase 4 13/16, phase 5 13/16; adversarial phase 3/4/5/6 16/16, 12/12, 14/14, 7/8; router diễn đạt lại 18/18; router Haiku 119/119 lượt, 0 lần rơi về Nova. 11 ca trượt: 7 do bộ chấm `evals/run.py`, 4 do model (lùi an toàn); không ca nào lộ lỗi mã sản phẩm (mục "Còn mở" (b), (c)). Lượt trước (v25, 24/11): golden 31/31, 14/14, 11/15 (15/15 sau chạy lại); adversarial 16/16, 12/12, 14/14; diễn đạt lại 18/18. OCR real 9/11 ở v25 (r08 đã sửa và đạt ở v26, r12 sai ngày do ảnh mờ), chưa đo lại.
- Chi phí một lượt eval đầy đủ khoảng **2,0 USD** ở v34 (115 ca; log ghi 1,91 USD, trong đó Sonnet planner 1,38, Haiku router 0,36); ở v25 khoảng 2,2–2,5 USD. Vì vậy: **chỉ chạy eval đầy đủ khi đã deploy xong và ổn hẳn; bình thường chỉ chạy vài ca `--only`**.

## Việc kế tiếp

### A. Phúc / Claude Code (người điều phối)

1. Sau khi Học đi cảnh (mục B): điền bảng đóng phase 5; quyết tiêu chí 3 (OCR 9/11 hay 10/11 sau khi đo lại cả bộ một lần ở mốc đóng phase).
2. Bộ nhớ còn lệch (ca `memory-state-preference` trượt ở v26): Nova Lite vẫn chép nguyên câu thành "sự thật" (ngôi thứ nhất, lặp sở thích) và bỏ chữ "tháng này". Hướng: override luôn bước hợp nhất (P1-6 trong nghiên cứu) hoặc thử model trích xuất mạnh hơn; đo bằng vài ca nhỏ.
3. Đợt 5, 7, 8 của kiểm toán prompt (đo lại rồi bỏ lớp vá quanh lỗi ngoài phạm vi; chip mang ý định có cấu trúc; writer cho câu đang dựng bằng mã).
4. Phase 6 (đánh giá, cứng hóa, đóng gói).
5. Quyết định treo: bật CloudWatch Transaction Search không.

### B. Học

Đăng nhập trên máy tính (không cần điện thoại) ở `https://main.dcrwn4u7vqklo.amplifyapp.com`. Ghi kết quả (đạt / lỗi kèm ảnh chụp, giờ) vào mục "Kiểm sau" của file phase 5 hoặc gửi Phúc. Bấm "Đặt lại dữ liệu demo" (Hồ sơ) trước mỗi việc.

1. **Đi lại 6 cảnh trên giao diện mới** với `giamkhao1` (tiêu chí 10): theo [figma-ui-design.md §8.2](docs/research/figma-ui-design.md) và [demo-script.md](docs/plan/demo-script.md), bấm giờ từng cảnh. Giao diện đã đổi nhiều: Tổng quan chỉ còn "hôm nay" (lộ trình và Trả sau chỉ hiện khi có việc), "Hũ nào sắp cạn" chuyển về Nhìn trước, biểu đồ chi tiêu ở màn Hoạt động (Theo hũ / Theo ngày). Ghi chỗ nào khó tìm, chữ nào còn dài, chỗ nào còn lặp.
2. **Nạp chứng từ ngoại tệ**: nạp một hóa đơn/biên lai bằng USD (ví dụ hóa đơn dịch vụ thu qua thẻ): dòng vào hàng chờ với số VND ước tính, mở dòng phụ thấy tỷ giá Vietcombank và ngày, sửa được số VND, chốt được. Nạp ảnh không phải chứng từ và ảnh màn xác nhận chưa chuyển: câu báo đúng lý do.
3. **Hỏi agent tỷ giá**: "50 USD là bao nhiêu tiền Việt?", "Mua tai nghe 60 USD bằng hũ Giải trí có đủ không?" — số VND phải khớp tỷ giá Vietcombank của ngày mô phỏng.
4. **Bộ nhớ**: phiên 1 gõ một sở thích (ví dụ ưu tiên một hũ). Đợi 1–2 phút, đăng xuất/đăng nhập lại, hỏi "Tháng này còn dư, nên để vào hũ nào?": câu trả lời dùng đúng sở thích, không gán cho mình điều chưa nói. Đổi ý ("giờ ưu tiên hũ khác") rồi xem Hồ sơ → Bộ nhớ của tôi: chỉ còn ý mới. Xóa một mục: biến mất ngay.
5. **Biểu đồ chi tiêu** (`minh`, màn Hoạt động): số kỳ này khớp câu trả lời khi hỏi agent "Kỳ này mình tiêu bao nhiêu, so với kỳ trước?".

Việc code nhỏ Học nhận (mỗi việc một nhánh, chỉ unit test, gửi Phúc merge; không chạy eval):

6. Màn So với bản cũ (L3) ghi "Loại bước", "Giai đoạn" bằng mã thô (`set_aside`, `phase_id`): sửa ở `gateway/tools/ledger/yofina_ledger/roadmap_logic.py`.
7. Lambda sinh lại lộ trình (`pipelines/roadmap/`) âm thầm bỏ bản đề xuất đang chờ: ghi lý do vào bản mới hoặc phát notice.
8. Router/tiện ích ngày chưa đọc "trong 6 tháng"; luật dự phòng không đọc hũ tên chứa "mua" ("Mua xe").
9. Bộ đọc số bằng mã (`router._code_params`) đọc "1200 USD" thành 1.200 ₫ khi router không trích `currency`; agent chưa truyền `date` cho `get_exchange_rate`.

### C. Việc để sau (ghi trong file phase 4, 5 và các file nghiên cứu)

- `GET /cashflow`: phần tách khoản cố định/Trả sau đang cộng bằng mã (khoảng 10 truy vấn mỗi lần): chuyển thành hàm SQL bằng migration.
- `turn_persist_timeout` xuất hiện mỗi ca eval ở v25 (eval v34 chỉ ghi 1 lần), chưa rõ nguyên nhân; `numeric_ungrounded` 2 lần ở v25 (lời bị bỏ, ca vẫn đạt).
- `period_end` của lộ trình chưa theo ngày lương; tỷ lệ phải hỏi của phân loại 17,4%.
- Bước lập lộ trình chưa đọc bộ nhớ; học từ `feedback` (đếm loại đề xuất bị từ chối, P1-5 nghiên cứu bộ nhớ).
- Guardrail `ApplyGuardrail` p50 446 ms > 400 ms.
- Ghi chú duyệt nhãn của 25 ảnh thật bị lỗi mã (dấu thành `?`) từ commit a70b9a3; một số tài khoản 8 chữ số từng nằm trong ghi chú cũ (đã xóa khỏi file, còn trong lịch sử git — chủ dự án quyết có viết lại lịch sử không).

## Cách làm việc

Claude Code là người điều phối: plan, giao mỗi việc cho một worker `kiro-cli chat --no-interactive --trust-workspace --trust-all-tools --model claude-opus-5.5 --effort high` trong worktree riêng `C:\moMo-wt\<việc>`, review diff, merge, chạy unit. Nhiều nhánh thì gộp lại, deploy một lần, eval một lần. Quy tắc của chủ dự án:

- **Không hardcode, không giả lập** ([master-plan mục 2](docs/plan/master-plan.md#2-quyết-định-áp-dụng-cho-mọi-phase)).
- **Không vá prompt/mã cho vừa vài ca eval** (không câu mẫu, không ví dụ chép từ eval, không lọc câu chữ của model bằng mã); lỗi hành vi thì tìm nguyên nhân gốc và sửa theo nguyên tắc chung.
- **Eval tốn tiền** (khoảng 2,0 USD/lượt đầy đủ ở v34, 2,2–2,5 USD ở v25): chỉ chạy đầy đủ ở mốc deploy đã ổn; bình thường chỉ vài ca `--only`, mỗi ca một lần.
- **Giao diện ít chữ**: chỉ để chữ cho phần quan trọng, phần giải thích thu vào mục bấm mở; mỗi thông tin một màn là nhà.
- Một luồng deploy tại một thời điểm; `cdk diff` trước mỗi deploy. Commit không Co-Authored-By.

## Quyết định đã chốt

- Region `ap-southeast-1`; không kéo FAST; frontend theo [ADR-0001](docs/decisions/0001-frontend-stack.md) và Figma; Cognito tắt tự đăng ký; bộ model (Sonnet 4.6, Nova 2 Lite, Kimi K3, Cohere); xác nhận bằng token dùng một lần do server cấp, Cedar là lớp phụ; sản phẩm trả sau mô phỏng.
- 24/11: cắt RAG; cảnh 4 để agent lập lộ trình trong chat; bộ nhớ theo best practice AgentCore (một Memory, namespace theo `sub`, override trích xuất, `IngestData`, che PII, không lưu số tiền, không nhân bản dữ liệu Aurora); rút tiền mặt ngoài phạm vi; màn tra soát không tạo dòng; ngoại tệ quy đổi theo tỷ giá bán Vietcombank, người dùng duyệt.
- Quyền với AWS: được tạo và sửa tài nguyên `yofina-*` (tag `project=yofina`, ghi vào aws-resources.md) ở `ap-southeast-1`; hỏi trước với thứ tính tiền theo giờ đáng kể và trước khi xóa thứ không do dự án tạo; không đụng `jars-dev*`, `Jars*`, `CDKToolkit`.

## Quyết định còn treo

- Bật CloudWatch Transaction Search không.
- Viết lại lịch sử git để xóa số tài khoản cũ trong ghi chú nhãn không.
- Hạn nộp chính xác, trọng số chấm, giữ tên Yofina ([open-questions.md](docs/requirements/open-questions.md)).

## Môi trường (kiểm 24/11, tự kiểm lại mỗi phiên)

- Windows 11, repo `C:\moMo` (Phúc), nhánh `main`, remote GitHub public. Python 3.13, uv, Node 24. `npm.ps1` bị chặn trong PowerShell: dùng `npm.cmd`. Console mặc định cp1252: đặt `PYTHONIOENCODING=utf-8`.
- AWS CLI dùng `aws login` (phiên 12 giờ). Không ghi account ID vào tài liệu.
- `kiro-cli` 3.5.0, model `claude-opus-5.5`.
- MCP: `aws-docs`, `agentcore`, `aws-mcp` (có lúc mất kết nối; dùng AWS CLI chỉ đọc thay thế).

## Lưu ý

- Repo public: không commit account ID, ARN có account ID, secret, token, mật khẩu demo, email.
- Mọi lời gọi model đi qua `yofina_core.llm` có giới hạn tốc độ và trần mỗi ngày (bảng `yofina-usage`). Hết trần thì ghi nhận, không chạy lại.
- `evals/results/`, `evals/ingest/results/` không vào git.
