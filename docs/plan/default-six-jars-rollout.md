# Lộ trình bộ hũ mặc định và tỷ lệ theo kê khai

Ngày lập: 25/11/2026. Cập nhật sau khi rà soát với trang Notion "Feedback hũ" và file đề xuất BR-78 đến BR-84.  
Nhánh: `feat/default-six-jars`  
SHA gốc đã đối chiếu với `origin/main`: `865fba9f60039294c9afdb936a1c1f401de11430`. Commit WIP chứa bộ sáu hũ: `622a1b0`.

Tên file giữ nguyên để không gãy liên kết, nhưng phạm vi đã đổi: người dùng mới nhận **ba hũ**, demo dùng **cấu hình hũ riêng** với bốn hũ. Trước khi sửa tiếp, xác minh lại worktree, nhánh, SHA và `origin/main` theo hướng dẫn Git của dự án.

## Quyết định đã chốt

| # | Quyết định | Ghi chú |
| --- | --- | --- |
| Q1 | Người dùng mới nhận ba hũ: Chi hằng ngày, Nghĩa vụ, Dự phòng | Các hũ để dành khác chỉ tạo khi có số liệu (mục "Cấu hình hũ") |
| Q2 | Demo có cấu hình hũ riêng, không đọc bộ mặc định của onboarding | Cả bốn persona (`minh`, `khoa`, `lan`, `vy`) dùng chung cấu hình demo |
| Q3 | Minh có bốn hũ: Chi hằng ngày, Nghĩa vụ, Dự phòng, Mục tiêu | Bỏ Quỹ dồn và Tích lũy dài hạn khỏi dữ liệu demo vì số dư 0, không có mục tiêu, không cảnh nào dùng |
| Q4 | Kê khai ở bước 3 của onboarding (màn "Chi phí cố định") | Khai qua chat chưa làm trong lượt này |
| Q5 | Hũ Nghĩa vụ mặc định là một hũ chung | Tiền trọ, hóa đơn, khoản vay và Trả Sau cùng trả từ hũ này |
| Q6 | Hoãn bộ hũ theo giai đoạn sống (BR-70) | Mọi người dùng mới nhận cùng ba hũ; xem mục "Chưa làm trong lượt này" |

## Cấu hình hũ

### Onboarding (tài khoản mới)

| Hũ | Loại | `purpose` | Tạo sẵn | Tỷ lệ thử nghiệm |
| --- | --- | --- | --- | ---: |
| Chi hằng ngày | `spending` | — | Có | 42% |
| Nghĩa vụ | `obligation` | — | Có | 33%, thay bằng số đã khai ở bước 3 |
| Dự phòng | `saving` | `buffer` | Có | 25% |
| Quỹ dồn | `saving` | `sinking` | Khi khai khoản biết trước ở bước 3 | Tính từ số đã khai |
| Mục tiêu | `saving` | `goal` | Khi người dùng thêm, kèm số tiền và hạn (BR-67) | Người dùng nhập |
| Tích lũy dài hạn | `saving` | `long_term` | Không | Người dùng tự thêm như hiện nay |
| **Tổng ba hũ tạo sẵn** | | | | **100%** |

Tỷ lệ 42/33/25 lấy theo các nhóm của bộ "Mới đi làm" ở [B2a](../ba/02-business-rules.md): Ăn uống, Đi lại, Giải trí cộng lại 42%; Nhà ở và Trả sau 33%; Dự phòng, Quỹ dồn và Mục tiêu 25%. Đây là **giả định thử nghiệm**, chưa có nguồn nào chứng minh là tối ưu. Người dùng sửa được và chỉ lưu khi tổng bằng 100%. Hai hũ hệ thống vẫn tạo theo cơ chế hiện hành.

### Demo (Reset data)

| Hũ | Loại | `purpose` | Tỷ lệ | Số dư sau reset |
| --- | --- | --- | ---: | --- |
| Chi hằng ngày | `spending` | — | 45% | Gộp từ Ăn uống, Đi lại, Giải trí, trừ 700.000 ₫ đã để riêng cho nghĩa vụ |
| Nghĩa vụ | `obligation` | — | 35% | Gộp từ Hóa đơn và Nghĩa vụ cũ, cộng 700.000 ₫ |
| Dự phòng | `saving` | `buffer` | 15% | Giữ từ Dự phòng cũ |
| Mục tiêu | `saving` | `goal` | 5% | Từ Du lịch cũ, giữ mục tiêu 6.000.000 ₫, hạn 01/04/2027 |
| **Tổng** | | | **100%** | |

