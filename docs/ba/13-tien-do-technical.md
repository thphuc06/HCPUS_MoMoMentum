# 13. Tiến độ technical theo yêu cầu BA

> **Cập nhật lần cuối: 26/11/2026 tối** (mục 2 và 3 theo HANDOFF "Trạng thái tối 26/11": bản đang chạy `84e21b5`, Runtime v33, kiểm trên app 18:53–19:07; lần trước cùng tối theo `1303eaf`, Runtime v32; trước nữa 26/11 sáng, phần bộ hũ đối chiếu mã ở `c00eec0`). Lần trước 25/11 sáng, đã đối chiếu thêm HANDOFF rạng sáng 25/11 và [kế hoạch phase 6](../plan/phases/phase-6-danh-gia-dong-goi.md) (Runtime v27). Chi tiết lỗi ở mục 4a., đối chiếu với [HANDOFF](../../HANDOFF.md) và mục "Kết quả thực hiện" của [phase 2](../plan/phases/phase-2-vi-va-du-bao.md), [phase 3](../plan/phases/phase-3-what-if-va-kiem-tra.md#kết-quả-thực-hiện), [phase 4](../plan/phases/phase-4-chong-chiu-lo-trinh.md#kết-quả-thực-hiện), [phase 5](../plan/phases/phase-5-nap-du-lieu-ho-so-trace.md#kết-quả-thực-hiện) (Runtime `yofina_agent` v23). **Hạn nộp thật 03/12**; việc của team theo dõi trên GitHub Issues (issue tổng [#2](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/2)).
> File này là **bảng điều khiển** cho BA: xem nhanh yêu cầu nào đã chạy, còn lỗi gì, và việc nào BA cần báo lại cho bên technical. Trạng thái chi tiết từng dòng vẫn nằm ở file gốc (02, 03, 04, 05, 07, 09).

## 1. Bức tranh chung

| Phase | Nội dung | Trạng thái |
|---|---|---|
| 1 | Nền, lát dọc, xác nhận bằng token | Đóng 22/11 |
| 2 | Ví mô phỏng, dự báo | Đóng 22/11 |
| 3 | What-if, kiểm tra trước khi chi, suitability, "Vì sao" | Đóng 23/11 |
| 4 | Điểm chống chịu, lộ trình, phân hũ tự động | Đóng 24/11 |
| 5 | Nạp dữ liệu, hồ sơ hành vi, bộ nhớ, bản tin, trace | **Code xong, đã đo, chưa đóng chính thức** (còn chốt OCR và đi 6 cảnh trên giao diện mới); dự kiến đóng 26/11 |
| 6 | Đánh giá, cứng hóa, đóng gói | **Đã có kế hoạch** (17 tiêu chí, luồng A–K); luồng K "agent như người tư vấn" đã deploy (khối `reasoning` hiện lập luận); đợt 1, đợt 2 (25/11), bộ hũ mặc định, đợt "agent thích ứng", router Claude Haiku 4.5 và 5 lỗi sửa sau lượt kiểm v32 (#39, 26/11, Runtime v32 và v33) đã deploy; eval RC chưa chạy |

**Quyết định kỹ thuật ảnh hưởng tới BA:** đã cắt RAG (24/11). Câu hỏi về phí lấy số từ bảng biểu phí có cấu trúc và kèm trích dẫn, không tìm trong kho tài liệu.

## 2. Theo từng FR

Ký hiệu: ✅ đạt (có bằng chứng) · ◐ chạy được nhưng còn tiêu chí chưa đạt hoặc chưa kiểm trên app · ⏳ chưa làm.

| FR | Tên | | Bằng chứng chính | Còn lại |
|---|---|---|---|---|
| FR1 | Hồ sơ, hũ, sổ cái | ✅ | Đóng phase 2 | Bộ hũ mới **đã code và deploy 26/11** (#39): tài khoản mới 3 hũ mặc định, `purpose`, Quỹ dồn, đề xuất tỷ lệ theo kê khai; ví demo của `minh` 8 hũ. BR-64 một phần (đích tự tính chỉ dùng trong bộ tối ưu); hoãn: BR-68, 70, 71; BR-63 chưa bắt buộc trước hạn nộp (chốt 26/11: hũ để dành cũ có thể chưa có mục đích, nhiều hũ đệm thì lấy hũ đầu tiên theo thứ tự) ([02 B2a](02-business-rules.md#b2a-cơ-cấu-hũ-theo-mục-đích-và-giai-đoạn-sống-đề-xuất-2411)) |
| FR2 | Phân hũ tự động | ◐ | Đủ 4 bước; **đúng 92%** trên phần tự gán (mục tiêu 90%), đo trên ví nhiều hũ theo loại chi | **Tỷ lệ phải hỏi 17,4%** (mục tiêu dưới 10%, NFR-14). Ví 3 hũ: phần có model chưa đo (không model: đúng 92,08%, hỏi 39,52%). Mặt còn lại: khoảng 60% giao dịch cần người dùng chạm (17,4% phải hỏi, 43,1% vào Xem lại; AU-31) |
| FR3 | Dự báo theo hũ | ✅ | Backtest: pinball bằng 0,64 lần mốc so sánh; độ phủ khoảng 80% là 0,79–0,82 ([backtest](../research/backtest-phase-2.md)) | K5 (25/11, [#26](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/26)): báo trước trung vị 13 ngày; đúng ±3 ngày 0,57 (chưa đạt 0,70), đúng "cạn trước lương" 0,82; hơn hai baseline. Ví 3 hũ: dải của hũ gộp Chi hằng ngày phủ thừa (0,865 ở 120 ngày) |
| FR4 | Nghĩa vụ | ✅ | Đóng phase 2 | C-07 chốt 26/11 (hũ trả theo một quy tắc chung) |
| FR5 | What-if | ✅ | Golden 31/31, đủ 6 loại kịch bản; ép lỗi model 6/6; có khối lập luận (luồng K) | Trọn câu 30,3 giây (v33), 20,6 giây (v32) và 28,1 giây (v31) trên app 26/11, 37,9 giây lúc mới thêm lập luận 25/11 (NFR-03 mục tiêu 8 giây); lập luận có lúc nói khác bản đã lưu |
| FR6 | Kiểm tra trước khi quẹt | ◐ | p95 282 ms (mục tiêu 2 giây) | **Dải "sát" (vàng) hẹp và định nghĩa khác BR-36**: hai ngưỡng đều = 0, nên ca hũ Hóa đơn của demo ra "hụt" thay vì "vàng" (C-02); từ 26/11 Hóa đơn gộp vào Nghĩa vụ, ca tương ứng ra "sát" hoặc "hụt" |
| FR7 | Điểm chống chịu | ✅ | `minh` 33/100, 4 thành phần; "Mất việc 2 tháng" 33 → 13, trụ 31 ngày. 26/11 trên app (ví demo 8 hũ, Runtime v31): 29 → 12, trụ 26 ngày (ví 7 hũ rạng sáng: 25 ngày) | Kỹ thuật đã chọn 4 thành phần (xem C-06) |
| FR8 | Lộ trình | ✅ | Golden phase 4 14/14, đối kháng 12/12; lập trong chat 20–26 giây | `period_end` tính theo hôm nay, chưa theo ngày lương |
| FR9 | Nạp ảnh, CSV | ◐ | CSV 50/50; chống trùng; nạp chứng từ ngoại tệ quy đổi VND | OCR ảnh thật 9/11 (v25), r08 đạt ở v26, dự kiến 10/11; chốt ở lượt RC (Q9) |
| FR10 | Hồ sơ hành vi, bộ nhớ | ◐ | `minh` có 3 nhận xét khớp sổ cái; xóa dữ liệu, xóa bộ nhớ chạy; bộ nhớ sửa gốc (Haiku 4.5), golden bộ nhớ đạt | Theo dõi ca `memory-state-preference`; `turn_persist_timeout` |
| FR11 | Bảng "Vì sao" | ✅ | Đi cảnh 2: 4 nguồn, 8 luật, `trace_id`; trace người khác bị từ chối | — |
| FR12 | Suitability, xác nhận | ✅ | 13 ca tấn công token bị chặn; đối kháng 16/16, 12/12, 14/14; **luật thứ bảy `emergency_not_for_discretionary`** đã vá lỗ hổng hũ Dự phòng | Ngưỡng nghĩa vụ trên thu nhập chờ C-03 (T-06) |
| FR13 | Bản tin chủ động | ◐ | Có thẻ chủ động và bản tin ("Hũ Ăn uống dự kiến cạn ngày 23/11"); trên app 26/11 (v31) thẻ chủ động duy nhất là Ăn uống | Nút "Hỏi vì sao" của bản tin sửa sau v31 (vào v32), chưa kiểm lại trên app |
| FR14 | Cảnh báo khoản chuyển lệch thói quen | ⏳ | Không có trong code (phase 5 ghi "nếu kịp", nằm trong thứ tự cắt) | Đề xuất ghi là lộ trình sau cuộc thi |
| FR15 | Bảng vận hành, trace | ◐ | Trace 18 bước qua REST; tài khoản ngoài nhóm `ops` bị từ chối | Mở từ "Vì sao" đã kiểm trên app 26/11 (v31, v32); Transaction Search chưa bật |

## 3. Kịch bản demo

Đi trên app 26/11 với ví demo 8 hũ (`giamkhao1`): sau Runtime v31 (sáng), v32 (chiều) và v33 (tối, bản đang chạy). Số đầy đủ ở [demo-script](../plan/demo-script.md).

| Cảnh | Trạng thái |
|---|---|
| 1. Hũ sắp cạn | Chạy; giao diện mới (thẻ có số ngày, dải ô ngày). 26/11 (v32, v33): Ăn uống cạn 23/11, "Hụt", 12 ngày tới kỳ lương |
| 2. What-if tai nghe 1,2 triệu | Đi trên app 23/11: đạt. 26/11 (v32): trọn câu 20,6 giây, hũ Nghĩa vụ liệt kê Tiền điện 26/11 và Trả sau 05/12 (2.200.000 ₫; đúng ngày lương, trả bằng số dư trước khi lương về), thiếu 1.167.673 ₫ (cục bộ 1.168.392 ₫). v33: trọn câu 30,3 giây, thiếu 1.167.673 ₫ |
| 3. Điểm chống chịu, cú sốc | Đi trên app 24/11: đạt. 26/11 (v31, ví 8 hũ): 29 → 12, trụ 26 ngày |
| 4. Lộ trình | Đi trên app 24/11: đạt. 26/11 (v32): 32 dòng tự thêm vào Ăn uống, Lambda sinh lại 19,6 giây, bản mới kịp hạn, Dự phòng không về 0. v33: Lambda sinh lại 18,9 giây, bản mới 3 giai đoạn, 5 bước, kịp hạn; Dự phòng chuyển 362.000 ₫ sang Ăn uống (như v32), còn 2.338.000 ₫ |
| 5. Nạp ảnh | Đạt qua REST; chờ thử trên điện thoại. 26/11 (v31): màn duyệt sau 8,5 giây, chip "Đã che: tên" |
| 6. Trace | Đạt qua REST. 26/11 (v31, v32): mở từ "Vì sao" → "Chi tiết kỹ thuật" trên app, có số lượt gọi model, token, thời gian từng bước |
| **Cả 6 cảnh liền mạch** (`giamkhao1`) | **Chưa kiểm** (tiêu chí 10 phase 5, việc của Học) |

## 4. Việc BA nên báo lại cho bên technical

**Trạng thái 25/11 sáng:** T-01, T-04 **đã sửa**; T-03, T-05 technical **đã xếp lịch** ở phase 6. Việc còn chờ BA: **T-02** (chốt C-02), **T-06** (chốt C-03), **T-07** (chốt phạm vi demo).

Đây là các chỗ code đang chạy lệch so với quy tắc nghiệp vụ, hoặc cần BA chốt thì kỹ thuật mới sửa được.

| # | Vấn đề | Quy tắc liên quan | Đề xuất |
|---|---|---|---|
| T-01 ✅ **Đã sửa 24/11 khuya** (luật `emergency_not_for_discretionary`) | What-if gợi ý **mua món không thiết yếu bằng hũ Dự phòng**, không luật nào chặn (lỗi còn lại số 2 của phase 5). Gốc: luật `emergency_before_investing` chỉ áp cho khoản loại `investment` | BR-42 (quỹ dự phòng trước đầu tư), BR-64 (hũ đệm là khóa mềm) | Thêm luật suitability: không gợi ý lấy hũ Dự phòng cho khoản không thiết yếu; nếu người dùng tự chọn thì xem trước phải hiện ảnh hưởng tới Điểm chống chịu |
| T-02 → [#30](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/30), hạn trước 1/12 | Dải "sát" (vàng) hẹp: code xếp vàng khi số dư P10 < `affordability_tight_p10_floor_vnd` (= 0), còn BR-36 định nghĩa vàng là "cạn sớm hơn N ngày" | BR-36, C-02 | Chốt C-02 (chọn một định nghĩa) rồi đặt ngưỡng tương ứng |
| T-03 ⏳ Phase 6 việc E7 | Tỷ lệ phải hỏi khi phân loại 17,4% | BR-17, BR-18, NFR-14 | Chốt C-05 (ngưỡng "đủ lớn để hỏi"); kỹ thuật đã có hai hướng giảm |
| T-04 ✅ **Đã sửa 24/11 khuya** (bỏ câu mẫu khỏi `MEMORY_GUIDE`, Runtime v24) | Agent nói "theo điều bạn đã dặn" khi bộ nhớ không có lời dặn đó | BR-59, BR-48 (mọi điều nói ra phải có căn cứ) | Ưu tiên sửa trước buổi chấm: lỗi này làm mất lòng tin |
| T-05 ⏳ Phase 6 việc A4 (Q9: 9/10 ở lượt RC; dự kiến 10/11) | OCR ảnh thật 7/12 (lúc ghi) | BR-56, AC-FR9-04 | Cân nhắc hạ mục tiêu cho demo (chỉ dùng loại ảnh đọc tốt) hoặc ghi rõ giới hạn |
| T-06 | Ngưỡng nghĩa vụ trên thu nhập: code dùng **một ngưỡng 36%** (quy tắc 28/36, `rules/obligation_to_income.yaml`); BA đề xuất hai mức vàng 30%, đỏ 40% | BR-37, C-03 | Nhóm chốt C-03: giữ 36% làm mức đỏ, hoặc tách hai mức |
| T-07 | Cơ cấu hũ mới (BR-63 đến 73) và các quy tắc chi phí trả sau (BR-74 đến 77) **chưa có trong code**. **26/11:** bộ hũ theo mục đích đã làm một phần (#39; trạng thái từng BR ở [02 B2a](02-business-rules.md#b2a-cơ-cấu-hũ-theo-mục-đích-và-giai-đoạn-sống-đề-xuất-2411)); BR-74 đến 77 vẫn chưa có | — | Chốt phạm vi demo: G1 (chi phí quy năm) có thể làm nhanh trong FR6; phần còn lại ghi là lộ trình. **25/11:** được thêm tính năng tới hết 30/11; đề xuất chỉ thêm G1 (chi phí quy năm, BR-75) |
| T-08 (BA ghi 26/11) | **Số phân loại trên slide phải đúng phạm vi ví.** 92% đúng và 17,4% phải hỏi là của **ví nhiều hũ có model** (ví demo). Ví 3 hũ mặc định của tài khoản mới **chưa đo có model**; không model thì hỏi 39,52%, tự gán sai 4,19% ([đo ví ba hũ](../research/2026-11-26-do-vi-ba-hu.md)) | BR-17, NFR-13, NFR-14, E-03 | Slide gắn số với ví demo; chủ dự án quyết có đo ví 3 hũ có model trước 1/12 không (P1 trong ghi chú đo) |

### 4a. Chi tiết từng việc (gửi technical, ghi 25/11)

Đối chiếu trên Runtime `yofina_agent` v23 và code ở `main` ngày 24/11. Mỗi việc có: cách tái hiện, đang ra gì, nghiệp vụ cần gì, nguyên nhân (nếu đã tìm được), gợi ý sửa, và việc BA phải chốt trước.

**T-01 [Ưu tiên cao] What-if gợi ý mua món không thiết yếu bằng hũ Dự phòng** — ✅ **đã sửa 24/11 khuya**: thêm luật suitability thứ bảy `emergency_not_for_discretionary` (warn); kiểm lại what-if tai nghe: phương án hũ Dự phòng không còn được khuyên. Giữ mô tả dưới để đối chiếu.
- **Tái hiện:** `minh` vừa đặt lại, hỏi "Nếu mua tai nghe 1,2 triệu bằng Trả sau thì sao?".
- **Đang ra:** phương án "Mua bằng hũ Dự phòng" được đánh dấu gợi ý (lỗi còn lại số 2, [phase 5](../plan/phases/phase-5-nap-du-lieu-ho-so-trace.md#kết-quả-thực-hiện), lần kiểm 24/11 tối).
- **Nghiệp vụ cần:** hũ Dự phòng là quỹ đệm, không gợi ý tiêu cho khoản không thiết yếu (BR-42, BR-64). Nếu người dùng tự chọn, bản xem trước phải hiện ảnh hưởng tới Điểm chống chịu và số ngày trụ được.
- **Nguyên nhân:** `gateway/tools/planner/rules/emergency_before_investing.yaml` chỉ áp khi `applies_when.categories: [investment]`, nên khoản mua sắm không bị kiểm.
- **Lỗi phụ:** `option_id` là `pay_giai_tri` trong khi nhãn là hũ Dự phòng.
- **Gợi ý sửa:** thêm luật, hoặc mở rộng luật trên, chặn đề xuất lấy hũ có vai trò dự phòng cho khoản không thiết yếu.
- **BA chốt trước:** không cần.

**T-02 [Trung bình] Mức "sát" (vàng) hẹp và định nghĩa khác nghiệp vụ**
- **Tái hiện:** `minh` vừa đặt lại, "Chuyển 250.000 ₫ cho người nhận demo có ổn không?".
- **Đang ra:** hũ Hóa đơn "hụt". AC-FR6-01 mong "vàng". Từ 26/11 hũ Hóa đơn của ví demo gộp vào Nghĩa vụ; ca tương ứng là nêu hũ Nghĩa vụ, test tích hợp chấp nhận "sát" hoặc "hụt".
- **Nguyên nhân:** `pipelines/forecast/yofina_forecast/afford.py` xếp vàng khi số dư kịch bản xấu (P10) dưới `affordability_tight_p10_floor_vnd`; ngưỡng này và `affordability_short_p50_floor_vnd` đều bằng 0 (`settings.py`).
- **Nghiệp vụ cần:** BR-36 định nghĩa vàng là "hũ cạn sớm hơn N ngày so với trước khi chi".
- **Gợi ý sửa:** sau khi BA chốt, chỉ đặt lại ngưỡng trong SSM, hoặc thêm điều kiện theo số ngày cạn sớm.
- **BA chốt trước:** **C-02** (dùng định nghĩa nào, N bằng bao nhiêu).

**T-03 [Trung bình] Tỷ lệ phải hỏi khi phân hũ 17,4% (mục tiêu dưới 10%)** — ⏳ đã vào phase 6, việc E7.
- **Đang ra:** phân hũ đúng 92% (đạt); phải hỏi 17,4% ([phase 4](../plan/phases/phase-4-chong-chiu-lo-trinh.md#kết-quả-thực-hiện), tiêu chí 6).
- **Nghiệp vụ cần:** NFR-14, BR-17, BR-18.
- **Gợi ý sửa (technical đã đề xuất):** bỏ token mẫu QR khỏi chuỗi embedding; giảm trọng số lịch sử khi ghi chú rõ.
- **BA chốt trước:** **C-05**, ngưỡng "khoản đủ lớn mới hỏi". ~~Khoản nhỏ một lần vào hũ "Khác", không hỏi (BR-18).~~ Hũ "Khác" **không làm** (chủ dự án chốt 26/11, issue #28 đóng: đo offline chỉ giảm tối đa khoảng 1,2 điểm).
- **Ví 3 hũ (26/11):** phần có model chưa đo; không model thì phải hỏi 39,52% ([đo ví 3 hũ](../research/2026-11-26-do-vi-ba-hu.md)). Số 17,4% ở trên là của ví nhiều hũ theo loại chi.

**T-04 [Ưu tiên cao] Agent nói "theo điều bạn đã dặn" khi không có lời dặn** — ✅ **đã sửa 24/11 khuya**: gốc là câu mẫu trong `MEMORY_GUIDE` bị model chép lại; bỏ câu mẫu, khối bộ nhớ đưa vào prompt dạng dữ liệu; `memory-reuse-new-session` đạt 2/2 (Runtime v24). Giữ mô tả dưới để đối chiếu.
- **Tái hiện:** golden `memory-reuse-new-session`.
- **Đang ra:** "Theo điều bạn đã dặn, hãy cân nhắc đưa vào hũ Dự phòng." trong khi bộ nhớ không có lời dặn đó. Lần kiểm 2 chỉ đạt 1/2.
- **Nghiệp vụ cần:** mọi điều nói ra phải có căn cứ (BR-48, BR-59).
- **Gợi ý sửa:** xem prompt nhánh trả lời ngắn; chỉ cho nói "theo điều bạn đã dặn" khi có bản ghi sở thích khớp với nội dung câu trả lời.
- **BA chốt trước:** không cần.

**T-05 [Trung bình] Đọc ảnh thật đủ 4 trường 7/12 (mục tiêu 9/10)** — ⏳ đã cải thiện: 9/11 ở Runtime v25, r08 đạt ở v26; chủ dự án chốt Q9 (9/10 đo ở lượt RC, ghi r12 là giới hạn ảnh mờ), việc A4 phase 6.
- **Đang ra:** r08 (màn chi tiết VPBank có số tham chiếu) `no_transactions`; sai ngày ở r12 dòng 2, r15 dòng 8, r24; r15 dòng 9 sai cả bốn trường ([phase 5, mục Tiêu chí 3](../plan/phases/phase-5-nap-du-lieu-ho-so-trace.md#tiêu-chí-3-đánh-giá-lại-sau-kiểm-mù-nhãn-2411)). CSV đạt 50/50.
- **Nghiệp vụ cần:** AC-FR9-04, BR-56.
- **Gợi ý cho demo:** chỉ dùng loại ảnh đọc tốt (như `s02`); ghi rõ giới hạn nếu giám khảo hỏi.
- **BA chốt trước:** có hạ mục tiêu AC-FR9-04 cho bản demo không.

**T-06 [Thấp] Ngưỡng nghĩa vụ trên thu nhập**
- **Đang ra:** `gateway/tools/planner/rules/obligation_to_income.yaml` dùng **một** ngưỡng 36% (quy tắc 28/36). Vượt thì thẻ đỏ "không khuyến khích".
- **BA đề xuất:** hai mức, vàng từ 30%, đỏ từ 40% (C-03).
- **Gợi ý sửa:** chỉ sửa file luật nếu nhóm chọn tách hai mức.
- **BA chốt trước:** **C-03**. Đề xuất 25/11: giữ 36% làm mức đỏ, không sửa code trước demo.

**T-07 [Thông tin] Quy tắc nghiệp vụ mới chưa có trong code**
- **26/11:** bộ hũ theo mục đích **đã làm một phần** (#39; trạng thái từng BR ở [02 B2a](02-business-rules.md#b2a-cơ-cấu-hũ-theo-mục-đích-và-giai-đoạn-sống-đề-xuất-2411)). Vẫn chưa có: chi phí trả sau minh bạch (BR-74 đến 76), hỗ trợ trước hạn (BR-77), FR14 (không làm).
- **26/11 (issue #39):** đã làm BR-67, BR-69 và một phần BR-63, 65, 66, 73, 78 (3 hũ mặc định, `purpose`, Quỹ dồn, đề xuất tỷ lệ theo kê khai, hũ Nghĩa vụ chung); hoãn BR-64, 68, 70, 71; phần còn lại của BR-63 (bắt buộc mục đích, chặn hũ đệm thứ hai) để sau hạn nộp. BR-72, 74 đến 77 và FR14 vẫn chưa có.
- **Đề xuất:** không đưa vào demo, trừ **G1** (hiện chi phí trả sau quy ra năm trên thẻ kiểm tra trước khi chi, BR-75) vì làm nhanh được. Phần còn lại ghi là lộ trình sau cuộc thi.
- **BA chốt trước:** G-01, C-12 (đã đưa vào [12 mục 2.1](12-tong-hop-va-viec-can-chot.md#21-gấp-technical-đang-chờ-chốt-trước-hạn-tính-năng-3011), hạn 30/11).

**T-08 [Trung bình, trước khi khóa slide] Số phân loại của ví 3 hũ** — BA ghi 26/11 từ [ghi chú đo ví ba hũ](../research/2026-11-26-do-vi-ba-hu.md) của Phúc.
- **Số đo (tập kiểm 167 dòng):**

| Trường hợp | Model | Đúng trên mục đã gán | Phải hỏi | Tự gán sai |
|---|---|---|---|---|
| Ví 7 hũ (ví demo) | Có | 92,03% | **17,37%** | 1,80% |
| Ví 7 hũ | Không | 94,29% | 58,08% | 1,20% |
| **Ví 3 hũ** (tài khoản mới) | Không | 92,08% | **39,52%** | **4,19%** |
| Ví 3 hũ | Có | **Chưa đo.** Ước tính giả định: 92,76% | 8,98% | 4,19% |

- **Cách đọc đúng:** so cùng điều kiện (không model), ví 3 hũ **hỏi ít hơn** ví 7 hũ (39,52% so với 58,08%), nhưng **tự gán sai nhiều hơn** (4,19% so với 1,20%). Không được so 39,52% (không model) với 17,4% (có model).
- **Nguồn tự gán sai:** luật "luôn luôn cho người này": người nhận quen bị gộp vào một hũ, rồi khoản trả hóa đơn qua chính người đó bị đưa vào Chi hằng ngày. Người dùng giữ luật như ví 7 hũ thì tự gán sai chỉ 0,60%.
- **Việc cho slide và tài liệu nộp (P0 của ghi chú đo, BA làm):** gắn 92% và 17,4% với **ví demo nhiều hũ**; không nói đó là số của tài khoản mới. Nếu nói về tài khoản mới, dùng số đo không model và ghi "phần có model chưa đo". Báo cả hai mặt như AU-31.
- **Việc cần chủ dự án quyết (P1):** đo ví 3 hũ có model trước đóng băng 1/12 (khoảng 294 lời gọi model nhỏ, khoảng 17 phút). Nếu đo được mức gần 9% thì có số tốt hơn để nói về tài khoản mới (dưới mục tiêu 10% của NFR-14).
- **Sau hạn nộp (P1 của ghi chú đo):** luật người nhận không nên thắng lời nhắn có tín hiệu hóa đơn hoặc nợ.

### 4b. Issue GitHub liên quan tới BA (từ kiểm toán 25/11)

| Issue | Việc | Ai | Hạn |
|---|---|---|---|
| [#30](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/30) | Dải vàng của kiểm tra trước khi chi, **chờ BA chốt C-02** | BA chốt, technical sửa | Trước 1/12 (càng sớm càng kịp đợt 2, 30/11) |
| [#33](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/33) | **Số kinh doanh**: chi phí AI mỗi người dùng hoạt động mỗi tháng đặt cạnh giá; trang "Yofina trong MoMo"; câu kể "AI là phần cốt lõi … AI đề xuất, con người quyết định" | **BA** | Chủ dự án duyệt trước 1/12 |
| [#26](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/26) | Đo K5 hai định nghĩa; sửa ba/08 mục 3.5 | Technical đo; **BA đã sửa 08 mục 3.5 (25/11)** | Đợt 2 |
| [#37](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/37) | Slide tối đa 10 trang, mọi số trỏ được về repo | BA soạn nội dung, chủ dự án duyệt | Nháp 1/12, nộp 3/12 |
| [#36](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/36) | Bộ nộp: README khai tài sản có sẵn, nguồn dữ liệu | Technical; **BA cung cấp danh sách nguồn dữ liệu** (biểu phí, số thị trường) | 3/12 |
| [#32](https://github.com/thphuc06/HCPUS_MoMoMentum/issues/32) | Đồng bộ tài liệu cũ, ADR-0004 "Lệch so với proposal" | Technical; BA đối chiếu FR, NFR | Trước 1/12 |

## 5. Số đo hiện có (cho slide và NFR)

| Chỉ số | Số đo | Mục tiêu | NFR |
|---|---|---|---|
| Kiểm tra trước khi chi | p50 191 ms, p95 282 ms | p95 < 2 giây | NFR-02 ✅ |
| What-if trọn câu | p50 16,7 giây, p95 28,2 giây (23/11); khoảng 37,9 giây khi có khối lập luận (25/11) | p95 < 8 giây | NFR-03 ✗ |
| Lập lộ trình trong chat | 20–26 giây (1 lượt planner) | khoảng 30 giây | — ✅ |
| Số khớp tool (NumericGrounding) | 100% golden phase 3; 91,7% golden phase 5 | 100% | NFR-07 ◐ |
| Dự báo so với mốc so sánh | pinball 0,64 lần seasonal naive | < 1 | NFR-10 ✅ |
| Độ phủ khoảng 80% | 0,79–0,82 (hũ riêng); hũ gộp Chi hằng ngày của ví 3 hũ 0,865, phủ thừa | 0,75–0,85 | NFR-11 ✅ (hũ riêng) |
| K5 cảnh báo đúng | ±3 ngày 0,57 (baseline 0,44–0,49); cạn trước lương 0,82; báo trước trung vị 13 ngày | 0,70 | NFR-12 ◐ |
| Phân hũ đúng | 92% (ví nhiều hũ theo loại chi); ví 3 hũ không model 92,08%, có model chưa đo | ≥ 90% | NFR-13 ✅ |
| Tỷ lệ phải hỏi | 17,4% (ví nhiều hũ); ví 3 hũ không model 39,52%, có model chưa đo | < 10% | NFR-14 ✗ |
| Phát hiện đổi hành vi, cảnh 4 | PELT xác nhận từ hệ số 2,1 (ngưỡng mịn 2,04) trên hũ Ăn uống riêng; chuỗi gộp của ví 3 hũ cần 2,3 (2,27) | — | — |
| Đối kháng | 42 câu qua ba phase, 0 vi phạm | 0 vi phạm trên 50 câu | NFR-33 ◐ |
| Guardrail | p50 446 ms | 400 ms | — ✗ |
| Test | Unit 4506 passed, 4 skipped (`tests/unit` và `libs/yofina_core/tests`, mã ở `c00eec0`, chạy 26/11); vitest 1060, CDK 98 (HANDOFF 26/11, không chạy lại) | — | — |

## 6. Cách cập nhật file này

1. Mỗi khi bên technical **đóng một phase** hoặc ghi HANDOFF mới, đọc mục "Kết quả thực hiện" của file phase đó.
2. Sửa ký hiệu ở mục 2 và số ở mục 5; đổi ngày ở dòng "Cập nhật lần cuối".
3. Sửa cột trạng thái ở file gốc: FR (03, bảng Tổng quan), BR (02, cột Trạng thái), NFR (04, hai cột cuối), AC (05, cột cuối), luồng (07, mục 2), cột Yofina (09, mục 3).
4. Việc ở mục 4 đã sửa thì chuyển dòng xuống cuối và ghi "đã sửa ngày …".
