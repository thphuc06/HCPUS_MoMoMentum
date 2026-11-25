# Prompt điều phối: thực hiện lộ trình bộ hũ mặc định

Ngày lập: 25/11/2026. Dùng cho agent điều phối (Claude Code) khi thực hiện [default-six-jars-rollout.md](default-six-jars-rollout.md). Copy nguyên phần trong khung "Prompt" vào một phiên mới, mở tại gốc repo.

Prompt dùng hai worker có sẵn trong `~/.claude/agents/`:

- `codex-worker`, `Tier: deep`, chạy `gpt-6.2-sol` với effort `high`.
- `kiro-worker`, `Tier: deep`, chạy `claude-opus-5.5` với effort `high` (2,00x credits).

---

## Prompt

```text
Bạn là agent điều phối cho repo D:\Projects\HCPUS_MoMoMentum, nhánh feat/default-six-jars.
Nhiệm vụ: hoàn thành Bước 1 đến Bước 6 của docs/plan/default-six-jars-rollout.md (gọi tắt là "lộ trình")
bằng hai loại subagent, dùng ít quota nhất có thể. Bước 7 (phát hành) KHÔNG làm.

## 0. Đọc trước (chỉ đọc, không giao cho worker)
- CLAUDE.md, HANDOFF.md (mục "Cách làm việc" và "Quyết định đã chốt"), lộ trình.
- ~/.claude/agents/codex-worker.md và ~/.claude/agents/kiro-worker.md để biết định dạng brief.
- Đọc phần "Hiện trạng commit WIP cần sửa" và các file nó trỏ tới. Chỉ đọc đủ để viết brief.
  Không đọc toàn repo.

## 1. Kiểm trạng thái Git (tự làm)
- `git status`, `git rev-parse HEAD`, `git fetch origin`, `git log -1 origin/main`.
- Lúc lập prompt: HEAD = 622a1b0 (WIP), gốc 865fba9, origin/main đã lên eee9718. Từ 865fba9 tới
  eee9718 chỉ có tài liệu, CLAUDE.md và HANDOFF.md thay đổi. Nếu bây giờ origin/main có thay đổi
  code ở các file của lộ trình thì DỪNG lại và báo chủ dự án. Không tự rebase.
- docs/plan/default-six-jars-rollout.md đang có sửa đổi chưa commit. Commit file đó (và file prompt
  này) lên nhánh trước khi tạo worktree, để worker đọc được bản mới.
- Mỗi việc ghi một worker chạy trong một worktree riêng:
  `git worktree add C:\moMo-wt\<việc> -b wt/<việc> feat/default-six-jars`.
  Không cho worker ghi vào checkout chính.

## 2. Chia việc và lý do chọn model
Nguyên tắc tiết kiệm quota:
- Mỗi việc chỉ giao cho MỘT worker. Không xin "ý kiến thứ hai" và không chạy hai model cùng một việc.
- Việc cơ học thì tự làm: git, merge, sửa dưới khoảng 30 dòng, đánh dấu checkbox, ai-log, HANDOFF,
  sửa lời trong demo-script, chạy test.
- Gom việc dùng chung file vào một worker, để không phải giao lại vì xung đột merge.
- Brief ngắn: trỏ tới mục trong lộ trình bằng đường dẫn và tên mục, không dán lại cả tài liệu.
  Liệt kê file được sửa, file chỉ được đọc, và tiêu chí xong.
- Worker trả về tóm tắt ngắn: file đã đổi, test đã chạy, điểm còn nghi. Không trả transcript.
- Nếu worker thất bại, KHÔNG gửi lại nguyên brief cũ. Thu hẹp phạm vi, kèm đúng đoạn lỗi.

Codex (gpt-6.2-sol) nhận phần backend có ràng buộc chặt: SQL, migration, Python, test PostgreSQL.
Kiro (claude-opus-5.5) nhận phần sản phẩm nhiều quy tắc nghiệp vụ, đi từ server tới giao diện, và
một lượt review cuối. Opus tốn 2,00x credits, nên Kiro chỉ chạy W3 và R1, cộng W4 nếu lỗi nằm
ở phần của W3.

| Đợt | Việc | Worker | Mode | Phạm vi (theo lộ trình) | Phụ thuộc |
| --- | --- | --- | --- | --- | --- |
| W1 | `jar-layout` | codex deep | write | Bước 1 trọn, cộng phần dữ liệu của Bước 5: cấu hình `jar_layout` cho onboarding (3 hũ) và demo (4 hũ); tách migration 0055 (khi gộp vào `main` đổi thành 0057, 0058, 0059 vì `main` đã có 0055, 0056); seed; `six_jars.py`; `reset_demo` đọc cấu hình demo; `minh_six_jars.json`; bốn persona sau reset | — |
| W2 | `purpose-domain` | codex deep | write | Bước 2 trọn: `purpose` qua contracts/, libs/yofina_core, Ledger, Agent, Planner, forecast, frontend/src/api; hũ Nghĩa vụ chung làm nguồn trả; dự báo hũ Nghĩa vụ theo ngày; phí Trả Sau; sàn thiết yếu theo loại giao dịch (làm không kịp thì giữ cách cũ, ghi giới hạn) | Đã merge W1 |
| W3 | `onboarding-declare` | kiro deep | write | Bước 3 và Bước 4: tính tỷ lệ đề xuất ở server, khoản biết trước và Quỹ dồn, kiểm tra theo ngày, bỏ qua bước 3, ca vượt 100%; bản xem trước `save_jars` có số tiền mỗi kỳ và kỳ áp dụng; UI trong frontend/src/features/jars và trang onboarding; test vitest và local_pg cho phần này | Đã merge W2 |
| W4 | `fix-<tên>` | worker đã làm phần lỗi | write | Chỉ khi test ở mục 3 lỗi mà không tự sửa được dưới khoảng 30 dòng. Brief chỉ gồm test lỗi, đoạn lỗi và file liên quan | Sau mục 3 |
| R1 | `review` | kiro deep | read-only | Review toàn bộ diff `865fba9..feat/default-six-jars`, theo phạm vi ở dòng "Review Kiro Opus 5.5" của lộ trình: nguồn trả nghĩa vụ, `purpose`, cấu hình hũ, tương thích reset, thứ tự an toàn của migration. Chỉ báo lỗi có kịch bản cụ thể, xếp theo mức nặng | Sau mục 3 xanh |

Chạy tuần tự W1, W2, W3. Không chạy song song: ba đợt cùng đụng `wallet_writes.py`, `service.py`
và contracts/, nên chạy song song thường dẫn tới xung đột và phải giao lại.

Mẫu brief (điền vào chỗ trống):
  Tier: deep
  Mode: write
  Cwd: C:\moMo-wt\<việc>
  [Kiro] Spec: no
  Task: Đọc docs/plan/default-six-jars-rollout.md, mục "<tên mục>", và các quyết định Q1–Q6.
        Làm đúng các checkbox <liệt kê>. Được sửa: <file/thư mục>. Chỉ đọc: <file>.
        Quy tắc dự án: không hardcode, không giả lập; tiền là số nguyên VND; server tính mọi số;
        giữ tương thích với ví cũ chưa có `purpose`; không gọi AWS, không deploy, không chạy evals
        hoặc tests/integration; không commit.
        Test được chạy: <lệnh cục bộ nhắm đúng phần này>. Nếu sandbox không chạy được test thì ghi
        rõ, đừng cố cài thêm.
  Output wanted: danh sách file đã đổi; checkbox nào xong và checkbox nào còn; test đã chạy và kết
        quả; giả định đã đặt; tối đa 15 dòng.

Sau mỗi đợt:
1. Đọc `git -C C:\moMo-wt\<việc> diff`. Kiểm tra diff nằm trong phạm vi đã giao, không có số
   hardcode cho vừa test, và không có lời gọi AWS mới.
2. Commit trong worktree, rồi merge `wt/<việc>` vào feat/default-six-jars (local).
   Theo HANDOFF, commit KHÔNG kèm Co-Authored-By.
3. Chạy nhanh test của phần vừa merge (xem mục 3), rồi mới giao đợt kế.
4. Đánh dấu checkbox đã xong trong lộ trình. Xóa worktree khi đã merge.

## 3. Kiểm thử: CHỈ chạy cục bộ
Trước mỗi lệnh test, chặn AWS để lỡ có lời gọi thật thì nó lỗi ngay chứ không tốn tiền.
Trong PowerShell:
  $env:AWS_SHARED_CREDENTIALS_FILE = "NUL"; $env:AWS_CONFIG_FILE = "NUL"
  $env:AWS_PROFILE = $null; $env:AWS_ACCESS_KEY_ID = $null; $env:AWS_SECRET_ACCESS_KEY = $null
  $env:AWS_SESSION_TOKEN = $null; $env:AWS_EC2_METADATA_DISABLED = "true"

Được chạy:
- `uv run pytest tests/unit libs/yofina_core/tests`
- PostgreSQL cục bộ (lệnh ở gateway/tools/ledger/README.md):
  uv run --python 3.12 --no-project --with pgserver --with "psycopg[binary]" --with pydantic --with pytest --with jsonschema --with pyyaml --with referencing --with numpy --with boto3 pytest tests/local_pg -p no:cacheprovider
- Frontend: `npm run typecheck`, `npm run lint`, `npm test` trong frontend/.
- Bước 5: chạy lại cảnh 1–4 bằng engine cục bộ trên PostgreSQL cục bộ. Đối chiếu với số ở lộ trình
  (cảnh 1: 1.080.000 ₫, cạn 03/12; cảnh 2: đến hạn 2.200.000 ₫ ngày 03/12, gồm phí 33.000 ₫, thiếu
  khoảng 761.000 ₫). Lệch thì ghi số mới và nguyên nhân; không chỉnh dữ liệu cho khớp số cũ.
- Các ca ở Bước 6: ví cũ, ví ba hũ, ví demo bốn hũ, reset hai lần, vượt 100%, có sự kiện lương chờ,
  và quay lui về bộ bảy.
- Trước khi chạy một script trong scripts/, đọc nó trước. Có boto3, Cognito, Bedrock, AgentCore,
  `rds-data` thật hoặc URL deploy thì không chạy.

CẤM (sau khi hoàn thành cũng vậy, kể cả khi test cục bộ đã xanh):
- Mọi eval: evals/run.py, scripts/eval_*.py, scripts/measure_*.py, và mọi lệnh có `--only` gọi model.
- tests/integration và mọi lệnh `pytest -m integration`.
- cdk diff/synth/deploy, scripts/cdk.py, agent_deploy.py, deploy_frontend.py, build_lambda.py
  (khi dùng để upload), create_demo_users.py, get_token.py, inject_behavior_shift.py,
  agent_call_local.py hoặc agent_run_local.py khi chúng gọi Bedrock.
- Tool MCP của AWS (aws-docs thì được đọc), agentcore, Amplify. Không push, không merge vào main.
Nếu muốn kiểm thêm thứ gì cần AWS, ghi vào HANDOFF ở mục "Cần chạy khi được duyệt", đừng chạy.

## 4. Review cuối (R1)
- Sau khi mục 3 xanh, giao R1 cho Kiro (read-only). Đọc báo cáo và tự xác minh từng lỗi trên code.
- Lỗi xác nhận thì tự sửa nếu nhỏ, sửa lớn thì giao một W4 cho đúng worker. Chạy lại test bị ảnh
  hưởng. Không review lần hai.

## 5. Kết thúc
- Thêm một entry vào docs/ai-log/2026-11.md: tóm tắt từng đợt, ghi model của từng đợt, và lý do
  chia việc như vậy.
- Cập nhật HANDOFF.md với trạng thái lộ trình, kết quả test (số ca qua/lỗi theo từng bộ), số
  cảnh demo mới, việc còn mở, và danh sách kiểm cần AWS đang chờ duyệt.
- Báo chủ dự án: SHA cuối của nhánh, số lượt gọi mỗi worker (Codex x?, Kiro x?), test đã chạy
  và chưa chạy. Dừng ở đó: không push, không deploy, không eval.
```

---

## Ghi chú cho người dùng prompt

- Nếu `kiro-cli whoami` báo chưa đăng nhập thì worker sẽ dừng. Chạy `kiro-cli login` trước.
- Nếu slug `gpt-6.2-sol` bị từ chối, `codex-worker` báo lỗi chứ không tự đổi model. Xem `~/.codex/models_cache.json`.
- HANDOFF mô tả worker Kiro chạy với `--trust-all-tools`, nhưng định nghĩa `kiro-worker` cấm cờ này. Prompt theo định nghĩa worker: write thì `fs_read,fs_write`. Cách này có thể khiến Kiro không chạy được test trong worktree; khi đó agent điều phối tự chạy test.
- Cách chia: Codex 2 lượt (W1, W2), Kiro 2 lượt (W3, R1). W4 chỉ chạy khi có lỗi.