Tỷ lệ demo dồn 10% của hai hũ bỏ đi vào Chi hằng ngày, gần mức 44% trong spec cũ của Minh. Tỷ lệ chỉ ảnh hưởng các kỳ lương từ 05/12, nhưng vẫn phải chạy lại bốn cảnh trước khi chốt số (bước 5).

Reset data chỉ dùng được với tài khoản thuộc nhóm demo ([`rest_api.py`](../../gateway/tools/ledger/yofina_ledger/rest_api.py), route `POST /demo/reset`) và thay toàn bộ dữ liệu bằng persona. Tài khoản thật đã có hũ **không** được chuyển bộ; người dùng tự sửa hũ ở màn "Thêm hoặc sửa hũ".

## Hiện trạng commit WIP cần sửa

| Chỗ | Commit WIP đang làm | Cần đổi |
| --- | --- | --- |
| [Migration 0055](../../db/migrations/0055_default_six_jars.sql) và [seed](../../db/seed/jar_templates.sql) | Bật bộ sáu ngay khi chạy | Tách phần schema và phần bật bộ hũ (bước 1) |
| [`six_jars.py`](../../data/personas/six_jars.py) | Lấy hũ demo từ `is_default`, báo lỗi nếu không đúng sáu hũ | Đọc cấu hình demo riêng (bước 1, bước 5) |
| [`service.py` `reset_demo`](../../gateway/tools/ledger/yofina_ledger/service.py) | Lấy `purpose` từ danh mục mặc định | Lấy từ cấu hình demo |
| [`settings.py`](../../pipelines/forecast/yofina_forecast/settings.py) `DEFAULT_ESSENTIAL_JAR_CODES` | Coi cả Chi hằng ngày là thiết yếu, kể cả giải trí | Tính sàn theo phần chi thiết yếu (bước 2) |
| [`wallet_writes.py` `_prep_save_jars`](../../gateway/tools/ledger/yofina_ledger/wallet_writes.py) | Bản xem trước chỉ có % trước và sau | Thêm số tiền mỗi kỳ và kỳ áp dụng (bước 4) |

## Lộ trình thực hiện

### Bước 1. Tách cấu hình bộ hũ và migration

- [x] Thêm cấu hình bộ hũ riêng cho onboarding và cho demo (ví dụ `jar_layout`). Onboarding đọc bộ ba; Reset data đọc bộ demo. Bỏ điều kiện "đúng sáu hũ" trong `use_default_jars`.
- [x] Tách [migration 0055](../../db/migrations/0055_default_six_jars.sql) thành phần mở rộng schema và phần bật bộ hũ. Thêm `purpose` cho `jars` và `jar_templates`, chấp nhận `NULL` trên dữ liệu cũ. Giữ hợp đồng đọc cũ trong giai đoạn chạy xen kẽ, kể cả quyền truy cập và RLS.
- [x] Phần bật bộ hũ đặt `is_default = true` cho đúng ba hũ, `false` cho Quỹ dồn, Mục tiêu, Tích lũy dài hạn và bảy hũ cũ. Đồng bộ cả migration và seed để chạy seed sớm cũng chưa bật bộ mới.
- [x] Đối chiếu snapshot trước và sau migration và seed trên PostgreSQL cục bộ. Hũ, số dư, tỷ lệ, giao dịch và nghĩa vụ của ví cũ phải khớp. Ledger cũ còn phải khởi tạo được bộ bảy sau khi schema mở rộng.

Chuyển danh mục sớm sẽ khiến Ledger cũ tạo hũ mới mà bỏ trống `purpose`. Chạy Ledger mới trước schema sẽ khiến những truy vấn cần cột đó lỗi.

### Bước 2. Nghiệp vụ theo `purpose` và hũ Nghĩa vụ chung

