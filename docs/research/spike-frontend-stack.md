# Spike: stack frontend Yofina Foresight có dựng và chạy được không

> Chạy ngày 2026-11-21 trên Windows 11, Node v24.15.0, npm 11.14.1, Chrome 157.0.8103.79. Mã nằm ở `spikes/frontend-stack/` (README ở đó có lệnh chạy lại). Ảnh chụp ở `docs/research/assets/frontend-spike/`. Đây là **bản thử, không phải app thật**; dữ liệu dự báo là số giả sinh trong code (không phải kết quả ML).
>
> Nhãn: **[Đã chạy]** tôi chạy và thấy kết quả (lệnh hoặc ảnh kèm theo). **[Suy luận]** chưa chạy, chỉ là nhận định.

---

## 0. Phiên bản thực cài (từ `npm ls`)

| Gói | Phiên bản | Ghi chú |
|---|---|---|
| `create-vite` | 9.3.4 | mặc định `typescript ~7.0.2`, `oxlint 1.94.0`, `@vitejs/plugin-react 6.3.0` |
| `vite` | 8.3.8 | engines `^20.19 \|\| >=22.12` |
| `react`, `react-dom` | 19.3.1 | |
| `typescript` | 7.0.2 | `tsc -b` chạy được |
| `tailwindcss`, `@tailwindcss/vite` | 4.3.5 | |
| `shadcn` (CLI + gói runtime) | 4.23.0 | engines `>=20.18.1` |
| `@base-ui/react` | 1.9.0 | engines `>=14` |
| `@shadcn/react` | 0.3.1 | do `message-scroller` kéo vào |
| `cn` | 0.5.2 | component shadcn import `cn` từ gói này |
| `tw-animate-css`, `class-variance-authority`, `lucide-react` | 1.4.0, 0.7.1, 1.77.0 | |
| `recharts` | 3.11.0 | `shadcn add chart` tự cài 3.8.0, phải nâng tay (xem §1) |
| `motion` | 14.14.0 | |
| `@number-flow/react` | 0.6.2 | |
| `@ag-ui/client` (+ `core`, `encoder`, `proto`) | 1.0.5 | giấy phép MIT; peer `zod ^3.25.18 \|\| ^4`; phụ thuộc `rxjs 7.8.1`, `fast-json-patch`, `@bufbuild/protobuf 2.17.0` |
| `zod` | 4.6.7 | |
| `@fontsource-variable/plus-jakarta-sans` | 5.3.0 | |
| `d3-shape`, `@types/d3-shape` | 3.2.1, 3.2.0 | chỉ cài; app chưa dùng (sparkline chưa làm) |
| `playwright` | 1.65.1 | dùng Chrome có sẵn qua `channel: 'chrome'`, không tải chromium |

Yêu cầu Node (tra `npm view <gói> engines`): `react-router@8.5.2` cần `>=22.22.0` (**không cài**, chỉ tra); `vite` và `@vitejs/plugin-react` cần `^20.19 || >=22.12`; `shadcn` `>=20.18.1`; `recharts` `>=18`; `typescript 7.0.2` `>=16.20`. Các gói còn lại không khai engines. Đĩa: trước 15 GB trống, sau khi cài còn khoảng 12 GB (không tải chromium).

`npm audit` báo 4 lỗ hổng mức moderate (gói `minimatch`, qua phụ thuộc gián tiếp). Chưa tìm xem nó đến từ gói nào.

---

## 1. Dựng project (Vite + React + TS + Tailwind 4 + shadcn)

**Cách thử.** `npm create vite@9.3.4 . -- --template react-ts --no-interactive --no-immediate`, `npm install`, `npm install tailwindcss @tailwindcss/vite`, sửa `vite.config.ts` (thêm plugin tailwind và alias `@`), thêm `paths` vào `tsconfig.json` và `tsconfig.app.json`, rồi shadcn.

**Kết quả [Đã chạy].**

