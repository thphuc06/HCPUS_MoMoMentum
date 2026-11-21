# Yêu cầu và ranh giới MVP

Nguồn: proposal §4, §5. Bảng đầy đủ tiêu chí chấp nhận của FR/NFR nằm ở [proposal-summary.md §5](../proposal/proposal-summary.md#5-yêu-cầu-chức-năng-fr-và-phi-chức-năng-nfr-5); file này chỉ dùng làm bảng theo dõi nhanh (cột trạng thái do đội cập nhật).

## FR theo mức

| ID | Yêu cầu | Tính năng | Mức | Trạng thái |
|---|---|---|---|---|
| FR1 | Hồ sơ, hũ và sổ cái | nền | MVP | chưa làm |
| FR2 | Phân hũ tự động | nền (pipeline sự kiện) | MVP | chưa làm |
| FR3 | Dự báo theo hũ (P10/P50/P90, 30 ngày) | F1 | MVP | chưa làm |
| FR4 | Quản lý nghĩa vụ | nền, F1, F3 | MVP | chưa làm |
| FR5 | What-if hội thoại (≥ 6 loại kịch bản) | F2 | MVP | chưa làm |
| FR6 | Kiểm tra trước khi quẹt | F3 | MVP | chưa làm |
| FR7 | Điểm chống chịu (0–100, 4 thành phần, 3 cú sốc) | F4 | MVP | chưa làm |
| FR8 | Lộ trình thích ứng | F5 | MVP | chưa làm |
| FR9 | Nạp dữ liệu ngoài ví (ảnh chụp + CSV; PDF là mở rộng) | F6 | MVP một phần | chưa làm |
| FR10 | Hồ sơ hành vi và bộ nhớ | F7, Memory | MVP | chưa làm |
| FR11 | Bảng "Vì sao" | xuyên suốt | MVP | chưa làm |
| FR12 | Suitability và xác nhận | xuyên suốt | MVP | chưa làm |
| FR13 | Bản tin chủ động | F7 | Mở rộng | — |
| FR14 | Cảnh báo khoản chuyển lệch thói quen | phụ | Mở rộng | — |
| FR15 | Bảng vận hành cho đội sản phẩm | vận hành | Mở rộng | — |

## Ghi chú từ số đo (2026-11-21)

Yêu cầu của proposal **không đổi**. Bảng dưới chỉ ghi chỗ số đo hoặc spike đã chạy cho thấy có vấn đề hay đã có bằng chứng; mọi dòng **[đã chạy thử]** trừ khi ghi khác, trên dữ liệu thử (ML dùng dữ liệu tổng hợp). Bảng NFR đầy đủ ở [proposal-summary.md §5](../proposal/proposal-summary.md#5-yêu-cầu-chức-năng-fr-và-phi-chức-năng-nfr-5). Tổng hợp số đo: [overview.md](../architecture/overview.md#số-đo-đã-có).

| Mục | Ghi chú | Nguồn |
|---|---|---|
| NFR độ trễ: ký tự đầu dưới 1,5 giây | **Không đạt khi phiên Runtime lạnh**: event đầu 1,8 đến 3,9 s (V1 và V2); phiên ấm khoảng 0,3 s. Có LLM (Haiku 4.5 + 1 tool, V1) lượt đầu của phiên lạnh: chữ đầu 6,55 s (gồm nạp thư viện Strands), lượt hai cùng phiên event đầu 0,33 s. Đề xuất làm nóng phiên khi mở màn hình chat và hiện tiến độ cho lượt đầu | [Runtime §4](../research/spike-agentcore-runtime-cors.md) |
| NFR độ trễ: kiểm tra trước khi quẹt p95 dưới 2 giây (FR6) | **Phần DB đã đo, phần còn lại chưa**: luồng 3 truy vấn qua Data API p95 113 ms (có RLS qua hàm: p95 106 ms); Gateway ấm dưới 200 ms kể cả interceptor và Cedar. Chưa đo: cold start Lambda và Runtime, bước LLM giải thích. Aurora tự pause làm lần gọi đầu mất 16,4 s: không để pause khi chấm điểm | [Aurora §2, §4, §6](../research/spike-aurora-data-api.md), [Gateway §6](../research/spike-agentcore-gateway-identity.md) |
| NFR độ trễ: what-if trọn câu p95 dưới 8 giây (FR5) | Một lượt (router Haiku, planner Sonnet 2 vòng, diễn giải Haiku) đo được 6,3 s trong 3 lượt, **chưa tính** guardrail, KB, Gateway, Aurora, cold start; Claude 4.x chỉ 10 request/phút mỗi model nên không đủ khi nhiều người dùng song song hoặc chạy bộ đánh giá | [Bedrock §2c, §9](../research/spike-bedrock-models.md) |
| NFR độ đúng của số | Số trong khối UI do code dựng từ kết quả tool; LLM chỉ thấy bản gọn. Nhưng các cách phát khối khác để LLM thấy toàn bộ kết quả và nó viết lại thành bảng, nên số trong phần văn bản vẫn cần `NumericGrounding` | [Strands §2.5](../research/spike-strands-agui-local.md) |
| NFR chất lượng dự báo: tốt hơn seasonal naive | Hurdle tự viết và Chronos-2 đạt pinball khoảng 0,55 so với seasonal naive; AutoETS dưới khoảng 60 ngày lịch sử tệ hơn seasonal naive. **Chỉ trên dữ liệu tổng hợp**, hurdle cùng họ với bộ sinh | [ML §3](../research/spike-ml-forecasting.md) |
| NFR chất lượng dự báo: khoảng 80% phủ từ 75% đến 85% (FR3) | **Tổng 30 ngày phủ thiếu ở mọi model**: 0,48 đến 0,61 ở hũ dày, hurdle ở hũ thưa 0,72. Khoảng conformal mặc định của StatsForecast phủ theo ngày chỉ 0,54 đến 0,60; ACI tự viết sửa được (0,61 lên 0,81). Cần xử lý trước khi hiện xác suất hụt cho người dùng | [ML §3, §5](../research/spike-ml-forecasting.md) |
| FR3: xác suất hụt trước kỳ lương | Monte Carlo lấy mẫu độc lập đánh giá thấp khi rủi ro thấp (5,8% thay vì 10% ở hũ ăn uống); cần tương quan giữa các ngày, hũ thưa mô phỏng hurdle trực tiếp | [ML §6](../research/spike-ml-forecasting.md) |
| NFR phân loại: đúng từ 90% (FR2) | Bằng embedding, 1-NN theo hũ đạt 81 đến 84% thô và 93% sau khi chuẩn hóa chuỗi (Cohere v3 và v4) trên 43 chuỗi tự soạn, chưa phải bộ kiểm thử persona. Ngưỡng cosine 0,97 của proposal không hợp lý (gộp nhầm "tiền điện/nước" với "tiền trọ") | [Bedrock §6](../research/spike-bedrock-models.md) |
| FR9: nạp ảnh chụp | Trên 3 ảnh dựng sạch, Sonnet 4.6 và Kimi K3 đọc đúng cả bốn trường; Haiku 4.5 tự sửa sai nội dung không dấu. Ảnh chụp thật, CSV chưa thử. Bedrock Data Automation (cho PDF mở rộng) bỏ vì không liệt kê tiếng Việt (**[đọc tài liệu]**, [bedrock.md](../research/bedrock.md)) | [Bedrock §5](../research/spike-bedrock-models.md) |
| FR12 và NFR bảo mật: xác nhận trước khi ghi; tool mặc định bị từ chối | Cedar mặc định từ chối chạy đúng. Cờ xác nhận trong tham số do LLM điền nên giả mạo được; token xác nhận do server cấp qua 13 ca đúng kỳ vọng. Cơ chế này là **đề xuất, chủ dự án chưa chốt**, khác proposal §9. Dữ liệu tách theo người dùng: interceptor ghi đè `user_id` + Cedar + RLS đều đã chạy | [Gateway §3–§5](../research/spike-agentcore-gateway-identity.md), [Aurora §4](../research/spike-aurora-data-api.md) |
| NFR quyền riêng tư: che thông tin định danh trước khi vào LLM | **[đọc tài liệu]** Guardrails không kiểm kết quả tool và không có mẫu PII Việt Nam: che ở Lambda tool và bước nạp dữ liệu. Chưa tạo guardrail thử. Dữ liệu có thể được xử lý ngoài Singapore vì các model gọi được đều qua profile `global.` (**[đã chạy thử]**) | [bedrock.md](../research/bedrock.md), [Bedrock §2](../research/spike-bedrock-models.md) |
| NFR độ tin cậy: LLM lỗi vẫn trả thẻ số | Lỗi ném giữa luồng SSE là HTTP 200 với thân rỗng, không có `RUN_ERROR`: UI phải coi luồng rỗng hoặc đứt là lỗi. Structured output không đặt `structured_output_attempts` có thể lặp không dừng. Graph của Strands không rẽ lỗi (**[đọc tài liệu]**, [strands-agui.md](../research/strands-agui.md)): F3 viết bằng code tuần tự | [Runtime §1](../research/spike-agentcore-runtime-cors.md), [Strands §2.2](../research/spike-strands-agui-local.md) |
| NFR giải thích và kiểm toán: 100% lượt có trace (FR11) | `trace_id` do client sinh bằng `traceparent` và được giữ nguyên tới app. Span trong CloudWatch chưa xem được (chưa bật Transaction Search) | [Runtime §6](../research/spike-agentcore-runtime-cors.md) |
| NFR chi phí: prompt caching cho phần lặp | Haiku 4.5 chỉ cache khi prompt từ khoảng 4.096 token (router ngắn không cache được); Sonnet 4.6 từ khoảng 1.024; Kimi K3 và model open-weight không cache | [Bedrock §4](../research/spike-bedrock-models.md) |

## MVP và mở rộng

- **Làm lát dọc F1, F2, F3 trước** (§13 giảm thiểu rủi ro "phạm vi quá rộng"). Sao kê PDF, bản tin, bảng vận hành là phần mở rộng.
- **Ngoài MVP, đã có hướng thiết kế (§4)**: tự phát hiện khoản định kỳ; nhận diện loại tiền vào; thu nhập không đều (freelancer, tài xế, người bán online); lương về ngân hàng thay vì ví.
- Mở rộng kỹ thuật: Automated Reasoning checks, AgentCore Evaluations và Code Interpreter (§14), contextual bandit cho F7, Chronos-2 ("MVP nếu kịp"; số đo đề xuất để ngoài MVP, **chưa chốt**, xem [open-questions](open-questions.md)).
- Cắt đầu tiên nếu đội 2 người: F6 (§15).

## Giả định scope cần đội xác nhận (§1)

- Web app chạy tốt trên điện thoại, không làm app native.
- Không có API lấy giao dịch thật của MoMo: dùng ví mô phỏng và dữ liệu tự nạp. Lương, chi phí cố định, khoản vay do người dùng tự khai báo; hệ thống không tự đoán.
- Không khuyến nghị mã cổ phiếu hay quỹ cụ thể; chỉ nói điều kiện tiên quyết và tỷ lệ theo nhóm.
- Agent không tự chuyển tiền; mọi thay đổi số dư hũ cần người dùng xác nhận.
- Tài liệu viết bằng tiếng Việt, thuật ngữ kỹ thuật giữ tiếng Anh.

## Nguyên tắc thiết kế xuyên suốt

- LLM không tự tính số; mọi con số đến từ engine tất định hoặc mô hình dự báo qua tool (NFR: 100% số khớp kết quả tool).
- Mọi thay đổi số dư cần người dùng xác nhận (FR12); tool ghi qua Gateway bị Cedar chặn mặc định.
- Mọi gợi ý kèm bảng "Vì sao" và `trace_id` (FR11); luật suitability tất định (nghĩa vụ trước, dự phòng trước đầu tư, không vượt khẩu vị rủi ro, không khuyên vay để tiêu).
- Tiền vào khác lương không tính là thu nhập.
