# Yêu cầu chức năng (FR)

> Bản nháp để chủ dự án duyệt, tổng hợp ngày 22/11/2026. FR1–FR15 giữ đúng mã và phạm vi của proposal §5. File này viết chi tiết thêm phần proposal chỉ có một dòng: người dùng, luồng chính, ngoại lệ, quy tắc áp dụng ([BR](02-business-rules.md)), tiêu chí nghiệm thu ([AC](05-acceptance-criteria.md)).
> Trạng thái thực hiện lấy theo [HANDOFF](../../HANDOFF.md) và kết quả các phase, **cập nhật 24/11/2026 tối** (phase 5 đã deploy, chưa đóng). Bảng điều khiển tiến độ: [13-tien-do-technical.md](13-tien-do-technical.md).

## Tổng quan

| FR | Tên | Tính năng | Mức | Phase | Trạng thái thực hiện |
|---|---|---|---|---|---|
| FR1 | Hồ sơ, hũ và sổ cái | nền | MVP | 1–2 | ✅ Đạt (đóng phase 2, 22/11). Cơ cấu hũ mới (BR-63 đến 73) chưa code |
| FR2 | Phân hũ tự động | nền | MVP | 2 (bước 0), 4 | ◐ Đủ 4 bước (phase 4, đóng 24/11): đúng 92%; **phải hỏi 17,4%**, chưa đạt < 10% |
| FR3 | Dự báo theo hũ | F1 | MVP | 2 | ✅ Đạt (phase 2); backtest đạt NFR-10, 11 |
| FR4 | Quản lý nghĩa vụ | nền, F1, F3 | MVP | 2 | ✅ Đạt (phase 2); C-07 chưa chốt |
| FR5 | What-if hội thoại | F2 | MVP | 3 | ✅ Đạt (phase 3, đóng 23/11): golden 30/30; p95 28 giây chưa đạt NFR-03 |
| FR6 | Kiểm tra trước khi quẹt | F3 | MVP | 3 | ◐ Chạy (phase 3): p95 282 ms; **dải "sát" hẹp và định nghĩa khác BR-36** (C-02) |
| FR7 | Điểm chống chịu | F4 | MVP | 4 | ✅ Đạt (phase 4, đóng 24/11) |
| FR8 | Lộ trình thích ứng | F5 | MVP | 4 | ✅ Đạt (phase 4); lập trong chat 20–26 giây |
| FR9 | Nạp dữ liệu ngoài ví | F6 | MVP một phần | 5 | ◐ Đã deploy (phase 5, chưa đóng): CSV 50/50; OCR ảnh thật 9/11 (v25), chốt ở lượt RC |
| FR10 | Hồ sơ hành vi và bộ nhớ | F7 | MVP | 5 | ◐ Đã deploy (phase 5): hồ sơ hành vi đạt; bộ nhớ đã sửa gốc (25/11), chờ đóng phase 5 |
| FR11 | Bảng "Vì sao" | xuyên suốt | MVP | 3, 5 | ✅ Đạt (phase 3); trace mở qua REST (phase 5) |
| FR12 | Suitability và xác nhận | xuyên suốt | MVP | 1 (xác nhận), 3 (suitability) | ✅ Xác nhận: Đạt (phase 1). Suitability: Đạt đối kháng (phase 3–5); lỗ hổng hũ Dự phòng đã vá bằng luật thứ bảy (25/11) |
| FR13 | Bản tin chủ động | F7 | Mở rộng | 5 | ◐ Đã deploy (phase 5): thẻ và bản tin; chờ kiểm trên app |
| FR14 | Cảnh báo khoản chuyển lệch thói quen | phụ | Mở rộng | 5 (nếu kịp) | ⏳ Chưa làm (phase 5 ghi "nếu kịp", nằm trong thứ tự cắt) |
| FR15 | Bảng vận hành cho đội sản phẩm | vận hành | Mở rộng | 5 | ◐ Đã deploy (phase 5): trace qua REST đạt; Transaction Search chưa bật |

