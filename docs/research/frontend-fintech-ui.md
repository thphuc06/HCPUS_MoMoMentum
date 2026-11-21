# Thiết kế app fintech mobile và chọn stack frontend "đẹp nhất" cho Yofina Foresight

> Ghi chú nghiên cứu ngày 2026-11-21. Mục đích: để các phiên code frontend sau làm theo mà không phải tra lại. Chỉ đọc và tra cứu, không cài gì, không tạo project.
>
> **Ký hiệu độ tin cậy** đặt cuối mỗi khẳng định quan trọng:
> - **[TL]** đã đọc trong tài liệu chính thức (docs của thư viện/AWS/W3C).
> - **[BV]** blog, bài báo, diễn đàn, trang tổng hợp, nguồn thứ cấp.
> - **[KT]** tôi tự kiểm tra trực tiếp hôm nay (npm registry, bundlephobia, Node 24/ICU 78, đọc file font bằng fontTools, tính độ tương phản).
> - **[ĐG]** đánh giá hoặc đề xuất của tôi, không phải sự thật khách quan. "Đẹp" là chủ quan: tôi dựa vào (a) thư viện nào được dùng trong sản phẩm thật và showcase chính thức, (b) mức độ tùy biến ra thương hiệu riêng, (c) cái gì không bị "giao diện mẫu" khi để mặc định. Tôi không mở được app thật của Revolut/Monzo/MoMo… để xem trực tiếp, nên phần mẫu thiết kế dựa trên bài viết và tài liệu của chính hãng.

---

## 1. Câu hỏi cần trả lời

1. Framework nào (Next.js App Router, React + Vite SPA, khác) cho web app mobile-first có SSE streaming, deploy lên Amplify Hosting, cài lên màn hình chính, cảm giác như app native?
2. Thư viện component và hệ thiết kế nào cho giao diện đẹp nhất, tùy biến thành thương hiệu riêng, dark mode, AI coding agent sinh code đúng, giấy phép ổn?
3. Thư viện biểu đồ nào, và biểu đồ nào phải tự vẽ SVG (fan chart P10–P90, what-if, vòng tiến độ hũ, gauge điểm chống chịu, thanh phân bổ lương, lịch nghĩa vụ)?
4. Animation, number ticker, skeleton, haptic, hiệu năng điện thoại tầm trung.
5. Mẫu thiết kế app ngân hàng/ví nên học và nên tránh; hướng nhận diện riêng cho Yofina.
6. Chi tiết Việt Nam: định dạng VND, ngày, font có dấu, nhập tiền, VietQR.
7. Hiển thị bất định và trạng thái đủ/sát/hụt cho người không chuyên, đúng accessibility, không gây lo lắng.
8. Chỗ đặt chatbot và cách một bộ component dùng ở hai nơi (màn hình chính và khối UI do AI trả về).
9. State, form, xác thực Cognito, kiểm thử.

---

## 2. Kết luận ngắn: một stack đề xuất

**Stack duy nhất đề xuất: "Vite SPA + shadcn/ui (Base UI) + Recharts + Motion + NumberFlow", font Plus Jakarta Sans.**

- **Framework: React 19.3 + Vite 8.3 + React Router 8.5 (chế độ declarative/data, SPA), build ra file tĩnh, host tĩnh trên Amplify Hosting** với một luật rewrite 200 về `index.html`. Đây là lệch so với proposal §14 (Next.js); lý do ở §3.1: tài liệu Amplify ghi hỗ trợ Next.js "đến 15" và liệt kê "Next.js streaming" là tính năng **không** hỗ trợ; app này đăng nhập rồi mới dùng, không cần SEO, và SSE đi thẳng từ trình duyệt tới AgentCore, nên SSR không đem lại gì. [TL][ĐG]
- **Phương án dự phòng của framework:** Next.js 16.4 với `output: 'export'` (cũng là host tĩnh, mất hết tính năng server). Toàn bộ component, Tailwind, shadcn dùng lại nguyên vẹn, chỉ đổi lớp router. [TL]
- **Component: shadcn/ui CLI 4.23 (mặc định Base UI 1.9 từ 07/2026) + Tailwind CSS 4.3.5 + lucide-react.** shadcn là "mã nguồn của bạn", không phải look cố định, nên tùy biến ra thương hiệu riêng tốt nhất; AI agent sinh code đúng nhất nhờ MCP server và skill chính thức; có sẵn Drawer có snap points (bottom sheet), Chart, Questionnaire (onboarding), Message Scroller/Bubble/Trace/AI Elements (chatbot). [TL][ĐG]
- **Chống "trông như shadcn mặc định" bằng công thức riêng** (§5.4): bảng màu và font riêng, bo góc lớn, số tiền chữ to, minh họa hũ thủy tinh có mực nước, motion có chủ đích. Beauty đến từ tokens và chi tiết, không đến từ thư viện. [ĐG]
- **Biểu đồ: Recharts 3.11 (qua `ChartContainer` của shadcn) cho fan chart, what-if, cột/donut chi tiêu; tự vẽ SVG cho gauge điểm chống chịu, vòng/mực nước của hũ, sparkline; thanh phân bổ lương và lịch nghĩa vụ làm bằng HTML/CSS.** Recharts có ví dụ Ranged Area, ReferenceLine, ReferenceDot, và từ 3.11 có pattern fill và theme chung. [TL][ĐG]
- **Dự phòng biểu đồ:** nếu Recharts không đạt cho fan chart/what-if thì vẽ riêng bằng visx 4 (`AreaClosed`, `LinePath`, scale) hoặc `d3-shape` thuần, vẫn là SVG. ECharts 6.1 chỉ khi cần canvas (nặng hơn, khó ra giao diện thương hiệu). [ĐG]
- **Animation: Motion 14.14 (`motion/react`, dùng `LazyMotion` + `m` để nhẹ), `@number-flow/react` 0.6.2 cho số tiền, React 19.3 `<ViewTransition>` (đã stable) cho chuyển trang, shadcn Skeleton khi stream.** Haptic chỉ là phần thêm (không dựa vào, vì iOS Safari không có Vibration API). [TL]
- **State/form/dữ liệu: Zustand 5 (UI state + reducer cho sự kiện AG-UI), TanStack Query 5 (REST sổ cái/hũ), React Hook Form 7.92 + Zod 4.6, `aws-amplify/auth` (chỉ module Auth, giao diện đăng nhập tự dựng) để lấy JWT Cognito.** Kiểm thử: Vitest 5 + Testing Library, Playwright (viewport iPhone/Android), MSW 3 giả lập luồng SSE. [KT][ĐG]
- **AG-UI tương thích:** `@ag-ui/client` 1.0.5 (`HttpAgent`, header Authorization, `abortRun`) không phụ thuộc framework; CopilotKit 1.90 là tùy chọn. Chưa xác nhận được browser support từ tài liệu `HttpAgent`; cần thử sớm. [TL][KT] **[Đã chạy thử 2026-11-21]** `@ag-ui/client` 1.0.5 bundle được bằng Vite 8 và chạy trong Chrome 157: `HttpAgent` + `AgentSubscriber` nhận đủ `TEXT_MESSAGE_*`, `TOOL_CALL_*`, `CUSTOM`, `ACTIVITY_SNAPSHOT` từ một mock server SSE cục bộ; giá phải trả là ~53 KB gzip (cộng ~26 KB Zod dùng chung), vì gói kéo cả `@ag-ui/proto`/protobuf. Chi tiết: `spike-frontend-stack.md` §5.
- **Một bộ component, hai nơi dùng:** mỗi khối AI (`forecast_timeline`, `obligation_impact`, `options`, `explain`, `confirm` …) là một component thuần "props → UI" có Zod schema, nằm ở `components/blocks/`; màn hình Dự báo/Hũ/Chuyển tiền và bong bóng chat cùng import. Bố cục co giãn bằng container queries của Tailwind v4 (`@container`). [TL][ĐG]
- **Điều hướng:** thanh tab dưới 5 mục: Tổng quan · Hũ · **Hỏi Yofina (nút giữa nổi)** · Nhìn trước · Hồ sơ; chuyển tiền là luồng toàn màn hình mở từ nút nhanh ở Tổng quan; chat còn mở được dạng bottom sheet từ mọi màn hình ("Hỏi về hũ này"). [ĐG]
- **Nhận diện riêng:** nền kem ấm `#F6F5F1`, chủ đạo chàm `#4338CA`, ba trạng thái teal/hổ phách/hồng san hô kèm biểu tượng và chữ, bo góc 24–28px, hũ thủy tinh có mực nước và vạch "mực dự báo". Không dùng hồng/tím của MoMo, xanh Revolut, san hô Monzo, xanh neon Cash App. [ĐG]
- **Font: Plus Jakarta Sans (biến thiên, `@fontsource-variable`, tự host)**: đủ bộ dấu tiếng Việt, có `tnum` cho số tiền; phương án dự phòng Inter. Tránh Geist/Onest cho số tiền vì thiếu ký tự `₫` (kiểm bằng cmap). [KT]
- **Định dạng VND tự viết một module** (`lib/format.ts`) thay vì tin `notation:'compact'` giữa các trình duyệt: lưu số nguyên đồng, hiển thị `1.200.000đ`, rút gọn "1,2 triệu". Cố định múi giờ `Asia/Ho_Chi_Minh`. [KT][ĐG]
- **Việc cần thử trong tuần 1** (rủi ro cao nhất, §6): CORS và header JWT từ trình duyệt tới AgentCore Runtime; hiệu ứng "dịch chuyển" what-if trong Recharts; Base UI Drawer snap points có cuộn trong; node 22 trên build image Amplify; haptic trên iPhone thật.

---

## 3. Chi tiết theo từng mục

### 3.1. Framework, hosting Amplify, PWA, cảm giác native

**Bảng phiên bản hiện hành (npm registry, tra 2026-11-21)** [KT]

| Gói | Phiên bản | Ngày phát hành | Ghi chú |
|---|---|---|---|
| `next` | 16.4.6 | 2026-11-09 | 16.0 ra 10/2025; 16.3 ra 08/2026 |
| `react`, `react-dom` | 19.3.1 | | 19.3 ra 09/09/2026, `<ViewTransition>` đã stable [TL] |
| `vite` | 8.3.8 | | `@vitejs/plugin-react` yêu cầu Node `^20.19 \|\| >=22.12` |
| `react-router` | 8.5.2 | 2026-11-18 | Yêu cầu Node ≥ 22.22, React ≥ 19.2.7 [TL] |
| `@tanstack/react-start` / `react-router` | 1.169.7 / 1.170.46 | | phương án khác, ít dữ liệu huấn luyện hơn |
| `tailwindcss` | 4.3.5 | 2026-11-06 | |
| `shadcn` (CLI) | 4.23.0 | 2026-10-27 | |
| `@base-ui/react` | 1.9.0 | 2026-10-09 | |
| `radix-ui` | 1.8.1 | | vẫn được hỗ trợ |
| `recharts` | 3.11.0 | 2026-11-17 | |
| `motion` | 14.14.0 | 2026-11-13 | trước là `framer-motion` |
| `@number-flow/react` | 0.6.2 | 2026-07-18 | |
| `@tanstack/react-query` | 5.108.2 | 2026-11-20 | |
| `zustand` | 5.1.0 | | |
| `react-hook-form` / `zod` / `@hookform/resolvers` | 7.92.0 / 4.6.7 / 7.0.8 | | kiểm tra khớp Zod 4 khi cài |
| `aws-amplify` | 6.22.2 | | dùng `aws-amplify/auth` |
| `@ag-ui/client` | 1.0.5 | 2026-11-17 | |
| `vite-plugin-pwa` | 2.0.0 | 2026-10-03 | peer hỗ trợ Vite 8 |
| `vitest` / `@playwright/test` / `msw` | 5.1.1 / 1.65.1 / 3.0.7 | | |
| `web-haptics` | 0.0.6 | | rất mới, thận trọng |

