# Kế hoạch tổng — Yofina Foresight

Viết ngày 2026-11-21 bởi người điều phối (Claude Fable 5.2). Thay cho bảng "3 tuần" trong [README.md](README.md) về mặt thứ tự việc; mốc hạn nộp giữ nguyên (giả định trước 11/12/2026).

Phạm vi: toàn bộ F1–F7 và FR1–FR15 trong [requirements.md](../requirements/requirements.md), kể cả phần proposal ghi là mở rộng (FR13, FR14, FR15, sao kê PDF) nếu kịp. Sản phẩm cuối chạy thật trên AWS `ap-southeast-1` và đi được cả 6 cảnh trong [demo-script.md](demo-script.md).

## 1. Sáu phase

Mỗi phase kết thúc bằng một thứ chạy được từ đầu tới cuối trên môi trường đã deploy. Hết thời gian ở phase nào thì những phase trước vẫn demo được.

| Phase | Ngày dự kiến | Kết thúc bằng | Cảnh demo chạy được | FR chính | File |
|---|---|---|---|---|---|
| 1. Nền và lát dọc | 21–24/11 | Đăng nhập → chat → agent trên Runtime → tool qua Gateway → Aurora → khối UI trên màn hình; chuyển giữa hũ có xác nhận bằng token | (chưa có cảnh nào trọn) | FR12 (cơ chế), nền FR1 | [phase-1](phases/phase-1-nen-va-lat-doc.md) |
| 2. Ví mô phỏng và dự báo (F1) | 25–28/11 | App ngân hàng dùng được: khai báo, hũ, chuyển tiền, nghĩa vụ, trả sau mô phỏng; dự báo 30 ngày tính mỗi đêm và khi có giao dịch | Cảnh 1 | FR1, FR3, FR4 | [phase-2](phases/phase-2-vi-va-du-bao.md) |
| 3. What-if, kiểm tra trước khi quẹt, harness đầy đủ (F2, F3) | 29/11–2/12 | Hỏi "nếu thì" có streaming, thẻ đủ/sát/hụt khi chuyển tiền, bảng "Vì sao", từ chối đúng phạm vi | Cảnh 1, 2 (và nửa sau cảnh 4) | FR5, FR6, FR11, FR12 | [phase-3](phases/phase-3-what-if-va-kiem-tra.md) |
| 4. Chống chịu, lộ trình, phân hũ tự động (F4, F5) | 3–5/12 | Điểm chống chịu và 3 cú sốc; lộ trình có phiên bản, sinh lại khi hành vi đổi; pipeline sự kiện phân loại giao dịch | Cảnh 1–4 | FR2, FR7, FR8 | [phase-4](phases/phase-4-chong-chiu-lo-trinh.md) |
| 5. Nạp dữ liệu, hồ sơ hành vi, bộ nhớ, trace (F6, F7) | 6–8/12 | Nạp ảnh và CSV; hồ sơ hành vi và bản tin; bộ nhớ dài hạn; kho tri thức; màn hình trace | Cả 6 cảnh | FR9, FR10, FR13, FR14, FR15 | [phase-5](phases/phase-5-nap-du-lieu-ho-so-trace.md) |
| 6. Đánh giá, cứng hóa, đóng gói | 9–10/12 | Bộ đánh giá chạy được trong giới hạn quota, số đo NFR, tổng duyệt 6 cảnh trên điện thoại, README và tài liệu nộp | Cả 6 cảnh, có phương án dự phòng | NFR | [phase-6](phases/phase-6-danh-gia-dong-goi.md) |

Thứ tự ưu tiên theo proposal: F1 → F2 → F3, rồi F4, F5, F6, F7. Phase 5 và 6 có thể co lại nếu chậm: thứ cắt trước là sao kê PDF, FR14, AgentCore Evaluations, giao diện tối.

Bộ câu đánh giá không dồn về cuối: mỗi phase thêm câu chuẩn và test đối kháng của tính năng mình vào `evals/`, phase 6 chỉ chạy tổng và bổ sung cho đủ.

