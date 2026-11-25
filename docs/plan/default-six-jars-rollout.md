# Kế hoạch phát hành bộ sáu hũ mặc định của Yofina

Ngày lập: 25/11/2026  
Nhánh: `feat/default-six-jars`  
SHA gốc đã đối chiếu với `origin/main`: `865fba9f60039294c9afdb936a1c1f401de11430`

Bộ sáu hũ đã có trong diff của worktree. Kế hoạch này dùng diff đó làm điểm xuất phát và sắp xếp phần migration, hoàn thiện ứng dụng, kiểm thử và phát hành theo thứ tự phụ thuộc. Trước khi sửa tiếp, xác minh lại worktree, nhánh, SHA và `origin/main` theo hướng dẫn Git của dự án.

## Cấu hình đợt này

| Hũ | Loại | `purpose` | Tỷ lệ thử nghiệm |
| --- | --- | --- | ---: |
| Chi hằng ngày | `spending` | — | 35% |
| Nghĩa vụ | `obligation` | — | 35% |
| Dự phòng | `saving` | `buffer` | 15% |
| Quỹ dồn | `saving` | `sinking` | 5% |
| Mục tiêu | `saving` | `goal` | 5% |
| Tích lũy dài hạn | `saving` | `long_term` | 5% |
| **Tổng** | | | **100%** |

Người dùng có thể sửa tỷ lệ và chỉ lưu khi tổng bằng 100%. Hũ hệ thống tiếp tục được tạo theo cơ chế hiện hành. Sau khi kích hoạt, tài khoản mới nhận bộ sáu. Tài khoản đã có chỉ nhận bộ mới khi xác nhận **Reset data** qua luồng và quyền hiện có.

## 1. Tách migration và kích hoạt bộ hũ

- [ ] Tách [migration 0055](../../db/migrations/0055_default_six_jars.sql) thành phần mở rộng schema và phần chuyển bộ mặc định. Thêm `purpose` cho `jars` và `jar_templates`, chấp nhận `NULL` trên dữ liệu cũ. Giữ hợp đồng đọc cũ trong giai đoạn chạy xen kẽ, kể cả quyền truy cập và RLS.
- [ ] Giữ bộ bảy hiện hành trong giai đoạn đầu, gồm cả tỷ lệ của những hũ trùng mã như Nghĩa vụ và Dự phòng. Đồng bộ cả migration và [seed danh mục](../../db/seed/jar_templates.sql) để chạy seed sớm cũng chưa bật bộ sáu.
- [ ] Đối chiếu snapshot trước và sau migration và seed trên PostgreSQL cục bộ. Hũ, số dư, tỷ lệ, giao dịch và nghĩa vụ của ví cũ phải khớp. Ledger cũ còn phải khởi tạo được bộ bảy sau khi schema mở rộng.

Chuyển danh mục sớm sẽ khiến Ledger cũ tạo sáu hũ mà bỏ trống `purpose`. Chạy Ledger mới trước schema sẽ khiến những truy vấn cần cột đó lỗi.

## 2. Hoàn thiện nghiệp vụ trên cả hai bộ hũ

- [ ] Truyền `purpose` qua tạo, đọc, sửa và reset. Cập nhật hợp đồng API, Ledger, Agent, Planner, forecast và frontend. Bên đọc phải chấp nhận dữ liệu thiếu `purpose` và dữ liệu có `purpose`. Agent cũ kiểm tra chặt trường trả về, nên cập nhật bên đọc trước khi Ledger phát trường mới.
- [ ] Dùng `buffer` cho số dư Dự phòng trong Planner, stress test và LP. Giữ quy tắc tương thích cho ví cũ chưa có `purpose`. Đưa `goal` vào luồng mục tiêu và lộ trình hiện có. Cho `sinking` lưu số tiền, ngày dự kiến và giữ ngày đã cam kết. Cho `long_term` có ngày đích tùy chọn.
- [ ] Gán rõ nguồn trả cho tiền nhà, hóa đơn, khoản vay và Trả Sau. Ưu tiên nguồn đã lưu và dùng hũ Nghĩa vụ chuẩn làm mặc định của bộ sáu. Khi ví cũ thiếu hũ Nghĩa vụ và chưa có nguồn hợp lệ, yêu cầu chọn hũ trả. Dùng cùng quy tắc trong sổ cái và what-if, đồng thời kiểm tra các luồng còn chọn hũ `obligation` đầu tiên.
- [ ] Ghi và dự báo một khoản đến hạn gồm cả gốc và phí Trả Sau khi phí đã nằm trong tổng. Phí trả ngay đi theo giao dịch gốc.

