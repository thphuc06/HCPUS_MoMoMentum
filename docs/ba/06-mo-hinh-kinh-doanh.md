# Mô hình kinh doanh, chỉ số đo lường và gói dịch vụ

> Bản nháp để chủ dự án duyệt, viết ngày 24/11/2026. Mục đích: (1) chọn hướng thương mại hóa; (2) định nghĩa ba nhóm chỉ số **người dùng mới**, **người dùng quay lại** và **ROI**, nói rõ lấy dữ liệu ở đâu; (3) chia gói theo mức dùng AI.
> Mọi con số về giá, mức tăng giảm trong file này là **giả thuyết cần kiểm chứng bằng pilot**, trừ khi có ghi nguồn. KPI gốc của proposal ở [proposal-summary §6](../proposal/proposal-summary.md#6-lợi-ích-và-kpi-6).

## 1. Đề xuất ngắn

1. **Hướng chính: B2B2C.** Bán Yofina như một **lớp AI kế hoạch tài chính** gắn vào app của bên khác: ví điện tử (trước hết là MoMo), ngân hàng số, công ty tài chính có sản phẩm trả sau. Người dùng cuối dùng Yofina ngay trong app quen thuộc của họ.
2. **B2C độc lập không nên là hướng chính.** Người Việt ít trả phí cho app. Ngay cả nền tảng video nội địa cũng đang phải đổi mô hình vì tỷ lệ trả phí thấp [N7]. Một app riêng thì cũng không có dữ liệu giao dịch thật (BC-01).
3. **Gói dịch vụ chia theo mức dùng AI** vì chi phí AI tăng theo độ sâu tính năng: dự báo chạy batch thì rẻ, còn hội thoại "nếu thì" và đọc ảnh thì đắt. Gói càng cao càng mở khóa tính năng tốn tài nguyên hơn và có hạn mức lượt dùng lớn hơn ([mục 5](#5-chia-gói-theo-mức-dùng-ai)).
4. **Nguyên tắc không thương lượng: không kiếm tiền bằng cách đẩy người dùng vay thêm.** Cleo, một app AI tài chính ở Mỹ, có doanh thu từ phí ứng tiền nhanh đã vượt doanh thu thuê bao (ước tính 61,7% năm 2025) và từng bị FTC xử lý về quảng cáo ứng tiền [N4]. Mô hình đó mâu thuẫn trực tiếp với BR-42 ("không khuyên vay để tiêu"), và cũng là rủi ro uy tín với giám khảo.

## 2. Các hướng thương mại hóa

| Hướng | Ai trả tiền | Lợi thế | Bất lợi | Đánh giá |
|---|---|---|---|---|
| **B2C độc lập** (app riêng, freemium) | Người dùng cuối | Tự chủ sản phẩm, đi nhanh | Không có dữ liệu giao dịch thật; người dùng phải nhập tay, mà đó chính là pain point P4; tỷ lệ chuyển sang trả phí ở mô hình freemium chỉ khoảng 2–4% [N5]; người Việt ít trả phí cho app [N7] | Yếu. Chỉ hợp làm bản demo hoặc kênh thử nghiệm |
| **B2B2C: tính năng trong ví** (MoMo, ZaloPay…) | Ví trả phí bản quyền, hoặc ví bán gói nâng cao cho người dùng và chia doanh thu | Có sẵn dữ liệu giao dịch, hũ, trả sau; có hàng chục triệu người dùng; MoMo đã có hơn 3 triệu người dùng Quản Lý Chi Tiêu/tháng ([01](01-boi-canh-thi-truong.md)) | Phụ thuộc một đối tác; chu kỳ bán hàng dài; ví có thể tự làm | **Mạnh nhất.** Hợp với cuộc thi, vì MoMo vừa là người chấm vừa là khách hàng tự nhiên |
| **B2B2C: ngân hàng, công ty tài chính** (white-label) | Ngân hàng hoặc công ty tài chính | Bên cho vay hưởng lợi trực tiếp khi khách trả đúng hạn; ngân hàng muốn giữ tiền gửi và bán chéo. Personetics bán theo mô hình này cho hơn 100 ngân hàng [N3] | Yêu cầu tích hợp và bảo mật cao; định giá theo từng hợp đồng | Mạnh, là hướng mở rộng thứ hai |
| **B2B: bảng điều khiển cho đội sản phẩm, rủi ro** | Đội sản phẩm hoặc rủi ro của đối tác | Đã có ý tưởng FR15 (trace, luật chặn) | Không tự đứng một mình được | Bán kèm gói Doanh nghiệp |

**Lộ trình đề xuất:**
1. **Cuộc thi:** trình bày Yofina như một **tính năng trong MoMo**.
2. **Pilot:** 4–8 tuần với một đối tác, có nhóm đối chứng ([mục 4.4](#44-cách-đo-thật-pilot-có-nhóm-đối-chứng)).
3. **Mở rộng:** bán white-label cho ngân hàng số và công ty tài chính có sản phẩm trả sau.

## 3. Giá trị tạo ra và bên hưởng lợi

| Bên | Giá trị | Cách quy ra tiền | Liên quan |
|---|---|---|---|
| **Người dùng** | Biết trước lúc thiếu tiền, không bị phí bất ngờ, ít nhập tay | Ít phí trễ hạn hơn; ít phải vay nóng | P1–P5 |
| **Ví điện tử** | Người dùng mở app thường xuyên hơn và ở lại lâu hơn; tính năng khác biệt | Giữ chân nhiều hơn × doanh thu trung bình mỗi người dùng; doanh thu gói nâng cao | KPI "người dùng quay lại" |
| **Bên cho vay trả sau** | Khách trả đúng hạn hơn, ít khiếu nại phí | Giảm tỷ lệ trễ hạn × dư nợ × tỷ lệ tổn thất; giảm chi phí thu hồi nợ | Proposal §6: giả thuyết, cần pilot |
| **Ngân hàng** | Giữ tiền gửi, bán chéo tiết kiệm và bảo hiểm **sau khi hũ đệm đã đạt mục tiêu** | Biên lợi nhuận tiền gửi; hoa hồng bán chéo (chỉ khi qua luật phù hợp BR-42, BR-65, BR-68; xem R7) | Personetics định vị tương tự [N3] |
| **Đội rủi ro, CSKH** | Lời khuyên truy vết được; ít ticket về khoản trừ không rõ | Giảm số ticket × chi phí mỗi ticket | FR11, FR15 |

## 3a. Nguồn thu cụ thể khi triển khai B2B2C (bổ sung 24/11)

### Nguồn thu của Yofina

| # | Nguồn thu | Ai trả | Đơn vị tính | Bắt đầu từ | Phụ thuộc KPI | Ràng buộc |
|---|---|---|---|---|---|---|
| R1 | **Phí bản quyền nền** | Ví hoặc ngân hàng đối tác | Mỗi người dùng hoạt động/tháng (MAU), theo bậc gói (mục 5.2) | Năm đầu (M2), sau pilot | K1 (độ phủ), K3 (giữ chân) | Phải ≤ giá trị đối tác nhận được (điểm hòa vốn, [08 mục 3.8](08-kpi-kinh-doanh.md#38-k9-roi-của-đối-tác-tính-bằng-điểm-hòa-vốn)) |
| R2 | **Phí theo lượt AI vượt hạn mức** | Đối tác | Mỗi lượt hỏi "nếu thì", đọc ảnh, sinh lộ trình vượt hạn mức kèm gói | M2 | K7 (chi phí AI trên doanh thu) | Giá ≥ chi phí model × (1 + biên). Bảo vệ biên lợi nhuận khi người dùng hỏi nhiều |
| R3 | **Chia doanh thu gói nâng cao** | Người dùng cuối trả cho ví; ví chia lại cho Yofina | % doanh thu gói Thông minh và Chuyên sâu | M2 | K8 (tỷ lệ chuyển sang trả phí) | Gói nâng cao không được bán thêm tính năng an toàn (mục 5.2) |
| R4 | **Phí theo kết quả** | Bên cho vay trả sau | % phần tổn thất trễ hạn giảm được, đo so với nhóm đối chứng | Pilot (M1) → năm đầu | K4, K4-R | Chỉ tính khi tổng phí của người dùng không tăng (K4-R). Phải có nhóm đối chứng để đo |
| R5 | **Phí triển khai một lần** | Đối tác | Theo dự án: tích hợp dữ liệu giao dịch, nạp biểu phí của từng sản phẩm tín dụng vào `fee_schedules`, hiệu chỉnh mô hình trên dữ liệu đối tác | Khi ký hợp đồng | — | Thu đủ chi phí, không đặt lợi nhuận chính ở đây |
| R6 | **Gói giám sát cho đội rủi ro và tuân thủ** | Đội rủi ro của đối tác | Phí cố định/tháng: bảng vận hành, trace, báo cáo số lần luật chặn, xuất bằng chứng kiểm toán (FR15) | Năm đầu | NFR-31 đến 33 | Bán kèm gói Doanh nghiệp |
| R7 | **Phí giới thiệu sản phẩm tích lũy phù hợp** | Ngân hàng, công ty bảo hiểm đối tác | Mỗi tài khoản tiết kiệm hoặc hợp đồng bảo hiểm mở qua gợi ý | Sau năm đầu | Không phải KPI chính | **Chỉ qua cổng phù hợp**: hũ đệm đã đủ (BR-65, BR-68), không nêu sản phẩm đầu tư cụ thể (BC-03), **ghi rõ "có hoa hồng"** ngay trên gợi ý |

**Không làm (loại trừ có chủ đích):**
- **Hoa hồng giới thiệu khoản vay hoặc tăng hạn mức.** Xung đột trực tiếp với BR-42 ("không khuyên vay để tiêu"). Đây cũng là bài học từ Cleo ([06 mục 1](#1-đề-xuất-ngắn)).
- **Bán hoặc chia sẻ dữ liệu cá nhân, kể cả dạng hồ sơ hành vi.** Trái với Luật Bảo vệ dữ liệu cá nhân và với nguyên tắc thu thập tối thiểu (BC-06).
- **Quảng cáo trong luồng tư vấn.** Làm mất lý do tồn tại của bảng "Vì sao".

### Giá trị đối tác nhận được (lý do để đối tác trả tiền)

| Đối tác | Đầu lợi | Cách quy ra tiền | Căn cứ |
|---|---|---|---|
| **Ví** | Người dùng ở lại lâu hơn; có tính năng khác biệt mà đối thủ chưa có ([09](09-phan-tich-doi-thu.md)); **tiền nằm lại trong ví lâu hơn** nhờ hũ có số dư riêng (giả thuyết) | Δ giữ chân × doanh thu mỗi người dùng; Δ số dư lưu ví | K3, K1 |
| **Bên cho vay trả sau** | Ít nợ quá hạn, ít phải thu hồi, ít khiếu nại phí | Δ tỷ lệ trễ hạn × dư nợ × (tổn thất + chi phí thu hồi) | K4; bằng chứng RCT ([08 mục 3.4](08-kpi-kinh-doanh.md#34-k4-và-k4-r-giảm-phí-trễ-hạn-ít-nhất-10-tổng-phí-không-tăng)) |
| **Ngân hàng** | Tiền gửi từ hũ đệm và hũ dài hạn; khách hàng trẻ gắn bó sớm | Biên lợi nhuận tiền gửi; giá trị trọn đời của khách | R7, BR-68 |

**Một điểm trừ của bên cho vay phải nói thẳng:** phí chậm trả là nguồn thu của họ (MoMo công bố 5,25–21% dư nợ quá hạn; [09](09-phan-tich-doi-thu.md)). Giảm trễ hạn nghĩa là **giảm phần thu này**. Lập luận để thuyết phục: tổn thất nợ xấu, chi phí thu hồi và rủi ro uy tín lớn hơn phần phí đó; và xu hướng quản lý trong khu vực đang siết phí trả sau (Thái Lan rà soát trần phí, [01 mục 7](01-boi-canh-thi-truong.md#7-bối-cảnh-pháp-lý-đầu-vào-cho-ràng-buộc-nghiệp-vụ)). Đây là chỗ R4 (phí theo kết quả) quan trọng: Yofina chỉ được trả khi phần lợi ròng là thật. Phân tích đủ ở [10-tac-dong-stakeholder.md](10-tac-dong-stakeholder.md).

### Ví dụ cơ cấu doanh thu năm đầu

**Mọi số là giả định để thấy cách ghép các nguồn thu, không phải dự báo.**

| Giả định | Giá trị |
|---|---|
| Người dùng trả sau của đối tác | 2.000.000 (quy mô Ví Trả Sau MoMo tự công bố) |
| Độ phủ năm đầu (K1) | 15%, tức **300.000 MAU** |
| Phí nền R1 | 1.500 ₫/MAU/tháng (dưới mức hòa vốn khoảng 2.000 ₫ ở file 08) |
| Chuyển sang gói trả phí (K8) | 3%, tức 9.000 người × 25.000 ₫/tháng; Yofina nhận 30% |
| Phí theo kết quả R4 | 20% phần tổn thất giảm được. Với trễ hạn giảm 1 điểm % thì giá trị khoảng 2.000 ₫/người/tháng (file 08), nên R4 khoảng 400 ₫/người/tháng |

| Nguồn | Mỗi tháng | Tỷ trọng |
|---|---|---|
| R1 phí nền | 300.000 × 1.500 = **450 triệu ₫** | khoảng 68% |
| R3 chia doanh thu gói | 9.000 × 25.000 × 30% = **67,5 triệu ₫** | khoảng 10% |
| R4 phí theo kết quả | 300.000 × 400 = **120 triệu ₫** | khoảng 18% |
| R2, R6 (ước lượng thô) | khoảng **25 triệu ₫** | khoảng 4% |
| **Tổng** | **khoảng 660 triệu ₫/tháng (khoảng 7,9 tỷ ₫/năm)** | 100% |

Cách đọc ví dụ này:
- **R1 là nền, nhưng phụ thuộc hoàn toàn vào việc đối tác thấy giá trị.** Vì vậy R4 dù nhỏ lại là bằng chứng quan trọng nhất khi gia hạn hợp đồng.
- **R3 nhỏ**, đúng với thực tế người Việt ít trả phí cho app. Không nên xây kế hoạch tài chính dựa vào R3.
- Chi phí đối ứng (AI, hạ tầng, tích hợp) phải trừ đi để ra biên lợi nhuận, xem K6, K7 ở [08](08-kpi-kinh-doanh.md).

## 4. Chỉ số đo lường

Mục này định nghĩa **cách đo**. Con số mục tiêu kèm benchmark và căn cứ nằm ở [08-kpi-kinh-doanh.md](08-kpi-kinh-doanh.md).

### 4.1 Người dùng mới (thu hút và kích hoạt)

| Chỉ số | Công thức | Ý nghĩa | Lấy dữ liệu ở đâu |
|---|---|---|---|
| **Người dùng mới** | Số người lần đầu mở Yofina trong kỳ | Độ rộng của phễu | Sự kiện đăng nhập lần đầu (Cognito, hoặc ID người dùng của ví khi tích hợp) |
| **Tỷ lệ kích hoạt** | Số người hoàn thành onboarding (lương + ngày nhận) ÷ người dùng mới | Onboarding có đủ nhẹ không. Chỉ có 2 trường bắt buộc (BR-01) | Bảng `users`, `jars` (đã có) |
| **Thời gian tới giá trị đầu tiên** | Thời gian từ lúc mở app tới lúc thấy dự báo ngày cạn đầu tiên | Thấy "aha" ngay trong phiên đầu | Mốc thời gian onboarding và `forecast_runs` (đã có) |
| **Tỷ lệ chạm tính năng lõi** | Số người dùng ít nhất một trong các tính năng xem dự báo, hỏi "nếu thì", kiểm tra trước khi chi trong 7 ngày ÷ số người kích hoạt | Có dùng phần khác biệt hay chỉ xem số dư | Trace và nhật ký sự kiện (cần thêm, xem 4.5) |
| **Tỷ lệ tiếp cận** (khi nằm trong ví) | Người dùng mới ÷ người dùng ví thấy lối vào | Vị trí lối vào trong ví có tốt không | Dữ liệu của đối tác |

### 4.2 Người dùng quay lại (giữ chân)

| Chỉ số | Công thức | Mốc tham chiếu | Lấy dữ liệu ở đâu |
|---|---|---|---|
| **Giữ chân theo nhóm ngày** (D1, D7, D30) | Số người của nhóm bắt đầu ngày X còn hoạt động ở ngày X+N ÷ quy mô nhóm | App tài chính: D1 khoảng 28–30%, D30 khoảng 7–12% (UXCam 7%, số Adjust 11,6%) [N1]. Mục tiêu đề xuất: **D30 ≥ 15%**, tức vượt mức trung bình ngành | Nhật ký phiên |
| **Giữ chân theo tuần** (W1, W4, W8) | Như trên, theo tuần | Hợp với nhịp dùng của công cụ kế hoạch hơn số theo ngày | Nhật ký phiên |
| **Độ gắn bó** (WAU/MAU) | Người dùng hoạt động trong tuần ÷ trong tháng | Cao nghĩa là dùng đều, không chỉ dùng quanh ngày lương | Nhật ký phiên |
| **Quay lại nhờ nhắc** | Số phiên mở từ thẻ chủ động hoặc bản tin ÷ số lần nhắc đã gửi | Nhắc có giá trị hay làm phiền (BR-60) | Bảng `nudges` (phase 5) |
| **Tỷ lệ gợi ý được chấp nhận** | Số gợi ý được bấm chấp nhận ÷ số gợi ý đã hiện | Lời khuyên dùng được (KPI proposal §6) | `audit_events`, `feedback` |
| **Giữ chân qua kỳ lương** | Số người còn dùng sau lần lương về thứ 2 ÷ số người kích hoạt | Chỉ số riêng cho Yofina: công cụ kế hoạch phải sống qua ít nhất một chu kỳ lương | Nhật ký phiên và `salary_events` |

**Chỉ số "Bắc Đẩu"** (đề xuất): **số người dùng mỗi tuần có ít nhất một hũ được cảnh báo trước và tránh được hụt** (không có hũ nào âm trước kỳ lương). Chỉ số này gộp cả giữ chân lẫn giá trị thật cho người dùng.

### 4.3 ROI

ROI tính theo hai góc: ROI của **đối tác** khi mua Yofina (đây là thứ cần thuyết phục), và hiệu quả kinh tế của **chính Yofina** khi bán.

**a) ROI của đối tác**

```
ROI = (Giá trị tăng thêm − Chi phí Yofina) ÷ Chi phí Yofina

Giá trị tăng thêm/tháng =
    ΔTỷ lệ trễ hạn × Dư nợ trả sau × (Tỷ lệ tổn thất + Chi phí thu hồi)    ← bên cho vay
  + ΔTỷ lệ giữ chân × Số người dùng × Doanh thu/người dùng/tháng           ← ví
  + ΔSố tài khoản tiết kiệm mở mới × Biên lợi nhuận mỗi tài khoản           ← ngân hàng
  + ΔSố ticket CSKH × Chi phí mỗi ticket                                     ← vận hành
  + Doanh thu gói nâng cao (phần đối tác giữ lại)

Chi phí Yofina/tháng = Phí bản quyền + Chi phí AI theo lượt dùng + Chi phí tích hợp (chia theo tháng)
```

Mỗi biến "Δ" là chênh lệch giữa **nhóm dùng Yofina** và **nhóm đối chứng** trong pilot. Không lấy chênh lệch trước–sau, vì kết quả sẽ lẫn mùa vụ và kỳ lương.

**Ví dụ minh họa** (mọi số là giả định để thấy cách tính, **không phải dự báo**). Một đối tác có 100.000 người dùng trả sau, dư nợ trung bình 2 triệu ₫/người, tức tổng dư nợ 200 tỷ ₫:

| Biến | Giả định |
|---|---|
| Tỷ lệ trễ hạn giảm | 1 điểm % |
| Chi phí mỗi khoản trễ (tổn thất và thu hồi) | 10% dư nợ trễ (gần chi phí tín dụng ngành 11,5%, FiinGroup; [11 mục 5a](11-can-bang-chi-phi-va-loi-ich.md)) |
| Giá trị một tháng | 200 tỷ × 1% × 10% = **200 triệu ₫/tháng** |

Như vậy, chi phí Yofina dưới 200 triệu ₫/tháng cho nhóm này là có lãi, chưa tính lợi ích giữ chân. **Cần thay bằng số thật của đối tác.**

**c) Phần CSKH: quy ra tiền (bổ sung 24/11)**

Công thức đã có dòng `ΔSố ticket CSKH × Chi phí mỗi ticket` nhưng chưa có mốc. Cách lập mốc và tính:

```
Tiết kiệm CSKH/tháng = Số người dùng × (Tỷ lệ ticket nhóm đối chứng − Tỷ lệ ticket nhóm Yofina) × Chi phí mỗi ticket

Tỷ lệ ticket = số ticket thuộc nhóm chủ đề "phí trả sau, khoản trừ không rõ, hạn trả, số dư" ÷ 1.000 người dùng/tháng
Chi phí mỗi ticket = (lương + phụ cấp + công cụ + quản lý của đội CSKH) ÷ số ticket đã xử lý   ← lấy từ đối tác
```

- **Mốc hiện tại:** lấy tỷ lệ ticket của 3 tháng trước pilot, cùng nhóm chủ đề, ở nhóm người dùng trả sau. Không có số này thì không chứng minh được gì, nên đây là dữ liệu đầu tiên cần xin đối tác (H-01).
- **Benchmark tham khảo:** Gartner đưa trung vị **13,50 USD mỗi lượt có người hỗ trợ** so với **1,84 USD mỗi lượt tự phục vụ** ([Gartner](https://www.gartner.com/en/documents/5164231)). Số này chủ yếu từ doanh nghiệp quốc tế, **không áp được cho Việt Nam**, chỉ cho thấy chênh lệch khoảng 7 lần giữa hai kênh.

**Ví dụ minh họa** (mọi số là giả định):

| Biến | Giả định |
|---|---|
| Người dùng hoạt động | 300.000 (như mục 3a) |
| Ticket về phí, khoản trừ, hạn trả | 20 trên 1.000 người dùng/tháng, tức 6.000 ticket |
| Yofina giảm | 20%, tức 1.200 ticket/tháng |
| Chi phí mỗi ticket | 40.000 ₫: lương CSKH 8–12 triệu ₫/tháng ([CareerLink 2026](https://www.careerlink.vn/cam-nang-viec-lam/tu-van-nghe-nghiep/bo-phan-cham-soc-khach-hang)), cộng khoảng 30% chi phí kèm theo, chia khoảng 325 ticket mỗi người mỗi tháng (**giả định**) |
| **Tiết kiệm** | **48 triệu ₫/tháng**, khoảng 160 ₫/người dùng/tháng |

**Cách đọc:** phần CSKH **dễ chứng minh nhưng nhỏ**, chỉ khoảng 10% của phí nền R1 (1.500 ₫/người dùng/tháng). Nên dùng nó làm **bằng chứng sớm** trong pilot (đo được sau vài tuần, không phải chờ chu kỳ nợ), chứ không làm trụ cột ROI. Trụ cột vẫn là giảm tổn thất trễ hạn (mục a, [11 mục 5](11-can-bang-chi-phi-va-loi-ich.md#5-bên-cho-vay-có-lời-ròng-không-điểm-hòa-vốn)) và giữ chân.

**d) Có nên tính "cắt nhân sự CSKH nhờ AI" vào ROI không? (bổ sung 24/11)**

**Đề xuất: không.** Tính phần CSKH là **chi phí tránh được và giờ công giải phóng**, rồi chuyển giờ công đó sang việc có giá trị cao hơn.

*Yofina giảm nguyên nhân sinh ticket, không thay người trả lời ticket.* Yofina làm cho người dùng ít gặp phí bất ngờ, nên ít phải hỏi. Đó là **giảm cầu**. Một chatbot CSKH thay nhân viên là **thay cung**, là sản phẩm khác, ngoài phạm vi của Yofina.

*Chuyển chi phí nhân công thành chi phí AI thay đổi mô hình kinh doanh thế nào:*

| Khía cạnh | Chi phí nhân công CSKH | Chi phí AI thay thế | Ảnh hưởng tới Yofina |
|---|---|---|---|
| Tính chất | Cố định theo đầu người, trả bằng VND | **Biến đổi theo lượt dùng**, giá model tính bằng USD | Biên lợi nhuận phụ thuộc giá model, tỷ giá và quota (BC-11). Phải có R2 (phí lượt AI vượt hạn mức) để không lỗ khi dùng tăng vọt |
| Vị trí trong sổ sách của đối tác | Chi phí vận hành của đội CSKH | Phí trả nhà cung cấp | Nếu Yofina được định vị là "công cụ cắt người", phí của Yofina bị đem so với quỹ lương CSKH và **bị ép giá** mỗi lần đối tác cắt giảm. Định vị theo giá trị giảm tổn thất thì neo giá cao hơn |
| Chi phí mới phát sinh | — | **Chi phí giám sát AI**: người duyệt luật và ngưỡng, đánh giá chất lượng, xử lý ngoại lệ, kiểm toán | Đây chính là "loại chi phí riêng biệt" mà nhân công chuyển thành. Yofina có thể bán phần này thành R6 (gói giám sát) |
| Pháp lý | — | Bộ luật Lao động 2019 (45/2019/QH14): cho nghỉ việc vì thay đổi công nghệ phải có phương án sử dụng lao động (Điều 42) và trả trợ cấp mất việc (Điều 47). Luật Bảo vệ quyền lợi người tiêu dùng 2023 yêu cầu tiếp nhận và giải quyết khiếu nại. Luật Trí tuệ nhân tạo: con người giữ quyền kiểm soát (BC-04) | Phần "tiết kiệm từ cắt người" bị trừ đi chi phí trợ cấp và vẫn phải giữ kênh người thật cho khiếu nại |
| Uy tín | — | Truyền thông "AI thay người" | Rủi ro với giám khảo và cơ quan quản lý (S6) |

*Bằng chứng từ thị trường:*
- Chỉ **21%** lãnh đạo CSKH cho biết đã giảm nhân sự vì AI; ở nhóm có giảm, mức giảm bình quân 16,7% trong 18 tháng ([Gartner, 05/11/2026](https://www.gartner.com/en/newsroom/press-releases/2026-11-05-gartner-survey-finds-21-percent-of-service-and-support-leaders-have-reduced-human-agent-headcount-because-of-ai)).
- Gartner dự báo đến 2027, **50%** tổ chức định cắt mạnh nhân sự CSKH nhờ AI sẽ bỏ kế hoạch ([06/2025](https://www.gartner.com/en/newsroom/press-releases/2025-06-10-gartner-predicts-50-percent-of-organizations-will-abandon-plans-to-reduce-customer-service-workforce-due-to-ai)), và **một nửa** công ty đã cắt sẽ tuyển lại người cho việc tương tự dưới tên khác ([02/2026](https://www.gartner.com/en/newsroom/press-releases/2026-02-03-gartner-predicts-half-of-companies-that-cut-customer-service-staff-due-to-ai-will-rehire-by-2027)).
- **Klarna**, một công ty trả sau, từng nói trợ lý AI làm việc của 700 nhân viên (02/2024), rồi đến 05/2025 CEO thừa nhận chạy theo cắt chi phí đã đi quá xa, chất lượng giảm, và tuyển lại người ([Entrepreneur](https://www.entrepreneur.com/business-news/klarna-ceo-reverses-course-by-hiring-more-humans-not-ai/491396), [CX Dive](https://www.customerexperiencedive.com/news/klarna-reinvests-human-talent-customer-service-AI/747586/)). Đây là bài học cùng ngành, rất sát với MoMo.

*Hướng chuyển hóa nên đề xuất: từ "trả lời ticket" sang "hỗ trợ trước hạn".*

Giờ công CSKH giải phóng được dùng cho một vai trò mới: **gọi hoặc nhắn hỗ trợ người dùng mà Yofina dự báo sắp hụt nghĩa vụ lớn** (BR-77 đề xuất). Lý do:
- Can thiệp trước hạn rẻ hơn thu hồi nợ sau hạn, nên chi phí nhân công lúc này **tạo ra giá trị** cho bên cho vay (giảm `p_mất` và `c_thu_hồi`, [11 mục 5](11-can-bang-chi-phi-va-loi-ich.md#5-bên-cho-vay-có-lời-ròng-không-điểm-hòa-vốn)), thay vì chỉ là chi phí cần cắt.
- Đúng tinh thần con người quyết định: AI phát hiện, người hỗ trợ ở ca khó, người dùng tự chọn.
- Không có rủi ro pháp lý và uy tín của việc cắt người.

**b) Hiệu quả kinh tế của Yofina (unit economics)**

| Chỉ số | Công thức | Lấy dữ liệu ở đâu |
|---|---|---|
| **Chi phí AI mỗi lượt hội thoại** | Tổng (token vào × giá + token ra × giá) theo từng model trong lượt | **Đã có:** `yofina_core.llm` ghi số token mỗi lần gọi; giá lấy ở trang giá Bedrock. Đo ở phase 6 (NFR-37) |
| **Chi phí AI mỗi người dùng hoạt động/tháng** | Số lượt mỗi người dùng/tháng × chi phí mỗi lượt, tính riêng từng loại (dự báo, kiểm tra trước khi chi, "nếu thì", đọc ảnh) | Trace và bảng `yofina-usage` |
| **Chi phí hạ tầng mỗi người dùng/tháng** | (Aurora + Lambda + Runtime + lưu trữ) ÷ số người dùng | AWS Cost Explorer có tag `project=yofina` |
| **Biên lợi nhuận gộp** | (Doanh thu − chi phí AI − chi phí hạ tầng) ÷ doanh thu | Mục tiêu đề xuất: ≥ 70% ở gói Cơ bản |
| **Tỷ lệ chuyển sang gói trả phí** (nếu bán gói cho người dùng cuối) | Số người trả phí ÷ số người kích hoạt | Mốc tham chiếu: freemium khoảng 2,1% sau 35 ngày (RevenueCat), app tài chính khoảng 4% [N5] |

### 4.4 Cách đo thật: pilot có nhóm đối chứng

Trong cuộc thi chỉ có dữ liệu mô phỏng, nên **không đo được** giữ chân và ROI thật (proposal §6 đã ghi như vậy). Những gì đo được ngay trong cuộc thi:

- Chi phí AI mỗi lượt và độ trễ (đo trực tiếp từ trace).
- Số ngày cảnh báo trước khi hũ cạn và tỷ lệ cảnh báo đúng (backtest trên 3 persona).
- Mô phỏng phí trễ hạn có và không có trợ lý.

Thiết kế pilot đề xuất:

| Hạng mục | Đề xuất |
|---|---|
| Đối tượng | Người dùng 18–30 có dùng trả sau, của một đối tác |
| Chia nhóm | Chia ngẫu nhiên: nhóm dùng Yofina và nhóm đối chứng không dùng |
| Thời gian | 8 tuần, để qua **ít nhất 2 kỳ lương** |
| Chỉ số chính | Tỷ lệ trễ hạn; giữ chân W4, W8; phí phát sinh mỗi người mỗi tháng |
| Chỉ số phụ | Tỷ lệ gợi ý được chấp nhận; số ticket CSKH; số tài khoản tiết kiệm mở mới |
| Cỡ mẫu | Tính theo mức chênh muốn phát hiện. Ví dụ, để phát hiện trễ hạn giảm từ 8% xuống 7% (độ tin cậy 95%, power 80%) cần khoảng **11.000 người mỗi nhóm**; muốn phát hiện mức giảm 2 điểm % thì cần khoảng 2.700 người mỗi nhóm. Tính lại với số thật của đối tác |
| Quyền riêng tư | Xin đồng ý; dữ liệu theo Luật BVDLCN (BC-06) |

### 4.5 Dữ liệu cần bổ sung vào sản phẩm

Hiện chưa có **nhật ký phiên và sự kiện sản phẩm** (mở app, xem màn hình, bấm nút), nên chưa tính được giữ chân. Đề xuất thêm vào phase 5:

- Bảng `product_events`, gồm: người dùng, sự kiện, màn hình, thời điểm, phiên. Không lưu nội dung giao dịch.
- Một màn chỉ số trong bảng vận hành (FR15): phễu kích hoạt, giữ chân theo nhóm, chi phí AI mỗi người dùng.

## 5. Chia gói theo mức dùng AI

### 5.1 Chi phí theo từng tính năng

Gói được chia theo **loại chi phí** của từng tính năng trong kiến trúc hiện tại ([overview](../architecture/overview.md)):

| Mức chi phí | Tính năng | Vì sao |
|---|---|---|
| **Rất thấp** (không gọi LLM) | Hũ, sổ cái, chia lương; dự báo ngày cạn (chạy batch đêm, Monte Carlo khoảng 0,65 giây mỗi người dùng); thẻ chủ động; nhắc hạn | Engine tất định, tính sẵn, đọc từ DB |
| **Thấp** (model nhỏ, 1–2 lượt) | Kiểm tra trước khi chi (engine quyết định, model nhỏ viết 2 câu); hỏi nhanh số dư, giao dịch; phân loại giao dịch (chủ yếu bảng tra và embedding) | Theo thiết kế, đường nhanh và kiểm tra trước khi chi không cần LLM để ra số |
| **Trung bình–cao** (model lớn, tối đa 4 lượt) | Hỏi "nếu thì"; bảng "Vì sao" chi tiết; điểm chống chịu và cú sốc | Planner chạy trên Sonnet, kèm mô phỏng |
| **Cao** | Lộ trình tự sửa (Sonnet cộng LP); đọc ảnh và sao kê; bộ nhớ dài hạn và bản tin cá nhân hóa | Model đọc ảnh, lưu trữ, chạy nền |

### 5.2 Ba gói đề xuất

| | **Cơ bản** | **Thông minh** | **Chuyên sâu** |
|---|---|---|---|
| Định vị | "Biết trước" | "Hỏi trước khi chi" | "Có người lập kế hoạch riêng" |
| Hũ có số dư riêng, chia lương, nghĩa vụ trong một lịch | ✅ | ✅ | ✅ |
| Cơ cấu hũ theo mục đích (đệm, quỹ dồn, mục tiêu, dài hạn), bộ hũ mẫu theo giai đoạn sống (BR-63 đến 70) | ✅ (**phần an toàn, không bán thêm**) | ✅ | ✅ |
| Gợi ý chia tiền dư theo thứ tự ưu tiên (BR-65) | ✅ thẻ số liệu | ✅ có giải thích | ✅ |
| Gợi ý chuyển giai đoạn sống (BR-71) | — | ✅ | ✅ gắn vào lộ trình |
| Dự báo ngày cạn, thẻ chủ động, nhắc hạn | ✅ | ✅ | ✅ |
| Kiểm tra trước khi chi (đủ, sát, hụt; tổng chi phí thật) | ✅ thẻ số liệu | ✅ có giải thích và phương án | ✅ |
| Hỏi "nếu thì" | — | ✅ hạn mức N lượt/tháng | ✅ hạn mức cao |
| Bảng "Vì sao" | Bản rút gọn | ✅ | ✅ |
| Điểm chống chịu, 3 cú sốc | — | ✅ | ✅ cú sốc tùy chỉnh |
| Lộ trình tự sửa theo mục tiêu | — | — | ✅ |
| Nạp ảnh, CSV, sao kê | — | Ảnh, hạn mức thấp | ✅ |
| Bộ nhớ dài hạn, bản tin cá nhân hóa | — | — | ✅ |
| Luật phù hợp, xác nhận trước khi ghi | ✅ | ✅ | ✅ (**luôn bật ở mọi gói**) |

Nguyên tắc chia gói:
- **An toàn không bán thêm tiền.** Xác nhận trước khi ghi, luật phù hợp, cảnh báo phí và nhãn AI có ở mọi gói. Nếu gói thấp thiếu những thứ này, người dùng gói thấp sẽ chịu rủi ro, và đó là rủi ro uy tín cho cả đối tác.
- **Gói Cơ bản phải đủ để thấy giá trị.** Gói này chạy gần như không tốn tiền LLM, nên có thể phát cho toàn bộ người dùng ví để tạo phễu.
- **Gói cao bán theo mức dùng AI**, có hạn mức lượt mỗi tháng. Hết hạn mức thì quay về thẻ số liệu tất định, vì cơ chế này đã có (trần lượt gọi trong `yofina_core.llm`, NFR-35).

### 5.3 Cách tính giá

**Cho đối tác (B2B2C):**
- **Phí nền theo người dùng hoạt động mỗi tháng**, phân bậc theo gói.
- **Cộng phí theo lượt AI** khi vượt hạn mức đã kèm. Phần này bảo vệ biên lợi nhuận, vì chi phí model tăng theo số lượt.
- Có thể **chia sẻ phần lợi ích đo được**, ví dụ một phần khoản giảm tổn thất trễ hạn trong pilot. Cách này dễ thuyết phục đối tác, nhưng cần đo cẩn thận.

**Cho người dùng cuối** (nếu đối tác bán gói nâng cao):
- Thuê bao tháng. Mốc tham chiếu: Facebook Plus 27.990 ₫/tháng ở Việt Nam [N6]; Cleo từ 5,99 USD/tháng ở Mỹ [N4].
- **Giả thuyết cần thử:** gói Thông minh khoảng 19.000–29.000 ₫/tháng. Mức này phải **thấp hơn rõ** phí dịch vụ trả sau 33.000 ₫/tháng, để câu chuyện "trả ít hơn một tháng phí trả sau để không bao giờ bị phí bất ngờ" có sức thuyết phục.
- Dùng thử 14–30 ngày cho gói cao. Theo RevenueCat, dùng thử 17–32 ngày có tỷ lệ chuyển cao nhất (42,5%) [N5].

**Sàn giá:** giá mỗi người dùng phải ≥ (chi phí AI + chi phí hạ tầng mỗi người dùng) ÷ (1 − biên lợi nhuận mục tiêu). Chi phí AI mỗi người dùng phải đo ở phase 6 rồi mới chốt giá.

## 6. Rủi ro của mô hình

| Rủi ro | Giảm thiểu |
|---|---|
| Ví tự làm tính năng tương tự | Đi trước bằng phần khó sao chép: dự báo có hiệu chỉnh, luật phù hợp, truy vết; đề xuất hợp tác thay vì cạnh tranh |
| Xung đột lợi ích: đối tác cho vay muốn người dùng vay nhiều hơn | Hợp đồng ghi rõ luật phù hợp không tắt được; chỉ số chính là trễ hạn giảm, không phải dư nợ tăng |
| Chi phí AI vượt doanh thu khi người dùng hỏi nhiều | Hạn mức lượt theo gói; tính sẵn bằng batch; model nhỏ cho việc nhỏ (đã có trong kiến trúc) |
| Không chứng minh được ROI | Pilot có nhóm đối chứng; cam kết chỉ số đo được ngay từ hợp đồng |
| Quy định về tư vấn tài chính và AI | Không nêu sản phẩm cụ thể (BC-03), gắn nhãn AI (BC-05), con người quyết định (BC-04) |

## 7. Việc cần chủ dự án quyết

| ID | Câu hỏi | Gợi ý |
|---|---|---|
| D-01 | Chọn hướng chính: B2B2C qua ví, B2B2C qua ngân hàng hay B2C | B2B2C qua ví (MoMo) cho cuộc thi và pilot đầu |
| D-02 | Chỉ số Bắc Đẩu | "Số người mỗi tuần tránh được hụt nhờ cảnh báo trước" |
| D-03 | Tên và ranh giới ba gói | Như mục 5.2; chốt sau khi đo chi phí AI mỗi lượt |
| D-04 | Có đưa mô hình kinh doanh vào slide cuộc thi không, ở mức nào | 1 slide: B2B2C, ba gói, công thức ROI và thiết kế pilot |
| D-05 | Thêm bảng `product_events` để đo giữ chân (phase 5) | Nên thêm; chi phí thấp |
| H-01 | Xin đối tác số ticket theo chủ đề 3 tháng trước pilot và chi phí mỗi ticket | Bắt buộc để có mốc cho phần CSKH (mục 4.3c) |
| H-02 | Có tính "cắt nhân sự CSKH nhờ AI" vào ROI không | Không. Tính chi phí tránh được và giờ công giải phóng (mục 4.3d) |
| H-03 | Có đề xuất vai trò "hỗ trợ trước hạn" cho đội CSKH trong pilot không | Nên, ghép với G3 ở file 11; cần đồng ý chia sẻ dữ liệu (BC-06) |

## 8. Nguồn

| # | Nguồn | Ngày | Ghi chú |
|---|---|---|---|
| N1 | [UXCam: Mobile App Retention Benchmarks by Industry (2026)](https://uxcam.com/blog/mobile-app-retention-benchmarks/); [Panto: Mobile App Retention Statistics 2026](https://www.getpanto.ai/blog/mobile-app-retention-statistics) (dẫn số Adjust 2026) | 2026 | Blog nhà cung cấp công cụ; phương pháp khác nhau, chỉ dùng làm khoảng tham chiếu |
| N2 | [Sacra: Cleo](https://sacra.com/c/cleo) | 05/2026 | Ước tính của bên thứ ba, không phải số công ty công bố |
| N3 | [PYMNTS: Personetics hợp tác Plaid](https://www.pymnts.com/partnerships/2026/personetics-partners-plaid-to-give-banks-deeper-customer-insights/); [Personetics ra mắt Banking Console](https://personetics.com/resource-center/personetics-launches-banking-console-bringing-ai-powered-customer-intelligence-to-the-relationship-managers-desktop/); [AI Fintech Index: Personetics](https://aifintechindex.com/vendors/personetics) | 08–09/2026 | Mô hình bán bản quyền cho ngân hàng; giá không công khai; số khách hàng khác nhau giữa các nguồn |
| N4 | [Toolradar: Cleo pricing](https://toolradar.com/tools/cleo-ai/pricing); [Sacra: Cleo $400M/year](https://sacra.com/research/400m-year-instinct-meets-cashnetusa/) | 10/2026 | Giá gói tại Mỹ; cơ cấu doanh thu là ước tính; vụ FTC chưa đối chiếu nguồn gốc |
| N5 | [RevenueCat: State of Subscription Apps 2026](https://www.revenuecat.com/blog/growth/subscription-app-trends-benchmarks-2026); [ProductGrowth: Freemium benchmarks 2026](https://www.productgrowth.blog/calculators/freemium) | 2026 | Freemium 2,1% sau 35 ngày (mọi ngành); số 4% của app tài chính dùng phương pháp khác |
| N6 | [Sforum: Facebook Plus ra mắt Việt Nam](https://cellphones.com.vn/sforum/facebook-plus-ra-mat-viet-nam) | 2026 | Mốc giá thuê bao tại Việt Nam |
| N7 | [Báo Pháp Luật: Thị trường video trực tuyến, doanh thu thuê bao chững lại](https://doanhnhan.baophapluat.vn/thi-truong-video-truc-tuyen-viet-nam-doanh-thu-thue-bao-chung-lai-nen-tang-noi-dia-chuyen-huong-kinh-doanh.html); [BBW: Vì sao chỉ bán thuê bao là chưa đủ](https://bbw.vn/vi-sao-chi-ban-thue-bao-la-chua-du-voi-ott-tai-viet-nam-58711.html) | 2026 | Tỷ lệ trả phí cho app ở Việt Nam thấp |
| N8 | [VnBusiness: MoMo có lãi 2 năm liên tiếp](https://vnbusiness.vn/momo-co-lai-2-nam-lien-tiep-nhung-bat-ngo-muon-ban-toi-50-co-phan.html); [MoMo Trợ thủ tài chính](https://www.momo.vn/tro-thu-tai-chinh) | 2026 | MoMo lãi sau thuế khoảng 347,5 tỷ năm 2024; Ví Trả Sau do TPBank, MBV, VCBNeo cung cấp, tức MoMo đóng vai trò phân phối |