**Amplify Hosting hỗ trợ gì (đọc từ tài liệu AWS)**

- "Amplify supports … apps built with Next.js versions up through Next.js 15"; "Amplify Hosting compute fully manages SSR for apps built with Next.js versions 12 through 15". Không có dòng nào nói Next.js 16 được hỗ trợ SSR. [TL] https://docs.aws.amazon.com/amplify/latest/userguide/ssr-amplify-support.html
- Danh sách **không hỗ trợ** của Amplify cho Next.js: Edge API Routes, On-Demand ISR, **Next.js streaming**, chạy middleware trên static/ảnh, `unstable_after`. [TL] (cùng trang)
- Compute của Amplify: một Node.js HTTP server cổng 3000, tối đa 15 phút/instance, bundle giải nén tối đa 220 MB; runtime Node 20/22/24. [TL] https://docs.aws.amazon.com/amplify/latest/userguide/ssr-deployment-specification.html
- Có một bài của bên thứ ba (u11d) triển khai Next.js 16 lên Amplify bằng `output: "export"` (static) và nêu các lỗi hay gặp: `baseDirectory` phải là `out`, route động cần `generateStaticParams`, route handler/ISR không chạy; cần rewrite `/<*>` → `/index.html` 200 cuối danh sách luật. [BV] https://dev.to/u11d/how-to-deploy-nextjs-16-ssg-to-aws-amplify-complete-guide-5g9j
- Next.js `output: 'export'` không hỗ trợ: Server Actions, Proxy, rewrites/redirects/headers trong `next.config`, ISR, ảnh với loader mặc định, route động thiếu `generateStaticParams`, Intercepting Routes. [TL] https://nextjs.org/docs/app/guides/static-exports
- SPA trên Amplify: luật rewrite 200 mẫu có sẵn trong tài liệu:
  `[{"source":"</^[^.]+$|\\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json|webp)$)([^.]+$)/>","status":"200","target":"/index.html","condition":null}]` [TL] https://docs.aws.amazon.com/amplify/latest/userguide/redirect-rewrite-examples.html
