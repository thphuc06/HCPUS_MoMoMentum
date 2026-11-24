# Ràng buộc nghiệp vụ (BC) và quy tắc nghiệp vụ (BR)

> Bản nháp để chủ dự án duyệt, tổng hợp ngày 22/11/2026. Các quy tắc này trước đây nằm rải rác trong proposal, master-plan, ADR, file phase, `contracts/README.md` và code. File này gom lại, đánh mã, ghi nguồn và trạng thái để đội technical bám theo.
> Khi file này lệch với code thì **code đang chạy là hiện trạng**, file này là ý định. Mỗi chỗ lệch được ghi ở cột "Ghi chú" hoặc ở [mục C](#c-việc-cần-chủ-dự-án-quyết).

**Trạng thái:**
- **Chốt**: chủ dự án đã quyết.
- **Code**: đã cài và có test.
- **Thiết kế**: có trong proposal hoặc plan, chưa cài.
- **Đề xuất**: người tổng hợp thêm vào, cần duyệt.
- **Cần quyết**: còn thiếu giá trị hoặc định nghĩa.

**Tham số**: tên cấu hình (SSM `/yofina/<tên>` hoặc biến môi trường). Giá trị triển khai nằm ở SSM, không nằm trong repo. Giá trị ghi ở đây lấy từ ADR, mặc định trong code hoặc test, nên cần đối chiếu.

## A. Ràng buộc nghiệp vụ (BC)

Ràng buộc là điều kiện từ bên ngoài (pháp lý, cuộc thi, nguồn lực) mà sản phẩm phải chấp nhận. Bối cảnh pháp lý ở [01 mục 7](01-boi-canh-thi-truong.md#7-bối-cảnh-pháp-lý-đầu-vào-cho-ràng-buộc-nghiệp-vụ).

| ID | Ràng buộc | Lý do / nguồn | Trạng thái |
|---|---|---|---|
| BC-01 | Không có API giao dịch thật của ví. Dùng **ví mô phỏng** trong app và dữ liệu tổng hợp theo persona; người dùng và giám khảo tự tạo giao dịch | Proposal §1, §7 | Chốt |
| BC-02 | Sản phẩm trả sau là **mô phỏng**, không cấp tín dụng thật. Giao diện ghi "Trả sau (mô phỏng)", không dùng tên "Ví Trả Sau" hay thương hiệu MoMo. Router vẫn hiểu khi người dùng gõ "Ví Trả Sau" | Open-questions (chốt 21/11); Luật TCTD: chỉ tổ chức được cấp phép mới cho vay | Chốt |
| BC-03 | Không khuyến nghị mã cổ phiếu, quỹ cụ thể hay nơi vay. Chỉ nói điều kiện tiên quyết và tỷ lệ theo nhóm | Proposal §1, §13 (rủi ro bị coi là tư vấn đầu tư) | Chốt |
| BC-04 | **Con người quyết định**: agent không tự chuyển tiền hay đổi số dư | Proposal §1; Luật AI (con người giữ quyền kiểm soát) | Chốt |
| BC-05 | Nội dung do AI tạo phải **gắn nhãn** rõ ràng | Luật Trí tuệ nhân tạo 134/2025/QH15, Nghị định 142/2026 Điều 18 | Đề xuất (chưa có trong plan) |
| BC-06 | Dữ liệu cá nhân: đồng ý riêng cho từng nguồn nạp; thu thập tối thiểu; người dùng xem và xóa được dữ liệu và bộ nhớ; che số tài khoản, số điện thoại, tên người nhận trước khi đưa vào LLM. Model có thể xử lý dữ liệu **ngoài Singapore** (profile `global.`), cần công bố khi chạy thật | Luật BVDLCN 91/2025/QH15; proposal §7; open-questions | Thiết kế (phase 5); phần công bố: Cần quyết |
| BC-07 | "**Điểm chống chịu**" luôn kèm dòng "không phải điểm tín dụng". Không dùng tên FinHealth Score | Open-questions (chốt 21/11, vấn đề license) | Chốt |
| BC-08 | Web app ưu tiên điện thoại (khung 390x844), không làm app native. Giao diện và câu trả lời bằng tiếng Việt | Proposal §1 | Chốt |
| BC-09 | **Không hardcode, không giả lập** trên bản deploy: không câu trả lời soạn sẵn, không mock, không số persona trong frontend; mọi số đi từ Aurora qua tool hoặc engine | Master-plan §2 (chốt 21/11) | Chốt |
| BC-10 | **Ngày mô phỏng** theo tài khoản: đặt lại dữ liệu thì quay về ngày neo 21/11/2026 rồi trôi theo thời gian thật. Giao diện ghi "Ví mô phỏng · ngày mô phỏng" | ADR-0003 | Chốt, Code |
| BC-11 | Quota model: Claude 4.x chỉ 10 request/phút mỗi model, không tăng được. Mỗi lượt hội thoại phải tốn ít lượt gọi | Open-questions (chốt 21/11) | Chốt |
| BC-12 | Thời hạn: nộp trước 11/12/2026 (giả định). Thứ tự ưu tiên F1 → F2 → F3 → F4, F5, F6, F7; nếu chậm thì cắt sao kê PDF, FR14, Evaluations, giao diện tối | Master-plan §1; proposal §15 | Giả định, Cần quyết (hạn chính xác) |
| BC-13 | **Phạm vi người dùng: người 18–30 tuổi đang ở giai đoạn có thu nhập đều đặn đầu tiên** (khoảng 0–8 năm đầu), gồm Gen Z đã đi làm và Millennials trẻ. Định nghĩa theo **tuổi và giai đoạn sống**, không theo thế hệ. "Gen Z" chỉ dùng trong truyền thông, và khi trích khảo sát thì ghi đúng nhóm tuổi của khảo sát đó. Lý do: (1) sản phẩm xoay quanh lương và trả sau, mà trả sau yêu cầu từ 18 tuổi (SPayLater 18–55, ZaloPay từ 18; [09](09-phan-tich-doi-thu.md)); năm 2026, Gen Z gồm cả người 14–17 tuổi. (2) Nhóm Gen Z già thêm mỗi năm, còn nhu cầu (thu nhập đầu tiên, thuê trọ, trả sau, xây quỹ đệm) gắn với giai đoạn sống | Đề xuất 24/11 | Đề xuất |

## B. Quy tắc nghiệp vụ (BR)

### B1. Hồ sơ và khai báo

| ID | Quy tắc | Nguồn | Trạng thái | Tham số | FR |
|---|---|---|---|---|---|
| BR-01 | Chỉ **lương thực nhận** và **ngày nhận** là bắt buộc. Phần còn lại (chi phí cố định, khoản vay, mục tiêu, mức rủi ro) khai dần, bằng màn hình hoặc chat | Proposal §4 | Code (onboarding) | — | FR1 |
| BR-02 | Hệ thống **không tự đoán** thu nhập, chi phí cố định hay khoản vay. Dự báo ghi rõ "dựa trên số đã khai" | Proposal §4 | Thiết kế (câu chữ hiển thị chưa kiểm) | — | FR1, FR3 |
| BR-03 | Mức chấp nhận rủi ro: chọn **một trong ba mức**. Dùng cho luật suitability | Proposal §4 | Thiết kế | — | FR12 |

### B2. Hũ và số dư

| ID | Quy tắc | Nguồn | Trạng thái | Tham số | FR |
|---|---|---|---|---|---|
| BR-04 | Hũ của người dùng có loại `spending` (chi theo kỳ), `saving` (tích lũy) hoặc `obligation` (nghĩa vụ). Có thể có mục tiêu (số tiền, hạn). **Tổng tỷ lệ chia lương của các hũ người dùng = 100%**. *Đề xuất 24/11:* hũ `saving` có thêm **mục đích** (BR-63), cơ cấu hũ theo [mục B2a](#b2a-cơ-cấu-hũ-theo-mục-đích-và-giai-đoạn-sống-đề-xuất-2411) | contracts/README | Code (3 loại); mục đích: Đề xuất | — | FR1 |
| BR-05 | Có hai hũ hệ thống. **Tiền vào khác**: chứa mọi tiền vào chưa gán, số dư không âm. **Chưa phân loại**: khoản chi chưa xếp được hũ, số dư **được phép âm** (tiền đã ra khỏi ví nhưng chưa trừ vào hũ nào). Hai hũ này không có tỷ lệ chia, không có mục tiêu, không có dự báo | contracts/README | Code | — | FR1, FR2 |
| BR-06 | **Tổng số dư** = tổng số dư mọi hũ, kể cả hai hũ hệ thống, nên luôn bằng tiền thật trong ví | contracts/README | Code | — | FR1 |
| BR-07 | Số dư mỗi hũ = tổng các dòng sổ cái trả bằng tiền trong hũ (`funding = jar`). Dòng mua bằng trả sau không đổi số dư hũ | contracts/README | Code | — | FR1, FR4 |
| BR-08 | Tiền là **số nguyên VND** ở mọi nơi, không có số lẻ. Hiển thị "1.200.000 ₫" trên thẻ, "1,2 triệu" trong câu chữ | contracts/README | Code | — | Mọi FR |
| BR-09 | Mỗi giao dịch và mỗi lần chuyển giữa hũ có **trần số tiền** | Master-plan (Cedar hạn mức) | Code | `transaction_max_amount_vnd`, `move_max_amount_vnd` | FR1, FR12 |

### B2a. Cơ cấu hũ theo mục đích và giai đoạn sống (đề xuất 24/11)

**Ý tưởng:** mỗi hũ ứng với một **nhu cầu bền vững** của người 18–30, và mỗi loại hũ có **luật riêng**. Mục đích là để luật phù hợp, dự báo và Điểm chống chịu phân biệt được "tiền để tiêu", "tiền phải trả" và "tiền không được đụng".

Bộ 7 hũ hiện tại có hai chỗ lẫn lộn:
- Hũ Hóa đơn (30%) đang thuộc loại `spending`, trong khi hóa đơn và tiền trọ là khoản cố định, biết trước.
- Hũ Du lịch (tiền để tiêu vào một mục tiêu) và hũ Dự phòng (tiền không được đụng) cùng thuộc loại `saving`, nên luật "dự phòng trước đầu tư" (BR-42) không tách được hai loại tiền này.

**Cơ cấu đề xuất:**

| Nhóm | Mục đích | Nhu cầu bền vững | Hũ gợi ý | Luật |
|---|---|---|---|---|
| Chi theo kỳ (`spending`) | — | Sống hằng ngày | Ăn uống, Đi lại, Giải trí, Mua sắm cá nhân | Dự báo ngày cạn theo tốc độ chi (BR-73) |
| Nghĩa vụ (`obligation`) | — | Giữ cam kết | Nhà ở và hóa đơn, Trả sau và vay | Giữ đủ tiền trước ngày đến hạn; không gợi ý cắt khoản thiết yếu (BR-21, BR-69) |
| Tích lũy (`saving`) | `buffer`: đệm an toàn | An toàn trước biến cố | Dự phòng | BR-64, BR-65 |
| | `sinking`: quỹ dồn | Khoản biết trước nhưng không theo tháng | Tết và hiếu hỉ; Học phí và khóa học; Bảo hiểm năm; Sửa xe và điện thoại | BR-66 |
| | `goal`: mục tiêu có hạn | Trải nghiệm, mua sắm lớn | Du lịch, Laptop, Xe | BR-67 |
| | `long_term`: dài hạn | Tương lai xa | Tích lũy dài hạn | BR-68 |

| ID | Quy tắc | Nguồn | Trạng thái | Tham số | FR |
|---|---|---|---|---|---|
| BR-63 | Mỗi hũ loại `saving` có đúng **một mục đích**: `buffer`, `sinking`, `goal` hoặc `long_term`. Hũ loại khác không có mục đích. Mỗi người dùng có **tối đa một** hũ `buffer` | Đề xuất 24/11 | Đề xuất | — | FR1 |
| BR-64 | Hũ **đệm an toàn** có mục tiêu tự tính = **N tháng chi thiết yếu**. Chi thiết yếu = tổng nghĩa vụ hằng tháng + mức chi P50 của các hũ chi theo kỳ được đánh dấu thiết yếu. Rút tiền khỏi hũ đệm là **khóa mềm**: vẫn rút được, nhưng bản xem trước phải hiện ảnh hưởng tới Điểm chống chịu và số ngày trụ được, rồi mới qua xác nhận (BR-45) | Đề xuất 24/11; UOB ACSS 2026: chỉ 47% Gen Z có tiết kiệm đủ hơn 3 tháng ([01](01-boi-canh-thi-truong.md)) | Đề xuất | `buffer_target_months` (mặc định đề xuất 3; xem C-13) | FR1, FR7, FR12 |
| BR-65 | **Thứ tự ưu tiên khi chia tiền dư**: nghĩa vụ đến hạn → hũ đệm (tới mục tiêu) → quỹ dồn có ngày cần gần → mục tiêu → dài hạn. Khi hũ đệm chưa đủ mục tiêu, gợi ý không được đề xuất tăng hũ mục tiêu hay dài hạn trước. Đây là phần cụ thể hóa của BR-42 | BR-42; đề xuất 24/11 | Đề xuất | — | FR8, FR12 |
| BR-66 | Hũ **quỹ dồn** gồm các khoản có tên, số tiền và ngày cần (ví dụ "Tết 3.000.000 ₫, cần trước 25/01"). Số cần trích mỗi kỳ lương = phần còn thiếu ÷ số kỳ lương còn lại trước ngày cần. Ngày cần hiện thành **mốc** trên dòng thời gian dự báo, giống nghĩa vụ. Ý nghĩa: biến "cú sốc biết trước" thành khoản trích đều | Đề xuất 24/11 | Đề xuất | — | FR3, FR4, FR8 |
| BR-67 | Hũ **mục tiêu** bắt buộc có số tiền mục tiêu và hạn. Được đưa vào lộ trình và bộ tối ưu; hạn là ràng buộc mềm, lùi được (BR-54) | Proposal §4 (ví dụ hũ Du lịch); đề xuất 24/11 | Đề xuất | — | FR8 |
| BR-68 | Hũ **dài hạn** chỉ nhận tiền khi (1) hũ đệm đã đạt mục tiêu và (2) không có nghĩa vụ quá hạn. Tiền trong hũ dài hạn và hũ đệm **không tính là tiền có thể chi** trong dự báo và trong kiểm tra trước khi quẹt. Không gợi ý sản phẩm đầu tư cụ thể (BC-03) | BR-42, BC-03; đề xuất 24/11 | Đề xuất | — | FR6, FR8, FR12 |
| BR-69 | Hũ **Nhà ở và hóa đơn** thuộc loại `obligation` (bộ hiện tại để hũ Hóa đơn ở loại `spending`). Các nghĩa vụ đã khai (trọ, điện, nước, thuê bao) trả từ hũ này | Đề xuất 24/11 | Đề xuất; **ảnh hưởng số demo**, xem C-12 | — | FR1, FR4 |
| BR-70 | Có **3 bộ hũ mẫu theo giai đoạn sống** (bảng dưới). Onboarding hỏi giai đoạn bằng **một câu tùy chọn**. Bỏ qua thì dùng bộ "Mới đi làm". Câu này không làm tăng số trường bắt buộc (BR-01 giữ nguyên). Người dùng sửa, thêm, bớt hũ thoải mái | Đề xuất 24/11 | Đề xuất; bộ "Mới đi làm" đã có căn cứ (24/11), hai bộ còn lại minh họa, xem C-11 | Bảng `jar_templates` | FR1 |
| BR-71 | Hệ thống **không tự đổi giai đoạn**. Khi có tín hiệu (lương tăng ổn định qua 2 kỳ, hũ đệm đạt mục tiêu, hết nghĩa vụ vay), lộ trình **gợi ý** chuyển sang bộ hũ của giai đoạn kế tiếp. Người dùng duyệt từng thay đổi tỷ lệ qua xác nhận | Đề xuất 24/11 | Đề xuất | — | FR8 |
| BR-72 | **Hũ tùy chọn** thêm được ở mọi giai đoạn: Gửi về gia đình (nghĩa vụ không thiết yếu, khoản lặp hằng tháng), Phát triển bản thân (quỹ dồn hoặc mục tiêu), Sức khỏe (quỹ dồn) | Đề xuất 24/11 | Đề xuất | — | FR1 |
| BR-73 | **Dự báo theo loại hũ:** chi theo kỳ thì dự báo ngày cạn; nghĩa vụ thì dự báo đủ hay thiếu trước ngày đến hạn; quỹ dồn và mục tiêu thì dự báo tiến độ tới số tiền và ngày cần; đệm và dài hạn thì không dự báo "cạn", chỉ theo dõi mức so với mục tiêu và cảnh báo khi bị rút | Đề xuất 24/11 | Đề xuất (engine hiện dự báo mọi hũ người dùng như nhau) | — | FR3 |

**Ba bộ hũ mẫu theo giai đoạn sống** (tỷ lệ **minh họa**, mỗi bộ cộng đủ 100%; cần nguồn hoặc hiệu chỉnh, xem C-11):

| Hũ | Loại / mục đích | Sinh viên đi làm thêm (18–22) | Mới đi làm (22–26), **mặc định** | Đi làm ổn định (26–30) |
|---|---|---|---|---|
| Ăn uống | chi theo kỳ | 30% | **30%** | 18% |
| Đi lại | chi theo kỳ | 10% | **7%** | 7% |
| Giải trí | chi theo kỳ | 10% | **5%** | 7% |
| Nhà ở và hóa đơn | nghĩa vụ | 20% | **30%** | 25% |
| Trả sau và vay | nghĩa vụ | 5% | **3%** | 3% |
| Học tập / Quỹ dồn (Tết, hiếu hỉ, sửa đồ) | quỹ dồn | 10% (Học tập) | **5%** | 8% |
| Dự phòng | đệm an toàn | 10% | 15% | 12% |
| Mục tiêu (du lịch, laptop…) | mục tiêu | 5% | **5%** | 10% |
| Tích lũy dài hạn | dài hạn | — | — | 10% |
| **Tổng** | | **100%** | **100%** | **100%** |

**Căn cứ của bộ "Mới đi làm" (hiệu chỉnh 24/11).** Hai bộ còn lại vẫn là minh họa.

| Hũ | Tỷ lệ | Căn cứ |
|---|---|---|
| Thu nhập tham chiếu | 10 triệu ₫/tháng | Lao động làm công hưởng lương ở thành thị: 11,2 triệu ₫/tháng, 9 tháng 2026 ([Cục Thống kê, 03/10/2026](https://www.nso.gov.vn/tin-tuc-thong-ke/2026/10/thong-cao-bao-chi-ve-tinh-hinh-lao-dong-viec-lam-quy-iii-va-9-thang-nam-2026/)). Lương khởi điểm mới ra trường khoảng 6–15 triệu ₫ tùy ngành ([Joboko 2026, qua Hướng nghiệp 360](https://huongnghiep360.com/en/news/luong-sinh-vien-moi-ra-truong-2026-theo-nganh)) |
| Nhà ở và hóa đơn | 30% | Phòng trọ, căn hộ mini ở TP.HCM khoảng 2–6 triệu ₫/tháng, là lựa chọn chủ đạo của người trẻ ([Báo Pháp luật, đầu 2026](https://baophapluat.vn/o-gan-trung-tam-hay-ra-thanh-pho-thu-duc-thue-phong-tro-dau-toi-uu-chi-phi-hon.html)). Lấy 2,5 triệu ₫ tiền phòng + khoảng 0,5 triệu ₫ điện, nước, Internet = 3 triệu ₫ |
| Ăn uống | 30% | Chi ăn uống gần 1,4 triệu ₫ trên 2,8 triệu ₫ chi đời sống mỗi người mỗi tháng, tức khoảng 50%, tính cả hộ nông thôn ([Khảo sát mức sống dân cư 2024, Cục Thống kê, 16/05/2025](https://nso.gov.vn/tin-tuc-thong-ke/2025/05/thong-cao-bao-chi-ket-qua-khao-sat-muc-song-dan-cu-nam-2024/)). Người trẻ ở thành phố có thu nhập cao hơn nên tỷ trọng thấp hơn; 30% thu nhập tương đương khoảng 40% chi tiêu nếu chi khoảng 75% thu nhập |
| Hũ đệm | 15% | Đạt 1 tháng chi thiết yếu sau khoảng 5 kỳ lương (K10). CFPB khuyên bắt đầu bằng một mốc nhỏ rồi tiến tới 3–6 tháng chi tiêu ([CFPB](https://www.consumerfinance.gov/an-essential-guide-to-building-an-emergency-fund/), [bộ công cụ CFPB](https://files.consumerfinance.gov/f/documents/cfpb_your-money-your-goals_financial-empowerment_toolkit.pdf)) |
| Đi lại 7%, giải trí 5%, trả sau 3%, quỹ dồn 5%, mục tiêu 5% | 25% | Phần còn lại sau ba hũ trên; **chưa có nguồn riêng**. Nên kiểm bằng khảo sát 50–100 người 18–30 |

**Bộ 7 hũ hiện tại** (`an_uong`, `di_lai`, `hoa_don`, `giai_tri`, `du_lich`, `du_phong`, `nghia_vu`) **giữ nguyên cho tới khi nhóm chốt**, vì persona `minh` và cảnh 1 của demo đang được hiệu chỉnh theo bộ này (C-12).

### B3. Lương và tiền vào

| ID | Quy tắc | Nguồn | Trạng thái | Tham số | FR |
|---|---|---|---|---|---|
| BR-10 | Lương về được ghi vào Tiền vào khác và tạo một **sự kiện lương chờ xác nhận**. Người dùng chọn một chạm: **chia vào hũ** theo tỷ lệ, hoặc **giữ** ở Tiền vào khác | Proposal §10.3; contracts/README | Code | — | FR1 |
| BR-11 | Khi chia lương: mỗi hũ nhận phần làm tròn xuống, phần dư vào hũ có tỷ lệ lớn nhất. Lịch lương của dự báo dùng cùng cách chia | contracts/README | Code | — | FR1, FR3 |
| BR-12 | Lương nhận lệch số đã khai quá ngưỡng thì **hỏi có cập nhật lương không**. Độ lệch = (nhận − khai) / khai × 100 | contracts/README | Code | `salary_deviation_ask_percent` (test dùng 10%, cần đối chiếu SSM) | FR1 |
| BR-13 | **Tiền vào khác lương không phải thu nhập** (bạn trả lại, được cho, thu nhập phụ). Vẫn tính vào tổng số dư; người dùng tự gán vào hũ nếu muốn. Lý do: coi nhầm tiền vay hay tiền trả lại là thu nhập làm kế hoạch lạc quan sai | Proposal §4 | Code | — | FR1, FR3 |

### B4. Giao dịch và phân loại

| ID | Quy tắc | Nguồn | Trạng thái | Tham số | FR |
|---|---|---|---|---|---|
| BR-14 | **Không chặn lúc thanh toán** để hỏi hũ. Người dùng trả trong app và tự chọn hũ nguồn thì bỏ qua phân loại | Proposal §10.3 | Code (tự chọn hũ) | — | FR1, FR2 |
| BR-15 | Chống ghi trùng: gửi lại cùng mã tham chiếu thì không ghi lần hai. Dòng nạp từ tệp luôn có khóa chống trùng. Hai lần chi giống hệt nhau trong ngày mà không gửi mã tham chiếu vẫn hợp lệ | contracts/README | Code | — | FR1, FR9 |
| BR-16 | Thứ tự phân loại khoản chi, **rẻ trước đắt sau**: (0) theo loại giao dịch (bảng tra) → (1) luật của người dùng → (2) giao dịch tương tự đã có nhãn (embedding) → (3) LLM nhỏ | Proposal §10.3 | Code (phase 4): đủ bước 0–3 | — | FR2 |
| BR-17 | Xử lý theo độ tin cậy: **≥ 0,9** tự gán, không báo; **0,6 đến < 0,9** tự gán và đưa vào "Xem lại" (sửa một chạm); **< 0,6** vào Chưa phân loại, **hỏi gộp một lần mỗi ngày**, mỗi khoản kèm 2 gợi ý | Proposal §10.3 (ngưỡng minh họa) | Code (phase 4); ngưỡng là cấu hình. Đo: đúng 92%, **phải hỏi 17,4%** (mục tiêu < 10%) | — | FR2 |
| BR-18 | **Chỉ hỏi khi đáng hỏi**: khoản đủ lớn, hoặc người nhận có khả năng lặp lại. Khoản nhỏ một lần vào hũ "Khác", không hỏi | Proposal §10.3 | Code một phần (phase 4, hỏi gộp `review_asks`); **ngưỡng "đủ lớn": Cần quyết** (C-05) | — | FR2 |
| BR-19 | Người dùng sửa phân loại thì tạo luật, kèm phạm vi **"chỉ lần này"** hoặc **"luôn luôn cho người này"**. Sửa nhiều lần cho cùng một người nhận thì nâng ngưỡng tự gán của riêng người đó | Proposal §10.3 | Code (phase 4, tiêu chí 7 đạt) | — | FR2 |

### B5. Nghĩa vụ và trả sau (mô phỏng)

| ID | Quy tắc | Nguồn | Trạng thái | Tham số | FR |
|---|---|---|---|---|---|
| BR-20 | Nghĩa vụ do người dùng khai gồm: loại (vay, tiền trọ, hóa đơn, thuê bao), số tiền **hoặc khoảng**, phí, chu kỳ (một lần, tuần, tháng), ngày đến hạn, cờ thiết yếu. Khai khoảng thì dùng trung điểm làm tròn xuống | Proposal §4; contracts/README | Code | — | FR4 |
| BR-21 | **Khoản thiết yếu** (ví dụ tiền trọ) không bao giờ bị gợi ý cắt | Proposal §4 | Code (phase 3–4) | — | FR4, FR5, FR8 |
| BR-22 | Mua bằng trả sau **không trừ hũ**. Giao dịch đó sinh mới hoặc cộng dồn vào **một nghĩa vụ trả sau** đến hạn vào **ngày 5 kế tiếp sau ngày mua**; mua đúng ngày 5 thì tính sang tháng sau | contracts/README | Code | `credit_lines.due_day` (mặc định 5) | FR4 |
| BR-23 | Phí dịch vụ **33.000 ₫, tính một lần cho mỗi tháng có giao dịch** bằng hạn mức. Số phải trả = tổng gốc + phí. Phí lấy từ bảng biểu phí có nguồn và ngày hiệu lực | contracts/README; db/seed/fee_schedules.sql | Code | Bảng `fee_schedules` | FR4, FR6 |
| BR-24 | **Không bịa phí khi chưa có nguồn công khai.** Hiện chưa có phí trả chậm trong biểu phí | db/seed/fee_schedules.sql | Code; **Cần quyết** (xem C-04) | — | FR4, FR6 |
| BR-25 | Hạn mức trả sau: dư nợ tính theo gốc, không cộng phí. Mua làm dư nợ vượt hạn mức thì **từ chối** | contracts/README | Code | `default_credit_limit_vnd` | FR4 |
| BR-26 | Trả nghĩa vụ = chi từ một hũ có gắn nghĩa vụ. Khoản một lần chuyển "đã trả"; khoản lặp dời hạn sang kỳ sau; dư nợ trả sau giảm theo gốc | contracts/README | Code | — | FR4 |
| BR-27 | Nhắc nghĩa vụ sắp đến hạn trước **N ngày** | ledger settings | Code | `proactive_obligation_days` (mặc định 3) | FR4, FR13 |

### B6. Dự báo (F1)

| ID | Quy tắc | Nguồn | Trạng thái | Tham số | FR |
|---|---|---|---|---|---|
| BR-28 | Mỗi hũ người dùng có dự báo **30 ngày**: phân vị P10/P50/P90 của số dư theo ngày, **ngày cạn dự kiến**, và xác suất hụt trước kỳ lương (hoặc nhóm tin cậy, xem BR-31). Tính cả lịch lương và lịch nghĩa vụ | Proposal §5 FR3 | Code | `forecast_horizon_days` | FR3 |
| BR-29 | Dưới **21 ngày** lịch sử thì hiện nhãn "**ước lượng ban đầu**", dùng luật và trung bình nhóm tương tự | Phase 2; ml types | Code | `forecast_cold_start_min_days` (21) | FR3 |
| BR-30 | Nhãn độ tin cậy: **Thấp** khi dưới 21 ngày lịch sử hoặc độ phủ dữ liệu dưới 0,4. **Cao** khi từ 60 ngày, độ phủ từ 0,7 và khoảng dự báo đã hiệu chỉnh đạt. Còn lại là **Vừa** | ml quality.py, types.py | Code | `forecast_band_medium_min_days` (21), `forecast_band_high_min_days` (60) | FR3 |
| BR-31 | **Chỉ hiện xác suất hụt dạng %** khi backtest gần nhất đạt độ phủ 0,75–0,85; chưa đạt thì hiện nhóm Cao/Vừa/Thấp | Phase 2 | Code | `forecast_probability_enabled` | FR3 |
| BR-32 | Trạng thái hũ trước kỳ lương: **Hụt** khi xác suất hụt ≥ 0,5; **Sát** khi 0,2 đến < 0,5; **Đủ** khi < 0,2. Ba trạng thái luôn có biểu tượng kèm chữ, không chỉ dùng màu | ml types; phase 2 luồng D | Code | `short_threshold`, `tight_threshold` | FR3 |
| BR-33 | Dự báo tính lại **mỗi đêm lúc 02:00** và **khi có giao dịch** (trong vòng 1 phút). Bản dự báo quá hạn độ tươi thì tính lại trước khi trả lời | Proposal §10.4; phase 2 | Code | `forecast_freshness_seconds` | FR3 |
| BR-34 | "Còn N ngày tới kỳ lương" phải dùng **một cách tính thống nhất** ở thẻ chủ động, chi tiết hũ và chat | HANDOFF (lỗi 12 so với 14 ngày) | **Cần quyết** (xem C-01) | — | FR3 |

### B7. Kiểm tra trước khi chi (F3) và what-if (F2)

| ID | Quy tắc | Nguồn | Trạng thái | Tham số | FR |
|---|---|---|---|---|---|
| BR-35 | Kết quả **đủ / sát / hụt** do **engine tất định** quyết định. LLM chỉ viết hai câu giải thích và phương án; LLM lỗi hoặc chậm quá 2 giây thì chỉ trả thẻ số liệu | Proposal §10.2 | Code (phase 3) | — | FR6 |
| BR-36 | Trả bằng tiền trong hũ: **xanh** là đủ; **vàng** là sát (hũ cạn sớm hơn N ngày); **đỏ** là hụt M đồng trước kỳ lương | Proposal §10.2 | Code (phase 3); **code định nghĩa vàng khác BR-36**: vàng khi số dư kịch bản xấu (P10) xuống dưới `affordability_tight_p10_floor_vnd` (đang = 0), không theo "cạn sớm hơn N ngày"; N: Cần quyết (C-02) | — | FR6 |
| BR-37 | Trả bằng tín dụng: hiện **tổng chi phí thật** = gốc + phí dịch vụ (+ phạt nếu trễ, khi có nguồn), ngày đến hạn, và hũ nào hụt tháng sau. Tỷ lệ nghĩa vụ trên thu nhập vượt ngưỡng thì thẻ đỏ kèm "không khuyến khích" | Proposal §10.2 | Code (phase 3); ngưỡng đang cấu hình chưa đối chiếu với C-03 | — | FR6 |
| BR-38 | Phương án đưa ra: hoãn, đổi hũ, chia nhỏ, trả ngay. Người dùng chọn: vẫn trả, chọn phương án, hoặc bỏ qua. Bỏ qua nhiều lần thì **giảm tần suất nhắc loại đó** | Proposal §10.2 | Code (phase 3) | — | FR6 |
| BR-39 | What-if hỗ trợ ít nhất **6 loại**: mua một lần, mua trả sau, đổi thu nhập, thêm khoản định kỳ, chuyển giữa hũ, lùi mục tiêu | Proposal §5 FR5 | Code (phase 3): golden đủ 6 loại | — | FR5 |
| BR-40 | Thiếu tham số (ví dụ số tiền) thì **hỏi lại đúng một câu**, trả lời xong thì chạy tiếp | Proposal §10.1 | Code (phase 3, tiêu chí 6 đạt) | — | FR5 |
| BR-41 | Mỗi lượt what-if dùng tối đa **4 lượt gọi model** (1 router + 2 planner + 1 diễn giải) | Master-plan §2; agent defaults | Code (trần chung) | `max_model_calls_per_turn` (4) | FR5 |

### B7a. Chi phí trả sau minh bạch (đề xuất 24/11)

Căn cứ và tính toán: [11-can-bang-chi-phi-va-loi-ich.md](11-can-bang-chi-phi-va-loi-ich.md).

| ID | Quy tắc | Nguồn | Trạng thái | Tham số | FR |
|---|---|---|---|---|---|
| BR-74 | Gợi ý **chuyển trả góp** chỉ khi đủ cả năm điều kiện: (1) dự báo nghĩa vụ hụt trước ngày đến hạn; (2) áp cho dư nợ **đã có**, không tăng hạn mức, không mở khoản mới; (3) tổng chi phí trả góp **thấp hơn** chi phí trễ hạn dự kiến; (4) hiện cả hai con số cạnh nhau; (5) người dùng tự chọn qua xác nhận (BR-45). Đây không phải "khuyên vay để tiêu" (BR-42) vì không tạo nợ mới | 11 mục 4 (G3), mục 5 | Đề xuất | `fee_schedules` của sản phẩm trả sau | FR4, FR6 |
| BR-75 | Bản xem trước mua bằng trả sau hiện **chi phí quy năm trên dư nợ bình quân** cạnh tổng phải trả, kèm dòng "để so sánh, không phải lãi suất theo hợp đồng" | 11 mục 2.1 (G1) | Đề xuất | — | FR6 |
| BR-76 | Có từ 2 tài khoản trả sau cùng tính phí cố định thì hiện tổng phí cố định mỗi tháng và mỗi năm. **Không** gợi ý đóng tài khoản cụ thể nào | 11 mục 2.2 (G2) | Đề xuất | — | FR4 |
| BR-77 | **Chuyển sang người hỗ trợ trước hạn**: khi dự báo nghĩa vụ hụt vượt ngưỡng, hoặc đã trễ 2 kỳ liền, Yofina **đề nghị** người dùng được nhân viên đối tác liên hệ. Chỉ chuyển khi người dùng đồng ý, chỉ chia sẻ phần dữ liệu cần cho ca đó (BC-06). Không tự động chuyển, không dùng cho mục đích thu hồi nợ hay bán sản phẩm | 06 mục 4.3d | Đề xuất | Ngưỡng hụt: Cần quyết | FR13 |

### B8. Suitability, xác nhận và giải thích (xuyên suốt)

| ID | Quy tắc | Nguồn | Trạng thái | Tham số | FR |
|---|---|---|---|---|---|
| BR-42 | Thứ tự ưu tiên cố định: (1) **nghĩa vụ trước**; (2) **quỹ dự phòng trước đầu tư** (*đề xuất 24/11:* "quỹ dự phòng" = hũ đệm an toàn `buffer` đã đạt mục tiêu theo BR-64; thứ tự chi tiết ở BR-65, cổng dài hạn ở BR-68); (3) không vượt khẩu vị rủi ro đã khai; (4) **không khuyên vay để tiêu** | Proposal §9 | Code (phase 3). Lỗ hổng hũ Dự phòng (T-01) **đã vá 24/11 khuya** bằng luật `emergency_not_for_discretionary` | — | FR12 |
| BR-43 | Câu hỏi ngoài phạm vi (mã cổ phiếu, vay ở đâu) thì **nói rõ giới hạn** và gợi ý việc làm được. Không nêu mã chứng khoán nào | Proposal §10.1 | Code (phase 3, tiêu chí 5 đạt) | — | FR12 |
| BR-44 | Gợi ý vi phạm luật thì trả về cho agent sửa **tối đa 2 lần**; hết lượt thì chỉ trả thẻ số liệu tất định (what-if) hoặc bỏ hành động vi phạm và giữ phần hợp lệ (lộ trình) | Proposal §10.1, §10.5 | Code (phase 3, Verifier) | — | FR5, FR8, FR12 |
| BR-45 | **Mọi thay đổi số dư cần người dùng bấm xác nhận.** Agent chỉ tạo khối đề nghị. Bấm nút thì server cấp **token dùng một lần**, gắn với người dùng và đúng tham số đã hiển thị. LLM không nằm trên đường ghi | ADR-0002 | Chốt, Code | `confirm_token_ttl_seconds` (2 phút), `confirm_offer_ttl_seconds` | FR12 |
| BR-46 | Đề nghị chưa bấm có hạn. Hết hạn, đã làm hoặc đã hủy thì không áp dụng được; người dùng phải hỏi lại | contracts/README | Code (chưa tách mã `OFFER_EXPIRED`) | `confirm_offer_ttl_seconds` | FR12 |
| BR-47 | Bản **xem trước** do server tính: số dư từng hũ trước và sau, số phải trả kèm phí, hạn mức còn lại. Frontend không tự tính phí hay số dư | contracts/README | Code (chưa có cho sửa hồ sơ, `save_jars`, nghĩa vụ) | — | FR1, FR4, FR12 |
| BR-48 | **Mọi con số đến từ engine hoặc tool**; LLM không tự tính. Số trong câu chữ phải khớp kết quả tool | Proposal §4, §7 | Code (khối UI); kiểm tự động: phase 3 | — | Mọi FR |
| BR-49 | Mỗi gợi ý có bảng **"Vì sao"**: dữ liệu đã dùng, luật đã kiểm, độ tin cậy, `trace_id`. Người dùng chỉ xem được trace của chính mình | Proposal §5 FR11 | Code (phase 3, đi cảnh 2 đạt) | — | FR11 |
| BR-50 | Có thể **hoàn tác** một lần chuyển giữa hũ vừa làm (cũng qua xác nhận) | Phase 3 tiêu chí 2 | Code (phase 3, Hoàn tác đạt trên app) | — | FR12 |

### B9. Điểm chống chịu và lộ trình (F4, F5)

| ID | Quy tắc | Nguồn | Trạng thái | FR |
|---|---|---|---|---|
| BR-51 | Điểm chống chịu từ 0 đến 100, gồm **4 thành phần** có giải thích, tính từ hành vi thật | Proposal §5 FR7 | Code (phase 4): 4 thành phần Tiết kiệm, Chi tiêu, Vay nợ, Kế hoạch; trọng số trong cấu hình engine | FR7 |
| BR-52 | Có **3 cú sốc mẫu**: mất việc 2 tháng, tiền trọ tăng, ốm một tuần. Mỗi cú sốc cho điểm sau sốc và **số ngày trụ được** | Proposal §4, §15 | Code (phase 4): độ lớn cú sốc trong `shocks.json` | FR7 |
| BR-53 | Lộ trình có **phiên bản** và lý do sinh lại. Sinh lại khi lệch dự báo kéo dài (mức mới giữ khoảng **2 tuần**), đổi mục tiêu hoặc thu nhập, hoặc người dùng yêu cầu. **Một khoản lớn đơn lẻ không làm sinh lại lộ trình** | Proposal §10.3, §10.5 | Code (phase 4) | FR8 |
| BR-54 | Mục tiêu không khả thi: nới ràng buộc mềm (lùi hạn, giảm hũ không thiết yếu) **một lần**; vẫn không được thì nói thẳng và đưa **2 lựa chọn** | Proposal §10.5 | Code (phase 4, tiêu chí 4 đạt) | FR8 |
| BR-55 | Người dùng duyệt **từng bước**: chấp nhận, sửa, từ chối. Sửa một bước thì lưu phiên bản mới, không sinh lại toàn bộ. Bước nào đổi số dư thì đi qua BR-45 | Proposal §10.5 | Code (phase 4) | FR8 |

### B10. Nạp dữ liệu, hồ sơ hành vi, nhắc chủ động (F6, F7)

| ID | Quy tắc | Nguồn | Trạng thái | FR |
|---|---|---|---|---|
| BR-56 | Ảnh chụp thông báo và CSV là MVP; sao kê PDF là mở rộng. Ảnh mờ hoặc không phải tài liệu tài chính thì báo lỗi rõ | Proposal §5, §10.6 | Code (phase 5): ảnh và CSV; OCR ảnh thật đủ 4 trường 7/12 | FR9 |
| BR-57 | **Nội dung tệp chỉ là dữ liệu, không phải lệnh.** Dòng độ tin cậy thấp vào hàng chờ người dùng duyệt; không dòng nào tự gọi thao tác ghi | Proposal §10.6, §13 | Code (phase 5, đối kháng 14/14) | FR9 |
| BR-58 | Nạp xong thì cập nhật **điểm độ phủ dữ liệu** và tính lại dự báo | Proposal §10.6 | Code (phase 5) | FR9 |
| BR-59 | Bộ nhớ dài hạn lưu **sở thích, mục tiêu, mẫu hành vi**, không lưu giao dịch thô. Người dùng xem và xóa được | Proposal §7 | Code (phase 5, AgentCore Memory); lỗi gán lời dặn (T-04) đã sửa 24/11 khuya | FR10 |
| BR-60 | Nhắc chủ động **tối đa một lần mỗi ngày**, chỉ khi vượt ngưỡng giá trị. Thẻ chủ động chỉ nêu **một việc**, có "Hỏi vì sao", "Để sau", "Ít nhắc loại này" | Proposal §5 FR13; phase 2 luồng D | Code (phase 5): thẻ và bản tin; **ngưỡng giá trị: Cần quyết** (C-10) | FR13 |

### B11. Tài khoản demo

| ID | Quy tắc | Nguồn | Trạng thái | FR |
|---|---|---|---|---|
| BR-61 | Tắt tự đăng ký. Có sẵn các tài khoản `minh`, `lan`, `khoa`, `giamkhao1`–`3`; mật khẩu sinh ngẫu nhiên, không vào repo | Master-plan §2 | Chốt, Code | — |
| BR-62 | "**Đặt lại dữ liệu**" chỉ xóa dữ liệu của chính người bấm, sinh lại persona, đưa ngày mô phỏng về ngày neo và tính lại dự báo | ADR-0003 | Code | FR1 |

## C. Việc cần chủ dự án quyết

| ID | Câu hỏi | Liên quan | Gợi ý của người tổng hợp |
|---|---|---|---|
| C-01 | "Còn N ngày tới kỳ lương" tính **từ hôm nay** (14 ngày) hay **từ ngày cạn** (12 ngày)? | BR-34; demo cảnh 1 | Tách thành hai câu: "Cạn ngày 23/11, còn 12 ngày nữa mới tới lương (05/12)". Đây là khoảng trống tiền, đúng với kịch bản |
| C-02 | Ngưỡng "sát" cho kiểm tra trước khi chi: hũ cạn sớm bao nhiêu ngày thì vàng? | BR-36 | Vàng khi ngày cạn mới rơi trước kỳ lương nhưng sau ngày cạn cũ; hoặc khi xác suất hụt vào khoảng sát của BR-32 |
| C-03 | Tỷ lệ nghĩa vụ trên thu nhập bao nhiêu thì thẻ đỏ "không khuyến khích"? | BR-37 | **Căn cứ (24/11):** Việt Nam chưa có trần tỷ lệ nợ trên thu nhập cho vay tiêu dùng; Thông tư 43/2016/TT-NHNN chỉ giới hạn khoản vay tối đa 100 triệu ₫ mỗi khách ở công ty tài chính. Singapore (MAS) đặt trần tổng nghĩa vụ trả nợ **55%** thu nhập gộp và **30%** cho khoản vay mua nhà ở xã hội ([MAS](https://www.mas.gov.sg/regulation/explainers/new-housing-loans/msr-and-tdsr-rules)). Đề xuất: **vàng từ 30%, đỏ từ 40%** thu nhập thực nhận. Lý do: ngưỡng MAS tính trên thu nhập gộp và cho người vay mua nhà; người 18–30 có quỹ đệm mỏng nên cần thấp hơn 55%. Cấu hình được |
| C-04 | Có thêm **phí trả chậm** vào biểu phí mô phỏng không? | BR-24, BR-37 | **Đã có nguồn** (cập nhật 24/11): VCCI 28/10/2026 dẫn biểu phí MoMo công bố phí trả chậm 5,25–21% dư nợ quá hạn tùy số ngày chậm, thanh toán tối thiểu 15%, dư nợ chuyển kỳ chịu phí 6,3% ([01, nguồn #20](01-boi-canh-thi-truong.md#9-nguồn)). Đề xuất thêm vào `fee_schedules` kèm nguồn, sau khi đối chiếu bậc phí theo số ngày trên trang biểu phí gốc |
| C-05 | Ngưỡng "đủ lớn để hỏi" khi phân loại chuyển khoản cá nhân | BR-18 | Cấu hình theo tỷ lệ thu nhập, ví dụ từ 2% lương tháng |
| C-06 | Bốn thành phần của Điểm chống chịu, trọng số, và độ lớn ba cú sốc **[24/11: kỹ thuật đã làm ở phase 4 với Tiết kiệm, Chi tiêu, Vay nợ, Kế hoạch; BA chỉ cần duyệt lại]** | BR-51, BR-52 | Có thể lấy cảm hứng từ cấu trúc chi tiêu, tiết kiệm, vay, kế hoạch (không dùng tên FinHealth). Cần chốt trước phase 4 |
| C-07 | Tài khoản không có hũ loại nghĩa vụ (như `lan`) thì mốc trả sau hiện ở đâu? | BR-22, FR4 | Hiện trên dòng thời gian tổng quan; hoặc gợi ý tạo hũ Nghĩa vụ |
| C-08 | Nhãn "do AI tạo" đặt ở đâu và viết thế nào | BC-05 | Dòng nhỏ dưới mỗi câu trả lời của trợ lý, cộng một dòng trong màn Giới thiệu |
| C-09 | Công bố việc model xử lý dữ liệu ngoài Singapore | BC-06 | Một dòng trong màn quyền riêng tư; bản demo chỉ dùng dữ liệu tổng hợp |
| C-10 | Ngưỡng giá trị để gửi nhắc chủ động | BR-60 | Xác định ở phase 5 theo số tiền bị ảnh hưởng hoặc số ngày cạn sớm |
| C-11 | Tỷ lệ mặc định của 3 bộ hũ theo giai đoạn sống (BR-70) | BR-70 | **Cập nhật 24/11:** bộ "Mới đi làm" đã hiệu chỉnh theo Cục Thống kê và giá phòng trọ (bảng căn cứ ở B2a); hai bộ còn lại vẫn minh họa. Nên có căn cứ trước khi đưa lên slide: khảo sát cơ cấu chi tiêu của người trẻ, hoặc dữ liệu persona đã hiệu chỉnh |
| C-12 | Có đổi bộ hũ của tài khoản demo sang cơ cấu mới ngay không? | BR-69, BR-70 | **Đề xuất: chưa đổi trước khi đóng phase 3.** Đổi hũ Hóa đơn sang nghĩa vụ và tách hũ tích lũy làm số dự báo của `minh` thay đổi, phải hiệu chỉnh lại bộ sinh dữ liệu để cảnh 1 vẫn ra "cạn 23/11". Làm cùng phase 4 (Điểm chống chịu, lộ trình) |
| C-13 | Hũ đệm an toàn: mục tiêu mấy tháng chi thiết yếu? | BR-64 | Mặc định 3 tháng; sinh viên có thể là 1 tháng. Cấu hình được. **Căn cứ (24/11):** CFPB nêu mốc phổ biến 3–6 tháng chi tiêu và khuyên bắt đầu bằng mốc nhỏ ([bộ công cụ CFPB](https://files.consumerfinance.gov/f/documents/cfpb_your-money-your-goals_financial-empowerment_toolkit.pdf)); 3 tháng là cận dưới, hợp với người mới đi làm |
| C-14 | Persona chính là sinh viên đi làm thêm hay người mới đi làm? (câu hỏi cũ trong open-questions) | BC-13, BR-70 | Gắn với bộ hũ mặc định. Đề xuất: **mới đi làm (22–26)**, khớp persona Minh 22 tuổi |

## D. Tác động kỹ thuật của mục B2a (cho đội technical)

Chỉ làm sau khi nhóm chốt C-11, C-12. Thứ tự đề xuất:

| Bước | Việc | Chỗ sửa | Rủi ro |
|---|---|---|---|
| 1 | Thêm cột `purpose` cho hũ (chỉ hũ `saving`, ràng buộc CHECK) và `is_essential` cho hũ chi theo kỳ | Migration mới; `contracts/` (schema hũ, OpenAPI, Zod sinh lại) | Thấp: cột tùy chọn, dữ liệu cũ hợp lệ |
| 2 | Thêm 3 bộ hũ mẫu và cột `life_stage` cho bảng mẫu; `GET /jar-templates?life_stage=` | `db/seed/jar_templates.sql`, ledger REST, màn onboarding O2 | Thấp |
| 3 | Bảng khoản của hũ quỹ dồn (tên, số tiền, ngày cần), hiện thành mốc trên dự báo | Migration, ledger, `pipelines/forecast` (giống nghĩa vụ) | Vừa |
| 4 | Dự báo theo loại hũ (BR-73); loại hũ đệm và dài hạn khỏi "tiền có thể chi" | `ml/yofina_ml`, `pipelines/forecast`, kiểm tra trước khi quẹt | Vừa: đổi số dự báo |
| 5 | Đổi hũ Hóa đơn sang nghĩa vụ; hiệu chỉnh lại persona | Bộ sinh persona, `jar_templates` | **Cao với demo**: cảnh 1 phải ra lại đúng số |
| 6 | Luật ưu tiên (BR-65), cổng mở hũ dài hạn (BR-68), gợi ý chuyển giai đoạn (BR-71) | Lộ trình, suitability (phase 3–4) | Gắn với phase 4 |