- [x] Truyền `purpose` qua tạo, đọc, sửa và reset. Cập nhật hợp đồng API, Ledger, Agent, Planner, forecast và frontend. Bên đọc phải chấp nhận dữ liệu thiếu `purpose` và dữ liệu có `purpose`. Agent cũ kiểm tra chặt trường trả về, nên cập nhật bên đọc trước khi Ledger phát trường mới.
- [x] Dùng `buffer` cho số dư Dự phòng trong Planner, stress test và LP, giữ quy tắc tương thích cho ví cũ chưa có `purpose`. Đưa `goal` vào luồng mục tiêu và lộ trình hiện có; hũ `goal` phải có số tiền và hạn. Cho `sinking` lưu khoản cần (tên, số tiền, ngày cần) và giữ ngày đã cam kết.
- [x] Hũ Nghĩa vụ chung là nguồn trả mặc định cho tiền nhà, hóa đơn, khoản vay và Trả Sau. Ưu tiên nguồn đã lưu. Khi ví cũ thiếu hũ Nghĩa vụ và chưa có nguồn hợp lệ, yêu cầu chọn hũ trả. Dùng cùng quy tắc trong sổ cái và what-if, đồng thời kiểm tra các luồng còn chọn hũ `obligation` đầu tiên.
- [x] Dự báo hũ Nghĩa vụ liệt kê các khoản đến hạn trước kỳ lương kế tiếp theo ngày, nêu khoản đầu tiên bị thiếu và số thiếu.
- [x] Ghi và dự báo một khoản đến hạn gồm cả gốc và phí Trả Sau khi phí đã nằm trong tổng. Phí trả ngay đi theo giao dịch gốc.
- [x] Tính sàn thiết yếu của Chi hằng ngày theo phần chi có loại giao dịch thiết yếu (ăn uống, đi lại), không theo cả hũ. Nếu chưa làm kịp, giữ cách hiện tại và ghi rõ giới hạn trong bảng "Vì sao" của lộ trình.

### Bước 3. Kê khai ở bước 3 của onboarding

- [ ] **Nghĩa vụ theo số đã khai.** Sau khi người dùng khai nghĩa vụ, server tính tỷ lệ đề xuất = tổng nghĩa vụ quy về tháng ÷ lương đã khai, làm tròn lên điểm nguyên. Lệch tỷ lệ đang đặt từ 1 điểm thì hiện thẻ. Phần chênh lấy từ hoặc trả về Chi hằng ngày trước, Dự phòng sau; Dự phòng không xuống dưới sàn `buffer_min_split_percent` (giả định 10%).
- [ ] **Khoản biết trước.** Thêm câu hỏi tùy chọn "Khoản biết trước trong 12 tháng tới" (Tết, học phí, bảo hiểm năm…), mỗi khoản có tên, số tiền và ngày cần. Có khai thì đề xuất tạo Quỹ dồn với tỷ lệ = số tiền còn thiếu ÷ số kỳ lương còn lại trước ngày cần ÷ lương, làm tròn lên điểm nguyên, nguồn bù như trên. Không khai thì không tạo hũ.
- [ ] **Kiểm tra theo ngày.** Với kỳ lương hiện tại và kỳ kế tiếp, cộng các khoản đến hạn trước ngày lương rồi so với số dư cộng phần chia. Thiếu thì thẻ nêu khoản nào thiếu và thiếu bao nhiêu.
- [ ] **Bỏ qua bước 3.** Giữ tỷ lệ mẫu và ghi "chưa có số khai" trên thẻ hũ.
- [ ] **Nghĩa vụ vượt số tiền chia được.** Khi tổng Nghĩa vụ, Quỹ dồn và sàn Dự phòng vượt 100%, không lưu tỷ lệ và không gợi ý cắt khoản thiết yếu (BR-21). Hiện danh sách nghĩa vụ theo thứ tự ưu tiên (nhà ở, điện nước, rồi nợ) và mở lộ trình.
- [ ] Mẫu số chỉ là lương đã khai. Lương nhận lệch số khai quá ngưỡng BR-12 thì hỏi cập nhật lương trước khi đề xuất.

### Bước 4. Xác nhận mọi thay đổi tỷ lệ

- [ ] Thẻ và bản xem trước `save_jars` hiện lý do bằng số đo, tỷ lệ trước và sau, số tiền mỗi kỳ lương trước và sau, và phần chênh lệch. Server tính mọi số (BR-47, BR-48).
- [ ] Người dùng chọn Đồng ý, Sửa số hoặc Không đổi. Tổng phải bằng 100% mới lưu được. Thay đổi chỉ có hiệu lực sau khi xác nhận qua `save_jars` (BR-45).
- [ ] Tỷ lệ mới áp từ lần xác nhận chia lương đầu tiên sau khi lưu. Nếu đang có sự kiện lương chờ, thẻ hỏi rõ "áp cho kỳ này" hay "từ kỳ sau". Dự báo cập nhật ngay và thẻ ghi rõ điều đó.

### Bước 5. Demo bốn hũ

