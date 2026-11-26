# Tóm tắt proposal — Yofina Foresight

> Bản chắt từ [Proposal-Yofina-Foresight.pdf](Proposal-Yofina-Foresight.pdf) (33 trang, bản nháp ngày 20/11/2026, "cập nhật: đầu vào khai báo, phân hũ tự động"). Đủ để làm việc hằng ngày mà không phải mở PDF. Số trong ngoặc `§n` là số mục trong proposal để tra ngược. Chỗ proposal ghi "cần xác nhận / chưa chốt" được giữ nguyên tính chất đó. Khi bản tóm tắt và PDF lệch nhau thì PDF đúng.

## 1. Sản phẩm (§1)

- **Yofina Foresight** (tên tạm) — trợ lý tài chính "Hũ nhìn trước" cho **MoMo Tech Contest 2026**. Dự báo từng hũ chi tiêu sẽ cạn vào ngày nào, tính cả nợ nhỏ (Ví Trả Sau, vay, hóa đơn định kỳ), và tự đổi lộ trình khi hành vi người dùng lệch khỏi dự báo.
- Chủ đề cuộc thi: Trợ lý AI (tài chính và cá nhân). Chống lừa đảo chỉ ở mức phụ: cảnh báo khoản chuyển lệch khỏi thói quen.
- Khác biệt: nhìn tới tương lai thay vì nhìn lại; nợ nhỏ nằm trong kế hoạch; mọi lời khuyên có lý do và qua kiểm tra phù hợp.
- Vai trò của AI: hiểu hành vi, dự báo, mô phỏng "nếu thì", chấm điểm chống chịu, lập và sửa lộ trình, đọc sao kê.
- Người dùng chính: người trẻ 18–30 tuổi nhận lương/trợ cấp theo tháng, có dùng mua trước trả sau.
- Persona demo: **Minh**, 22 tuổi, thu nhập 9 triệu/tháng, lương về ngày 5, 7 hũ, một hạn mức Ví Trả Sau. Persona phụ (không thuộc MVP): thu nhập không đều (freelancer, tài xế công nghệ, người bán online) — xem §4.
- Nền tảng: Strands Agents chạy trên Amazon Bedrock AgentCore, toàn bộ trên AWS.
- **Giả định scope cần đội xác nhận**: web app chạy tốt trên điện thoại (không làm app native); không có API lấy giao dịch thật của MoMo nên dùng ví mô phỏng và dữ liệu tự nạp; lương, chi phí cố định, khoản vay do người dùng tự khai báo, hệ thống không tự đoán; không khuyến nghị mã cổ phiếu hay quỹ cụ thể (chỉ nói điều kiện tiên quyết và tỷ lệ theo nhóm); agent không tự chuyển tiền, mọi thay đổi số dư hũ cần người dùng xác nhận; tài liệu viết tiếng Việt, thuật ngữ kỹ thuật giữ tiếng Anh.

## 2. Vấn đề và số liệu (§2)

Người dùng ví đã có công cụ xem mình đã tiêu gì nhưng chưa biết mình sắp thiếu khi nào; khoảng trống lớn nhất là nợ nhỏ và phí nằm ngoài ngân sách. Số liệu (kèm nguồn gốc, xem [links.md](../references/links.md)):

| Vấn đề | Số liệu |
|---|---|
| Muốn quản lý chi tiêu nhưng không duy trì | Hơn 90% muốn quản lý, chỉ 8% làm có hệ thống (MoMo 14/10/2026, số nội bộ, không công bố phương pháp) |
| Nhu cầu đủ lớn | Hơn 3 triệu người dùng tính năng Quản Lý Chi Tiêu mỗi tháng, trên nền hơn 30 triệu người (CafeF 05/11/2026) |
| Công cụ hiện chỉ nhìn lại | Phân loại, ngân sách, cảnh báo vượt mức, báo cáo tuần/tháng; không có dự báo, mô phỏng, lộ trình theo mục tiêu |
| Nợ nhỏ phổ biến | 64,3% người 18–35 tuổi được khảo sát đã dùng mua trước trả sau trong 12 tháng; Ví Trả Sau có khoảng 2 triệu người dùng |
| Thiếu nền tảng hiểu biết | Trong 275 Gen Z đã dùng mua trước trả sau, 54,5% là sinh viên và 68,4% chưa từng học quản lý tài chính cá nhân |
| Phí gây bất ngờ | Phí dịch vụ Ví Trả Sau 33.000đ/tháng có giao dịch |
| Áp lực chi phí | 62% người Việt lo chi phí sinh hoạt tăng (UOB ACSS 2026) |
| Chỉ số sức khỏe tài chính | Chương trình của MoMo là danh sách nhiệm vụ cố định, không mô phỏng biến cố cá nhân hóa |

Điểm khác với MoMo: hũ của MoMo gắn danh mục cho giao dịch sau khi tiêu; công cụ Phân Bổ Lương gợi ý tỷ lệ chia 6 hũ nhưng không tách tiền thật (tiền vẫn một khối). Hũ trong đề xuất này có số dư riêng, chuyển qua lại và dự báo được. Phân loại giao dịch của MoMo vẫn còn phần làm tay; độ chính xác không công bố (cần kiểm tra lại trong app, xem [open-questions](../requirements/open-questions.md)).

## 3. Stakeholders (§3)

| Stakeholder | Vai trò | Họ cần gì |
|---|---|---|
| Người dùng cuối 18–30 tuổi có dùng trả sau | Người dùng chính | Biết trước lúc thiếu tiền, không bị phí bất ngờ, không phải nhập tay |
| Đội sản phẩm quản lý tài chính của ví | Chủ sản phẩm | Tăng tỷ lệ dùng lại, biến 3 triệu người xem báo cáo thành người có kế hoạch |
| Đội tín dụng và đối tác cho vay | Hưởng lợi gián tiếp | Giảm trễ hạn, giảm khiếu nại về phí (lợi ích là giả thuyết, cần pilot) |
| Đội rủi ro và tuân thủ | Giám sát | Xem lại vì sao AI khuyên như vậy (trace, luật suitability) |
| Đội chăm sóc khách hàng | Hưởng lợi gián tiếp | Ít ticket về khoản trừ không rõ (bảng "Vì sao") |
| Cơ quan quản lý | Ràng buộc | Con người giữ quyền kiểm soát, dữ liệu cá nhân được bảo vệ, nội dung AI gắn nhãn |

## 4. Giải pháp và 7 tính năng (§4)

Ghép ba thứ đang rời nhau: hũ chi tiêu, nghĩa vụ tín dụng và dự báo. **AI không tự tính số**: mọi con số đến từ engine tất định hoặc mô hình dự báo; LLM lo hiểu câu hỏi, lập kế hoạch, giải thích.

| # | Tính năng | Người dùng thấy gì | AI làm gì | Chạy khi nào |
|---|---|---|---|---|
| F1 | Dự báo dòng tiền theo hũ | Dòng thời gian 30 ngày, ngày cạn kiến, xác suất hụt trước kỳ lương | Mô hình chuỗi thời gian xác suất + lịch lương + nghĩa vụ, mô phỏng Monte Carlo số dư | Batch mỗi đêm; cập nhật khi có giao dịch mới |
| F2 | Hỏi "nếu thì" | Gõ câu hỏi, biểu đồ dịch chuyển, so sánh trước/sau | Agent dịch câu hỏi thành đặc tả kịch bản có cấu trúc, engine mô phỏng, agent giải thích | Runtime, streaming |
| F3 | Kiểm tra trước khi quẹt | Thẻ kết quả đủ/sát/hụt, tổng chi phí thật gồm phí, phương án khác | Engine tất định quyết định, LLM nhỏ chỉ diễn giải | Runtime, mục tiêu dưới 2 giây |
| F4 | Điểm chống chịu và cú sốc | Điểm 0–100 với 4 thành phần; nút "mất việc 2 tháng", "tiền trọ tăng", "ốm một tuần" | Chỉ số tính từ hành vi thật, stress test trên dự báo | Batch tính điểm, runtime chạy kịch bản |
| F5 | Lộ trình thích ứng | Lộ trình theo giai đoạn, mỗi bước có lý do; phiên bản mới khi hành vi đổi | Roadmap agent, bộ tối ưu phân bổ hũ, cổng suitability | Theo sự kiện (lệch dự báo, đổi mục tiêu) và theo yêu cầu |
| F6 | Nạp dữ liệu ngoài ví | Tải sao kê hoặc ảnh, xác nhận dòng chưa chắc, thấy điểm độ phủ dữ liệu tăng | Trích xuất tài liệu đa phương thức, phân loại 3 bước, khử trùng | Job bất đồng bộ có tiến độ |
| F7 | Hồ sơ hành vi và bản tin chủ động | Nhận xét về thói quen chi tiêu và một việc cần làm tiếp theo | Khám phá mẫu hành vi, bộ nhớ dài hạn, cổng giá trị trước khi nhắc | Batch và theo sự kiện |

Xuyên suốt cả bảy: lớp **suitability + bảng "Vì sao"** (gợi ý kèm dữ liệu đã dùng, luật đã kiểm, phương án thay thế).

