# Spike: stack frontend Yofina Foresight (2026-11-21)

Bản THỬ để lấy bằng chứng cho `docs/research/frontend-fintech-ui.md`. Không phải app thật. Dữ liệu hư cấu. Kết quả đầy đủ: `docs/research/spike-frontend-stack.md`.

## Chạy lại

Yêu cầu: Node >= 22.12 (đã thử với Node 24.15, npm 11.14), Chrome hoặc Edge để chụp ảnh.

```bash
cd spikes/frontend-stack
npm install                      # một node_modules duy nhất; package-lock.json ghim phiên bản đã thử

# 1) dev
npm run dev                      # http://localhost:5173  (?theme=dark, ?blocks để xem trang khối UI)
node mock-server/server.mjs      # mock AG-UI SSE ở http://localhost:8787/run (PORT=..., FAST=1 để bỏ độ trễ)

# 2) build + preview (cái đã đo/chụp)
npm run build
npx vite preview --port 4173 --host 127.0.0.1

# 3) kiểm tra không cần trình duyệt (Node 24 chạy trực tiếp file .ts)
node scripts/check-format.ts     # định dạng VND, dữ liệu dự báo giả
node scripts/check-blocks.ts     # Zod union + registry: khối hợp lệ / lạ / sai schema

# 4) chụp ảnh khổ 390x844, sáng + tối (cần preview ở :4173 và mock ở :8787)
node scripts/shots.mjs http://127.0.0.1:4173 [light|dark]
node scripts/nf-check.mjs        # NumberFlow: giữa chừng + sau animation

# 5) đo bundle theo nhóm gói (ghi dist-analyze/, xóa sau khi xem)
npx vite build -c vite.analyze.config.ts
```

Ảnh ghi vào `docs/research/assets/frontend-spike/`. `shots.mjs` dùng `channel: 'chrome'` nên không cần tải chromium.

## Cách dựng từ đầu (lệnh đã dùng)

```bash
npm create vite@9.3.4 . -- --template react-ts --no-interactive --no-immediate
npm install
npm install tailwindcss @tailwindcss/vite
# sửa vite.config.ts (plugin tailwind + alias @), tsconfig.json và tsconfig.app.json (paths @/*), src/index.css = @import "tailwindcss";
npx shadcn@4.23.0 init -t vite -b base -p nova --yes --force   # KHÔNG tương tác chỉ khi có -p nova (không có -p thì hiện menu chọn preset)
npx shadcn@4.23.0 add card drawer tabs input skeleton badge --yes
npx shadcn@4.23.0 add message message-scroller bubble trace chart --yes
npm install recharts@latest motion @number-flow/react @ag-ui/client zod @fontsource-variable/plus-jakarta-sans d3-shape
npm install -D @types/d3-shape playwright
```

## Cấu trúc

- `src/lib/format.ts`: `formatVND`, `formatVNDShort`, `formatVNDAxis`, ngày theo `Asia/Ho_Chi_Minh`.
- `src/lib/forecast-data.ts`: dữ liệu dự báo giả (P10/P50/P90, ngày lương, nghĩa vụ, what-if).
- `src/components/ForecastChart.tsx`: biểu đồ Recharts (dải P10-P90, P50, mốc, hatch vùng hụt, what-if hai dải).
- `src/components/JarGlass.tsx`, `ResilienceGauge.tsx`: SVG tự vẽ (Motion + NumberFlow).
- `src/blocks/`: `schemas.ts` (Zod discriminated union), `registry.tsx` (type -> component + fallback + error boundary), `components.tsx`, `fixtures.ts`.
- `src/agui/useYofinaChat.ts`: client mỏng trên `@ag-ui/client` (`HttpAgent` + `AgentSubscriber`).
- `src/components/ChatSheet.tsx`: bottom sheet (Base UI Drawer, snap 0.6 và 1) + message-scroller/bubble/trace của shadcn.
- `mock-server/server.mjs`: SSE mock phát chuỗi event AG-UI.
- `src/components/ui/*`: file do shadcn sinh ra (giữ nguyên, trừ khi ghi chú khác).
