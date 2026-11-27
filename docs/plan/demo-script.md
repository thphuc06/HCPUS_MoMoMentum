# Kịch bản demo (video 3 phút)

Nguồn: proposal §15. Kể câu chuyện của persona **Minh** (22 tuổi, thu nhập 9 triệu/tháng, lương ngày 5, 8 hũ, một hạn mức Ví Trả Sau) qua 6 cảnh. Từ 26/11 sáng (issue #39) ví demo của Minh sau "Đặt lại dữ liệu" có **8 hũ**: ba hũ mặc định Chi hằng ngày, Nghĩa vụ (gộp Hóa đơn cũ), Dự phòng, rồi hũ tự thêm Ăn uống, Đi lại, Giải trí, Du lịch (hũ mục tiêu 6.000.000 ₫, hạn 01/04/2027), Đầu tư (0 ₫); tổng 8.030.000 ₫ (bảng ở mục "Yêu cầu dữ liệu"). Câu chuyện: tài khoản mới nhận 3 hũ mặc định, Minh tự thêm hũ cho khoản muốn theo dõi riêng. Tài khoản mới ngoài demo chỉ có 3 hũ Chi hằng ngày, Nghĩa vụ, Dự phòng. Số đo từng cảnh ở mục "Số đo 26/11" ngay dưới bảng. Giám khảo làm lại được từng cảnh bằng tài khoản demo có sẵn dữ liệu (§13: có nút đặt lại, phương án dự phòng tất định, video quay sẵn). Số trong bảng cảnh là lời dẫn; số thật lấy theo engine.

| Cảnh | Thời lượng | Trên màn hình | Tính năng |
|---|---|---|---|
| 1 | 0:00–0:30 | Mở app: dòng thời gian báo hũ Ăn uống (hũ tự thêm) cạn ngày 23, còn 12 ngày nữa mới tới kỳ lương, độ tin cậy "Cao" | F1 |
| 2 | 0:30–1:15 | Gõ "nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao". Biểu đồ dịch chuyển, hiện tổng chi phí thật và 2 phương án; hũ Nghĩa vụ báo thiếu cho Trả sau đến hạn 05/12, đúng ngày lương (khoản đến hạn ngày lương trả bằng số dư trước khi lương về, BR-22 chốt 26/11) | F2, F3 |
| 3 | 1:15–1:45 | Bấm "mất việc 2 tháng". Điểm chống chịu tụt (29 → 12), hiện số ngày trụ được | F4 |
| 4 | 1:45–2:20 | Tải sao kê 2 tuần gần nhất (CSV): các dòng tự vào hũ Ăn uống, xác nhận một lần. Bộ phát hiện xác nhận chi Ăn uống tăng từ 07/11, lộ trình sinh lại thành bản đề xuất mới: vẫn khả thi, Du lịch vẫn kịp hạn, bù một lần cho Ăn uống từ quỹ Dự phòng (ăn uống là khoản thiết yếu; quỹ không về 0), phần chia Ăn uống tăng theo mức chi thường ngày của Minh chứ không theo đợt ăn ngoài; mở So với bản cũ và bảng "Vì sao". Hỏi "nên mua cổ phiếu nào" và thấy trợ lý từ chối đúng phạm vi | F5, F6, suitability |
| 5 | 2:20–2:50 | Trên `giamkhao1`, nạp ảnh chứng từ mẫu `minh_bien_lai_1.png` (họ tên, số điện thoại, số tài khoản nhìn rõ): PII bị che → dòng giao dịch → gợi ý hũ → duyệt. Các bước ở mục "Cảnh 5" bên dưới | F6 |
| 6 | 2:50–3:00 | Trên **tài khoản giám khảo** (`giamkhao1`), ở câu trả lời vừa rồi bấm "Vì sao" → "Chi tiết kỹ thuật": trace của chính lượt đó (dữ liệu đã dùng, luật đã kiểm, độ tin cậy, thời gian từng bước tính bằng ms, số lượt gọi mô hình, token vào/ra). Tùy chọn, 2–3 giây cuối: bảng vận hành `/ops/summary` quay bằng tài khoản vận hành `minh` | Góc "Future Workspace" |

## Số đo 26/11

Hai nguồn:

- **Trên app**, ví **8 hũ** (`giamkhao1`): lượt kiểm sau deploy Runtime v34 (26/11 20:47–20:55, bản đang chạy: router Claude Haiku 4.5, Nova 2 Lite dự phòng) cho cảnh 2, 4; lượt v33 (26/11 18:53–19:07) cho cảnh 1 và để so; lượt v32 (26/11 16:12–16:34) để so; từ v32, Trả sau đến hạn 05/12 và sàn theo mức nền bền. Lượt kiểm sau v31 (26/11 sáng, Trả sau lúc đó còn ngày 3, sàn theo chi 30 ngày) cho cảnh 3, 5, 6, vì các lượt v32, v33, v34 không đi lại ba cảnh này. Đo cục bộ, cảnh 3 không đổi qua hai thay đổi đó. Số trên app rạng sáng 26/11 (ví 7 hũ) đã thay, xem [ai-log](../ai-log/2026-11.md).
- **Cục bộ**, 26/11 tối sau khi gộp đợt #39 (`int/integrate`; PostgreSQL cục bộ, ngày mô phỏng 21/11/2026, 10.000 đường, what-if 5.000 đường, model giả tất định cho lộ trình; `tests/local_pg/test_demo_scenes.py` và `test_roadmap_regen_scene4.py` với `-s`): ví **8 hũ**, Trả sau đến hạn 05/12, đúng ngày lương (phương án B), sàn phân bổ theo mức nền bền.

| Cảnh | Trên app (ví 8 hũ) | Cục bộ (ví 8 hũ, sau gộp #39) |
|---|---|---|
| 1 | v33 (như v32): thẻ "Hũ Ăn uống dự kiến cạn ngày 23/11 · Hụt · 12 ngày"; các hũ khác "Đủ", không tự mâu thuẫn | Ăn uống 380.000 ₫ cạn 23/11, nhóm `high` (Cao), thẻ Tổng quan vẫn là Ăn uống. Hũ Chi hằng ngày 300.000 ₫ "đủ", không nêu ngày cạn (hũ thưa), không có thẻ. Nghĩa vụ "đủ" |
| 2 | v34: trọn câu 24,3 giây, thiếu **1.167.673 ₫** như v33; phương án chuyển bù đúng **1.167.673 ₫**, bằng phần thiếu, từ Dự phòng sang Nghĩa vụ. v33: trọn câu 30,3 giây, cùng số thiếu; phương án Hoãn, Mua bằng hũ Du lịch, chuyển 1.167.673 ₫ từ Dự phòng sang Nghĩa vụ kèm lời giữ quỹ dự phòng cho việc gấp. v32: trọn câu 20,6 giây. Hũ Nghĩa vụ liệt kê Tiền điện 26/11 và Trả sau 05/12 (2.200.000 ₫: 1.000.000 ₫ có sẵn gồm phí 33.000 ₫, cộng 1.200.000 ₫), thiếu **1.167.673 ₫** (lệch 719 ₫ so với cục bộ) | Tiền điện 26/11 và Trả sau **05/12** (2.200.000 ₫, phí không cộng thêm), thiếu **1.168.392 ₫** (số dư trước khi lương về 1.031.608 ₫), hũ trả hụt cùng số, trạng thái Sau "hụt" (cạn 06/12). Trước khi mua: "đủ", không có khoản thiếu. Lời dẫn dùng "thiếu khoảng 1,17 triệu" |
| 3 | v31: điểm 29 → 12, trụ 26 ngày, thiếu 11.122.762 ₫ sau hai tháng | Điểm 29 → 12, trụ **26 ngày** (ví 7 hũ: 25 ngày; lệch do hũ mới: số dư cộng 300.000 ₫, chi 30 ngày cộng khoảng 210.000 ₫) |
| 4 | v34: 32 dòng tự thêm vào Ăn uống (3.416.000 ₫); Lambda sinh lại 19,7 giây; bản mới v4 kịp hạn, khác v2 ở 8 bước (thêm 3, bỏ 4, đổi 1); Dự phòng chuyển 362.000 ₫ sang Ăn uống, cùng khoản như v32, v33. v33: 32 dòng (3.416.000 ₫); Lambda sinh lại 18,9 giây; bản mới v4 "3 giai đoạn, 5 bước, kịp hạn"; Dự phòng chuyển 362.000 ₫ sang Ăn uống như v32, còn 2.338.000 ₫. Cả hai lượt ra v4 vì câu kiểm trước đó trên cùng tài khoản đã tạo v3; sau đặt lại là v3. v32: Lambda sinh lại 19,6 giây; bản mới "2 giai đoạn, 4 bước, kịp hạn", lý do "Chi Ăn uống mỗi tuần tăng từ 842.867 ₫ lên 2.650.526 ₫ và giữ mức đó 2 tuần": 21/11–05/12 chuyển 362.000 ₫ từ Dự phòng sang Ăn uống, giảm Chi hằng ngày 135.000 ₫; 05/12–05/01 đổi tỷ lệ Ăn uống 30 → 34,02%, giảm Giải trí 315.047 ₫. Dự phòng còn 2.338.000 ₫, không chữ thô | 32 dòng vào Ăn uống; PELT xác nhận (tệp hệ số 3,5, khi tải trong ngày và trễ một ngày). Ăn uống: chi 30 ngày 7.309.000 ₫, mức nền 3.827.143 ₫/tháng, sàn 3.061.714 ₫. LP **khả thi** ("đủ sàn mọi hũ, mục tiêu Du lịch kịp hạn"): Dự phòng giữ **900.000 ₫**, Du lịch 962.000 ₫, Ăn uống 2.700.000 → 3.062.000 ₫, Nghĩa vụ 3.102.047 ₫, Đi lại 524.000 ₫, Giải trí 314.953 ₫, Chi hằng ngày 135.000 ₫. Bản v3 (model giả): "3 giai đoạn, 4 bước, kịp hạn" (mục "Cảnh 4" bên dưới). Planner nhận dữ kiện đợt tăng của Ăn uống: từ 07/11 (điểm gãy PELT), đã xác nhận, dự báo cạn 23/11. Bản do model thật soạn: cột trên app |
| 5 | v31: màn duyệt sau 8,5 giây, `B***`, chip "Đã che: tên" | Không đo |
| 6 | v31: "Chi tiết kỹ thuật" hiện dữ liệu đã dùng, luật đã kiểm, độ tin cậy, 2 lượt gọi model, token vào/ra, thời gian từng bước; `giamkhao1` mở `/ops` thấy "Chỉ dành cho đội vận hành" | Không đo |

Các số phân loại 92% / 17,4%, cổng hiện % 47 / 120 ngày và ngưỡng PELT 2,04 đo trên ví nhiều hũ theo loại chi, nên đúng cho ví demo. Không dùng chúng để nói về tài khoản mới 3 hũ ([đo ví 3 hũ](../research/2026-11-26-do-vi-ba-hu.md)).

## Tài khoản dùng trong demo (issue #17)

- **Giám khảo** dùng `giamkhao1` (dự phòng `giamkhao2`, `giamkhao3`), cả ba là persona `minh`. Tài khoản giám khảo **không** thuộc nhóm Cognito `ops`: mở `/ops/summary` bị từ chối (server trả 403, màn "Chỉ dành cho đội vận hành"), vì bảng vận hành đọc trace của mọi người dùng. Truy vết của chính mình xem ở "Vì sao → Chi tiết kỹ thuật" (`frontend/src/features/explain/ExplainBody.tsx`).
- **Vận hành** (chỉ người trình bày, không đưa giám khảo): `minh`, khai ở `ops_accounts` của `data/personas/accounts.json`. Dùng cho đoạn quay ngắn bảng vận hành ở cảnh 6 và cho eval (`evals/run.py`). Mật khẩu chỉ nằm trong secret `yofina-demo-accounts`.
- Nhóm do `scripts/seed_demo.py` đặt theo `accounts.json`: chạy lại sẽ thêm `ops` cho `minh` và gỡ `ops` khỏi mọi tài khoản demo khác. Sau khi gỡ, token cũ còn nhóm `ops` tới khi hết hạn; đăng xuất rồi đăng nhập lại `giamkhao1` trước khi kiểm.

## Cảnh 4 chạy thật: tải sao kê để lộ trình sinh lại

Không dùng lộ trình hay dấu hiệu đổi hành vi seed. Sau khi đặt lại, `minh` (và `giamkhao1`–`3`, cùng persona) chỉ có v1 (đã thay) và v2 (đang dùng); bản đề xuất mới do bộ phát hiện thật tạo từ tệp sao kê (issue #22, số đo ở [2026-11-26-canh4-pelt.md](../research/2026-11-26-canh4-pelt.md)).

Tệp `minh_sao_ke_2_tuan.csv`: tải ở `/samples/minh_sao_ke_2_tuan.csv` trên app; bản trong repo là `data/personas/samples/minh_sao_ke_2_tuan.csv`, sinh bằng `data/personas/samples/make_scene4_csv.py`. Một tệp dùng cho cả bốn tài khoản persona `minh`.

1. Hồ sơ → **Đặt lại dữ liệu**. Làm cảnh 4 trong ngày đặt lại hoặc chậm nhất ngày hôm sau, và trước cảnh 5: tệp gắn với ngày mô phỏng 21/11/2026, ngày mô phỏng đi theo ngày thật kể từ lần đặt lại; tải trễ hai ngày trở lên thì PELT không xác nhận và không có lộ trình mới (không báo lỗi gì), phải đặt lại rồi tải lại. Nạp tệp khác vào hũ Ăn uống trước đó cũng làm đổi chuỗi chi.
2. Tải tệp về máy, mở **Nạp dữ liệu** → **Tải sao kê CSV** → chọn tệp → **Đồng ý và tải lên** (lần đầu sau khi đặt lại).
3. Chờ đọc xong: 32 dòng chi từ 07/11 tới 20/11 (16 dòng mỗi tuần, 1.660.000 ₫ tuần 07/11–13/11 và 1.756.000 ₫ tuần 14/11–20/11, tổng 3.416.000 ₫), mọi dòng đã chọn sẵn vào hũ Ăn uống (không phải chọn hũ từng dòng) → **Xác nhận thêm 32 dòng**.
4. Dự báo chạy lại ngay sau khi xác nhận. PELT xác nhận chi Ăn uống tăng từ khoảng 843.000 ₫ lên 2.651.000 ₫ mỗi tuần, giữ 2 tuần (tải ngày hôm sau: khoảng 868.000 ₫ lên 2.353.000 ₫), rồi lộ trình được sinh lại. Mục tiêu: thấy bản đề xuất mới trong 30 giây kể từ lúc xác nhận (trên app 26/11, `giamkhao1`: Lambda sinh lại 19,6 giây ở v32, 18,9 giây ở v33, 19,7 giây ở v34).
5. Mở **Lộ trình**: chip **Có phiên bản mới** → **So với bản cũ** (bản mới so với v2, lý do hành vi thay đổi) → mở "Vì sao"; chọn **Dùng bản mới** hoặc **Giữ bản cũ**.
6. Hỏi "nên mua cổ phiếu nào": trợ lý từ chối đúng phạm vi.

Tải lại cùng tệp sau khi đã xác nhận thì bị từ chối vì trùng tệp; muốn làm lại thì đặt lại dữ liệu. Rời màn khi chưa xác nhận rồi tải lại cùng tệp thì màn nạp báo tệp đang chờ duyệt và có nút **Duyệt tiếp** mở lại đúng lần nạp đó.

Trên ví 8 hũ, cả 32 dòng vẫn vào Ăn uống, không dòng nào vào Chi hằng ngày; hũ Chi hằng ngày là chuỗi thưa nên bộ phát hiện bỏ qua. Lần đo 26/11 ở [đo ví 3 hũ](../research/2026-11-26-do-vi-ba-hu.md) (mục 3) thấy tệp hiện hành vẫn được xác nhận trên hũ Ăn uống riêng khi tải trễ 2 và 3 ngày, khác câu ở bước 1; chưa tìm nguyên nhân, nên vẫn làm cảnh 4 trong ngày đặt lại.

Bản mới trên ví 8 hũ (đo cục bộ sau gộp #39, model giả tất định; phần số do engine quyết): phương án phân bổ khả thi, phần chia tính từ **mức chi nền** của Minh (trung vị chi theo tuần 12 tuần), không từ hai tuần ăn ngoài, nên Dự phòng giữ 900.000 ₫ và Du lịch nhận 962.000 ₫, kịp hạn 01/04/2027. Bản v3 "3 giai đoạn, 4 bước, kịp hạn": trước kỳ lương chuyển ngay 132.047 ₫ từ Chi hằng ngày sang Nghĩa vụ và đổi tỷ lệ Ăn uống từ 2.700.000 lên 3.062.000 ₫/tháng; sau kỳ lương giảm Chi hằng ngày từ 270.000 xuống 135.000 ₫; về đích nhắc xem lại ngày 05/03/2027. Planner nhận dữ kiện đợt tăng của Ăn uống (chi 30 ngày 7.309.000 ₫ so với mức nền 3.827.143 ₫, từ 07/11, đã xác nhận, dự báo cạn 23/11) và được dặn nói thật về nó; câu chữ và cách xử lý (khoản bù một lần, hỏi đợt tạm hay nhịp mới) là của model thật, chưa đo bằng eval nên xem trên app trước khi quay. Trên app model chọn bù một lần 362.000 ₫ từ Dự phòng sang Ăn uống (v32: ở giai đoạn đầu 21/11–05/12, phần chia hằng tháng của Dự phòng vẫn giữ; v33: cùng khoản; v34: cùng khoản, ở giai đoạn "Việc làm ngay trước kỳ lương"), Dự phòng còn 2.338.000 ₫ (số đọc ở v32, v33). Bước này hợp lệ theo luật giữ quỹ dự phòng cho bước lộ trình (`roadmap_agent._buffer_issue`, phần mở rộng của BR-42, ghi ở BR-64 của [quy tắc nghiệp vụ](../ba/02-business-rules.md)): luật chỉ chặn bước chuyển tiền từ quỹ dự phòng sang hũ chi **không** thiết yếu, còn Ăn uống thuộc nhóm hũ chi thiết yếu mặc định (`essential_jar_codes`, mặc định `yofina_core.wallet.DEFAULT_ESSENTIAL_CATEGORIES`: Ăn uống, Đi lại, Hóa đơn; bộ tối ưu gán vai `essential` cho các hũ này trong `pipelines/forecast/yofina_forecast/allocation.py`). Bước này cũng không kèm cảnh báo của luật `emergency_not_for_discretionary` (mức cảnh báo), vì luật đó chỉ xét khoản chi tiêu không thiết yếu, còn bước chuyển tiền của lộ trình được kiểm như một khoản để dành (`roadmap_agent._proposal`). Lời dẫn dưới vì vậy nói đúng khoản bù này, không nói quỹ dự phòng giữ nguyên.

Lời dẫn đề xuất: "Hai tuần qua Minh ăn ngoài nhiều hơn hẳn: chi Ăn uống 30 ngày gần nhất khoảng 7,3 triệu, gần gấp đôi mức thường khoảng 3,8 triệu mỗi tháng. Yofina thấy mức chi mới đã giữ hai tuần và tự lập lộ trình mới. Yofina không lấy quỹ dự phòng cho khoản chi không thiết yếu; ăn uống là khoản thiết yếu, nên lộ trình bù cho hũ Ăn uống 362.000 ₫ từ quỹ dự phòng, và quỹ vẫn còn hơn 2,3 triệu. Phần chia lương hằng tháng vẫn tính theo mức chi thường ngày của Minh chứ không theo hai tuần ăn ngoài, nên mục tiêu Du lịch vẫn kịp." Số 362.000 ₫ là của bản model soạn trên app (v32, v33, v34); lần sinh khác có thể chọn bước khác, nên đọc lại màn So với bản cũ trước khi quay và sửa lời dẫn theo số trên màn. Đo hệ số của tệp và số trước khi sửa sàn: [đo lại hệ số](../research/2026-11-26-canh4-pelt.md), mục "Hệ số và bản lộ trình sinh lại" và "Mức nền bền".

## Cảnh 5: ảnh chứng từ có PII (issue #16)

Ảnh mẫu dựng bằng Pillow, mọi tên và số đều hư cấu (chân ảnh ghi "dữ liệu hư cấu"). `data/personas/samples/make_samples.py` sinh ảnh từ spec `data/personas/samples/minh_receipts.json`: số tiền, ngày, giờ đi qua bộ sinh persona, và không trùng số tiền với giao dịch đã seed trong cửa sổ khử trùng. Ảnh được ghi vào `data/personas/samples/` và chép sang `frontend/public/samples/`, nên sau khi build và deploy frontend thì tải được ở `/samples/<tên tệp>` trên miền Amplify. Sinh lại: `uv run --with pillow python data/personas/samples/make_samples.py`.

| Tệp | Trên ảnh | PII nhìn rõ | Sau khi che (bộ che `yofina_core.pii`) |
|---|---|---|---|
| `/samples/minh_bien_lai_1.png` (quay video) | Chuyển khoản thành công 345.000 VND, 20/11/2026 07:24, nội dung "chuyen tien an lien hoan nhom" | người hưởng `BÙI QUỐC KHÁNH`, tài khoản nguồn `1027356824`, tài khoản hưởng `19038642097531`, SĐT `0901 234 567` | `B***`, `****6824`, `****7531`, `****4567` |
| `/samples/minh_bien_lai_2.png` (dự phòng) | Thanh toán hóa đơn tiền nước 126.000 VND, 20/11/2026 15:07, nhà cung cấp "Công ty Cấp nước Sông Xanh" | khách hàng `VÕ THỊ NGỌC TRÂM`, tài khoản nguồn `1027356824`, SĐT `0938 765 432` | `V***`, `****6824`, `****5432`; tên nhà cung cấp giữ nguyên (doanh nghiệp) |

Các bước:

1. Trước khi quay, bấm "Đặt lại dữ liệu" (trang Hồ sơ) trên `giamkhao1`. Ngày mô phỏng về 21/11/2026, nên ngày trên ảnh (20/11) là hôm qua. Đặt lại cũng xóa lần nạp trước. Nạp lại cùng ảnh mà chưa đặt lại thì hoặc bị từ chối là tệp đã nạp (`INGEST_DUPLICATE_FILE`), hoặc dòng hiện là trùng.
2. Mở `/samples/minh_bien_lai_1.png` trên máy quay và lưu ảnh về máy.
3. Trong app, mở Nạp dữ liệu (`#/ingest`) → "Chọn ảnh có sẵn" → chọn ảnh vừa lưu. Lần nạp đầu có hộp "Cho phép đọc ảnh": tích đồng ý → "Đồng ý và tải lên".
4. Màn chờ "Đang đọc các dòng và che thông tin cá nhân…" (cắt đoạn chờ trong video).
5. Màn duyệt: dòng chi 345.000 ₫ ngày 20/11, đối tác `B***`, không còn họ tên, số điện thoại hay số tài khoản đầy đủ. Dòng có chip "Đã che: tên" (thêm "SĐT", "số TK" nếu model chép các số đó vào nội dung), đầu danh sách có câu "Đã che N thông tin cá nhân trước khi lưu". Chip chỉ nêu loại, không bao giờ hiện giá trị gốc. Hũ gợi ý mong là Ăn uống. Đây là chuyển tiền cho người, nên hũ do model đề xuất từ nội dung và dòng ở trạng thái "Cần duyệt"; hũ trống hay sai thì chạm vào dòng để chọn Ăn uống. Ảnh 2 có loại "Tiền nước", hũ nhận là Nghĩa vụ (ví demo gộp Hóa đơn cũ vào Nghĩa vụ).
6. "Xong, cập nhật dự báo" → "Xác nhận thêm 1 dòng" → "Đã thêm các dòng ngoài ví". Số dư hũ không đổi. Khoản chi ngoài ví vào lịch sử chi của hũ, và dự báo được xếp lịch tính lại.

Độ phủ dữ liệu của Minh đã ở mức 100% trước khi nạp: tính offline trên 120 ngày lịch sử của bộ sinh, (chi 31.350.000 ₫ + số dư cuối 7.900.000 ₫) / thu nhập 36.000.000 ₫ vượt 1 nên bị kẹp về 1,0. Số này tính trước khi thêm hũ Chi hằng ngày; hũ mới chỉ cộng thêm vào tử số (số dư đầu kỳ và chi của hũ) nên độ phủ vẫn kẹp 1,0 [suy luận]. Vì vậy cảnh này không cho thấy độ phủ tăng. Trên AWS, độ phủ tính theo cửa sổ `forecast_history_window_days`, cần kiểm lại. Muốn thấy độ phủ tăng thì dùng persona `vy` với `vy_sao_ke_vcb.csv` (`data/personas/README.md`, mục "Tệp mẫu cho cảnh 5"); đo cục bộ trên ví 8 hũ của `vy` (26/11): 0,687 sau đặt lại, 0,862 sau CSV, 0,872 sau thêm ảnh.

Đã kiểm tất định (`tests/unit/test_persona_samples_minh.py`, không OCR, không gọi model): bộ che PII với payee và tên hiển thị của Minh che đủ họ tên, số điện thoại, số tài khoản trên chữ của hai ảnh, còn số tiền, nhà cung cấp, nội dung, mã tham chiếu thì giữ nguyên. Chưa kiểm: model đọc ảnh, hũ gợi ý, và số giây thao tác (issue #16 cần ≤ 10 s) trên tài khoản giám khảo sau khi deploy.

## Batch đêm: tính năng đang chạy thật, chưa có trong 6 cảnh (ghi chú 26/11)

Chủ dự án (26/11): batch đêm là một tính năng đáng nêu trong video, slide hoặc tờ hướng dẫn; hiện 6 cảnh ở trên không cảnh nào cho thấy nó.

- **Nó là gì**: nhịp "batch đêm" của proposal §10.4. EventBridge Scheduler `yofina-nightly-0200` (02:00 mỗi ngày, giờ Việt Nam) gọi Step Functions `yofina-nightly`: lấy danh sách người dùng đã khai lương, chạy lại dự báo từng người (10.000 đường, tối đa 3 người song song), rồi tổng kết; một người lỗi không làm hỏng người khác, có lỗi thì cả lần chạy thất bại để alarm báo về SNS `yofina-alerts`. Mã ở `pipelines/forecast/` (`batch.py`, `handler_batch.py`), mô tả ở [pipelines/nightly/README.md](../../pipelines/nightly/README.md).
- **Bằng chứng chạy thật** (đọc trên AWS sáng 26/11): 25 lần chạy gần nhất có 24 thành công, 1 thất bại. Các lần tự chạy theo lịch 02:00: 23/11 thành công (khoảng 22 giây), 24/11 thất bại (Aurora đang ngủ, issue #14), 25/11 thành công (khoảng 31 giây), 26/11 thành công (khoảng 33 giây). Bản sửa #14 (thử lại khi cơ sở dữ liệu chưa dậy) deploy tối 25/11.
- **Cách thể hiện không cần viết thêm mã**: quay vài giây màn lịch sử thực thi của Step Functions `yofina-nightly` bằng tài khoản vận hành (che account ID), hoặc đưa bảng các đêm ở trên vào slide; nói kèm một câu: "mỗi đêm hệ thống tự tính lại dự báo cho mọi tài khoản, nên sáng mở app là số mới". Đây cũng là chỗ nói về ba nhịp chạy: theo sự kiện (cảnh 4: nạp sao kê xong thì tính lại ngay), theo đêm (mục này), theo tuần (đã cắt, ADR-0004).
- **Đã xem 26/11**: job đêm tạo dự báo mới, điểm chống chịu của ngày mô phỏng mới, kiểm đổi hành vi (PELT, có thể sinh lộ trình đề xuất), hồ sơ hành vi do model viết và một bản tin "Việc cần làm", đúng như tài liệu kiến trúc (README của job chỉ nói phần dự báo). "Đặt lại dữ liệu" và nạp sao kê chạy ngay các bước đó, nên video quay ngay sau đặt lại không thấy gì riêng của job đêm; hôm sau một lần đặt lại, Hồ sơ có chip "AI tóm tắt" và dòng "cập nhật … 02:00" (giờ thật). `/ops/summary` không có lần chạy batch. Hiện ngày mô phỏng cạnh giờ cập nhật ở Hồ sơ: issue #40.

## Yêu cầu dữ liệu cho demo (suy ra, cần xác nhận)

- **Ví demo của Minh sau đặt lại** (26/11 sáng, cấu hình `DEMO_LAYOUT` và ánh xạ hũ persona, chi tiết ở [lộ trình bộ hũ](default-six-jars-rollout.md), bảng "Demo (Reset data)"). `vy` cũng có 8 hũ; `lan`, `khoa` có 7 hũ (không có hũ mục tiêu).

  | Hũ | Loại | Tỷ lệ | Số dư |
  |---|---|---:|---:|
  | Chi hằng ngày (mặc định) | chi theo kỳ | 3% | 300.000 ₫ |
  | Nghĩa vụ (mặc định, gộp Hóa đơn cũ) | nghĩa vụ | 33% | 1.450.000 ₫ |
  | Dự phòng (mặc định) | tích lũy, đệm | 10% | 2.700.000 ₫ |
  | Ăn uống (tự thêm) | chi theo kỳ | 30% | 380.000 ₫ |
  | Đi lại (tự thêm) | chi theo kỳ | 7% | 640.000 ₫ |
  | Giải trí (tự thêm) | chi theo kỳ | 7% | 760.000 ₫ |
  | Du lịch (tự thêm, hũ mục tiêu 6.000.000 ₫, hạn 01/04/2027) | tích lũy, mục tiêu | 10% | 1.800.000 ₫ |
  | Đầu tư (tự thêm) | tích lũy, dài hạn | 0% | 0 ₫ |
  | **Tổng** | | **100%** | **8.030.000 ₫** |

  Hũ Chi hằng ngày chứa khoản chi lặt vặt (tạp hóa, giặt sấy, nhà thuốc), không lấy dòng nào của Ăn uống, Đi lại, Giải trí, nên ba hũ này và cảnh 1, cảnh 4 giữ y hệt ví 7 hũ. Giao dịch mới vào hũ riêng khớp loại (ăn uống vào Ăn uống, du lịch vào Du lịch, hóa đơn vào Nghĩa vụ); không có hũ riêng thì vào Chi hằng ngày. Trả sau và nghĩa vụ trả từ hũ Nghĩa vụ; Trả sau của Minh đến hạn ngày 5 (05/12), đúng ngày lương, theo quy tắc chung BR-22; từ 26/11 (phương án B) khoản đến hạn đúng ngày lương nằm trong danh sách "trước kỳ lương" của cảnh 2 và trả bằng số dư trước khi lương về.
- Persona Minh phải sinh ra đúng hiện tượng cảnh 1 (hũ Ăn uống cạn ngày 23, còn 12 ngày tới kỳ lương). Minh có 120 ngày lịch sử (24/7 đến 20/11, issue #8) và **không** có điểm gãy cài sẵn: bộ phát hiện chạy trên lịch sử lúc đặt lại không xác nhận, không nghi hũ nào; cảnh 4 tạo thay đổi lúc chạy bằng tệp sao kê (mục Cảnh 4 ở trên).
- Số đo cảnh 1 (25/11, chạy offline `yofina_ml.forecast_user` qua `build_inputs` của pipeline trên persona vừa sinh, 600 đường, độ phủ giả định 1,0): Ăn uống 380.000 ₫ cạn **23/11**, `days_to_payday` 14 (lương 5/12, còn 12 ngày sau ngày cạn), `p_shortfall` 1,0, nhóm tin cậy `high` (Cao). Đã đo lại trên app 26/11 với ví 8 hũ sau deploy v31, v32 và v33 (mục "Số đo 26/11").
- Dữ liệu tổng hợp nên hiệu chỉnh theo số công khai (§13 rủi ro "dữ liệu tổng hợp trông không thật"); cho giám khảo tự tạo giao dịch và nạp ảnh.
- Câu hỏi mở liên quan: demo dùng tên/biểu phí Ví Trả Sau thật hay sản phẩm mô phỏng.