- [x] Viết cấu hình demo bốn hũ theo bảng "Demo (Reset data)". Bỏ ánh xạ sang Quỹ dồn và Tích lũy dài hạn; dòng chia lương cũ của các hũ bị bỏ gộp vào hũ nhận tương ứng.
- [x] Cập nhật [lộ trình seed của Minh](../../data/personas/roadmaps/minh_six_jars.json) nếu còn tham chiếu hũ bị bỏ. Lộ trình hiện chỉ dùng Mục tiêu, Nghĩa vụ, Chi hằng ngày và Dự phòng.
- [x] Kiểm tra cả bốn persona sau reset. Lan có thêm hũ Nghĩa vụ (C-07).
- [ ] Chạy lại cảnh 1 đến 4 theo [kịch bản demo](demo-script.md) bằng engine cục bộ. Số đợt trước, cần xác nhận lại:
  - Cảnh 1: Chi hằng ngày có 1.080.000 ₫ và dự kiến cạn ngày 03/12, trước kỳ lương 05/12.
  - Cảnh 2: mua tai nghe 1.200.000 ₫ bằng Trả Sau, Nghĩa vụ có khoản đến hạn 2.200.000 ₫ ngày 03/12, đã gồm phí 33.000 ₫, và dự kiến thiếu khoảng 761.000 ₫.
- [ ] Sửa lời dẫn trong kịch bản demo. Cảnh 1 nêu hai nguyên nhân: nhịp chi và 700.000 ₫ đã để riêng cho nghĩa vụ. Cảnh 2 nêu ngày đến hạn 03/12 là điều khoản mô phỏng (spec Minh và BR-22 dùng ngày 5) và liệt kê các khoản đến hạn trước lương: cơm văn phòng, tiền điện, Trả Sau.

### Bước 6. Kiểm thử cục bộ

- [ ] Duy trì fixture riêng cho ví cũ chưa reset, ví ba hũ và ví demo bốn hũ. Cập nhật các ca tích hợp sau reset còn truy vấn `an_uong`, kỳ vọng mốc cạn 23/11 hoặc kỳ vọng sáu hũ. Giữ các ca dùng mã cũ để kiểm hành vi tương thích.
- [ ] Kiểm tài khoản mới có và không có kê khai, tài khoản cũ chưa reset, và tài khoản demo reset hai lần. Xác nhận đúng số hũ và tổng 100%, dữ liệu cũ còn nguyên trước reset, reset lặp lại giữ số dư nhất quán và hũ không bị trùng.
- [ ] Kiểm ca nghĩa vụ vượt số tiền chia được và ca có sự kiện lương chờ khi đổi tỷ lệ.
- [ ] Kiểm quay lui: đổi cấu hình onboarding về bộ bảy thì tài khoản mới nhận bộ bảy, reset demo vẫn chạy.

Chỉ chạy test đã kiểm tra là dùng tài nguyên cục bộ. Đợt trước đã đạt 234 ca PostgreSQL cục bộ và chạy hai cảnh demo; cần chạy lại các ca chịu ảnh hưởng.

### Bước 7. Thứ tự phát hành sau khi được duyệt

1. Áp dụng schema tương thích trong khi bộ bảy còn hoạt động.
2. Cập nhật các bên đọc dữ liệu hũ, sau đó cập nhật Ledger và các luồng ghi. Kiểm tra cả ví cũ và ví có `purpose` trên môi trường đã được phép kiểm thử.
3. Bật cấu hình demo bốn hũ, rồi bật bộ ba cho onboarding. Kiểm tra lại hai luồng với tài khoản thử.
4. Nếu cần quay lui, chuyển cấu hình cho các lần tạo ví và reset tiếp theo. Giữ schema và các bên đọc tương thích để những ví đã tạo vẫn hoạt động.

## Chưa làm trong lượt này

Các mục dưới đây đã bàn nhưng **chưa làm trong lượt này**. Ghi lại để không mất và để biết điều kiện bắt đầu.