- Vite/Tailwind dựng ngay, `npm run build` chạy được lần đầu với TypeScript 7.
- **shadcn init không tương tác:** `npx shadcn@4.23.0 init -t vite -b base -p nova --yes --force` chạy xong, exit 0.
  - Có `--yes` mà thiếu `-p` thì vẫn hiện menu chọn preset (Nova, Vega, Maia, Lyra, Mira, Luma, Sera, Rhea, Custom); chạy với stdin rỗng thì thoát code 0 mà không cài gì (dễ tưởng đã thành công).
  - `-p base-nova` bị từ chối: "Invalid preset … Available presets: nova, vega, maia, lyra, mira, luma, sera, rhea". `--defaults` ép `--template=next`.
  - `-b` nhận `base`, `radix`, `aria` (`aria` không có trong ghi chú cũ, tôi không thử).
  - CLI kiểm alias `@/*` trong tsconfig trước ("Validating import alias") nên phải cấu hình trước khi init.
- Cái init sinh ra: `components.json` với `style: base-nova`, `src/lib/utils.ts`, `button.tsx`, ghi đè `index.css` (Tailwind 4 `@theme inline`, màu OKLCH, `@import "shadcn/tailwind.css"`, font **Geist** mặc định).
- **Khác ghi chú:**
  1. Các file shadcn import `cn` từ gói `cn@0.5.2` (không phải `@/lib/utils`), `src/lib/utils.ts` vẫn được tạo.
  2. Font mặc định là Geist; ghi chú cũ đã nói Geist thiếu `₫`, nên phải đổi sang Plus Jakarta Sans (làm xong, xem §6).
  3. Preset `nova` làm nút rất nhỏ (`h-8`, `sm` là `h-7`), radius 0.625rem: không đủ vùng chạm cho điện thoại, phải ghi đè bằng `className` (tôi dùng `h-11`/`h-12`).
  4. `shadcn add chart` ghi `recharts@^3.8.0` và lockfile ra 3.8.0, dù 3.11.0 là bản mới nhất; phải `npm i recharts@latest`. Sau khi nâng, `chart.tsx` vẫn qua `tsc`, nhưng **app không dùng `ChartContainer`**: tôi dùng Recharts trực tiếp, nên tương thích runtime của wrapper shadcn với 3.11 là **chưa thử**.
- **Component đã thêm** (`npx shadcn@4.23.0 add … --yes`): `button`, `card`, `drawer`, `tabs`, `input`, `skeleton`, `badge`, `chart`; chat: `message`, `message-scroller`, `bubble`, `trace` (kéo thêm `collapsible`). Tất cả là **Base UI** (không phải Radix): `drawer.tsx` import `@base-ui/react/drawer`, `tabs` dùng `TabsPrimitive.Panel`.
- **AI Elements** (Prompt Input, Confirmation, Reasoning, Suggestion…): tôi tìm trong registry `@shadcn` với các từ khóa `prompt`, `confirmation`, `reasoning`, `suggestion`: không thấy. Chỉ thấy `message`, `message-scroller`, `bubble`, `trace` (và ví dụ của chúng). Chưa kiểm xem AI Elements nằm ở registry khác.

---

## 2. Biểu đồ dự báo (Recharts 3.11.0)

**Cách thử.** `src/components/ForecastChart.tsx`: dòng thời gian số dư một hũ 30 ngày, dữ liệu giả `src/lib/forecast-data.ts` (dạng `date/p10/p50/p90` giống §9.4 tài liệu agentic-ui).

**Kết quả [Đã chạy]**, ảnh: `home-light-forecast.png`, `home-light-forecast-readout.png`, `whatif-light-mid.png`, `whatif-light-after.png` (và bản `dark`).