**Vai trò:**
- **Người dùng**: người 18–30 tuổi đang ở giai đoạn có thu nhập đều đặn đầu tiên, có dùng trả sau (BC-13), chia ba giai đoạn: sinh viên đi làm thêm, mới đi làm, đi làm ổn định. Persona chính là Minh, 22 tuổi, 9 triệu/tháng, giai đoạn mới đi làm.
- **Giám khảo**: dùng tài khoản demo, có quyền như người dùng.
- **Đội vận hành (`ops`)**: chỉ xem trace và bảng vận hành.
- **Hệ thống**: các job nền như batch đêm và pipeline sự kiện.

---

## FR1 — Hồ sơ, hũ và sổ cái

**User story**: Là người dùng, tôi muốn khai lương một lần, chia lương vào các hũ có số dư riêng và ghi giao dịch, để biết từng hũ còn bao nhiêu tiền thật.

- **Tiền điều kiện**: đã đăng nhập.
- **Luồng chính**
  1. Onboarding: nhập lương thực nhận và ngày nhận (bắt buộc), chọn bộ hũ mẫu hoặc tự tạo, đặt tỷ lệ chia sao cho tổng bằng 100%. *Đề xuất 24/11:* thêm một câu **tùy chọn** "Bạn đang ở giai đoạn nào?" để chọn một trong 3 bộ hũ theo giai đoạn sống; bỏ qua thì dùng bộ "Mới đi làm" (BR-70).
  2. Tổng quan hiện tổng số dư, các hũ, thẻ chủ động và giao dịch gần đây.
  3. Tạo, sửa hũ: tên, loại, tỷ lệ chia, mục tiêu và hạn (tùy chọn). *Đề xuất 24/11:*
     - Hũ tích lũy chọn thêm **mục đích**: đệm an toàn, quỹ dồn, mục tiêu, dài hạn (BR-63).
     - Hũ đệm có mục tiêu tự tính theo số tháng chi thiết yếu (BR-64).
     - Hũ quỹ dồn có danh sách khoản cần (tên, số tiền, ngày cần) và số trích mỗi kỳ tự tính (BR-66).
     - Hũ dài hạn chỉ nhận tiền khi hũ đệm đã đủ (BR-68).
     - Có thể thêm các hũ tùy chọn: Gửi về gia đình, Phát triển bản thân, Sức khỏe (BR-72).
  4. Ghi giao dịch trên ví mô phỏng: chi tiêu, chuyển cho người nhận, chuyển giữa hũ. Người dùng chọn hũ nguồn.
  5. Lương về thì hệ thống tạo sự kiện chờ. Người dùng chọn "chia vào hũ" hoặc "giữ ở Tiền vào khác".
  6. Tiền vào khác lương nằm ở ô Tiền vào khác; người dùng tự gán sang hũ.
- **Ngoại lệ**
  - Tổng tỷ lệ khác 100%: không cho lưu.
  - Số tiền vượt trần hoặc vượt số dư hũ: từ chối, kèm lý do.
  - Lương lệch số đã khai quá ngưỡng: hỏi có cập nhật lương không.
  - Gửi trùng giao dịch: không ghi lần hai.
