# Kịch bản demo (video 3 phút)

Nguồn: proposal §15. Kể câu chuyện của persona **Minh** (22 tuổi, thu nhập 9 triệu/tháng, lương ngày 5, 8 hũ, một hạn mức Ví Trả Sau) qua 6 cảnh. Từ 26/11 sáng (issue #39) ví demo của Minh sau "Đặt lại dữ liệu" có **8 hũ**: ba hũ mặc định Chi hằng ngày, Nghĩa vụ (gộp Hóa đơn cũ), Dự phòng, rồi hũ tự thêm Ăn uống, Đi lại, Giải trí, Du lịch (hũ mục tiêu 6.000.000 ₫, hạn 01/04/2027), Đầu tư (0 ₫); tổng 8.030.000 ₫ (bảng ở mục "Yêu cầu dữ liệu"). Câu chuyện: tài khoản mới nhận 3 hũ mặc định, Minh tự thêm hũ cho khoản muốn theo dõi riêng. Tài khoản mới ngoài demo chỉ có 3 hũ Chi hằng ngày, Nghĩa vụ, Dự phòng. Số đo từng cảnh ở mục "Số đo 26/11" ngay dưới bảng. Giám khảo làm lại được từng cảnh bằng tài khoản demo có sẵn dữ liệu (§13: có nút đặt lại, phương án dự phòng tất định, video quay sẵn). Số trong bảng cảnh là lời dẫn; số thật lấy theo engine.

| Cảnh | Thời lượng | Trên màn hình | Tính năng |
|---|---|---|---|
| 1 | 0:00–0:30 | Mở app: dòng thời gian báo hũ Ăn uống (hũ tự thêm) cạn ngày 23, còn 12 ngày nữa mới tới kỳ lương, độ tin cậy "Cao" | F1 |
| 2 | 0:30–1:15 | Gõ "nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao". Biểu đồ dịch chuyển, hiện tổng chi phí thật và 2 phương án; hũ Nghĩa vụ báo thiếu cho Trả sau đến hạn 05/12, đúng ngày lương (khoản đến hạn ngày lương trả bằng số dư trước khi lương về, BR-22 chốt 26/11) | F2, F3 |
| 3 | 1:15–1:45 | Bấm "mất việc 2 tháng". Điểm chống chịu tụt (29 → 12), hiện số ngày trụ được | F4 |
| 4 | 1:45–2:20 | Tải sao kê 2 tuần gần nhất (CSV): các dòng tự vào hũ Ăn uống, xác nhận một lần. Bộ phát hiện xác nhận chi Ăn uống tăng, lộ trình sinh lại thành bản đề xuất mới; mở So với bản cũ và bảng "Vì sao". Hỏi "nên mua cổ phiếu nào" và thấy trợ lý từ chối đúng phạm vi | F5, F6, suitability |
| 5 | 2:20–2:50 | Trên `giamkhao1`, nạp ảnh chứng từ mẫu `minh_bien_lai_1.png` (họ tên, số điện thoại, số tài khoản nhìn rõ): PII bị che → dòng giao dịch → gợi ý hũ → duyệt. Các bước ở mục "Cảnh 5" bên dưới | F6 |
| 6 | 2:50–3:00 | Trên **tài khoản giám khảo** (`giamkhao1`), ở câu trả lời vừa rồi bấm "Vì sao" → "Chi tiết kỹ thuật": trace của chính lượt đó (dữ liệu đã dùng, luật đã kiểm, độ tin cậy, thời gian từng bước tính bằng ms, số lượt gọi mô hình, token vào/ra). Tùy chọn, 2–3 giây cuối: bảng vận hành `/ops/summary` quay bằng tài khoản vận hành `minh` | Góc "Future Workspace" |

## Số đo 26/11

Hai nguồn, chưa có số nào đo trên app với ví 8 hũ:

- **Trên app**, 26/11 rạng sáng sau deploy (`giamkhao1`, `minh`): ví demo lúc đó có **7 hũ** (chưa có Chi hằng ngày).
- **Cục bộ**, 26/11 (PostgreSQL cục bộ, ngày mô phỏng 21/11/2026, 10.000 đường, what-if 5.000 đường; [lộ trình bộ hũ](default-six-jars-rollout.md) Bước 5): ví **8 hũ**, Trả sau đến hạn ngày 5 (phương án B, chốt 26/11; số cảnh 2 đo lại sau khi đổi). Chờ đo lại trên app sau khi deploy và đặt lại.

| Cảnh | Trên app (ví 7 hũ) | Cục bộ (ví 8 hũ, chờ đo lại) |
|---|---|---|
| 1 | Ăn uống 380.000 ₫ cạn 23/11, nhãn Cao | Như trên app: Ăn uống cạn 23/11, nhóm `high` (Cao), thẻ Tổng quan vẫn là Ăn uống. Hũ Chi hằng ngày 300.000 ₫ "đủ", không nêu ngày cạn (hũ thưa), không có thẻ |
| 2 | Trọn câu 34 giây. Hũ Nghĩa vụ liệt kê Tiền điện 26/11 và Trả sau 03/12 (2.200.000 ₫: 1.000.000 ₫ có sẵn gồm phí 33.000 ₫, cộng 1.200.000 ₫), thiếu 1.161.791 ₫ | Số đo cục bộ (Trả sau ngày 5): Tiền điện 26/11 và Trả sau **05/12** (2.200.000 ₫), thiếu **1.168.392 ₫** (số dư trước khi lương về 1.031.608 ₫), hũ trả hụt cùng số, trạng thái Sau "hụt". Lời dẫn dùng "thiếu khoảng 1,17 triệu" |
| 3 | Điểm 29 → 12, trụ 25 ngày | Điểm 29 → 12, trụ **26 ngày**. Lệch do hũ mới: số dư cộng 300.000 ₫, chi 30 ngày cộng khoảng 210.000 ₫ |
| 4 | 32 dòng vào Ăn uống; bản v3 sau khoảng 30 giây, giai đoạn đầu 21/11–05/12, bước lớn nhất vào Ăn uống 2.657.800 ₫ | Phần không cần model như trên app: 32 dòng vào Ăn uống, PELT xác nhận từ hệ số 2,1 (ngưỡng mịn 2,04), tệp (hệ số 3,5) xác nhận khi tải trong ngày và trễ một ngày. Bản v3 với model giả tất định (`test_roadmap_regen_scene4.py`, phần số do engine quyết): Ăn uống 2.700.000 → 5.048.300 ₫/tháng, Dự phòng và Du lịch về 0 ₫, Chi hằng ngày 105.000 ₫, Giải trí 204.500 ₫, LP "sàn bắt buộc vượt thu nhập 798.900 ₫". Hệ số nhỏ hơn không giữ được cả Dự phòng lẫn độ bền khi tải trễ một ngày ([đo lại hệ số](../research/2026-11-26-canh4-pelt.md), mục "Hệ số và bản lộ trình sinh lại"). Bản v3 với model thật chưa đo trên ví 8 hũ |
| 5 | Màn duyệt sau 8,5 giây, chip "Đã che: tên" | Không đo |

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
4. Dự báo chạy lại ngay sau khi xác nhận. PELT xác nhận chi Ăn uống tăng từ khoảng 843.000 ₫ lên 2.651.000 ₫ mỗi tuần, giữ 2 tuần (tải ngày hôm sau: khoảng 868.000 ₫ lên 2.353.000 ₫), rồi lộ trình được sinh lại. Mục tiêu: thấy bản đề xuất mới trong 30 giây kể từ lúc xác nhận (chưa đo trên tài khoản giám khảo).
5. Mở **Lộ trình**: chip **Có phiên bản mới** → **So với bản cũ** (bản mới so với v2, lý do hành vi thay đổi) → mở "Vì sao"; chọn **Dùng bản mới** hoặc **Giữ bản cũ**.
6. Hỏi "nên mua cổ phiếu nào": trợ lý từ chối đúng phạm vi.

Tải lại cùng tệp lần hai bị từ chối vì trùng tệp; muốn làm lại thì đặt lại dữ liệu.

Trên ví 8 hũ, cả 32 dòng vẫn vào Ăn uống, không dòng nào vào Chi hằng ngày; hũ Chi hằng ngày là chuỗi thưa nên bộ phát hiện bỏ qua. Lần đo 26/11 ở [đo ví 3 hũ](../research/2026-11-26-do-vi-ba-hu.md) (mục 3) thấy tệp hiện hành vẫn được xác nhận trên hũ Ăn uống riêng khi tải trễ 2 và 3 ngày, khác câu ở bước 1; chưa tìm nguyên nhân, nên vẫn làm cảnh 4 trong ngày đặt lại.

Bản mới trên ví 8 hũ (đo cục bộ với model giả tất định) tăng phần chia Ăn uống lên khoảng 5 triệu ₫/tháng và đưa Dự phòng, Du lịch về 0 ₫, vì sàn thiết yếu của Ăn uống (5.847.200 ₫) vượt phần lương còn lại sau Nghĩa vụ, Đi lại và sàn chi. Du lịch hiện "chưa khả thi" kèm hai lựa chọn (lùi hạn 6 tháng, giảm mục tiêu còn 1.800.000 ₫). Khi dẫn, nói đây là hệ thống báo mức chi mới vượt khả năng, đừng nói như một lời khuyên bỏ tiết kiệm. Hệ số nhỏ hơn và các đánh đổi: [đo lại hệ số](../research/2026-11-26-canh4-pelt.md), mục "Hệ số và bản lộ trình sinh lại".

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
- **Chưa xác minh**: tài liệu kiến trúc ghi batch đêm phục vụ cả điểm chống chịu (F4) và hồ sơ hành vi (F7), còn README của job chỉ mô tả việc tính lại dự báo; job đêm để lại dấu vết gì trên giao diện (dấu thời gian cập nhật, bảng vận hành) đang được điều tra, kết quả ghi ở HANDOFF.

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

  Hũ Chi hằng ngày chứa khoản chi lặt vặt (tạp hóa, giặt sấy, nhà thuốc), không lấy dòng nào của Ăn uống, Đi lại, Giải trí, nên ba hũ này và cảnh 1, cảnh 4 giữ y hệt ví 7 hũ. Giao dịch mới vào hũ riêng khớp loại (ăn uống vào Ăn uống, du lịch vào Du lịch, hóa đơn vào Nghĩa vụ); không có hũ riêng thì vào Chi hằng ngày. Trả sau và nghĩa vụ trả từ hũ Nghĩa vụ; Trả sau của Minh đến hạn ngày 3 trên ví demo (điều khoản mô phỏng; quy tắc chung là ngày 5, BR-22) để khoản này nằm trong danh sách "trước kỳ lương" của cảnh 2.
- Persona Minh phải sinh ra đúng hiện tượng cảnh 1 (hũ Ăn uống cạn ngày 23, còn 12 ngày tới kỳ lương). Minh có 120 ngày lịch sử (24/7 đến 20/11, issue #8) và **không** có điểm gãy cài sẵn: bộ phát hiện chạy trên lịch sử lúc đặt lại không xác nhận, không nghi hũ nào; cảnh 4 tạo thay đổi lúc chạy bằng tệp sao kê (mục Cảnh 4 ở trên).
- Số đo cảnh 1 (25/11, chạy offline `yofina_ml.forecast_user` qua `build_inputs` của pipeline trên persona vừa sinh, 600 đường, độ phủ giả định 1,0): Ăn uống 380.000 ₫ cạn **23/11**, `days_to_payday` 14 (lương 5/12, còn 12 ngày sau ngày cạn), `p_shortfall` 1,0, nhóm tin cậy `high` (Cao). Đã đo trên app 26/11 với ví 7 hũ (mục "Số đo 26/11"). **Cần đo lại trên AWS sau khi deploy ví 8 hũ và đặt lại**: ngày cạn và nhãn của cảnh 1, số thiếu của hũ Nghĩa vụ ở cảnh 2, điểm và số ngày trụ được của "Mất việc 2 tháng" (cảnh 3; cục bộ 26 ngày), bản v3 của cảnh 4.
- Dữ liệu tổng hợp nên hiệu chỉnh theo số công khai (§13 rủi ro "dữ liệu tổng hợp trông không thật"); cho giám khảo tự tạo giao dịch và nạp ảnh.
- Câu hỏi mở liên quan: demo dùng tên/biểu phí Ví Trả Sau thật hay sản phẩm mô phỏng.