- `Area` nhận `dataKey` trả về mảng `[p10, p90]` và **vẽ đúng dải** (không cần thủ thuật `baseValue`).
- `Line` P50, `ReferenceLine` dọc ngày lương (xanh, nét đứt) và ngày đến hạn (hổ phách), `ReferenceLine y=0`, `ReferenceDot` ở ngày cạn, `ReferenceArea` + `<pattern>` SVG cho vùng hụt gạch chéo (từ ngày cạn tới ngày lương): tất cả chạy.
- **What-if hai dải có animation chuyển: chạy.** Hai `Area` cùng vẽ: dải xám "trước" tĩnh, dải chàm "sau" có `isAnimationActive`. Khi bấm nút (đổi `data`), Recharts tự nội suy cả dải lẫn đường P50. Ảnh `whatif-light-mid.png` (chụp 260 ms sau khi bấm) có dải nằm giữa vị trí cũ và mới. Không cần visx hay d3-shape cho biểu đồ này.
- Dòng đọc cố định phía trên biểu đồ (thay tooltip): `onMouseMove` nhận `activeTooltipIndex`; chạm bằng Playwright `touchscreen.tap` ra dòng "5/12 · giữa 3,3 triệu · khoảng 80% khả năng từ 3 triệu đến 3,6 triệu".
- **Những chỗ phải vá** (lần vẽ đầu chưa đẹp):
  1. `tickCount={5}` cho trục Y ra các mốc lệch nhau (4tr, 3tr, 1tr…): chuyển sang tự tính `ticks` theo bước 0,5/1/2 triệu.
  2. Nhãn mốc dùng `insideTopLeft/Right` chồng chữ "Tiền điện 26/11" lên "Lương 5/12": đổi `position: 'top'`, thêm viền chữ (halo) bằng `paintOrder: stroke`.
  3. Chấm "cạn" đặt ở `y=0` tại ngày đầu tiên P50 ≤ 0 thì lệch khỏi đường: nội suy điểm cắt giữa hai ngày.
  4. Chạm vào biểu đồ hiện khung focus xanh: ẩn bằng CSS `.recharts-surface:focus { outline: none }`.
  5. Nhãn trục X cuối ("21/12") bị cắt: tăng lề phải.
- **Chưa kiểm:** chỉ hũ Ăn uống được xem bằng mắt; hai hũ còn lại (Đi lại, Giải trí) chỉ có dữ liệu và không có ảnh. Hiệu năng animation trên điện thoại thật: chưa. Nhãn chạy dưới 30 ngày hoặc trường hợp dải rất rộng: chưa.

---

## 3. Component tự vẽ SVG

**Kết quả [Đã chạy].**

- `JarGlass.tsx`: hũ thủy tinh, nước là `clipPath` + đường sóng tĩnh, mực nước đổi bằng `motion.g` (spring), vạch nét đứt "dự báo" kèm nhãn. Ảnh: `home-light-top.png` (hai hũ trong dải cuộn), `blocks-light.png`.
- `ResilienceGauge.tsx`: cung nửa vòng 0–100 (nền xám, đầu chạy tô gradient san hô → hổ phách → teal), núm tròn, số lớn bằng NumberFlow, nhãn "Tạm ổn", bốn thanh Tiết kiệm/Chi tiêu/Vay nợ/Kế hoạch bằng HTML/CSS, dòng "Điểm này không phải điểm tín dụng". Nút "Mất việc 2 tháng?" đổi điểm 68 → 41 để thử animation (chưa chụp riêng trạng thái 41). Ảnh: `home-light-full.png`, `home-dark-full.png`.
- Sai sót đã sửa sau khi nhìn ảnh: nhãn "0" và "100" đè lên đầu cung (mở rộng viewBox); lớp "kính" trắng làm hũ ở chế độ tối bị xám (giảm độ đục).
- Sóng nước **không** tự động chuyển động (chỉ mực nước chuyển bằng spring).

---

## 4. Khối UI từ JSON (Zod + registry)

**Cách thử.** `src/blocks/schemas.ts` (`z.discriminatedUnion('type', [...])` cho `forecast_timeline`, `jar_summary`, `affordability_card`, `confirm`, với phong bì `v/id/trace_id/fallback_text` theo §5.1 tài liệu agentic-ui), `registry.tsx` (type → `{schema, Component}`), `fixtures.ts` (4 khối hợp lệ + 1 `type` lạ + 1 khối sai schema).

**Kết quả [Đã chạy].**

