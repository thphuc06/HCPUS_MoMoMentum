# Thiết kế giao diện Yofina Foresight trong Figma

> Bộ màn hình đủ để demo 6 cảnh, theo chuẩn agentic UI trong [agentic-ui-generative-ui.md](agentic-ui-generative-ui.md) và điều hướng trong [frontend-fintech-ui.md](frontend-fintech-ui.md). Dựng ngày 21/11/2026 bằng Figma MCP. Toàn bộ dữ liệu là hư cấu theo persona Minh; mọi màn đều có chỗ ghi "Ví mô phỏng".

## 1. Link và cấu trúc file

- **File Figma**: https://www.figma.com/design/l9vWyORNRjDqiEOXqpbzYm (tên "Yofina Foresight — UI demo", team Phuc_team). Mã file `l9vWyORNRjDqiEOXqpbzYm`.
- Khổ mobile 390×844 (riêng trace là desktop 1280×800), mỗi màn một frame auto layout, đặt tên theo mã màn. Các frame được gom vào Section theo luồng demo.

| Trang | Node id | Nội dung |
|---|---|---|
| Foundations | `0:1` (frame `28:2`) | Biến màu Sáng/Tối, bảng tương phản WCAG, thang chữ, bo góc, khoảng cách |
| Components | `2:2` | 33 component và component set |
| Screens | `2:3` | 7 section màn hình sáng + 1 section màn tối |

### Section và frame trên trang Screens

| Section (node id) | Frame (node id) |
|---|---|
| Cảnh 1 · Tổng quan, danh sách hũ, chi tiết hũ (`21:2335`) | C1 Tổng quan `17:2`; C1 Tổng quan cuộn xuống `17:289`; C2 Danh sách hũ `17:489`; C2 Danh sách hũ cuộn xuống `17:673`; C2 Chi tiết hũ Ăn uống `17:801`; C2 Chi tiết hũ cuộn xuống `17:925` |
| Cảnh 2 · Chuyển tiền (`21:2336`) | T1 chọn người nhận `19:787`; T2 nhập số tiền + hũ nguồn `19:872`; T3a kiểm tra XANH `19:955`; T3b VÀNG `19:1009`; T3c ĐỎ `19:1084`; T4 xem lại và xác nhận `19:1158`; T5 biên nhận `19:1217` |
| Cảnh 2 · Hỏi Yofina 1/2 (`21:2337`) | H1 mở đầu `21:1283`; H2 đang chạy `21:1379`; H3a dòng thời gian trước–sau `21:1453`; H3b tác động nghĩa vụ `21:1555`; H3c phương án + lời giải thích + "Vì sao" `21:1670`; H4 bảng "Vì sao" `21:1762` |
| Cảnh 2 và 4 · Hỏi Yofina 2/2 (`21:2338`) | H5 hỏi lại `21:1862`; H6a xác nhận đổi số dư `21:1932`; H6b đã thực hiện + Hoàn tác `21:2025`; H7 từ chối đúng phạm vi `21:2107`; H8a suy giảm `21:2179`; H8b độ tin cậy thấp `21:2271` |
| Cảnh 3 và 4 · Chống chịu, lộ trình (`25:2757`) | R1 điểm chống chịu `23:1786`; R2 sau "Mất việc 2 tháng" `23:1881`; R3 bốn thành phần `23:1993`; L1 lộ trình v3 `23:2088`; L2 giai đoạn sau `23:2190`; L3 so với bản cũ `23:2279` |
| Cảnh 5 · Nạp dữ liệu và phân hũ (`25:2758`) | I1 chọn ảnh `24:2165`; I2 đang xử lý `24:2210`; I3 duyệt dòng `24:2269`; I4 độ phủ tăng `24:2347`; A1 "Xem lại" `24:2406`; A2 hỏi gộp `24:2505` |
| Onboarding và Cảnh 6 · Trace (`25:2759`) | O1 lương + ngày nhận `25:2327`; O2 hũ + tỷ lệ chia `25:2391`; O3 chi phí cố định + khai bằng chat `25:2508`; X1 trace desktop `25:2591` |
| Giao diện tối, bổ sung (`28:2741`) | Tổng quan tối `28:2742`; H3b tối `28:2967`; H6a tối `28:3074` |
| Đăng nhập và khung giữ chỗ, mới thêm cho prototype (section nằm phía trên cùng trang) | S0 Đăng nhập `31:2715`; S1 Hồ sơ (khung giữ chỗ) `31:2754`; S2 Quét QR (khung giữ chỗ) `31:2804`; S3 Hoạt động (khung giữ chỗ) `31:2830` |