- **BR**: BR-01, 02, 04–15, 45–47, 62; đề xuất: 63, 64, 66, 68–70, 72
- **AC**: [AC-FR1](05-acceptance-criteria.md#fr1--hồ-sơ-hũ-và-sổ-cái)

## FR2 — Phân hũ tự động

**User story**: Là người dùng, tôi không muốn phải chọn hũ cho mọi khoản chi, và chỉ muốn bị hỏi khi thật cần.

- **Tiền điều kiện**: có giao dịch chi chưa có hũ, ví dụ chuyển khoản cho người nhận hoặc dòng nạp từ tệp.
- **Luồng chính**
  1. Giao dịch xong thì phân loại chạy sau, không chặn lúc trả.
  2. Lần lượt qua 4 bước: loại giao dịch, luật của người dùng, giao dịch tương tự đã có nhãn, LLM nhỏ.
  3. Xử lý theo độ tin cậy: tự gán; tự gán và đưa vào "Xem lại"; hoặc vào Chưa phân loại để hỏi gộp mỗi ngày, mỗi khoản kèm 2 gợi ý.
  4. Người dùng sửa thì chọn "chỉ lần này" hoặc "luôn luôn cho người này"; lần sau với cùng người nhận thì tự gán đúng.
- **Ngoại lệ**
  - Khoản nhỏ một lần: vào hũ "Khác", không hỏi.
  - Không rõ và đáng hỏi: hỏi gộp.
  - Lỗi xử lý: đưa vào hàng đợi lỗi.
- **BR**: BR-14–19
- **AC**: [AC-FR2](05-acceptance-criteria.md#fr2--phân-hũ-tự-động)

## FR3 — Dự báo theo hũ

**User story**: Là người dùng, tôi muốn biết hũ nào sắp cạn và cạn vào ngày nào trước kỳ lương, để kịp xoay xở.

- **Tiền điều kiện**: đã khai lương và ngày nhận, có ít nhất một hũ người dùng.
- **Luồng chính**
  1. Batch đêm và pipeline sự kiện tính dự báo 30 ngày cho từng hũ.
  2. Chi tiết hũ hiện biểu đồ dải P10–P90 và đường P50, mốc lương và nghĩa vụ, ngày cạn dự kiến, xác suất hụt hoặc nhóm tin cậy, độ phủ và độ tươi.
  3. Tổng quan có thẻ chủ động cho hũ rủi ro nhất.
  4. Trong chat, hỏi "hũ X còn trụ được bao lâu" thì nhận cùng khối dự báo với màn hình.
- **Ngoại lệ**
  - Dưới 21 ngày dữ liệu: nhãn "ước lượng ban đầu".
  - Backtest chưa đạt độ phủ: hiện nhóm tin cậy thay cho %.
  - Dự báo quá hạn: tính lại trước khi trả lời.
  - Hũ hệ thống: không có dự báo.
  - *Đề xuất 24/11:* mỗi loại hũ dự báo một kiểu (BR-73):
    - Chi theo kỳ: dự báo ngày cạn.
    - Nghĩa vụ: đủ hay thiếu trước ngày đến hạn.
    - Quỹ dồn và mục tiêu: tiến độ tới số tiền và ngày cần. Ngày cần của khoản quỹ dồn hiện thành mốc (BR-66).
    - Đệm an toàn và dài hạn: chỉ theo dõi mức so với mục tiêu, không dự báo "cạn".
- **BR**: BR-02, 11, 13, 28–34; đề xuất: 66, 73
- **AC**: [AC-FR3](05-acceptance-criteria.md#fr3--dự-báo-theo-hũ)

## FR4 — Quản lý nghĩa vụ

**User story**: Là người dùng, tôi muốn mọi khoản phải trả (trọ, hóa đơn, vay, trả sau) nằm chung một lịch và được tính vào dự báo, để không bị bất ngờ.

- **Luồng chính**
  1. Khai nghĩa vụ: loại, số tiền hoặc khoảng, chu kỳ, ngày đến hạn, cờ thiết yếu, hũ dùng để trả.
  2. Mua bằng hạn mức trả sau mô phỏng thì tự sinh hoặc cộng dồn nghĩa vụ trả sau (gốc + phí, đến hạn ngày 5 kế tiếp).
  3. Nghĩa vụ hiện thành mốc trên dòng thời gian dự báo, và được nhắc trước khi đến hạn.
  4. Trả nghĩa vụ từ một hũ: khoản một lần chuyển "đã trả", khoản lặp dời sang kỳ sau.
- **Ngoại lệ**
  - Vượt hạn mức trả sau: từ chối.
  - Khai khoảng số tiền: dùng trung điểm.
  - Chưa có phí trễ hạn có nguồn: không tính.
- **BR**: BR-07, 20–27
- **AC**: [AC-FR4](05-acceptance-criteria.md#fr4--quản-lý-nghĩa-vụ)

## FR5 — What-if hội thoại

**User story**: Là người dùng, tôi muốn hỏi "nếu mua tai nghe 1,2 triệu bằng trả sau thì sao" và thấy ngay ảnh hưởng tới các hũ, cùng vài phương án khác.

- **Luồng chính**
  1. Gõ câu hỏi, router nhận đây là what-if.
  2. Agent dựng kịch bản có cấu trúc, gọi dự báo, nghĩa vụ và biểu phí, rồi engine mô phỏng.
  3. Hiện dòng thời gian trước và sau, khối tác động nghĩa vụ (tổng phải trả, ngày đến hạn, khoản hụt tháng sau), 2–3 phương án và lời giải thích. Khối số hiện trước văn bản.
  4. Chọn một phương án có đổi số dư thì đi qua xác nhận.
- **6 loại kịch bản**: mua một lần, mua trả sau, đổi thu nhập, thêm khoản định kỳ, chuyển giữa hũ, lùi mục tiêu.
- **Ngoại lệ**
  - Thiếu tham số: hỏi lại đúng một câu.
  - Ngoài phạm vi: từ chối kèm gợi ý.
  - LLM lỗi hoặc hết trần: chỉ trả thẻ số liệu.
  - Tool lỗi: thử lại một lần, rồi trả phần đã có và nói rõ phần thiếu.
- **BR**: BR-21, 39–44, 48
- **AC**: [AC-FR5](05-acceptance-criteria.md#fr5--what-if-hội-thoại)

## FR6 — Kiểm tra trước khi quẹt

**User story**: Là người dùng, trước khi trả tiền tôi muốn biết khoản này đủ, sát hay hụt với hũ mình chọn, và nếu trả sau thì tổng thật phải trả là bao nhiêu.

- **Luồng chính**
  1. Ở màn chuyển tiền hoặc thanh toán, sau khi nhập số tiền và chọn nguồn, hiện thẻ đủ, sát hoặc hụt cho từng hũ nguồn có thể chọn.
  2. Nguồn là trả sau: hiện tổng chi phí thật và ảnh hưởng tới tháng sau.
  3. Hai câu giải thích và phương án (hoãn, đổi hũ, chia nhỏ, trả ngay).
  4. Người dùng chọn: vẫn trả, phương án khác, hoặc bỏ qua.
- **Ngoại lệ**
  - LLM chậm quá 2 giây: chỉ hiện thẻ số.
  - Bỏ qua nhiều lần: giảm nhắc.
  - Nghĩa vụ trên thu nhập vượt ngưỡng: thẻ đỏ kèm "không khuyến khích".
- **BR**: BR-35–38, 42
- **AC**: [AC-FR6](05-acceptance-criteria.md#fr6--kiểm-tra-trước-khi-quẹt)

## FR7 — Điểm chống chịu

**User story**: Là người dùng, tôi muốn biết nếu có biến cố (mất việc, tiền trọ tăng, ốm) thì mình trụ được bao lâu.

- **Luồng chính**
  1. Màn Điểm chống chịu hiện điểm 0–100, bốn thành phần và giải thích từng thành phần.
  2. Bấm một trong ba cú sốc thì thấy điểm sau sốc và số ngày trụ được.
  3. Có dòng "không phải điểm tín dụng".
  4. *Đề xuất 24/11:* số ngày trụ được khi có cú sốc tính chủ yếu từ **hũ đệm an toàn** (tiền trong hũ mục tiêu chỉ dùng khi hết đệm). Rút tiền khỏi hũ đệm thì hiện trước ảnh hưởng tới điểm (BR-64).
- **BR**: BC-07, BR-51, 52; đề xuất: 64
- **AC**: [AC-FR7](05-acceptance-criteria.md#fr7--điểm-chống-chịu)

## FR8 — Lộ trình thích ứng

**User story**: Là người dùng, tôi muốn một kế hoạch theo giai đoạn để đạt mục tiêu, tự cập nhật khi tôi tiêu khác đi, và tôi được duyệt từng bước.

- **Luồng chính**
  1. Lộ trình được sinh khi onboarding xong, khi lệch dự báo kéo dài, khi đổi mục tiêu hoặc thu nhập, hoặc khi người dùng yêu cầu.
  2. Mỗi bước có lý do.
  3. Người dùng chấp nhận, sửa hoặc từ chối từng bước.
  4. Mỗi lần đổi lưu thành một phiên bản, và so được với bản trước.
- **Ngoại lệ**
  - Mục tiêu không khả thi: nới ràng buộc mềm một lần; vẫn không được thì nói thẳng và đưa 2 lựa chọn.
  - Bước vi phạm suitability: bỏ bước đó.
  - Từ chối toàn bộ: hỏi một câu về lý do.
- *Đề xuất 24/11:* lộ trình phân bổ tiền dư theo thứ tự cố định: nghĩa vụ → đệm an toàn → quỹ dồn → mục tiêu → dài hạn (BR-65). Khi có tín hiệu (lương tăng ổn định, hũ đệm đủ, hết khoản vay), lộ trình gợi ý chuyển sang bộ hũ của giai đoạn sống kế tiếp, không tự đổi (BR-71).
- **BR**: BR-21, 42, 44, 53–55; đề xuất: 65–68, 71
- **AC**: [AC-FR8](05-acceptance-criteria.md#fr8--lộ-trình-thích-ứng)

## FR9 — Nạp dữ liệu ngoài ví

**User story**: Là người dùng, tôi muốn chụp ảnh thông báo ngân hàng hoặc tải CSV để dự báo tính cả tiền ngoài ví, mà không phải nhập tay.

- **Luồng chính**
  1. Đồng ý cho nguồn nạp.
  2. Tải tệp, theo dõi tiến độ.
  3. Hệ thống trích, chuẩn hóa, che thông tin định danh, chống trùng, phân loại.
  4. Duyệt các dòng chưa chắc.
  5. Độ phủ dữ liệu tăng, dự báo tính lại.
- **Ngoại lệ**
  - Ảnh mờ hoặc không phải tài liệu tài chính: lỗi rõ.
  - Dòng trùng: bỏ qua.
  - Nội dung tệp có lệnh: coi là dữ liệu.
- **BR**: BC-06, BR-15, 56–58
- **AC**: [AC-FR9](05-acceptance-criteria.md#fr9--nạp-dữ-liệu-ngoài-ví)

## FR10 — Hồ sơ hành vi và bộ nhớ

**User story**: Là người dùng, tôi muốn trợ lý nhớ sở thích và mục tiêu của tôi ở phiên sau mà không phải nói lại, và tôi xóa được những gì nó nhớ.

- **Luồng chính**
  1. Sở thích nêu trong chat (ví dụ "đừng nhắc buổi sáng") được lưu.
  2. Batch đêm rút ra nhận xét hành vi kèm số liệu.
  3. Phiên sau dùng lại các thông tin đó.
  4. Người dùng xem và xóa được bộ nhớ.
- **BR**: BR-59, BC-06
- **AC**: [AC-FR10](05-acceptance-criteria.md#fr10--hồ-sơ-hành-vi-và-bộ-nhớ)

## FR11 — Bảng "Vì sao"

**User story**: Là người dùng, tôi muốn xem vì sao trợ lý khuyên như vậy: số liệu nào, luật nào, chắc chắn đến đâu.

- **Luồng chính**: mọi câu trả lời có gợi ý đều có nút "Vì sao". Bảng ghi dữ liệu đã dùng, luật đã kiểm, độ tin cậy và `trace_id`.
- **Ngoại lệ**: trace của người khác thì không truy cập được.
- **BR**: BR-48, 49
- **AC**: [AC-FR11](05-acceptance-criteria.md#fr11--bảng-vì-sao)

## FR12 — Suitability và xác nhận

**User story**: Là người dùng, tôi muốn không bao giờ bị trừ tiền nếu chưa bấm đồng ý, và không nhận lời khuyên đi ngược lợi ích của mình.

- **Luồng chính, phần xác nhận**
  1. Agent hoặc màn hình tạo đề nghị kèm bản xem trước do server tính.
  2. Người dùng bấm xác nhận, server cấp token dùng một lần.
  3. Ghi xong thì hiện biên nhận.
  4. Hủy được; hoàn tác được.
- **Luồng chính, phần suitability**
  1. Mọi gợi ý qua luật tất định (BR-42) trước khi hiện.
  2. Vi phạm thì agent sửa tối đa 2 lần, rồi mới đến phương án dự phòng.
- **Ngoại lệ**
  - Token hết hạn, sai, dùng lại hoặc của người khác: từ chối.
  - Đề nghị hết hạn: yêu cầu hỏi lại.
- **BR**: BC-03, BC-04, BR-03, 42–47, 50; đề xuất: 65, 68
- **AC**: [AC-FR12](05-acceptance-criteria.md#fr12--suitability-và-xác-nhận)

## FR13 — Bản tin chủ động (mở rộng)

**User story**: Là người dùng, tôi muốn nhận tối đa một gợi ý mỗi ngày và chỉ khi thật đáng.

- **Luồng chính**
  1. Sau batch đêm, cổng nhắc kiểm ngưỡng giá trị và kiểm hôm nay đã nhắc chưa.
  2. Gửi một việc cần làm, hoặc im lặng.
  3. Người dùng chọn "Để sau" hoặc "Ít nhắc loại này".
- **BR**: BR-27, 60
- **AC**: [AC-FR13](05-acceptance-criteria.md#fr13--bản-tin-chủ-động-mở-rộng)

## FR14 — Cảnh báo khoản chuyển lệch thói quen (mở rộng)

**User story**: Là người dùng, tôi muốn được cảnh báo khi một khoản chuyển khác hẳn thói quen của tôi và làm hụt hũ đệm an toàn (`buffer`, BR-64). Đây là mức phụ của chủ đề chống lừa đảo.

- **Luồng chính**: so khoản chuyển với mẫu chi cá nhân. Lệch nhiều thì hiện cảnh báo kèm ảnh hưởng tới hũ đệm an toàn (mức so với mục tiêu, số ngày trụ được; BR-64) trước khi xác nhận.
- **Trạng thái**: cắt đầu tiên nếu thiếu thời gian (master-plan).
- **AC**: [AC-FR14](05-acceptance-criteria.md#fr14-fr15--mở-rộng)

## FR15 — Bảng vận hành cho đội sản phẩm (mở rộng)

**User story**: Là thành viên đội sản phẩm hoặc rủi ro, tôi muốn xem lại mọi quyết định của agent, điểm đánh giá và số lần luật chặn.

- **Luồng chính**
  1. Tài khoản nhóm `ops` mở màn trace từ bảng "Vì sao" hoặc từ danh sách.
  2. Màn trace hiện các bước, tool đã gọi và luật đã kiểm.
- **Ngoại lệ**: tài khoản ngoài nhóm `ops` bị từ chối.
- **AC**: [AC-FR15](05-acceptance-criteria.md#fr14-fr15--mở-rộng)

---

## Ma trận truy vết

| FR | Pain point | BR chính | Cảnh demo | Phase |
|---|---|---|---|---|
| FR1 | P4, P6 | BR-01, 04–15; đề xuất 63–72 | 1 | 1–2; cơ cấu hũ mới: 4 |
| FR2 | P4 | BR-14–19 | — | 4 |
| FR3 | P1 | BR-28–34 | 1 | 2 |
| FR4 | P2, P3 | BR-20–27 | 1, 2 | 2 |
| FR5 | P1, P5 | BR-39–44 | 2 | 3 |
| FR6 | P3, P5 | BR-35–38 | 2 | 3 |
| FR7 | P6 | BR-51–52 | 3 | 4 |
| FR8 | P6 | BR-53–55 | 4 | 4 |
| FR9 | P4 | BR-56–58 | 5 | 5 |
| FR10 | P4, P7 | BR-59 | — | 5 |
| FR11 | P7 | BR-48–49 | 4 | 3, 5 |
| FR12 | P7 | BR-42–47, 50 | 2, 4 | 1, 3 |
| FR13 | P1, P2 | BR-27, 60 | — | 5 |
| FR14 | — | — | — | 5 |
| FR15 | P7 (đội rủi ro) | BR-49 | 6 | 5 |