## 2. Quyết định áp dụng cho mọi phase

Các quyết định của chủ dự án (đã chốt trong yêu cầu ngày 2026-11-21) và các quyết định thiết kế người điều phối chọn để ghép chúng lại. Mục có dấu (*) là lựa chọn của người điều phối, chủ dự án có thể đổi khi duyệt kế hoạch.

### Không hardcode, không giả lập (chủ dự án, 2026-11-21)

Lúc demo agent phải chạy thật và mọi luồng đi qua đúng đường của nó. Áp dụng cho mọi phase và là một mục người điều phối kiểm khi đóng phase:

- Bản đã deploy không có câu trả lời soạn sẵn, không nhánh riêng cho câu hỏi demo, không so khớp chuỗi câu hỏi để trả kết quả định trước, không mock server, không dữ liệu giả trong frontend.
- Mọi con số trên màn hình đi từ Aurora qua tool hoặc engine; mọi câu trả lời trong chat do agent trên Runtime sinh ra ở lượt đó. Frontend không chứa số của persona.
- Dữ liệu persona là dữ liệu đầu vào được seed vào DB (hợp lệ, vì không có API giao dịch thật). Hiệu chỉnh bộ sinh để ra đúng tình huống demo thì được; gắn cứng đầu ra thì không. Engine cho số khác Figma thì dùng số của engine.
- Thẻ số liệu tất định khi LLM lỗi vẫn là kết quả tính thật từ tool, không phải nội dung dựng sẵn.
- Model giả, fixture, mock chỉ tồn tại trong unit test và không được import từ mã sản phẩm.
- Giá trị cấu hình (model id, ngưỡng, trần lượt gọi, URL, tên tài nguyên, biểu phí) nằm trong cấu hình, SSM hoặc bảng DB, không rải trong code.

### Hạ tầng và công cụ

- Region `ap-southeast-1`, đặt tường minh ở CDK `env`, mọi client boto3, mọi lệnh CLI (`--region`). Không dựa vào mặc định.
- CDK viết TypeScript trong `infra-cdk/`. Các stack: `YofinaFoundation` (S3, Budgets, SNS, bảng DynamoDB), `YofinaData` (Aurora, bật termination protection), `YofinaIdentity` (Cognito), `YofinaTools` (Lambda, HTTP API, EventBridge, SQS, Step Functions), `YofinaAgent` (Runtime, Gateway, Policy, Memory), `YofinaFrontend` (Amplify Hosting). Phần nào CDK chưa có construct ổn định (interceptor, Policy) thì dùng L1 hoặc script boto3 trong `scripts/`, lấy lại từ `spikes/agentcore-gateway-identity/`.
- **Không dùng Docker ở đâu cả** (*): Runtime deploy bằng zip; mọi Lambda đóng zip bằng `uv pip install --python-platform` (như spike Runtime đã làm cho ARM64). Hệ quả: không deploy StatsForecast (cần container 332 MB). Baseline seasonal naive tự viết bằng numpy; StatsForecast chỉ chạy trên máy trong báo cáo backtest. Đây là lệch so với overview.md ("StatsForecast cần Lambda container image").
- Không NAT Gateway, không VPC endpoint, không SageMaker, không OpenSearch. Lambda nằm ngoài VPC, gọi Aurora qua Data API. Aurora tối thiểu 0,5 ACU. Cần thứ tính tiền theo giờ khác thì hỏi chủ dự án.
- Tên tài nguyên có tiền tố `yofina-`, tag `project=yofina` (CDK gắn ở mức app). Mọi tài nguyên ghi vào [docs/aws-resources.md](../aws-resources.md) (tên, loại, stack, phase tạo; không ghi account ID hay ARN đầy đủ).
- Không đụng tài nguyên `jars-dev*`. Danh tính deploy có thêm policy Deny tường minh lên chúng (phase 1).
- Repo public: không commit account ID, ARN chứa account ID, secret, token, mật khẩu demo, email chủ dự án. Giá trị phụ thuộc tài khoản đi qua SSM Parameter Store, output của CloudFormation và file `.env.local` (đã có trong `.gitignore`). `cdk.context.json` không commit.