Tổng cộng 48 frame (47 mobile + 1 desktop), trong đó 3 frame tối và 4 frame mới thêm. Phần nối prototype xem mục 8.

## 2. Bảng màu

Biến màu nằm trong collection `Color` (chế độ Sáng và Tối), có kèm collection `Spacing` và `Radius`. Hồng chủ đạo dựa tông ví MoMo nhưng chọn mã riêng, không dùng logo, tên, linh vật hay biểu tượng của MoMo; tên hiển thị là "Yofina".

| Vai trò | Sáng | Tối |
|---|---|---|
| Nền ứng dụng `bg/app` | `#FAF6F7` | `#17101A` |
| Thẻ `bg/surface` | `#FFFFFF` | `#241A28` |
| Nền phụ `bg/surface-2` | `#F4EEF0` | `#2F2433` |
| Nền hồng nhạt `bg/tint` | `#FCE7F1` | `#3A1C30` |
| Viền `border/default` | `#E8DFE3` | `#3A2E40` |
| Chữ chính | `#2B1A24` | `#F4EEF0` |
| Chữ phụ | `#6E5A66` | `#B8A9B2` |
| Chữ trên nền chủ đạo | `#FFFFFF` | `#FFFFFF` |
| Chữ thương hiệu `text/brand` | `#A50064` | `#FF7EBB` |
| Chủ đạo `brand/primary` (nút, FAB, tab) | `#C8207E` | `#C8207E` |
| Chủ đạo đậm `brand/deep` (đầu gradient thẻ số dư) | `#A50064` | `#8C0054` |
| Hồng sáng `brand/vivid` (trang trí) | `#D82D8B` | `#E0348F` |
| Nhấn phụ xanh dương `accent/blue` (đường dự báo, tiền) | `#3050C8` | `#8FA8FF` |
| Đủ: chữ / nền / nét | `#0B7A52` / `#E1F5EC` / `#12A877` | `#4FD3A1` / `#123428` / `#4FD3A1` |
| Sát: chữ / nền / nét | `#8F5200` / `#FFF0D2` / `#E39A00` | `#FFC25C` / `#3A2C10` / `#FFC25C` |
| Hụt: chữ / nền / nét | `#B8330A` / `#FFE8DC` / `#E8541C` | `#FF8C5E` / `#3C2016` / `#FF8C5E` |
| 7 màu hũ (Ăn uống, Đi lại, Hóa đơn, Giải trí, Du lịch, Dự phòng, Nghĩa vụ) | `#7C5CE0`, `#2FA3D6`, `#A8794A`, `#B05CE0`, `#1FA6A0`, `#3B6FD0`, `#7A8794` | các tông sáng hơn tương ứng |

### Tương phản đã kiểm (tính từ mã hex, WCAG AA chữ thường cần từ 4,5)

| Cặp | Sáng | Tối |
|---|---|---|
| Chữ chính trên nền app | 15,35 | 16,29 |
| Chữ phụ trên nền app | 5,91 | 8,31 |
| Chữ phụ trên thẻ trắng | 6,33 | 7,46 |
| Chữ trắng trên `brand/primary` | 5,30 | 5,30 |
| Chữ trắng trên `brand/deep` | 7,54 | 9,36 (trên `#8C0054`) |
| `text/brand` trên `bg/tint` | 6,41 | 6,45 |
| `text/brand` trên nền app | 7,04 | 7,96 |
| `accent/blue` trên thẻ trắng | 6,76 | 7,35 |
| Đủ: chữ trên nền | 4,71 | 7,21 |
| Sát: chữ trên nền | 5,53 | 8,48 |
| Hụt: chữ trên nền | 5,07 | 6,50 |