- Trong Node (`node scripts/check-blocks.ts`, Node 24 chạy thẳng file `.ts`): 4 khối hợp lệ qua cả union và schema registry; `hologram_3d` bị union từ chối, registry không có schema; `jar_summary` có `balance_vnd` là chuỗi bị từ chối.
- Trong trình duyệt: `BlockRenderer` gặp `type` lạ hoặc `safeParse` hỏng thì hiển thị `FallbackBlock` với `fallback_text` của chính khối và dòng nhỏ ("Cập nhật ứng dụng để xem đầy đủ" / "Không hiển thị được khối này"), trang không vỡ, `console.warn` ghi lỗi Zod. Ảnh: `blocks-light.png` (trang `?blocks`), `chat-light-bottom.png` (cùng việc trong chat).
- Trong luồng chat thật: 6 khối đến, kết quả DOM: `custom:forecast_timeline`, `activity:affordability_card`, `activity:jar_summary`, `custom:fallback:unknown_type`, `activity:fallback:invalid_schema`, `custom:confirm`.
- Error boundary bao từng khối có mặt trong mã nhưng **chưa được thử** (chưa có khối nào ném lỗi lúc render).
- Ghi chú thiết kế: dùng `z.discriminatedUnion` cho cả mảng sẽ làm hỏng cả tin nhắn nếu một khối lạ; đã phân tích theo từng khối bằng registry (đúng tinh thần "khối lạ không được làm hỏng cả tin nhắn" ở §5.2). Union vẫn dùng để suy `type Block`.

---

## 5. `@ag-ui/client` trong trình duyệt + mock server SSE

**Cách thử.** `src/agui/useYofinaChat.ts` (client mỏng) và `mock-server/server.mjs` (Node `http`, cổng 8787, CORS bật, `Content-Type: text/event-stream`, mỗi event một dòng `data: {json}`).

**Kết quả [Đã chạy].**

- **Bundle được cho trình duyệt: có.** `import { HttpAgent, type AgentSubscriber } from '@ag-ui/client'` build bằng Vite 8 (Rolldown) không cần cấu hình thêm, không cần polyfill. Chi phí: nhóm `@ag-ui/*` + rxjs + protobuf ~52,7 KB gzip, cộng Zod 26,2 KB (Zod là peer dependency, dùng chung với schema khối). Gói kéo cả `@ag-ui/proto`/`@bufbuild/protobuf` dù ta chỉ dùng SSE JSON; `package.json` khai `sideEffects: false` nhưng phần protobuf vẫn vào bundle (không thử cắt).
- **API ở bản hiện hành (1.0.5):** `new HttpAgent({ url, headers?, threadId?, fetch? })`; `agent.addMessage({id, role, content})`; `agent.runAgent(params, subscriber)` (subscriber theo lượt chạy) hoặc `agent.subscribe(subscriber)` (cố định); `agent.abortRun()`. `AgentSubscriber` có callback riêng cho từng event: tôi dùng `onTextMessageStartEvent/ContentEvent/EndEvent` (nhận sẵn `textMessageBuffer`), `onToolCallStartEvent/EndEvent` (`toolCallName`, `toolCallArgs` đã parse), `onToolCallResultEvent`, `onCustomEvent`, `onActivitySnapshotEvent`, `onRunErrorEvent`, `onRunFailed`, `onEvent`. `RunFinished` có `outcome` (`success`/`interrupt`/`cancelled`); không dùng trong spike này. `HttpAgent` POST body `RunAgentInput` (JSON) và đọc luồng SSE; preflight OPTIONS do server mock trả lời (cho phép `content-type`, `authorization`, `accept`).
- **Dãy event mock phát** (ghi lại từ `window.__aguiEvents` trong Chrome): `RUN_STARTED` → `TEXT_MESSAGE_START/CONTENT×N/END` → `TOOL_CALL_START/ARGS×2/END` → (chờ 1,6 s) `TOOL_CALL_RESULT` → `CUSTOM` (khối forecast) → text → tool thứ hai → `TOOL_CALL_RESULT` → `ACTIVITY_SNAPSHOT×3` + `CUSTOM` → `ACTIVITY_SNAPSHOT` → `CUSTOM` → text → `RUN_FINISHED`. Không có lỗi trong console ngoài các cảnh báo cố ý của khối sai schema.
- **`CUSTOM` và `ACTIVITY_SNAPSHOT` đều là kiểu có trong SDK** (`EventType.CUSTOM`, `EventType.ACTIVITY_SNAPSHOT`) và cả hai đưa được khối vào registry: `CUSTOM {name:'yofina.block', value}` và `ACTIVITY_SNAPSHOT {messageId, activityType:'yofina.block', content, replace:true}`. Gửi lại `ACTIVITY_SNAPSHOT` cùng `messageId` thì khối được thay tại chỗ (jar_summary Giải trí → Ăn uống chỉ còn một thẻ). Lưu ý: việc "thay tại chỗ" trên giao diện là do hàm `upsert` của tôi khóa theo `messageId`; tôi không kiểm cách SDK hợp nhất message trong `agent.messages`.
- **Chữ chạy dần:** hiện từng từ kèm con trỏ nhấp nháy (`chat-light-streaming.png`). **Skeleton khi tool chạy:** dòng `Trace` (shimmer) "Đang đọc dự báo hũ Ăn uống…" + khung xám cao đúng bằng khối forecast (`chat-light-skeleton.png`). Hai thứ này đúng ý §5.4 tài liệu agentic-ui.
- **Chưa thử:** header `Authorization`/JWT, `abortRun`, kết nối lại, `RUN_FINISHED` với `interrupt` + `resume`, event không hợp lệ (SDK có bước "enforcement" kiểm event, tôi chỉ gửi event hợp lệ), WebSocket, proto, AgentCore thật, CORS thật.

