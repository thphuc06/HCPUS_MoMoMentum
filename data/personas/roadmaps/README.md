# data/personas/roadmaps/

Lộ trình seed của persona (phase 4, F5), nạp khi bấm "Đặt lại dữ liệu" (`POST /demo/reset`). Chỉ `minh` có file (`minh.json`); persona khác không có lộ trình sau khi đặt lại.

| Phần trong file | Ý nghĩa |
|---|---|
| `nguon` | Ghi rõ con số nào là dữ liệu seed và con số nào đọc từ persona |
| `basis` | Độ tươi và độ tin cậy của dự báo mà lộ trình dựa vào (dữ liệu seed; lúc đặt lại chưa có lần chạy dự báo nào) |
| `versions` | Các phiên bản theo thứ tự. Bản có `phases` được nạp nguyên; bản có `edit` được dựng từ bản trước bằng đúng hàm sửa một bước của REST; `decisions` là trạng thái từng bước ghi bằng đúng hàm của REST |

`minh` có hai phiên bản: v1 (bản đầu, đã quyết từng bước, thành `superseded`) và v2 (sửa số tiền bước `bu_an_uong`, đang dùng), để màn So với bản cũ có hai bản để so.

Không có dấu hiệu đổi hành vi cài sẵn và không có bản đề xuất (issue #22). Cảnh 4 chạy thật: người dùng nạp tệp sao kê hai tuần gần nhất (`data/personas/samples/minh_sao_ke_2_tuan.csv`), batch dự báo chạy PELT, xác nhận điểm gãy, phát `behavior.changed`, rồi Lambda sinh lại lộ trình tạo bản đề xuất mới so với v2. Một dấu hiệu `confirmed` cài sẵn sẽ chặn đường này: batch đêm bỏ qua hũ đã có dấu hiệu mở. Vì vậy file seed không được có khóa `behavior_flag` hay phiên bản lý do `behavior_changed`.

Quy ước: mọi ngày là SỐ NGÀY KỂ TỪ NGÀY NEO (`start_day`, `end_day`, `due_day`, `fire_on_day`), nên file không gắn với một ngày cụ thể. `goal_monthly_plan_vnd` là mức dành mỗi tháng cho hũ mục tiêu (tham số seed); mục tiêu, hạn và số dư hũ lấy từ persona và sổ cái vừa nạp, rồi chiếu thành `goals` (`roadmap_seed.project_goal`). Mỗi bước phải qua luật suitability như bước do agent soạn; seed vi phạm thì đặt lại báo lỗi.
