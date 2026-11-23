# data/personas/roadmaps/

Lộ trình seed của persona (phase 4, F5), nạp khi bấm "Đặt lại dữ liệu" (`POST /demo/reset`). Chỉ `minh` có file (`minh.json`); persona khác không có lộ trình sau khi đặt lại.

| Phần trong file | Ý nghĩa |
|---|---|
| `nguon` | Ghi rõ con số nào là dữ liệu seed và con số nào đọc từ persona |
| `basis` | Độ tươi và độ tin cậy của dự báo mà lộ trình dựa vào (dữ liệu seed; lúc đặt lại chưa có lần chạy dự báo nào) |
| `behavior_flag` | MỘT dòng `behavior_flags` trạng thái `confirmed` (PELT, Ăn uống tăng 520.000 lên 810.000 mỗi tuần, giữ 2 tuần); ngày tính theo "số ngày trước ngày neo" |
| `versions` | Các phiên bản theo thứ tự. Bản có `phases` được nạp nguyên; bản có `edit` được dựng từ bản trước bằng đúng hàm sửa một bước của REST; `decisions` là trạng thái từng bước ghi bằng đúng hàm của REST |

Quy ước: mọi ngày là SỐ NGÀY KỂ TỪ NGÀY NEO (`start_day`, `end_day`, `due_day`, `fire_on_day`), nên file không gắn với một ngày cụ thể. `goal_monthly_plan_vnd` là mức dành mỗi tháng cho hũ mục tiêu (tham số seed); mục tiêu, hạn và số dư hũ lấy từ persona và sổ cái vừa nạp, rồi chiếu thành `goals` (`roadmap_seed.project_goal`). Mỗi bước phải qua luật suitability như bước do agent soạn; seed vi phạm thì đặt lại báo lỗi.

Dấu hiệu seed giữ trạng thái `confirmed` (không chuyển `applied` như khi một lần lưu thật dùng nó) để batch đêm không dựng thêm dấu hiệu thứ hai cho cùng hũ (mỗi hũ chỉ một dấu hiệu mở) và không sinh lại lộ trình trước cảnh 4.