---

## 6. Màn hình mobile 390×844

**Kết quả [Đã chạy]**, ảnh: `home-light-top.png`, `home-light-full.png`, `home-dark-top.png`, `home-dark-full.png`, `chat-*-open.png`, `chat-*-blocks.png`.

- Một trang ghép: header, thẻ số dư chàm với hành động nhanh (5 nút), câu "nhìn trước", ba thẻ hũ (dải cuộn ngang, `snap`), thẻ "Nhìn trước 30 ngày" (Tabs chọn hũ + biểu đồ + nút what-if), gauge điểm chống chịu, thanh tab dưới 5 mục với nút giữa nổi mở bottom sheet chat.
- **Bottom sheet** = shadcn Drawer (Base UI), `snapPoints={[0.6, 1]}`, tự chuyển lên 1 khi gửi tin. Hai phát hiện: (a) popup bị giới hạn `max-height: calc(100dvh - 6rem)` (748 px ở 844 px) và dịch xuống theo snap, nên ô nhập ở đáy rơi ngoài màn hình; (b) biến `--drawer-snap-point-offset` nằm trên chính popup và **không kế thừa** xuống phần tử con (tính được `padding-bottom: 0` ở phần tử con dù popup có 241,6 px). Cách sửa: `pb-[var(--drawer-snap-point-offset,0px)]` đặt lên `DrawerContent`.
- **Bản sắc:** nền kem `#F6F5F1`, chàm `#4338CA`, hũ/ba trạng thái teal/hổ phách/san hô kèm biểu tượng và chữ, bo 24–28 px, nút giữa nổi. Token trong `src/index.css`, chế độ tối dùng bảng màu của ghi chú.
- **Font:** `@fontsource-variable/plus-jakarta-sans` 5.3.0 tự host. Build ra ba file woff2 theo subset (`vietnamese` 8,35 KB, `latin-ext` 21,7 KB, `latin` 27,3 KB), chỉ tải subset cần; **dấu tiếng Việt hiển thị đúng** ở mọi ảnh ("Hũ", "Ăn uống", "Cạn sớm", "Tiết kiệm", "Chuyển tiền", "ơ", "ữ", "ệ"), ký hiệu `₫` hiện đúng; số dùng `tabular-nums`.
- **Định dạng VND** (`src/lib/format.ts`, chạy bằng `node scripts/check-format.ts`): `formatVND(1200000)` = "1.200.000 ₫" (NBSP trước `₫`), `formatVND(-120000)` = "−120.000 ₫", `formatVNDShort(1200000)` = "1,2 triệu", `950000` → "950 nghìn", `1500000000` → "1,5 tỷ", `1250000` → "1,3 triệu" (làm tròn 1 chữ số), trục biểu đồ "500k", "−1,2tr". Tôi chọn `₫` thay vì "đ" ghi chú gợi ý: hiển thị ổn với Plus Jakarta Sans; quyết định cuối thuộc về chủ dự án.
- **Đánh giá bằng mắt, trung thực:**
  - Tốt: thẻ số dư, thẻ hũ và biểu đồ có bố cục sạch, dấu tiếng Việt rõ, số lớn dễ đọc, mã hóa ba lớp (màu + biểu tượng + chữ) cho trạng thái; bản tối ổn; biểu đồ có dải mờ, mốc rõ.
  - Chưa đẹp/chưa đủ: bố cục vẫn "app web dựng bằng shadcn" hơn là một thương hiệu: icon lucide mặc định, thẻ trắng bo tròn như nhau, thiếu minh họa riêng và chuyển động có chủ đích ngoài số tiền và nước. Hũ thủy tinh còn đơn giản (nhìn như hộp nhựa, chưa ra "hũ thủy tinh"). Biểu đồ vẫn hơi dày chữ ở mép (nhãn "Cạn ~29/11" chồng lên dải). Gauge dùng gradient ba màu, hơi sặc sỡ so với yêu cầu "không tô đỏ chói". Chưa có minh họa, đồng xu rơi hay các micro-interaction mà ghi chú đề xuất.
  - Đã sửa sau khi nhìn ảnh (lần chụp đầu): thẻ hũ đầu tiên dính mép trái (`scroll-px-4`), số dư đè lên dòng "Ví mô phỏng", nhãn "Chuyển tiền" xuống hàng, nhãn biểu đồ chồng nhau, trục Y lệch, gauge đè chữ, ô nhập chat mất ở snap 0.6, thẻ khối trong chat trắng trên nền trắng (đổi nền sheet sang kem) và viền thẻ bị `content-visibility:auto` của `MessageScrollerItem` cắt cụt góc (thêm đệm).
  - Ảnh `fullPage` có thanh tab dưới xuất hiện giữa trang: đó là hiện tượng của chụp toàn trang với phần tử `fixed`, không phải lỗi giao diện; ảnh viewport thể hiện đúng.