Ví dụ AI tư vấn theo hũ (số minh họa): Hũ Ăn uống (46% ngân sách tháng tiêu trong 10 ngày đầu kỳ lương → đổi trần tháng thành trần tuần); Hũ Du lịch (mục tiêu 6 triệu trước tháng 4, đang trễ 5 tuần → lùi ngày đi hoặc chuyển 150 nghìn/tuần từ hũ Giải trí); Hũ Nghĩa vụ (Ví Trả Sau đến hạn ngày 5 trùng lương, giữ sẵn); Hũ Dự phòng (điểm chống chịu thấp, chỉ sống 9 ngày nếu mất thu nhập → ưu tiên hũ này trước mọi gợi ý đầu tư).

> **Ghi chú lệch (thêm 26/11, không thuộc proposal):** proposal kể Minh với 7 hũ và các hũ theo loại chi ở trên. Sản phẩm dùng **bộ hũ mặc định theo mục đích thay bộ 7 hũ theo loại chi**: tài khoản mới nhận 3 hũ Chi hằng ngày, Nghĩa vụ (chung cho tiền nhà, hóa đơn, vay, Trả sau), Dự phòng; hũ khác do người dùng tự thêm. Ví demo của Minh có 8 hũ: 3 hũ đó (Hóa đơn gộp vào Nghĩa vụ) cộng hũ tự thêm Ăn uống, Đi lại, Giải trí, Du lịch (hũ mục tiêu), Đầu tư; Trả sau của Minh đến hạn ngày 3 (điều khoản mô phỏng). Vì sao: bộ 7 hũ để hóa đơn ở loại chi tiêu và để Du lịch cùng loại với Dự phòng, nên luật và dự báo không tách được tiền để tiêu, tiền phải trả, tiền không được đụng. Chi tiết: [ADR-0004](../decisions/0004-lech-so-voi-proposal.md) dòng 29.

### Đầu vào: người dùng tự khai báo (§4)

Hackathon không tự đoán thu nhập hay chi phí cố định. Khai một lần lúc bắt đầu, sửa được bất cứ lúc nào, trên màn hình hoặc bằng chat ("tiền trọ 2,5 triệu, đóng ngày 1"). **Chỉ lương và ngày nhận là bắt buộc**; phần còn lại khai dần, dự báo ghi rõ dựa trên số đã khai.

| Đầu vào | Người dùng khai | Dùng làm gì |
|---|---|---|
| Lương (bắt buộc) | Số tiền thực nhận, ngày nhận | Mốc tiền vào trong dự báo; khi lương về người dùng xác nhận một chạm, lương được chia vào hũ theo luật |
| Hũ và luật chia | Danh sách hũ, tỷ lệ hoặc số tiền cho mỗi hũ | Chia lương, tính số dư từng hũ |
| Chi phí cố định | Tiền trọ, hóa đơn, gói thuê bao: số tiền hoặc khoảng, ngày đến hạn, chu kỳ | Lịch tiền ra biết trước; khoản thiết yếu như tiền trọ không bị gợi ý cắt |
| Khoản vay | Gốc, phí hoặc lãi, lịch trả | Lịch nghĩa vụ, tỷ lệ nghĩa vụ trên thu nhập |
| Mục tiêu | Số tiền, hạn, hũ gắn với mục tiêu | Lộ trình, tiến độ |
| Mức chấp nhận rủi ro | Chọn một trong ba mức | Luật suitability |

- Khoản trả sau không cần khai: tự sinh khi người dùng mua bằng hạn mức trong ví mô phỏng. Chi tiêu hằng ngày vẫn được ghi và phân hũ tự động (xem §10.3).
- **Tiền vào khác lương** (bạn trả lại tiền, được cho, thu nhập phụ) **không tính là thu nhập**: nằm ở ô "Tiền vào khác", vẫn tính vào tổng số dư nhưng chưa thuộc hũ nào; người dùng tự gán vào hũ nếu muốn. Lý do: coi nhầm tiền vay hay tiền trả lại là thu nhập làm kế hoạch lạc quan sai.

### Ngoài phạm vi MVP (§4) — thiết kế nhưng không làm trong bản hackathon

| Hướng mở rộng | Cách làm dự kiến | Vì sao để sau |
|---|---|---|
| Tự phát hiện khoản định kỳ | Gom giao dịch theo đối tác, xét khoảng cách giữa các lần (trung vị gần 7, 14 hay 30 ngày, ít dao động) và độ ổn định số tiền, cần ít nhất 3 lần; gắn nhãn theo loại giao dịch; khoản cá nhân lặp lại chỉ là gợi ý, người dùng xác nhận mới thành nghĩa vụ. Kế thừa từ Swinburne | Cần 2–3 tháng lịch sử mới có tác dụng; khai báo thay được trong demo |
| Nhận diện loại tiền vào | Theo thứ tự: loại giao dịch (nạp từ ngân hàng liên kết, giải ngân, hoàn tiền), người gửi là chính người dùng, luật theo người gửi, khoản định kỳ, ghép cặp với khoản chi trước đó, LLM, rồi hỏi | Nhiều ca biên, tốn thời gian, không hiện rõ trong demo |
| Thu nhập không đều | Dự báo thu nhập bằng mô hình chuỗi gián đoạn; kế hoạch chỉ tính mức thận trọng P10 cho tới khi tiền về; Monte Carlo cả phía thu | Cần nhận diện tiền vào trước |
| Lương về ngân hàng thay vì ví | Lấy từ sao kê ngân hàng (F6) hoặc kết nối ngân hàng nếu có API được phép dùng | Ví mô phỏng nhận lương trực tiếp |

## 5. Yêu cầu chức năng (FR) và phi chức năng (NFR) (§5)

MVP gồm 12 FR; 3 FR còn lại (FR13–15) là mở rộng nếu còn thời gian. FR9 chỉ MVP một phần.

| ID | Yêu cầu | Tiêu chí chấp nhận | Mức |
|---|---|---|---|
| FR1 | Hồ sơ, hũ và sổ cái | Khai báo lương và ngày nhận. Tạo, sửa hũ. Chia lương vào hũ theo luật khi người dùng xác nhận lương đã về. Ghi giao dịch trên ví mô phỏng. Tiền vào khác lương nằm ở ô riêng để người dùng tự gán | MVP |
| FR2 | Phân hũ tự động | Không hỏi lúc thanh toán. Phân loại theo loại giao dịch, luật của người dùng, embedding, rồi LLM. Ba mức độ tin cậy: tự gán, xem lại, hỏi gộp. Sửa một lần thì lần sau tự đúng | MVP |
| FR3 | Dự báo theo hũ | Phân vị P10, P50, P90 cho 30 ngày. Ngày cạn dự kiến. Xác suất hụt trước kỳ lương | MVP |
| FR4 | Quản lý nghĩa vụ | Người dùng khai khoản vay, tiền trọ, hóa đơn, gói thuê bao với số tiền, ngày đến hạn. Trả sau tự sinh từ ví mô phỏng | MVP |
| FR5 | What-if hội thoại | Ít nhất 6 loại kịch bản: mua một lần, mua trả sau, đổi thu nhập, thêm khoản định kỳ, chuyển giữa hũ, lùi mục tiêu | MVP |
| FR6 | Kiểm tra trước khi quẹt | Trả kết quả đủ, sát, hụt. Với tín dụng: tổng chi phí gồm phí và khoản hụt tháng sau | MVP |
| FR7 | Điểm chống chịu | Điểm 0–100, 4 thành phần có giải thích, 3 cú sốc mẫu | MVP |
| FR8 | Lộ trình thích ứng | Sinh, giải thích, lưu phiên bản. Người dùng chấp nhận hoặc sửa từng bước | MVP |
| FR9 | Nạp dữ liệu ngoài ví | Ảnh chụp thông báo và CSV ở MVP. Sao kê PDF ngân hàng là phần mở rộng | MVP một phần |
| FR10 | Hồ sơ hành vi và bộ nhớ | Lưu sở thích, mục tiêu, mẫu chi tiêu. Dùng lại ở phiên sau mà không hỏi lại | MVP |
| FR11 | Bảng "Vì sao" | Mỗi gợi ý có dữ liệu đã dùng, luật đã kiểm, độ tin cậy, trace_id | MVP |
| FR12 | Suitability và xác nhận | Luật chặn gợi ý không phù hợp. Mọi thay đổi số dư cần người dùng bấm xác nhận | MVP |
| FR13 | Bản tin chủ động | Tối đa một nhắc mỗi ngày, chỉ khi vượt ngưỡng giá trị | Mở rộng |
| FR14 | Cảnh báo khoản chuyển lệch thói quen | So với mẫu chi cá nhân và ảnh hưởng đến hũ Dự phòng | Mở rộng |
| FR15 | Bảng vận hành cho đội sản phẩm | Xem trace, điểm đánh giá, số lần luật chặn | Mở rộng |

**NFR** (mục tiêu đội tự đặt, sẽ đo bằng load test và backtest):

