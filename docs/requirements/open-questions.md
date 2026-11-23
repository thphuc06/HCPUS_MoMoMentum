# Câu hỏi mở

Tick `[x]` khi đã chốt và ghi kết quả bên dưới câu hỏi (kèm ngày). Quyết định kỹ thuật quan trọng thì ghi thêm thành ADR trong [../decisions/](../decisions/README.md).

## Về scope (proposal §16, giữ nguyên 8 câu)

- [ ] Hạn nộp bài chính xác là ngày nào, và tiêu chí chấm có trọng số ra sao? *(kế hoạch hiện giả định nộp trước chung kết 11/12/2026)*
- [ ] Đội có 2 hay 3 người, ai làm frontend? *(nếu 2 người: gộp vai frontend vào người lo agent và cắt F6 — proposal §15)*
- [ ] Persona chính là sinh viên đi làm thêm hay người đi làm 1 đến 3 năm?
- [x] Demo dùng tên và biểu phí Ví Trả Sau thật, hay một sản phẩm trả sau mô phỏng? *(đề xuất của proposal: mô phỏng, dẫn biểu phí công khai làm ví dụ)*
  - Chốt 2026-11-21 (chủ dự án): sản phẩm trả sau **mô phỏng**, lấy biểu phí công khai làm ví dụ; giao diện ghi "Trả sau (mô phỏng)".
- [x] Tool viết Python toàn bộ, hay tách phần sổ cái sang Java Spring?
  - Chốt 2026-11-21 (chủ dự án): Python toàn bộ.
- [x] Chronos-2 có cần cho MVP không, hay chạy mô hình thống kê trước? *(proposal §14: "MVP nếu kịp, không thì mở rộng")*
  - Chốt 2026-11-21 (chủ dự án): để ngoài, cùng SageMaker; dùng hurdle tự viết và baseline thống kê.
- [ ] Giữ tên Yofina hay đổi tên?
- [ ] Mở app MoMo kiểm tra lại: đã có dự báo, what-if hay lộ trình theo mục tiêu chưa? Có hũ có số dư riêng chưa? Chuyển tiền cho cá nhân có được tự phân loại không?

## Hạ tầng và môi trường (phát sinh khi scaffold)

Không phải câu hỏi của proposal; ghi nhận ngày 2026-11-21 từ trạng thái máy.

- [x] **Region triển khai**: AWS CLI đang để mặc định `us-east-1`, proposal nhắc Singapore (`ap-southeast-1`; §13 ghi AgentCore có ở Singapore theo tra cứu 20/11/2026, từng tính năng con cần kiểm riêng trong tuần 1). Cần chốt Region trước khi deploy; sau đó đặt Region tường minh trong cấu hình CDK/CLI. Kiểm tính năng theo Region bằng `get_regional_availability` hoặc tài liệu AWS ([aws-tooling.md](../references/aws-tooling.md)).
  - Chốt 2026-11-21 (chủ dự án): `ap-southeast-1`, đặt tường minh ở mọi nơi.
