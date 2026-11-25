# Kịch bản demo (video 3 phút)

Nguồn: proposal §15. Kể câu chuyện của persona **Minh** (22 tuổi, thu nhập 9 triệu/tháng, lương ngày 5, 7 hũ, một hạn mức Ví Trả Sau) qua 6 cảnh. Giám khảo làm lại được từng cảnh bằng tài khoản demo có sẵn dữ liệu (§13: có nút đặt lại, phương án dự phòng tất định, video quay sẵn). Số trong cảnh là minh họa trong proposal, sẽ chỉnh theo persona thật.

| Cảnh | Thời lượng | Trên màn hình | Tính năng |
|---|---|---|---|
| 1 | 0:00–0:30 | Mở app: dòng thời gian báo hũ Ăn uống cạn ngày 23, còn 12 ngày nữa mới tới kỳ lương, độ tin cậy "Cao" | F1 |
| 2 | 0:30–1:15 | Gõ "nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao". Biểu đồ dịch chuyển, hiện tổng chi phí thật và 2 phương án | F2, F3 |
| 3 | 1:15–1:45 | Bấm "mất việc 2 tháng". Điểm chống chịu tụt, hiện số ngày trụ được | F4 |
| 4 | 1:45–2:20 | Tải sao kê 2 tuần gần nhất (CSV): các dòng tự vào hũ Ăn uống, xác nhận một lần. Bộ phát hiện xác nhận chi Ăn uống tăng, lộ trình sinh lại thành bản đề xuất mới; mở So với bản cũ và bảng "Vì sao". Hỏi "nên mua cổ phiếu nào" và thấy trợ lý từ chối đúng phạm vi | F5, F6, suitability |
| 5 | 2:20–2:50 | Trên `giamkhao1`, nạp ảnh chứng từ mẫu `minh_bien_lai_1.png` (họ tên, số điện thoại, số tài khoản nhìn rõ): PII bị che → dòng giao dịch → gợi ý hũ → duyệt. Các bước ở mục "Cảnh 5" bên dưới | F6 |
| 6 | 2:50–3:00 | Trên **tài khoản giám khảo** (`giamkhao1`), ở câu trả lời vừa rồi bấm "Vì sao" → "Chi tiết kỹ thuật": trace của chính lượt đó (dữ liệu đã dùng, luật đã kiểm, độ tin cậy, thời gian từng bước tính bằng ms, số lượt gọi mô hình, token vào/ra). Tùy chọn, 2–3 giây cuối: bảng vận hành `/ops/summary` quay bằng tài khoản vận hành `minh` | Góc "Future Workspace" |

## Tài khoản dùng trong demo (issue #17)

- **Giám khảo** dùng `giamkhao1` (dự phòng `giamkhao2`, `giamkhao3`), cả ba là persona `minh`. Tài khoản giám khảo **không** thuộc nhóm Cognito `ops`: mở `/ops/summary` bị từ chối (server trả 403, màn "Chỉ dành cho đội vận hành"), vì bảng vận hành đọc trace của mọi người dùng. Truy vết của chính mình xem ở "Vì sao → Chi tiết kỹ thuật" (`frontend/src/features/explain/ExplainBody.tsx`).
- **Vận hành** (chỉ người trình bày, không đưa giám khảo): `minh`, khai ở `ops_accounts` của `data/personas/accounts.json`. Dùng cho đoạn quay ngắn bảng vận hành ở cảnh 6 và cho eval (`evals/run.py`). Mật khẩu chỉ nằm trong secret `yofina-demo-accounts`.
- Nhóm do `scripts/seed_demo.py` đặt theo `accounts.json`: chạy lại sẽ thêm `ops` cho `minh` và gỡ `ops` khỏi mọi tài khoản demo khác. Sau khi gỡ, token cũ còn nhóm `ops` tới khi hết hạn; đăng xuất rồi đăng nhập lại `giamkhao1` trước khi kiểm.

## Cảnh 4 chạy thật: tải sao kê để lộ trình sinh lại