Lưu ý: `#D82D8B` với chữ trắng chỉ đạt 4,50 (sát ngưỡng) nên **không** dùng làm nền chữ nhỏ, chỉ để trang trí. Nút và FAB dùng `#C8207E` (5,30). Hồng chủ đạo có hue khoảng 330 độ, san hô "hụt" khoảng 20 độ; ba trạng thái luôn kèm biểu tượng (dấu tích, tam giác cảnh báo, mũi tên chéo xuống) và chữ, nên không chỉ dựa vào màu.

## 3. Kiểu chữ

Font **Plus Jakarta Sans** (có trong Figma, đã kiểm bằng mắt các chữ "ự ễ ợ ặ ữ" trên trang Foundations). Text style có tiền tố `Yofina/`:

| Style | Cỡ / dòng | Độ đậm | Dùng cho |
|---|---|---|---|
| Số lớn | 34 / 40 | ExtraBold | Tổng số dư, điểm |
| Số tiền | 20 / 28 | ExtraBold | Số tiền trong thẻ |
| Tiêu đề màn | 24 / 32 | Bold | Tiêu đề màn |
| Tiêu đề khối | 18 / 26 | Bold | Tiêu đề phần |
| Tiêu đề nhỏ | 16 / 24 | SemiBold | Tiêu đề thẻ, khối AI |
| Thân, Thân đậm | 15 / 22 | Regular, SemiBold | Nội dung |
| Phụ, Phụ đậm | 13 / 18 | Regular, SemiBold | Giải thích, nhãn |
| Chú thích | 12 / 16 | Medium | Chú thích nhỏ (không dưới 12) |
| Nút | 16 / 20 | Bold | Nút lớn |

Định dạng tiền: `1.200.000 ₫` ở thẻ và `1,2 triệu` ở câu hỏi và lời giải thích. Bo góc: thẻ 24, sheet 28 phía trên, nút và chip dạng viên thuốc. Hai effect style: "Bóng thẻ" và "Bóng sheet".

## 4. Danh mục component (trang Components)

| Nhóm | Component (node id) | Ghi chú |
|---|---|---|
| Nền tảng | Button `5:26` (4 kiểu × 2 cỡ), StatusChip `5:60` (Đủ, Sát, Hụt, AI, Thông tin), StatusBar `5:71`, TabBar `5:218` (5 trạng thái, nút giữa "Hỏi Yofina"), ChatInput `5:226`, AppBar `14:457`, Numpad `14:450` | Nút giữa nổi, đủ 5 mục |
| Hũ | JarIcon `7:46` (7 hũ), JarCard `7:130` (đủ / sát / hụt, hũ thủy tinh có mực nước và vạch "mực dự báo"), JarRow `14:236` | Hũ vẽ riêng, không phải hộp chữ nhật trơn |
| Tổng quan | BalanceCard `14:143`, ProactiveCard `14:176`, MiniTimeline `7:146`, TxRow `14:264` | Thẻ chủ động có "Hỏi vì sao", "Để sau", "Ít nhắc loại này" |
| Khối UI của AI (theo `type`) | ForecastBlock `7:248` (`forecast_timeline`, 2 biến thể), AffordCard `11:196` (`affordability_card`, XANH / VÀNG / ĐỎ), ObligationImpact `10:122` (`obligation_impact`), OptionsBlock `10:154` (`options`), ExplainSheet `11:378` (`explain`), ConfirmBlock `11:244` (`confirm`), ReceiptBlock `11:269` (`receipt`), ClarifyBlock `11:295` (`clarify`), Notice `10:196` (`notice`: ngoài phạm vi, rút gọn, dữ liệu ít, lỗi), SuggestionChips `10:215` (`suggestions`), ToolProgress `10:75`, SkeletonBlock `10:82`, AIFooter `10:233`, UserBubble `10:238`, AIMessage `10:242` | Cùng component dùng ở Tổng quan, Chi tiết hũ, Chuyển tiền và trong chat |
| Chống chịu, lộ trình, nạp dữ liệu | ResilienceGauge `14:319` (điểm 58 và 34), ScoreRow `14:332`, RoadmapStep `14:385` (chờ / đã chấp nhận / đã từ chối), IngestRow `14:417` (tự thêm / cần duyệt) | `resilience_score`, `roadmap`, `ingest_review` |

