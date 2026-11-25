# Kịch bản demo (video 3 phút)

Nguồn: proposal §15. Kể câu chuyện của persona **Minh** (22 tuổi, thu nhập 9 triệu/tháng, lương ngày 5, 7 hũ, một hạn mức Ví Trả Sau) qua 6 cảnh. Giám khảo làm lại được từng cảnh bằng tài khoản demo có sẵn dữ liệu (§13: có nút đặt lại, phương án dự phòng tất định, video quay sẵn). Số trong cảnh là minh họa trong proposal, sẽ chỉnh theo persona thật.

| Cảnh | Thời lượng | Trên màn hình | Tính năng |
|---|---|---|---|
| 1 | 0:00–0:30 | Mở app: dòng thời gian báo hũ Ăn uống cạn ngày 23, còn 12 ngày nữa mới tới kỳ lương, độ tin cậy "Cao" | F1 |
| 2 | 0:30–1:15 | Gõ "nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao". Biểu đồ dịch chuyển, hiện tổng chi phí thật và 2 phương án | F2, F3 |
| 3 | 1:15–1:45 | Bấm "mất việc 2 tháng". Điểm chống chịu tụt, hiện số ngày trụ được | F4 |
| 4 | 1:45–2:20 | Lộ trình sinh lại. Mở bảng "Vì sao". Hỏi "nên mua cổ phiếu nào" và thấy trợ lý từ chối đúng phạm vi | F5, suitability |
| 5 | 2:20–2:50 | Chụp ảnh một thông báo chuyển khoản nạp vào. Độ phủ dữ liệu tăng, dự báo cập nhật | F6 |
| 6 | 2:50–3:00 | Trên **tài khoản giám khảo** (`giamkhao1`), ở câu trả lời vừa rồi bấm "Vì sao" → "Chi tiết kỹ thuật": trace của chính lượt đó (dữ liệu đã dùng, luật đã kiểm, độ tin cậy, thời gian từng bước tính bằng ms, số lượt gọi mô hình, token vào/ra). Tùy chọn, 2–3 giây cuối: bảng vận hành `/ops/summary` quay bằng tài khoản vận hành `minh` | Góc "Future Workspace" |

## Tài khoản dùng trong demo (issue #17)

- **Giám khảo** dùng `giamkhao1` (dự phòng `giamkhao2`, `giamkhao3`), cả ba là persona `minh`. Tài khoản giám khảo **không** thuộc nhóm Cognito `ops`: mở `/ops/summary` bị từ chối (server trả 403, màn "Chỉ dành cho đội vận hành"), vì bảng vận hành đọc trace của mọi người dùng. Truy vết của chính mình xem ở "Vì sao → Chi tiết kỹ thuật" (`frontend/src/features/explain/ExplainBody.tsx`).
- **Vận hành** (chỉ người trình bày, không đưa giám khảo): `minh`, khai ở `ops_accounts` của `data/personas/accounts.json`. Dùng cho đoạn quay ngắn bảng vận hành ở cảnh 6 và cho eval (`evals/run.py`). Mật khẩu chỉ nằm trong secret `yofina-demo-accounts`.
- Nhóm do `scripts/seed_demo.py` đặt theo `accounts.json`: chạy lại sẽ thêm `ops` cho `minh` và gỡ `ops` khỏi mọi tài khoản demo khác. Sau khi gỡ, token cũ còn nhóm `ops` tới khi hết hạn; đăng xuất rồi đăng nhập lại `giamkhao1` trước khi kiểm.

## Yêu cầu dữ liệu cho demo (suy ra, cần xác nhận)

- Persona Minh phải sinh ra đúng hiện tượng cảnh 1 (hũ Ăn uống cạn ngày 23, còn 12 ngày tới kỳ lương). Minh có 120 ngày lịch sử (24/7 đến 20/11, issue #8) và **không** có điểm gãy cài sẵn: bộ phát hiện chạy trên lịch sử lúc đặt lại không xác nhận, không nghi hũ nào; cảnh 4 phải tự tạo thay đổi lúc chạy.
- Số đo cảnh 1 (25/11, chạy offline `yofina_ml.forecast_user` qua `build_inputs` của pipeline trên persona vừa sinh, 600 đường, độ phủ giả định 1,0): Ăn uống 380.000 ₫ cạn **23/11**, `days_to_payday` 14 (lương 5/12, còn 12 ngày sau ngày cạn), `p_shortfall` 1,0, nhóm tin cậy `high` (Cao). Cần đo lại trên AWS sau khi đặt lại: ngày cạn và nhãn của cảnh 1, điểm chống chịu và số ngày trụ được của `Mất việc 2 tháng` (cảnh 3).
- Dữ liệu tổng hợp nên hiệu chỉnh theo số công khai (§13 rủi ro "dữ liệu tổng hợp trông không thật"); cho giám khảo tự tạo giao dịch và nạp ảnh.
- Câu hỏi mở liên quan: demo dùng tên/biểu phí Ví Trả Sau thật hay sản phẩm mô phỏng.