### Model và giới hạn

- Planner và đọc ảnh: Sonnet 4.6; dự phòng Kimi K3. Router, diễn giải, phân loại giao dịch: Nova 2 Lite (*, vì 20–25 request/phút so với 10 của Haiku 4.5); dự phòng Haiku 4.5. Embedding: Cohere Embed Multilingual. Chuỗi dự phòng bắt cả `ThrottlingException` lẫn `AccessDeniedException`.
- Một module duy nhất `yofina_core.llm` bọc mọi lời gọi Bedrock (agent, Lambda, pipeline, evals đều đi qua nó). Module này làm ba việc: giới hạn tốc độ mỗi model (mặc định 8 request/phút cho Claude 4.x), trần lượt gọi mỗi ngày đếm bằng DynamoDB (mặc định (*): 400 lượt Sonnet, 2.000 lượt model nhỏ, 3.000 lượt embedding; chạm trần thì trả lỗi có kiểu để luồng rẽ sang thẻ số liệu tất định), và ghi số token vào log.
- Thiết kế để một lượt hội thoại tốn ít lượt gọi: đường nhanh và F3 không cần LLM để ra số; what-if tối đa 1 lượt router + 2 lượt planner + 1 lượt diễn giải.
- Đánh giá chạy tuần tự có giãn nhịp, lưu kết quả từng câu để chạy tiếp khi đứt, ưu tiên evaluator viết bằng code.

### Xác nhận trước khi ghi

- Đã chốt: không có cờ xác nhận do LLM điền. Agent chỉ tạo khối `confirm`.
- Luồng (*): tool ghi được gọi không có `confirm_token` thì không ghi, trả `NEEDS_CONFIRMATION` và phát khối `confirm` chứa đúng tham số sẽ được ký. Người dùng bấm nút → frontend gọi `POST /confirmations` (HTTP API, JWT) lấy token dùng một lần (HMAC trên sub, tool, hash tham số, hạn 2 phút, `jti`) → frontend gọi `POST /actions` kèm token → Lambda `ledger` kiểm token rồi ghi và trả khối `receipt`. **LLM không nằm trên đường ghi.** Sau đó frontend chèn một dòng hệ thống vào hội thoại để agent biết việc đã làm.
- Tool ghi qua Gateway vẫn kiểm `confirm_token` theo cùng mã, và Cedar giữ làm lớp phụ (`user_id == principal.id`, hạn mức số tiền, có `confirm_token`).
- Interrupt/resume của AG-UI qua Runtime vẫn được thử ở phase 1 (mục "Chưa thử"), nhưng luồng xác nhận không phụ thuộc vào nó. Hỏi lại một câu (màn H5) là một lượt hội thoại thường.
- Ghi thành ADR-0002 ở phase 1.

### Đồng hồ mô phỏng (*)

Bảng số Figma và kịch bản demo giả định hôm nay là 21/11/2026 (hũ Ăn uống cạn 23/11, lương về 5/12), trong khi video quay và chấm vào khoảng 9–11/12. Mỗi tài khoản demo có `clock_offset_days`: khi bấm "Đặt lại dữ liệu", ngày mô phỏng của tài khoản quay về 21/11/2026 rồi trôi theo thời gian thật. Mọi tool, pipeline và màn hình lấy "hôm nay" qua một hàm duy nhất (`app_today(user)`); giao diện ghi "Ví mô phỏng · ngày mô phỏng". Nhờ vậy cảnh 1 luôn dựng lại được với đúng số.

### Tên gọi

- Sản phẩm trả sau trong app tên "Trả sau (mô phỏng)"; không dùng tên "Ví Trả Sau" hay MoMo trên giao diện. Router vẫn hiểu khi người dùng gõ "Ví Trả Sau". Biểu phí 33.000 ₫ mỗi tháng có giao dịch lấy từ biểu phí công khai làm ví dụ, ghi rõ nguồn trong kho tri thức. Chỗ nào frame Figma ghi "Ví Trả Sau" thì đổi nhãn khi code.
- "Điểm chống chịu", kèm dòng "không phải điểm tín dụng".

