# Bộ tài liệu BA

Tài liệu nghiệp vụ của Yofina Foresight, bắt đầu soạn ngày 22/11/2026. Mục đích: chủ dự án duyệt, rồi đội technical bám theo khi code.

| File | Nội dung | Mã |
|---|---|---|
| [01-boi-canh-thi-truong.md](01-boi-canh-thi-truong.md) | Thị trường ví điện tử, công cụ hiện có, số liệu và pain point người 18–30, khoảng trống thị trường, bối cảnh pháp lý. Nguồn trong 12 tháng | P1–P7, G1–G7 |
| [02-business-rules.md](02-business-rules.md) | Ràng buộc nghiệp vụ và quy tắc nghiệp vụ, kèm nguồn, trạng thái, tham số cấu hình; danh sách việc cần quyết | BC-xx, BR-xx, C-xx |
| [03-functional-requirements.md](03-functional-requirements.md) | FR1–FR15 chi tiết: user story, luồng chính, ngoại lệ, BR; ma trận truy vết | FR1–FR15 |
| [04-non-functional-requirements.md](04-non-functional-requirements.md) | NFR có chỉ tiêu đo được, cách đo và số đo hiện có | NFR-xx |
| [05-acceptance-criteria.md](05-acceptance-criteria.md) | Tiêu chí nghiệm thu dạng Cho trước / Khi / Thì, kèm trạng thái | AC-FRx-yy |
| [06-mo-hinh-kinh-doanh.md](06-mo-hinh-kinh-doanh.md) | Hướng thương mại hóa (B2C, B2B2C, B2B), chỉ số người dùng mới, giữ chân, ROI và nguồn dữ liệu, chia gói theo mức dùng AI, **7 nguồn thu (R1–R7) và ví dụ cơ cấu doanh thu**, thiết kế pilot | D-xx, R1–R7 |
| [07-dac-ta-luong-hoat-dong.md](07-dac-ta-luong-hoat-dong.md) | Đặc tả luồng hoạt động toàn ứng dụng (20 luồng, sơ đồ Mermaid), máy trạng thái, phân tích human-in-the-loop, gợi ý bộ diagram | L01–L18 |
| [08-kpi-kinh-doanh.md](08-kpi-kinh-doanh.md) | KPI kinh doanh mục tiêu theo 3 mốc (cuộc thi, pilot, năm đầu), benchmark có nguồn, căn cứ đạt được, điểm hòa vốn ROI, dự phóng chi phí vận hành | K1–K9, E-xx |
| [09-phan-tich-doi-thu.md](09-phan-tich-doi-thu.md) | Phân tích đối thủ CHỈ từ nguồn chính thức (MoMo, ZaloPay, ShopeePay, Viettel Money): hồ sơ, biểu phí trả sau, bảng so sánh với Yofina, ví dụ tổng phải trả, hàm ý định vị | — |
| [10-tac-dong-stakeholder.md](10-tac-dong-stakeholder.md) | Tác động tích cực và tiêu cực lên 6 stakeholder đã chốt (proposal §3), bản đồ ảnh hưởng, ma trận tính năng × stakeholder, xung đột lợi ích, chuỗi tác động | S1–S6, X1–X5, F-xx |
| [11-can-bang-chi-phi-va-loi-ich.md](11-can-bang-chi-phi-va-loi-ich.md) | Pain point chi phí trả sau quy ra mỗi năm; bên cho vay lời từ đâu; 6 đòn bẩy G1–G6 giúp người dùng đỡ tốn mà MoMo và ngân hàng không thiệt; điểm hòa vốn của bên cho vay; BR-74 đến 76 | G1–G6, G-xx |
| [12-tong-hop-va-viec-can-chot.md](12-tong-hop-va-viec-can-chot.md) | Tổng hợp kết luận của 01–11 và mọi câu hỏi đang mở, xếp theo thời điểm cần chốt (demo, slide, pilot, phase 4–5, kiểm trong app) | C-, D-, E-, F-, G-, H-, I-xx |
| [13-tien-do-technical.md](13-tien-do-technical.md) | Bảng điều khiển tiến độ technical: trạng thái FR1–FR15, kịch bản demo, số đo hiện có, việc BA cần báo lại cho technical (T-01 đến T-07), cách cập nhật | T-xx |

**Chuỗi truy vết:** pain point (P) → khoảng trống (G) → FR → BR → AC → tiêu chí trong file phase → test.

**Quy ước:**
- **Cách duyệt.** Chủ dự án sửa trực tiếp, hoặc đổi trạng thái "Đề xuất" và "Cần quyết" thành "Chốt" kèm ngày. Quyết định quan trọng thì ghi thêm vào [open-questions](../requirements/open-questions.md) hoặc thành ADR.
- **Khi lệch với code.** Code đang chạy là hiện trạng, tài liệu này là ý định. Đổi quy tắc thì sửa cả hai, và ghi vào [ai-log](../ai-log/README.md).
- **Quan hệ với tài liệu cũ.** [requirements.md](../requirements/requirements.md) giữ bảng theo dõi nhanh và ghi chú số đo. Phần chi tiết FR, NFR, AC nằm ở đây.
