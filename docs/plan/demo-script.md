# Kịch bản demo (video 3 phút)

Nguồn: proposal §15. Kể câu chuyện của persona **Minh** (22 tuổi, thu nhập 9 triệu/tháng, lương ngày 5, 7 hũ, một hạn mức Ví Trả Sau) qua 6 cảnh. Giám khảo làm lại được từng cảnh bằng tài khoản demo có sẵn dữ liệu (§13: có nút đặt lại, phương án dự phòng tất định, video quay sẵn). Số trong cảnh là minh họa trong proposal, sẽ chỉnh theo persona thật.

| Cảnh | Thời lượng | Trên màn hình | Tính năng |
|---|---|---|---|
| 1 | 0:00–0:30 | Mở app: dòng thời gian báo hũ Ăn uống cạn ngày 23, còn 12 ngày nữa mới tới kỳ lương, độ tin cậy "Cao" | F1 |
| 2 | 0:30–1:15 | Gõ "nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao". Biểu đồ dịch chuyển, hiện tổng chi phí thật và 2 phương án | F2, F3 |
| 3 | 1:15–1:45 | Bấm "mất việc 2 tháng". Điểm chống chịu tụt, hiện số ngày trụ được | F4 |
| 4 | 1:45–2:20 | Tải sao kê 2 tuần gần nhất (CSV): các dòng tự vào hũ Ăn uống, xác nhận một lần. Bộ phát hiện xác nhận chi Ăn uống tăng, lộ trình sinh lại thành bản đề xuất mới; mở So với bản cũ và bảng "Vì sao". Hỏi "nên mua cổ phiếu nào" và thấy trợ lý từ chối đúng phạm vi | F5, F6, suitability |
| 5 | 2:20–2:50 | Chụp ảnh một thông báo chuyển khoản nạp vào. Độ phủ dữ liệu tăng, dự báo cập nhật | F6 |
| 6 | 2:50–3:00 | Màn hình trace cho đội sản phẩm: mọi quyết định của agent xem lại được | Góc "Future Workspace" |

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

## Yêu cầu dữ liệu cho demo (suy ra, cần xác nhận)

- Persona Minh phải sinh ra đúng hiện tượng cảnh 1 (hũ Ăn uống cạn ngày 23, còn 12 ngày tới kỳ lương). Minh có 120 ngày lịch sử (24/7 đến 20/11, issue #8) và **không** có điểm gãy cài sẵn: bộ phát hiện chạy trên lịch sử lúc đặt lại không xác nhận, không nghi hũ nào; cảnh 4 tạo thay đổi lúc chạy bằng tệp sao kê (mục Cảnh 4 ở trên).
- Số đo cảnh 1 (25/11, chạy offline `yofina_ml.forecast_user` qua `build_inputs` của pipeline trên persona vừa sinh, 600 đường, độ phủ giả định 1,0): Ăn uống 380.000 ₫ cạn **23/11**, `days_to_payday` 14 (lương 5/12, còn 12 ngày sau ngày cạn), `p_shortfall` 1,0, nhóm tin cậy `high` (Cao). Cần đo lại trên AWS sau khi đặt lại: ngày cạn và nhãn của cảnh 1, điểm chống chịu và số ngày trụ được của `Mất việc 2 tháng` (cảnh 3).
- Dữ liệu tổng hợp nên hiệu chỉnh theo số công khai (§13 rủi ro "dữ liệu tổng hợp trông không thật"); cho giám khảo tự tạo giao dịch và nạp ảnh.
- Câu hỏi mở liên quan: demo dùng tên/biểu phí Ví Trả Sau thật hay sản phẩm mô phỏng.