### Tài khoản demo

Cognito tắt tự đăng ký. Tạo sẵn: `minh` (persona chính), `lan` (sinh viên làm thêm), `khoa` (tài khoản mới 18 ngày dữ liệu, cho trạng thái độ tin cậy thấp), `giamkhao1`–`giamkhao3` (mỗi tài khoản một bản Minh riêng). Mật khẩu sinh ngẫu nhiên, lưu ở Secrets Manager, không vào repo. Nút "Đặt lại dữ liệu" trong Hồ sơ gọi `POST /demo/reset`: xóa dữ liệu của chính người dùng, sinh lại persona, tính lại dự báo.

## 3. Cách chia việc trong một phase

Mỗi file phase có cùng bố cục: mục tiêu, phạm vi, đọc trước, hợp đồng dùng chung, các luồng việc, tiêu chí hoàn thành, cách kiểm, rồi mục "Kết quả thực hiện" để điền sau.

1. **Hợp đồng trước** (một subagent, tuần tự): schema khối UI, schema tool, đặc tả REST, migration DB. Nằm trong `contracts/` và `db/migrations/`. Xong mới mở các luồng song song.
2. **Luồng song song** (mỗi luồng một subagent Sonnet 5.5, effort high): mỗi luồng sở hữu một tập thư mục riêng, không sửa thư mục của luồng khác; cần đổi hợp đồng thì báo người điều phối.
3. **Ghép và deploy** (một subagent hoặc người điều phối): chỉ bước này chạy `cdk deploy` và cập nhật Runtime, để không có hai lần deploy chồng nhau (cập nhật Runtime V2 mất khoảng 5 phút).
4. **Người điều phối tự kiểm**: chạy test, gọi thật trên môi trường đã deploy, đi lại cảnh demo liên quan bằng trình duyệt. Không tin báo cáo của subagent. Chưa đạt tiêu chí thì giao sửa, chưa sang phase sau.
5. **Đóng phase**: điền "Kết quả thực hiện" trong file phase, thêm entry ai-log, ghi đè HANDOFF.md, tick open-questions.md, cập nhật aws-resources.md, commit (không có dòng Co-Authored-By) và push.

Quy tắc cho mọi subagent:

- Đọc CLAUDE.md, HANDOFF.md, file phase, rồi các file trong mục "Đọc trước" của luồng mình. Chỗ spike mâu thuẫn ghi chú đọc tài liệu thì tin spike. Thứ ghi chú chưa phủ thì tra tài liệu chính thức hiện hành (aws-docs MCP, agentcore MCP, trang của thư viện) trước khi code.
- Lấy lại đoạn code đã chứng minh trong `spikes/` thay vì viết lại từ trí nhớ.
- Frontend lấy thiết kế qua Figma MCP (file `l9vWyORNRjDqiEOXqpbzYm`, node id trong [figma-ui-design.md](../research/figma-ui-design.md)).
- Test đi kèm code: unit test cho logic tất định, test tích hợp gọi môi trường đã deploy đặt trong `tests/integration/`.
- Không ghi account ID, secret, token vào file nào được commit. Không tạo tài nguyên AWS ngoài danh sách của phase.
- Báo cáo cuối: đã làm gì, lệch gì so với plan, lệnh để kiểm lại, thứ chưa xong.

## 4. Bố cục mã nguồn

Giữ cây thư mục ở [project-structure.md](../architecture/project-structure.md), thêm:

| Thư mục | Chứa |
|---|---|
| `contracts/` | Nguồn duy nhất cho hợp đồng: `blocks/*.schema.json` (khối UI), `tools/*.json` (schema tool cho Gateway), `rest/openapi.yaml`. Script sinh Zod (frontend) và Pydantic (Python) từ đây |
| `libs/yofina_core/` | Gói Python dùng chung cho agent, Lambda và pipeline: client Data API (transaction + `set_config`, retry `DatabaseResumingException`), `llm` (giới hạn và trần), token xác nhận, dựng khối UI, che PII, `app_today`, định dạng tiền |
| `ml/yofina_ml/` | Dự báo hurdle, ACI, Monte Carlo, điểm chống chịu, PELT/CUSUM, LP. Chỉ phụ thuộc numpy, scipy, ruptures |
| `docs/aws-resources.md` | Danh sách tài nguyên AWS đã tạo |