---

## 7. Animation (Motion + NumberFlow)

**Kết quả [Đã chạy].** Motion 14.14.0 và `@number-flow/react` 0.6.2 cài và chạy với React 19.3.1 (StrictMode bật), không lỗi console.

- NumberFlow: số dư tổng "12.480.000 ₫" → bấm "Tiền vào" → "27.480.000 ₫": các chữ số cuộn (ảnh `numberflow-mid.png`: hàng đầu đang cuộn qua "26"; `numberflow-after.png`). `locales="vi-VN"` cho dấu chấm nhóm nghìn; ký hiệu tiền phải tự cấp bằng `suffix`. Còn dùng cho điểm gauge, số ngày còn lại, số trong khối `confirm`.
- Motion: spring cho mực nước hũ, `strokeDashoffset` cho cung gauge, núm gauge, thanh thành phần, `<MotionConfig reducedMotion="user">` bọc app.
- Chưa thử: `LazyMotion`/`m` (bundle Motion vẫn là bản đầy đủ ~46,6 KB gzip, khớp con số ~43 KB ghi chú), `<ViewTransition>` của React 19.3, React Router (chưa cài), hiệu năng trên máy tầm trung, haptic.

---

## 8. Build và kích thước

`npm run build` (= `tsc -b && vite build`) thành công, ~0,6–0,9 s. [Đã chạy]

| Tệp | Kích thước | Gzip |
|---|---|---|
| `index-*.js` (một chunk) | 1.332,9 KB | **386,9 KB** |
| `index-*.css` | 93,4 KB | **17,9 KB** |
| `index.html` | 0,5 KB | 0,3 KB |
| Font woff2 (3 subset, không nén thêm) | 8,4 + 21,7 + 27,3 KB | tải theo subset |