- [x] **Danh tính deploy**: CLI đang đăng nhập bằng root user của tài khoản. Nên tạo IAM user/role riêng (quyền tối thiểu đủ để chạy CDK) cho việc deploy và không dùng root.
  - Chốt 2026-11-21 (chủ dự án): **tiếp tục dùng root** cho bản hackathon; IAM user `yofina-deployer` đã tạo sẵn nhưng chưa dùng. Rủi ro đã nêu cho chủ dự án (root không bị policy nào giới hạn).
  - Kế hoạch ban đầu 2026-11-21: việc đầu tiên của [phase 1](../plan/phases/phase-1-nen-va-lat-doc.md#luồng-a--danh-tính-deploy-và-nền-cdk); tick khi xong.
- [x] **Khung FAST**: kéo FAST về bằng cách nào?
  - Chốt 2026-11-21 (chủ dự án): **không kéo FAST về**. FAST chỉ là nguồn tham khảo; code tự viết theo tài liệu chính thức của từng dịch vụ/thư viện. Khác với proposal §8 và §14 ("khởi đầu từ khung FAST"). Xem [project-structure.md](../architecture/project-structure.md#fast-chỉ-để-tham-khảo).
- [x] **Frontend**: dùng framework và thư viện giao diện nào?
  - Chốt 2026-11-21 (chủ dự án, sau khi xem ảnh màn hình mẫu): React + Vite SPA, shadcn/ui + Tailwind, Recharts + SVG tự vẽ, Motion. Xem [ADR-0001](../decisions/0001-frontend-stack.md).
  - Tiêu chí của chủ dự án (2026-11-21): ưu tiên cái nào cho giao diện đẹp nhất. Không copy frontend của FAST; stack ở proposal §14 (Next.js + React, Tailwind, Recharts/visx, client AG-UI) là điểm xuất phát, không bắt buộc. Chốt stack cụ thể khi bắt đầu làm frontend, sau khi tra các lựa chọn hiện hành; ghi ADR.

## Rút ra từ nghiên cứu (2026-11-21)

Từ bảy ghi chú đọc tài liệu và bảy spike chạy thật trong [../research/](../research/README.md). Mỗi dòng ghi rõ **đã chạy thử** hay mới **đọc tài liệu**.

### Cần chủ dự án quyết

- [x] **Cơ chế xác nhận trước khi ghi**: proposal §9 để Cedar cho tool ghi chạy khi tham số có cờ xác nhận; cờ do LLM điền nên giả mạo được. Đề xuất: người dùng bấm nút → endpoint riêng cấp token dùng một lần (gắn người dùng + tham số, hạn ngắn) → tool ghi kiểm token; Cedar làm lớp phụ (hạn mức, khớp người dùng). **Đã chạy thử** 13 ca đúng kỳ vọng. [spike-agentcore-gateway-identity.md](../research/spike-agentcore-gateway-identity.md), [spike-strands-agui-local.md](../research/spike-strands-agui-local.md)
  - Chốt 2026-11-21 (chủ dự án): agent chỉ tạo khối xác nhận; người dùng bấm nút thì server cấp token dùng một lần, tool ghi kiểm token; Cedar là lớp phụ; không dùng cờ do LLM điền. Cách ghép cụ thể: [master-plan.md](../plan/master-plan.md#xác-nhận-trước-khi-ghi), sẽ ghi ADR-0002 ở phase 1.
- [x] **Bộ model**: chủ dự án không xin tăng quota được; Claude 5.x bị chặn (`AccessDeniedException`). **Đã gọi thử** ở Singapore: Sonnet 4.6 (planner, đọc ảnh), Haiku 4.5 hoặc Nova 2 Lite/Nova Pro (router, diễn giải), Kimi K3 (dự phòng), Cohere Embed Multilingual v3/v4. Claude 4.x chỉ 10 request/phút mỗi model: đủ demo một người, không đủ cho nhiều người hoặc chạy bộ đánh giá. `us-east-1` có quota rộng hơn (dữ liệu xử lý ở Mỹ). [spike-bedrock-models.md](../research/spike-bedrock-models.md)
  - Chốt 2026-11-21 (chủ dự án): Sonnet 4.6 (planner, đọc ảnh), Nova hoặc Haiku 4.5 (router, diễn giải), Kimi K3 dự phòng, Cohere Embed Multilingual. Không tăng quota được; thiết kế và đánh giá tính tới 10 request/phút.
- [x] **Chronos-2**: **đã đo** trên dữ liệu tổng hợp: hòa với mô hình hurdle tự viết (chỉ cần numpy), thắng ETS; cần torch + container. Đề xuất không đưa vào MVP. Lưu ý hurdle cùng họ với bộ sinh dữ liệu nên được lợi. [spike-ml-forecasting.md](../research/spike-ml-forecasting.md)
  - Chốt 2026-11-21 (chủ dự án): để ngoài.
- [x] **Tên "FinHealth Score"**: dùng Score trong phần mềm thương mại cần license; chưa rõ chỉ số tự tính có bị áp dụng không. Đề xuất gọi "Điểm chống chịu", ghi "lấy cảm hứng từ". Đọc tài liệu. [ml-forecasting.md](../research/ml-forecasting.md)
  - Chốt 2026-11-21 (chủ dự án): gọi "Điểm chống chịu", không dùng tên FinHealth Score.
- [x] **Bỏ Bedrock Data Automation**: không liệt kê tiếng Việt; model đọc ảnh trực tiếp đã thử được (Sonnet 4.6, Kimi K3 đúng cả bốn trường trên 3 ảnh dựng). [bedrock.md](../research/bedrock.md), [spike-bedrock-models.md](../research/spike-bedrock-models.md)
  - Chốt 2026-11-21 (chủ dự án): bỏ; cũng bỏ Automated Reasoning.
- [ ] **Dữ liệu xử lý ngoài Singapore**: nhiều model ở Singapore chỉ có profile `global`; cần ghi rõ trong phần quyền riêng tư. Đọc tài liệu. [bedrock.md](../research/bedrock.md)
- [ ] **Mục tiêu "ký tự đầu dưới 1,5 giây"** (NFR): **đã đo** không đạt khi phiên Runtime lạnh (event đầu khoảng 2,5 giây; ấm khoảng 0,3 giây). Đề xuất mở phiên ngay khi người dùng vào app, hoặc nới mục tiêu cho lượt đầu. [spike-agentcore-runtime-cors.md](../research/spike-agentcore-runtime-cors.md)
- [x] **Stack frontend** (chốt 2026-11-21, [ADR-0001](../decisions/0001-frontend-stack.md)): React + Vite SPA, shadcn/ui + Tailwind, Recharts + SVG tự vẽ, Motion, font Plus Jakarta Sans. **Đã dựng thử.**

### Chỉnh kiến trúc so với proposal (đã áp vào overview.md ngày 2026-11-21)

Các mục dưới đây đã được phản ánh trong [overview.md](../architecture/overview.md) với nhãn **[đã chạy thử]**, **[đọc tài liệu]** hoặc **[đề xuất]**; cơ chế xác nhận và bộ model vẫn ghi là đề xuất vì chủ dự án chưa chốt (mục "Cần chủ dự án quyết" ở trên).

- [ ] **Tên tool** (đã chạy thử): Gateway từ chối dấu chấm; tool hiện ra là `ledger___get_jar_balances` (target `ledger`). [spike-agentcore-gateway-identity.md](../research/spike-agentcore-gateway-identity.md)
- [ ] **Danh tính xuống tool** (đã chạy thử): Lambda sau Gateway không nhận claim nào; header do client gửi đi qua nguyên văn nên không tin được. Dùng hai lớp: interceptor đọc JWT đã xác minh và ghi đè `user_id`, cộng Cedar `context.input.user_id == principal.id`. [spike-agentcore-gateway-identity.md](../research/spike-agentcore-gateway-identity.md)
- [ ] **Frontend gọi thẳng Runtime** (đã chạy thử): không cần proxy; gửi **access token** Cognito (ID token bị từ chối); session id 33–256 ký tự; dùng Runtime **V2** (V1 không ghim phiên theo người dùng); gửi lại toàn bộ `messages` mỗi lượt. Deploy bằng zip lên S3, không cần Docker. [spike-agentcore-runtime-cors.md](../research/spike-agentcore-runtime-cors.md)
- [x] **Khối UI** (đã chạy thử hai đầu, chưa nối với nhau): tool phát khối thành event `ACTIVITY_SNAPSHOT` trước khi trả kết quả gọn cho LLM; frontend render qua registry `type → component`. Khối không nằm trong lịch sử hội thoại nên phải lưu DB để phát lại. Không gửi khối qua state (bị xóa cuối lượt). JSON gộp của §9 giữ làm bản ghi. [spike-strands-agui-local.md](../research/spike-strands-agui-local.md), [spike-frontend-stack.md](../research/spike-frontend-stack.md)
  - Đã nối (phase 1 và 2): khối do tool phát hiện trong chat qua registry, lưu DB và phát lại sau tải trang; `forecast_timeline` dùng chung component với màn Chi tiết hũ (kiểm trên trình duyệt 22/11).
- [ ] **Xác nhận trong luồng agent** (đã chạy thử local): `ToolBehavior(interrupt_on_call=True)` + session manager bền; resume chạy được sau khi khởi động lại server. [spike-strands-agui-local.md](../research/spike-strands-agui-local.md)
- [x] **Thêm REST API cho màn hình không cần LLM** (khai báo, hũ, chuyển tiền, danh sách xem lại, cấp token xác nhận): HTTP API + JWT Cognito, dùng chung Lambda sổ cái. Đọc tài liệu. [aws-data-events-infra.md](../research/aws-data-events-infra.md)
  - Xong ở phase 2 (22/11): `yofina-api` 18 route, ghi qua `POST /confirmations` rồi `POST /actions`; đã đi trên trình duyệt.
- [x] **F3 không dùng Graph của Strands**: viết code tuần tự có timeout cho bước LLM. Đọc tài liệu. [strands-agui.md](../research/strands-agui.md)
  - Xong ở phase 3 (22/11): `agent/src/yofina_agent/turn.py` gọi `affordability_check`, phát `affordability_card` rồi mới gọi model nhỏ viết hai câu; quá hạn thì bỏ phần lời. Chưa đo trên Runtime.
- [x] **Aurora qua Data API** (đã chạy thử): đủ nhanh (luồng 3 truy vấn p95 khoảng 113 ms từ Lambda). Không để tự tắt khi demo (đánh thức 16 giây và lệnh đầu lỗi, phải retry `DatabaseResumingException`). RLS: tool dùng role riêng không phải owner (master user vượt được RLS); `set_config` phải nằm trong transaction hoặc hàm plpgsql. Mọi truy vấn có `LIMIT` (phản hồi tối đa 1 MiB). [spike-aurora-data-api.md](../research/spike-aurora-data-api.md)
  - Đo ở phase 2 (22/11): `GET /overview` phía Lambda p95 18 ms (n=60, `scripts/measure_wallet.py`).
- [x] **Dự báo và Monte Carlo** (đã chạy thử trên dữ liệu tổng hợp; **đã cài và chạy thật ở phase 2**, 22/11: engine `yofina_ml` trong Lambda zip arm64 numpy + scipy (không Docker), batch đêm `yofina-nightly`, đường sự kiện SQS, tool `forecast___get_forecast`; Monte Carlo 7 hũ x 10.000 đường khoảng 0,65 giây trên Lambda 1.769 MB; mô hình trên dữ liệu không cùng họ bộ sinh đã đo ở [backtest-phase-2.md](../research/backtest-phase-2.md); số đo hạ tầng ở [pipelines/forecast/README.md](../../pipelines/forecast/README.md)): hurdle tự viết cho hũ; mô phỏng có tương quan giữa các ngày (lấy mẫu độc lập đánh giá thấp xác suất hụt); khoảng dự báo tổng 30 ngày phủ thiếu ở mọi mô hình — cần xử lý trước khi hiện xác suất hụt; StatsForecast phải đóng container (332 MB); PELT theo tuần, bỏ ADWIN; LP bằng `scipy.optimize.linprog` với mức phạt theo ưu tiên. [spike-ml-forecasting.md](../research/spike-ml-forecasting.md)
- [ ] **Phân loại giao dịch** (đã chạy thử, 43 chuỗi): bỏ ngưỡng 0,97; chuẩn hóa chuỗi (bỏ dấu, chữ thường, mở rộng viết tắt) trước khi nhúng; hiệu chỉnh ngưỡng theo từng model. Không dùng Haiku 4.5 để đọc ảnh (tự sửa sai nội dung không dấu). [spike-bedrock-models.md](../research/spike-bedrock-models.md)
- [ ] **Structured output** (đã chạy thử): luôn đặt `structured_output_attempts`, nếu không vòng lặp có thể không dừng; không chuyển nguyên event stream của Strands ra trình duyệt (chứa system prompt). Nova không hỗ trợ `outputConfig`, dùng ép tool. [spike-strands-agui-local.md](../research/spike-strands-agui-local.md), [spike-bedrock-models.md](../research/spike-bedrock-models.md)
- [x] **Che PII**: Guardrails không kiểm kết quả tool và không có mẫu PII Việt Nam; che ở Lambda tool và bước nạp dữ liệu. Đọc tài liệu, chưa tạo guardrail thử. [bedrock.md](../research/bedrock.md)
  - Phase 3 (22/11): `yofina_core.pii` che SĐT, CCCD, số tài khoản trước khi vào LLM và trước khi ghi bộ nhớ; Guardrail `yofina-guardrail` chỉ lọc chủ đề cấm và prompt injection. Đã deploy; `ApplyGuardrail` chặn câu "nên mua cổ phiếu VNM" (`GUARDRAIL_INTERVENED`).
- [ ] **Automated Reasoning checks**: chỉ tiếng Anh, không có ở Singapore; giữ verifier Python. Đọc tài liệu. [bedrock.md](../research/bedrock.md)
- [ ] **Phiên bản** (đã cài thử): `strands-agents` 1.65.0, `ag-ui-strands` 1.0.4, `ag-ui-protocol` 1.0.0, `@ag-ui/client` 1.0.5; thư viện `mcp` 2.x đổi tên hàm so với mẫu của FAST.

### Chưa thử (cần làm khi dựng thật)

Các điểm này được thử trong [phase 1](../plan/phases/phase-1-nen-va-lat-doc.md) (bảng phép thử) và phase 2, 3, 5; tick khi có kết quả.

- [x] Nối frontend thật với Runtime thật: **chạy** (22/11, người điều phối tự đi trên trình duyệt với bản build ở localhost nối backend thật: hỏi số dư, chuyển hũ qua xác nhận, phát lại sau tải trang). Phía backend đã chạy (22/11): token Cognito → Runtime V2 → Gateway (interceptor + Cedar `ENFORCE`) → Aurora, khối UI qua SSE, lưu và đọc lại hội thoại ([spike-vertical-slice.md](../research/spike-vertical-slice.md)); còn thử từ app đã host bằng trình duyệt.
- [x] Interrupt/resume AG-UI qua Runtime với session manager bền: **chạy** với `S3SessionManager`, kể cả khi microVM bị dừng; không session manager thì `UNKNOWN_INTERRUPT_ID` sau khi microVM đổi. Yofina không dùng (ADR-0002). `AgentCoreMemorySessionManager` chưa thử ([spike-vertical-slice.md](../research/spike-vertical-slice.md) mục 5).
- [ ] CORS từ domain thật, Safari trên iPhone, Amplify Hosting. Đã thử bằng `curl` với Origin là URL Amplify: preflight 200, `Access-Control-Allow-Origin: *`, header frontend được phản chiếu ([spike-vertical-slice.md](../research/spike-vertical-slice.md) mục 10); còn thử từ trình duyệt thật và Safari iPhone.
- [x] Strands `MCPClient` xử lý thế nào khi Cedar từ chối (lỗi giao thức `-32002`): với Gateway thật `MCPClient` nuốt thành chuỗi, `_GatewayMCPClient` giữ ngoại lệ gốc và đọc `MCPError.code`; người dùng thấy khối `notice` "Không có quyền thực hiện" ([spike-vertical-slice.md](../research/spike-vertical-slice.md) mục 3).
- [x] Cedar `context.input.user_id` khi `user_id` là tham số tùy chọn trong schema: chạy (`has` + so với `principal.id`); không interceptor thì `user_id` của người khác, vắng hoặc rỗng đều bị `-32002` ([spike-vertical-slice.md](../research/spike-vertical-slice.md) mục 2).
- [x] Thông điệp từ chối của Gateway khi không bật `DEBUG`: giống bản `DEBUG` với luật toàn `permit`; dùng mức mặc định ([spike-vertical-slice.md](../research/spike-vertical-slice.md) mục 4).
- [x] Token hết hạn giữa luồng SSE: luồng đang mở không bị cắt; lời gọi Gateway sau lúc hết hạn ra `403 -32002 insufficient_scope` (agent nhận diện, hiện "cần đăng nhập lại"); Runtime từ chối request mới với token hết hạn hoặc sắp hết hạn trong vòng một phút ([spike-vertical-slice.md](../research/spike-vertical-slice.md) mục 6).
- [x] Số đo lát dọc: event đầu lượt 1 phiên lạnh trung vị 2,04 s, lượt 2 0,34 s; trọn lượt 5,75 s và 3,00 s; Gateway ấm có interceptor + Cedar 174 ms so với 140 ms Lambda trực tiếp ([spike-vertical-slice.md](../research/spike-vertical-slice.md) mục 7).
- [x] Sonnet 4.6 làm Analyst và Orchestrator: **chạy** trên Runtime (22/11, bộ golden phase 3, 4 trên 8 ca what-if đạt; `whatif-bnpl` đỏ vì Verifier). Guardrails: **chạy** (xem "Che PII"). Còn chưa thử: ảnh chụp màn hình thật, Knowledge Bases.
- [ ] Mô hình dự báo trên dữ liệu không do cùng bộ sinh tạo ra.

### Cần chủ dự án chốt (phát sinh ở phase 3, 22/11)

- [ ] **Độ trễ Guardrail** (đo 23/11, `scripts/measure_phase3.py`): `ApplyGuardrail` p50 446 ms, p95 531 ms trong lượt, vượt ngưỡng 400 ms của kế hoạch phase 3. Đầu vào chạy song song với router nên không cộng vào lượt; đầu ra chạy tuần tự trước khi phát chữ (khoảng 0,4 s). Chấp nhận, hay bỏ lọc đầu ra cho phần chữ đã qua NumericGrounding và luật suitability?
- [ ] **Guardrail fail-open** (F5): lưu ý 22–23/11 Guardrail luôn AccessDenied trên Runtime mà không ai thấy vì fail-open chỉ ghi log; nên có cảnh báo CloudWatch cho `guardrail_error`. `guardrail_fail_open: true` trong `agent/src/yofina_agent/defaults.json`; Guardrail lỗi hoặc quá 3 giây thì lượt đi tiếp không lọc đầu vào, chỉ còn router và Verifier chặn. Giữ fail-open (ưu tiên demo không gãy) hay đổi sang fail-closed (chặn khi không lọc được)?
- [ ] **Ngưỡng đủ/sát/hụt**: `short_floor` và `tight_floor` cùng bằng 0 nên Hóa đơn 250.000 ₫ của `minh` ra "hụt" (không phải "vàng" như câu chữ tiêu chí 3) và dải "sát" rất hẹp; hụt 1 đồng và hụt 200 nghìn cùng một nhãn. Giữ, hay đặt `tight_floor` > 0 (CDK context `affordabilityTightP10FloorVnd`)?
- [ ] **Phí Trả sau trong tiêu chí 1 và 3** (đã chốt tạm 22/11 theo engine: 2.200.000 ₫ và 1.250.000 ₫): giữ quy tắc phí một lần mỗi nghĩa vụ, hay đổi quy tắc hoặc persona `minh` để ra 1.233.000 ₫ và 283.000 ₫ như câu chữ cũ?
- [ ] **Trần model mỗi lượt** (F6): 4 lượt (`max_model_calls_per_turn`) làm vòng sửa thứ hai của Verifier không chạy được. Giữ 4 (khớp tiêu chí 9) hay nâng lên 5?
- [ ] **Tên miền Amplify trong repo public** (F10): tên miền `*.amplifyapp.com` ở `HANDOFF.md` và `docs/aws-resources.md`. Giữ, hay thay bằng chỗ giữ chỗ?