| Mục | Nguồn | Lý do chưa làm | Điều kiện để làm |
| --- | --- | --- | --- |
| Gợi ý chỉnh tỷ lệ theo lịch sử chi tiêu (BR-80 đến BR-82) | File đề xuất | Mốc 2 kỳ lương và ngưỡng 5 điểm chưa có bằng chứng; Monarch dùng 6 tháng, YNAB tối đa 12 tháng. Chưa persona nào có đủ 2 kỳ lương trọn | Có dữ liệu pilot; bật bằng cờ, ghi lại lượt đồng ý và độ lệch để chỉnh ngưỡng. Loại kỳ có Tết hoặc lương tháng 13, thêm ngưỡng theo số tiền |
| Bộ hũ theo giai đoạn sống (BR-70, BR-71) | Notion, B2a | Hai trong ba bộ chưa có nguồn (C-11). Khác biệt lớn nhất là tiền nhà, đã xử lý bằng kê khai | Có khảo sát hoặc dữ liệu pilot cho tỷ lệ từng giai đoạn |
| Kê khai qua chat với agent | Rà soát | Đợt này làm form bước 3 trước. Chưa có công cụ nhận khoản biết trước | Có tool nhận khoản Quỹ dồn; agent dùng cùng quy tắc tính |
| Tự tính lại mức góp Quỹ dồn mỗi kỳ lương (BR-66) | Notion | Đợt này chỉ tính tỷ lệ một lần khi khai | Sau khi bước 3 ổn định |
| Gợi ý thêm hũ theo tín hiệu (BR-84), gồm gợi ý Quỹ dồn khoảng 3 tháng trước Tết | File đề xuất | Cần cổng bản tin và quy tắc kích hoạt | Sau bước 3 |
| Mục tiêu tự tính và khóa mềm khi rút Dự phòng (BR-64) | Notion | Cần bản xem trước ảnh hưởng tới Điểm chống chịu | Gắn với luồng rút tiền |
| Cổng mở Tích lũy dài hạn (BR-68) | Notion | Chưa tạo sẵn hũ này. Người dùng tự thêm vẫn được như hiện nay, nên chưa có chặn | Khi làm mục tiêu Dự phòng (BR-64) |
| Tách hũ Trả sau và vay | Notion | Đã chốt một hũ Nghĩa vụ chung (Q5) | Khi nhóm muốn tách nợ khỏi tiền nhà |
| Dự báo theo loại hũ (BR-73) | B2a | Engine đang dự báo mọi hũ người dùng như nhau | Sau khi `purpose` chạy ổn định |
| Review Kiro Opus 5.5 read-only (`kiro-worker`, `Tier: deep`, `Spec: no`) | Kế hoạch cũ | Cần phê duyệt chi phí | Có đồng ý rõ ràng; phạm vi là nguồn trả nghĩa vụ, `purpose`, cấu hình hũ và tương thích reset |

## Bàn giao

- Bàn giao diff trên nhánh riêng, SHA gốc, kết quả kiểm thử và thứ tự phát hành. Push, merge và deploy cần chỉ đạo riêng.
- Mọi eval và thao tác có thể phát sinh phí hoặc tiêu hao credits cần đồng ý rõ ràng trước.

## Căn cứ chính

- Quỹ khẩn cấp dành cho khoản không dự tính trước, quy mô tùy hoàn cảnh: [CFPB](https://www.consumerfinance.gov/an-essential-guide-to-building-an-emergency-fund/). Đệm khoảng 6 tuần thu nhập ròng; tiết kiệm theo % cố định có thể không đủ: [JPMorgan Chase Institute](https://www.jpmorganchase.com/institute/all-topics/household-financial-health/report-weathering-volatility-2-a-monthly-stress-test-to-guide-saving).
- Ưu tiên hóa đơn theo hậu quả và lên lịch theo ngày lương: [CFPB prioritizing bills](https://files.consumerfinance.gov/f/documents/cfpb_your-money-goals_prioritizing-bills_tool.pdf), [CFPB bill calendar](https://www.consumerfinance.gov/documents/7168/cfpb_your-money-your-goals_bill_calendar_tool_2018-11_ADA.pdf).
- Mặc định thường được giữ nguyên: [Madrian và Shea 2001](https://www.nber.org/papers/w7682).
- Phí dịch vụ Ví Trả Sau 33.000 ₫ mỗi tháng có giao dịch: [biểu phí MoMo](https://www.momo.vn/vi-tra-sau/bieu-phi).
- Cửa sổ lịch sử của sản phẩm khác: [Monarch](https://help.monarch.com/hc/en-us/articles/360048883631-Creating-Your-Budget-in-Monarch), [YNAB](https://support.ynab.com/en_us/auto-assign-a-guide-r1gBNbBJo).
- Không nguồn nào ở trên chứng minh một tỷ lệ hũ, số hũ, mốc 2 kỳ lương hay ngưỡng 5 điểm là tối ưu.