Trong màn hình, component được dùng bằng instance; nội dung đổi bằng ghi đè văn bản và đổi biểu tượng hũ bằng `swapComponent`. Màu icon và mọi fill/stroke chính gắn biến màu, nên đổi sang chế độ Dark là đổi cả bộ.

## 5. Ánh xạ màn hình, cảnh demo và tính năng

| Cảnh demo | Màn hình | Tính năng |
|---|---|---|
| 1 (0:00–0:30) Mở app, hũ Ăn uống cạn 23/11, còn 12 ngày tới kỳ lương | C1 Tổng quan (thẻ chủ động + dòng thời gian thu gọn), C2 Danh sách hũ, C2 Chi tiết hũ (biểu đồ 30 ngày) | F1 |
| 2 (0:30–1:15) "Mua tai nghe 1,2 triệu bằng Ví Trả Sau" | H1, H2, H3a, H3b, H3c, H4, H5, H6a, H6b, H8a, H8b; luồng Chuyển tiền T1–T5 (kiểm tra XANH / VÀNG / ĐỎ) | F2, F3 |
| 3 (1:15–1:45) "Mất việc 2 tháng" | R1, R2, R3 | F4 |
| 4 (1:45–2:20) Lộ trình sinh lại, "Vì sao", từ chối đúng phạm vi | L1, L2, L3, H4, H7 | F5, suitability |
| 5 (2:20–2:50) Chụp thông báo chuyển khoản | I1–I4, A1, A2 | F6, phân hũ tự động |
| 6 (2:50–3:00) Trace cho đội sản phẩm | X1 | Góc "Future Workspace" |
| Trước demo | O1, O2, O3 (khai báo, có lối khai bằng chat) | FR1, FR4 |

### Bảng số liệu thống nhất (dùng xuyên suốt, ngày hôm nay là 21/11/2026)

| Mục | Giá trị |
|---|---|
| Tổng số dư | 8.260.000 ₫ = 7.730.000 ₫ trong 7 hũ + 350.000 ₫ "Tiền vào khác" + 180.000 ₫ "Chưa phân loại" |
| Lương | 9.000.000 ₫, về ngày 5. Chia: Hóa đơn 31%, Ăn uống 30%, Đi lại 7%, Giải trí 7%, Du lịch 10%, Dự phòng 10%, Nghĩa vụ 5% |
| Số dư hũ | Ăn uống 380.000 (hụt, cạn 23/11); Đi lại 640.000 (đủ); Hóa đơn 450.000 (sát); Giải trí 760.000 (đủ); Du lịch 1.800.000 (đủ, trễ mục tiêu 5 tuần); Dự phòng 2.700.000 (đủ, khoảng 9 ngày); Nghĩa vụ 1.000.000 (giữ sẵn cho Trả Sau 5/12) |
| What-if tai nghe | Gốc 1.200.000 + phí 33.000 = 1.233.000 ₫, đến hạn 5/12; hũ Giải trí còn 823.000 ₫ khi lương về nên hụt 410.000 ₫ |
| Chuyển tiền demo | 250.000 ₫ cho Trần Quang Huy (tiền điện nước chia đôi); Đi lại = xanh, Hóa đơn = vàng, Ăn uống = đỏ (hụt khoảng 1.300.000 ₫); qua Trả Sau tổng 283.000 ₫ |
| Chống chịu | 58/100 (Chi tiêu 68, Tiết kiệm 41, Vay nợ 74, Kế hoạch 50); sau "Mất việc 2 tháng" 34/100, trụ được 27 ngày (riêng hũ Dự phòng 9 ngày), thiếu 9.740.000 ₫ cho 60 ngày |
| Độ phủ dữ liệu | 62% (47 ngày dữ liệu), sau khi nạp ảnh lên 81% |
| Trace | `tr_8f3a21c9`, 3,9 s, 5.412 / 912 token, 0,011 $ |

## 6. Quyết định thiết kế và lý do

