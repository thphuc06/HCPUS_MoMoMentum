# HANDOFF — ảnh chụp trạng thái hiện tại

> **Quy ước**: cập nhật (ghi đè phần trạng thái bên dưới) vào **cuối mỗi phiên làm việc**. HANDOFF là ảnh chụp hiện tại; lịch sử thay đổi nằm ở [docs/ai-log/](docs/ai-log/README.md). Đầu phiên mới: đọc file này trước.

Cập nhật lần cuối: **2026-11-26 rạng sáng** (Claude Code điều phối worker `kiro-cli` `claude-opus-5.5`). Nhánh `feat/default-six-jars` của Học **đã gộp vào `main` và đã deploy** (Runtime **v30**, Amplify **job 26**, migration tới **0059**; `main` `c65fa98` là bản đang chạy), đã kiểm trên app, không chạy eval: xem mục "Cập nhật rạng sáng 26/11" ngay dưới. Đợt 1 và đợt 2 phase 6 đã deploy từ khuya 25/11. Phase 5 vẫn chưa đóng chính thức (tiêu chí 3 OCR, đi lại 6 cảnh, xem mục B).

## Cập nhật rạng sáng 26/11: gộp bộ hũ mặc định theo mục đích (#39), đã deploy, kiểm trên app

Chủ dự án (đêm 25/11) duyệt: gộp nhánh của Học, push, migration, deploy, kiểm vài ca mới trên app, **không chạy eval**; migration của nhánh đổi số thành 0057–0059; tài khoản mới nhận 3 hũ mặc định; tài khoản demo có thêm hũ tự thêm để vẫn tách được hành vi theo ăn uống, đi lại. Việc theo dõi ở issue [#39](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/39). `main` = `4cf2bdb` lúc deploy.

**Bộ hũ hiện hành**
- **Tài khoản mới (onboarding)**: Chi hằng ngày 42 / Nghĩa vụ 33 / Dự phòng 25 (`jar_templates.is_default`, migration 0059). Hũ khác (Quỹ dồn, Mục tiêu, Tích lũy dài hạn, bảy hũ cũ) là hũ tự thêm. Bước 3 onboarding có kê khai và đề xuất tỷ lệ (`POST /jars/split-proposal`). Quay lui về bộ bảy cho tài khoản tạo sau đó: `uv run scripts/cdk.py deploy YofinaTools --require-approval never -c onboardingJarLayout=legacy`.
- **Tài khoản demo (sau "Đặt lại dữ liệu")**: Nghĩa vụ (gộp Hóa đơn cũ), Dự phòng (`buffer`), cộng hũ tự thêm Ăn uống, Đi lại, Giải trí, Du lịch (mã `muc_tieu`, `goal`, chỉ persona có hũ Du lịch mang mục tiêu), Đầu tư (`dau_tu`, `long_term`, 0 ₫). **Không có hũ Chi hằng ngày** (câu chuyện: người dùng đã tách hũ này thành ba hũ chi). `minh`, `vy` 7 hũ; `lan`, `khoa` 6 hũ. Tỷ lệ suy từ spec persona qua ánh xạ mã hũ (`yofina_core.wallet.LEGACY_JAR_ALIASES`, `data/personas/six_jars.py` `apply_demo_layout`). Lý do không dùng bộ demo 4 hũ của nhánh: PELT, hồ sơ hành vi, cờ đổi hành vi tính theo mã hũ; cảnh 1 và cảnh 4 dựa vào hũ `an_uong`. Phân tích theo loại chi (`tx_type`) bên trong một hũ gộp là việc để sau.
- Ví cũ 7 hũ trên Aurora (chưa đặt lại) vẫn đọc ghi được (`purpose` NULL).

**Quy tắc đổi theo nhánh**: hũ trả nghĩa vụ và Trả sau dùng chung `resolve_obligation_pay_jar` (hũ đã lưu, hũ chọn, `nghia_vu`, hũ obligation đầu tiên); ví không có hũ obligation mà mua bằng Trả sau thì phải chọn hũ trả (agent và màn chuyển tiền hỏi; lỗi tool mang `field: pay_jar`). Khoản Trả sau ghi từ trước chưa có hũ trả vẫn lùi về `bnpl_pay_jar` trong dự báo (giữ sửa lỗi #15). Ngày đến hạn Trả sau của `minh` trên ví demo là ngày 3 (điều khoản mô phỏng; BR-22 ghi ngày 5).

**Số đo trên app sau deploy** (`giamkhao1`, `minh`; ảnh ở `C:\moMo-wt\logs\ui-F\`, máy của Phúc, ngoài repo): cảnh 1 Ăn uống 380.000 ₫ cạn 23/11, nhãn Cao; cảnh 2 trọn câu 34 s, hũ Nghĩa vụ liệt kê Tiền điện 26/11 và Trả sau 03/12 (2.200.000 ₫), thiếu 1.161.791 ₫; cảnh 3 điểm 29 → 12, trụ 25 ngày; cảnh 4: 32 dòng vào Ăn uống, bản v3 sau khoảng 30 s, không còn chữ "Subscription", giai đoạn đầu 21/11–05/12, bước lớn nhất vào Ăn uống 2.657.800 ₫; cảnh 5 màn duyệt sau 8,5 s, chip "Đã che: tên". Tài khoản mới (tạo tạm bằng admin rồi xóa): 3 hũ 42/33/25, kê khai trọ + điện ra đề xuất 36/39/25. Log khoảng giờ kiểm: 0 `ContractMismatch`, 0 `Traceback`, 0 lỗi 5xx, 1 `turn_persist_timeout`. Tiền model khoảng 0,3–0,5 USD.

**Test** (`4cf2bdb`): unit 4390 passed, 2 skipped; `tests/local_pg` 264 passed (10 ca đỏ sẵn trên `main` cũ đã viết lại theo #8, #22, #19); `db_local_check.py` 57/57; vitest 1056; CDK 98; tích hợp sau deploy 93 đạt, 1 đỏ (`test_phase3_engine.py::test_chuyen_250k…`, test cũ).

**Sửa kèm trong đợt này**: bản lộ trình sinh lại ở cảnh 4 (#19): nhãn loại nghĩa vụ tiếng Việt đưa vào ngữ cảnh model, giai đoạn đầu từ hôm nay tới ngày lương, kiểm số tiền bước bằng mã; khử trùng dòng nạp so tên đối tác theo từ (`same_party`); hũ không có gì rút tiền không có ngày cạn; sàn thiết yếu của hóa đơn tính theo loại giao dịch trên hũ obligation; đề xuất tỷ lệ không cắt hũ thiết yếu trước; route `POST /jars/split-proposal` trên HTTP API; test tĩnh so `openapi.yaml` với route CDK.

**Phát hành lần sau nhớ**: Runtime cũ kiểm chặt trường trả về (`extra=forbid`), nên khi Lambda thêm trường mới phải **deploy Runtime trước, Lambda sau** (`tests/unit/agent/test_runtime_lambda_compat.py`); không quay lui riêng Runtime. `migrate.py` chạy mọi file chờ: muốn dừng ở một số thì dùng `--dir` với thư mục tạm. Snapshot Aurora `yofina-db-pre-0057-20261126` còn giữ (xóa khi không cần lùi nữa).

**Còn mở sau đợt này**
- **Đã sửa và deploy lần hai lúc 05:09** (`c65fa98`, Runtime v30, Amplify job 26, đóng lại cả 5 zip Lambda): chi tiết hũ không có khoản chi dự kiến ghi "Chưa có tiền, không có khoản chi dự kiến trong 30 ngày." (hũ 0 ₫) hoặc "Không có khoản chi dự kiến trong 30 ngày." thay cho "Đang hết tiền"; lỗi nghiệp vụ 4xx do hàm SQL ném ghi WARNING `data_api_business_error` thay cho ERROR; `test_chuyen_250k…` và `test_phase4_live.py` 06–10 viết lại theo dữ liệu hiện hành và chạy đạt (6/6). Test: unit 4402, `tests/local_pg` 266, vitest 1060. Cả 6 tài khoản demo đã đặt lại lúc 05:06.
- Thấy khi kiểm lần hai, chưa sửa: hũ Du lịch và Dự phòng ghi "Không có khoản chi dự kiến trong 30 ngày." dù lịch sử có khoản rút "Bù tiền ăn cuối tháng" (đúng theo số dự báo, cần xem lại lời); trong khung chat, nhãn mốc trên biểu đồ dự báo bị cắt ở mép trái và chồng nhãn "Lương về 05/12"; `JarStatusChip.tsx` ghi "Đã hết tiền" cho mọi hũ 0 ₫ chưa có dự báo; `writer.py` có thêm một câu giải thích trường `no_outflow_expected` chưa đo bằng eval.
- Trên ví demo, đề xuất tỷ lệ khi kê khai và bản v3 cảnh 4 đưa Giải trí về 0% (đúng quy tắc "cắt hũ không thiết yếu trước", nhưng nên có sàn cho hũ không thiết yếu): chờ chủ dự án quyết.
- Câu "lập giúp mình lộ trình xây quỹ dự phòng…" không lập bản mới: router không trích hũ nên `turn.py` mất ý định tạo (dòng `create = action == "create" or goal is not None`), và hũ Dự phòng (`buffer`) không đặt mục tiêu được. Chưa sửa vì đổi hành vi agent mà không có eval.
- Hiếm gặp, chưa sửa: what-if Trả sau có thể tính trùng khoản cũ chưa lưu hũ trả trên ví không có hũ obligation; hũ đã lưu thắng hũ người dùng chọn cho khoản Trả sau cùng ngày đến hạn.
- Tài liệu BA: B2a và C-12 đã ghi quyết định 26/11; BR-63..78 và BR-79..84 (trang Notion "Feedback hũ") chưa đồng bộ vào `docs/ba/` (việc của BA). Eval, độ chính xác phân loại 92% và hiệu chỉnh dự báo đo trên bộ 7 hũ: tài khoản demo giữ các hũ chi cũ nên số cũ còn dùng được cho demo; ví 3 hũ chưa có số đo riêng.
- Lượt eval cuối (#34) sẽ chạy trên bộ hũ demo mới: ca golden nào hỏi hũ Hóa đơn hoặc "hũ Du lịch" theo mã cũ cần xem lại trước khi chạy.

## Cập nhật khuya 25/11: đã deploy gộp đợt 1 + đợt 2, kiểm trên app (không chạy eval)

Chủ dự án duyệt deploy và dặn: chỉ kiểm vài ca trên app thật, **không chạy eval** (để lượt eval tới gần cuối). Trước deploy làm thêm 4 việc nhỏ (worker `kiro-cli --model claude-opus-5.5 --effort high`): câu "hũ nào sắp cạn?" có nhóm hũ thưa "có thể cạn trước ngày lương", thẻ Tổng quan không lặp chữ (#25); sửa 3 lỗi `pii.py` và màn duyệt nạp có chip "Đã che: tên, SĐT, số TK" + dòng tổng, migration 0056 (#16; KHÔNG hiện ảnh, theo chủ dự án); CSV cảnh 4 sinh lại bền khi tải trễ 1 ngày (hệ số tự chọn 3,5 sau khi bộ che không còn che "Huỳnh Hoa") (#22). Unit 4170 passed, 2 skipped.

**Đã deploy** (`main` `65effe2`; chi tiết ở `docs/aws-resources.md`): migration 0055, 0056 (chạy thử 0001–0056 trên Postgres cục bộ trước); 5 zip; `YofinaTools`, `YofinaIngest`, `YofinaAgent`, `YofinaFrontend`; Runtime **v28**; Amplify **job 24**; `seed_demo.py` 4 tài khoản (đặt lại lần cuối sau khi kiểm). Khóa SSM thử (`/yofina/quota/chat_turns_per_day`, `/yofina/agent/reasoning_enabled`) đã xóa.

**Lỗi tìm thấy khi kiểm và đã sửa, đã deploy**:
- Zip ingest đóng thiếu `yofina_classify` (dùng lệnh cũ trong README thay vì `INGEST_BUILD_COMMAND`): `yofina-ingest-api` trả 500 khoảng 5 phút. Đã đóng lại, sửa lệnh trong `infra-cdk/README.md`. **Luôn đóng zip theo các hằng `*_BUILD_COMMAND` trong `infra-cdk/lib/`.**
- Luật rewrite SPA của Amplify trả `index.html` cho `.csv`: tệp mẫu cảnh 4 không tải được. Thêm `csv`, `pdf` vào luật + test CDK (`3b98fa2`).
- Mở chat rồi gửi tin ngay (khoảng 1,5 s) bị 409 `SESSION_BUSY` vì lượt làm nóng chưa xong: frontend chờ làm nóng (trần 15 s), 409 tự thử lại 1/2/4 s (`53a2887`).

**Kết quả kiểm trên app** (Chrome tự động 390×844, ảnh chụp và log CloudWatch): CSP có `frame-ancestors 'none'`; `giamkhao1` bị từ chối ở `/ops`, `minh` vào được; cảnh 1 Ăn uống cạn 23/11, nhãn "Cao"; cảnh 2 what-if khoảng 26 s trọn câu, khối đầu khoảng 1 s khi ấm, khối lập luận còn (1/4 bước bị bỏ vì `jar_mismatch` ở một lượt); cache Sonnet đọc 1.716 và 4.359 token ở lượt sau; cảnh 3 điểm 29 → 12, trụ 24 ngày; cảnh 4: 32 dòng tự vào Ăn uống, bản đề xuất mới khoảng 24 s sau khi xác nhận, "Số tính ngày 21/11", "Giữ bản cũ" hỏi lý do và lưu được; cảnh 5: màn duyệt sau 8,6 s, `B***`, chip "Đã che: tên"; trần lượt chat 2 → tin thứ 3 bị chặn đúng câu; công tắc lập luận tắt → không còn khối lập luận; 0 `turn_persist_timeout`. Tiền model của các lượt kiểm khoảng dưới 0,5 USD.

**Đã đóng** (đạt "Cách kiểm"): #8, #10, #12, #16, #17, #20, #22, #24, #25, #26, #27, #29 (cùng #18 từ trước). **Còn mở** đã có comment: #7 (ca lộ trình `--only` khi eval; quyết trường hũ có cấu trúc), #11 (đếm `audit_events`, đủ 3 lượt ấm), #13 (SSM trần chung ngày 2/12), #19 (chữ "Subscription" thô và ngày giai đoạn lệch trong bản lộ trình model sinh ở cảnh 4; chưa kiểm tài khoản 0 ₫), #5, #6, #23 (cần eval), #9 (cần tài khoản lịch sử ngắn), #14 (xem job đêm vài đêm), #15 (kiểm trên `lan`), #28 (đề xuất đóng), #32, #36.

**Thấy khi kiểm, chưa sửa**: câu "lập giúp mình lộ trình xây quỹ dự phòng 3 triệu trong 3 tháng" không lập bản mới mà hiện lại bản đang dùng, kèm câu "Bạn chưa nói mục tiêu này thuộc hũ nào…"; bản lộ trình v3 sinh lại ở cảnh 4 có bước "Đổi tỷ lệ chia lương" dồn 5.358.067 ₫ vào Ăn uống. Đáng xem lại trước khi quay video cảnh 4.

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

**Deploy gộp (đợt 1 + đợt 2, từ `main` `66807ad`), CHỜ chủ dự án duyệt.** `cdk diff` từng stack trước; một luồng deploy tại một thời điểm; máy mở suốt khoảng 60–75 phút.
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
- `pii.py` có ba lỗi đã thấy (ghi ở comment #16): che sót số tài khoản tách nhóm, che thừa giờ, che nhầm tên quán "Huỳnh Hoa". Chưa có issue riêng.

**Câu hỏi đang chờ chủ dự án**: xem tin nhắn của người điều phối ngày 25/11 tối (vòng 1, đánh số). Tóm tắt: duyệt deploy gộp; #7 thêm trường hũ có cấu trúc vào bước lập luận; #22 hệ số CSV 2,1 hay 3; #28 đóng; #24 làm nốt giá ghi cache; #23 cho router trích `date_text` cho what-if; câu hỏi của #36 về cách khai tài sản có sẵn.

**Nhánh**: mọi nhánh `p6/*` của hai vòng đã nằm trong `main`; worktree `C:\moMo-wt\p*` đều sạch, không còn bản vá chưa merge.

## Cập nhật trưa 25/11: kiểm toán toàn dự án, hạn nộp thật là 03/12

- **Hạn nộp thật: 23:59:59 ngày 03/12/2026** (trang cuộc thi), không phải 10/12. Sau hạn không được sửa mã nguồn, slide, sản phẩm đang chạy; sản phẩm phải chạy tới hết 11/12. Lịch mới ở mục 8 của [phase 6](docs/plan/phases/phase-6-danh-gia-dong-goi.md): đợt 1 ngày 28/11, đợt 2 ngày 30/11 (hạn cuối tính năng mới), freeze tối 1/12, RC và eval cuối 2/12, nộp trước 18:00 ngày 3/12.
- Kiểm toán bằng 9 subagent (Kiro CLI điều phối): [tổng hợp](docs/research/2026-11-25-audit-tong-hop.md) và 9 ghi chú `docs/research/2026-11-25-audit-*.md`. Quyết định của chủ dự án ở mục 7 file phase 6 ("Chốt 25/11 sau kiểm toán").
- **Việc theo dõi trên GitHub Issues**: issue tổng [#2](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/2), 36 issue con (#3–#38) chia theo đợt, nhãn `ready-for-agent` / `ready-for-human`, có quan hệ blocked-by. Cấu hình skill ở `docs/agents/`.
- Đã làm trên AWS: đăng ký một email vào SNS `yofina-alerts` (đã xác nhận; trước đó topic có 0 người nhận). Yêu cầu tăng quota Bedrock qua API bị từ chối vì quota của tài khoản thấp hơn mặc định: phải mở case AWS Support (#3).
- Máy của Phúc đã có `uv` và `.venv`; unit 3920 passed, 3 skipped.

## Cập nhật chiều 25/11: đợt 1 đã code và merge vào `main`, CHƯA deploy

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

**Deploy đợt 1 (chờ chủ dự án duyệt, dự kiến 28/11)**, theo thứ tự:
1. `uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 --keep-boto --extra data/personas:personas`, rồi `uv run scripts/cdk.py deploy YofinaTools --require-approval never`.
2. `uv run scripts/agent_deploy.py` (Runtime).
3. `uv run scripts/cdk.py deploy YofinaFrontend --require-approval never`; `uv run scripts/print_env.py frontend --write`; `npm.cmd run build` trong `frontend/`; `uv run scripts/deploy_frontend.py frontend/dist`.
4. `uv run scripts/seed_demo.py minh giamkhao1 giamkhao2 giamkhao3` (chuyển `giamkhao3` sang nhóm Cognito `persona-minh`).

**Kiểm sau deploy**: `curl -I` URL Amplify thấy CSP, đăng nhập, chat, nạp ảnh không bị "Refused to connect" (rollback: `git revert` commit CSP rồi deploy lại YofinaFrontend và zip); 3 lượt what-if ấm (đo thời gian tới RUN_FINISHED, trước khoảng 21 s); 0 `turn_persist_timeout`; số `audit_events` bằng số lượt; gửi tin thứ hai ngay sau tin đầu không bị 409 `SESSION_BUSY`; bấm xác nhận ngay sau khi có thẻ vẫn chạy; đo lại số cảnh 1 và cảnh 3 của `minh` rồi sửa `docs/plan/demo-script.md`; chạy 8 ca đối kháng mới `--only`; xem lịch sử `yofina-nightly` vài đêm.

**Rủi ro còn mở từ đợt 1**: hũ Nghĩa vụ phủ 0,728 ở mọi độ dài lịch sử nhưng vẫn hiện %; client Data API chưa coi `57P01` là lỗi tạm thời (C2); lộ trình mới bắt đầu ở ngày lương kế (không còn chặng bắt đầu hôm nay); thẻ tiến độ chưa thử trên trình duyệt; vitest có test chập chờn khi máy tải nặng.

**Issue chưa làm**: #3 (chờ AWS duyệt quota), #4 (đi 6 cảnh), #7 (lập luận nhất quán + công tắc SSM), #13 (trần lượt gọi), #16 (cảnh 5), #17 (bỏ `ops` khỏi tài khoản giám khảo), #21 (đo sau đợt 1), #22–#29 (đợt 2), #30 (chờ BA chốt C-02), #31 (20 câu giữ riêng), #32 (tài liệu, ADR-0004), #33 (số kinh doanh), #34–#38 (RC và nộp). Lô kế tiếp đề xuất: #7, #13, #17, #16, rồi deploy đợt 1.

## Quy ước cho người điều phối

### Chưa duyệt

- Deploy gộp đợt 1 + đợt 2 **đã làm khuya 25/11** (chủ dự án duyệt). Deploy sau này vẫn phải hỏi trước, kèm chi phí, tác động, cách rollback. Không deploy, không seed, không đặt SSM, không chạy eval trên Runtime, không gọi Bedrock khi chưa hỏi. Khi xin duyệt: nêu chi phí, tác động, cách rollback.
- Việc cần người hoặc chờ điều kiện: #3, #4, #21, #30, #31, #33, #34, #35, #37, #38.

### Quy ước giao việc cho worker (đã dùng ở đợt 1 và đợt 2)

- Mỗi issue một worker, worktree riêng (`git worktree add <thư mục> -b p6/<tên> main`, hoặc `-B p6/<tên> origin/p6/<tên>` cho nhánh đã có), chỉ sửa file trong phạm vi được giao, theo skill `/tdd` với seam do người điều phối chốt sẵn (không hỏi người dùng), commit từng phần xanh ngay (mạng hay làm đứt worker), không push, không đụng `main`.
- Commit tiếng Việt, kết bằng `(#số issue)`, **không thêm `Co-authored-by` hay trailer nào** (yêu cầu của chủ dự án).
- Worker không sửa `docs/ai-log/`, `HANDOFF.md`, file phase 6, issue; người điều phối làm các việc đó.
- Chạy tối đa khoảng 6 worker song song. Lần trước chạy 11 cùng lúc thì 6 cái bị lỗi mạng, phải chạy lại.
- Gộp qua một nhánh tích hợp (ví dụ `p6/wave2`), xung đột kiểu "cả hai cùng thêm" thì giữ cả hai, chạy `uv run pytest tests/unit libs/yofina_core/tests -q -p no:cacheprovider` (mốc **4127 passed, 2 skipped** sau đợt 2) trước khi fast-forward `main` và push. `git fetch` trước: BA (bloan0908) hay commit vào `main`, và đầu `docs/ai-log/2026-11.md` hay xung đột (gộp tay, giữ mọi entry, mới nhất ở trên).
- Sau khi gộp: comment trạng thái lên từng issue (`gh issue comment <n> --body-file <tệp>`; PowerShell không có heredoc). **Chỉ đóng issue khi đã deploy và kiểm theo mục "Cách kiểm" của issue**, trừ việc không cần deploy (như #18).
- Repo public: không ghi email, mật khẩu, account ID, thông tin thật về tài khoản AWS vào file hay issue.
- Bẫy đã gặp: ca eval `leak-1` phải hỏi tài khoản demo khác `minh` (giờ là `lan`); `giamkhao1–3` đều là persona `minh`.
- Rút ra ở đợt 2: giữ sẵn số migration cho từng worker (0055, 0056… để không trùng); chỉ rõ dòng nào trong file dùng chung (ví dụ `ReadConfig` của `agent-stack.ts`, khóa cuối `defaults.json`) để xung đột chỉ là "cả hai cùng thêm"; worktree mới cần `uv sync --frozen`, còn worker đụng CDK/frontend/contracts thì cần `npm.cmd ci` trong `infra-cdk/`, `frontend/`, gốc repo; `.venv` không có Pillow nên 2 test ảnh bị skip (`uv run --with pillow pytest …` để chạy); vitest cả bộ có 2 test chập chờn khi máy tải nặng; `scripts/scan_repo.py` (B2) chưa có, quét bí mật bằng regex trên dòng thêm trước khi push. Lượt review độc lập sau vòng đầu bắt được lỗi thật (tập hũ của lập luận, trần chặn eval), nên giữ bước này.

## Cập nhật rạng sáng 25/11 (sau khi viết bản trên)

- **Bộ nhớ đã sửa gốc** (nhánh p5/mem-extract, ac2a4fe): bước hợp nhất mặc định của AWS bỏ sở thích có thời hạn ("temporary states") và Nova Lite không theo chỉ dẫn; nay override cả hợp nhất, đổi sang Haiku 4.5. `memory-state-preference` và `memory-knowledge-update` đạt (mỗi ca một lần). Mục A.2 bên dưới coi như xong; chi tiết ở file phase 5 và agentcore-memory-design.md mục 2.2a.
- **Phase 6 đã có kế hoạch** ([phase-6](docs/plan/phases/phase-6-danh-gia-dong-goi.md)), chủ dự án chốt Q1–Q9 theo đề xuất; Q10–Q15 còn chờ. Đợt 7 kiểm toán prompt (chip mang ý định có cấu trúc) hoãn tới sau cuộc thi.
- **Luồng K (agent như người tư vấn) K1–K3 đã deploy** (589eb1c, Runtime v27, Amplify job 21): khối mới `reasoning` hiện 2–5 bước lập luận và một câu kết luận trong what-if và lộ trình, thu gọn "Xem cách mình cân nhắc". Còn mở:
  - Độ trễ tăng khoảng 6 s mỗi lượt có lập luận (what-if trọn câu 37,9 s); lập luận hiện sau khi Analyst xong chứ chưa hiện trong lúc chờ (cần stream có cấu trúc, làm cùng D2).
  - Lập luận có thể nói khác bản đã lưu (ca lộ trình: lập luận nói chuyển từ hũ Giải trí, bản lưu chuyển từ Đi lại) — cần kiểm nhất quán giữa lập luận và kết quả đã lưu trước demo.
  - "Kiểm tra trước khi chi" chưa có lập luận (đường này không có Analyst); bộ chấm eval chưa kiểm số trong khối `reasoning`.

## Đang ở đâu trong kế hoạch

Kế hoạch: [docs/plan/master-plan.md](docs/plan/master-plan.md), sáu phase trong [docs/plan/phases/](docs/plan/phases/). Hạn nộp giả định trước 11/12/2026.

| Phase | Trạng thái |
|---|---|
| 1. Nền và lát dọc | Xong 22/11 |
| 2. Ví mô phỏng và dự báo | Xong 22/11 |
| [3. What-if, kiểm tra trước khi chi](docs/plan/phases/phase-3-what-if-va-kiem-tra.md) | Đóng 23/11 |
| [4. Chống chịu, lộ trình, phân hũ tự động](docs/plan/phases/phase-4-chong-chiu-lo-trinh.md) | Đóng 24/11 (tiêu chí 6: tỷ lệ phải hỏi 17,4%, mục tiêu < 10%) |
| [5. Nạp dữ liệu, hồ sơ hành vi, bộ nhớ, trace](docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md) | **Code xong, deploy Runtime v26, đo xong**. Kết quả từng đợt ở mục "Nghiệm thu 24/11" và các mục "Kiểm lại…", "Đo sau đợt sửa kiểm toán và bộ nhớ (Runtime v25)", "Sửa nhỏ sau v25". Còn: tiêu chí 3 (OCR), đi lại 6 cảnh trên UI mới, rồi điền bảng đóng phase |
| [6. Đánh giá, cứng hóa, đóng gói](docs/plan/phases/phase-6-danh-gia-dong-goi.md) | Chưa bắt đầu |

## Đã làm trong ngày 24/11 (chi tiết ở ai-log và file phase 5)

- **Bộ nhớ (AgentCore Memory)** sửa gốc, không chặn câu chữ bằng mã: khối bộ nhớ đưa vào prompt dạng dữ liệu có cấu trúc, bỏ câu mẫu; trích xuất "built-in with overrides" bằng Nova Lite (tiếng Việt, chỉ lời khẳng định, giữ chữ thời hạn, câu đổi ý viết thành lời khẳng định mới); bỏ strategy tóm tắt phiên; không ghi lượt hỏi đáp thuần và lượt `profile_update`. Đổi ý đo thật: bản cũ mất hẳn, `DELETE /memory` xóa sạch mọi thứ API cho kiểm. Nghiên cứu: [long-term-memory-research.md](docs/research/long-term-memory-research.md), thiết kế: [agentcore-memory-design.md](docs/research/agentcore-memory-design.md).
- **Kiểm toán prompt chống overfit** ([prompt-overfit-audit.md](docs/research/prompt-overfit-audit.md)): đã làm đợt 1–4, 6 (bỏ mã chết, writer không còn khuôn "đúng N câu", chặn hỏi lại bằng mã ở `clarify.CLARIFY_INTENTS`, router trích ý định phụ thay bảng từ khóa/regex, gom prompt ảnh). Có test CI cấm prompt chứa cụm 5 từ trùng câu eval. Bộ 18 câu diễn đạt lại cho router: 18/18.
- **Luật suitability thứ bảy** `emergency_not_for_discretionary` (warn): không khuyên tiêu quỹ dự phòng cho khoản không thiết yếu.
- **Nạp chứng từ ngoại tệ**: quy đổi sang VND theo tỷ giá bán Vietcombank theo ngày (API công khai), dòng vào hàng chờ duyệt, sửa được số VND; mã lỗi mới `INGEST_NO_TRANSACTIONS` kèm lý do. Tool Gateway `knowledge___get_exchange_rate` dùng chung `yofina_core.fx` cho agent chat. Rút tiền mặt ngoài phạm vi; màn tra soát không tạo dòng. [ingest-fx-rates.md](docs/research/ingest-fx-rates.md).
- **Giao diện**: bảng màu mới, cảnh 1–4 có chuyển động, biểu đồ chi tiêu B1/B2/B3/B5/B6/B7 ([spending-visualization.md](docs/research/spending-visualization.md)), giảm chữ (luật §9) và "mỗi thông tin một nhà" (§10) trong [ui-design-review.md](docs/research/ui-design-review.md). REST mới `GET /cashflow`.

## Đang chạy trên AWS (`ap-southeast-1`)

- Bảy stack đều `*_COMPLETE`. Danh sách tài nguyên: [docs/aws-resources.md](docs/aws-resources.md).
- **Runtime `yofina_agent` v28**, **Amplify job 24**, migration tới **0056** (deploy khuya 25/11). App: `https://main.dcrwn4u7vqklo.amplifyapp.com`.
- Memory `yofina_memory` (id không đổi) với hai strategy override `preferences_vi`, `facts_vi`: override cả trích xuất lẫn hợp nhất, model **Claude Haiku 4.5** (khoảng $0,007–0,0125 mỗi lượt được ghi; quota 10 RPM dùng chung với model dự phòng của vai `small`). Lambda nạp gọi ra API tỷ giá Vietcombank (không VPC, không NAT).
- Sáu tài khoản demo (`minh`, `lan`, `khoa`, `giamkhao1`–`3`), mật khẩu trong secret `yofina-demo-accounts`. **Mật khẩu đã lộ trong lịch sử chat 23/11: đổi trước buổi chấm.** `minh`, `giamkhao1` thuộc nhóm `ops`.
- Aurora `yofina-db` min 0 ACU (lần gọi đầu chậm 15–20 giây). **Trước buổi demo** lên 0,5 ACU: `uv run scripts/cdk.py deploy YofinaData --require-approval never -c dbMinAcu=0.5`, xong trả về `-c dbMinAcu=0`.

Lệnh hay dùng (chi tiết ở `scripts/README.md`, `infra-cdk/README.md`): `uv run pytest tests/unit libs/yofina_core/tests -q`; `uv run scripts/cdk.py diff|deploy <Stack> --require-approval never`; `uv run scripts/agent_deploy.py` (có thể exit 1 dù READY); `uv run scripts/migrate.py`; `uv run scripts/seed_demo.py <persona>`; frontend: `uv run scripts/print_env.py frontend --write`, `npm.cmd run build` trong `frontend/`, `uv run scripts/deploy_frontend.py frontend/dist`. Đặt `PYTHONIOENCODING=utf-8` khi chạy script in tiếng Việt trên Windows.

## Số đo mới nhất

- Unit 3871 passed; CDK 77/77; vitest 978.
- Eval đầy đủ một lần trên Runtime v25: golden phase 3 31/31, phase 4 14/14, phase 5 11/15 (4 ca bộ nhớ trượt do lỗi script nạp bản ghi, đã sửa, chạy lại riêng: 3/4, ca còn lại là judge chấm sai, đã sửa judge và đạt ở v26); adversarial phase 3/4/5 16/16, 12/12, 14/14; router diễn đạt lại 18/18; OCR real 9/11 (r08 đã sửa và đạt ở v26, r12 sai ngày do ảnh mờ).
- Chi phí một lượt eval đầy đủ khoảng **$2,2–2,5** (khoảng 80% là Sonnet 4.6). Vì vậy: **chỉ chạy eval đầy đủ khi đã deploy xong và ổn hẳn; bình thường chỉ chạy vài ca `--only`**.

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
- `turn_persist_timeout` xuất hiện mỗi ca eval, chưa rõ nguyên nhân; `numeric_ungrounded` 2 lần ở v25 (lời bị bỏ, ca vẫn đạt).
- `period_end` của lộ trình chưa theo ngày lương; tỷ lệ phải hỏi của phân loại 17,4%.
- Bước lập lộ trình chưa đọc bộ nhớ; học từ `feedback` (đếm loại đề xuất bị từ chối, P1-5 nghiên cứu bộ nhớ).
- Guardrail `ApplyGuardrail` p50 446 ms > 400 ms.
- Ghi chú duyệt nhãn của 25 ảnh thật bị lỗi mã (dấu thành `?`) từ commit a70b9a3; một số tài khoản 8 chữ số từng nằm trong ghi chú cũ (đã xóa khỏi file, còn trong lịch sử git — chủ dự án quyết có viết lại lịch sử không).

## Cách làm việc

Claude Code là người điều phối: plan, giao mỗi việc cho một worker `kiro-cli chat --no-interactive --trust-workspace --trust-all-tools --model claude-opus-5.5 --effort high` trong worktree riêng `C:\moMo-wt\<việc>`, review diff, merge, chạy unit. Nhiều nhánh thì gộp lại, deploy một lần, eval một lần. Quy tắc của chủ dự án:

- **Không hardcode, không giả lập** ([master-plan mục 2](docs/plan/master-plan.md#2-quyết-định-áp-dụng-cho-mọi-phase)).
- **Không vá prompt/mã cho vừa vài ca eval** (không câu mẫu, không ví dụ chép từ eval, không lọc câu chữ của model bằng mã); lỗi hành vi thì tìm nguyên nhân gốc và sửa theo nguyên tắc chung.
- **Eval tốn tiền** (~$2,3/lượt đầy đủ): chỉ chạy đầy đủ ở mốc deploy đã ổn; bình thường chỉ vài ca `--only`, mỗi ca một lần.
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