Vite cảnh báo chunk >500 KB (chưa tách chunk, chưa `lazy`).

**Phân rã theo nhóm gói** (build riêng bằng `vite.analyze.config.ts`, có minify, mỗi nhóm một chunk; tổng gzip các chunk ≈ 386,8 KB, khớp bản thật; ranh giới nhóm là ước lượng của tôi):

| Nhóm | Gzip |
|---|---|
| Recharts + d3 + `@reduxjs/toolkit`/immer/es-toolkit/decimal.js | **118,1 KB** |
| `react` + `react-dom` | 64,8 KB |
| `@ag-ui/*` + rxjs + fast-json-patch + protobuf | 52,7 KB |
| Motion (`motion`, `motion-dom`, `framer-motion`) | 46,6 KB |
| Base UI + `@shadcn/react` | 40,3 KB |
| Zod 4.6.7 | 26,2 KB |
| Mã app + phần lẻ | 17,9 KB |
| `cn` + `lucide-react` + cva | 14,6 KB |
| NumberFlow | 5,7 KB |
| Runtime bundler | 0,4 KB |

Nhận xét [Suy luận từ số đo]: 387 KB JS gzip cho một trang là nặng cho mạng di động chậm; phần lớn thuộc về Recharts (118 KB) và React (65 KB). Cách giảm hợp lý: `React.lazy` cho biểu đồ và chat (cả hai không cần ở lần tải đầu), `LazyMotion`, bỏ protobuf nếu cắt được. Chưa làm và chưa đo lại.

---

## 9. Nhìn bằng mắt (ảnh chụp)

Playwright 1.65.1 + Chrome 157 (`channel: 'chrome'`), khổ 390×844, `deviceScaleFactor: 2`, `isMobile`, `hasTouch`, sáng và tối, đọc bằng `Read` rồi sửa lỗi (xem §6). Chạy qua `npm run build` + `vite preview`. Ảnh nhúng (đường dẫn tương đối từ `docs/research/`):

| Cảnh | Sáng | Tối |
|---|---|---|
| Trang chủ (đầu trang) | ![](assets/frontend-spike/home-light-top.png) | ![](assets/frontend-spike/home-dark-top.png) |
| Biểu đồ dự báo | ![](assets/frontend-spike/home-light-forecast.png) | ![](assets/frontend-spike/home-dark-forecast.png) |
| Chạm để đọc số từng ngày | ![](assets/frontend-spike/home-light-forecast-readout.png) | ![](assets/frontend-spike/home-dark-forecast-readout.png) |
| What-if, giữa animation (260 ms) | ![](assets/frontend-spike/whatif-light-mid.png) | ![](assets/frontend-spike/whatif-dark-mid.png) |
| What-if, sau animation | ![](assets/frontend-spike/whatif-light-after.png) | ![](assets/frontend-spike/whatif-dark-after.png) |
| Chat mở ở snap 0.6 | ![](assets/frontend-spike/chat-light-open.png) | ![](assets/frontend-spike/chat-dark-open.png) |
| Chữ chạy dần | ![](assets/frontend-spike/chat-light-streaming.png) | ![](assets/frontend-spike/chat-dark-streaming.png) |
| Skeleton khi tool chạy | ![](assets/frontend-spike/chat-light-skeleton.png) | ![](assets/frontend-spike/chat-dark-skeleton.png) |
| Khối render từ JSON trong chat | ![](assets/frontend-spike/chat-light-blocks.png) | ![](assets/frontend-spike/chat-dark-blocks.png) |
| Khối cuối: fallback + confirm | ![](assets/frontend-spike/chat-light-bottom.png) | ![](assets/frontend-spike/chat-dark-bottom.png) |
| Trang khối UI từ JSON (`?blocks`) | ![](assets/frontend-spike/blocks-light.png) | ![](assets/frontend-spike/blocks-dark.png) |
| Cả trang | ![](assets/frontend-spike/home-light-full.png) | ![](assets/frontend-spike/home-dark-full.png) |
| NumberFlow giữa chừng / sau | ![](assets/frontend-spike/numberflow-mid.png) ![](assets/frontend-spike/numberflow-after.png) | |