1. **Giữ bố cục bản thử, đổi màu sang hồng–magenta.** Thẻ số dư dùng gradient `#A50064` đến `#C8207E` để mọi chữ trắng đều đạt từ 5,3. Nền kem chàm thay bằng nền hồng ngả ấm `#FAF6F7`.
2. **Màu "hụt" là san hô cam đỏ, không phải đỏ hồng**, và ba trạng thái luôn có biểu tượng + chữ (không chỉ dựa vào màu).
3. **Màu nhấn phụ là xanh dương dùng cho dữ liệu dự báo** (đường giữa, dải 80%), để hồng không bị lẫn với vùng hụt.
4. **Hũ có hình riêng**: thủy tinh, mực nước theo số dư, vạch đứt "mực dự báo", nắp theo màu hũ; mỗi hũ thêm một biểu tượng.
5. **Số liệu đến trước lời**: trong chat, thẻ dự báo và thẻ nghĩa vụ hiện trước đoạn giải thích; có khung chờ (skeleton) ở H2 để chữ không nhảy.
6. **Người dùng quyết định mọi thay đổi số dư**: xem trước (trước → sau hai hũ, tác động dự báo) → nút nêu hành động và số tiền → biên nhận → Hoàn tác có đếm ngược (H6a, H6b). Phương án nào cần xác nhận đều ghi "Cần bạn xác nhận".
7. **Hỏi lại thay vì đoán** (H5): một câu, chip trả lời, ô gõ tự do, giả định hiển thị.
8. **Nói rõ giới hạn và mức tin cậy**: H1 liệt kê "Mình làm được / chưa làm", bảng "Vì sao" dùng nhóm Cao/Vừa/Thấp kèm lý do (không phần trăm do AI tự đưa), độ phủ dữ liệu là số thật của hệ thống.
9. **Lỗi vẫn hữu ích** (H8a): thẻ số liệu tất định hiện trước, ghi rõ lời giải thích đến sau, có nút thử lại; H8b mời nạp thêm dữ liệu.
10. **Một việc mỗi lần**: Tổng quan chỉ có một thẻ chủ động, kèm "Để sau" và "Ít nhắc loại này".
11. **Dùng chung component** giữa màn chính và chat (dòng thời gian, thẻ kiểm tra, thẻ hũ).
12. **Nhãn AI**: chip "Do AI tạo" ở đầu sheet, chip AI trên từng khối do AI sinh, nhắc rõ "Điểm này không phải điểm tín dụng".
13. **Danh sách hũ và Tổng quan chia hai frame "cuộn xuống"** để không nhồi chữ nhỏ vào một màn 844 px.

## 7. Chưa làm hoặc còn hạn chế

- Prototype chỉ nối cho luồng demo (mục 8); các màn ngoài demo để tĩnh.
- Chỉ **3 frame tối** (Tổng quan, tác động nghĩa vụ, xác nhận). Biểu đồ và hũ thủy tinh dùng một số màu cố định (SVG và fill trong suốt), nên chưa dựng frame tối chứa biểu đồ.
- Bốn dòng `ScoreRow` ở R3 đã được tách khỏi component (để đặt độ dài thanh); thành phần gốc vẫn có trong Components.
- Icon là SVG vẽ tay theo phong cách nét mảnh, **không phải thư viện icon chính thức**; chưa có bộ icon thành component riêng (chỉ JarIcon).
- Frame H8b dùng số "18 ngày, độ phủ 38%" (tài khoản mới, minh họa trạng thái dữ liệu ít), khác với 62% của tài khoản Minh ở các màn khác; tên frame đã ghi chú.
- Ngày cạn 23/11 và ngày lương 5/12 theo demo-script; bản thử trước dùng 29/11 và số dư 12.480.000 ₫, đã thay bằng bộ số ở mục 5.
- Hoạt động, Quét QR, Hồ sơ chỉ là khung giữ chỗ (mục 8); chưa có màn Cài đặt.
- Các bước xác thực Face ID chỉ là mô phỏng trên màn hình, nhãn ghi rõ.
- Chưa kiểm khả năng đọc trên điện thoại thật; tương phản mới kiểm bằng tính toán, chưa chạy công cụ kiểm tự động trên frame.

## 8. Prototype bấm được (luồng demo 6 cảnh)

### 8.1 Link và cách chạy

- **Link trình chiếu (bắt đầu từ màn Đăng nhập)**: https://www.figma.com/proto/l9vWyORNRjDqiEOXqpbzYm/Yofina-Foresight-UI-demo?page-id=2%3A3&node-id=31-2715&starting-point-node-id=31%3A2715&scaling=scale-down&hide-ui=1
  (nếu link không mở đúng điểm bắt đầu, vào file, chọn trang Screens, bấm nút Present và chọn flow "Demo đầy đủ: Đăng nhập → 6 cảnh").