- Một câu hỏi trên re:Post báo `ReadableStream` từ API route Next.js trên Amplify bị buffer (không đọc được trang, bị 403 khi tôi mở; chỉ thấy tóm tắt từ công cụ tìm kiếm). Mức tin cậy thấp, nhưng khớp với dòng "Next.js streaming không hỗ trợ" ở tài liệu chính thức. [BV]
- AgentCore Runtime AG-UI: nhận HTTP/SSE tại `/invocations` cổng 8080, hỗ trợ xác thực SigV4 hoặc OAuth 2.0 (JWT bearer) [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui.html. Lỗi CORS từ frontend trình duyệt được xử lý bằng cách thêm CORS middleware vào server của runtime (`BedrockAgentCoreApp`) [TL] https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-tool-troubleshooting.html. Việc này thuộc phần backend nhưng quyết định kiến trúc frontend (xem "Điều chưa chắc").

**So sánh lựa chọn framework**

| Tiêu chí | **Vite 8 + React Router 8 (SPA)** | Next.js 16.4 `output:'export'` | Next.js 16 SSR trên Amplify | TanStack Start/Router |
|---|---|---|---|---|
| Phù hợp Amplify (tài liệu) | Host tĩnh, có luật SPA chính thức | Host tĩnh, cần luật rewrite, dev.to có hướng dẫn | **Ngoài danh sách hỗ trợ (≤15)**, streaming không hỗ trợ | Host tĩnh được (SPA mode) |
| SSE từ trình duyệt tới AgentCore | Trực tiếp (`fetch` + SSE) | Trực tiếp | Không nên đi qua route handler (streaming bị buffer) | Trực tiếp |
| Khái niệm cho AI agent | Một mô hình: toàn client | Thừa khái niệm server/client component, `"use client"`, hydration mismatch với `Intl`/`localStorage` | Như cột trước, thêm cache | Ít dữ liệu huấn luyện |
| Tốc độ dev, HMR | Rất nhanh | Nhanh (Turbopack) | Nhanh | Nhanh |
| SEO, SSR | Không (không cần: app sau đăng nhập) | Chỉ HTML tĩnh | Có | Tùy |
| Font tối ưu, `next/image` | Tự host font bằng `@fontsource-variable`, ảnh ít | `next/font` dùng được, `next/image` cần loader riêng | Có | Không |
| Rủi ro lớn nhất | React Router 8 mới, Node ≥ 22.22 trên build | Mất tính năng server mà vẫn mang chi phí khái niệm | Hỗ trợ chưa chắc, streaming | Ít người dùng, ít mẫu |

Khuyến nghị [ĐG]: **Vite SPA**. Phần lớn lý do kỹ thuật nằm ở hai chỗ: (1) tài liệu Amplify không ủng hộ Next 16 SSR và streaming; (2) khi đã phải `output: 'export'` thì Next.js chỉ còn thêm phức tạp. Next.js hợp lý nếu đội đã quen và chỉ cần file-based routing; khi đó cấu hình `output: 'export'` và mọi thứ còn lại trong tài liệu này vẫn đúng. Tôi không chạy thử cả hai trên Amplify, nên đây là suy luận từ tài liệu, không phải kiểm chứng.

**Chuyển trang mượt (view transitions)**

- React 19.3 (09/09/2026): `<ViewTransition>` "now stable"; chạy khi cập nhật nằm trong `startTransition`, Suspense hoặc `useDeferredValue`; kiểu `enter/exit/update/share`; `addTransitionType` để phân biệt hướng trượt (next/previous). [TL] https://react.dev/blog/2026/09/09/react-19-3
- React Router 8 khuyến nghị bọc `<Outlet/>` trong một `<ViewTransition>` bền vững ở layout (không `key` theo location), router tự bọc `startTransition`; các prop cũ `viewTransition` bị đánh dấu deprecated; **bấm Back/Forward có thể không animate** vì popstate đồng bộ. [TL] https://reactrouter.com/how-to/view-transitions
- Phải tự thêm `@media (prefers-reduced-motion: reduce)` tắt `::view-transition-*` (React không tự làm). [TL]
- Mẫu hợp lý cho app: chuyển tab = cross-fade ngắn (150ms), vào chi tiết hũ = `share` element (thẻ hũ → đầu trang chi tiết), luồng chuyển tiền = trượt ngang theo hướng. [ĐG]

**Cảm giác native, checklist** [ĐG, kỹ thuật web chuẩn; các điểm iOS đối chiếu với firt.dev]

- `<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">`; tab bar và sheet đệm `env(safe-area-inset-bottom)`; dùng `100dvh`/`svh`, không `100vh`.
- Input `font-size ≥ 16px` để iOS không tự zoom; `touch-action: manipulation`; `-webkit-tap-highlight-color: transparent`; `overscroll-behavior: contain` ở vùng cuộn trong; `user-select: none` ở chrome UI (không ở số liệu cần sao chép).
- Bàn phím số tự dựng cho màn nhập tiền (tránh bàn phím hệ thống đẩy bố cục).
- Bottom sheet: Base UI Drawer. Trang tài liệu: Drawer "supports swipe gestures to dismiss", prop `snapPoints` ("snap a bottom sheet drawer to preset heights"), `swipeDirection`; mở rộng Dialog. [TL] https://base-ui.com/react/components/drawer. Bản Base của shadcn nói rõ "now uses Base UI instead of Vaul" và hỗ trợ `snapPoints` cho drawer dọc. [TL] https://ui.shadcn.com/docs/components/base/drawer. Đây là điểm cộng: gói `vaul` (Drawer của bản Radix) ngừng cập nhật từ 2024-12-14. [KT]
- Vuốt giữa các thẻ hũ: Embla carousel 8.6 (shadcn Carousel). Kéo thả: `@use-gesture/react` nếu cần.
- **PWA cài lên màn hình chính**: manifest `display: standalone`, icon 192/512 và maskable, `theme-color`. iOS: không có `beforeinstallprompt`; từ iOS 26 mọi trang web thêm vào Home Screen đều mở như web app theo mặc định (người dùng có thể tắt) [BV] https://www.idownloadblog.com/?p=1042117; bảng khả năng iOS: standalone từ 11.3, Web Push từ 16.4 chỉ khi đã cài, Camera `getUserMedia` từ 13, WebAuthn từ 14.5, cookie đăng nhập được copy vào app đã cài từ 17.2, **Vibration API không hỗ trợ**. [BV] https://firt.dev/notes/pwa-ios/. Tài liệu Next.js cũng khuyên không dựa vào `beforeinstallprompt` vì không chạy trên Safari iOS; hiện hướng dẫn thủ công. [TL] https://nextjs.org/docs/app/guides/progressive-web-apps
- Service worker: tối thiểu (cache vỏ app) bằng `vite-plugin-pwa` 2.0.0, **không cache API/SSE**; nguy cơ SW cũ gây lỗi khi demo, nên có luồng "có bản mới, tải lại". Offline không phải yêu cầu. Cần kiểm điều kiện cài trên Android Chrome với thiết bị thật. [ĐG]
- Tailwind v4 yêu cầu Chrome 111, Safari 16.4, Firefox 128 — điện thoại cũ hơn iOS 16.4 sẽ vỡ giao diện. [TL] https://tailwindcss.com/docs/compatibility

### 3.2. Thư viện component và hệ thiết kế

**Tailwind CSS hiện hành: 4.3.5** (cấu hình trong CSS bằng `@theme`, plugin `@tailwindcss/vite`, tự dò nội dung, không còn `tailwind.config.ts`). Thay đổi đáng biết khi dùng với shadcn: màu OKLCH, `tw-animate-css` thay `tailwindcss-animate`, ring mặc định 1px thay vì 3px, một số lỗi dropdown "nền trong suốt" khi migrate từ v3. Container queries (`@container`, `@sm:`, `@md:` …) là tính năng lõi, kích thước `@3xs` đến `@7xl`. [TL] https://tailwindcss.com/docs/responsive-design ; shadcn: https://ui.shadcn.com/docs/tailwind-v4 và các thảo luận [BV].

**shadcn/ui hiện hành** (changelog chính thức) [TL] https://ui.shadcn.com/docs/changelog :
- 07/2026: **Base UI là mặc định** (`shadcn init`); Radix vẫn hỗ trợ đầy đủ, dùng `init -b radix` để giữ Radix; có skill để agent tự migrate.
- 04/2026: preset; 06/2026: component chat (Message Scroller, Message, Bubble, Attachment, Marker, gói `@shadcn/react`); 08/2026: Questionnaire (nhiều bước, onboarding, câu hỏi có điều kiện, bỏ qua); 09/2026: gói `cn` tách riêng; 10/2026: Trace, Code Block, **AI Elements** (21 mẫu: Chat, Prompt Input, Reasoning, Tool, Plan, Confirmation, Suggestion…, sao chép vào dự án, không cài gói).
- 67 component, có Drawer, Sheet, Chart, Field, Input OTP, Progress, Skeleton, Spinner, Toast, Carousel, Calendar… [TL] https://ui.shadcn.com/docs/components
- Hỗ trợ agent: `pnpm dlx shadcn@latest mcp init --client claude` cài MCP server để agent duyệt, tìm, cài component bằng ngôn ngữ tự nhiên. [TL] https://ui.shadcn.com/docs/mcp
- Cài trên Vite: `shadcn init -t vite`, hoặc tạo preset ở shadcn/create rồi `init --preset … --template vite`. [TL] https://ui.shadcn.com/docs/installation/vite
- **[Đã chạy thử 2026-11-21]** Lệnh không tương tác thực tế: `npx shadcn@4.23.0 init -t vite -b base -p nova --yes --force` (thiếu `-p` thì vẫn hiện menu chọn preset dù có `--yes`; `-p base-nova` bị từ chối, tên preset là `nova|vega|maia|lyra|mira|luma|sera|rhea`; phải tự thêm alias `@/*` vào tsconfig và vite.config trước). Khác ghi chú: component import `cn` từ gói `cn` 0.5.2; preset nova mặc định font Geist (thiếu `₫`) và nút cao 28–32 px nên phải chỉnh cho cảm ứng; `shadcn add chart` kéo `recharts@^3.8.0` (lockfile ra 3.8.0, phải `npm i recharts@latest` mới có 3.11.0); `create-vite` 9.3.4 mặc định TypeScript 7.0.2 và oxlint. Có sẵn trong registry `@shadcn`: `message`, `message-scroller`, `bubble`, `trace`; không tìm thấy mẫu AI Elements (prompt, confirmation, reasoning, suggestion) trong registry này. Xem `spike-frontend-stack.md` §1.

**Sổ đối chiếu**

| Thư viện | Độ đẹp mặc định (ĐG) | Mobile | Tùy biến thương hiệu | Dark mode | AI agent sinh đúng | Giấy phép | Ghi chú |
|---|---|---|---|---|---|---|---|
| **shadcn/ui + Base UI** | Trung tính, sạch, "quen mắt"; đẹp khi có token riêng | Có Drawer snap points, Carousel, Field; không phải bộ "mobile" | **Tốt nhất**: mã nằm trong repo, đổi được mọi thứ | Có, biến CSS | **Rất tốt**: MCP + skill + docs đọc được như Markdown | MIT [KT] | Base UI mới làm mặc định 3 tháng; bản Radix vẫn song hành |
| HeroUI v3 3.2.7 | Đẹp sẵn, mềm, hiện đại | Chủ yếu web; mobile là sản phẩm Native riêng | Tốt (CSS variables, BEM, từng slot) | Có | Tốt: có MCP, skills, llms.txt [TL] | Apache-2.0 | Xây trên React Aria + Tailwind v4, cần React ≥ 19; chưa xác nhận có bottom sheet |
| Mantine 9.8.2 | Gọn, hơi "dashboard" | Có hook, drawer | Tốt nhưng đi theo hệ riêng, không Tailwind | Có | Khá | MIT | `@mantine/charts` cũng xây trên Recharts; peer cần React ^19.2 [KT] |
| MUI 9.5.0 | Dễ nhận ra Material | Vừa | Khó ra thương hiệu riêng "đẹp", phải đè nhiều | Có | Rất tốt (nhiều dữ liệu) | MIT | Emotion hoặc Pigment CSS; nặng; trông "Google" |
| Konsta UI 5.5.0 | Giả lập iOS/Material đúng "native" | **Rất tốt** (Tabbar, Sheet Modal, Navbar, Action Sheet) | Hạn chế (chọn theme ios/material) | Có | Ít dữ liệu | MIT | Không nói rõ hỗ trợ Tailwind v4 [TL]; giao diện giống app hệ thống, **không có nhận diện riêng** |
| Ionic React 9.0.13 | Giống native | Rất tốt | Trung bình | Có | Khá | MIT | Mang theo router/framework riêng, nặng, trái hướng "tự vẽ đẹp" |
| Chakra UI 3.38.0 | Dễ nhìn | Vừa | Tốt | Có | Khá | MIT | Emotion |
| Tremor | Đẹp cho dashboard | Vừa | Copy-paste được | Có | Vừa | Apache-2.0 | `@tremor/react` cập nhật cuối 2025-01-13 [KT]; trang chủ nói "joining Vercel", xây trên Recharts + Radix [TL] https://tremor.so; chỉ nên mượn ý tưởng, không phụ thuộc gói |
| Magic UI | Hiệu ứng bắt mắt (Number Ticker, Blur Fade…) | Hướng landing page | Copy-paste | | | Trang docs không nêu giấy phép; có phần Pro $199 [TL] | Chỉ nhặt vài hiệu ứng nếu cần, kiểm giấy phép từng file |
| Aceternity UI | Hiệu ứng nặng | Hướng landing page | | | | Không xác minh được (trang FAQ 404) | Không dùng cho app tài chính (nhiễu) |
| Origin UI / registry khác | Chưa kiểm | | | | | | Không đủ dữ liệu, bỏ qua |

Khuyến nghị tổ hợp [ĐG]: **shadcn/ui (Base UI) làm nền + token riêng; HeroUI v3 là phương án B** nếu muốn bộ có hình dáng đẹp sẵn mà ít công thiết kế (đánh đổi: ít tùy biến sâu hơn, ít mẫu mobile). Không dùng Konsta/Ionic làm nền vì kết quả là "app iOS mặc định", mâu thuẫn mục tiêu đẹp **và riêng**.

### 3.3. Biểu đồ tài chính

**So sánh thư viện** (kích thước là bundlephobia cho cả gói, chưa tree-shake, chỉ để so thứ tự độ lớn) [KT]

| Thư viện | Phiên bản | Gzip (cả gói) | Đẹp, mượt trên điện thoại (ĐG) | Hợp với dự án |
|---|---|---|---|---|
| **Recharts** | 3.11.0 | ~177 KB | SVG khai báo, animation sẵn, theme và pattern accessibility từ 3.11 [TL], touch tooltip được sửa [TL] | **Chọn làm chính**; shadcn Chart xây trên nó và đã lên v3 [TL]. **[Đã chạy thử 2026-11-21]** đo thật sau tree-shake: nhóm Recharts + d3 + redux toolkit ~118 KB gzip (không nhẹ hơn bundlephobia nhiều, vì Recharts kéo `@reduxjs/toolkit`, `immer`, `es-toolkit`, `d3-*`) |
| visx | 4.0.0 (`@visx/shape` ~11 KB) | rất nhẹ theo gói | Kiểm soát tuyệt đối, nhiều code hơn; `xychart` cần `@react-spring/web` | Dự phòng khi cần fan chart tùy biến sâu |
| ECharts | 6.1.0 | ~368 KB | Canvas, mạnh (markArea, dataZoom), giao diện "dashboard", khó khớp thương hiệu | Chỉ nếu cần hàng nghìn điểm |
| Nivo | 0.99.0 (2025-05-23) | | Đẹp, nhưng không cập nhật từ 05/2025 [KT] | Không |
| Tremor | 3.18.7 (2025-01) | | Dựa Recharts, gói không cập nhật | Không |
| Lightweight Charts | 5.3.0 | | Dành cho nến/giá chứng khoán | Không hợp (không có dải tin cậy, nhiều tùy biến thêm) |
| Chart.js | 4.6.1 | | Canvas, ít hợp React declarative | Không |
| Observable Plot / D3 thuần | d3 7.9.2 | | Đẹp, nhưng không có animation tương tác sẵn trên mobile | Chỉ dùng `d3-shape`/`d3-scale` cho phần tự vẽ |

Recharts 3.11.0 (17/11/2026): thêm hệ theme dùng chung cho cây chart, pattern, nhãn, halo; **pattern được giới thiệu như cách cải thiện accessibility**; sửa tooltip cảm ứng; bar không re-animate khi render lại không liên quan; Safari không còn cuộn trang khi dùng phím mũi tên. [TL] https://github.com/recharts/recharts/releases . shadcn Chart: "now uses Recharts v3"; dùng `var(--chart-1)` thay vì `hsl(var(--chart-1))`; `ChartContainer` phải có chiều cao (`min-h-*` hoặc `aspect-*`). [TL] https://ui.shadcn.com/docs/components/radix/chart . Trang ví dụ Recharts có "Ranged Area Chart", "Banded Chart", "Line Chart With Reference Lines", "Simple Radial Bar Chart", "Stacked Bar Chart", "Pie Chart with gap and rounded corners". [TL] https://recharts.github.io/en-US/examples/

**Ánh xạ biểu đồ dự án → cách làm** [ĐG, trừ ghi chú]

| Biểu đồ cần | Cách làm | Ghi chú |
|---|---|---|
| **Fan chart dự báo số dư hũ, dải P10–P90** | Recharts `ComposedChart`: `Area` kiểu range (dữ liệu `[p10, p90]`), `Line` P50, `ReferenceLine` dọc cho **ngày lương** (nét đứt, nhãn "Lương 5/12") và **ngày đến hạn** (vạch nhỏ kèm biểu tượng), `ReferenceDot` tại **ngày cạn** (P50 chạm 0), `ReferenceLine y=0`. Vùng sau ngày cạn tô pattern gạch chéo | Có ví dụ Ranged Area/Banded [TL]; cách truyền `[min,max]` là hiểu biết của tôi, cần thử 1 buổi. **[Đã chạy thử 2026-11-21: xác nhận]** Recharts 3.11.0, `Area dataKey` trả mảng `[p10,p90]` chạy được; `ReferenceArea` + SVG `<pattern>` cho vùng gạch chéo chạy được. Chi tiết và các chỗ phải vá (tick trục Y, nhãn chồng nhau, chấm "cạn" lệch): `spike-frontend-stack.md` §2 |
| **So sánh trước–sau what-if, đường "dịch chuyển"** | Hai đường P50: "trước" nét đứt xám, "sau" nét liền màu thương hiệu, **tô vùng giữa hai đường** (Area range) = chênh lệch; đường "sau" vẽ dần từ trái sang; số ngày cạn đếm bằng NumberFlow (23 → 19). Chỉ vẽ dải tin cậy cho đường "sau" | Cần thử xem animation nội suy của Recharts khi đổi `data` có đẹp không; nếu không, vẽ riêng SVG `path` + Motion. **[Đã chạy thử 2026-11-21: xác nhận, bản vẽ hơi khác mô tả]** đổi `data` thì Recharts tự nội suy cả dải range lẫn đường P50 (ảnh giữa chừng 260 ms có dải nằm giữa hai vị trí); không cần SVG tự vẽ. Bản đã thử vẽ hai dải (xám "trước" cố định, chàm "sau" chuyển động) thay vì tô vùng giữa hai đường P50; số ngày cạn đếm bằng NumberFlow 8 → 4 chưa chụp ảnh riêng, chỉ có mã. Ảnh: `assets/frontend-spike/whatif-light-mid.png` |
| **Vòng tiến độ / mức đầy của hũ** | **Tự vẽ SVG**: hũ thủy tinh, mực nước là `clipPath` có sóng nhẹ; biến thể vòng tròn `stroke-dasharray`. Thêm vạch nét đứt "mực dự báo tới ngày lương" | Nhẹ, nhiều thẻ trên một trang, nhận diện thương hiệu |
| **Điểm chống chịu: gauge + 4 thành phần** | **Tự vẽ SVG**: cung nửa vòng 0–100, 3 vùng, kim hoặc đầu tròn, số lớn ở giữa, nhãn chữ ("Tạm ổn"); bốn thanh nhỏ Save/Spend/Borrow/Plan (nhãn tiếng Việt) bằng HTML/CSS | Recharts RadialBar làm được nhưng tự vẽ gọn hơn |
| **Thanh phân bổ lương vào hũ** | **HTML/CSS** flex phân đoạn, Motion `layout` để đổi độ rộng mượt; kéo chỉnh bằng Base UI Slider nhiều núm hoặc `use-gesture` | Không cần thư viện biểu đồ |
| **Lịch nghĩa vụ** | **HTML/CSS**: dải thời gian 30 ngày nằm ngay dưới fan chart cùng trục x, mỗi nghĩa vụ một chấm có biểu tượng và số tiền; cộng thêm danh sách "Sắp đến hạn" | Cùng trục x với fan chart giúp thấy "lương về trước hay sau khoản đến hạn" |
| Chi tiêu theo hũ (phân tích) | Recharts `BarChart` xếp chồng hoặc `PieChart` kiểu vòng | Đơn giản |
| Sparkline trên thẻ hũ | `d3-shape` + `<path>` tự vẽ | Tránh dựng 7+ instance Recharts trên một màn hình |

Hiệu năng trên máy tầm trung [ĐG]: giữ ≤ ~100 điểm mỗi series (30 ngày × 1–3 series là thừa); chỉ 1–2 biểu đồ Recharts đầy đủ mỗi màn hình; `React.lazy` cho tab "Nhìn trước" để Recharts không nằm trong bundle đầu; tắt animation khi `prefers-reduced-motion`; hiện số liệu then chốt ở một **dòng đọc cố định phía trên biểu đồ** thay vì tooltip nổi (ngón tay che mất tooltip).

### 3.4. Animation và cảm giác

| Nhu cầu | Giải pháp | Nguồn/ghi chú |
|---|---|---|
| Animation tổng quát, layout, drag, exit | **Motion 14.14** (`import … from "motion/react"`): `layout`, `layoutId`, `AnimatePresence`, gesture, spring; dùng WAAPI cho phần tăng tốc phần cứng | [TL] https://motion.dev/docs/react |
| Kích thước | Component `motion` không thể tree-shake dưới ~43 KB gzip; `LazyMotion` + `m` còn ~5 KB đầu, thêm `domAnimation` 24 KB hoặc `domMax` 38 KB (cần cho layout/drag); `animate()` bản mini 3,3 KB | [TL] https://motion.dev/docs/react-reduce-bundle-size. Dự án cần layout + drag nên dùng `domMax`; chỉ nạp khi cần |
| Giảm chuyển động | `<MotionConfig reducedMotion="user">` bọc toàn app (tắt transform và layout, giữ opacity/màu) | [TL] https://motion.dev/docs/react-accessibility |
| Số tiền chạy | **`@number-flow/react` 0.6.2** (~6 KB gzip [KT]): nhận `Intl.NumberFormat` options, `trend`, tôn trọng reduced motion mặc định. Không thấy tài liệu nói về VND, nhưng nhận `format` kiểu `Intl`, nên truyền `locales="vi-VN"` và `currency: 'VND'`; cần thử (nên tự cung cấp `suffix="đ"`). **[Đã chạy thử 2026-11-21]** chạy với React 19.3.1: `<NumberFlow value locales="vi-VN" format={{maximumFractionDigits:0}} suffix={' ₫'} />` ra "12.480.000 ₫" đúng dấu chấm nhóm nghìn, các chữ số cuộn khi đổi giá trị (ảnh `assets/frontend-spike/numberflow-mid.png`); không dùng `style:'currency'`, dùng `suffix` tự cung cấp. Chữ số cuộn giữa chừng làm số dư tạm thời hiện "26.480.000" trước khi về 27.480.000 (hiệu ứng bình thường, đáng để ý với số tiền) | [TL] https://number-flow.barvian.me/ |
| Chuyển trang | `<ViewTransition>` (§3.1) | |
| Skeleton khi stream | shadcn Skeleton cho khối chưa tới; với khối AI dùng **khung có kích thước cố định** (chiều cao đúng của khối) để không nhảy bố cục; câu "đang đọc dự báo…" lấy từ sự kiện bắt đầu/kết thúc tool, hiển thị bằng Trace của shadcn | [TL] Trace: https://ui.shadcn.com/docs/changelog (10/2026) |
| Haptic/phản hồi chạm | `web-haptics` 0.0.6: `useWebHaptics().trigger("success")`, preset success/nudge/error/buzz, có `isSupported` (Vibration API) và tùy chọn `showSwitch` cho iOS; README không giải thích cách chạy trên iOS | [TL] https://github.com/lochie/web-haptics. **iOS không có Vibration API** [BV firt.dev]. Dùng như điểm cộng: feature-detect, im lặng nếu không hỗ trợ. Phản hồi thay thế luôn có: hiệu ứng nhấn (`whileTap` scale 0.97), đổi trạng thái nút, âm thanh không dùng |
| Mượt trên máy tầm trung | Chỉ animate `transform`/`opacity`; không animate `width/height` của danh sách dài (dùng `layout` có chọn lọc); ảnh/minh họa SVG nhỏ; không blur/backdrop-filter chồng nhiều lớp; kiểm bằng CPU throttle 4× của Chrome DevTools | [ĐG] |

Gợi ý micro-interaction chủ đạo [ĐG]: (1) chuyển tiền xong thấy đồng xu rơi vào hũ đích và mực nước dâng; (2) bấm kịch bản what-if thấy đường dự báo dịch chuyển và số ngày cạn đếm; (3) giữ để xác nhận (hold-to-confirm) cho giao dịch lớn thay vì hộp thoại hai lần bấm.

### 3.5. Mẫu thiết kế app ngân hàng/ví

Chú thích về chất lượng nguồn: không có nghiên cứu UX độc lập đo đạc hiệu quả cho các mẫu dưới đây; phần lớn là tài liệu của chính hãng hoặc blog thiết kế. Hãy coi là gợi ý để thử với người dùng.

| Nguồn | Điều rút ra | Áp dụng cho Yofina [ĐG] |
|---|---|---|
| **Revolut** (bài ra mắt 7.0, diễn đàn, bài heuristic) | Ba tab Home/Wealth/Payments; số dư hiện ngay ở bước gửi tiền nên người dùng không phải nhớ; diễn đàn và một bài đánh giá chê Home dày đặc, giấu hành động quen thuộc [TL][BV] https://www.revolut.com/blog/post/introducing-revolut-7-0/ | Home ít khối, mỗi khối trả lời một câu hỏi; hành động nhanh luôn ở vị trí cố định |
| **Monzo** (bài "Delightful Payments", diễn đàn Pots) | Thứ tự cố định: số tiền → tham chiếu → nguồn → đích → nút xem lại, **cùng thứ tự cho mọi loại thanh toán**; bottom sheet phủ lên màn hình hiện có; chỉ gợi ý sửa khi chắc chắn; "Move money" khó tìm, chuyển giữa các Pot từng là một trong những điểm khó chịu nhất theo nghiên cứu của chính Monzo, người dùng muốn nút chuyển **ngay trên pot**; người dùng xin thanh tiến độ mục tiêu và ảnh thẻ pot tùy biến [TL][BV] https://monzo.com/blog/delightful-payments/ ; https://community.monzo.com/t/we-ve-shipped-pot-to-pot-transfers/148972 | Nút "Chuyển giữa hũ" nằm ngay trên thẻ hũ và trong chi tiết hũ; mọi luồng tiền dùng chung một khung và thứ tự; bottom sheet cho bước xem lại |
| **N26 Spaces** | Home dạng module; Spaces có dạng danh sách để thấy mọi số dư một lượt [BV] https://n26.com/en-de/blog/building-a-simple-flexible-banking-experience | Màn Hũ có hai chế độ: lưới thẻ hũ và danh sách gọn; mặc định danh sách cho 7 hũ |
| **Wise** (bài phân tích) | Hiện tổng chi phí, tỷ giá, số tiền người nhận **trước** khi cam kết; sau khi gửi vẫn có màn trạng thái: đã xảy ra gì, đang xảy ra gì, bao giờ tới [BV] https://raw.studio/blog/how-wise-uses-3-transparency-first-ux-principles/ | Đúng chất F3: thẻ "kiểm tra trước khi quẹt" hiện tổng chi phí thật và hũ nào bị ảnh hưởng ngay tại màn nhập số tiền; biên nhận có "Dự báo mới" |
| **Copilot Money** | Apple Design Award Finalist 2024; đội "rất kỹ" về thiết kế và làm tùy biến nhiều; biểu đồ Cash Flow xây bằng Swift Charts [BV] https://developer.apple.com/articles/copilot-money | Học cách "bình tĩnh": ít màu, số liệu nổi bật, biểu đồ tương tác sâu dần. Bài của Apple không mô tả gesture hay màu cụ thể, đừng suy diễn |
| **Cash App** | Một tương tác lõi làm cực nhanh, nhận diện táo bạo (màu, font riêng), phản hồi vật lý trên mỗi lần chạm [BV] https://www.lazarev.agency/articles/best-fintech-apps (nguồn thứ cấp của một agency) | Chuyển tiền ≤ 4 chạm từ Home; nhận diện đủ riêng để nhận ra ở ảnh chụp màn hình |
| **MoMo** (trang hướng dẫn chính thức) | Chuyển tiền: chọn "Đến MoMo" → người nhận (số điện thoại hoặc danh bạ) → số tiền + lời nhắn (kèm sticker, hình nền) → chọn nguồn tiền → xác nhận. **Ví Trả Sau không dùng để chuyển tiền sang ví khác** [TL] https://www.momo.vn/huong-dan/huong-dan-chuyen-tien-bang-vi-momo ; trang kết quả tìm kiếm | Giữ thứ tự bước quen thuộc với người Việt; trong luồng chuyển tiền của app mô phỏng, nguồn "Ví Trả Sau" hiện nhưng khóa kèm giải thích — đồng thời khớp luật suitability "không khuyên vay để tiêu". **Không** dùng màu, logo, mascot, sticker của MoMo |
| **TNEX/Timo/Cake/ZaloPay** | Tìm kiếm không cho đánh giá UI đáng tin cậy riêng cho các app này; khảo sát quốc tế cho biết 71,8% người dùng app ngân hàng lo thêm quá nhiều dịch vụ làm app rối [BV] (tìm kiếm tổng hợp) | Không rút mẫu cụ thể; áp nguyên tắc "ít dịch vụ, rõ việc chính" |
| Bài về lo âu tài chính | Số dư tạm thời tô đỏ lớn gây hiểu lầm (ví dụ Robinhood); nên hiện số dư và hành động chính ở đầu màn, khoảng trắng nhiều, phản hồi tức thì; nhận biết thiên lệch tránh mất mát [BV] https://uxmag.com/articles/designing-effective-experiences-for-financial-services ; https://finextra.com/blogposting/25955/money-is-about-emotions-dont-let-financial-services-ruin-lives | Xem §3.7 |

**Mẫu cụ thể nên áp dụng**

1. **Màn Tổng quan**: một câu "nhìn trước" ở trên cùng ("Hũ Ăn uống dự kiến cạn ngày 23, còn 12 ngày tới lương") + thẻ số dư + 4–5 hành động nhanh (Chuyển tiền, Quét QR, Chuyển giữa hũ, Kiểm tra trước khi quẹt, Tiền vào) + dải hũ cuộn ngang + "Sắp đến hạn" + giao dịch gần đây. Số dư ẩn/hiện bằng biểu tượng mắt. [ĐG]
2. **Thẻ hũ**: tên, biểu tượng riêng, số dư, mực nước theo % so với kế hoạch tháng, vạch dự báo, **một dòng trạng thái có chữ và biểu tượng** ("Đủ tới kỳ lương", "Sát: cạn sớm 3 ngày", "Hụt 120.000đ trước ngày 5"), nút chuyển. Chạm vào thẻ → chi tiết hũ (share element). [ĐG]
3. **Luồng chuyển tiền** (full-screen, bước có thanh tiến độ mảnh): **(1) Người nhận**: gần đây, danh bạ mô phỏng, nhập SĐT/số tài khoản, Quét QR → **(2) Số tiền**: bàn phím số tự dựng, gợi ý 100k/200k/500k, lời nhắn, đọc bằng chữ bên dưới ("một triệu hai trăm nghìn đồng"), hiển thị số dư hũ nguồn → **(3) Nguồn tiền**: chọn hũ, thẻ F3 xanh/vàng/đỏ ngay tại đây → **(4) Xem lại** (bottom sheet: người nhận, số tiền, nguồn, hũ sau giao dịch) → **(5) Xác nhận** (giữ để xác nhận hoặc PIN mô phỏng 6 số; giao dịch cuối cùng cần người dùng bấm — khớp FR12) → **(6) Biên nhận** (dấu tích động, số tiền, mã giao dịch, thời gian, "Hũ X còn Y", nút Chia sẻ ảnh, "Xem dự báo mới"). Mọi bước hiện lại số tiền để người dùng không phải nhớ. [ĐG, kết hợp Monzo/Wise/MoMo]
4. **Danh sách giao dịch**: nhóm theo ngày, avatar/biểu tượng hũ, chip lọc theo hũ, nhãn "Xem lại" cho khoản độ tin cậy 0,6–0,9 (sửa một chạm theo §10.3 proposal), mục "Chưa phân loại" nổi bật nhưng không báo động; chạm dòng → bottom sheet đổi hũ với lựa chọn "chỉ lần này / luôn luôn cho người này". [ĐG]
5. **Phân tích chi tiêu**: so với kế hoạch (không chỉ nhìn lại), cột xếp chồng theo hũ theo tuần, 1 nhận xét/việc tiếp theo ở đầu màn (F7). [ĐG]
6. **Onboarding khai báo** (dùng Questionnaire của shadcn): 1 lương + ngày nhận (bắt buộc) → 2 hũ và luật chia (thanh phân bổ kéo được, tổng = lương) → 3 chi phí cố định (bỏ qua được) → 4 khoản vay (bỏ qua được) → 5 mục tiêu (bỏ qua được) → 6 mức chấp nhận rủi ro (ba thẻ chọn) → xem "Hũ nhìn trước" lần đầu. Thanh "Dự báo dựa trên N/6 mục đã khai" để hiện độ phủ. Bước nào cũng có nút "Để sau" trừ bước 1. [ĐG, theo proposal §4: chỉ lương và ngày nhận bắt buộc]

**Điều nên tránh** [ĐG, có chỗ dựa vào nguồn ở bảng trên]: Home dày đặc/giấu hành động; chuyển giữa các hũ nằm sâu trong menu (bài học Monzo); nhiều tab hơn 5; hộp thoại chồng hộp thoại; tooltip chỉ hiện khi hover; số âm tô đỏ gắt; màu là tín hiệu duy nhất; cuộn vô hạn ở những màn giám khảo cần tìm nút; sao chép thẻ ngân hàng giả (skeuomorphic) và mọi nhận diện của MoMo; gây hiểu nhầm là app thật (giữ nhãn "Ví mô phỏng · dữ liệu minh họa").

### 3.6. Chi tiết Việt Nam

**Định dạng tiền** [KT: chạy trên Node 24.15 / ICU 78.2; trình duyệt khác có thể ra chữ khác nhau, nên tự viết]

- `Intl.NumberFormat('vi-VN',{style:'currency',currency:'VND'}).format(1200000)` → `"1.200.000 ₫"` (có ký tự NBSP trước `₫`).
- `notation:'compact'` mặc định ra `"1,2 Tr"`, `"950 N"`, `"1,5 T"`; `compactDisplay:'long'` ra `"1,2 triệu"`, `"950 nghìn"`, `"1,5 tỷ"`, nhưng 1.250.000 làm tròn 1 chữ số thành "1,3 triệu".
- Đề xuất `lib/format.ts` [ĐG]:
  - Lưu **số nguyên đồng** (VND không có đơn vị nhỏ hơn); không dùng `number` dấu phẩy động cho phép tính tiền, dùng số nguyên hoặc `bigint` khi cộng dồn.
  - `formatVND(n)` → `1.200.000đ` (chữ "đ" thường, quen thuộc trên app Việt; dùng `₫` chỉ khi cần). Âm: `−120.000đ` bằng dấu trừ Unicode `−`.
  - `formatVNDShort(n)` tự viết ngưỡng: ≥ 1e9 "x,y tỷ"; ≥ 1e6 "x,y triệu"; ≥ 1e3 "x nghìn" (hoặc "xk" ở chỗ rất chật); bỏ phần thập phân nếu là 0; dấu phẩy thập phân kiểu Việt.
  - Số trong biểu đồ trục dùng dạng rút gọn; số trong thẻ/biên nhận dùng dạng đầy đủ; số chính trong câu trả lời AI luôn đầy đủ để khớp NFR "100% số khớp tool".
  - `font-variant-numeric: tabular-nums` cho mọi số tiền.
- **Ngày giờ**: `Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })` cố định múi giờ (giám khảo có thể ở nơi khác, Việt Nam không có giờ mùa hè). Kết quả kiểm: `Thứ Bảy, 5 tháng 12`, `05/12/2026`, `5 thg 12`, `RelativeTimeFormat` → "sau 12 ngày nữa" / "Hôm qua". [KT] Câu hiển thị ưu tiên: "còn 12 ngày tới lương (5/12)". Ngày lương "ngày 5 hàng tháng" lưu số nguyên 1–31, xử lý tháng ngắn (ngày 31 ở tháng 30 ngày → ngày cuối tháng).
- **Nhập số tiền**: bàn phím số tự dựng (nút 1–9, 0, 000, xóa; giữ để xóa nhanh); hiển thị nhóm nghìn khi gõ; chip nhanh "+100k, +500k, +1 triệu"; giới hạn theo số dư nguồn; `inputMode="numeric"` chỉ làm phương án dự phòng. Đọc số thành chữ ("một triệu hai trăm nghìn đồng") dưới ô nhập như lớp chống nhập nhầm. [ĐG]
- **Mã QR/VietQR (mô phỏng)**: VietQR theo chuẩn EMVCo cho thanh toán bằng QR do người dùng quét, NAPAS bổ sung trường 38 chứa mã ngân hàng (6 số BIN) và số tài khoản, tiền tệ 704, số tiền tùy chọn (QR tĩnh bỏ qua, QR động có). Tôi chỉ đọc nguồn thứ cấp (thư viện, bài báo), chưa đọc đặc tả NAPAS; đừng khẳng định đây là đúng chuẩn. [BV] https://www.pkgstats.com/pkg:vietqr-ts ; https://english.vtv.vn/news/napas-unveils-unified-qr-code-system-for-bank-transfers-2021062123463189.htm . Cho demo: tạo QR "nhận tiền" bằng `qrcode.react` 4.2 hoặc `react-qr-code` 2.2 với **nội dung giả** (tên và số tài khoản hư cấu, không dùng BIN/tài khoản thật); quét bằng `@yudiel/react-qr-scanner` 2.6 (cần HTTPS và quyền camera; `getUserMedia` có trên iOS từ 13 [BV]) **kèm nút "Quét thử" chọn ngay một người nhận mẫu** để giám khảo không có camera vẫn đi hết luồng. [ĐG][KT phiên bản]
- **Font tiếng Việt** (kiểm bằng cách tải file TTF từ Google Fonts, đối chiếu cmap với các ký tự `Ạ Ấ Ặ Ọ Ụ Ỹ Đ đ Ơ ơ ₫` và dấu kết hợp U+0300/0309/0323, và liệt kê GSUB) [KT]:

| Font | Subset `vietnamese` (metadata Google) | Ký tự Việt trong file | `₫` | `tnum` | Nhận xét [ĐG] |
|---|---|---|---|---|---|
| **Plus Jakarta Sans** | Có | Đủ | Có | **Có** | **Chọn**: hình học ấm, dễ đọc, hợp ví/fintech, biến thiên |
| Inter | Có | Đủ | Có | Có | Dự phòng an toàn, hơi "mặc định" |
| Be Vietnam Pro | Có | Đủ | Có | **Không** (chỉ `frac`) | Thiết kế cho tiếng Việt, rất tốt cho tiêu đề/đoạn văn; số tiền sẽ lệch cột nếu không dùng NumberFlow |
| Bricolage Grotesque | Có | Đủ | Có | Có | Cá tính, hợp tiêu đề lớn, cân nhắc làm font hiển thị thứ hai |
| Manrope | Có | Thiếu dấu kết hợp U+0300/0309/0323 | Có | Có | Dùng được với chữ dựng sẵn nhưng rủi ro với văn bản gõ dấu rời |
| Geist / Onest | Có | Đủ | **Thiếu `₫`** | Có | Tránh cho số tiền nếu dùng `₫` |
| DM Sans, Figtree, Outfit, Sora | **Không** | | | | Loại |

  Cách nạp: `@fontsource-variable/plus-jakarta-sans` 5.3.0 (OFL-1.1) tự host, không gọi Google Fonts lúc chạy (giảm độ trễ và rủi ro mạng khi giám khảo thử). Thực hành: `line-height` thân ≥ 1.4, tiêu đề ≥ 1.2 (dấu chồng "Ế", "Ợ" bị cắt nếu quá chặt); tránh `letter-spacing` âm; `overflow:hidden`/`line-clamp` thêm padding trên-dưới; thử chữ in hoa "TỔNG QUAN", "HỦ ĂN UỐNG". [ĐG]

### 3.7. Trực quan hóa dữ liệu tài chính đúng cách

**Bất định cho người không chuyên** [ĐG, dựa trên các nguồn nêu]

- **Câu trả lời trước, biểu đồ sau**: đặt một câu và một con số lên đầu ("Dự kiến cạn ngày 23 · khả năng hụt trước lương: khoảng 7/10"), sau đó mới tới biểu đồ. Số then chốt có kích thước chữ lớn nhất của khối.
- **Một đường trung vị + một dải**, không nhiều dải lồng nhau. Nghiên cứu theo dõi mắt (Williams, Mulder và cộng sự) cho thấy đường trung vị làm giảm số lần nhìn và gánh nặng nhận thức cho cả người chuyên và không chuyên khi đọc fan plot. [BV] https://www.osti.gov/pages/servlets/purl/2311603 (kết quả tìm kiếm tổng hợp).
- **Đóng khung theo tần suất**: "trong 10 kịch bản mô phỏng, 7 bị hụt" kèm hàng 10 chấm (icon array); tổng quan tài liệu cho thấy hiển thị theo tần suất hiệu quả hơn với người ít tính toán, và nên giữ đúng tỷ lệ tử/mẫu. Biểu đồ khoảng (interval) khó cho cả chuyên gia lẫn người mới. [BV] Padilla, Kay, Hullman 2020 https://moodle2.units.it/pluginfile.php/466375/mod_resource/content/0/Uncertainty_Visualization_Padilla_Kay_Hullman_2020.pdf ; EU Data Visualisation Guide https://data.europa.eu/apps/data-visualisation-guide/frequencies
- **Nhãn thường ngày, không thuật ngữ**: dải = "khoảng 80% khả năng số dư nằm trong vùng này"; mép dưới = "nếu chi nhiều hơn bình thường", mép trên = "nếu chi ít hơn"; đừng viết P10/P90 trên giao diện (chỉ ở bảng "Vì sao").
- **Không giả chính xác**: làm tròn xác suất theo bậc 5% hoặc "khoảng x/10"; ngày cạn nói dạng khoảng ("21–25/11, nhiều khả năng 23/11"). Cảnh báo của tài liệu: hình ảnh hóa bất định có thể làm nó trông chắc chắn hơn dạng chữ [BV], nên luôn kèm nhãn "ước tính" và độ phủ dữ liệu ("dựa trên 4/6 mục đã khai").
- Hiển thị **độ tin cậy thấp** (dưới 30 ngày dữ liệu): dải rộng + nhãn "ước tính ban đầu", không tô màu trạng thái mạnh.

**Màu trạng thái đủ / sát / hụt và accessibility**

- WCAG 2.2 **1.4.1 Use of Color**: màu không được là phương tiện duy nhất truyền thông tin; phải kèm chữ, hình dạng hoặc biểu tượng. [TL] https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html
- **1.4.11 Non-text Contrast (AA)**: phần đồ họa cần để hiểu nội dung (đường, lát cắt) cần ≥ 3:1 so với nền kề; chữ trong biểu đồ vẫn theo 4.5:1; không áp dụng khi chữ truyền đạt cùng thông tin. [TL] https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html
- Mã hóa ba lớp: **màu + biểu tượng + chữ** — Đủ: tròn-tích (teal) "Đủ tới kỳ lương"; Sát: tam giác-chấm than (hổ phách) "Sát, cạn sớm N ngày"; Hụt: mũi tên xuống/hình thoi (san hô) "Hụt M đồng". Dùng thêm pattern gạch chéo cho vùng hụt trên biểu đồ (Recharts 3.11 có pattern). [ĐG][TL]
- Độ tương phản tôi tính cho bảng màu đề xuất (WCAG, trên nền trắng `#FFFFFF`) [KT]: đường `#12A37F` 3,20; `#0E9F78` 3,36; hổ phách `#E8A317` chỉ **2,17 (trượt 3:1)** nên dùng `#C98500` = 3,07 cho nét hổ phách; san hô `#E5484D` 3,91. Chữ trạng thái trên nền nhạt: `#0B6B52`/`#E3F6EE` 5,77; `#8A5300`/`#FFF2D9` 5,71; `#B4233C`/`#FFE9EC` 5,58. Dark mode: chữ phụ `#A3A5BF` trên `#181A2B` 7,12; teal `#34D3A0` 8,98; hổ phách `#F5B94A` 9,76; san hô `#FF7A8A` 6,88.
- Văn bản thay thế: mỗi biểu đồ có tóm tắt chữ liền kề, nút "Xem dạng bảng", `role="img"` + `aria-label` chứa số then chốt; điều hướng bằng phím mũi tên trên Recharts (3.11 đã xử lý Safari). [ĐG][TL]

**Tránh gây lo lắng** [ĐG, tinh thần theo các bài ở §3.5]

- Dùng hồng san hô, không dùng đỏ tươi; không tô số tiền lớn màu đỏ; **số âm hiển thị bằng chữ + hành động** ("Cần thêm 120.000đ trước ngày 5. Chuyển từ hũ Giải trí?").
- Mỗi màn hình tối đa **một** cảnh báo nổi bật; còn lại là thông tin yên tĩnh. Phù hợp FR13 (tối đa một nhắc mỗi ngày).
- Gauge không có vùng "nguy hiểm" tô đỏ chói; nhãn "Tạm ổn / Cần củng cố"; luôn kèm "Điểm này không phải điểm tín dụng" (proposal §11).
- Khoản tạm thời/chưa phân loại ghi rõ "dự kiến"/"chưa phân loại" (bài học Robinhood).
- Mọi cảnh báo có đường ra: nút hành động cụ thể + "Vì sao?".

### 3.8. Chỗ đặt chatbot và bộ component dùng chung

**Chỗ đặt chatbot** [ĐG]

- **Tab giữa nổi "Hỏi Yofina"** trong thanh tab dưới = màn chat đầy đủ (lịch sử, gợi ý nhanh: "nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao", "mất việc 2 tháng", "tháng này tôi tiêu thế nào").
- **Điểm vào theo ngữ cảnh**: nút "Hỏi về hũ này", "Hỏi vì sao" trên Chi tiết hũ, Nhìn trước, thẻ kiểm tra trước khi quẹt → mở **bottom sheet** (Base UI Drawer, snap 50% và 100%) với ngữ cảnh gắn sẵn (mã hũ, khoảng ngày).
- **Một luồng hội thoại duy nhất** (một store, một thread): sheet và tab chat hiển thị cùng tin nhắn.
- Chat không chặn việc chính: các khối kết quả có nút "Mở trong Nhìn trước" (điều hướng, mang theo kịch bản) để giám khảo thấy cùng một thứ ở hai nơi.
- Dùng bộ chat của shadcn: Message Scroller (quản lý cuộn khi stream, "không sở hữu message, AI state, transport"), Message, Bubble, Marker, Attachment; AI Elements cho Prompt Input, Suggestion, Tool/Trace, Confirmation, Plan. Chưa xác nhận được độ tương thích trực tiếp với luồng AG-UI tự dựng (trang chỉ nói component không giữ transport, nên về nguyên tắc ghép được); cần thử. [TL] https://ui.shadcn.com/docs/changelog/2026-06-chat-components , https://ui.shadcn.com/docs/ai-elements

**Một bộ component, hai nơi dùng**

Quy tắc [ĐG]:

1. Mỗi khối AI là **component thuần "props → UI"**, không tự fetch; props mô tả bằng **Zod schema** đặt cạnh component. Màn hình chính lấy dữ liệu bằng TanStack Query rồi truyền props; chat truyền props từ JSON của agent.
2. **Registry**: `blockRegistry: Record<BlockType, { schema: ZodType; Component: FC<any> }>`; trước khi vẽ phải `safeParse`; không hợp lệ hoặc `type` lạ → hiển thị phần văn bản + nhãn "Không hiển thị được khối này" (suy giảm có kiểm soát, đúng NFR độ tin cậy).
3. Mỗi component có `variant: 'full' | 'compact'` hoặc tự co giãn bằng `@container`: trong bong bóng chat (≈ 100% bề ngang trừ lề) tự ra bố cục gọn; trên màn hình đầy đủ ra bố cục rộng.
4. Cùng token màu, cùng định dạng tiền, cùng nhãn trạng thái; khối AI luôn có nhãn "AI" nhỏ và `trace_id` mở bảng "Vì sao" (proposal §9, §12).
5. Khối có hành động đổi số dư (`confirm`) **dùng chính component xem lại của luồng chuyển tiền** (`ReviewSheet`), nên nút xác nhận hành xử giống nhau và đúng FR12.

| Khối AI (`type`) | Component dùng chung | Nơi dùng ngoài chat |
|---|---|---|
| `forecast_timeline` | `ForecastFanChart` (+ `ObligationStrip`) | Nhìn trước, Chi tiết hũ |
| `obligation_impact` | `ObligationImpactCard` | Chi tiết khoản vay/trả sau, Kiểm tra trước khi quẹt |
| `options` | `OptionCards` | Lộ trình, thẻ F3 |
| `explain` | `WhySheetTrigger` + `WhyPanel` | Mọi nơi có nhãn "Vì sao?" |
| `confirm` | `ReviewSheet` + `HoldToConfirm` | Chuyển tiền, chuyển giữa hũ, nhận lương |
| (bổ sung) `affordability` | `AffordabilityCard` (xanh/vàng/đỏ) | Màn nhập số tiền của chuyển tiền |
| (bổ sung) `scenario_compare` | `WhatIfChart` | Nhìn trước (chip kịch bản) |
| (bổ sung) `resilience` | `ResilienceGauge` | Tổng quan, Nhìn trước |
| (bổ sung) `jar_summary` | `JarCard` | Hũ, Tổng quan |
| (bổ sung) `allocation` | `AllocationBar` | Onboarding, Lộ trình |
| (bổ sung) `ingest_progress` | `IngestProgress` + `RowReviewList` | Nạp dữ liệu |

(Các `type` "bổ sung" là đề xuất của tôi, cần thống nhất với agent làm hợp đồng Composer.)

### 3.9. State, dữ liệu, form, xác thực, kiểm thử

| Việc | Chọn | Lý do/Ghi chú |
|---|---|---|
| Dữ liệu REST (hũ, giao dịch, nghĩa vụ) | **TanStack Query 5.108** | Cache, refetch sau khi xác nhận giao dịch (invalidate theo hũ), trạng thái loading cho skeleton |
| Luồng AG-UI/SSE | **Zustand 5** store + reducer: ghép `TEXT_MESSAGE_*`, tiến trình tool, khối UI, trạng thái chờ xác nhận | SSE không đi qua TanStack Query. Dùng `@ag-ui/client` `HttpAgent` (`url`, `headers`, `runAgent`, `subscribe`, `abortRun`) [TL] https://docs.ag-ui.com/sdk/js/client/http-agent ; chưa thấy tài liệu nói rõ chạy trên trình duyệt, cần thử |
| Form và validate | **React Hook Form 7.92 + Zod 4.6 + `@hookform/resolvers` 7.0.8** | Onboarding (lương, hũ, chi phí cố định…), chuyển tiền; dùng cùng Zod với schema khối AI. Kiểm tra bản resolver tương thích Zod 4 khi cài |
| Xác thực Cognito | **`aws-amplify` 6.22 chỉ dùng `aws-amplify/auth`** (`signIn`, `fetchAuthSession`…), giao diện đăng nhập tự dựng cho đẹp | Tài liệu Amplify: token lưu `localStorage` mặc định, có thể đổi sang cookie/sessionStorage; `signIn` trả `nextStep`; ID token chứa thông tin cá nhân và **không dùng để cấp quyền truy cập tài nguyên**, access token mới dùng để xác minh người gọi [TL] https://docs.amplify.aws/react/build-a-backend/auth/concepts/tokens-and-credentials/ . Gói gzip ~20 KB cả gói [KT]. Cần phối hợp backend: AgentCore xác thực JWT bằng `allowedClients`/audience nào quyết định gửi access hay ID token |
| Tài khoản demo | Nút "Dùng tài khoản demo" đăng nhập sẵn + "Đặt lại dữ liệu" | Proposal §13 |
| Theme | Biến CSS + class `.dark`; `next-themes` 0.4.6 chạy được ngoài Next hoặc viết 20 dòng tự làm | |
| Kiểm thử nhanh | **Vitest 5.1 + Testing Library** cho `format.ts`, reducer AG-UI, schema khối; **Playwright 1.65** với thiết bị iPhone/Pixel, chụp ảnh màn hình hồi quy 6 cảnh demo; **MSW 3** giả lập SSE AG-UI để dựng giao diện khi backend chưa xong | Storybook 10.6 bỏ qua trong 3 tuần, trừ khi có người rảnh |
| Hỗ trợ AI agent | `shadcn mcp init --client claude`, cài skill của shadcn; đặt `CLAUDE.md` frontend ghi token, quy tắc `format.ts`, danh sách khối | |

---

## 4. Khuyến nghị cho Yofina

### 4.1. Màn hình và điều hướng đề xuất

**Thanh tab dưới (5):** `Tổng quan` · `Hũ` · **`Hỏi Yofina`** (nút giữa nổi, màu chủ đạo) · `Nhìn trước` · `Hồ sơ`.

| # | Màn hình | Nội dung chính | Tính năng |
|---|---|---|---|
| 0 | Đăng nhập | Email/mật khẩu (Cognito), nút "Dùng tài khoản demo" | — |
| 1 | Khai báo (onboarding) | Questionnaire 6 bước (§3.5), thanh phân bổ lương, độ phủ | FR1, FR4 |
| 2 | **Tổng quan** | Câu nhìn trước, số dư, hành động nhanh, dải hũ, điểm chống chịu thu nhỏ, sắp đến hạn, giao dịch gần đây, "Cần xem lại (n)" | F1, F4 |
| 3 | **Hũ** (danh sách) | Lưới/ danh sách, tổng, "Chưa phân loại", nút chuyển giữa hũ | FR1 |
| 3a | Chi tiết hũ | Mực nước, fan chart riêng của hũ, giao dịch, luật chia, mục tiêu, nút Chuyển/Hỏi | F1, F5 |
| 4 | **Nhìn trước** | Chọn phạm vi (tất cả hay một hũ), fan chart 30 ngày + dải nghĩa vụ, chip kịch bản (mất việc 2 tháng, tiền trọ tăng, ốm một tuần), điểm chống chịu (gauge + 4 thành phần), lộ trình | F1, F2, F4, F5 |
| 5 | **Chuyển tiền** (luồng toàn màn hình) | Người nhận → số tiền → nguồn (thẻ F3) → xem lại → xác nhận → biên nhận; biến thể "Chuyển giữa hũ" dùng chung | FR1, F3, FR12 |
| 5a | Quét/nhận QR | Quét thử, QR mô phỏng của mình | — |
| 6 | **Hỏi Yofina** (chat) | Thread, gợi ý, khối trực quan, tiến trình tool, xác nhận, đính ảnh | F2–F6 |
| 7 | Hoạt động | Danh sách giao dịch nhóm ngày, lọc theo hũ, đổi hũ một chạm | FR2 |
| 8 | Phân tích chi tiêu | So với kế hoạch theo hũ/tuần, 1 nhận xét/việc tiếp theo | F7 |
| 9 | Nạp dữ liệu | Chụp/chọn ảnh hoặc CSV, tiến độ, hàng chờ xác nhận, độ phủ tăng | F6 |
| 10 | Bảng "Vì sao" (sheet) | Dữ liệu đã dùng, luật đã kiểm, độ tin cậy, `trace_id` | FR11 |
| 11 | Hồ sơ/Cài đặt | Sửa khai báo (lương, chi phí cố định, khoản vay), theme, đặt lại demo, quyền riêng tư | FR1, FR4 |
| 12 | Trace cho đội sản phẩm (ngoài tab, đường dẫn riêng) | Màn "Future Workspace" cảnh 6 | FR15 (mở rộng) |

Ánh xạ 6 cảnh demo: Cảnh 1 = Tổng quan (câu nhìn trước + fan chart thu nhỏ); 2 = chat → `scenario_compare` + `affordability`; 3 = chip kịch bản ở Nhìn trước → gauge tụt; 4 = lộ trình + "Vì sao" + chatbot từ chối đúng phạm vi; 5 = Nạp dữ liệu; 6 = màn trace. [ĐG]

**Thứ tự dựng gợi ý trong 3 tuần** [ĐG]: tuần 1: scaffold Vite + token + `format.ts` + vỏ app (tab bar, ViewTransition) + dữ liệu giả + Tổng quan/Hũ + luồng chuyển tiền trên ví mô phỏng; tuần 2: fan chart, what-if, registry khối AI + chat với MSW rồi nối AG-UI thật; tuần 3: gauge, onboarding, nạp dữ liệu, dark mode, hiệu năng, quay demo trên điện thoại thật.

### 4.2. Hướng nhận diện riêng cho Yofina [ĐG, toàn bộ là đề xuất]

- **Ý tưởng**: "Hũ nhìn trước" = hũ thủy tinh có mực nước và một vạch mờ cho mực dự báo; cảm giác bình tĩnh, rõ ràng, không giống một ngân hàng.
- **Bảng màu (hex đã kiểm tỉ lệ ở §3.7)**

| Vai trò | Sáng | Tối |
|---|---|---|
| Nền | `#F6F5F1` (kem ấm) | `#0E0F1A` |
| Bề mặt (thẻ) | `#FFFFFF` | `#181A2B` |
| Chữ | `#14142B` (16,5:1 trên nền) | `#F2F2F8` |
| Chữ phụ | `#5B5B73` (6,0:1) | `#A3A5BF` |
| Chủ đạo (chàm) | `#4338CA` (7,9:1 với chữ trắng) | `#8B93FF` |
| Đủ (teal) | chữ `#0B6B52` trên `#E3F6EE`; nét `#0E9F78` | `#34D3A0` |
| Sát (hổ phách) | chữ `#8A5300` trên `#FFF2D9`; nét `#C98500` | `#F5B94A` |
| Hụt (san hô) | chữ `#B4233C` trên `#FFE9EC`; nét `#E5484D` | `#FF7A8A` |

  7 hũ: mỗi hũ một màu nhấn riêng (cách đều sắc độ, tránh trùng ba màu trạng thái) **và một biểu tượng riêng**, không dựa vào màu để phân biệt hũ. Màu hũ chỉ tô nền nhạt/mực nước, không tô số tiền.
- **Font**: Plus Jakarta Sans (biến thiên) toàn bộ; thang chữ gợi ý: số dư lớn 40/44 đậm 700 `tabular-nums`; tiêu đề màn 24/32; thân 16/24; chú thích 13/18 (không dưới 12).
- **Bo góc và phong cách thẻ**: thẻ 24px, sheet 28px phía trên, nút 16px (CTA chính dạng viên thuốc), chip tròn hoàn toàn; bóng đổ rất nhẹ, phân lớp bằng nền chứ không viền đậm; khoảng trắng rộng; không dùng gradient rực, chỉ dùng gradient mờ trên thẻ hũ.
- **Minh họa**: hũ SVG tự vẽ, đồng xu rơi; không dùng mascot hay tên/biểu tượng của MoMo hoặc app khác.
- **Giọng chữ**: tiếng Việt thân thiện, "bạn", câu ngắn, bắt đầu bằng việc có thể làm; thuật ngữ kỹ thuật giữ ở bảng "Vì sao".
- **Nhãn bắt buộc**: "Ví mô phỏng · dữ liệu minh họa", nhãn AI trên khối do AI sinh, "Điểm này không phải điểm tín dụng".

### 4.3. Bộ component dùng chung với khối UI của AI

Cấu trúc thư mục gợi ý (chỉ để định hướng, chưa tạo): `src/components/ui/` (shadcn), `src/components/blocks/` (khối dùng chung, mỗi khối một thư mục có `Component.tsx`, `schema.ts`, `fixtures.ts`), `src/lib/format.ts`, `src/lib/blocks/registry.ts`, `src/features/{home,jars,forecast,transfer,chat,onboarding,ingest}/`, `src/state/` (Zustand). Bảng ánh xạ khối ↔ component ở §3.8. **Mỗi khối có fixture** dùng cho MSW, kiểm thử và demo dự phòng tất định (proposal §13).

---

## 5. Điều chưa chắc / cần thử

Xếp theo mức rủi ro với 3 tuần:

1. **CORS và JWT từ trình duyệt tới AgentCore Runtime** (SSE qua `fetch`). Tài liệu cho thấy có thể thêm CORS middleware ở server runtime và dùng bearer JWT, nhưng tôi chưa kiểm cho runtime giao thức AG-UI. Nếu không được thì cần một lớp proxy; lớp đó **không** nên là route Next.js trên Amplify (streaming không hỗ trợ). Nên thử trong tuần 1. [TL một phần]
2. **Amplify build image và Node**: React Router 8 cần Node ≥ 22.22, Vite 8 cần ≥ 20.19/22.12; chưa kiểm Node mặc định của build image Amplify (cần ghim bằng `nvm` trong `amplify.yml`). Nếu vướng, hạ xuống React Router 7 (API declarative/data mode tương tự).
3. **Hiệu ứng "dịch chuyển" what-if trong Recharts** (nội suy khi đổi `data`, tô vùng giữa hai đường) và cách truyền dải `[p10,p90]` cho `Area`: chỉ thấy tên ví dụ, chưa chạy. Phương án B: SVG tự vẽ bằng `d3-shape` + Motion. **[Đã chạy thử 2026-11-21: xong, Recharts đủ dùng, không cần phương án B]** xem `spike-frontend-stack.md` §2.
4. **Base UI Drawer với `snapPoints` có nội dung cuộn bên trong** và trên iOS Safari/standalone (bàn phím, safe area). Bản Base của shadcn mới làm mặc định từ 07/2026, ít vết mòn hơn Radix. Nếu lỗi: dùng bản Radix (`init -b radix`) hoặc Dialog toàn màn hình. **[Đã chạy thử 2026-11-21: chạy được trên Chrome giả lập 390×844, còn thiếu iOS]** Drawer snap 0.6/1 mở được, nội dung chat cuộn bên trong bằng `message-scroller`. Nhưng với `snapPoints` popup cao 100dvh bị dịch xuống, ô nhập ở đáy nằm ngoài màn hình cho tới khi thêm `padding-bottom: var(--drawer-snap-point-offset)` lên chính popup (biến này không kế thừa xuống phần tử con). Chưa thử iOS Safari, bàn phím ảo, kéo tay thật.
5. **`web-haptics` trên iPhone**: README không nêu cơ chế iOS; Vibration API không có trên iOS [BV]. Xem là điểm cộng, không phụ thuộc.
6. **`@ag-ui/client` chạy trên trình duyệt?** Tài liệu `HttpAgent` không nói rõ; thiết kế dựa trên fetch + `Accept: text/event-stream` nhưng cần thử. Cũng chưa xác nhận Message Scroller của shadcn chạy mượt với luồng AG-UI tự dựng. **[Đã chạy thử 2026-11-21: được]** chạy trong Chrome 157 với mock SSE cục bộ (chưa thử header `Authorization`/JWT, chưa thử AgentCore thật); `message-scroller`, `bubble`, `trace` của shadcn ghép được với luồng chữ chạy dần và skeleton khi tool đang chạy. Xem `spike-frontend-stack.md` §5.
7. **React Router 8 + `<ViewTransition>`**: Back/Forward có thể không animate (tài liệu thừa nhận). Cần quyết định có chấp nhận hay đổi sang điều hướng bằng Navigation API.
8. **NumberFlow với VND** và với chữ "đ"/dấu trừ Unicode: chưa kiểm. **[Đã chạy thử 2026-11-21]** VND + `suffix` ổn; dấu trừ Unicode chỉ được dùng ở `format.ts` (không qua NumberFlow), chưa thử số âm trong NumberFlow.
9. **Hiệu năng trên điện thoại tầm trung thật**: tôi chưa chạy bất kỳ thứ gì; kích thước gói trong bảng là bundlephobia cho cả gói (chưa tree-shake). Cần đo thực tế bằng `vite build` + Lighthouse + CPU throttle. **[Đã chạy thử 2026-11-21: một nửa]** `vite build` đã đo: JS 386,9 KB gzip + CSS 17,9 KB gzip cho một chunk duy nhất, chưa tách chunk/lazy; vượt xa mức "đầu trang" nên cần `React.lazy`. Lighthouse, CPU throttle, điện thoại thật: chưa làm. Bảng theo gói ở `spike-frontend-stack.md` §8.
10. **Đẹp là chủ quan**: tôi chưa nhìn trực tiếp giao diện thật của Revolut, Monzo, N26, Wise, Copilot Money, MoMo, TNEX, Timo, Cake, ZaloPay; chưa đánh giá bằng mắt các font (chỉ kiểm cmap/GSUB), và chưa kiểm mù màu bằng công cụ mô phỏng. Bảng màu là đề xuất; độ tương phản đã tính nhưng cần xem trên màn hình thật ngoài nắng.
11. **Tailwind v4 yêu cầu Safari 16.4+**: máy giám khảo cũ hơn sẽ vỡ giao diện.
12. **Magic UI/Aceternity/Origin UI**: không xác minh được giấy phép từng component; không đưa vào stack.
13. **Hướng dẫn Next.js 16 trên Amplify** chỉ có bài của bên thứ ba cho static export; tài liệu AWS có thể chưa cập nhật; Next 16 SSR trên Amplify chưa được tôi thử.
14. **VietQR**: chưa đọc đặc tả NAPAS gốc; chỉ dùng QR giả cho mô phỏng.
15. **`zustand` 5.1.0 và `@hookform/resolvers` 7.0.8** là số phiên bản từ registry hôm nay; chưa kiểm tương thích chéo (Zod 4).

---

## 6. Nguồn (truy cập 2026-11-21)

**Tài liệu chính thức [TL]**
- Amplify hỗ trợ Next.js (đến 15, danh sách không hỗ trợ gồm streaming): https://docs.aws.amazon.com/amplify/latest/userguide/ssr-amplify-support.html
- Amplify SSR supported features (Node 20/22/24): https://docs.aws.amazon.com/amplify/latest/userguide/ssr-supported-features.html
- Amplify deployment specification (compute, 15 phút, 220 MB): https://docs.aws.amazon.com/amplify/latest/userguide/ssr-deployment-specification.html
- Amplify luật rewrite SPA: https://docs.aws.amazon.com/amplify/latest/userguide/redirect-rewrite-examples.html
- AgentCore AG-UI: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui.html ; CORS: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-tool-troubleshooting.html ; JWT bearer: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html
- Amplify Auth token: https://docs.amplify.aws/react/build-a-backend/auth/concepts/tokens-and-credentials/ ; đăng nhập: https://docs.amplify.aws/react/build-a-backend/auth/connect-your-frontend/sign-in/
- Next.js static exports: https://nextjs.org/docs/app/guides/static-exports ; PWA: https://nextjs.org/docs/app/guides/progressive-web-apps
- React 19.3 (ViewTransition stable): https://react.dev/blog/2026/09/09/react-19-3 ; tham chiếu: https://react.dev/reference/react/ViewTransition
- React Router: modes https://reactrouter.com/start/modes ; nâng cấp v8 https://reactrouter.com/upgrading/v7 ; view transitions https://reactrouter.com/how-to/view-transitions
- shadcn/ui: changelog https://ui.shadcn.com/docs/changelog ; Base UI mặc định https://ui.shadcn.com/docs/changelog/2026-07-base-ui-default ; chat https://ui.shadcn.com/docs/changelog/2026-06-chat-components ; AI Elements https://ui.shadcn.com/docs/ai-elements ; Questionnaire https://ui.shadcn.com/docs/changelog/2026-08-questionnaire ; Drawer (Base) https://ui.shadcn.com/docs/components/base/drawer ; Chart https://ui.shadcn.com/docs/components/radix/chart ; MCP https://ui.shadcn.com/docs/mcp ; Vite https://ui.shadcn.com/docs/installation/vite ; component list https://ui.shadcn.com/docs/components
- Base UI Drawer: https://base-ui.com/react/components/drawer
- Tailwind: compatibility https://tailwindcss.com/docs/compatibility ; container queries https://tailwindcss.com/docs/responsive-design
- Recharts: release 3.11.0 https://github.com/recharts/recharts/releases ; ví dụ https://recharts.github.io/en-US/examples/
- Motion: https://motion.dev/docs/react ; kích thước https://motion.dev/docs/react-reduce-bundle-size ; reduced motion https://motion.dev/docs/react-accessibility
- NumberFlow: https://number-flow.barvian.me/
- web-haptics: https://github.com/lochie/web-haptics ; README https://raw.githubusercontent.com/lochie/web-haptics/main/packages/web-haptics/README.md
- HeroUI: https://www.heroui.com/docs/react/getting-started ; Konsta UI: https://konstaui.com/react ; Tremor: https://tremor.so ; Magic UI: https://magicui.design/docs
- AG-UI HttpAgent: https://docs.ag-ui.com/sdk/js/client/http-agent
- vite-plugin-pwa: https://vite-pwa-org.netlify.app/guide/
- WCAG 2.2: https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html ; https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html
- MoMo hướng dẫn chuyển tiền: https://www.momo.vn/huong-dan/huong-dan-chuyen-tien-bang-vi-momo
- Monzo, "Delightful Payments": https://monzo.com/blog/delightful-payments/
- Revolut 7.0: https://www.revolut.com/blog/post/introducing-revolut-7-0/
- Apple, Copilot Money: https://developer.apple.com/articles/copilot-money

**Blog, bài báo, nguồn thứ cấp [BV]**
- Next.js 16 static export lên Amplify: https://dev.to/u11d/how-to-deploy-nextjs-16-ssg-to-aws-amplify-complete-guide-5g9j
- re:Post streaming trên Amplify (bị 403, chỉ có tóm tắt tìm kiếm): https://repost.aws/questions/QU5WPXEy6YSaCVXz6W73nCvg/why-doesnt-streaming-readable-stream-work-for-next-js-api-routes-on-aws-amplify-hosting
- iOS PWA: https://firt.dev/notes/pwa-ios/ ; iOS 26 mở mọi trang như web app: https://www.idownloadblog.com/?p=1042117 ; https://heise.de/-10749652
- Monzo Pots (diễn đàn): https://community.monzo.com/t/we-ve-shipped-pot-to-pot-transfers/148972
- N26: https://n26.com/en-de/blog/building-a-simple-flexible-banking-experience
- Wise: https://raw.studio/blog/how-wise-uses-3-transparency-first-ux-principles/
- Cash App/Wise tổng hợp: https://www.lazarev.agency/articles/best-fintech-apps
- Lo âu tài chính: https://uxmag.com/articles/designing-effective-experiences-for-financial-services ; https://finextra.com/blogposting/25955/money-is-about-emotions-dont-let-financial-services-ruin-lives
- Trực quan hóa bất định: https://moodle2.units.it/pluginfile.php/466375/mod_resource/content/0/Uncertainty_Visualization_Padilla_Kay_Hullman_2020.pdf ; https://data.europa.eu/apps/data-visualisation-guide/frequencies ; https://www.osti.gov/pages/servlets/purl/2311603
- VietQR: https://www.pkgstats.com/pkg:vietqr-ts ; https://english.vtv.vn/news/napas-unveils-unified-qr-code-system-for-bank-transfers-2021062123463189.htm

**Kiểm tra trực tiếp [KT] (2026-11-21)**
- npm registry (`registry.npmjs.org/<gói>`): phiên bản, ngày phát hành, giấy phép, peerDependencies của mọi gói trong bảng §3.1.
- bundlephobia (`bundlephobia.com/api/size`): kích thước cả gói.
- Google Fonts metadata (`fonts.google.com/metadata/fonts`) và file TTF từ `fonts.googleapis.com/css2`: subset `vietnamese`, cmap, GSUB, độ rộng chữ số.
- Node 24.15 / ICU 78.2: `Intl.NumberFormat`, `DateTimeFormat`, `RelativeTimeFormat` cho `vi-VN`.
- Tính độ tương phản WCAG cho các cặp màu ở §3.7 và §4.2 (công thức luminance WCAG 2.x).
