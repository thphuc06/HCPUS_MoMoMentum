# HANDOFF — ảnh chụp trạng thái hiện tại

> **Quy ước**: cuối mỗi phiên **ghi đè** phần trạng thái, giữ file khoảng 100 dòng. Lịch sử (số đo từng lượt, việc đã làm) chỉ ghi vào [docs/ai-log/](docs/ai-log/README.md), không chép thêm mục theo ngày vào đây. Bản dài trước khi cắt (28/11): `git show bf52cae:HANDOFF.md`.

Cập nhật lần cuối: **2026-11-28 chiều**. Bản đang chạy là `e784723` (đã gộp PR #57): Runtime **v36**, Amplify **job 30**, migration tới **0059**, Aurora **min 0**. Video demo xong (2:58, mp4 ở Drive, mã ở [video/](video/README.md)).

## Hạn

Tính năng 30/11 · freeze 01/12 · RC và eval cuối 02/12 (#34, #35) · **nộp trước 18:00 ngày 03/12** (#36, #37, #38) · chung kết 11/12.

## Trạng thái 28/11

- **Deploy 28/11 sáng đạt**: YofinaTools 06:47 (zip ledger, MetricFilter Guardrail `{ $.event = "guardrail_error" }`), YofinaAgent và Runtime v36 06:56, Amplify job 30 06:58. Không IAM, không migration, không YofinaIngest. Log 0 lỗi. Chi tiết: [aws-resources.md](docs/aws-resources.md).
- **6 cảnh demo**: cảnh 1–4 đạt trên v36. Cảnh 5, 6 chưa đi lại từ v31 (#4). Hai số trong lời dẫn của [demo-script](docs/plan/demo-script.md) cần sửa: cảnh 3 trụ **25 ngày** (không còn 26), cảnh 2 thiếu **1.166.692 ₫** (v34: 1.167.673 ₫, chưa rõ vì sao lệch 981 ₫).
- **Eval đầy đủ v36** (09:57–10:51, [eval-report.md](docs/research/eval-report.md)): qua Runtime 104/119, bộ diễn đạt lại router 20/21, khoảng 1,6 USD. Có 4 ca lùi so với v34, đều do router và prompt từ v35 (#60, #61), không phải PR #57.
- **Lỗi mở sau đợt này** (không lỗi nào chặn 6 cảnh demo):
  - [#58](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/58): khoản biết trước không khả thi thì lượt rỗng, vì bộ kiểm số bỏ lời writer và không có câu dự phòng. Sửa trước 30/11.
  - [#60](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/60): router hỏi lại hai câu, bị validator từ chối, nên lượt hiện "AI đang gặp sự cố". Sửa trước 30/11.
  - [#59](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/59): hạn Quỹ dồn lùi thêm 1 ngày ở lượt trả lời số tiền.
  - [#61](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/61) (needs-triage): 3 ca router đổi hành vi. Cần chủ dự án quyết sửa router hay sửa ca golden.
  - Lùi an toàn, đã biết: "để dành 5 triệu trước Tết" tự chọn hũ Du lịch nên ra "kịp sau khi nới" (thấy cả ở v34). "Tết này" phải hỏi hạn một lần.
- **Log group Runtime** giữ 14 ngày từ 28/11 (trước đó giữ vô hạn).

## Việc kế tiếp

1. **Đợt sửa trước 30/11**: #58, #60, rồi #59. #61 chờ quyết. Sau khi sửa: deploy, rồi chạy eval theo chính sách bên dưới.
2. **Tính năng trước 30/11**: #52 (phí trả chậm Trả sau), #54 (G1 chi phí trả sau quy ra năm), #53 (BR-79, chờ ước lượng), #55 (FR14, chờ chủ dự án), #47 (bộ nhớ lưu yêu cầu bị luật chặn), #31 (20 câu giữ riêng, người viết), #30 (chờ BA chốt C-02).
3. **Kiểm job đêm 29/11 02:00 chạy 6/6** (Step Functions `yofina-nightly`), vì trust policy Scheduler đã đổi ở #50.
4. **Freeze 01/12**: #45 (preflight, eval_summary, runbook), #32. Bỏ CORS localhost ở bản RC: truyền `-c extraCorsOrigins=` cho **cả** YofinaTools và YofinaIngest.
5. **RC 02/12**: #34 (eval cuối đầy đủ), #35 (Aurora 0,5 ACU tới 11/12, đổi mật khẩu demo, trần SSM, preflight). Đi lại 6 cảnh và sửa số lời dẫn (#4).
6. **Nộp 03/12**: #36 (bộ nộp, link video vào README), #37 (slide), #33 (số kinh doanh).
7. **Dọn repo, chờ chủ dự án duyệt**: đánh tag rồi bỏ `spikes/` khỏi `main` (22 tài liệu đang trỏ tới, phải sửa link); bỏ ảnh PNG cũ ở `docs/research/assets/frontend-spike/`.
8. Còn mở từ trước, cần soát để đóng: #2–#7, #9, #11, #13–#15, #19, #21, #23, #39.

## Chính sách eval (chủ dự án chốt 28/11)

- **Sau mỗi đợt sửa đã deploy**: chạy golden phase 3 và 4 cùng bộ diễn đạt lại router, khoảng 0,5–0,8 USD. Đợt v35 không được eval, nên 4 ca router lùi tới v36 mới lộ.
- **Đang sửa một ca**: `evals/run.py … --only <id>`, mỗi ca chạy một lần. Sửa router thì chạy `evals/paraphrase/run_router.py` trên máy (vài cent).
- **Eval đầy đủ** (khoảng 1,6–2 USD) chỉ chạy ở bản RC (#34).
- Mỗi lượt có thư mục `evals/results/<YYYYMMDD-HHMM>_v<NN>_<sha7>/` kèm `manifest.json`, và thêm một dòng vào [eval-report.md](docs/research/eval-report.md). Cách chạy ở [evals/README.md](evals/README.md).

## Đang chạy trên AWS (`ap-southeast-1`)

- Bảy stack Yofina `*_COMPLETE`; danh sách ở [docs/aws-resources.md](docs/aws-resources.md). App: `https://main.dcrwn4u7vqklo.amplifyapp.com`.
- Router Claude Haiku 4.5 (Nova 2 Lite dự phòng), planner Sonnet 4.6. Memory `yofina_memory` có hai strategy override (`preferences_vi`, `facts_vi`), hợp nhất bằng Haiku 4.5.
- Sáu tài khoản demo (`minh`, `lan`, `khoa`, `giamkhao1`–`3`); mật khẩu trong secret `yofina-demo-accounts`. **Mật khẩu đã lộ trong lịch sử chat 23/11: đổi trước buổi chấm (#35).** Chỉ `minh` thuộc nhóm `ops`. Lần đặt lại cuối: 28/11 sau eval. Bộ nhớ của `minh`, `giamkhao1`, `giamkhao2` trống.
- Aurora `yofina-db` min 0 (lần gọi đầu chậm 15–20 s). Trước buổi chấm: `uv run scripts/cdk.py deploy YofinaData --require-approval never -c dbMinAcu=0.5`, xong trả về `-c dbMinAcu=0`.
- Snapshot Aurora `yofina-db-pre-0057-20261126` giữ tới sau 03/12, rồi xóa.
- Cùng tài khoản AWS có tài nguyên của dự án khác: `Jars*`, `jars-dev-db`, EC2 `sidewalk-labelstudio`. Không đụng tới.

Lệnh hay dùng (chi tiết ở `scripts/README.md`, `infra-cdk/README.md`):
- Test unit: `uv run pytest tests/unit libs/yofina_core/tests -q`.
- CDK: `uv run scripts/cdk.py diff|deploy <Stack> --require-approval never`.
- Runtime: `uv run scripts/agent_deploy.py` (có thể exit 1 dù đã READY).
- Dữ liệu: `uv run scripts/migrate.py`, `uv run scripts/seed_demo.py <persona>`.
- Frontend: `uv run scripts/print_env.py frontend --write`, rồi `npm.cmd run build` trong `frontend/`, rồi `uv run scripts/deploy_frontend.py frontend/dist`.
- Trên Windows: đặt `PYTHONIOENCODING=utf-8`. Trong Git Bash: đặt thêm `MSYS_NO_PATHCONV=1` cho đường `/aws/…` và `/yofina/…`.

## Lưu ý vận hành

- **Thứ tự Runtime và Lambda khi đổi trường**:
  - Runtime kiểm chặt trường trả về (`extra=forbid`). Lambda trả thêm trường thì **Runtime trước, Lambda sau** (đợt v32: zip forecast có `recent_spend` đóng và deploy sau Runtime).
  - Runtime gửi thêm đầu vào mà Lambda cũ từ chối thì **Lambda trước** (đợt v31: `goals` cho hũ Dự phòng).
  - Tool Gateway mới (`YofinaAgent`) lên trước Runtime gọi nó.
  - Frontend lên trước khi hợp đồng khối nới (frontend cũ từ chối khối `clarify` quá 6 chip).
  - Test: `tests/unit/agent/test_runtime_lambda_compat.py`. Không quay lui riêng Runtime.
- `migrate.py` chạy mọi file chờ; muốn dừng ở một số thì dùng `--dir` với thư mục tạm. Luôn đóng zip theo các hằng `*_BUILD_COMMAND` trong `infra-cdk/lib/` (zip forecast theo khối "Đóng gói" của `infra-cdk/README.md`).
- `tests/local_pg` để lại thư mục `pgdata_ledger_*` trong `%TEMP%` (26/11 ổ C hết chỗ, dọn 256 thư mục, khoảng 24 GB). Chạy với `TEMP`/`TMP` trỏ vào thư mục con riêng rồi xóa. Chạy bằng `uv run --python 3.12.3` (3.12.13 làm `initdb` lỗi).
- Tệp CSV cảnh 4 gắn ngày neo 21/11: đặt lại rồi tải trong ngày, chậm nhất hôm sau.
- Eval cần nâng SSM `/yofina/quota/chat_turns_per_day` khi số lượt chat vượt 100 (lượt đầy đủ), rồi xóa khóa khi xong. Golden 3 và 4 (53 lượt) không cần, nếu trong ngày `minh` chưa dùng nhiều.
- **Chặn credential**:
  - Agent không nhập mật khẩu. Kiểm qua API thì lấy token bằng `scripts/_demo_auth.login_access_token`: hàm này đọc secret trực tiếp, nên agent không thấy mật khẩu. Bấm trên app thì chủ dự án tự đăng nhập.
  - Repo public: không commit account ID, ARN có account ID, secret, token, mật khẩu demo, email.
  - Trước mỗi commit và push, chạy `uv run python scripts/scan_repo.py`; kết quả phải là 0 phát hiện.
- Phiên AWS CLI (`aws login`) hết hạn sau khoảng 12 giờ; chủ dự án tự đăng nhập lại.

## Cách làm việc

- Claude Code là người điều phối: plan, giao mỗi issue cho một worker trong worktree riêng (`git worktree add <thư mục> -b p6/<tên> main`), review diff, merge, chạy unit. Kiro hết hạn mức tháng (27/11), nên dùng subagent Claude. Tối đa khoảng 6 worker song song.
- Worker chỉ sửa file trong phạm vi, theo `/tdd`, commit từng phần xanh, không push, không đụng `main`, không sửa `docs/ai-log/`, `HANDOFF.md`, issue.
- Commit tiếng Việt, kết bằng `(#số issue)`, **không `Co-authored-by` hay trailer nào**. `git fetch` trước khi gộp: BA hay commit vào `main`, và đầu `docs/ai-log/2026-11.md` hay xung đột (gộp tay, giữ mọi entry).
- **Chỉ đóng issue khi đã deploy và kiểm** theo mục "Cách kiểm" của issue.
- Quy tắc của chủ dự án:
  - **Không hardcode, không giả lập** ([master-plan mục 2](docs/plan/master-plan.md#2-quyết-định-áp-dụng-cho-mọi-phase)).
  - **Không vá prompt hay mã cho vừa vài ca eval**: không câu mẫu, không lọc chữ của model bằng mã. Lỗi hành vi thì tìm nguyên nhân gốc.
  - Giao diện ít chữ; mỗi thông tin chỉ một màn là nhà.
  - Một luồng deploy tại một thời điểm, chạy `cdk diff` trước. Mọi deploy, seed, đặt SSM, eval trên Runtime đều hỏi chủ dự án trước, kèm chi phí, tác động, cách quay lui.

## Quyết định

- **Đã chốt**:
  - Region `ap-southeast-1`; frontend theo [ADR-0001](docs/decisions/0001-frontend-stack.md); Cognito tắt tự đăng ký; sản phẩm Trả sau mô phỏng.
  - Xác nhận bằng token dùng một lần do server cấp, Cedar là lớp phụ.
  - Cắt RAG. Bộ nhớ theo best practice AgentCore.
  - Ngoại tệ quy đổi theo tỷ giá bán Vietcombank, người dùng duyệt.
  - Quyền AWS: tạo và sửa tài nguyên `yofina-*`, ghi vào aws-resources.md; hỏi trước với thứ tốn tiền theo giờ và trước khi xóa.
  - Lệch so với proposal ghi ở ADR-0004.
- **Còn treo**: bật CloudWatch Transaction Search không; viết lại lịch sử git để xóa số tài khoản cũ trong ghi chú nhãn không; trọng số chấm ([open-questions.md](docs/requirements/open-questions.md)).

## Môi trường

Windows 11, nhánh `main`, remote GitHub public. Python 3.13, uv, Node 24. `npm.ps1` bị chặn nên dùng `npm.cmd`. MCP `aws-docs`, `agentcore`, `aws-mcp` (có lúc mất kết nối). `evals/results/` không vào git. Mọi lời gọi model đi qua `yofina_core.llm` có trần mỗi ngày (bảng `yofina-usage`).