## 3. Nối onboarding, reset và kiểm thử cục bộ

- [ ] Cho onboarding và [luồng reset demo](../../data/personas/six_jars.py) dùng bộ hũ phù hợp với cấu hình đang bật. Trong giai đoạn chuyển phiên bản, reset vẫn cần hoạt động với bộ hiện hành. Khi bật bộ sáu, reset đã xác nhận dựng đúng sáu hũ cùng dữ liệu persona.
- [ ] Duy trì fixture riêng cho ví cũ chưa reset và ví sáu hũ. Cập nhật các ca tích hợp sau reset còn truy vấn `an_uong` hoặc kỳ vọng mốc cạn 23/11. Giữ các ca dùng mã cũ để kiểm hành vi tương thích.
- [ ] Kiểm cả tài khoản mới, tài khoản cũ chưa reset và tài khoản demo reset hai lần. Xác nhận đúng sáu hũ và tổng 100% khi bật bộ mới, dữ liệu cũ còn nguyên trước reset, reset lặp lại giữ số dư nhất quán và hũ không bị trùng.
- [ ] Chạy lại hai cảnh theo [kịch bản demo](demo-script.md) bằng engine cục bộ. Chi hằng ngày của Minh có 1.080.000 ₫ và dự kiến cạn ngày 03/12 do nhịp chi, trước kỳ lương 05/12. Khi mô phỏng mua tai nghe 1.200.000 ₫ bằng Trả Sau, Nghĩa vụ có một khoản đến hạn 2.200.000 ₫ ngày 03/12, đã gồm phí 33.000 ₫, và dự kiến thiếu khoảng 761.000 ₫.

Chỉ chạy test đã kiểm tra là dùng tài nguyên cục bộ. Đợt trước đã đạt 234 ca PostgreSQL cục bộ và chạy hai cảnh demo. Cần chạy lại các ca chịu ảnh hưởng sau khi tách migration và hoàn thiện các thay đổi trên.

## 4. Thứ tự phát hành sau khi được duyệt

1. Áp dụng schema tương thích trong khi bộ bảy còn hoạt động.
2. Cập nhật các bên đọc dữ liệu hũ, sau đó cập nhật Ledger và các luồng ghi. Kiểm tra cả ví cũ và ví có `purpose` trên môi trường đã được phép kiểm thử.
3. Bật bộ sáu cho onboarding và Reset data đã xác nhận. Kiểm tra lại hai luồng với tài khoản thử.
4. Nếu cần quay lui, chuyển cấu hình cho các lần tạo ví và reset tiếp theo. Giữ schema và các bên đọc tương thích để những ví sáu hũ đã tạo vẫn hoạt động.

## Bàn giao và phạm vi đợt sau

- Bàn giao diff trên nhánh riêng, SHA gốc, kết quả kiểm thử và thứ tự phát hành. Push, merge và deploy cần chỉ đạo riêng.
- Kiro Opus 5.5 review read-only bằng skill `kiro-worker`, `Tier: deep`, `Spec: no`, sau khi có phê duyệt chi phí. Phạm vi review là nguồn trả nghĩa vụ, `purpose` và tương thích reset. Ghi lại model thực tế và kết quả đối chiếu với mã. Mọi eval và thao tác có thể phát sinh phí hoặc tiêu hao credits cũng cần đồng ý rõ ràng trước.
- Nếu chọn pilot mở ví ba hũ, dùng cấu hình onboarding riêng cho Chi hằng ngày, Nghĩa vụ và Dự phòng, với đường thêm Quỹ dồn ngay khi cần. Giữ bộ sáu cho demo Minh. Tự tính mức góp Quỹ dồn, nhắc khi rút Dự phòng và cổng đầu tư thuộc đợt sau.
