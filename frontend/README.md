# frontend/

Web app Yofina ưu tiên điện thoại (khung 390 px; trên màn rộng căn giữa thành khung điện thoại). Stack theo [ADR-0001](../docs/decisions/0001-frontend-stack.md): React + Vite + TypeScript, Tailwind 4, shadcn/ui (Base UI), `@ag-ui/client`, Zod. Thiết kế theo Figma `l9vWyORNRjDqiEOXqpbzYm` ([figma-ui-design.md](../docs/research/figma-ui-design.md)).

Trạng thái (25/11/2026): các màn của phase 1 đến 5 đã ghép với backend thật và chạy trên Amplify Hosting (stack `YofinaFrontend`, deploy bằng `scripts/deploy_frontend.py`); các đoạn dưới ghi theo từng phase.

Phase 2: **luồng D đã ghép với backend thật** ([các màn ví và dự báo](../docs/plan/phases/phase-2-vi-va-du-bao.md#luồng-d--frontend-các-màn-hình-ví-và-dự-báo)), xây trên phase 1; đã đi hết các màn với `minh`, `khoa`, `lan` trên API AWS thật. Có: đăng nhập Cognito SRP; **Tổng quan** (một lệnh `GET /overview`), **Hũ**, **Chi tiết hũ** với biểu đồ dự báo 30 ngày, **Nhìn trước**, **Chuyển tiền** (T1, T2, T4, T5), **Hoạt động**, **Onboarding** (O1–O3), **Nghĩa vụ** (thêm, sửa, xóa), **Tiền vào** và ô Tiền vào khác, **Lương về** (xác nhận một chạm), **Giữa hũ**, **Thêm hoặc sửa hũ**, **Hồ sơ** (sửa lương và ngày nhận, đặt lại dữ liệu, đăng xuất); sheet chat với tám khối (`jar_summary`, `confirm`, `receipt`, `notice`, `forecast_timeline`, `proactive_card`, `confirm_action`, `receipt_action`). Thẻ kiểm tra đủ/sát/hụt (T3) là phase 3; Quét QR và "Kiểm tra" ở Tổng quan là nút vô hiệu có nhãn "Sắp có".

**Phase 5 (luồng E)**: Hồ sơ thay khung S1 (xem bảng dưới); thẻ chủ động ở Tổng quan ưu tiên bản tin của cổng giá trị (`GET /nudges/today`; "Để sau", "Ít nhắc loại này" và nút làm việc gửi `POST /nudges/{id}/feedback`, thẻ tất định của `/overview` chỉ còn khi không có bản tin); khối `behavior_insight` và `citation` trong registry (23 khối); bảng vận hành và màn trace X1 cho nhóm `ops`. `dev-mocks/server/readonly.ts` trả thẳng fixture hợp đồng (chỉ đọc, không giữ trạng thái) cho chống chịu, lộ trình, bản tin (rỗng), bộ nhớ, "Vì sao", duyệt; câu chat "khoi <tên fixture>" (ví dụ "khoi citation.phi_tra_sau") phát đúng khối mẫu đó, "van ban dai" trả một lời dài để xem "Xem thêm"; email bắt đầu bằng `ops` ở `dev:mock` thuộc nhóm `ops`.

**Màn hình và đường dẫn** (hash router; màn toàn khung không có tab bar):

| Đường dẫn | Màn | Dữ liệu |
|---|---|---|
| `/` | Tổng quan (chưa khai thì chuyển sang `/onboarding`) | `GET /overview` |
| `/jars`, `/jars/:code`, `/jars/edit` | Danh sách hũ; Chi tiết hũ; thêm/sửa hũ | `/overview`; `GET /jars/{code}` + `GET /forecasts/{code}` song song; `save_jars` |
| `/foresight` | Nhìn trước: hũ nào cạn trước, chất lượng dự báo | `/overview` |
| `/transfer` → `/amount` → `/review` → `/receipt` | Chuyển tiền T1, T2, T4, T5 | `GET /payees`, `/credit-line`, `/tx-types`; `record_transaction` |
| `/activity` | Hoạt động (lọc theo hũ, "Cần xem lại", con trỏ) | `GET /transactions` |
| `/onboarding` | O1 lương + ngày nhận (bắt buộc), O2 hũ + tỷ lệ, O3 chi phí cố định | `update_profile`, `save_jars`, `GET /jar-templates` |
| `/obligations`, `/obligations/new`, `/obligations/:id` | Nghĩa vụ và hạn mức Trả sau | `GET /obligations`, `/credit-line`; `update_profile` |
| `/income`, `/salary`, `/move` | Tiền vào + Tiền vào khác; xác nhận lương về; chuyển giữa hũ | `record_transaction`, `confirm_salary`, `move_between_jars` |
| `/profile` | Hồ sơ: thông tin khai báo, nhận xét hành vi, bộ nhớ của trợ lý (xem, xóa từng mục, xóa hết), đồng ý theo nguồn nạp, đặt lại dữ liệu demo, xóa dữ liệu của tôi (token xác nhận), đăng xuất | `/overview`; `GET /profile/behavior`; `GET/DELETE /memory`; `GET /ingest/jobs`; `update_profile`; `POST /demo/reset`; `POST /me/delete-data/confirmations` + `POST /me/delete-data` |
| `/roadmap`, `/roadmap/compare?from=&to=` | Lộ trình thích ứng (kèm danh sách phiên bản: bấm để xem từng bản, so với bản đang dùng); So với bản cũ. Lối vào: thẻ trên tab Nhìn trước, dòng ở Tổng quan | `GET /roadmap`, `/roadmap/versions`, `/roadmap/diff` |
| `/ops/summary` (`/ops` chuyển về đây), `/ops/traces/:traceId` | Bảng vận hành và màn trace X1 (chỉ nhóm Cognito `ops`, đọc nhóm từ claim `cognito:groups` của access token; khung giãn thành desktop 1280×800 trên màn rộng). Lối vào: hàng "Mã trace" của bảng "Vì sao", dòng "Bảng vận hành" ở Hồ sơ | `GET /ops/summary`, `/ops/traces`, `/ops/traces/{id}` |

## Chạy

```bash
cd frontend
npm install
cp .env.example .env.local        # điền giá trị (hoặc: uv run scripts/print_env.py frontend --write ở gốc repo)
npm run dev                       # backend thật
npm run build && npm run preview -- --port 5173 --strictPort   # bản build chạy với backend thật (cần .env.local); cách kiểm với API thật
npm run dev:mock                  # máy chủ giả trong dev-mocks/, không cần backend và không cần đăng nhập thật
                                  # (email bất kỳ + mật khẩu bất kỳ khác "sai"; email bắt đầu "trang" = tài khoản chưa khai để thử onboarding,
                                  #  "moi" = tài khoản ít dữ liệu "ước lượng ban đầu"; trạng thái giữ trong bộ nhớ theo email, khởi động lại là về ban đầu)

npm test                          # Vitest + Testing Library (unit và tích hợp mức ứng dụng)
npm run typecheck                 # tsc -b
npm run lint                      # oxlint
npm run build                     # tsc -b && vite build -> dist/
npm run check:bundle              # grep dist/: không mock, fixture, số liệu persona, bí mật, từ cấm; in kích thước gzip
```

Đăng nhập Cognito thật (bỏ qua nếu thiếu biến môi trường), dùng đúng `CognitoAuthClient` của app:

```bash
YOFINA_LIVE_EMAIL=... YOFINA_LIVE_PASSWORD=... npx vitest run src/auth/cognito.live.test.ts
```

Deploy: `npm run build` rồi `uv run scripts/deploy_frontend.py frontend/dist` (Amplify, zip thủ công). Router là **hash router** (`#/profile`), nên Amplify không cần quy tắc rewrite SPA và tải lại trang không bị 404. Biến `VITE_*` được nhúng lúc build: build trên máy có `.env.local` đúng của môi trường cần deploy.

## Cấu hình (`.env.local`, không commit; mẫu ở `.env.example`)

| Biến | Bắt buộc | Ý nghĩa |
|---|---|---|
| `VITE_AWS_REGION` | có | Region (dựng URL Runtime từ ARN) |
| `VITE_COGNITO_USER_POOL_ID`, `VITE_COGNITO_CLIENT_ID` | có | User pool và app client công khai (chỉ SRP) |
| `VITE_API_URL` | có | URL gốc HTTP API `yofina-api` (không có `/` cuối). Chấp nhận cả tên cũ `VITE_API_BASE_URL` |
| `VITE_AGENT_RUNTIME_URL` hoặc `VITE_AGENT_RUNTIME_ARN` | có một | URL đầy đủ của `/invocations?qualifier=DEFAULT` (`print_env.py` chỉ ghi biến này; ARN chứa account ID mà Vite nhúng mọi `VITE_*` vào bundle nên `check:bundle` từ chối), hoặc ARN của Runtime (tự dựng `https://bedrock-agentcore.<region>.amazonaws.com/runtimes/<ARN url-encode>/invocations?qualifier=DEFAULT`) |
| `VITE_DEMO_EMAIL` | không | Email demo cho nút "Dùng tài khoản demo" (chỉ điền email, không có mật khẩu) |
| `VITE_CONVERSATION_REPLAY` | không | `0` tắt việc nạp lại hội thoại từ server (mặc định bật) |

Thiếu biến bắt buộc thì app hiện màn "Chưa cấu hình ứng dụng" liệt kê biến thiếu. `scripts/print_env.py frontend` sinh các biến này từ SSM (`api/url` thành `VITE_API_URL`).

## Cấu trúc

```
src/
  main.tsx, App.tsx, router.tsx, AppContext.tsx   # khởi động, router (hash), cấu hình
  index.css                                       # token Figma: màu Sáng/Tối, thang chữ, bo góc, bóng, khung điện thoại
  contracts/blocks.ts                             # Zod SINH TỰ ĐỘNG từ ../contracts (node scripts/gen_contracts.mjs); không sửa tay
  auth/       # AuthClient (giao diện), CognitoAuthClient (SRP), AuthProvider (làm mới token), RequireAuth (route guard)
  api/        # createApiClient (REST có kiểu, Bearer, traceparent, lỗi tiếng Việt), schemas (Zod của phản hồi REST), errors (25 mã lỗi),
              # ApiProvider (+ "phiên bản dữ liệu"), OverviewProvider (GET /overview dùng chung), resource (useApiResource), useWrite (luồng ghi của màn hình)
  chat/       # ChatSession (lõi: luồng AG-UI, lỗi, lịch sử), ChatProvider, ChatSheet, MessageList, repository (phát lại), launcher (mở chat từ màn khác)
  blocks/     # registry type -> { schema Zod, Component } cho 8 khối; views (phase 1), walletViews (4 khối phase 2), useConfirmFlow
  features/   # forecast (model.ts thuần hàm, ForecastChart = Recharts tách chunk, ForecastBlock dùng chung màn + chat), transfer, jars, obligations, overview
  components/ # BalanceCard, JarCard, JarRow, JarGlass (SVG, vạch dự báo), JarIcon, JarStatusChip, StatusChip, ProactiveCard, MiniTimeline, TxRow, Numpad,
              # MoneyInput, ScreenHeader, StateViews (lỗi/rỗng/skeleton), SimNote, Notice, ui/ (shadcn: button, input, drawer, ...)
  layout/     # PhoneFrame, AppShell (provider + tab bar ẩn ở màn toàn khung + launcher chat), TabBar
  pages/      # Login, Overview, Jars, JarDetail, JarsEdit, Foresight, Activity, Onboarding, Obligations, ObligationEdit, Income, Salary, Move, Profile, transfer/*
  lib/        # format (Intl; thêm vndInWords, formatVndAxis...), dates (số học ngày), jar (mực nước, chip trạng thái), nudgePrefs, config, ids, cn, user
  test/       # helper, fixture dùng chung với phía Python (contracts/fixtures), dựng SSE giả
dev-mocks/    # CHỈ cho `npm run dev:mock`: client/mock-auth.ts, server/plugin.ts (SSE giả + định tuyến), server/wallet.ts (REST ví và dự báo giả, có trạng thái). Không vào bundle
scripts/check-bundle.mjs
```

## Cách các phần hoạt động

**Chat gọi thẳng Runtime** (không proxy; CORS do dịch vụ AgentCore xử lý, xem [spike](../docs/research/spike-agentcore-runtime-cors.md)). Mỗi lượt: `@ag-ui/client` `HttpAgent` POST tới URL Runtime với `Authorization: Bearer <access token>`, `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` (UUID của cuộc hội thoại, giữ ở localStorage theo người dùng), `traceparent` mới; gửi lại **toàn bộ** lịch sử (tin người dùng, câu trả lời chữ của trợ lý, các dòng hệ thống); không `credentials: 'include'`. Khối UI không vào lịch sử gửi agent.

- Event dùng: `TEXT_MESSAGE_*` (chữ chạy dần), `TOOL_CALL_START/RESULT` (thẻ "Yofina đang làm"), `ACTIVITY_SNAPSHOT` với `activityType: "yofina.block"` (khối UI, **thay tại chỗ** theo `messageId`), `RUN_ERROR`, `RUN_FINISHED`. Event khác bỏ qua.
- Lỗi: luồng rỗng, đứt giữa chừng (không có `RUN_FINISHED`) hoặc kết thúc mà không có nội dung đều là lỗi: hiện `Notice` + nút Thử lại (lượt lỗi không đi vào lịch sử). 401: làm mới token (ép refresh) rồi thử lại **một** lần. 403: báo phiên chat không thuộc tài khoản. 409 `SESSION_BUSY`: báo bận, cho thử lại. Nút Dừng gọi `abortRun`.
- Mở sheet thì làm nóng phiên: POST `/invocations` với `forwardedProps.warmup = true` (agent chỉ nạp cấu hình, không gọi model).
- Token được bảo đảm còn sống tối thiểu 2 phút trước mỗi lượt chat và mỗi lời gọi REST; ngoài ra `AuthProvider` hẹn làm mới 5 phút trước khi hết hạn.

**Khối `confirm`** ([ADR-0002](../docs/decisions/0002-xac-nhan-truoc-khi-ghi.md)): nút "Xác nhận chuyển …" → `POST /confirmations` (tool, params, params_hash lấy nguyên từ khối) → `POST /actions` kèm `confirm_token` → khối được thay bằng `receipt` ở đúng vị trí → làm mới số dư Tổng quan → thêm một dòng `system` vào lịch sử gửi agent (người dùng không thấy). Cả hai lời gọi kèm `conversation_id` và `confirm_block_id` (= `id` của khối confirm): **server** chỉ cho một đề nghị được thực hiện một lần và lưu biên nhận gắn với nó. "Không" chỉ đánh dấu hủy ở phiên đang mở (server chưa lưu việc hủy), không gọi API. Đề nghị có hạn (`expires_at`), quá hạn thì vô hiệu nút. Lỗi token hết hạn cho bấm lại (lấy token mới); `TOKEN_REUSED` và `ALREADY_APPLIED` khóa nút, làm mới số dư và đồng bộ lại trạng thái đề nghị từ server (`ChatSession.applyResolutions`: khối confirm đổi thành biên nhận, không dựng lại cả hội thoại); lỗi số dư/hạn mức khóa nút.

**Phát lại sau khi tải lại trang**: localStorage chỉ giữ conversation id (`yofina.conversation.<email>`). Nội dung nạp từ `GET /conversations/{conversation_id}` ([openapi.yaml](../contracts/rest/openapi.yaml)). Nếu tải lỗi, chat bắt đầu trống. Khối `confirm` được lưu như lúc phát; trạng thái của nó do server giữ ở `resolutions` của lượt (`pending` | `done` kèm `receipt` | `expired`) và `ChatSession.hydrate` áp theo đó, không suy từ số dư hay đồng hồ máy: **`done`** → biên nhận thay chỗ khối confirm (không còn nút) và một dòng `system` báo agent việc đã làm; **`expired`** → "hết hạn", nút bị vô hiệu; **`pending`** → còn hạn thì bấm được. Lời của agent trong một lượt có đề nghị đã thực hiện ("chưa có khoản nào được chuyển…") được làm mờ và ghi "Trước khi bạn xác nhận" ở tầng hiển thị (`MessageList.supersededAssistantIds`, theo trạng thái khối chứ không theo nội dung chữ).

**Token thiết kế**: lấy từ Figma Foundations (`28:2`) thành biến CSS ở `src/index.css`; bộ Tối đổi theo `prefers-color-scheme` hoặc `<html data-theme="dark|light">`. Dùng qua class Tailwind: `bg-surface`, `text-ink`, `text-ink-2`, `bg-tint`, `text-brand-text`, `bg-ok-bg text-ok-fg` (đủ), `warn` (sát), `bad` (hụt), cỡ chữ `text-display/amount/title/section/subtitle/body/small/note`, `rounded-card` (24), `rounded-sheet` (28), `shadow-card`. `cn` (tương thích tailwind-merge) được cấu hình biết các tên tự đặt này ở `src/lib/cn.ts`; thêm cỡ chữ mới thì thêm vào đó, nếu không `text-xxx` bị coi là màu và xóa mất màu chữ đứng trước.

**Dữ liệu và làm mới sau khi ghi** (phase 2): mọi GET đi qua `useApiResource` (loading → ready | error, `reload` cho nút Thử lại, bỏ kết quả về muộn). `ApiProvider` giữ một "phiên bản dữ liệu" tăng sau mỗi lần ghi thành công (`useRefreshAfterWrite()`); mọi tài nguyên đang hiện (tổng quan, Chi tiết hũ, dự báo, giao dịch, nghĩa vụ...) nghe số này và tải lại, giữ số cũ trong lúc tải. `GET /overview` được nạp một lần ở `OverviewProvider` và dùng chung cho Tổng quan, tab Hũ, Nhìn trước, Hoạt động, chuyển tiền.

**Luồng ghi của màn hình** (`api/useWrite.ts`, ADR-0002): người dùng bấm nút nêu rõ việc sẽ làm → `POST /confirmations` (`tool` + `params` tự dựng, không `conversation_id`) → `POST /actions` kèm token và đúng `params` đã được server chuẩn hóa → biên nhận do server trả (`receipt_action`, hoặc `receipt` với chuyển hũ) → làm mới dữ liệu. Frontend không tự tính số nghiệp vụ: số dư sau, phí, tổng phải trả gồm phí, ngày cạn, trạng thái đủ/sát/hụt đều là số server trả (xem "Ràng buộc"). Mã chống ghi trùng `client_ref` (`ui-<uuid>`) sinh một lần cho mỗi lần chuyển hoặc ghi và dùng lại khi bấm lại sau lỗi tạm thời.

**Xem trước do server tính** (`api/useConfirmPreview.ts`, `components/PreviewPanel.tsx`): `POST /confirmations` trả thêm `preview` (`summary`, `changes` trước → sau, `warnings`) và không ghi gì. Các màn ghi (Xem lại chuyển tiền, Chuyển giữa hũ, Tiền vào, Lương về) gọi nó ngay khi đủ dữ liệu để hiện số dư hai hũ, phí và phải trả của Trả sau (mô phỏng), hạn mức còn lại, phần chia lương; frontend không tự tính các số này. Lỗi nghiệp vụ (không đủ số dư, vượt hạn mức, trùng giao dịch) hiện sớm ở đây và khóa nút xác nhận; lỗi tạm thời thì vẫn cho bấm. Token của lời gọi xem trước bị bỏ: lúc bấm xác nhận `useWriteFlow` xin token mới (token chỉ sống 2 phút).

**Theo dõi dự báo sau khi ghi** (`api/ApiProvider.tsx`, tham số `poll` của `useApiResource`): ghi xong thì số dư làm mới ngay (phiên bản dữ liệu), còn dự báo do pipeline sự kiện tính sau khoảng 3 đến 4 giây. `bump(serverAt)` nhận `as_of` của biên nhận; Tổng quan và dự báo trong Chi tiết hũ đọc lại mỗi 3 giây cho tới khi `computed_at` >= thời điểm server của lần ghi (tối đa 60 giây; Chi tiết hũ ghi "Đang tính lại dự báo…"). `forecast.stale` (Tổng quan) hoặc `stale` (dự báo) thì thử lại mỗi 4 giây trong 20 giây; đã khai hồ sơ mà chưa có dự báo cũng vậy. Ghi không kèm mốc server (đặt lại demo, làm mới sau lỗi) thì không chờ.

**Thời gian chờ** (`api/client.ts`): mỗi lời gọi hết giờ sau 40 giây (`TIMEOUT`, thông báo nhắc kiểm tra Hoạt động trước khi ghi lại), `POST /demo/reset` 60 giây (mất 2,6 đến 8 giây; nút ghi "Đang đặt lại, mất vài giây…"). `GET /forecasts/{jar}` có thể mất 1 đến 5 giây: có skeleton; 503 `FORECAST_UNAVAILABLE` hiện thông báo dễ hiểu kèm Thử lại, không vỡ màn. Hũ hệ thống không gọi `/forecasts` (server trả 503).

**Ngày giờ trên biên nhận và "Cập nhật"** (`formatSimMoment`): ngày lấy từ ngày mô phỏng (`app_date`, `origin_date`), chỉ giờ lấy từ thời điểm thật, để khỏi thấy "22/11" cạnh "ngày mô phỏng 21/11". Vạch "dự báo" trên hũ lấy từ `forecast_floor_vnd` của server (có thể âm: vẽ như cạn).

**Biểu đồ dự báo** (`features/forecast`): `model.ts` đổi khối `forecast_timeline` thành dữ liệu vẽ (điểm gốc là số dư lúc chạy, rồi mỗi ngày P10/P50/P90; mốc nghĩa vụ và lương; điểm cạn nội suy đúng trên đường P50; vùng hụt tới ngày lương; mốc trục 1-2-5); `ForecastChart.tsx` vẽ bằng Recharts 3.11 (dải P10–P90, đường P50 màu `accent/blue`, mốc, điểm cạn) và là **chunk riêng** (`React.lazy`), không nằm trong phần tải đầu; `ForecastBlock.tsx` là component dùng chung cho Chi tiết hũ và khối `forecast_timeline` trong chat (qua registry), nên hai nơi luôn cùng số. Chạm vào biểu đồ chọn một ngày (dòng đọc số bên trên, vì tooltip nổi khó chạm trên điện thoại); có thêm thanh chọn ngày dùng bằng bàn phím hoặc chạm, và danh sách mốc dạng văn bản. Hiện ngày cạn, xác suất hụt HOẶC nhóm tin cậy (theo trường nào có), độ phủ dữ liệu, thời điểm tính, nhãn "Ước lượng ban đầu" và "Số liệu cũ".

**Khối `confirm` và `confirm_action` hủy được**: nút "Không" gọi `POST /confirmations/cancel` (server lưu `cancelled`, tải lại trang vẫn thấy đã hủy); gặp `ALREADY_APPLIED` thì không đánh dấu hủy mà đồng bộ lại từ server. Đề nghị quá hạn do server ép (403 `TOKEN_EXPIRED` khi xin token) hiện như "hết hạn, hỏi lại Yofina", không cho bấm lại.

**Trợ giúp chia hũ** (#39, `features/jars/SplitHelp.tsx`): nút "?" cạnh tiêu đề ở màn "Thêm hoặc sửa hũ" và bước 2 của onboarding mở tấm "Chia hũ sao cho hợp lý" (Drawer của Base UI; đóng bằng nút, Esc, chạm ra ngoài; tiêu điểm về nút). Lời nằm ở `features/jars/splitHelpContent.ts`, sửa lời ở đó. Đây là hướng dẫn chung; số duy nhất là tỷ lệ mặc định đọc từ `GET /jar-templates` (`is_default`), không có dữ liệu thì lời định tính; mức sàn Dự phòng không có trong phản hồi nào của hai màn nên chỉ nói "mức sàn". Đối chiếu từng ý với quy tắc và căn cứ (quỹ khẩn cấp, lịch hóa đơn theo ngày lương, mặc định chỉ là điểm bắt đầu) ghi ở chú thích đầu tệp lời; giao diện không nêu tên tổ chức nguồn.

## Thêm một loại khối UI

1. Tạo `contracts/blocks/<type>.schema.json`, thêm vào `block.schema.json` và `FILES` trong `scripts/gen_contracts.mjs`, viết `build_*` phía Python, thêm fixture hợp lệ/không hợp lệ ([contracts/README.md](../contracts/README.md)).
2. `node scripts/gen_contracts.mjs` để sinh lại `src/contracts/blocks.ts` (không sửa tay).
3. Viết component trong `src/blocks/views.tsx` (props `BlockViewProps<XBlock>`) và thêm **một dòng** `<type>: defineBlock(blockSchemas.<type>, XView)` vào `registry` ở `src/blocks/registry.tsx`.
4. `npm test`: test registry kiểm mọi loại trong hợp đồng đã có component và mọi fixture hợp lệ vẽ được, mọi fixture sai hiện `fallback_text`.

Frontend parse **từng khối riêng**: type lạ hoặc sai schema hiện `fallback_text` (dòng nhỏ "Cập nhật ứng dụng…" khi phiên bản khối mới hơn); mỗi khối có error boundary riêng.

## Ràng buộc đã giữ

- Không có dữ liệu persona, fixture hay mock trong `src/`; số trên màn hình đến từ các GET REST (chủ yếu `GET /overview`), khối do agent phát, hoặc biên nhận của server. `npm run check:bundle` kiểm bằng grep trên `dist/`. Fixture chỉ được nạp trong test (`src/**/*.test.*`, `src/test/`); mock server chỉ ở `dev-mocks/` (vite.config.ts chỉ import khi `--mode mock`).
- Không có mật khẩu nào trong mã; "Dùng tài khoản demo" chỉ điền email từ `VITE_DEMO_EMAIL`.
- Không dùng tên "MoMo", "Ví Trả Sau", "FinHealth" trên giao diện; sản phẩm trả sau sau này sẽ là "Trả sau (mô phỏng)". Mọi màn ghi "Ví mô phỏng · ngày mô phỏng dd/mm/yyyy".
- Ba trạng thái đủ/sát/hụt luôn có biểu tượng + chữ (`StatusChip`, `JarStatusChip`); nhãn lấy từ `status` của server. Hũ chưa có dự báo ghi "Chưa có dự báo" (không đoán); hũ hết tiền mà chưa có dự báo ghi "Đã hết tiền".
- Không tự tính số nghiệp vụ mà server đã trả (phí, tổng gồm phí, số dư sau, ngày cạn, xác suất, trạng thái). Việc duy nhất giao diện tự tính là đổi ngày thành tọa độ, mức nước hũ để vẽ, và sắp xếp hũ theo mức cần chú ý.
- "Tiền vào khác" và "Chưa phân loại" (hũ hệ thống) nằm trong tổng số dư; Chưa phân loại có thể âm, ghi "Đã chi, chưa xếp hũ" theo giá trị tuyệt đối.
- localStorage chỉ giữ conversation id và tùy chọn hiển thị "Để sau" / "Ít nhắc loại này" (quyết định hợp đồng số 15); không giữ dữ liệu tài chính.
- Vùng chạm >= 44 px, `Intl` cho tiền và ngày, hỗ trợ Sáng/Tối, mọi màn có skeleton, trạng thái lỗi (nút Thử lại) và rỗng, dòng "Ví mô phỏng · ngày mô phỏng dd/mm/yyyy".

## Phiên bản đã ghim (xem `package.json`, đã chạy được)

`vite` 8.3.8, `react`/`react-dom` 19.3.1, `typescript` 7.0.2, `tailwindcss` + `@tailwindcss/vite` 4.3.5, `shadcn` 4.23.0 (preset `base-nova`) + `@base-ui/react` 1.9.0, `cn` 0.5.2, `react-router` 8.5.2 (cần Node >= 22.22), `@ag-ui/client` 1.0.5, `zod` 4.6.7, `amazon-cognito-identity-js` 6.3.22, `@fontsource-variable/plus-jakarta-sans` 5.3.0 (tự host, có subset tiếng Việt), `lucide-react` 1.77.0, `vitest` 5.1.1, `@testing-library/react` 16.3.3, `jsdom` 31.0.1, `oxlint` 1.94.0. Phase 2 thêm `recharts` 3.11.0 (đúng bản spike đã chứng minh; tải lười ở chunk riêng). Motion và NumberFlow của spike **chưa dùng** (mực nước hũ chuyển động bằng CSS transition, số tiền không đếm chạy), nên bundle không gánh thêm khoảng 50 KB.

**Kích thước bản build** (`npm run build`, gzip, JS + CSS): phần tải đầu khoảng 238 KB (`index`, React, Zod, Base UI, CSS); chunk biểu đồ `ForecastChart` (Recharts) khoảng 115 KB chỉ tải khi mở Chi tiết hũ hoặc khối dự báo trong chat; sheet chat khoảng 16 KB và `@ag-ui/client` khoảng 53 KB tải khi mở chat; các màn ít dùng (Chuyển tiền, Hoạt động, Onboarding, Nghĩa vụ, Tiền vào, Lương về, Giữa hũ, Thêm hoặc sửa hũ, Chi tiết hũ) mỗi màn 1 đến 4 KB, tải theo route; tổng mọi chunk khoảng 455 KB.

Ghi chú vận hành: `amazon-cognito-identity-js` cần `define: { global: 'globalThis' }` (đã đặt trong `vite.config.ts`); Drawer có vá của spike (snap points, `padding-bottom` theo `--drawer-snap-point-offset`, vùng chạm >= 44 px) và được portal vào khung điện thoại; `build.target` là `es2023` (Tailwind 4 cần Safari >= 16.4).

## Tài liệu liên quan

- Proposal: §12 (streaming, giao diện sinh từ JSON), §9 (hợp đồng khối); [agentic UI](../docs/research/agentic-ui-generative-ui.md), [thiết kế fintech](../docs/research/frontend-fintech-ui.md), [spike stack](../docs/research/spike-frontend-stack.md), [spike Runtime + CORS](../docs/research/spike-agentcore-runtime-cors.md), [spike Strands + AG-UI](../docs/research/spike-strands-agui-local.md), [overview.md](../docs/architecture/overview.md).
- Kịch bản demo: [demo-script.md](../docs/plan/demo-script.md).