- Trên trang Screens có **8 điểm bắt đầu (flow starting point)** để tập từng cảnh: Demo đầy đủ (Đăng nhập `31:2715`), Cảnh 1 Tổng quan (`17:2`), Cảnh 2 Hỏi Yofina (`21:1283`), Cảnh 2 Chuyển tiền (`19:787`), Cảnh 3 Chống chịu (`23:1786`), Cảnh 4 Lộ trình (`23:2088`), Cảnh 5 Nạp dữ liệu (`24:2165`), Cảnh 6 Trace (`25:2591`).
- Có **170 tương tác** (đã đọc lại bằng API: mọi đích đều tồn tại, không có đích sai). Từ màn Đăng nhập đi tới được **42 trên 48 frame**; 6 frame còn lại là onboarding O1–O3 và 3 frame tối, cố ý để tĩnh. Chưa chạy thử trong chế độ trình chiếu thật.
- Quy ước: "→" là bấm; **kéo** là kéo chuột/vuốt trên vùng nội dung của màn; "tự chuyển" là After delay. Nút quay lại, nút Dừng và nút Không dùng hành động "Quay lại" của Figma (trở về frame vừa xem).
- Hiệu ứng: đổi tab và bước trong chat dùng Dissolve 0,2 s; đi tới màn con dùng Slide in từ phải 0,25 s; mở chat dùng Move in từ dưới 0,3 s và đóng chat dùng Move out xuống dưới; kéo để cuộn dùng Move in 0,25 s.
- Bottom sheet chat là **chuyển frame có hiệu ứng trượt từ dưới lên, không phải overlay thật**: mỗi frame chat tự mang nền mờ của Tổng quan, nên dùng overlay thật của Figma sẽ phải tách lại toàn bộ frame chat. Chấp nhận để giữ gọn.

### 8.2 Kịch bản bấm cho người thuyết trình

**Mở đầu.** Màn Đăng nhập → bấm **Dùng tài khoản demo** → Tổng quan.

**Cảnh 1 (0:00–0:30), F1.** Tổng quan, thẻ gợi ý chủ động cho thấy hũ Ăn uống cạn 23/11 và dòng thời gian thu gọn → bấm **Hỏi vì sao** (hoặc **Xem dự báo**) → Chi tiết hũ Ăn uống (biểu đồ 30 ngày, mốc điện 26/11, lương 5/12, cạn 23/11). Tuỳ chọn: ở Tổng quan bấm tiêu đề **Hũ của bạn** hoặc kéo lên để thấy dải thẻ hũ; bấm thẻ hũ Ăn uống để vào Chi tiết hũ; tab **Hũ** → Danh sách hũ (bấm dòng Ăn uống → Chi tiết; kéo lên để thấy phần còn lại); ở Chi tiết hũ kéo lên để thấy giao dịch gần đây.

**Cảnh 2 (0:30–1:15), F2 + F3.**
1. Bấm nút giữa **Hỏi Yofina** trên tab bar → Chat mở đầu (trượt từ dưới lên) → bấm gợi ý **Nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao?** → Đang chạy (tự chuyển sau 2 s).
2. Kết quả: dòng thời gian trước–sau → bấm vùng hội thoại (cuộn xuống) → Tác động nghĩa vụ → bấm vùng hội thoại lần nữa → Phương án + lời giải thích.
3. Bấm **Vì sao** (hoặc ở Chi tiết hũ bấm "Vì sao" của khối dự báo) → Bảng "Vì sao" → bấm X để quay lại.
4. Chọn phương án 1 **Chuyển 410.000 ₫ từ hũ Du lịch sang hũ Giải trí** → Xác nhận đổi số dư → **Xác nhận chuyển 410.000 ₫** → Đã thực hiện → **Hoàn tác** → quay về Phương án (hoặc **Không** ở bước xác nhận để quay lại).
5. Đường chuyển tiền (kiểm tra trước khi quẹt): Tổng quan → **Chuyển tiền** → bấm dòng **Trần Quang Huy** → nhập số tiền → **Kiểm tra trước khi chuyển** → thẻ **VÀNG** (hũ Hóa đơn). Từ đây: **Trả bằng Ví Trả Sau** (tổng 283.000 ₫) hoặc **Vẫn chuyển 250.000 ₫** → Xem lại → **Xác nhận bằng Face ID** → Biên nhận. Nhánh xanh: **Dùng tiền hũ Đi lại** → thẻ XANH → Tiếp tục. Nhánh đỏ: ở thẻ vàng bấm **Đổi nguồn** → thẻ ĐỎ (hũ Ăn uống hụt), có Trả Sau và phương án Đi lại.
6. Nhánh agentic bổ sung (không bắt buộc): ở khung chat đang chạy bấm **Dừng** → suy giảm có kiểm soát (thẻ số liệu, lời giải thích đến sau); trong bảng "Vì sao" bấm chip **Vừa** → độ tin cậy thấp, mời nạp dữ liệu; ở frame từ chối bấm ô nhập → hỏi lại một câu.

