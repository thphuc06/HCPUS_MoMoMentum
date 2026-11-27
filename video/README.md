# video/: video demo Yofina (Remotion)

Video demo ≤ 3 phút cho bài nộp (issue #38, mục I3 của [phase 6](../docs/plan/phases/phase-6-danh-gia-dong-goi.md)). Bản cuối 27/11/2026 dài 2:58, mp4 ở Drive (không đưa vào repo).

- `narration.md`: lời dẫn tiếng Anh theo cảnh; `scripts/tts.mjs` đọc file này, gọi Amazon Polly (engine generative, giọng Tiffany, ap-southeast-1), ghi `public/voice/*.mp3` và `manifest.json` (chỉ tạo lại câu đổi chữ).
- `src/demo/`: composition `YofinaDemo` (1920×1080, 30 fps). `scenes.ts` là dữ liệu dựng: đoạn cắt, đoạn tua (chỉ lúc chờ agent), spotlight (làm tối xung quanh, khung sáng; không zoom), vòng chạm, nhãn dịch Việt → Anh. `ArchScene.tsx` là sơ đồ hệ thống.
- `src/Story.tsx`: phần mở đầu cũ (composition `YofinaStory`).
- `scripts/check-edit.mjs`: kiểm không tua hay cắt bên trong đoạn cuộn.
- `public/rec/` (không trong repo): đoạn quay app thật 390×844 ở DPR 2, quay bằng Playwright + CDP trên tài khoản `giamkhao1` (hồ sơ trình duyệt do chủ dự án tự đăng nhập), đoạn cuộn chụp từng khung 30 fps; `REPORT.md` ghi số trên màn từng cảnh.

Lệnh (trong `video/`): `npm i`; xem thử `npm run dev`; giọng `node scripts/tts.mjs`; xuất `npx remotion render YofinaDemo out/yofina-demo.mp4`; chuẩn hóa âm lượng về −16 LUFS bằng `npx remotion ffmpeg` (`loudnorm`).
