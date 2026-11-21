# frontend/

Web app Yofina ưu tiên điện thoại (khung 390 px; trên màn rộng căn giữa thành khung điện thoại). Stack theo [ADR-0001](../docs/decisions/0001-frontend-stack.md): React + Vite + TypeScript, Tailwind 4, shadcn/ui (Base UI), `@ag-ui/client`, Zod. Thiết kế theo Figma `l9vWyORNRjDqiEOXqpbzYm` ([figma-ui-design.md](../docs/research/figma-ui-design.md)).

Trạng thái: **phase 1** ([luồng E](../docs/plan/phases/phase-1-nen-va-lat-doc.md#luồng-e--frontend)). Có: đăng nhập Cognito SRP, Tổng quan (số dư các hũ), Hồ sơ (đặt lại dữ liệu, đăng xuất), sheet chat với khối `jar_summary`, `confirm`, `receipt`, `notice`. Tab Hũ và Nhìn trước là trạng thái rỗng (chưa có số liệu giả).

## Chạy

```bash
cd frontend
npm install
cp .env.example .env.local        # điền giá trị (hoặc: uv run scripts/print_env.py frontend --write ở gốc repo)
npm run dev                       # backend thật
npm run dev:mock                  # máy chủ giả trong dev-mocks/, không cần backend và không cần đăng nhập thật

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
  api/        # createApiClient (REST có kiểu, Bearer, traceparent, lỗi tiếng Việt), ApiProvider + JarsProvider (số dư dùng chung)
  chat/       # ChatSession (lõi: luồng AG-UI, lỗi, lịch sử), ChatProvider, ChatSheet, MessageList, repository (phát lại)
  blocks/     # registry type -> { schema Zod, Component }, views (jar_summary, confirm, receipt, notice), useConfirmFlow
  components/ # BalanceCard, JarCard, JarGlass (SVG), JarIcon, StatusChip, Notice, ui/ (shadcn: button, input, drawer, ...)
  layout/     # PhoneFrame, AppShell, TabBar
  pages/      # LoginPage, OverviewPage, ProfilePage, EmptyTabPage
  lib/        # format (Intl), config (import.meta.env), ids (uuid, traceparent), cn, user
  test/       # helper, fixture dùng chung với phía Python (contracts/fixtures), dựng SSE giả
dev-mocks/    # CHỈ cho `npm run dev:mock`: client/mock-auth.ts, server/plugin.ts (REST + SSE giả). Không vào bundle
scripts/check-bundle.mjs
```

## Cách các phần hoạt động

**Chat gọi thẳng Runtime** (không proxy; CORS do dịch vụ AgentCore xử lý, xem [spike](../docs/research/spike-agentcore-runtime-cors.md)). Mỗi lượt: `@ag-ui/client` `HttpAgent` POST tới URL Runtime với `Authorization: Bearer <access token>`, `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` (UUID của cuộc hội thoại, giữ ở localStorage theo người dùng), `traceparent` mới; gửi lại **toàn bộ** lịch sử (tin người dùng, câu trả lời chữ của trợ lý, các dòng hệ thống); không `credentials: 'include'`. Khối UI không vào lịch sử gửi agent.

- Event dùng: `TEXT_MESSAGE_*` (chữ chạy dần), `TOOL_CALL_START/RESULT` (thẻ "Yofina đang làm"), `ACTIVITY_SNAPSHOT` với `activityType: "yofina.block"` (khối UI, **thay tại chỗ** theo `messageId`), `RUN_ERROR`, `RUN_FINISHED`. Event khác bỏ qua.
- Lỗi: luồng rỗng, đứt giữa chừng (không có `RUN_FINISHED`) hoặc kết thúc mà không có nội dung đều là lỗi: hiện `Notice` + nút Thử lại (lượt lỗi không đi vào lịch sử). 401: làm mới token (ép refresh) rồi thử lại **một** lần. 403: báo phiên chat không thuộc tài khoản. 409 `SESSION_BUSY`: báo bận, cho thử lại. Nút Dừng gọi `abortRun`.
- Mở sheet thì làm nóng phiên: POST `/invocations` với `forwardedProps.warmup = true` (agent chỉ nạp cấu hình, không gọi model).
- Token được bảo đảm còn sống tối thiểu 2 phút trước mỗi lượt chat và mỗi lời gọi REST; ngoài ra `AuthProvider` hẹn làm mới 5 phút trước khi hết hạn.

**Khối `confirm`** ([ADR-0002](../docs/decisions/0002-xac-nhan-truoc-khi-ghi.md)): nút "Xác nhận chuyển …" → `POST /confirmations` (tool, params, params_hash lấy nguyên từ khối) → `POST /actions` kèm `confirm_token` → khối được thay bằng `receipt` ở đúng vị trí → làm mới số dư Tổng quan → thêm một dòng `system` vào lịch sử gửi agent (người dùng không thấy). Cả hai lời gọi kèm `conversation_id` và `confirm_block_id` (= `id` của khối confirm): **server** chỉ cho một đề nghị được thực hiện một lần và lưu biên nhận gắn với nó. "Không" chỉ đánh dấu hủy ở phiên đang mở (server chưa lưu việc hủy), không gọi API. Đề nghị có hạn (`expires_at`), quá hạn thì vô hiệu nút. Lỗi token hết hạn cho bấm lại (lấy token mới); `TOKEN_REUSED` và `ALREADY_APPLIED` khóa nút, làm mới số dư và đồng bộ lại trạng thái đề nghị từ server (`ChatSession.applyResolutions`: khối confirm đổi thành biên nhận, không dựng lại cả hội thoại); lỗi số dư/hạn mức khóa nút.

**Phát lại sau khi tải lại trang**: localStorage chỉ giữ conversation id (`yofina.conversation.<email>`). Nội dung nạp từ `GET /conversations/{conversation_id}` ([openapi.yaml](../contracts/rest/openapi.yaml)); route chưa deploy (404) hoặc lỗi thì chat bắt đầu trống. Khối `confirm` được lưu như lúc phát; trạng thái của nó do server giữ ở `resolutions` của lượt (`pending` | `done` kèm `receipt` | `expired`) và `ChatSession.hydrate` áp theo đó, không suy từ số dư hay đồng hồ máy: **`done`** → biên nhận thay chỗ khối confirm (không còn nút) và một dòng `system` báo agent việc đã làm; **`expired`** → "hết hạn", nút bị vô hiệu; **`pending`** → còn hạn thì bấm được. Lời của agent trong một lượt có đề nghị đã thực hiện ("chưa có khoản nào được chuyển…") được làm mờ và ghi "Trước khi bạn xác nhận" ở tầng hiển thị (`MessageList.supersededAssistantIds`, theo trạng thái khối chứ không theo nội dung chữ).

**Token thiết kế**: lấy từ Figma Foundations (`28:2`) thành biến CSS ở `src/index.css`; bộ Tối đổi theo `prefers-color-scheme` hoặc `<html data-theme="dark|light">`. Dùng qua class Tailwind: `bg-surface`, `text-ink`, `text-ink-2`, `bg-tint`, `text-brand-text`, `bg-ok-bg text-ok-fg` (đủ), `warn` (sát), `bad` (hụt), cỡ chữ `text-display/amount/title/section/subtitle/body/small/note`, `rounded-card` (24), `rounded-sheet` (28), `shadow-card`. `cn` (tương thích tailwind-merge) được cấu hình biết các tên tự đặt này ở `src/lib/cn.ts`; thêm cỡ chữ mới thì thêm vào đó, nếu không `text-xxx` bị coi là màu và xóa mất màu chữ đứng trước.

## Thêm một loại khối UI

1. Tạo `contracts/blocks/<type>.schema.json`, thêm vào `block.schema.json` và `FILES` trong `scripts/gen_contracts.mjs`, viết `build_*` phía Python, thêm fixture hợp lệ/không hợp lệ ([contracts/README.md](../contracts/README.md)).
2. `node scripts/gen_contracts.mjs` để sinh lại `src/contracts/blocks.ts` (không sửa tay).
3. Viết component trong `src/blocks/views.tsx` (props `BlockViewProps<XBlock>`) và thêm **một dòng** `<type>: defineBlock(blockSchemas.<type>, XView)` vào `registry` ở `src/blocks/registry.tsx`.
4. `npm test`: test registry kiểm mọi loại trong hợp đồng đã có component và mọi fixture hợp lệ vẽ được, mọi fixture sai hiện `fallback_text`.

Frontend parse **từng khối riêng**: type lạ hoặc sai schema hiện `fallback_text` (dòng nhỏ "Cập nhật ứng dụng…" khi phiên bản khối mới hơn); mỗi khối có error boundary riêng.

## Ràng buộc đã giữ

- Không có dữ liệu persona, fixture hay mock trong `src/`; số trên màn hình đến từ `GET /jars`, khối do agent phát, hoặc biên nhận của server. `npm run check:bundle` kiểm bằng grep trên `dist/`. Fixture chỉ được nạp trong test (`src/**/*.test.*`, `src/test/`); mock server chỉ ở `dev-mocks/` (vite.config.ts chỉ import khi `--mode mock`).
- Không có mật khẩu nào trong mã; "Dùng tài khoản demo" chỉ điền email từ `VITE_DEMO_EMAIL`.
- Không dùng tên "MoMo", "Ví Trả Sau", "FinHealth" trên giao diện; sản phẩm trả sau sau này sẽ là "Trả sau (mô phỏng)". Mọi màn ghi "Ví mô phỏng · ngày mô phỏng dd/mm/yyyy".
- Ba trạng thái đủ/sát/hụt luôn có biểu tượng + chữ (`StatusChip`); phase 1 chưa có dự báo nên chỉ dùng "hụt" cho hũ hết tiền.

## Phiên bản đã ghim (xem `package.json`, đã chạy được)

`vite` 8.3.8, `react`/`react-dom` 19.3.1, `typescript` 7.0.2, `tailwindcss` + `@tailwindcss/vite` 4.3.5, `shadcn` 4.23.0 (preset `base-nova`) + `@base-ui/react` 1.9.0, `cn` 0.5.2, `react-router` 8.5.2 (cần Node >= 22.22), `@ag-ui/client` 1.0.5, `zod` 4.6.7, `amazon-cognito-identity-js` 6.3.22, `@fontsource-variable/plus-jakarta-sans` 5.3.0 (tự host, có subset tiếng Việt), `lucide-react` 1.77.0, `vitest` 5.1.1, `@testing-library/react` 16.3.3, `jsdom` 31.0.1, `oxlint` 1.94.0. Đã bỏ khỏi spike: Recharts, Motion, NumberFlow, d3 (chưa cần ở phase 1; Recharts quay lại khi làm biểu đồ dự báo).

Ghi chú vận hành: `amazon-cognito-identity-js` cần `define: { global: 'globalThis' }` (đã đặt trong `vite.config.ts`); Drawer có vá của spike (snap points, `padding-bottom` theo `--drawer-snap-point-offset`, vùng chạm >= 44 px) và được portal vào khung điện thoại; `build.target` là `es2023` (Tailwind 4 cần Safari >= 16.4).

## Tài liệu liên quan

- Proposal: §12 (streaming, giao diện sinh từ JSON), §9 (hợp đồng khối); [agentic UI](../docs/research/agentic-ui-generative-ui.md), [thiết kế fintech](../docs/research/frontend-fintech-ui.md), [spike stack](../docs/research/spike-frontend-stack.md), [spike Runtime + CORS](../docs/research/spike-agentcore-runtime-cors.md), [spike Strands + AG-UI](../docs/research/spike-strands-agui-local.md), [overview.md](../docs/architecture/overview.md).
- Kịch bản demo: [demo-script.md](../docs/plan/demo-script.md).