Tôi đã xem trực tiếp (bằng `Read`) các ảnh sáng: home-top, home-forecast, home-forecast-readout, whatif-mid/after, chat-open/skeleton/streaming/blocks/bottom, blocks, home-full, numberflow; và các ảnh tối: home-full, chat-bottom. Các ảnh tối còn lại được sinh bằng cùng mã và cùng script nhưng **tôi không xem từng ảnh**.

---

## Kết luận: stack này có nên chốt không

**Nên chốt phần lõi, kèm các điều chỉnh sau** (kết luận của tôi từ bằng chứng trên, chủ dự án quyết).

1. **Vite + React 19.3 + TypeScript + Tailwind 4 + shadcn (Base UI) dựng và chạy được**; không có vật cản kỹ thuật nào ở §1–§8. Không cần Next.js cho phần client đã thử. (Hosting Amplify chưa thử.)
2. **Recharts 3.11 đủ cho fan chart + what-if** (dải `[p10,p90]`, mốc, vùng hụt, animation chuyển). Giữ làm chính; không cần visx/d3-shape cho cái này. Giá phải trả là ~118 KB gzip: dùng `React.lazy`.
3. **`@ag-ui/client` dùng được trong trình duyệt** với client mỏng (HttpAgent + subscriber), khối UI đi qua `CUSTOM` hoặc `ACTIVITY_SNAPSHOT` đều được. Nên chọn một: `ACTIVITY_SNAPSHOT` với `messageId` ổn định khớp thiết kế "thay khối tại chỗ" ở tài liệu agentic-ui và có sẵn kiểu trong SDK. `CUSTOM` nên để cho tín hiệu phụ.
4. **Registry + Zod + fallback chạy đúng yêu cầu** (khối lạ/hỏng không làm vỡ trang), nhưng cần phân tích theo từng khối, không `parse` cả mảng bằng một union.
5. **Cần đổi/chuẩn bị:**
   - Thêm `-p nova` (hoặc preset khác) vào lệnh `shadcn init` trong kế hoạch; ghi `cn` và `recharts@latest` vào hướng dẫn dựng.
   - Đổi font Geist mặc định sang Plus Jakarta Sans (đã làm); ghi đè kích thước nút/ô nhập cho cảm ứng (mặc định nova quá nhỏ).
   - Với Drawer snap points, thêm padding đáy bằng `--drawer-snap-point-offset`; kiểm lại trên iOS thật.
   - Bundle: tách chunk, `lazy` biểu đồ/chat, cân nhắc `LazyMotion`.
   - "Đẹp" chưa đạt: cần một vòng thiết kế thật (minh họa hũ, icon riêng, chuyển động) trước khi tuyên bố "đẹp hơn mặc định shadcn". Spike này chỉ chứng minh stack làm được, không chứng minh gu thẩm mỹ.
6. **Không thử, vẫn mở:** React Router 8 (chỉ tra engines Node ≥ 22.22) và `<ViewTransition>`, `web-haptics`, `LazyMotion`, shadcn `ChartContainer`/Questionnaire/AI Elements.

## Điều vẫn chưa thử được

- **Điện thoại thật** (iOS Safari, Android Chrome): vuốt Drawer, bàn phím ảo và safe area, PWA cài lên màn hình chính, hiệu năng/animation trên máy tầm trung, Lighthouse, CPU throttle, haptic. Spike chỉ chạy Chrome desktop giả lập khổ 390×844.
- **Amplify Hosting**: build image, phiên bản Node, rewrite SPA, deploy.
- **Backend thật**: AgentCore Runtime (CORS, JWT/Authorization từ trình duyệt, SSE qua mạng thật, độ trễ), Strands + adapter AG-UI, interrupt/resume cho khối `confirm` (hiện chỉ đổi trạng thái cục bộ).
- Hai hũ còn lại của biểu đồ (chưa xem bằng mắt), số âm trong NumberFlow, error boundary của khối, event AG-UI không hợp lệ, `abortRun`.
- Trình duyệt khác (Safari/Firefox) và máy cũ hơn iOS 16.4 (Tailwind 4).
