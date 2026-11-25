# Lộ trình bộ hũ mặc định và tỷ lệ theo kê khai

Ngày lập: 25/11/2026. Cập nhật sau khi rà soát với trang Notion "Feedback hũ" và file đề xuất BR-78 đến BR-84.  
Nhánh: `feat/default-six-jars`  
SHA gốc đã đối chiếu với `origin/main`: `865fba9f60039294c9afdb936a1c1f401de11430`. Commit WIP chứa bộ sáu hũ: `622a1b0`.

Tên file giữ nguyên để không gãy liên kết, nhưng phạm vi đã đổi: người dùng mới nhận **ba hũ**, demo dùng **cấu hình hũ riêng**: hai hũ mặc định cộng các hũ người dùng tự thêm (đổi 26/11, issue #39). Trước khi sửa tiếp, xác minh lại worktree, nhánh, SHA và `origin/main` theo hướng dẫn Git của dự án.

## Quyết định đã chốt

| # | Quyết định | Ghi chú |
| --- | --- | --- |
| Q1 | Người dùng mới nhận ba hũ: Chi hằng ngày, Nghĩa vụ, Dự phòng | Các hũ để dành khác chỉ tạo khi có số liệu (mục "Cấu hình hũ") |
| Q2 | Demo có cấu hình hũ riêng, không đọc bộ mặc định của onboarding. **Đổi 26/11**: bộ demo là hai hũ mặc định Nghĩa vụ, Dự phòng cộng các hũ người dùng tự thêm (Ăn uống, Đi lại, Giải trí, Mục tiêu, Đầu tư); không có hũ Chi hằng ngày | Cả bốn persona (`minh`, `khoa`, `lan`, `vy`) dùng chung cấu hình demo. Lý do đổi: PELT, hồ sơ hành vi và cờ đổi hành vi tính theo mã hũ; gom Ăn uống, Đi lại, Giải trí vào một hũ thì mất tín hiệu, mà cảnh 1 và cảnh 4 (kiểm trên app tối 25/11: Ăn uống cạn 23/11, CSV cảnh 4 vào Ăn uống rồi PELT xác nhận) dựa vào hũ `an_uong` |
| Q3 | ~~Minh có bốn hũ: Chi hằng ngày, Nghĩa vụ, Dự phòng, Mục tiêu~~. **Đổi 26/11**: Minh có bảy hũ (bảng "Demo (Reset data)") | Cùng lý do với Q2. Đầu tư là hũ mới 0 ₫, không lịch sử (câu chuyện: người dùng tự thêm); Quỹ dồn và Tích lũy dài hạn vẫn không có trong demo |
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

Đổi 26/11 (issue #39, lý do ở Q2). Cấu hình ở [`jar_layout.py`](../../gateway/tools/ledger/yofina_ledger/jar_layout.py) (`DEMO_LAYOUT`: mã, tên, loại, `purpose`), ánh xạ hũ persona sang hũ demo ở [`six_jars.py`](../../data/personas/six_jars.py) (`JAR_ALIASES`, mã không có trong ánh xạ giữ nguyên). Số dư, tỷ lệ, lịch sử, dòng chia lương cũ, hũ trả của nghĩa vụ, nhãn phân loại seed và lộ trình seed đi theo cùng ánh xạ; không bảng tỷ lệ nào chép cứng.

| Hũ | Mã | Loại | `purpose` | Hũ persona gộp vào | Tỷ lệ của `minh` | Số dư sau reset của `minh` |
| --- | --- | --- | --- | --- | ---: | ---: |
| Ăn uống (tự thêm) | `an_uong` | `spending` | — | `an_uong`, giữ nguyên mọi dòng | 30% | 380.000 ₫ |
| Đi lại (tự thêm) | `di_lai` | `spending` | — | `di_lai`, giữ nguyên | 7% | 640.000 ₫ |
| Nghĩa vụ (mặc định) | `nghia_vu` | `obligation` | — | `nghia_vu` + `hoa_don` | 31 + 5 = 36% | 1.450.000 ₫ |
| Giải trí (tự thêm) | `giai_tri` | `spending` | — | `giai_tri`, giữ nguyên | 7% | 760.000 ₫ |
| Hũ mục tiêu (tự thêm), tên theo hũ nguồn: "Du lịch" | `muc_tieu` | `saving` | `goal` | `du_lich`, tên, mục tiêu và hạn lấy từ hũ nguồn (6.000.000 ₫, 01/04/2027) | 10% | 1.800.000 ₫ |
| Dự phòng (mặc định) | `du_phong` | `saving` | `buffer` | `du_phong` | 10% | 2.700.000 ₫ |
| Đầu tư (tự thêm) | `dau_tu` | `saving` | `long_term` | không có (hũ mới, không lịch sử) | 0% | 0 ₫ |
| **Tổng** | | | | | **100%** | **7.730.000 ₫** (như ví persona) |

- Tỷ lệ mỗi hũ là tổng tỷ lệ của hũ nguồn trong spec persona, nên tổng luôn 100% và mỗi persona giữ tỷ lệ của mình. Đầu tư 0% (DB cho phép `split_percent` từ 0 tới 100; không bịa tỷ lệ cho hũ không có nguồn). Dự báo của Đầu tư (0 ₫, không chi, không khoản đến hạn) là "đủ", không có ngày cạn: engine không đặt ngày cạn cho hũ không có gì rút tiền (`yofina_ml.montecarlo.summarize_paths`), nên không màn, thẻ hay what-if nào nói hũ này cạn (`tests/local_pg/test_empty_saving_jar.py`).
- Persona thiếu hũ nguồn: hũ mục tiêu chỉ tạo khi persona có hũ nguồn mang mục tiêu (`goal` phải có số tiền và hạn, `save_jars` từ chối hũ `goal` thiếu một trong hai), các hũ khác luôn tạo (0 ₫, 0% nếu không có nguồn). Kết quả: `minh`, `vy` có 7 hũ (Mục tiêu của `vy` là 10.000.000 ₫, hạn 01/06/2027 từ hũ Du lịch của `vy`); `lan`, `khoa` có 6 hũ. Persona có hũ không nằm trong ánh xạ thì đặt lại báo lỗi thay vì bỏ số dư.
- Hũ trả của nghĩa vụ theo cùng ánh xạ: Tiền cơm văn phòng vẫn trả từ Ăn uống (mốc cạn 23/11 của cảnh 1), Netflix từ Giải trí, tiền nhà và hóa đơn từ Nghĩa vụ (gộp từ Hóa đơn); Trả sau trả từ Nghĩa vụ.
- Bỏ khoản chuyển 700.000 ₫ "Để riêng tiền trả nghĩa vụ" của bộ bốn hũ: nó lấy từ Chi hằng ngày, hũ không còn trong ví demo; Ăn uống không được đổi số dư hay chuỗi chi; lấy từ hũ khác (Dự phòng, Mục tiêu) là bịa thêm một giao dịch và làm đổi cảnh 3. Không có khoản này, Nghĩa vụ vẫn sát trước khi mua (1.450.000 ₫ cho Tiền điện 375.000 ₫ ngày 26/11 và Trả sau 1.000.000 ₫ ngày 03/12) và thiếu sau khi mua tai nghe, nên cảnh 2 vẫn có nghĩa (số đo ở Bước 5).
- Trả sau của `minh` đến hạn ngày 3 trên ví demo (`DEMO_CREDIT_DUE_DAY`, spec và BR-22 dùng ngày 5): giữ vì cửa sổ "đến hạn trước kỳ lương" của hũ Nghĩa vụ chỉ lấy khoản có ngày đến hạn **trước** ngày lương (`yofina_core.schedule.obligation_window`), khoản đến hạn đúng 05/12 sẽ không nằm trong danh sách của cảnh 2.
- Lộ trình seed: không có file riêng cho bộ hũ demo; đặt lại nạp `data/personas/roadmaps/minh.json` (v1 đã thay, v2 đang dùng, 120 ngày) với mã hũ đổi theo `JAR_ALIASES` (`du_lich` thành `muc_tieu`). `minh_six_jars.json` (dựng từ seed 47 ngày cũ, có `behavior_flag` và v3 `behavior_changed`) đã bỏ.

Reset data chỉ dùng được với tài khoản thuộc nhóm demo ([`rest_api.py`](../../gateway/tools/ledger/yofina_ledger/rest_api.py), route `POST /demo/reset`) và thay toàn bộ dữ liệu bằng persona. Tài khoản thật đã có hũ **không** được chuyển bộ; người dùng tự sửa hũ ở màn "Thêm hoặc sửa hũ".

## Hiện trạng commit WIP cần sửa

| Chỗ | Commit WIP đang làm | Cần đổi |
| --- | --- | --- |
| [Migration 0057](../../db/migrations/0057_default_six_jars.sql) (trước khi gộp vào `main` là 0055) và [seed](../../db/seed/jar_templates.sql) | Bật bộ sáu ngay khi chạy | Tách phần schema và phần bật bộ hũ (bước 1) |
| [`six_jars.py`](../../data/personas/six_jars.py) | Lấy hũ demo từ `is_default`, báo lỗi nếu không đúng sáu hũ | Đọc cấu hình demo riêng (bước 1, bước 5); 26/11 đổi sang bộ hũ có hũ tự thêm (`apply_demo_layout`) |
| [`service.py` `reset_demo`](../../gateway/tools/ledger/yofina_ledger/service.py) | Lấy `purpose` từ danh mục mặc định | Lấy từ cấu hình demo |
| [`settings.py`](../../pipelines/forecast/yofina_forecast/settings.py) `DEFAULT_ESSENTIAL_JAR_CODES` | Coi cả Chi hằng ngày là thiết yếu, kể cả giải trí | Tính sàn theo phần chi thiết yếu (bước 2) |
| [`wallet_writes.py` `_prep_save_jars`](../../gateway/tools/ledger/yofina_ledger/wallet_writes.py) | Bản xem trước chỉ có % trước và sau | Thêm số tiền mỗi kỳ và kỳ áp dụng (bước 4) |

## Lộ trình thực hiện

### Bước 1. Tách cấu hình bộ hũ và migration

- [x] Thêm cấu hình bộ hũ riêng cho onboarding và cho demo (ví dụ `jar_layout`). Onboarding đọc bộ ba; Reset data đọc bộ demo. Bỏ điều kiện "đúng sáu hũ" trong `use_default_jars` (26/11: đổi tên thành `apply_demo_layout`).
- [x] Tách [migration 0057](../../db/migrations/0057_default_six_jars.sql) thành phần mở rộng schema và phần bật bộ hũ. Thêm `purpose` cho `jars` và `jar_templates`, chấp nhận `NULL` trên dữ liệu cũ. Giữ hợp đồng đọc cũ trong giai đoạn chạy xen kẽ, kể cả quyền truy cập và RLS.
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

- [x] **Nghĩa vụ theo số đã khai.** Sau khi người dùng khai nghĩa vụ, server tính tỷ lệ đề xuất = tổng nghĩa vụ quy về tháng ÷ lương đã khai, làm tròn lên điểm nguyên. Lệch tỷ lệ đang đặt từ 1 điểm thì hiện thẻ. Phần chênh lấy từ hoặc trả về Chi hằng ngày trước, Dự phòng sau; Dự phòng không xuống dưới sàn `buffer_min_split_percent` (giả định 10%).
- [x] **Khoản biết trước.** Thêm câu hỏi tùy chọn "Khoản biết trước trong 12 tháng tới" (Tết, học phí, bảo hiểm năm…), mỗi khoản có tên, số tiền và ngày cần. Có khai thì đề xuất tạo Quỹ dồn với tỷ lệ = số tiền còn thiếu ÷ số kỳ lương còn lại trước ngày cần ÷ lương, làm tròn lên điểm nguyên, nguồn bù như trên. Không khai thì không tạo hũ.
- [x] **Kiểm tra theo ngày.** Với kỳ lương hiện tại và kỳ kế tiếp, cộng các khoản đến hạn trước ngày lương rồi so với số dư cộng phần chia. Thiếu thì thẻ nêu khoản nào thiếu và thiếu bao nhiêu.
- [x] **Bỏ qua bước 3.** Giữ tỷ lệ mẫu và ghi "chưa có số khai" trên thẻ hũ.
- [x] **Nghĩa vụ vượt số tiền chia được.** Khi tổng Nghĩa vụ, Quỹ dồn và sàn Dự phòng vượt 100%, không lưu tỷ lệ và không gợi ý cắt khoản thiết yếu (BR-21). Hiện danh sách nghĩa vụ theo thứ tự ưu tiên (nhà ở, điện nước, rồi nợ) và mở lộ trình.
- [x] Mẫu số chỉ là lương đã khai. Lương nhận lệch số khai quá ngưỡng BR-12 thì hỏi cập nhật lương trước khi đề xuất.

### Bước 4. Xác nhận mọi thay đổi tỷ lệ

- [x] Thẻ và bản xem trước `save_jars` hiện lý do bằng số đo, tỷ lệ trước và sau, số tiền mỗi kỳ lương trước và sau, và phần chênh lệch. Server tính mọi số (BR-47, BR-48).
- [x] Người dùng chọn Đồng ý, Sửa số hoặc Không đổi. Tổng phải bằng 100% mới lưu được. Thay đổi chỉ có hiệu lực sau khi xác nhận qua `save_jars` (BR-45).
- [x] Tỷ lệ mới áp từ lần xác nhận chia lương đầu tiên sau khi lưu. Nếu đang có sự kiện lương chờ, thẻ hỏi rõ "áp cho kỳ này" hay "từ kỳ sau". Dự báo cập nhật ngay và thẻ ghi rõ điều đó.

### Bước 5. Demo có hũ tự thêm (đổi 26/11)

Bản 25/11 làm demo bốn hũ (Chi hằng ngày 45%, Nghĩa vụ 35%, Dự phòng 15%, Mục tiêu 5%, khoản chuyển 700.000 ₫ để riêng cho nghĩa vụ, lộ trình riêng `minh_six_jars.json`). Ngày 26/11 chủ dự án đổi Q2, Q3; bản dưới thay bản đó.

- [x] Viết cấu hình demo theo bảng "Demo (Reset data)": `DEMO_LAYOUT` và `JAR_ALIASES`; tỷ lệ, số dư, mục tiêu suy từ spec persona; dòng chia lương cũ gộp theo ánh xạ (một dòng mỗi hũ mỗi kỳ, như `confirm_salary`).
- [x] Lộ trình seed của Minh dựng từ [`roadmaps/minh.json`](../../data/personas/roadmaps/minh.json) của `main` qua cùng ánh xạ (`roadmap_seed.load_seed(..., jar_aliases=...)`); bỏ `minh_six_jars.json`. Test unit kiểm file đổi mã y hệt file gốc ngoài mã hũ.
- [x] Kiểm cả bốn persona sau reset, reset hai lần cho cùng kết quả, tổng tiền ví bằng persona gốc (`tests/local_pg/test_default_six_jars.py`, `tests/unit/test_personas.py`).
- [x] Chạy lại cảnh 1 đến 4 bằng engine cục bộ, ngày mô phỏng 21/11/2026 (`tests/local_pg/test_demo_scenes.py` với `-s`; cảnh 4: `tests/unit/ingest/test_scene4_statement.py`, `scripts/measure_scene4_pelt.py`). Kết quả 26/11 (PostgreSQL cục bộ, 10.000 đường, what-if 5.000 đường, người dùng thử `sub-minh`):
  - Cảnh 1: Ăn uống 380.000 ₫ cạn **23/11**, `days_to_payday` 14 (lương 05/12), khả năng hụt 1,0, nhóm tin cậy `high` (Cao), thẻ chủ động `runout_warning`. Ăn uống, Đi lại, Giải trí dự báo y hệt ví persona trên cùng người dùng. Đi lại 640.000 ₫ và Giải trí 760.000 ₫ "đủ", không nêu ngày cạn (`runout_date_shown` sai, hũ thưa #25). Nghĩa vụ 1.450.000 ₫ "sát" (khả năng hụt 0,26).
  - Cảnh 2: mua tai nghe 1.200.000 ₫ bằng Trả sau: khoản đến hạn 03/12 thành 2.200.000 ₫ (1.000.000 ₫ có sẵn gồm phí 33.000 ₫, cộng 1.200.000 ₫, phí không cộng thêm vì tháng đã có phí). Hũ Nghĩa vụ liệt kê trước lương: Tiền điện 375.000 ₫ (tối đa 450.000 ₫) ngày 26/11, Trả sau 2.200.000 ₫ ngày 03/12; khoản thiếu đầu tiên là Trả sau 03/12, thiếu **1.162.559 ₫** (số dư P50 trước hạn 1.037.441 ₫). Trước khi mua không có khoản thiếu.
  - Cảnh 3: điểm 29 → 12 khi mất việc 2 tháng, trụ **25 ngày** (mốc trên app 25/11: 29 → 12, 24 ngày). Ví persona trên cùng máy cũng ra 25 ngày, nên lệch một ngày không do bộ hũ: hạt Monte Carlo theo mã người dùng (`sub-minh` cục bộ, tài khoản thật trên app) và ngày mô phỏng lúc đo.
  - Cảnh 4 (phần không cần model): 32 dòng tự vào Ăn uống trên cả ví persona và ví demo; PELT xác nhận từ hệ số 2,1 (ngưỡng mịn 2,04), tệp dùng 3,5 xác nhận 20/20 hạt chia khoản khi tải trong ngày và trễ một ngày, y hệt ví persona.
- [ ] Sửa lời dẫn trong kịch bản demo (người điều phối làm): cảnh 1 không còn "700.000 ₫ đã để riêng"; cảnh 2 nêu ngày đến hạn 03/12 là điều khoản mô phỏng.

### Bước 6. Kiểm thử cục bộ

- [ ] Duy trì fixture riêng cho ví cũ chưa reset, ví ba hũ và ví demo (26/11: bảy hũ, có `an_uong`). Cập nhật các ca tích hợp sau reset còn truy vấn `an_uong`, kỳ vọng mốc cạn 23/11 hoặc kỳ vọng sáu hũ. Giữ các ca dùng mã cũ để kiểm hành vi tương thích.
  - 25/11: phần fixture cục bộ đã có (`tests/local_pg/test_default_six_jars.py`: ví cũ, bộ ba, demo bốn hũ). Chưa sửa 10 file trong `tests/integration` còn truy vấn `an_uong` (73 chỗ) vì chỉ kiểm được khi chạy tích hợp với AWS; xem HANDOFF mục "Cần chạy khi được duyệt".
  - 26/11: ví demo lại có `an_uong`, `di_lai`, `giai_tri` với số dư như persona; các ca tích hợp truy vấn `an_uong` và mốc cạn 23/11 khớp lại, chỉ còn ca nào hỏi `hoa_don` hay `du_lich` trên ví demo (nay là `nghia_vu`, `muc_tieu`) cần xem khi chạy tích hợp. `tests/local_pg/test_forecast_pipeline.py` lấy lại kỳ vọng của `main` (Ăn uống cạn 23/11, thẻ `runout_warning`).
- [x] Kiểm tài khoản mới có và không có kê khai, tài khoản cũ chưa reset, và tài khoản demo reset hai lần. Xác nhận đúng số hũ và tổng 100%, dữ liệu cũ còn nguyên trước reset, reset lặp lại giữ số dư nhất quán và hũ không bị trùng.
- [x] Kiểm ca nghĩa vụ vượt số tiền chia được và ca có sự kiện lương chờ khi đổi tỷ lệ.
- [x] Kiểm quay lui: đổi cấu hình onboarding về bộ bảy thì tài khoản mới nhận bộ bảy, reset demo vẫn chạy.

Chỉ chạy test đã kiểm tra là dùng tài nguyên cục bộ. Đợt trước đã đạt 234 ca PostgreSQL cục bộ và chạy hai cảnh demo; cần chạy lại các ca chịu ảnh hưởng.

### Bước 7. Thứ tự phát hành sau khi được duyệt

1. Áp dụng schema tương thích trong khi bộ bảy còn hoạt động.
2. Cập nhật các bên đọc dữ liệu hũ, sau đó cập nhật Ledger và các luồng ghi. Kiểm tra cả ví cũ và ví có `purpose` trên môi trường đã được phép kiểm thử.
3. Bật cấu hình demo (bảng "Demo (Reset data)"), rồi bật bộ ba cho onboarding. Kiểm tra lại hai luồng với tài khoản thử.
4. Nếu cần quay lui, chuyển cấu hình cho các lần tạo ví và reset tiếp theo. Giữ schema và các bên đọc tương thích để những ví đã tạo vẫn hoạt động.
   - Công tắc: context `onboardingJarLayout` của `infra-cdk` thành biến `YOFINA_ONBOARDING_JAR_LAYOUT` của Lambda ledger (mặc định `catalogue`). Quay lui bộ bảy hũ cho tài khoản mới: `uv run scripts/cdk.py deploy YofinaTools --require-approval never -c onboardingJarLayout=legacy` (giữ `-c` này ở mọi lần deploy `YofinaTools` sau cho tới khi bật lại); bật lại: deploy không có `-c` hoặc `-c onboardingJarLayout=catalogue`. Reset demo không đọc công tắc này (bảng [`infra-cdk/README.md`](../../infra-cdk/README.md), test `infra-cdk/test/onboarding-jar-layout.test.ts`).

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