Python quản lý bằng uv (một workspace ở gốc repo); frontend và CDK dùng npm.

## 5. Việc chủ dự án phải tự làm

| Khi nào | Việc |
|---|---|
| Trước phase 1 | Đăng nhập lại AWS: cả `aws login` trên máy lẫn connector AWS MCP đều đã hết phiên (kiểm 2026-11-21) |
| Đầu phase 1 | Sau khi agent tạo IAM user `yofina-deployer` bằng phiên root: vào console đặt mật khẩu và MFA cho user đó, bật MFA cho root nếu chưa, rồi `aws login --profile yofina-deploy` và kết nối lại connector AWS MCP bằng user mới. Chi tiết ở [phase 1](phases/phase-1-nen-va-lat-doc.md#luồng-a--danh-tính-deploy-và-nền-cdk) |
| Đầu phase 1 | Cho biết số tiền ngân sách tháng và email nhận cảnh báo (email không vào repo; mặc định đề xuất 100 USD, ngưỡng 50/80/100%) |
| Cuối phase 1 và phase 6 | Mở app trên Safari iPhone thật một lần (người điều phối không làm thay được) |
| Phase 5 | Trả lời có bật CloudWatch Transaction Search không (đổi cấu hình mức tài khoản, có phí ghi span) |
| Phase 6 | Quay video, làm slide, nộp bài |

## 6. Rủi ro của kế hoạch

| Rủi ro | Cách xử lý |
|---|---|
| Quota 10 request/phút làm chậm kiểm thử và đánh giá | Mọi lời gọi đi qua `yofina_core.llm`; test logic dùng model giả; test thật giãn nhịp; đánh giá chạy nền, chạy tiếp được |
| Lát dọc phase 1 lộ ra thứ spike chưa thấy (interrupt qua Runtime, MCPClient với Gateway thật, CORS domain thật) | Mỗi điểm có thời hạn thử riêng và phương án lùi ghi sẵn trong file phase 1; luồng xác nhận không phụ thuộc interrupt |
| Persona Minh không ra đúng số của Figma | Hiệu chỉnh bộ sinh để ngày cạn hũ Ăn uống rơi đúng 23/11; các số khác lấy theo engine, lệch thì sửa nhãn giao diện, không sửa engine. Từ 26/11 ví demo dùng bộ hũ riêng (Chi hằng ngày, Nghĩa vụ, Dự phòng cộng hũ tự thêm, giữ Ăn uống) nên cảnh 1 vẫn ra 23/11 |
| Đổi bộ hũ mặc định giữa phase 6 (26/11: tài khoản mới 3 hũ theo mục đích, issue #39) làm số đo cũ không còn đúng cho mọi ví | Ví demo giữ hũ chi riêng nên số của cảnh 1–4 dùng được; số phân loại 92% / 17,4%, cổng 47/120 ngày, PELT 2,04 chỉ gắn với ví nhiều hũ theo loại chi; ví 3 hũ dẫn [số đo riêng](../research/2026-11-26-do-vi-ba-hu.md) |
| Khoảng dự báo 30 ngày phủ thiếu (đã đo) | Phase 2 hiệu chỉnh bằng độ phủ trên backtest trước khi hiện xác suất hụt; hiện nhóm Cao/Vừa/Thấp thay vì phần trăm khi chưa đạt |
| Ổ C còn 12 GB | Xóa `.venv` và `node_modules` trong `spikes/` trước khi cài project (giữ mã nguồn spike) |
| Chi phí | Budgets + trần lượt gọi; Aurora 0,5 ACU khoảng 73 USD/tháng là khoản lớn nhất |
