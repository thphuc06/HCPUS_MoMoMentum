# Rà soát thiết kế UI và đề xuất cho buổi demo

> Người viết: Kiro (Claude Opus 5.5), worker do Claude Code điều phối, ngày 24/11/2026. Chỉ là tài liệu đề xuất: không sửa code `frontend/`. Bản xem trước tĩnh: [ui-design-preview.html](ui-design-preview.html) (mở thẳng bằng trình duyệt, khổ 390 px, sáng và tối).
>
> Cách làm: đọc các skill và hướng dẫn thiết kế ở mục 2 (clone vào thư mục tạm ngoài repo, đã xóa); đọc `figma-ui-design.md`, `frontend/src/index.css` và các màn Tổng quan, Hũ, Chi tiết hũ, Nhìn trước, Mô phỏng cú sốc, Lộ trình, chat, Hồ sơ, trace. **Chưa chạy app và chưa chạy `npm run build`** (worktree chưa có `node_modules`). Tỷ lệ tương phản tính bằng script từ mã hex theo công thức WCAG 2.x. Font kiểm bằng `fontTools` trên file tải từ Google Fonts.

## 1. Kết luận ngắn

Nền móng đã tốt: token gắn với Figma, ba trạng thái đủ/sát/hụt luôn có biểu tượng và chữ, vùng chạm đủ 44 px, số dùng chữ số đều bề ngang, dữ liệu thiếu thì nói thật. Thứ còn thiếu cho buổi demo là **một khoảnh khắc chính ở mỗi cảnh** và **thứ bậc thị giác**: con số quan trọng nhất của mỗi cảnh (12 ngày, 58 → 34, 27 ngày, 62% → 81%) hiện cùng cỡ với chữ xung quanh, và gần như không có chuyển động gắn với dữ liệu.

Năm việc đáng làm nhất:

1. **Đổi mã hồng thương hiệu.** `--brand-deep` và `--text-brand` đang là `#A50064`, đúng mã màu logo MoMo ([worldvectorlogo](https://worldvectorlogo.com/logo/momo-2)). Thay bằng họ hồng riêng (`#C8276A`, `#821041`, `#6E113D`), chỉ đổi giá trị biến, không đổi tên biến. Khoảng 1 giờ.
2. **Thẻ "Hũ Ăn uống sắp cạn" có số lớn "12 ngày" và dải ngày tới kỳ lương** thay cho thanh `MiniTimeline` 10 px. Đây là câu chuyện của cảnh 1. Khoảng 3 giờ.
3. **Đường "Sau" trên biểu đồ dự báo vẽ dần trong 700 ms** (hiện mọi animation của Recharts đều tắt), để đúng câu "biểu đồ dịch chuyển" trong kịch bản cảnh 2. Khoảng 1,5 giờ.
4. **Đồng hồ điểm chống chịu chạy từ 58 xuống 34 và thanh "trụ được 27/60 ngày"** trên màn kết quả cú sốc (hiện chỉ có dòng chữ "58 → 34"). Khoảng 3 giờ.
5. **Lộ trình dạng dòng thời gian**: đường dọc, nút tròn theo trạng thái, một nút chính mỗi bước thay cho ba bốn nút. Khoảng 3 giờ.

Bảng màu đề xuất ở mục 4.1. Danh sách việc P0/P1/P2 ở mục 6: P0 khoảng 14 giờ (hai ngày làm), chỉ sửa phần hiển thị, không đụng hợp đồng khối.

## 2. Nguyên tắc rút ra từ từng nguồn

Các ý dưới đây đã diễn đạt lại, không chép nguyên văn.

### 2.1 Anthropic `frontend-design` ([anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/frontend-design); bản trong plugin Claude Code nay nằm ở [claude-plugins-official](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/frontend-design), nội dung SKILL.md giống hệt)

- Chọn hình ảnh từ chính chủ đề sản phẩm. Với Yofina đó là cái hũ, mực nước và lịch tới ngày lương. Hũ thủy tinh hiện có đúng tinh thần này.
- Dồn sự táo bạo vào một chỗ mỗi màn; phần còn lại giữ yên. Một chuỗi chuyển động có chủ đích tốt hơn hiệu ứng rải rác. Chuyển động đáp lại thao tác (mở, xác nhận) thì nên có, vì nó cho thấy cái gì vừa đổi.
- Dấu hiệu của giao diện "rập khuôn": mọi nội dung chặt thành thẻ tròn giống nhau, một bán kính bo cho mọi thứ, cùng một bóng xám, gradient chỉ để trang trí; nhãn ALL CAPS; chuỗi meta nối bằng dấu "·". Đánh số chỉ khi nội dung thật sự là trình tự, như các bước lộ trình.
- Chữ trong giao diện viết theo góc nhìn người dùng; nút nói rõ việc sẽ xảy ra; lỗi nói cách sửa.

### 2.2 Anthropic `theme-factory`, `brand-guidelines`, `canvas-design` (cùng repo)

- `theme-factory`: một chủ đề gồm bảng màu có mã hex và cặp font, áp đồng nhất, kiểm tương phản. Mười chủ đề mẫu không hợp với ví (Desert Rose quá nhạt cho chữ nhỏ), nên dùng phần "tự tạo chủ đề" và đặt tên theo ý nghĩa.
- `brand-guidelines`: là bộ nhận diện riêng của Anthropic. Bài học dùng được: màu nhấn chỉ cho hình khối, chữ dùng màu tối hoặc sáng theo nền. Không dùng màu hay font của Anthropic cho Yofina.
- `canvas-design`: dành cho poster và ảnh tĩnh, không dành cho UI. Ý dùng được: thông tin nằm ở hình khối và tỷ lệ, chữ chỉ là điểm nhấn. Áp vào thẻ demo: số lớn, nhãn nhỏ, ít đoạn văn.

### 2.3 UI UX Pro Max ([nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill))

Chạy công cụ tìm kiếm của skill với "fintech personal finance budgeting mobile app" và vài truy vấn theo miền:

- Thứ tự ưu tiên: khả năng tiếp cận, chạm và tương tác, hiệu năng, rồi mới tới phong cách. Vùng chạm từ 44 px, chữ thân 16 px, tương phản 4,5:1.
- Chuyển động: mỗi chuyển động thể hiện một quan hệ nhân quả; thoát nhanh hơn vào (khoảng 60–70%); lệch nhịp 30–50 ms mỗi mục; ấn thì thu nhỏ 0,95–0,97; dùng spring cho cảm giác tự nhiên; luôn có bản giảm chuyển động.
- Biểu đồ dự báo: đường liền cho thực tế, đường đứt cho dự báo, dải tin cậy cùng tông độ mờ thấp, nhãn trực tiếp trên biểu đồ, có bản tóm tắt bằng chữ.
- Chế độ tối: dùng tông nhạt và giảm bão hòa, không đảo màu; thiết kế sáng và tối cùng lúc.
- Gợi ý font cho tiếng Việt: Be Vietnam Pro. Đã kiểm và **không chọn**, lý do ở mục 4.4.
- Bộ màu "fintech" mà skill sinh ra (navy, vàng, tím, nền tối) là bộ chung chung và còn ghi "tránh gradient hồng tím của AI". Yofina giữ hồng vì đó là ngữ cảnh ví quen thuộc với người Việt; điều cần tránh là dùng hồng làm trang trí khắp nơi.

### 2.4 Vercel Web Interface Guidelines ([vercel-labs/web-interface-guidelines](https://github.com/vercel-labs/web-interface-guidelines), [vercel.com/design/guidelines](https://vercel.com/design/guidelines))

- Chỉ animate `transform` và `opacity`; không bao giờ `transition: all`; animation phải ngắt được; tôn trọng `prefers-reduced-motion`; SVG transform đặt trên `<g>` với `transform-box: fill-box`.
- Thứ trông như bấm được thì phải bấm được; không có ngõ cụt.
- Trạng thái không chỉ dựa vào màu; số so sánh dùng `tabular-nums`; ngày giờ và số theo locale.
- Bóng nhiều lớp (bóng nền và bóng gần); viền bán trong suốt; bo góc lồng nhau thì con nhỏ hơn cha; viền, bóng và chữ ngả theo tông nền.
- Biểu đồ dùng bảng màu an toàn cho người mù màu; `theme-color` khớp nền; `color-scheme: dark` cho chế độ tối.

### 2.5 Apple HIG, phần biểu đồ và chuyển động ([Charting data](https://developer.apple.com/design/human-interface-guidelines/charting-data), [Motion](https://developer.apple.com/design/human-interface-guidelines/motion))

- Mỗi biểu đồ có một điều chính cần nói; đặt câu tóm tắt ngay trên biểu đồ (kiểu "khả năng mưa trong giờ tới" của app Thời tiết). Giữ biểu đồ đơn giản, chi tiết thì người dùng tự mở thêm.
- Biểu đồ cùng dữ liệu ở nhiều nơi dùng cùng kiểu, màu và chú thích. Yofina đã làm điều này giữa Chi tiết hũ và chat.
- Biểu đồ kiểu mới thì dạy cách đọc bằng chuyển động lần đầu, như vòng Activity hiện từng vòng một.
- Chuyển động có mục đích, ngắn và chính xác; tránh chuyển động ở thao tác lặp lại thường xuyên; cho phép hủy; không dùng chuyển động làm cách duy nhất để truyền thông tin.

### 2.6 Material Design 3 ([màu](https://m3.material.io/styles/color/system/how-the-system-works), [easing và duration](https://m3.material.io/styles/motion/easing-and-duration/tokens-specs), [dark theme codelab](https://codelabs.developers.google.com/codelabs/design-material-darktheme))

- Màu theo vai trò: primary và on-primary, container và on-container, các tầng surface. Container là màu nền, không dùng làm màu chữ. Token Yofina nên đặt theo vai trò như vậy (nay đã gần đúng).
- Mặt tối là chế độ đi kèm, giữ nhận diện; độ cao trong tối thể hiện bằng tông surface sáng dần, không bằng bóng.
- Hệ easing và duration cũ của M3 (vào chậm dần, ra nhanh dần, thoát ngắn hơn vào) vẫn dùng được cho chuyển cảnh. M3 Expressive đã chuyển sang hệ spring và ghi rằng hệ cũ không còn bảo trì.

### 2.7 Bài viết UX fintech ([Eleken, 2026](https://www.eleken.co/blog-posts/fintech-ux-best-practices), [Toptal case study](https://www.toptal.com/designers/ux/mastering-fintech-ux-case-study))

- Người dùng mở app tài chính khi đang lo; giao diện rối làm tăng lo lắng và giảm niềm tin.
- Dữ liệu tài chính dày: đơn giản hóa mà không giấu điều quan trọng; số chính trước, chi tiết sau.
- Thao tác rủi ro cần bước xem lại, xác nhận rõ, có lối hoàn tác. Yofina đã có (xác nhận, biên nhận, Hoàn tác).
- Có thể vui mà vẫn đáng tin: chuyển động và hình ảnh vui phải gắn với số thật.

## 3. Đánh giá hiện trạng

### 3.1 Điểm mạnh

- **Token có hệ thống**: biến CSS theo vai trò, ánh xạ sang tên của shadcn và Tailwind, thang chữ `Yofina/*` khớp Figma (`frontend/src/index.css`).
- **Trạng thái không chỉ dựa vào màu**: `StatusChip` luôn có biểu tượng và chữ; màu "hụt" là san hô, tách khỏi hồng thương hiệu.
- **Chạm và nhập trên điện thoại**: `min-h-11` gần như khắp nơi, ô nhập 16 px (không bị iOS phóng to), `touch-action: manipulation`, safe area, `overscroll-behavior`.
- **Số**: lớp `.num` bật `tnum`, định dạng `1.200.000 ₫` và `1,2 triệu`, ngày `23/11`.
- **Trung thực với dữ liệu**: "Chưa có dự báo", "Ước lượng ban đầu", "Số liệu cũ", nhóm tin cậy thay cho phần trăm tự nghĩ; skeleton có hình dạng gần với nội dung thật.
- **Dùng chung**: `ForecastBlock` và `AffordCard` dùng cho cả màn chính lẫn chat, đúng nguyên tắc liên tục của HIG.
- **Khả năng tiếp cận của biểu đồ**: `role="img"` kèm mô tả, dòng đọc số `aria-live`, thanh trượt thay cho thao tác kéo trên biểu đồ.
- **Hình ảnh gắn với chủ đề**: hũ thủy tinh có mực nước và vạch "dự báo" là thứ riêng của Yofina, không phải thanh tiến độ chung chung.
- Recharts tải lười, `prefers-reduced-motion` đã có ở mức toàn cục.

### 3.2 Các vấn đề cụ thể

| # | Màn, thành phần (file) | Vấn đề | Vì sao quan trọng | Ưu tiên |
|---|---|---|---|---|
| 1 | Toàn app (`index.css`: `--brand-deep`, `--text-brand`; `BalanceCard.tsx` gradient) | Mã `#A50064` trùng mã màu logo MoMo. Các hồng khác (`#C8207E`, `#D82D8B`) cùng hue OKLCH 353° với nó. | Yêu cầu là "mã riêng, không dùng thương hiệu MoMo". Thẻ số dư là thứ giám khảo thấy đầu tiên. | P0 |
| 2 | Tổng quan (`OverviewPage.tsx`, `BalanceCard.tsx`) | Thẻ số dư gradient chữ 34 px chiếm khoảng 260 px; thông điệp của cảnh 1 (hũ Ăn uống cạn) nằm trong thẻ trắng phía dưới, tiêu đề 16 px. Thẻ số dư còn kèm bảng ba dòng "Trong các hũ / Tiền vào khác / Chưa phân loại" và bốn nút. | Mỗi màn chỉ nên có một thứ nổi nhất (frontend-design). Ở cảnh 1, thứ đó là "12 ngày trước lương hũ trống", không phải tổng số dư. | P0 |
| 3 | Tổng quan, hàng hành động nhanh (`QuickActions`) | Nút "Kiểm tra · Sắp có" bị tắt, mờ 60%. | Thứ trông như bấm được thì phải bấm được (Vercel). Trong buổi demo đây là chỗ hỏng thấy rõ. | P0 |
| 4 | Thẻ chủ động (`MiniTimeline.tsx`) | Thanh 10 px: phần xanh "còn tiền", phần cam sau ngày cạn. Nhãn "Cạn dự kiến" đặt bằng `marginLeft` kẹp tối đa 70% nên lệch khỏi chấm khi ngày cạn gần lương. Không có mốc "hôm nay". Số ngày hũ trống (12) không hiện thành số. | Đây là "dòng thời gian" mà kịch bản cảnh 1 nhắc tới. Thanh mảnh đọc khó trên máy chiếu; xanh chiếm phần lớn thanh cho cảm giác "ổn" trong khi chip ghi "Cần xử lý". | P0 |
| 5 | Biểu đồ dự báo (`ForecastChart.tsx`) | Mọi `Area` và `Line` đều `isAnimationActive={false}`; đường "Sau" hiện tức thì. Nhãn mốc 10,5 px, nhãn trục 11 px (dưới mức 12 px của Figma). Đường mốc nghĩa vụ dùng `--status-warn-line` `#E39A00`, chỉ 2,36:1 trên nền trắng. | Kịch bản cảnh 2 ghi "biểu đồ dịch chuyển". Đồ họa mang nghĩa cần từ 3:1 (WCAG 1.4.11). | P0 |
| 6 | Kết quả cú sốc (`StressResult.tsx`, `StressResultScreen.tsx`) | Không có đồng hồ điểm; "58 → 34" là một dòng chữ 18 px, chỉ số sau đếm xuống. "Trụ được 27 ngày" là một dòng `dl` cỡ 13 px như các dòng khác. | Cảnh 3 xoay quanh "điểm tụt, hiện số ngày trụ được". Hai con số này cần là thứ to nhất màn. | P0 |
| 7 | Lộ trình (`Roadmap.tsx`, `RoadmapStep.tsx`) | Giai đoạn và bước là các hộp xám lồng nhau, không có trục thời gian. Mỗi bước có tới bốn nút (Chấp nhận, Sửa, Từ chối, Thực hiện), 6–8 bước là hơn 20 nút. Trạng thái "Chờ" dùng chip vàng, vốn là màu của "sát". | Nội dung là trình tự thật nên hợp với dòng thời gian có đánh số. Quá nhiều nút làm loãng việc chính. Dùng màu "sát" cho "chờ" làm sai nghĩa màu. | P0 |
| 8 | Hũ thủy tinh (`JarGlass.tsx`) | Nước có `transition` 700 ms nhưng lần vẽ đầu đã ở mức cuối, nên không bao giờ thấy nước dâng. Vệt sáng `#fff` cố định, trên nền tối thành vệt trắng gắt. Chữ "dự báo" 11 px, và ở thẻ 148 px thì bị cắt mất chữ cuối khi phóng 12 px. | Hũ là hình ảnh riêng của sản phẩm; một lần nước dâng khi mở là khoảnh khắc rẻ mà đáng nhớ. | P1 |
| 9 | Dải thẻ hũ ở Tổng quan (`OverviewPage.tsx`) | Thứ tự theo API; tab Nhìn trước đã có `sortByRisk` nhưng Tổng quan không dùng. Thẻ rộng 180 px, chỉ thấy khoảng hai thẻ. | Hũ hụt nên đứng đầu để khớp với thẻ cảnh báo phía trên. | P1 |
| 10 | Khối dự báo trong chat (`ForecastBlock.tsx`) | Một khối gồm tóm tắt, chip, dòng đọc số, biểu đồ, thanh trượt, chú giải, hai danh sách mốc, lưới bốn chỉ số và chân khối. Trong sheet 60% phải cuộn nhiều lần. | HIG: giữ biểu đồ đơn giản, chi tiết thì người dùng tự mở. Fintech: số chính trước, chi tiết sau. | P1 |
| 11 | Bốn thành phần điểm và danh sách cú sốc (`ScoreRow.tsx`, `ShockCard.tsx`) | `ScoreRow` chỉ có chữ, không có thanh (Figma R3 có thanh). `ShockCard` là các hàng chữ giống nhau, không biểu tượng. | So sánh bốn con số bằng thanh nhanh hơn đọc chữ. Ô cú sốc là lời mời bấm của cảnh 3. | P1 |
| 12 | Sheet chat, lúc trống (`ChatSheet.tsx`) | Thẻ "Mình làm được / Mình chưa làm" đứng trước gợi ý; ở mức sheet 0,6 các gợi ý nằm dưới mép màn. Gợi ý là hộp viền cao 48 px, rộng hết. Chip "Do AI tạo" hiện ở đầu sheet và sau mỗi câu trả lời. | Người dùng mở chat để hỏi; gợi ý bấm được nên ở trên. Nhãn lặp lại nhiều lần thì mất tác dụng. | P1 |
| 13 | Chữ trạng thái (`lib/jar.ts`, `ProactiveCard.tsx`, `RoadmapStep.tsx`) | Cùng một trạng thái có ba cách gọi: "Hụt" / "Cạn ngày 23/11" / "Cần xử lý"; "Đủ" / "Đủ tới kỳ lương" / "Thông tin"; "Sát" / "Sát, cần nhắc". | Từ vựng thống nhất giúp người dùng học app (frontend-design, phần viết). "Sát, cần nhắc" khó hiểu. | P1 |
| 14 | Nút (`components/ui/button.tsx`) | Lớp gốc có `transition-all`; nhấn chỉ dịch 1 px. | Vercel: không bao giờ `transition: all`. Nhấn thu nhỏ 0,97 cho cảm giác chạm rõ hơn. | P1 |
| 15 | Chế độ tối (`index.css`, `index.html`) | Bộ token tối viết hai lần (trong media query và trong `[data-theme="dark"]`), dễ lệch nhau khi sửa. Không có nút chuyển chế độ trong app (máy chiếu demo hay ở chế độ sáng). `theme-color` cứng theo mã cũ. Màu hũ Đi lại `#2FA3D6` (2,86:1) và Du lịch `#1FA6A0` (2,99:1) dưới 3:1 trên nền trắng. | Đổi bảng màu ở hai chỗ là nguồn lỗi. Mực nước hũ là đồ họa mang nghĩa. | P2 |

Ghi chú thêm, chưa xếp thành vấn đề riêng: màn trace (`OpsTracePage.tsx`) vẽ thanh thời lượng của mọi bước đều bắt đầu từ mép trái, nhìn giống waterfall nhưng không phải; hợp đồng chỉ có `ms` cho từng bước, không có thời điểm bắt đầu. `text-note` 12/16 hơi chật cho chữ có dấu chồng như "ữ", "ẫ".

## 4. Hệ thiết kế đề xuất

Nguyên tắc: **giữ nguyên tên biến CSS**, chỉ đổi giá trị và thêm vài biến mới, để việc đổi bảng màu là một diff trong `index.css`.

### 4.1 Bảng màu

Hướng màu: hồng ngả sang hồng sen (hue OKLCH khoảng 2°, của MoMo là 353°), chữ màu mực mận thay cho đen, nền ngả hồng rất nhẹ. Khoảng cách màu so với `#A50064` (ΔE OKLab × 100): `brand` 8,7; `brand-text` 9,0; `brand-deep` 13,0; `brand-vivid` 17,7. Bản tối dùng `brand-text` `#FEA6C5` (ΔE 35,8).

| Token (tên biến hiện có) | Sáng | Tối | Dùng cho |
|---|---|---|---|
| `--bg-app` | `#FBF5F8` | `#1A0D14` | Nền app |
| `--bg-surface` | `#FFFFFF` | `#281821` | Thẻ |
| `--bg-surface-2` | `#F3EAEF` | `#37232E` | Ô trong thẻ, thanh nền |
| `--bg-tint` | `#FFEAF1` | `#4D1E30` | Nền chip AI, nút mềm |
| `--border-default` | `#E8DCE2` | `#47323D` | Đường chia, viền trang trí |
| `--border-strong` (mới) | `#967E8B` | `#816A76` | Viền ô nhập, viền cần nhìn thấy |
| `--text-primary` | `#2B1823` | `#F7EFF3` | Chữ chính |
| `--text-secondary` | `#5D4452` | `#CAB8C1` | Chữ phụ (đậm hơn bản cũ `#6E5A66` cho màn ngoài trời) |
| `--text-tertiary` (mới) | `#725B68` | `#B39DA9` | Chú thích 12 px |
| `--text-on-brand` | `#FFFFFF` | `#FFFFFF` | Chữ trên nút hồng |
| `--brand-primary` | `#C8276A` | `#C8276A` | Nút chính, FAB, tab đang chọn |
| `--text-brand` | `#821041` | `#FEA6C5` | Chữ liên kết, chữ thương hiệu |
| `--brand-deep` | `#6E113D` | `#550A2E` | Đầu gradient thẻ số dư |
| `--brand-vivid` | `#E4518F` | `#E4518F` | Chỉ trang trí, không đặt chữ nhỏ lên |
| `--accent-blue` | `#3050C8` | `#93A9FF` | Đường dự báo, dải 80% |
| `--accent-blue-tint` | `#EAEFFF` | `#1E2752` | Nền chip thông tin |
| Đủ: `fg` / `bg` / `line` | `#0A6B45` / `#E0F3E9` / `#00A166` | `#5AD6A6` / `#10342A` / `#5AD6A6` | Trạng thái đủ |
| Sát: `fg` / `bg` / `line` | `#8A4B00` / `#FFF0D1` / `#C78200` | `#FFC55E` / `#3A2B0E` / `#FFC55E` | Trạng thái sát |
| Hụt: `fg` / `bg` / `line` | `#AE2F0E` / `#FFE8DE` / `#E04F1A` | `#FF9166` / `#3D1F15` / `#FF9166` | Trạng thái hụt |

Tỷ lệ tương phản đã tính (WCAG 2.x, chữ thường cần từ 4,5; đồ họa và viền ô nhập cần từ 3):

| Cặp | Sáng | Tối |
|---|---|---|
| Chữ chính trên nền app / trên thẻ | 15,52 / 16,70 | 16,73 / 14,96 |
| Chữ phụ trên nền app / thẻ / surface-2 | 8,09 / 8,70 / 7,38 | 10,02 / 8,96 / 7,72 |
| Chữ chú thích trên thẻ / nền app / surface-2 | 6,16 / 5,72 / 5,22 | 6,69 / 7,48 / 5,76 |
| Chữ trắng trên `brand-primary` | 5,31 | 5,31 |
| Chữ trắng trên `brand-deep` | 11,60 | 14,29 |
| Chữ trắng trên `brand-vivid` (chỉ chữ lớn, từ 3) | 3,58 | 3,58 |
| `text-brand` trên thẻ / nền app / tint | 10,00 / 9,30 / 8,71 | 9,23 / 10,32 / 7,43 |
| `accent-blue` trên thẻ / trên tint xanh | 6,76 / 5,89 | 7,53 / 6,38 |
| Đủ: chữ trên nền đủ / trên thẻ | 5,67 / 6,56 | 7,50 / 9,34 |
| Sát: chữ trên nền sát / trên thẻ | 6,04 / 6,80 | 8,75 / 10,78 |
| Hụt: chữ trên nền hụt / trên thẻ | 5,56 / 6,54 | 6,76 / 7,64 |
| Nét đủ / sát / hụt trên thẻ (đồ họa) | 3,34 / 3,17 / 3,96 | 9,34 / 10,78 / 7,64 |
| `border-strong` trên thẻ | 3,71 | 3,42 |
| `brand-primary` trên nền app / thẻ (nút như đồ họa) | 4,94 / 5,31 | 3,56 / 3,18 |

So với bản hiện tại: nét "sát" `#E39A00` chỉ 2,36 và nét "đủ" `#12A877` 3,05 trên nền trắng; bản đề xuất đưa cả ba nét lên trên 3. Chữ "đủ" trên nền đủ từ 4,71 lên 5,67.

**Màu hũ**: giữ năm màu, sửa hai màu dưới 3:1 trên nền trắng: Đi lại `#2FA3D6` → `#0085BC` (4,13), Du lịch `#1FA6A0` → `#008E89` (4,01). Bản tối giữ như hiện tại. Ăn uống `#7C5CE0` và Giải trí `#B05CE0` khá gần nhau; vì hũ luôn có biểu tượng và tên nên chấp nhận được, ghi lại để tính sau.

**Gradient thẻ số dư**: `radial-gradient(130% 150% at 0% 0%, var(--brand-deep), var(--brand-primary) 72%)` thay cho gradient chéo hai màu. Điểm sáng nhất là `#C8276A` nên chữ trắng tối thiểu 5,31 ở mọi chỗ.

### 4.2 Kiểu chữ

**Giữ Plus Jakarta Sans Variable** (đang cài qua `@fontsource-variable`). Đã kiểm file trên Google Fonts:

| Font | Subset tiếng Việt | Tính năng `tnum` | Bề ngang chữ số 0 và 1 (đơn vị/1000) |
|---|---|---|---|
| Plus Jakarta Sans | Có | Có | 708 và 403 khi mặc định, đều nhau khi bật `tnum` |
| Be Vietnam Pro | Có | **Không** | 700 và 431, không có cách làm đều |

Be Vietnam Pro được thiết kế cho tiếng Việt nhưng không có chữ số đều bề ngang, nên số dư khi đếm sẽ nhảy ngang và cột số không thẳng hàng. Plus Jakarta Sans có đủ subset tiếng Việt và `tnum`, đã dựng khắp Figma. Nếu muốn đổi font thì cần một font khác có cả hai.

Thang chữ đề xuất (cỡ / dòng, độ đậm):

| Vai | Hiện tại | Đề xuất | Ghi chú |
|---|---|---|---|
| Số anh hùng (số dư, "12 ngày", điểm, số ngày trụ) | 34/40 ExtraBold | **40/44**, 800, `letter-spacing: -0.02em` | Chỉ dùng cho số, không cho chữ có dấu chồng |
| Ký hiệu `₫` cạnh số lớn | cùng cỡ | 0,55em, 600 | Số là nhân vật chính |
| Tiêu đề màn | 24/32 | giữ | |
| Tiêu đề khối | 18/26 | giữ | |
| Tiêu đề nhỏ | 16/24 | giữ | |
| Thân | 15/22 | giữ (tỷ lệ 1,47 đủ cho dấu chồng) | |
| Phụ | 13/18 | 13/19 | |
| Chú thích | 12/16 | **12/18** | Chừa chỗ cho "ữ", "ẫ", "Ặ" |
| Nhãn trên biểu đồ | 10,5–11 | **12**, 600–700 | Tối thiểu 12 như Figma |

Không dùng ALL CAPS cho nhãn; không dùng chữ đơn cách (monospace) cho số liệu nhỏ.

### 4.3 Khoảng cách

Lưới 4 px: `4, 8, 12, 16, 20, 24, 32, 40`. Lề màn 16. Đệm thẻ 16 (thẻ chính 20). Khoảng cách giữa các phần trong màn 24. Trong thẻ: 12 giữa các nhóm, 8 giữa nhãn và giá trị, 4 giữa dòng chính và dòng phụ. Khoảng cách giữa hai vùng chạm liền nhau tối thiểu 8.

### 4.4 Bo góc

Bo theo thứ bậc thay vì một bán kính cho mọi thứ:

| Thành phần | Bán kính |
|---|---|
| Sheet, thẻ số dư | 28 |
| Thẻ thường | 24 (giữ) |
| Ô bên trong thẻ (bước lộ trình, cột trước và sau) | 16 |
| Ô nhỏ (ngày trong dải ngày, ô nhập) | 7–14 |
| Nút, chip, ô nhập chat | tròn hẳn (viên thuốc) |

Quy tắc lồng: bán kính con bằng bán kính cha trừ đệm (24 − 8 = 16).

### 4.5 Đổ bóng

| Token | Sáng | Tối |
|---|---|---|
| `--elev-card` | `0 1px 2px rgba(43,24,35,.05), 0 8px 24px -12px rgba(43,24,35,.18)` | `0 1px 2px rgba(0,0,0,.35)` kèm viền `1px rgba(255,255,255,.06)` |
| `--elev-hero` (mới, thẻ số dư và FAB) | `0 2px 4px rgba(110,17,61,.12), 0 18px 36px -14px rgba(110,17,61,.45)` | `0 18px 36px -16px rgba(0,0,0,.7)` |
| `--elev-sheet` | giữ | giữ |

Bóng ngả theo màu mận của thương hiệu, không dùng xám trung tính. Trong tối, độ cao thể hiện bằng tông surface (bg → surface → surface-2) và viền mảnh, như M3.

### 4.6 Chuyển động

Token:

```css
--ease-out: cubic-bezier(0.2, 0, 0, 1);    /* vào, mở, dữ liệu xuất hiện */
--ease-in: cubic-bezier(0.3, 0, 1, 1);     /* thoát, đóng */
--ease-pop: linear(0, 0.36 12%, 0.88 30%, 1.06 45%, 1.01 62%, 1); /* gần giống spring, cho dấu tích và chấm ngày cạn */
--dur-1: 120ms;  /* nhấn */
--dur-2: 200ms;  /* chip, đổi màu, thoát */
--dur-3: 320ms;  /* mở rộng thẻ, sheet */
--dur-4: 800ms;  /* dữ liệu: đếm số, vẽ đường, đồng hồ, nước dâng */
```

Quy tắc:

- Chỉ animate `transform`, `opacity`, `stroke-dashoffset`. Không `transition: all`.
- Chuyển động dữ liệu chạy **một lần** khi khối xuất hiện lần đầu trong phiên (cờ trong `sessionStorage`), không chạy lại mỗi lần quay về tab, theo HIG về thao tác lặp lại.
- Lệch nhịp 30–40 ms mỗi mục, tối đa 7 mục (7 hũ). Toàn chuỗi không quá 1,2 giây.
- Số đang đếm không phải dữ liệu: phần tử có `aria-label` bằng số cuối do server trả, phần đang chạy để `aria-hidden`. Bấm hoặc cuộn thì nhảy thẳng tới số cuối.
- `prefers-reduced-motion`: hiện thẳng trạng thái cuối (CSS toàn cục đã có; hook đếm số cũng phải kiểm, như `AnimatedNumber.tsx` đang làm).
- Nhấn: `transform: scale(0.97)` trong `--dur-1`.

## 5. Bố cục và khoảnh khắc chính cho 6 cảnh demo

Ràng buộc chung: chỉ sửa phần hiển thị; mọi số lấy từ trường đã có trong hợp đồng; không thêm trường, không đổi `type` khối. Những số "suy ra" chỉ là hiệu hai ngày server trả (như `ForecastBlock` đang tính khoảng trống từ ngày cạn tới lương).

### Cảnh 1 (0:00–0:30) · Tổng quan: "hũ Ăn uống cạn 23/11, còn 12 ngày nữa mới có lương"

```
┌ Chào buổi sáng · Minh ─────────────── ┐
│ ╭ Tổng số dư ───────────────────── ◉ ╮│  thẻ gọn: bỏ bảng 3 dòng (vào nút "Chi tiết")
│ │ 8.260.000 ₫   (đếm lên 0,8 s)      ││  3 nút: Chuyển tiền · Tiền vào · Giữa hũ
│ │ Ví mô phỏng · 21/11/2026           ││
│ ╰ [Chuyển] [Tiền vào] [Giữa hũ] ─────╯│
│ ┌ Việc cần làm hôm nay        Để sau ┐│
│ │ Hũ Ăn uống sắp cạn          ↘ Hụt  ││
│ │ 12 ngày  hũ trống trước kỳ lương   ││  số 40 px, màu hụt
│ │      Cạn 23/11                     ││
│ │ ▢▢●▨▨▨▨▨▨▨▨▨▨▨■   (15 ô ngày)       ││  ô hiện lần lượt, chấm cạn bật ra
│ │ Hôm nay 21/11            Lương 5/12││
│ │ [Xem cách bù] [Hỏi vì sao]         ││
│ └────────────────────────────────────┘│
│ Hũ của bạn   (hũ hụt đầu tiên, nước dâng lệch nhịp)
└───────────────────────────────────────┘
```

- **Khoảnh khắc chính**: một chuỗi duy nhất khi mở app: số dư đếm lên (0,8 s), cùng lúc các ô ngày hiện lần lượt từ trái sang (32 ms mỗi ô), chấm "Cạn 23/11" bật ra, rồi "12 ngày" hiện. Nước trong các hũ dâng từ đáy, lệch 40 ms mỗi hũ.
- **Dữ liệu**: `app_date`, `next_payday.date`, `jar.runout_date` (đã truyền vào `MiniTimeline`); 12 = hiệu ngày cạn và ngày lương.
- **File**: `components/MiniTimeline.tsx` (viết lại thành dải ngày, giữ nguyên props), `components/ProactiveCard.tsx` (dòng số lớn khi `kind === 'runout_warning'`), `components/BalanceCard.tsx` (đếm số, thu gọn bảng ba dòng), `pages/OverviewPage.tsx` (bỏ nút "Kiểm tra", sắp hũ theo rủi ro), `components/JarGlass.tsx` (nước dâng khi mount, vệt sáng theo token). Xem mẫu ở [ui-design-preview.html](ui-design-preview.html).

### Cảnh 2 (0:30–1:15) · "Nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao?"

```
Dự báo hũ Giải trí                     ↘ Hụt
Nếu mua tai nghe 1,2 triệu (Trả sau)
┌ Trước ─────────┐  ┌ Sau ────────────┐
│ ✓ Đủ           │  │ ↘ Hụt 410.000 ₫ │   số hụt to, màu hụt
│ đủ tới 5/12    │  │ khi lương về    │
└────────────────┘  └─────────────────┘
[biểu đồ: đường Trước đứt nét; đường Sau hồng vẽ dần trái → phải, vùng chênh tô theo]
Chi phí thật: 1.200.000 + 33.000 phí = 1.233.000 ₫ (đến hạn 5/12)
[Phương án 1 · Gợi ý]  [Phương án 2]
```

- **Khoảnh khắc chính**: đường "Trước" có sẵn, đường "Sau" và vùng chênh vẽ dần trong 700 ms, chấm "Sau: cạn" bật ra cuối. Đây là câu "biểu đồ dịch chuyển" của kịch bản.
- **Cách làm**: trong `ForecastChart.tsx` bật `isAnimationActive` chỉ cho `Line dataKey="after"` và `Area dataKey="gap"` (`animationDuration={700}`, `animationEasing="ease-out"`), các lớp khác vẫn tắt; nhãn lên 12 px; đường mốc nghĩa vụ dùng nét "sát" mới. `CompareSummary` trong `ForecastBlock.tsx`: số hụt và ngày cạn lớn hơn. `ObligationImpactBody.tsx`: viết tổng chi phí dạng phép cộng, phần phí in đậm.
- **Dữ liệu**: `compare.after`, `compare.delta`, khối `obligation_impact` (đã có).

### Cảnh 3 (1:15–1:45) · "Mất việc 2 tháng"

```
Nhìn trước
┌ Điểm chống chịu ─────────┐   ┌ Thử cú sốc ─────────────┐
│     ◠◠◠ 58/100  Vừa      │   │ [icon] Mất việc 2 tháng │  ô 2 cột có biểu tượng
└──────────────────────────┘   │ [icon] (cú sốc khác)    │
                               └─────────────────────────┘
Mô phỏng cú sốc
┌ Mất việc 2 tháng                    ↘ Hụt ┐
│        ◠◠◠  58 → 34   Vừa → Yếu          │  cung chạy từ 58 xuống 34, màu đổi theo nhóm
│ Trụ được                                  │
│ 27 ngày  ▓▓▓▓▓▓▓▓▓░░░░░░░░░░ 60           │  số 40 px, thanh 27/60
│ Riêng hũ Dự phòng: 9 ngày                 │
│ Thiếu 9.740.000 ₫ từ ...                  │
└───────────────────────────────────────────┘
[Xem lộ trình thích ứng]
```

- **Khoảnh khắc chính**: cung đồng hồ rút từ 58 xuống 34 (`stroke-dasharray` chuyển trong 900 ms), số đếm xuống cùng nhịp (`AnimatedNumber` đã có), màu chuyển từ "vừa" sang "yếu"; sau đó thanh "trụ được" chạy tới 27/60.
- **Dữ liệu**: `score_before`, `score_after`, `band_before`, `band_after`, `runway_days_total`, `horizon_days`, `runway_days_emergency`, `shortfall_vnd` của `stress_result` (đã có). Thanh dài theo `runway_days_total / horizon_days`.
- **File**: `features/resilience/ResilienceGauge.tsx` (thêm prop `from`), `StressResult.tsx` (bố cục mới), `ShockCard.tsx` và `ResilienceSection.tsx` (ô hai cột, biểu tượng theo `shock_id`, không khớp thì dùng biểu tượng chung), `ScoreRow.tsx` (thanh điểm).

### Cảnh 4 (1:45–2:20) · Lộ trình sinh lại, "Vì sao", từ chối đúng phạm vi

```
Lộ trình · Phiên bản 3                    ✦ Mới
[Đề xuất · chờ bạn chọn] [⚠ Khả thi sau điều chỉnh]
Chi ăn uống tuần qua cao hơn kế hoạch...
Tuần này · 21–30/11
 ●─ Bù hũ Giải trí trước hạn Trả sau
 │  410.000 ₫  (Du lịch) → (Giải trí)
 │  Đã chấp nhận · hạn 26/11
 ②─ Giảm ăn ngoài cuối tuần
 │  150.000 ₫ mỗi tuần
 │  [Chấp nhận] [Sửa, từ chối…]   Vì sao bước này?
Kỳ lương 5/12
 ③─ Giữ trước cho hũ Dự phòng  500.000 ₫
```

- **Khoảnh khắc chính**: bấm "Chấp nhận" thì nút tròn đổ đầy màu đủ, dấu tích tự vẽ (`stroke-dashoffset` 320 ms), đoạn trục tới bước kế đổi màu. Bản mới có chip "Mới" và một dòng nêu lý do lập lại (lấy từ `reason.text`).
- **Gọn hơn**: mỗi bước một nút chính ("Chấp nhận" khi đang chờ, "Thực hiện" khi đã chấp nhận và có `action`), "Sửa" và "Từ chối" gộp vào nút "Sửa, từ chối…" mở drawer đã có (`RoadmapStepDialogs.tsx`). Chip "Chờ" đổi sang kiểu `info`, không dùng màu "sát".
- **Từ chối đúng phạm vi** ("nên mua cổ phiếu nào"): khối `notice` loại `out_of_scope` dùng tông xanh thông tin (không dùng màu lỗi), kèm chip gợi ý quay về lộ trình. Chỉ đổi kiểu trong `components/Notice.tsx`.
- **Dữ liệu**: `phases[].steps[]` với `status`, `amount_vnd`, `jar_code`, `to_jar_code`, `due_date`, `reason` (đã có).
- **File**: `features/roadmap/Roadmap.tsx`, `RoadmapStep.tsx`, `pages/RoadmapPage.tsx`.

### Cảnh 5 (2:20–2:50) · Chụp thông báo chuyển khoản, độ phủ tăng

```
┌ Độ phủ dữ liệu tăng ──────────────┐
│   ◯ 62%  →  ◉ 81%                 │  vòng cung chạy từ 62 lên 81, số đếm lên
│ +N dòng · chi ngoài ví (số server)│
│ Hũ có thêm lịch sử: Ăn uống, ...  │
│ Dự báo đã được tính lại.          │
│ [Xem dự báo cập nhật]             │
└───────────────────────────────────┘
```

- **Khoảnh khắc chính**: vòng độ phủ chạy từ `before` tới `after`, số đếm theo; bấm "Xem dự báo cập nhật" sang Chi tiết hũ, nơi vạch "dự báo" của hũ trượt tới mức mới (`JarGlass` đã có transition).
- **Dữ liệu**: `coverage_change.before`, `after`, `rows_added`, `external_spend_added_vnd`, `jars_affected` (đã có).
- **File**: `features/ingest/CoverageChange.tsx`; tách một `ArcGauge` dùng chung với `ResilienceGauge`.

### Cảnh 6 (2:50–3:00) · Trace cho đội sản phẩm

- **Khoảnh khắc chính**: trên đầu màn, một thanh ngang chia đoạn theo tỷ trọng thời lượng từng bước (router, tool, verifier), màu theo loại bước, ghi "3,9 s". Giám khảo thấy ngay thời gian đi đâu trong 10 giây của cảnh này. Nhãn ghi rõ "tỷ trọng thời lượng", không gọi là waterfall, vì hợp đồng không có thời điểm bắt đầu.
- **Dữ liệu**: `steps[].ms`, `duration_ms` (đã có).
- **File**: `pages/OpsTracePage.tsx` (hàm `Steps`, `Header`).

## 6. Danh sách việc

Ước lượng tính cho một người đã quen code, gồm sửa test vitest bị ảnh hưởng.

### P0: trước buổi demo (khoảng 14 giờ)

| Việc | File | Công |
|---|---|---|
| Đổi giá trị token màu theo §4.1 (cả hai khối tối), thêm `--border-strong`, `--text-tertiary`, `--elev-hero`; gradient thẻ số dư; `theme-color` | `src/index.css`, `components/BalanceCard.tsx`, `index.html` | 1 h |
| Bỏ nút "Kiểm tra · Sắp có" | `pages/OverviewPage.tsx` (`QuickActions`), test `overview.test.tsx` nếu đếm nút | 0,5 h |
| Dải ngày và số "12 ngày" cho thẻ cảnh báo cạn | `components/MiniTimeline.tsx`, `components/ProactiveCard.tsx` | 3 h |
| Số dư đếm lên một lần mỗi phiên; tách hook đếm dùng chung từ `AnimatedNumber` | `components/BalanceCard.tsx`, `features/resilience/AnimatedNumber.tsx` → `lib/` hoặc `components/` | 1,5 h |
| Đường "Sau" vẽ dần; nhãn biểu đồ 12 px | `features/forecast/ForecastChart.tsx`, `ForecastBlock.tsx` | 1,5 h |
| Đồng hồ 58 → 34 và thanh "trụ được" | `features/resilience/ResilienceGauge.tsx`, `StressResult.tsx` | 3 h |
| Lộ trình dạng dòng thời gian, một nút chính mỗi bước, chip "Chờ" kiểu info | `features/roadmap/Roadmap.tsx`, `RoadmapStep.tsx` | 3,5 h |

### P1: nên làm (khoảng 11 giờ)

| Việc | File | Công |
|---|---|---|
| Nước hũ dâng khi mở; vệt sáng theo token; nhãn "dự báo" 12 px và nới viewBox để không bị cắt | `components/JarGlass.tsx` | 1 h |
| Sắp dải hũ ở Tổng quan theo rủi ro (chuyển `sortByRisk` sang `lib/jar.ts`) | `pages/OverviewPage.tsx`, `pages/ForesightPage.tsx`, `lib/jar.ts` | 0,5 h |
| Vòng độ phủ 62% → 81%, `ArcGauge` dùng chung | `features/ingest/CoverageChange.tsx`, `features/resilience/ResilienceGauge.tsx` | 2 h |
| Thanh điểm cho bốn thành phần | `features/resilience/ScoreRow.tsx` | 1 h |
| Ô cú sốc hai cột có biểu tượng | `features/resilience/ShockCard.tsx`, `ResilienceSection.tsx` | 1,5 h |
| Chat lúc trống: gợi ý lên trước dạng chip, phần "làm được / chưa làm" thu gọn; chip "Do AI tạo" chỉ ở đầu sheet và trên khối | `chat/ChatSheet.tsx`, `chat/MessageList.tsx` | 1,5 h |
| Thống nhất chữ trạng thái: "Đủ", "Sát", "Hụt" kèm ngày ("Hụt · cạn 23/11"); bỏ "Cần xử lý", "Sát, cần nhắc" | `lib/jar.ts`, `components/ProactiveCard.tsx`, test liên quan | 1 h |
| Khối dự báo trong chat: mốc tiền và lưới chỉ số vào `<details>` "Chi tiết dự báo" | `features/forecast/ForecastBlock.tsx` | 1,5 h |
| Token chuyển động; nút bỏ `transition-all`, nhấn `scale(0.97)` | `src/index.css`, `components/ui/button.tsx` | 1 h |
| Thanh tỷ trọng thời lượng ở màn trace | `pages/OpsTracePage.tsx` | 1 h |

### P2: khi còn thời gian (khoảng 6 giờ)

| Việc | File | Công |
|---|---|---|
| Gộp hai khối token tối thành một (ví dụ dùng `light-dark()` hoặc một selector chung), thêm nút chọn Sáng/Tối/Theo máy ở Hồ sơ | `src/index.css`, `pages/ProfilePage.tsx`, `main.tsx` | 2 h |
| Sửa màu hũ Đi lại và Du lịch (bản sáng) | `src/index.css` | 0,5 h |
| Thang chữ: số anh hùng 40/44, `₫` nhỏ, chú thích 12/18 | `src/index.css`, các chỗ dùng `text-display` | 1 h |
| Bo góc theo thứ bậc và bóng ngả màu mận | `src/index.css` | 1 h |
| Cập nhật biến màu Figma và bảng ở `figma-ui-design.md` §2 theo bảng mới | Figma file `l9vWyORNRjDqiEOXqpbzYm`, `docs/research/figma-ui-design.md` | 1,5 h |

## 7. Điều chưa chắc, chưa kiểm

- Chưa chạy app; nhận xét về độ cao từng phần ở Tổng quan là ước lượng từ class Tailwind, chưa đo trên máy thật. Cần xem lại trên điện thoại sau khi làm P0.
- Chưa chạy `npm run build` và vitest. Một số test có thể kiểm chữ của chip ("Cần xử lý", "Sát, cần nhắc") hoặc số nút; việc P1 về chữ trạng thái phải sửa test cùng lúc.
- Tương phản tính theo WCAG 2.x. Vercel khuyên dùng APCA; chưa tính APCA.
- `#A50064` là mã màu logo MoMo theo worldvectorlogo và nhiều dự án mở; trang màu chính thức của MoMo Developers trả 403 nên chưa đối chiếu được. Dù vậy, việc trùng đúng mã với logo đã đủ lý do để đổi.
- Recharts 3 có thể không cho bật animation riêng từng series mượt như mô tả; nếu không được, phương án dự phòng là bọc đường "Sau" trong một `<g>` có `clip-path` hình chữ nhật chạy bề ngang từ 0 tới 100% bằng CSS.
- Font: kiểm trên file Google Fonts phục vụ, chưa mở file của gói `@fontsource-variable/plus-jakarta-sans` trong `node_modules`; cùng nguồn nên khả năng cao giống nhau.
- Bản xem trước HTML đã chụp bằng Chrome không giao diện (có và không có giảm chuyển động); chưa thử trên Safari iOS.

## 8. Nguồn (truy cập 24/11/2026)

- [anthropics/skills](https://github.com/anthropics/skills): `frontend-design`, `canvas-design`, `theme-factory`, `brand-guidelines` (SKILL.md, README)
- [anthropics/claude-plugins-official, plugin frontend-design](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/frontend-design) (thư mục cũ trong `anthropics/claude-code/plugins` nay chỉ còn README trỏ sang đây)
- [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill): SKILL.md, `quick-reference.md`, công cụ `search.py` (design system, product, typography, chart, ux)
- [vercel-labs/web-interface-guidelines](https://github.com/vercel-labs/web-interface-guidelines) (`AGENTS.md`), [vercel.com/design/guidelines](https://vercel.com/design/guidelines)
- Apple HIG: [Charting data](https://developer.apple.com/design/human-interface-guidelines/charting-data), [Motion](https://developer.apple.com/design/human-interface-guidelines/motion) (đọc qua bản JSON của trang)
- Material Design 3: [How the color system works](https://m3.material.io/styles/color/system/how-the-system-works), [Easing and duration](https://m3.material.io/styles/motion/easing-and-duration/tokens-specs), [Design a dark theme codelab](https://codelabs.developers.google.com/codelabs/design-material-darktheme) (trang M3 dựng bằng JS, chỉ đọc được đoạn trích từ kết quả tìm kiếm)
- [Eleken: Fintech UX best practices 2026](https://www.eleken.co/blog-posts/fintech-ux-best-practices), [Toptal: Mastering fintech UX](https://www.toptal.com/designers/ux/mastering-fintech-ux-case-study)
- [worldvectorlogo: MoMo](https://worldvectorlogo.com/logo/momo-2) (mã màu logo `#A50064`)
- Google Fonts CSS API cho Plus Jakarta Sans và Be Vietnam Pro (subset, file TTF để kiểm `tnum` và bề ngang chữ số)

## 9. Luật chữ (đợt p5/ui-c, 25/11/2026)

Chủ dự án: "chữ ít thôi, phần nào quan trọng thì để chữ, ưu tiên sự gọn gàng; phần nào chữ nhiều quá thì bỏ vào mục thu gọn, ai có nhu cầu xem thì bấm vào". Áp cho mọi màn và mọi khối trong chat.

**Hiện ngay**: tiêu đề ngắn, con số chính, nhãn trạng thái, nút hành động. Nếu thật cần thì thêm một câu phụ, tối đa khoảng 12 từ.

**Thu gọn, mặc định đóng**: đoạn giải thích; câu tóm tắt lặp lại điều biểu đồ đã nói; bảng bằng chứng; chú thích phương pháp; ghi chú "mô phỏng" dài; danh sách mốc chi tiết; nguồn trích.

**Không xóa, chỉ ẩn**: thông tin truy căn cứ số liệu vẫn nằm trong DOM. Câu tóm tắt của biểu đồ vẫn là phần `sr-only` (hoặc `aria-describedby`) để trình đọc màn hình đọc ngay; phần nhìn thấy nằm trong mục thu gọn.

**Cách làm**: dùng `components/ui/Disclosure.tsx`. Nút là `<button>` thật có `aria-expanded`, `aria-controls`, cao tối thiểu 44 px, bấm được bằng Enter và Space. Mũi tên xoay khi mở. Vùng nội dung mở bằng `grid-template-rows` từ 0fr lên 1fr trong `--dur-3`; khi đóng thì vùng có `inert`, `aria-hidden` và `visibility: hidden`. Có `prefers-reduced-motion` thì không có transition. Nút và vùng nội dung có thể đặt ở hai chỗ khác nhau bằng `useDisclosure`, `DisclosureButton`, `DisclosurePanel`. Nhãn ngắn, theo việc người dùng muốn biết: "Chi tiết", "Vì sao?", "Xem căn cứ", "Giả định", "Phí và nguồn", "Chi tiết dự báo".

**Nhãn trạng thái**: dùng chung một bộ "Đủ", "Sát", "Hụt" ở thẻ hũ, danh sách hũ, chi tiết hũ, B2 và thẻ kiểm tra. Hũ hụt có ngày cạn thì ghi "Hụt · cạn 27/11". Thẻ "Việc cần làm hôm nay" bỏ "Cần xử lý". Thẻ có trạng thái `ok` giữ "Thông tin", vì nó không nói về một hũ.

**Lời trả lời chữ của agent trong chat**: lời dài hơn 160 ký tự (khoảng 3 dòng ở 390 px) chỉ hiện 3 dòng đầu, kèm nút "Xem thêm" hoặc "Thu gọn". Phần này chỉ cắt bằng CSS (`line-clamp-3`), nên chữ vẫn đủ trong DOM. Lời đang chạy thì không cắt.

Đã áp ở các màn sau. Số từ đếm bằng Chrome headless trên `dev:mock` ở khổ 390×844, tính chữ nhìn thấy trên cả trang khi chưa bấm gì, không tính `sr-only` và phần đang thu gọn. Ảnh có hậu tố `-gon-truoc` và `-gon-sau` nằm ở [ui-round1/](ui-round1/).

| Màn | Từ hiện ngay (trước → sau) | Đã thu gọn |
|---|---|---|
| Tổng quan | 518 → 406 | Bảng ba dòng của số dư ("Chi tiết số dư"); câu lý do "Còn …, còn … ngày tới kỳ lương" của thẻ cạn ("Chi tiết"); câu tóm tắt B2, các mốc nghĩa vụ (viết gọn: "Hóa đơn: Tiền điện 26/11 · 300.000–450.000 ₫") và chú thích "Hũ tiết kiệm không hiện…" ("Chi tiết"); câu tóm tắt và câu "đủ trả" của B6 |
| Hũ | 100 → 85 | Chip trạng thái rút còn Đủ, Sát, "Hụt · cạn 27/11" |
| Chi tiết hũ | 240 → 191 | Câu tóm tắt dài thay bằng dòng ngắn "Cạn 27/11, 8 ngày trước lương 05/12."; câu đầy đủ, mốc tiền, bốn chỉ số chất lượng vào "Chi tiết dự báo"; lời nhắc thanh trượt rút còn "Chạm vào biểu đồ để xem từng ngày." |
| Nhìn trước | 242 → 182 | Mô tả từng cú sốc chỉ còn cho trình đọc màn hình (màn kết quả có mục "Giả định") |
| Mô phỏng cú sốc | 81 → 66 | Câu tóm tắt (chỉ `sr-only`); thêm mục "Giả định": mô tả cú sốc, số đường Monte Carlo |
| Chi tiết điểm chống chịu | 142 → 75 | Câu giải thích của từng thành phần (chạm hàng để mở); câu tóm tắt (chỉ `sr-only`) |
| Lộ trình | 310 → 292 | Lý do lập lại và số trước → sau ("Vì sao có bản này?"); "Vì sao" của từng bước nay nằm cùng hàng với nút bước ở 390 px |
| Hồ sơ | 606 → 448 | Câu giải thích và bảng bằng chứng của từng nhận xét ("Xem căn cứ"); lý do của việc nên làm ("Vì sao?"); giới thiệu bộ nhớ ("Bộ nhớ là gì?"); danh sách thứ bị xóa ("Xóa những gì?"); chính sách giữ tệp ("Tệp được giữ thế nào?") |
| Nghĩa vụ | 158 → 99 | Câu tóm tắt B6 ("Chi tiết"); điều kiện phí và nguồn ("Phí và nguồn") |
| Nạp dữ liệu | 89 → 48 | Đoạn giới thiệu rút còn một câu; loại tệp và giới hạn kích thước ("Nạp được gì?"). Phần đồng ý trước khi tải lên giữ nguyên |
| Chat, lúc trống | 147 → 63 | Gợi ý lên trước; "Mình làm được / chưa làm" vào "Mình làm được gì?" (cả khối `suggestions`) |
| Chat, khối dự báo (`forecast_timeline`) | 167 → 117 | Như Chi tiết hũ; câu "cùng dãy số ngẫu nhiên" vào "Vì sao so được?" |
| Chat, bảng Vì sao (`explain`) | khoảng 293 → 205 | Lý do xếp nhóm tin cậy ("Vì sao?"); "Chi tiết kỹ thuật" dùng Disclosure thay `<details>` |
| Chat, `behavior_insight` | khoảng 242 → 159 | "Xem căn cứ", "Vì sao?" như Hồ sơ |
| Chat, `citation` | khoảng 180 → 108 | Loại phí và câu trích ("Xem trích dẫn"); ghi chú mô phỏng rút còn một câu ngắn |
| Chat, `stress_result`, `resilience_score` | khoảng 144 → 102, 356 → 257 | Như màn Mô phỏng cú sốc và Chi tiết điểm chống chịu |
| Chat, `affordability_card`, `obligation_impact` | khoảng 309 → 280, 366 → 338 | Dòng "Dựa trên dự báo cập nhật…" ("Căn cứ"); phí theo nguồn và phạt trễ hạn ("Phí và nguồn") |
| Chat, lời chữ dài | 9 dòng → 3 dòng | "Xem thêm" |

Số của khối chat là hiệu giữa hai lần chụp liên tiếp, nên có lẫn câu hỏi thử và nhãn "Do AI tạo"; chỉ là ước lượng.