| Nhóm | Mục tiêu |
|---|---|
| Độ trễ | Ký tự đầu tiên dưới 1,5 giây. Kiểm tra trước khi quẹt p95 dưới 2 giây. What-if trọn câu p95 dưới 8 giây |
| Độ đúng của số | 100% con số trong câu trả lời khớp với kết quả tool. LLM không tự làm phép tính |
| Chất lượng dự báo | Tốt hơn seasonal naive trên pinball loss. Khoảng 80% phủ từ 75% đến 85% trên backtest |
| Phân loại | Đúng từ 90% trở lên trên bộ kiểm thử persona. Dưới 10% giao dịch phải hỏi người dùng |
| Độ tin cậy | LLM lỗi thì vẫn trả thẻ số liệu tất định. Sự kiện xử lý idempotent, có hàng đợi lỗi |
| Bảo mật | Đăng nhập bằng JWT. Dữ liệu tách theo người dùng. Tool call mặc định bị từ chối trừ khi có luật cho phép. Mã hóa khi lưu và khi truyền |
| Quyền riêng tư | Che thông tin định danh trước khi vào LLM. Thu thập tối thiểu. Xóa theo yêu cầu |
| Giải thích và kiểm toán | 100% lượt hội thoại có trace. Mọi gợi ý truy được về dữ liệu và luật |
| Chi phí | Đặt ngân sách và cảnh báo chi phí. Model nhỏ cho việc nhỏ, prompt caching cho phần lặp |
| Ngôn ngữ và thiết bị | Tiếng Việt. Ưu tiên màn hình điện thoại |

## 6. Lợi ích và KPI (§6)

Các KPI là giả thuyết; phần đo được trong cuộc thi dùng dữ liệu mô phỏng, phần còn lại cần pilot thật.

| Bên hưởng lợi | KPI | Đo trong cuộc thi | Đo khi pilot |
|---|---|---|---|
| Người dùng — biết trước lúc thiếu tiền | Số ngày cảnh báo trước khi hũ cạn; tỷ lệ cảnh báo đúng | Backtest trên 3 persona | So với thực tế sau 30 ngày |
| Người dùng — không bị phí bất ngờ | Số lần trễ hạn và phí phát sinh mỗi người mỗi tháng | Mô phỏng có và không có trợ lý | So với nhóm đối chứng |
| Người dùng — lời khuyên dùng được | Tỷ lệ gợi ý được chấp nhận; điểm hữu ích của lời giải thích | Bộ câu hỏi chuẩn và chấm bằng LLM judge | Nút chấp nhận/từ chối trong app |
| Đội sản phẩm — người dùng quay lại | Tỷ lệ còn dùng sau 30 ngày; số phiên mỗi tuần | Không đo được | Theo dõi cohort |
| Đội rủi ro — kiểm tra được | 100% gợi ý có trace; số gợi ý vi phạm luật lọt ra bằng 0 | Bộ test đối kháng 50 câu | Lấy mẫu đánh giá online |
| Đối tác cho vay — người vay trả đúng hạn hơn | Tỷ lệ trả đúng hạn | Mô phỏng | Cần dữ liệu đối tác |
| Đội vận hành — AI rẻ và nhanh | Chi phí mỗi lượt hội thoại; độ trễ p95 | Đo trực tiếp từ trace | Đo trực tiếp từ trace |

## 7. Data strategy (§7)

Cơ sở dữ liệu quan hệ là **nguồn sự thật duy nhất** cho mọi con số. LLM chỉ đọc số qua tool có tham số, không viết SQL tự do và không tự tính.

**Nguồn dữ liệu**: khai báo của người dùng (lương, ngày nhận, chi phí cố định, khoản vay, mục tiêu, mức chấp nhận rủi ro) · ví mô phỏng trong app (sổ cái, số dư hũ, nghĩa vụ; người dùng và giám khảo tạo giao dịch, trả bằng hũ hoặc hạn mức trả sau) · dữ liệu tổng hợp theo persona (bộ sinh dữ liệu: lương theo kỳ, hóa đơn định kỳ, chi tiêu theo nhịp lương và tuần, khoản trả sau, cú sốc, và một điểm gãy lối sống cài sẵn, ví dụ chuyển trọ; mỗi persona kèm hồ sơ khai báo) · dữ liệu người dùng tự nạp (ảnh thông báo, CSV, sao kê PDF) · kho tri thức (biểu phí và điều khoản công khai, kiến thức tài chính cá nhân, bộ luật suitability) · phản hồi người dùng (sửa phân loại, chấp nhận/từ chối gợi ý, sửa lộ trình) · telemetry của agent (trace OpenTelemetry mỗi lượt).

