# HANDOFF — ảnh chụp trạng thái hiện tại

> **Quy ước**: cập nhật (ghi đè phần trạng thái bên dưới) vào **cuối mỗi phiên làm việc**. HANDOFF là ảnh chụp hiện tại; lịch sử thay đổi nằm ở [docs/ai-log/](docs/ai-log/README.md). Đầu phiên mới: đọc file này trước.

Cập nhật lần cuối: **2026-11-25 rạng sáng** (Claude Code điều phối các worker `kiro-cli`). Phase 5 đã code xong, đã deploy, đã đo; **chưa đóng chính thức** (còn tiêu chí 3 OCR và đi lại 6 cảnh trên giao diện mới, xem mục B).

## Bộ sáu hũ mặc định (25/11, nhánh feat/default-six-jars)

Onboarding và lần đặt lại demo đã xác nhận dùng Chi hằng ngày (35%), Nghĩa vụ (35%), Dự phòng (15%), Quỹ dồn (5%), Mục tiêu (5%) và Tích lũy dài hạn (5%). Tỷ lệ là giả định thử nghiệm, có thể chỉnh và phải cộng đủ 100%. Migration 0055 thêm purpose cho hũ để dành và cập nhật danh mục, giữ dữ liệu tài khoản cũ trước khi đặt lại.

Hai cảnh đầu của [kịch bản demo](docs/plan/demo-script.md) đã chạy bằng engine và PostgreSQL cục bộ. Các mục sau ghi lại trạng thái trước thay đổi này. Lượt Kiro Opus 5.5 đang chờ phê duyệt credits.

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
- **Runtime `yofina_agent` v27**, **Amplify job 21**, migration tới **0054**. App: `https://main.dcrwn4u7vqklo.amplifyapp.com`.
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