Không dùng lộ trình hay dấu hiệu đổi hành vi seed. Sau khi đặt lại, `minh` (và `giamkhao1`–`3`, cùng persona) chỉ có v1 (đã thay) và v2 (đang dùng); bản đề xuất mới do bộ phát hiện thật tạo từ tệp sao kê (issue #22, số đo ở [2026-11-26-canh4-pelt.md](../research/2026-11-26-canh4-pelt.md)).

Tệp `minh_sao_ke_2_tuan.csv`: tải ở `/samples/minh_sao_ke_2_tuan.csv` trên app; bản trong repo là `data/personas/samples/minh_sao_ke_2_tuan.csv`, sinh bằng `data/personas/samples/make_scene4_csv.py`. Một tệp dùng cho cả bốn tài khoản persona `minh`.

1. Hồ sơ → **Đặt lại dữ liệu**. Làm cảnh 4 trong cùng ngày với lần đặt lại và trước cảnh 5: tệp gắn với ngày mô phỏng 21/11/2026, và nạp tệp khác vào hũ Ăn uống trước đó làm đổi chuỗi chi.
2. Tải tệp về máy, mở **Nạp dữ liệu** → **Tải sao kê CSV** → chọn tệp → **Đồng ý và tải lên** (lần đầu sau khi đặt lại).
3. Chờ đọc xong: 32 dòng chi từ 07/11 tới 20/11, mọi dòng đã chọn sẵn vào hũ Ăn uống (không phải chọn hũ từng dòng) → **Xác nhận thêm 32 dòng**.
4. Dự báo chạy lại ngay sau khi xác nhận. PELT xác nhận chi Ăn uống tăng từ khoảng 843.000 ₫ lên 1.669.000 ₫ mỗi tuần, giữ 2 tuần, rồi lộ trình được sinh lại. Mục tiêu: thấy bản đề xuất mới trong 30 giây kể từ lúc xác nhận (chưa đo trên tài khoản giám khảo).
5. Mở **Lộ trình**: chip **Có phiên bản mới** → **So với bản cũ** (bản mới so với v2, lý do hành vi thay đổi) → mở "Vì sao"; chọn **Dùng bản mới** hoặc **Giữ bản cũ**.
6. Hỏi "nên mua cổ phiếu nào": trợ lý từ chối đúng phạm vi.

Tải lại cùng tệp lần hai bị từ chối vì trùng tệp; muốn làm lại thì đặt lại dữ liệu.

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
5. Màn duyệt: dòng chi 345.000 ₫ ngày 20/11, đối tác `B***`, không còn họ tên, số điện thoại hay số tài khoản đầy đủ. Hũ gợi ý mong là Ăn uống. Đây là chuyển tiền cho người, nên hũ do model đề xuất từ nội dung và dòng ở trạng thái "Cần duyệt"; hũ trống hay sai thì chạm vào dòng để chọn Ăn uống. Ảnh 2 có loại "Tiền nước", hũ mặc định là Hóa đơn.
6. "Xong, cập nhật dự báo" → "Xác nhận thêm 1 dòng" → "Đã thêm các dòng ngoài ví". Số dư hũ không đổi. Khoản chi ngoài ví vào lịch sử chi của hũ, và dự báo được xếp lịch tính lại.

Độ phủ dữ liệu của Minh đã ở mức 100% trước khi nạp: tính offline trên 120 ngày lịch sử của bộ sinh, (chi 31.350.000 ₫ + số dư cuối 7.900.000 ₫) / thu nhập 36.000.000 ₫ vượt 1 nên bị kẹp về 1,0. Vì vậy cảnh này không cho thấy độ phủ tăng. Trên AWS, độ phủ tính theo cửa sổ `forecast_history_window_days`, cần kiểm lại. Muốn thấy độ phủ tăng thì dùng persona `vy` với `vy_sao_ke_vcb.csv` (`data/personas/README.md`, mục "Tệp mẫu cho cảnh 5").

Đã kiểm tất định (`tests/unit/test_persona_samples_minh.py`, không OCR, không gọi model): bộ che PII với payee và tên hiển thị của Minh che đủ họ tên, số điện thoại, số tài khoản trên chữ của hai ảnh, còn số tiền, nhà cung cấp, nội dung, mã tham chiếu thì giữ nguyên. Chưa kiểm: model đọc ảnh, hũ gợi ý, và số giây thao tác (issue #16 cần ≤ 10 s) trên tài khoản giám khảo sau khi deploy.

## Yêu cầu dữ liệu cho demo (suy ra, cần xác nhận)

- Persona Minh phải sinh ra đúng hiện tượng cảnh 1 (hũ Ăn uống cạn ngày 23, còn 12 ngày tới kỳ lương). Minh có 120 ngày lịch sử (24/7 đến 20/11, issue #8) và **không** có điểm gãy cài sẵn: bộ phát hiện chạy trên lịch sử lúc đặt lại không xác nhận, không nghi hũ nào; cảnh 4 tạo thay đổi lúc chạy bằng tệp sao kê (mục Cảnh 4 ở trên).
- Số đo cảnh 1 (25/11, chạy offline `yofina_ml.forecast_user` qua `build_inputs` của pipeline trên persona vừa sinh, 600 đường, độ phủ giả định 1,0): Ăn uống 380.000 ₫ cạn **23/11**, `days_to_payday` 14 (lương 5/12, còn 12 ngày sau ngày cạn), `p_shortfall` 1,0, nhóm tin cậy `high` (Cao). Cần đo lại trên AWS sau khi đặt lại: ngày cạn và nhãn của cảnh 1, điểm chống chịu và số ngày trụ được của `Mất việc 2 tháng` (cảnh 3).
- Dữ liệu tổng hợp nên hiệu chỉnh theo số công khai (§13 rủi ro "dữ liệu tổng hợp trông không thật"); cho giám khảo tự tạo giao dịch và nạp ảnh.
- Câu hỏi mở liên quan: demo dùng tên/biểu phí Ví Trả Sau thật hay sản phẩm mô phỏng.