**Cảnh 3 (1:15–1:45), F4.** Tab **Nhìn trước** (hoặc ở Tổng quan kéo/bấm "Điểm chống chịu") → điểm 58/100 → bấm thẻ **Mất việc 2 tháng** → điểm tụt còn 34, trụ được 27 ngày. Bấm đồng hồ điểm để xem bốn thành phần.

**Cảnh 4 (1:45–2:20), F5 + suitability.** Ở frame sau cú sốc bấm **Xem lộ trình thích ứng** → Lộ trình phiên bản 3 ("Phiên bản mới do hành vi thay đổi") → bấm **So với bản cũ (v2)** → so sánh → **Dùng bản mới**. Bấm dòng lý do **Vì sao** của bước 1 → Bảng "Vì sao" → X. Bấm **Chấp nhận** → các giai đoạn sau. Hỏi trợ lý: nút giữa **Hỏi Yofina** → bấm **ô nhập** → frame **Nên mua cổ phiếu nào?** từ chối đúng phạm vi (bấm các gợi ý để quay về chống chịu hoặc lộ trình). Luồng xác nhận đổi số dư (confirm → đã thực hiện → hoàn tác) nằm ở Cảnh 2 bước 4.

**Cảnh 5 (2:20–2:50), F6.** Tổng quan → **Tiền vào** → bấm **Chụp ảnh** → đang xử lý (tự chuyển sau 2,2 s) → duyệt dòng → **Xong, cập nhật dự báo** → độ phủ 62% lên 81% → **Xem dự báo cập nhật** (về Chi tiết hũ).

**Cảnh 6 (2:50–3:00), trace.** Mở bảng "Vì sao" (từ chat hoặc lộ trình) → bấm hàng **Mã trace** → màn trace desktop. Bấm logo "Yofina · Trace" ở góc trái để về Tổng quan.

### 8.3 Danh sách điểm tương tác đã nối (nguồn → đích)