**Mô hình dữ liệu chính** (chi tiết hơn ở [overview.md](../architecture/overview.md#mô-hình-dữ-liệu)):

| Bảng | Nội dung |
|---|---|
| `users`, `jars` | Người dùng, lương và ngày nhận đã khai, mức chấp nhận rủi ro, hũ, luật chia lương, mục tiêu và hạn của hũ |
| `transactions` | Giao dịch đã chuẩn hóa: thời gian, số tiền, đối tác, hũ, nguồn, độ tin cậy phân loại |
| `category_rules` | Luật phân loại học từ lần người dùng sửa, kèm phạm vi: một lần hay luôn luôn cho người nhận đó |
| `obligations` | Mọi khoản tiền ra theo lịch: trả sau (tự sinh), khoản vay, tiền trọ, hóa đơn, gói thuê bao (người dùng khai). Số tiền hoặc khoảng, phí, ngày đến hạn, chu kỳ, trạng thái |
| `forecasts` | Phân vị theo hũ và ngày, tên mô hình, mã lần chạy |
| `resilience_scores` | Điểm và 4 thành phần theo ngày |
| `roadmaps` | Lộ trình dạng JSON có phiên bản và lý do sinh lại |
| `scenarios`, `nudges`, `feedback` | Kịch bản đã chạy, nhắc đã gửi, phản hồi |
| `audit_events` | Mỗi gợi ý: trace_id, dữ liệu đã dùng, luật đã kiểm, kết quả |

**Cổng chất lượng**:
- *Khởi đầu lạnh*: dưới 30 ngày dữ liệu → dùng luật và trung bình của nhóm tương tự; 30–90 ngày → mô hình thống kê; trên 90 ngày mới bật mô hình nền tảng.
- *Điểm độ phủ*: phần thu nhập giải thích được bằng chi tiêu đã ghi và số dư. Độ phủ thấp thì câu trả lời nói rõ dự báo kèm tin cậy và mời nạp thêm.
- *Khử trùng*: khóa băm từ ngày, số tiền và đối tác, kèm cửa sổ sai lệch thời gian.
- *Độ tươi*: mỗi bản ghi dự báo có dấu thời gian; quá hạn thì tính lại trước khi trả lời.
- *Thiếu dữ liệu thì hỏi lại*: điểm tin cậy dưới ngưỡng thì agent hỏi thêm thay vì đoán.

**Quyền riêng tư**: xin đồng ý riêng cho từng nguồn nạp; người dùng xem và xóa được dữ liệu và bộ nhớ của mình; che số tài khoản, số điện thoại, tên người nhận trước khi đưa vào LLM và trước khi ghi bộ nhớ; bộ nhớ dài hạn lưu sở thích và mẫu hành vi, không lưu giao dịch thô; bản demo chỉ dùng dữ liệu tổng hợp. Khi chạy thật, việc đặt hạ tầng ở Region ngoài Việt Nam cần đánh giá theo Luật Bảo vệ dữ liệu cá nhân (chưa xác minh chi tiết).

## 8. Kiến trúc AWS và ba nhịp chạy (§8)

Hệ thống chạy theo ba nhịp: **runtime** (người dùng đang chờ), **event** (có giao dịch mới), **batch** (phân tích định kỳ). Runtime không chạy mô hình nặng: nó đọc dự báo đã tính sẵn và chỉ chạy mô phỏng nhẹ. Hình 1 (trang 9) là sơ đồ kiến trúc.

| Tầng | Dịch vụ | Vai trò |
|---|---|---|
| Giao diện | Amplify Hosting, CloudFront, WAF | Web app React ưu tiên điện thoại, nhận sự kiện streaming |
| Định danh | Cognito, AgentCore Identity | JWT của người dùng được Runtime kiểm tra trước khi code agent chạy, rồi truyền xuống tool |
| Agent | AgentCore Runtime chạy Strands Agents | Mỗi phiên một microVM riêng. Streaming, job nền tới 8 giờ, giao thức AG-UI ra frontend |
| Bộ nhớ | AgentCore Memory | Ngắn hạn theo phiên, dài hạn theo người dùng |
| Cổng tool | AgentCore Gateway và Policy | Biến Lambda thành tool MCP. Luật Cedar kiểm từng tool call, mặc định từ chối |
| Mô hình | Amazon Bedrock, Guardrails, Knowledge Bases | LLM lớn cho lập kế hoạch, LLM nhỏ cho định tuyến và diễn giải, embedding, RAG, lọc vào ra |
| Tool | Lambda | Sổ cái, dự báo và mô phỏng, tối ưu lộ trình, nạp dữ liệu |
| Dữ liệu | Aurora PostgreSQL Serverless v2, S3 | Sổ cái và kết quả phân tích. Tệp nạp, artifact mô hình, log kiểm toán |
| ML | SageMaker, Lambda container | Mô hình nền tảng chuỗi thời gian. Mô hình thống kê nhẹ |
| Sự kiện và batch | EventBridge, SQS, Step Functions | Bus sự kiện giao dịch, lịch chạy đêm, hàng đợi nạp tệp, điều phối pipeline |
| Tài liệu | Bedrock Data Automation | Trích bảng từ sao kê PDF theo blueprint |
| Quan sát và quản trị | AgentCore Observability và Evaluations, CloudWatch, CloudTrail, KMS | Trace từng bước, chấm điểm chất lượng, cảnh báo, mã hóa |

**Cái gì chạy lúc nào**:

| Nhịp | Kích hoạt | Việc làm | Độ trễ mục tiêu |
|---|---|---|---|
| Runtime đồng bộ | Người dùng chat, bấm kiểm tra, bấm cú sốc | Định tuyến, gọi tool, mô phỏng nhẹ, kiểm tra, stream câu trả lời | Vài giây |
| Runtime bất đồng bộ | Sinh lại lộ trình, nạp sao kê | Agent chạy nền, giao diện nhận tiến độ từng bước | Chục giây đến vài phút |
| Event | Giao dịch mới, sửa phân loại, đổi mục tiêu | Phân loại, cập nhật số dư hũ, chỉnh nhanh dự báo, kiểm tra lệch, cổng nhắc | Dưới 1 phút |
| Batch đêm | Lịch 02:00 mỗi ngày | Dự báo lại, hồ sơ hành vi, điểm chống chịu, bản tin | Xong trước 06:00 |
| Batch tuần | Chủ nhật | Backtest, hiệu chỉnh khoảng tin cậy, đánh giá agent trên bộ câu hỏi chuẩn, đồng bộ kho tri thức | Không ràng buộc |

Để kịp 3 tuần, đội có thể khởi đầu từ **FAST** (Fullstack AgentCore Solution Template, khung mẫu của AWS đã nối sẵn Runtime, Gateway, Identity, Memory, frontend React và Cognito bằng CDK, có mẫu Strands với AG-UI) — xem blog AG-UI ở [links.md](../references/links.md) và đối chiếu layout ở [project-structure.md](../architecture/project-structure.md).

## 9. Agentic harness (§9)

Mỗi lượt đi qua **sáu tầng**; LLM chỉ làm ba việc: hiểu ý định, lập kế hoạch và diễn giải. Tính toán, kiểm tra luật và ghi dữ liệu nằm ở tool tất định. Hình 2 (trang 10) là sơ đồ.

| Tầng | Việc | Kỹ thuật | Thành phần |
|---|---|---|---|
| L0 Cổng vào | Xác thực, chặn prompt injection, che thông tin định danh | Input guardrail | JWT authorizer của Runtime, Bedrock Guardrails |
| L1 Intent Router | Phân loại ý định, rút tham số, chọn đường nhanh hay đầy đủ | Routing, structured output | LLM nhỏ, schema Pydantic của Strands |
| L2 Orchestrator | Lập kế hoạch các bước, gọi specialist và tool song song, giữ ngân sách lượt | Orchestrator-workers, plan rồi execute | LLM lớn, mẫu agents-as-tools của Strands |
| L3 Specialist | Phân tích, mô phỏng, lập lộ trình, đọc tài liệu; mỗi agent có ngữ cảnh riêng | Cô lập ngữ cảnh | 4 Strands Agent |
| L4 Verifier | Đối chiếu số với kết quả tool, chạy luật suitability, trả lỗi có cấu trúc để sửa | Evaluator-optimizer, tối đa 2 vòng | Luật Python, Automated Reasoning checks |
| L5 Composer | Ghép văn bản và khối giao diện, gắn nhãn AI và trace_id | Structured output, sự kiện AG-UI | LLM nhỏ |

Với luồng có thứ tự cố định (như kiểm tra trước khi quẹt), đội dùng **Graph của Strands** thay vì để orchestrator tự quyết.

| Agent | Model | Tool được dùng | Đầu ra có cấu trúc |
|---|---|---|---|
| Intent Router | LLM nhỏ | Chỉ đọc bộ nhớ | `IntentResult`: intent, tham số, độ tin cậy, có cần hỏi lại không |
| Orchestrator | LLM lớn | Các specialist dưới dạng tool | `Plan`: danh sách bước, bước nào chạy song song |
| Analyst Agent | LLM lớn | `ledger.*`, `forecast.get_*` | `Analysis`: phát hiện, bằng chứng, phương án |
| Simulation Agent | LLM nhỏ | `forecast.run_scenario`, `stress_test`, `affordability_check` | `ScenarioSpec` và `ScenarioResult` |
| Roadmap Agent | LLM lớn | `planner.*` | `Roadmap`: giai đoạn, hành động, lý do |
| Ingestion Agent | LLM đa phương thức | `ingest.*` | Danh sách giao dịch trích được kèm độ tin cậy |
| Verifier | Luật và LLM nhỏ | `planner.check_suitability` | `Verdict`: đạt hay không, danh sách vi phạm |

### Tool và MCP

Mọi tool là Lambda đăng ký làm target của AgentCore Gateway, nên agent thấy chúng như một MCP server duy nhất. Tool đọc mở cho mọi người dùng đã đăng nhập. Tool ghi chỉ được luật Cedar cho qua khi tham số mang cờ xác nhận của người dùng.

| Tool | Chức năng | Phía sau | Ghi dữ liệu |
|---|---|---|---|
| `ledger.get_jar_balances` | Số dư và hạn mức từng hũ | SQL có tham số | Không |
| `ledger.query_transactions` | Lọc giao dịch theo hũ, thời gian, đối tác | SQL có tham số | Không |
| `ledger.get_cashflow_summary` | Tổng thu chi theo kỳ và theo hũ | SQL view | Không |
| `ledger.get_obligations` | Nghĩa vụ và chi phí cố định đã khai: số tiền, phí, ngày đến hạn | SQL | Không |
| `ledger.update_profile` | Sửa lương, ngày nhận, chi phí cố định, khoản vay đã khai | SQL | Có, cần xác nhận |
| `ledger.record_transaction` | Ghi giao dịch trên ví mô phỏng | SQL | Có, cần xác nhận |
| `ledger.move_between_jars` | Chuyển tiền giữa hai hũ | SQL | Có, cần xác nhận |
| `ledger.get_unclassified` | Giao dịch đang ở hũ tạm hoặc danh sách xem lại, kèm 2 hũ gợi ý | SQL | Không |
| `ledger.assign_jar` | Gán hoặc sửa hũ của giao dịch, lưu luật theo phạm vi người dùng chọn | SQL | Có, cần xác nhận |
| `forecast.get_forecast` | Phân vị dự báo đã tính sẵn của một hũ | Đọc bảng | Không |
| `forecast.run_scenario` | Chạy `ScenarioSpec`, trả chênh lệch, ngày cạn, xác suất hụt | Monte Carlo | Không |
| `forecast.stress_test` | Áp một cú sốc mẫu lên dự báo | Monte Carlo | Không |
| `forecast.affordability_check` | Kết quả đủ, sát, hụt cho một khoản chi | Engine tất định | Không |
| `forecast.get_resilience_score` | Điểm chống chịu và 4 thành phần | Đọc bảng | Không |
| `forecast.get_behavior_profile` | Mẫu hành vi đã rút kèm bằng chứng | Đọc bảng | Không |
| `planner.optimize_allocation` | Chia thu nhập vào hũ theo ràng buộc | Quy hoạch tuyến tính | Không |
| `planner.check_suitability` | Kiểm bộ luật trên một đề xuất | Rule engine | Không |
| `planner.save_roadmap`, `get_roadmap` | Lưu và đọc lộ trình có phiên bản | SQL | Có |
| `planner.schedule_nudge` | Lên lịch một lời nhắc | EventBridge Scheduler | Có |
| `knowledge.search` | Tìm trong kho tri thức | Bedrock Knowledge Bases | Không |
| `knowledge.get_fee_schedule` | Biểu phí có cấu trúc theo sản phẩm tín dụng | Bảng, kèm trích dẫn từ RAG | Không |
| `ingest.start_job`, `get_job_status`, `confirm_rows` | Nạp tệp, theo dõi, duyệt dòng | Job bất đồng bộ | Có |
| `audit.get_trace` | Dữ liệu cho bảng "Vì sao" | Đọc log | Không |

### Memory (AgentCore Memory)

| Loại | Lưu gì | Cơ chế | Dùng khi nào |
|---|---|---|---|
| Ngắn hạn | Lượt hội thoại và tool call trong phiên | Event của AgentCore Memory | Giữ mạch, tiếp tục sau khi chờ xác nhận |
| Sở thích | "Đừng nhắc buổi sáng", "ưu tiên hũ Du lịch" | Chiến lược user preference | Chọn giọng và kiểu gợi ý |
| Sự thật về người dùng | "Đang ở trọ", "hay ăn chung với nhóm bạn" (số tiền và ngày lương nằm trong cơ sở dữ liệu, không nằm bộ nhớ) | Chiến lược semantic | Không hỏi lại |
| Tóm tắt phiên | Quyết định đã chốt | Chiến lược summarization | Nối tiếp phiên sau |
| Hành vi | Mẫu chi tiêu kèm bằng chứng, do pipeline đêm ghi | Chiến lược custom | Tư vấn sát người dùng |
| Bài học của agent | Kiểu gợi ý nào được chấp nhận, kiểu nào bị từ chối | Tóm tắt từ bảng `feedback`, ý tưởng từ ReasoningBank | Chọn cách đề xuất lần sau |

Bộ nhớ không lưu số dư hay giao dịch thô. Số luôn được đọc tươi từ tool.

### RAG

- Ba kho: biểu phí và điều khoản sản phẩm có ngày hiệu lực; kiến thức tài chính cá nhân; bộ luật suitability kèm giải thích.
- Truy xuất: hybrid search (câu hỏi chứa tên sản phẩm và con số cụ thể), rerank, lọc metadata theo sản phẩm và ngày hiệu lực, chia đoạn theo điều khoản.
- Chỉ truy xuất khi cần: planner gọi `knowledge.search` lúc cần trích dẫn, không nhồi sẵn vào ngữ cảnh.
- **Số để tính không đi qua RAG**: biểu phí dùng cho phép tính lấy từ bảng có cấu trúc; RAG chỉ cung cấp câu trích để giải thích.

### Guardrail và policy

1. **Bedrock Guardrails**: lọc đầu vào và đầu ra, che thông tin định danh, chặn chủ đề như khuyên mã chứng khoán.
2. **Policy trong AgentCore**: luật Cedar tại Gateway, mặc định từ chối. Tool ghi cần cờ xác nhận và nằm trong hạn mức số tiền. Chạy chế độ chỉ ghi log trước khi bật chặn.
3. **Luật suitability tất định**: nghĩa vụ trước, dự phòng trước đầu tư, không vượt khẩu vị rủi ro, không khuyên vay để tiêu.
4. **Automated Reasoning checks**: kiểm câu trả lời với chính sách đã viết thành logic hình thức. **Phần mở rộng.**

### Hợp đồng đầu ra (Composer)

Composer trả **một JSON duy nhất** gồm `trace_id`, `intent`, `text`, `blocks[]`. Frontend ánh xạ mỗi `type` sang một component, nên thêm tính năng là thêm một loại khối. Các `type` trong ví dụ của proposal (trang 12): `forecast_timeline`, `obligation_impact`, `options`, `explain`, `confirm`. Số trong ví dụ là minh họa. Ví dụ đầy đủ: [overview.md](../architecture/overview.md#hợp-đồng-đầu-ra-composer).

### Observability và đánh giá

- **Trace**: mỗi lượt là một trace OpenTelemetry, có span cho router, planner, từng tool call và verifier. `trace_id` trả về giao diện để mở bảng "Vì sao".
- **Dashboard** CloudWatch: độ trễ, token, chi phí mỗi lượt, tỷ lệ lỗi tool, số lần luật chặn.
- **Đánh giá online**: AgentCore Evaluations lấy mẫu phiên thật và chấm bằng evaluator có sẵn (Correctness, Helpfulness, GoalSuccessRate).
- **Evaluator tự viết**: `NumericGrounding` (mọi số trong câu trả lời có trong kết quả tool), `SchemaValidity` (kiểm JSON), `SuitabilityCompliance` (không có gợi ý vi phạm).
- **Đánh giá offline**: bộ câu chuẩn có quỹ đạo tool mong đợi, chạy mỗi lần đổi prompt hoặc đổi model.

### Quản lý ngữ cảnh

Specialist chạy trong ngữ cảnh riêng và chỉ trả kết luận ngắn cho orchestrator; phần đầu prompt ổn định (vai trò, mô tả tool) được cache; mỗi lượt có giới hạn số vòng và số token, chạm giới hạn thì trả thẻ số liệu tất định.

## 10. Pipeline từng tính năng (§10)

Sáu pipeline phủ cả bảy tính năng; sơ đồ Hình 3–8 ở trang 13–25 của PDF. Quy ước màu trong sơ đồ: tím = người dùng, xanh dương = LLM/agent, xanh lá = tool tất định hoặc ML, vàng = guardrail hoặc luật, đỏ = từ chối hoặc phương án dự phòng.

- **10.1 F2 Hỏi "nếu thì"** (luồng agentic runtime, đầy đủ nhất; câu đơn giản rẽ sang đường nhanh): Guardrails đầu vào → Intent Router → (ngoài phạm vi: nói rõ giới hạn / tra cứu đơn giản: đường nhanh 1 tool / what-if: kiểm đủ tham số, thiếu thì hỏi lại đúng 1 câu bằng interrupt) → Planner dựng `ScenarioSpec` → `get_forecast`, `get_obligations`, `get_fee_schedule` song song → `run_scenario` (Monte Carlo trên dự báo + lịch nghĩa vụ, kèm độ phủ và độ tươi) → kiểm độ tin cậy (thấp thì gắn cảnh báo + mời nạp thêm) → Analyst diễn giải và sinh 2–3 phương án → Verifier (số khớp tool? đạt suitability?) → sai thì trả lỗi có cấu trúc cho agent sửa **tối đa 2 lần**, hết lượt thì **chỉ trả thẻ số liệu tất định** → Composer stream văn bản + khối UI → nếu có hành động đổi số dư thì chờ người dùng xác nhận mới gọi tool ghi + ghi audit → ghi Memory + trace. Tình huống đặc biệt: thiếu số tiền/cách trả → hỏi đúng một câu; hỏi ngoài phạm vi (mã cổ phiếu, vay ở đâu) → nói rõ giới hạn và gợi ý việc làm được; prompt injection hoặc đòi dữ liệu người khác → chặn ở cổng vào, tool chỉ đọc được dữ liệu của chủ JWT; dữ liệu dưới 30 ngày hoặc độ phủ thấp → vẫn trả lời nhưng gắn độ tin cậy thấp; tool lỗi/quá thời gian → thử lại một lần rồi trả phần đã có và nói rõ phần thiếu.
- **10.2 F3 Kiểm tra trước khi quẹt** (quyết định do engine tất định; LLM chỉ viết hai câu giải thích nên luồng vẫn chạy khi LLM chậm hoặc lỗi): `affordability_check` (số dư hũ, dự báo P50/P90, nghĩa vụ sắp đến hạn). Nguồn trả là tiền trong hũ → thẻ xanh (đủ) / vàng (sát: cạn sớm N ngày) / đỏ (hụt M đồng trước kỳ lương). Nguồn trả là tín dụng (trả sau, vay) → tính tổng chi phí thật (gốc + phí dịch vụ + phạt nếu trễ), mô phỏng tháng sau hũ nào hụt khi khoản này đến hạn; nếu nghĩa vụ/thu nhập vượt ngưỡng → thẻ đỏ + luật suitability "không khuyến khích", ngược lại vàng/xanh kèm ngày đến hạn. LLM nhỏ diễn giải 2 câu + phương án (hoãn, đổi hũ, chia nhỏ, trả ngay); LLM lỗi hoặc quá 2 giây → chỉ trả thẻ số liệu. Người dùng chọn: vẫn trả (ghi giao dịch + cập nhật dự báo qua event), phương án khác (tạo nhắc hoặc chuyển hũ sau khi xác nhận), bỏ qua (ghi phản hồi để cá nhân hóa); bỏ qua nhiều lần → giảm tần suất nhắc loại này.
- **10.3 Pipeline theo sự kiện — phân hũ tự động và cập nhật tức thời**: giao dịch không bị chặn lúc thanh toán để hỏi hũ; phân loại sau khi giao dịch xong, theo thứ tự rẻ trước đắt sau, chỉ hỏi người dùng khi vừa không chắc vừa đáng hỏi. Khi người dùng trả trong app và tự chọn hũ nguồn thì bỏ qua toàn bộ phần phân loại. Sự kiện: EventBridge → SQS → Lambda (idempotent). Tiền vào chỉ có hai nhánh: khớp lương đã khai (xác nhận một chạm → chia lương vào hũ theo luật; lệch nhiều so với số đã khai thì hỏi có cập nhật lương không) hoặc vào ô "Tiền vào khác" (không tính là thu nhập, người dùng tự gán). Tiền ra theo **thứ tự phân loại**: bước 0 loại giao dịch (hóa đơn điện → hũ Hóa đơn, nạp điện thoại, QR cửa hàng có ngành hàng; bảng tra, không ML) → bước 1 luật của người dùng (SQL) → bước 2 embedding (tìm giao dịch gần nhất đã có nhãn, pgvector; độ tin cậy ≥ 0,97 thì gán) → bước 3 LLM nhỏ (đọc lời nhắn, số tiền, thời điểm, tín hiệu hành vi). **Xử lý theo độ tin cậy** (ngưỡng minh họa, cần chỉnh trên dữ liệu): ≥ 0,9 tự gán, không báo; 0,6–<0,9 tự gán + đưa vào danh sách "Xem lại" (sửa bằng một chạm); < 0,6 vào hũ tạm "Chưa phân loại" và hỏi gộp một lần mỗi ngày, mỗi khoản kèm 2 gợi ý. Tiền trong hũ tạm vẫn bị trừ khỏi tổng số dư; màn hình dự báo ghi rõ còn bao nhiêu tiền chưa phân loại. **Chuyển khoản cho tên riêng, không lời nhắn**: bước 3 dùng thêm tín hiệu hành vi (lặp lại: cùng người nhận, cùng số tiền, đầu mỗi tháng → khả năng là tiền trọ; lịch sử người nhận; số tiền tròn, giờ ăn trưa, ngay sau một hóa đơn nhóm). Nếu vẫn không rõ: chỉ hỏi khi đáng (khoản đủ lớn hoặc người nhận có khả năng lặp lại; khoản nhỏ một lần vào hũ "Khác", không hỏi); một câu trả lời thành một luật ("chỉ lần này" hoặc "luôn luôn cho người này" — cần cả hai vì cùng một người bạn có thể vừa là chia tiền ăn vừa là cho mượn); tự chỉnh theo từng người (sửa nhiều lần thì nâng ngưỡng tự gán của riêng người đó). Sau khi cập nhật số dư hũ + chỉnh nhanh dự báo: phát hiện lệch khỏi dự báo (CUSUM, ADWIN) → khoản lớn một lần (ECOD) = ngoại lai, chỉ chỉnh dự báo kỳ này, không sinh lại lộ trình; nghi đổi hành vi thì mức mới phải giữ khoảng 2 tuần (PELT đếm xác nhận) → sinh lại lộ trình (pipeline F5) → cổng nhắc (giá trị đủ lớn và hôm nay chưa nhắc?) → gửi 1 việc cần làm hoặc im lặng. Tình huống: giao dịch có loại rõ (hóa đơn, nạp tiền, QR cửa hàng) → gán ở bước 0, không gọi ML; đối tác đã có luật → SQL, không gọi LLM; đối tác mới → embedding rồi LLM, xử lý theo ba mức; sự kiện gửi trùng → khóa idempotency; chi tiêu lệch nhiều ngày liền → đánh dấu nghi đổi hành vi, mức mới giữ 2 tuần thì sinh lại lộ trình bằng job nền; lỗi → đưa vào hàng đợi lỗi, cảnh báo cho đội vận hành.
- **10.4 Pipeline batch đêm — F1 dự báo, F4 điểm chống chịu, F7 hồ sơ hành vi** (mô hình nặng chỉ chạy ở đây; kết quả ghi vào bảng để runtime đọc trong vài mili giây): EventBridge Scheduler 02:00 → Step Functions → nạp lịch đã khai báo (lương, chi phí cố định, nghĩa vụ) → rẽ theo lịch sử dữ liệu của hũ: **< 30 ngày** luật + trung bình nhóm tương tự; **30–90 ngày** mô hình thống kê (ETS, TSB, seasonal naive); **> 90 ngày** Chronos-2 + covariates (ngày lương, cuối tuần, hóa đơn) → hiệu chỉnh khoảng tin cậy (conformal prediction) → Monte Carlo số dư từng hũ (ngày cạn, xác suất hụt) → song song: điểm chống chịu (4 thành phần) và hồ sơ hành vi (đặc trưng + phân cụm → Memory) → phát hiện điểm gãy (PELT) → thay đổi đáng kể thì sinh lại lộ trình (job nền) → cổng nhắc → bản tin sáng "1 việc cần làm" hoặc không gửi → ghi Aurora + chạy đánh giá offline. Tình huống: người dùng mới dưới 30 ngày → luật + trung bình nhóm tương tự, ghi rõ ước lượng ban đầu; hũ chi thưa như Du lịch/Mua sắm → mô hình cho chuỗi gián đoạn thay vì làm mượt thông thường; đủ lịch sử, có nhịp lương rõ → mô hình nền tảng với covariate; khoảng tin cậy lệch thực tế → hiệu chỉnh lại bằng conformal prediction mỗi tuần; hành vi đổi hẳn (đổi việc, chuyển trọ) → phát hiện điểm gãy, mức mới giữ khoảng 2 tuần thì sinh lại lộ trình; không có gì đáng nhắc → không gửi gì.
- **10.5 F5 Sinh và sinh lại lộ trình** (agent đề xuất cấu trúc, bộ tối ưu tính số, cổng suitability có quyền phủ quyết; người dùng duyệt từng bước): kích hoạt bởi onboarding xong, lệch dự báo, đổi mục tiêu/thu nhập, hoặc người dùng yêu cầu → gom ngữ cảnh (mục tiêu, dự báo, nghĩa vụ, hồ sơ hành vi, điểm yếu chống chịu, sở thích từ Memory) → Roadmap Agent phác thảo giai đoạn và hành động → `optimize_allocation` (LP, ràng buộc cứng và mềm) → có nghiệm khả thi? Không → nới ràng buộc mềm (lùi hạn mục tiêu, giảm hũ không thiết yếu) một lần; vẫn không → nói thẳng mục tiêu chưa khả thi + 2 lựa chọn → cổng suitability (nghĩa vụ trước, dự phòng trước đầu tư, không vượt khẩu vị rủi ro, không khuyên vay để tiêu) → vi phạm thì trả lỗi có cấu trúc cho agent sửa (**tối đa 2 lần**), hết lượt thì bỏ hành động vi phạm, giữ phần hợp lệ → Roadmap JSON + lý do từng bước → người dùng duyệt từng bước (chấp nhận, sửa, từ chối) → lưu phiên bản mới + audit → lên lịch kiểm tra tiến độ. Tình huống: mục tiêu không khả thi → nới ràng buộc mềm một lần, vẫn không được thì nói thẳng và đưa 2 lựa chọn; đề xuất đầu tư khi chưa có quỹ dự phòng → cổng suitability chặn, agent sửa, hết lượt thì bỏ hành động đó; người dùng sửa một bước → lưu phiên bản mới, ghi phản hồi, không sinh lại toàn bộ; dự báo đổi nhẹ chưa tới ngưỡng → cập nhật số trong lộ trình cũ, giữ nguyên cấu trúc; người dùng từ chối toàn bộ → hỏi một câu về lý do, ghi vào bộ nhớ cho lần sau.
- **10.6 F6 Nạp dữ liệu ngoài ví** (job bất đồng bộ; người dùng thấy tiến độ và chỉ phải duyệt những dòng hệ thống chưa chắc): tải tệp → S3 + SQS → job bất đồng bộ, giao diện hiện tiến độ → rẽ theo loại tệp: PDF → Bedrock Data Automation; ảnh → LLM đa phương thức trích JSON; CSV → parser + LLM map tên cột; khác → báo lỗi rõ → chuẩn hóa ngày, số tiền, đối tác + che thông tin định danh → khử trùng với sổ cái → phân loại 3 bước → độ tin cậy từng dòng: cao thì tự thêm vào sổ cái; thấp thì vào hàng chờ xác nhận (người dùng duyệt từng dòng) → cập nhật điểm độ phủ dữ liệu → kích hoạt dự báo lại. Tình huống: ảnh mờ hoặc không phải tài liệu tài chính → báo lỗi rõ, gợi ý định dạng được hỗ trợ; dòng trùng với giao dịch đã có → khử trùng, không ghi hai lần; dòng trích được nhưng độ tin cậy thấp → hàng chờ, người dùng duyệt; sao kê có tên và số tài khoản người khác → che trước khi lưu và trước khi đưa vào LLM; tệp lớn → job nền, giao diện nhận tiến độ, xong thì dự báo được tính lại.
- **F7** (hồ sơ hành vi + bản tin chủ động) không có pipeline riêng: chạy trong batch đêm (§10.4) và qua cổng nhắc (§10.3).

## 11. ML và kỹ thuật áp dụng (§11)

Nguyên tắc: **ML và engine tất định lo phần số, LLM lo phần ngôn ngữ và kế hoạch.**

| Tính năng | Bài toán | Kỹ thuật | Vì sao chọn |
|---|---|---|---|
| F1 | Dự báo chi theo ngày của từng hũ | **Chronos-2** zero-shot với covariate biết trước: ngày lương, cuối tuần, lịch hóa đơn | Không cần huấn luyện riêng từng người; model 120 triệu tham số, chạy được trên CPU |
| F1 | Baseline và dữ liệu ngắn | Seasonal naive, ETS, chọn theo backtest | Luôn cần mốc so sánh; dữ liệu 30–90 ngày chưa đủ cho mô hình lớn |
| F1 | Hũ chi thưa, nhiều ngày bằng 0 | **Croston** và **TSB** cho chuỗi gián đoạn | Mô hình làm mượt thường dự báo sai loại chuỗi này |
| F1 | Khoảng tin cậy đúng độ phủ | **Adaptive conformal inference** (Zaffran et al., 2022) | Khoảng của mô hình hay quá hẹp; phương pháp này tự chỉnh khi hành vi đổi |
| F1, F2, F4 | Ngày cạn tiền, xác suất hụt, cú sốc | **Monte Carlo** trên phân vị dự báo cộng lịch nghĩa vụ tất định | Người dùng cần xác suất và ngày cụ thể, không phải đường trung bình |
| F4 | Điểm chống chịu | Chỉ số 4 thành phần theo 4 trụ **Spend, Save, Borrow, Plan** (FinHealth Score), tính từ hành vi thay cho bảng hỏi | Khung đo sức khỏe tài chính đã dùng rộng, trọng số minh bạch |
| F5, sự kiện | Phát hiện hành vi đổi | **CUSUM** và **ADWIN** chạy online, **PELT** (ruptures) chạy offline mỗi đêm. Mức mới phải giữ khoảng 2 tuần mới tính là điểm gãy. Khoản lớn một lần do **ECOD** tách riêng | Online để phản ứng nhanh, offline để xác nhận điểm gãy thật |
| F5 | Chia thu nhập vào hũ | **Quy hoạch tuyến tính** có ràng buộc cứng và mềm (OR-Tools / PuLP) | Có nghiệm tối ưu kiểm chứng được; LLM không phải đoán số |
| F7 | Hồ sơ hành vi | Đặc trưng theo nhịp lương, giờ, ngày trong tuần, mức dùng trả sau. Phân cụm. LLM tóm tắt kèm bằng chứng | Nhận xét phải truy được về số liệu, không phải cảm nhận của LLM |
| F7 | Chi bất thường | **ECOD** cho ngoại lai. Tự phát hiện khoản định kỳ để sau (xem §4) | Không cần nhãn |
| Phân loại | Gán giao dịch vào hũ | Bước 0 theo loại giao dịch, rồi thác ba bước: luật, embedding láng giềng gần, LLM. Ba mức tin cậy quyết định tự gán, xem lại hay hỏi. Chuyển khoản tên riêng dùng thêm đặc trưng hành vi: chu kỳ lặp, lịch sử người nhận, số tiền, thời điểm | Phần lớn giao dịch lặp lại, không đáng gọi LLM |
| F6 | Trích giao dịch từ tài liệu | Bedrock Data Automation theo blueprint, LLM đa phương thức cho ảnh | Blueprint định nghĩa sẵn trường cần lấy và luật kiểm |
| F7 mở rộng | Chọn kiểu và thời điểm nhắc | **Contextual bandit** học từ chấp nhận và từ chối | Mỗi người phản ứng với một kiểu nhắc khác nhau (chưa làm trong MVP) |

**Kỹ thuật agent**:

| Chỗ dùng | Kỹ thuật | Áp dụng thế nào |
|---|---|---|
| L1, L2, L4 | Routing, orchestrator-workers, evaluator-optimizer (Anthropic, Building effective agents) | Ba mẫu workflow ghép lại thay vì một agent tự do. Bắt đầu đơn giản, chỉ thêm tầng khi cần |
| L2, L3 | Agents-as-tools và Graph (Strands multi-agent) | Orchestrator gọi specialist như tool. Luồng cố định dùng Graph |
| F2 | LLM không làm số học (ý tưởng Program-of-Thoughts, Chen et al., 2022) | LLM sinh `ScenarioSpec`, engine tính, LLM đọc kết quả |
| Toàn hệ | Context engineering (Anthropic) | Specialist cô lập ngữ cảnh, truy xuất đúng lúc cần, giữ ngữ cảnh nhỏ và giàu tín hiệu |
| Memory | **Mem0** + AgentCore Memory | Trích, hợp nhất, truy xuất ký ức dài hạn; dùng chiến lược có sẵn của AgentCore Memory, thêm chiến lược custom cho hành vi |
| Memory | **ReasoningBank** | Ký ức chiến lược từ thành công và thất bại: tóm tắt kiểu gợi ý được chấp nhận hoặc bị từ chối để dùng lần sau |
| F7 | Proactive Agent / ProAct | Dùng thời gian rỗi (batch đêm) để chuẩn bị, chỉ can thiệp khi giá trị đủ lớn |
| RAG | Hybrid search và rerank (S3 Vectors hybrid search, Knowledge Bases) | Từ khóa bắt tên sản phẩm và số, vector bắt nghĩa |
| Tool | Ủy quyền tool call ngoài prompt (AWS Agentic AI Lens) | Luật **Cedar** tại Gateway, mặc định từ chối, điều kiện theo claim và tham số |
| L4 | Kiểm câu trả lời bằng logic hình thức (**Automated Reasoning**) | Chính sách suitability viết thành Automated Reasoning policy |
| Hỏi lại, xác nhận | Interrupt và resume (Strands human in the loop) | Agent dừng ở trạng thái chờ, session manager giữ trạng thái, chạy tiếp khi có trả lời |
| Giao diện | Generative UI qua **AG-UI** | Sự kiện có kiểu cho văn bản, tool call, trạng thái. Frontend vẽ component theo khối JSON |
| Đánh giá | LLM judge, evaluator viết bằng code, quỹ đạo tool mong đợi | Lấy online và chạy bộ câu chuẩn offline |

**Điểm chống chịu**: 4 thành phần là (1) **Save** — số ngày sống được bằng số dư khả dụng, (2) **Spend** — tỷ lệ chi trên thu và trả đúng hạn, (3) **Borrow** — tỷ lệ nghĩa vụ trên thu nhập, (4) **Plan** — tiến độ mục tiêu. Độ ổn định thu nhập sẽ thêm vào Plan khi có nhận diện tiền vào. Điểm này không phải điểm tín dụng.

## 12. Trải nghiệm: streaming, bất đồng bộ, giao diện sinh từ JSON (§12)

Người dùng thấy kết quả đầu tiên trong khoảng 2 giây vì thẻ số liệu tất định được đẩy lên trước, lời giải thích stream theo sau.

| Kỹ thuật | Cách làm |
|---|---|
| Streaming văn bản | `stream_async` của Strands, phát sự kiện AG-UI qua SSE |
| Hiển thị tiến trình tool | Sự kiện bắt đầu và kết thúc của từng tool call ("đang đọc dự báo", "đang mô phỏng") |
| Khối giao diện đến trước văn bản | Khối JSON phát ngay khi tool trả kết quả, frontend vẽ theo `type` |
| Gọi tool song song | Planner phát các lời gọi đọc độc lập trong cùng một bước |
| Job nền có tiến độ | Xử lý bất đồng bộ của AgentCore Runtime, phiên được giữ sống khi đang bận |
| Hỏi lại và xác nhận trong luồng | Interrupt và resume với session manager |
| Định tuyến model | LLM nhỏ cho router và diễn giải, LLM lớn cho planner và lộ trình |
| Prompt caching | Cache phần đầu prompt ổn định |
| Tính sẵn | Batch đêm và cập nhật theo sự kiện, runtime chỉ đọc bảng |
| Suy giảm có kiểm soát | Phương án dự phòng tất định ở mọi luồng |
| Một việc mỗi ngày | Cổng giá trị và giới hạn tần suất trước khi nhắc |
| Bảng "Vì sao" và nhãn AI | `trace_id` mở ra dữ liệu đã dùng và luật đã kiểm |

Ngân sách độ trễ cho một câu what-if: cổng vào và router 0,4 giây, ba tool đọc song song 0,6 giây, mô phỏng 0,5 giây. Khối dòng thời gian hiện ở khoảng giây thứ 2, văn bản kết thúc trước giây thứ 8.

## 13. Rủi ro (§13)

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Phạm vi quá rộng cho 3 tuần | Cao | Làm lát dọc F1, F2, F3 trước. Sao kê PDF, bản tin, bảng vận hành là phần mở rộng. Đầu vào do người dùng khai báo |
| Dự báo sai khi dữ liệu ít | Cao | Cổng khởi đầu lạnh, khoảng tin cậy, nhãn độ tin cậy, công bố kết quả backtest |
| Khai báo sai, thiếu hoặc quá dài | Trung bình | Chỉ bắt buộc lương và ngày nhận, phần còn lại khai dần, kể cả bằng chat. Dự báo ghi rõ là dựa trên số đã khai. Lương về khác số đã khai thì hỏi cập nhật |
| Dữ liệu tổng hợp trông không thật | Cao | Hiệu chỉnh persona theo số công khai. Cho giám khảo tự tạo giao dịch và nạp ảnh |
| Nền tảng ví đã có hoặc sắp có tính năng tương tự | Trung bình | Nhấn vào nợ nhỏ trong kế hoạch và bảng "Vì sao". Kiểm tra app trước khi chốt slide |
| LLM bịa số | Trung bình | Số chỉ đến từ tool, verifier đối chiếu, evaluator `NumericGrounding` |
| Lời khuyên bị xem là tư vấn đầu tư | Trung bình | Rủi ro pháp lý (chưa xác minh phân loại theo Luật Trí tuệ nhân tạo). Không nêu sản phẩm cụ thể, luật suitability, nhãn AI, con người quyết định |
| Prompt injection qua tệp nạp | Trung bình | Nội dung tệp chỉ là dữ liệu. Tool ghi cần xác nhận. Luật Cedar mặc định từ chối |
| Độ trễ của nhiều tầng agent | Trung bình | Đường nhanh, gọi song song, tính sẵn, giới hạn số vòng |
| Dịch vụ mới thiếu tính năng ở Region | Trung bình | AgentCore có ở Singapore theo tra cứu ngày 20/11/2026, nhưng từng tính năng con cần kiểm riêng trong tuần 1 |
| Chi phí vượt credit | Thấp | LLM nhỏ, caching, cảnh báo ngân sách, endpoint ML tắt khi không dùng |
| Dữ liệu cá nhân đặt ở Region nước ngoài | Trung bình khi chạy thật | Demo chỉ dùng dữ liệu tổng hợp. Đánh giá tác động trước khi dùng dữ liệu thật |
| Giám khảo dùng thử gặp lỗi | Trung bình | Tài khoản demo có sẵn dữ liệu, nút đặt lại, phương án dự phòng tất định, video quay sẵn |

## 14. Stack (§14)

Toàn bộ hạ tầng nằm trên AWS; phần ngoài AWS chỉ là thư viện mã nguồn mở và GitHub.

| Lớp | Lựa chọn | Ghi chú | Mức |
|---|---|---|---|
| Frontend | Next.js và React, Tailwind, Recharts hoặc visx | Client AG-UI. CopilotKit là lựa chọn nếu muốn có sẵn khung generative UI | MVP |
| Hosting và bảo vệ | Amplify Hosting, CloudFront, WAF | | MVP |
| Định danh | Cognito | JWT đi thẳng vào Runtime | MVP |
| Agent framework | Strands Agents SDK (Python) | Structured output, streaming, interrupt, agents-as-tools, Graph | MVP |
| Agent runtime | AgentCore Runtime | Giao thức AG-UI, streaming, job nền | MVP |
| Dịch vụ AgentCore | Memory, Gateway, Policy, Identity, Observability | Policy chạy chế độ ghi log trước rồi mới bật chặn | MVP |
| Dịch vụ AgentCore | Evaluations, Code Interpreter | Evaluations cho đánh giá online. Code Interpreter cho biểu đồ tùy biến | Mở rộng |
| Mô hình | Amazon Bedrock: một LLM lớn, một LLM nhỏ, embedding đa ngôn ngữ | Chọn theo model có ở Region triển khai | MVP |
| An toàn nội dung | Bedrock Guardrails | Automated Reasoning checks là phần mở rộng | MVP |
| RAG | Bedrock Knowledge Bases | Hybrid search và rerank | MVP |
| Tool | Lambda (Python) | Phần sổ cái có thể viết Java nếu đội muốn dùng thế mạnh Spring | MVP |
| Dữ liệu | Aurora PostgreSQL Serverless v2, pgvector, S3 | pgvector cho bước embedding của phân loại | MVP |
| Dự báo | StatsForecast hoặc Darts cho mô hình thống kê | Chạy trong Lambda container | MVP |
| Dự báo | Chronos-2 trên SageMaker | Có thể thay bằng container CPU để giảm chi phí | MVP nếu kịp, không thì mở rộng |
| ML khác | ruptures, PyOD, scikit-learn, OR-Tools hoặc PuLP | Điểm gãy, ngoại lai, phân cụm, tối ưu | MVP |
| Sự kiện và batch | EventBridge, SQS, Step Functions | | MVP |
| Tài liệu | LLM đa phương thức cho ảnh, Bedrock Data Automation cho PDF | PDF là phần mở rộng | Một phần |
| Quan sát | CloudWatch, OpenTelemetry, CloudTrail | | MVP |
| Bảo mật | KMS, Secrets Manager, IAM | | MVP |
| Hạ tầng dạng code | AWS CDK, khởi đầu từ khung FAST | GitHub Actions cho CI | MVP |

## 15. Kịch bản demo và kế hoạch 3 tuần (§15)

Video 3 phút kể một câu chuyện của Minh qua sáu cảnh. Giám khảo làm lại được từng cảnh bằng tài khoản demo có sẵn dữ liệu.

| Cảnh | Thời lượng | Trên màn hình | Tính năng |
|---|---|---|---|
| 1 | 0:00–0:30 | Mở app: dòng thời gian báo hũ Ăn uống cạn ngày 23, còn 12 ngày nữa mới tới kỳ lương | F1 |
| 2 | 0:30–1:15 | Gõ "nếu mua tai nghe 1,2 triệu bằng Ví Trả Sau thì sao". Biểu đồ dịch chuyển, hiện tổng chi phí thật và 2 phương án | F2, F3 |
| 3 | 1:15–1:45 | Bấm "mất việc 2 tháng". Điểm chống chịu tụt, hiện số ngày trụ được | F4 |
| 4 | 1:45–2:20 | Lộ trình sinh lại. Mở bảng "Vì sao". Hỏi "nên mua cổ phiếu nào" và thấy trợ lý từ chối đúng phạm vi | F5, suitability |
| 5 | 2:20–2:50 | Chụp ảnh một thông báo chuyển khoản nạp vào. Độ phủ dữ liệu tăng, dự báo cập nhật | F6 |
| 6 | 2:50–3:00 | Màn hình trace cho đội sản phẩm: mọi quyết định của agent xem lại được | Góc "Future Workspace" |

**Kế hoạch** (giả định đội nộp bài trước chung kết 11/12/2026; hạn nộp chính xác cần xác nhận):

| Tuần | Ngày | Mục tiêu | Việc chính |
|---|---|---|---|
| 1 | 21–27/11 | Nền chạy được từ đầu đến cuối | Triển khai khung FAST, schema Aurora, bộ sinh dữ liệu 3 persona, tool `ledger.*`, router và đường nhanh, màn hình khai báo, màn hình hũ, kiểm tra tính năng theo Region |
| 2 | 28/11–4/12 | Ba tính năng lõi | F1 dự báo và Monte Carlo, F2 what-if có streaming, F3 kiểm tra trước khi quẹt, verifier và luật suitability, memory, bảng "Vì sao" |
| 3 | 5–10/12 | Hoàn thiện và đóng gói | F4, F5, F6 với ảnh chụp, bộ 50 câu đánh giá, sửa lỗi, quay video, slide 10 trang, README |

Chia vai cho 3 người: một người lo agent và harness, một người lo dữ liệu, ML và batch, một người lo frontend và demo. Nếu đội 2 người thì gộp vai frontend vào người lo agent và cắt F6.

## 16. Kế thừa từ Swinburne và câu hỏi mở (§16)

Khoảng một nửa nền kỹ thuật của proposal Swinburne dùng lại được; phần thay đổi lớn nhất là đổi trục từ tín hiệu vĩ mô sang nghĩa vụ và hành vi của từng người.

| Thành phần trong Swinburne | Quyết định | Thay đổi |
|---|---|---|
| Pipeline phân loại hũ 3 bước | Giữ | Thêm bước embedding giữa luật và LLM, bước 0 theo loại giao dịch, ba mức độ tin cậy và hỏi gộp |
| Adaptive Wealth Roadmap | Giữ, đổi trục | Sinh lại theo lệch dự báo và nghĩa vụ thay vì CPI, VN-Index, lãi suất |
| Suitability và Cedar | Giữ | Cedar chuyển về Policy trong AgentCore tại Gateway. Suitability thành rule engine riêng |
| Audit trail với trace_id | Giữ | Thêm bảng "Vì sao" cho chính người dùng |
| Số chỉ lấy từ SQL | Giữ | Thêm evaluator kiểm số tự động |
| Mô hình 3 tầng tự quyết | Giữ 2 tầng | Bỏ tầng chuyển cho chuyên viên tư vấn khỏi MVP |
| Cổng khởi đầu lạnh, kiểm độ tươi, điểm tin cậy | Giữ | |
| Kats, River, PyOD, Statsmodels, Darts, ruptures | Giữ một phần | Thêm Chronos-2, conformal prediction, mô hình chuỗi gián đoạn |
| Strands và AgentCore (Memory, Identity, Observability) | Giữ | Thêm Gateway, Policy, Evaluations, AG-UI |
| Stock Agent, Efficient Frontier, VNStock, Dexter | Bỏ | Ngoài phạm vi, có rủi ro pháp lý |
| Macro-responsive budgeting | Thu nhỏ | Không nằm trong MVP |
| KPI B2B2C về chi phí chuyên viên | Bỏ | Thay bằng KPI ở §6 |

Phần mới hoàn toàn: mô hình nghĩa vụ, what-if, điểm chống chịu, nạp tài liệu, hồ sơ hành vi, giao diện sinh từ JSON.

**Câu hỏi mở về scope**: xem [open-questions.md](../requirements/open-questions.md) (8 câu hỏi, giữ dạng checklist).

## 17. Tài liệu tham khảo (§17)

Toàn bộ nguồn kỹ thuật ở mục 17 và nguồn số liệu ở bảng §2 được liệt kê, kèm URL, trong [docs/references/links.md](../references/links.md). Proposal ghi chú: Program-of-Thoughts (Chen et al., 2022) và Croston, TSB cho chuỗi gián đoạn được nêu tên nhưng **không kèm link** vì tác giả chưa mở lại trang gốc.