- **Đăng nhập**: Dùng tài khoản demo, Đăng nhập → Tổng quan.
- **Tổng quan**: Hỏi vì sao, Xem dự báo, thẻ hũ Ăn uống → Chi tiết hũ; tiêu đề "Hũ của bạn" và kéo → Tổng quan cuộn xuống; Chuyển tiền → T1; Quét QR → khung Quét QR; Tiền vào → I1; tab bar 5 mục.
- **Tổng quan cuộn xuống**: thẻ hũ → Chi tiết hũ; Cần xem lại (3) → A1; Điểm chống chịu → R1; Gần đây → khung Hoạt động; kéo → Tổng quan.
- **Danh sách hũ**: dòng Ăn uống → Chi tiết; kéo → bản cuộn xuống (có nút Phân loại ngay → A2); tab bar. **Chi tiết hũ**: quay lại, Vì sao hũ này cạn? và Hỏi Yofina về hũ này → H1; Vì sao (khối dự báo) → H4; kéo để cuộn; tab bar.
- **Chat**: nút X mọi frame → Tổng quan; H1 (3 gợi ý + ô nhập → H2, Chi tiết hũ, R2, H7); H2 (tự chuyển → H3a, Dừng → H8a); H3a, H3b (bấm vùng hội thoại → frame kế, phương án 1 → H6a, Vì sao → H4); H3c (phương án 1, Vì sao); H4 (X quay lại, Mã trace → X1, chip Vừa → H8b, Nạp thêm sao kê → I1); H5 (chọn Ví Trả Sau → H2); H6a (Xác nhận → H6b, Không quay lại); H6b (Hoàn tác → H3c, Xem dự báo mới → H3a); H7 (ô nhập → H5, 2 gợi ý → R1, L1); H8a (Thử lại → H3a); H8b (Nạp ảnh → I1).
- **Chuyển tiền**: T1 (dòng Trần Quang Huy → T2), T2 (Kiểm tra → T3b), T3a/T3b/T3c (xem 8.2 mục 5), T4 (Face ID → T5, Quay lại sửa), T5 (Xong → Tổng quan, Hỏi Yofina → H1); mọi nút quay lại.
- **Chống chịu và lộ trình**: R1 (Mất việc 2 tháng → R2, tab bar), R2 (Xem lộ trình → L1, đồng hồ → R3, tab bar), L1 (So với bản cũ → L3, lý do → H4, Chấp nhận → L2, tab bar), L2 và R3 (tab bar), L3 (Dùng bản mới → L1, Giữ bản cũ/quay lại).
- **Nạp dữ liệu**: I1 (Chụp ảnh, Chọn ảnh → I2), I2 (tự chuyển → I3, Hủy), I3 (Xong → I4), I4 (Xem dự báo → Chi tiết hũ, Nạp thêm ảnh khác → I1). A1, A2 chỉ có nút quay lại và lưu.
- **Trace**: logo → Tổng quan. **Hồ sơ (khung)**: tab bar.
- **Flow starting point**: 8 điểm như mục 8.1.

### 8.4 Cố ý không nối

- Onboarding O1–O3 và 3 frame tối (không thuộc đường demo, để tĩnh).
- Nút Kiểm tra (Tổng quan), Giữa hũ, Xem tất cả, dấu cộng thêm hũ, chuông, nút ẩn số dư, các nút Sửa/Từ chối của lộ trình, chip chọn nhanh số tiền, bàn phím số, danh bạ khác ngoài Trần Quang Huy, phương án 2 "Hoãn mua", Gán vào hũ, Chia sẻ biên nhận, nút gửi và nút X của chat không có đích riêng ngoài các đường ở trên.
- Frame H3b và H6a bản tối, R3 (chỉ vào được qua đồng hồ điểm), A1, A2 chỉ là nhánh phụ.
- Không có bàn phím thật: ô nhập chat và số tiền chỉ là điểm bấm giả lập.

### 8.5 Khung giữ chỗ mới thêm

- **S0 Đăng nhập** (`31:2715`): hero gradient hồng với wordmark chữ "Yofina" (không logo thương hiệu), ô email và mật khẩu, nút phụ "Đăng nhập", nút chính "Dùng tài khoản demo", dòng "Ví mô phỏng".
- **S1 Hồ sơ** (`31:2754`): tiêu đề, nhãn "Khung giữ chỗ · ngoài phạm vi demo", 4 khối giữ chỗ, tab bar (để tab Hồ sơ không dẫn vào chỗ trống).
- **S2 Quét QR** (`31:2804`) và **S3 Hoạt động** (`31:2830`): khung có nút quay lại, mở từ nút Quét QR và "Gần đây" ở Tổng quan.
- Tab "Nhìn trước" dùng frame R1 đã có.

### 8.6 Hạn chế của prototype

- Kéo để cuộn dùng trigger "On drag" của Figma với hiệu ứng Move in (Figma không cho Dissolve ở On drag); trong chế độ trình chiếu phải kéo chuột rõ ràng. Nếu bất tiện, dùng tiêu đề "Hũ của bạn" ở Tổng quan hoặc chạm vùng hội thoại trong chat.
- Hiệu ứng Smart animate không dùng vì các frame khác cấu trúc, kết quả sẽ giống Dissolve.
- Bấm các chip gợi ý hoặc ô nhập chỉ chuyển sang frame kết quả; câu hỏi không thật sự được gõ.
- Chưa chạy thử trong chế độ trình chiếu thật bằng trình duyệt; kiểm tra chỉ bằng đọc lại reaction qua API và chụp các frame then chốt.
