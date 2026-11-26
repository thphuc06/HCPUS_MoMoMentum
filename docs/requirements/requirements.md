# Yêu cầu và ranh giới MVP

Nguồn: proposal §4, §5. Bảng đầy đủ tiêu chí chấp nhận của FR/NFR nằm ở [proposal-summary.md §5](../proposal/proposal-summary.md#5-yêu-cầu-chức-năng-fr-và-phi-chức-năng-nfr-5); file này chỉ dùng làm bảng theo dõi nhanh (cột trạng thái do đội cập nhật).

> Bản chi tiết (BR, FR có luồng, NFR có chỉ tiêu đo, AC dạng Cho trước/Khi/Thì) ở [../ba/](../ba/README.md). Cột trạng thái bên dưới cập nhật 25/11/2026 theo [ba/13 mục 2](../ba/13-tien-do-technical.md#2-theo-từng-fr) và bảng FR của [kiểm toán proposal so với sản phẩm](../research/2026-11-25-audit-proposal-vs-product.md#bảng-fr1fr15-trạng-thái-trong-tài-liệu-so-với-mã) (đối chiếu với mã). "Làm" là có mã chạy trên AWS. Dòng FR1 đến FR4 bổ sung 26/11 theo bộ hũ mới (issue #39, cuối [B2a](../ba/02-business-rules.md#b2a-cơ-cấu-hũ-theo-mục-đích-và-giai-đoạn-sống-đề-xuất-2411)); "một phần" là còn tiêu chí chưa đạt hoặc chưa kiểm trên app. Lệch so với proposal: [ADR-0004](../decisions/0004-lech-so-voi-proposal.md).

## FR theo mức

| ID | Yêu cầu | Tính năng | Mức | Trạng thái (25/11) |
|---|---|---|---|---|
| FR1 | Hồ sơ, hũ và sổ cái | nền | MVP | Làm (phase 2). 26/11: tài khoản mới nhận 3 hũ mặc định (Chi hằng ngày, Nghĩa vụ, Dự phòng), bước 3 onboarding đề xuất tỷ lệ theo số đã khai; ví demo có thêm hũ tự thêm (`minh` 8 hũ); bộ hũ theo giai đoạn sống hoãn |
| FR2 | Phân hũ tự động | nền (pipeline sự kiện) | MVP | Một phần: đủ 4 bước (phase 4), đúng 92% trên dòng tự gán; phải hỏi 17,4% (mục tiêu dưới 10%); đo trên ví nhiều hũ theo loại chi. Ví 3 hũ: phần có model chưa đo |
| FR3 | Dự báo theo hũ (P10/P50/P90, 30 ngày) | F1 | MVP | Làm (phase 2); % hụt chỉ hiện khi đủ lịch sử (47 ngày hũ dày, 120 ngày hũ thưa, #9; đo trên hũ riêng theo loại chi); dải hiệu chỉnh CQR và PAV (#25). Hũ gộp Chi hằng ngày của ví 3 hũ phủ thừa (0,865) |
| FR4 | Quản lý nghĩa vụ | nền, F1, F3 | MVP | Làm (phase 2). 26/11: hũ Nghĩa vụ chung cho tiền nhà, hóa đơn, vay, Trả sau; hũ trả theo một quy tắc chung (C-07); hũ Nghĩa vụ liệt kê khoản đến hạn trước kỳ lương |
| FR5 | What-if hội thoại (≥ 6 loại kịch bản) | F2 | MVP | Làm (phase 3), đủ 6 loại; độ trễ chưa đạt NFR-03 |
| FR6 | Kiểm tra trước khi quẹt | F3 | MVP | Một phần: chạy (phase 3), nhưng dải "sát" gần như không xảy ra vì hai ngưỡng bằng 0 (chờ C-02) |
| FR7 | Điểm chống chịu (0–100, 4 thành phần, 3 cú sốc) | F4 | MVP | Làm (phase 4) |
| FR8 | Lộ trình thích ứng | F5 | MVP | Làm (phase 4); sinh lại do hành vi chạy thật từ tệp sao kê cảnh 4 (#22) |
| FR9 | Nạp dữ liệu ngoài ví (ảnh chụp + CSV; PDF là mở rộng) | F6 | MVP một phần | Một phần như kế hoạch: CSV và ảnh (phase 5); PDF chưa làm; OCR ảnh thật 9/11 (Runtime v25) |
| FR10 | Hồ sơ hành vi và bộ nhớ | F7, Memory | MVP | Làm (phase 5, chưa đóng phase): hồ sơ hành vi ở Aurora, bộ nhớ AgentCore hai strategy |
| FR11 | Bảng "Vì sao" | xuyên suốt | MVP | Làm (phase 3); trace qua REST (phase 5) |
| FR12 | Suitability và xác nhận | xuyên suốt | MVP | Một phần: token xác nhận và 7 luật suitability chạy; [ba/05](../ba/05-acceptance-criteria.md) ghi AC-FR12-03 một phần, AC-FR12-04 chờ kiểm, AC-FR12-07 chưa làm |
| FR13 | Bản tin chủ động | F7 | Mở rộng | Một phần: đã deploy (phase 5), chưa kiểm trên app |
| FR14 | Cảnh báo khoản chuyển lệch thói quen | phụ | Mở rộng | Chưa làm |
| FR15 | Bảng vận hành cho đội sản phẩm | vận hành | Mở rộng | Một phần: `/ops/summary` và trace qua REST (phase 5); CloudWatch Transaction Search không bật (phase 6 Q4) |

## Ghi chú từ số đo (2026-11-21)

Bảng dưới là số đo của bản thử ngày 21/11, giữ để tra ngược. Số của sản phẩm đang chạy nằm ở [ba/04](../ba/04-non-functional-requirements.md) và các file phase; riêng hai dòng chất lượng dự báo đã đổi sang số backtest của sản phẩm (25/11). Yêu cầu của proposal **không đổi**. Bảng chỉ ghi chỗ số đo hoặc spike đã chạy cho thấy có vấn đề hay đã có bằng chứng; mọi dòng **[đã chạy thử]** trừ khi ghi khác, trên dữ liệu thử (ML dùng dữ liệu tổng hợp). Bảng NFR đầy đủ ở [proposal-summary.md §5](../proposal/proposal-summary.md#5-yêu-cầu-chức-năng-fr-và-phi-chức-năng-nfr-5). Tổng hợp số đo: [overview.md](../architecture/overview.md#số-đo-đã-có).

| Mục | Ghi chú | Nguồn |
|---|---|---|
| NFR độ trễ: ký tự đầu dưới 1,5 giây | **Không đạt khi phiên Runtime lạnh**: event đầu 1,8 đến 3,9 s (V1 và V2); phiên ấm khoảng 0,3 s. Có LLM (Haiku 4.5 + 1 tool, V1) lượt đầu của phiên lạnh: chữ đầu 6,55 s (gồm nạp thư viện Strands), lượt hai cùng phiên event đầu 0,33 s. Đề xuất làm nóng phiên khi mở màn hình chat và hiện tiến độ cho lượt đầu | [Runtime §4](../research/spike-agentcore-runtime-cors.md) |
| NFR độ trễ: kiểm tra trước khi quẹt p95 dưới 2 giây (FR6) | **Phần DB đã đo, phần còn lại chưa**: luồng 3 truy vấn qua Data API p95 113 ms (có RLS qua hàm: p95 106 ms); Gateway ấm dưới 200 ms kể cả interceptor và Cedar. Chưa đo: cold start Lambda và Runtime, bước LLM giải thích. Aurora tự pause làm lần gọi đầu mất 16,4 s: không để pause khi chấm điểm | [Aurora §2, §4, §6](../research/spike-aurora-data-api.md), [Gateway §6](../research/spike-agentcore-gateway-identity.md) |
| NFR độ trễ: what-if trọn câu p95 dưới 8 giây (FR5) | Một lượt (router Haiku, planner Sonnet 2 vòng, diễn giải Haiku) đo được 6,3 s trong 3 lượt, **chưa tính** guardrail, KB, Gateway, Aurora, cold start; Claude 4.x chỉ 10 request/phút mỗi model nên không đủ khi nhiều người dùng song song hoặc chạy bộ đánh giá | [Bedrock §2c, §9](../research/spike-bedrock-models.md) |
| NFR độ đúng của số | Số trong khối UI do code dựng từ kết quả tool; LLM chỉ thấy bản gọn. Nhưng các cách phát khối khác để LLM thấy toàn bộ kết quả và nó viết lại thành bảng, nên số trong phần văn bản vẫn cần `NumericGrounding` | [Strands §2.5](../research/spike-strands-agui-local.md) |
| NFR chất lượng dự báo: tốt hơn seasonal naive | **Sản phẩm (phase 2)**: pinball P10/P50/P90 của chi ngày bằng 0,62 và 0,60 lần seasonal naive trên hai họ bộ sinh, seed giữ ra ngoài. Spike 21/11: hurdle tự viết và Chronos-2 khoảng 0,55; AutoETS dưới khoảng 60 ngày tệ hơn seasonal naive. **Chỉ trên dữ liệu tổng hợp**, bộ sinh do đội viết | [backtest-phase-2](../research/backtest-phase-2.md), [ML §3](../research/spike-ml-forecasting.md) |
| NFR chất lượng dự báo: khoảng 80% phủ từ 75% đến 85% (FR3) | **Sản phẩm**: dải số dư 30 ngày lấy từ Monte Carlo (hiệu chỉnh `rho`, `level_sigma`), không từ ACI; phase 2 đạt 0,80 ở hũ dày và hũ thưa. Theo độ dài lịch sử: hũ dày đạt từ 47 ngày, hũ thưa chỉ đạt từ 120 ngày, nên dưới ngưỡng thì ẩn % (#9). CQR hiệu chỉnh lại dải hũ dày sau Monte Carlo: ở 120 ngày phủ 0,798, mỗi đuôi khoảng 10% (#25). Spike 21/11 (trước hiệu chỉnh): tổng 30 ngày chỉ phủ 0,48 đến 0,61 ở hũ dày. Các số trên đo trên hũ riêng theo loại chi; ví 3 hũ (26/11, offline): hũ gộp phủ 0,865 ở 120 ngày, thừa so với mép trên 0,85 | [đo ví 3 hũ](../research/2026-11-26-do-vi-ba-hu.md), [backtest-final](../research/backtest-final.md), [backtest-phase-2](../research/backtest-phase-2.md) |
| FR3: xác suất hụt trước kỳ lương | Monte Carlo lấy mẫu độc lập đánh giá thấp khi rủi ro thấp (5,8% thay vì 10% ở hũ ăn uống); cần tương quan giữa các ngày, hũ thưa mô phỏng hurdle trực tiếp | [ML §6](../research/spike-ml-forecasting.md) |
| NFR phân loại: đúng từ 90% (FR2) | Bằng embedding, 1-NN theo hũ đạt 81 đến 84% thô và 93% sau khi chuẩn hóa chuỗi (Cohere v3 và v4) trên 43 chuỗi tự soạn, chưa phải bộ kiểm thử persona. Ngưỡng cosine 0,97 của proposal không hợp lý (gộp nhầm "tiền điện/nước" với "tiền trọ") | [Bedrock §6](../research/spike-bedrock-models.md) |
| FR9: nạp ảnh chụp | Trên 3 ảnh dựng sạch, Sonnet 4.6 và Kimi K3 đọc đúng cả bốn trường; Haiku 4.5 tự sửa sai nội dung không dấu. Ảnh chụp thật, CSV chưa thử. Bedrock Data Automation (cho PDF mở rộng) bỏ vì không liệt kê tiếng Việt (**[đọc tài liệu]**, [bedrock.md](../research/bedrock.md)) | [Bedrock §5](../research/spike-bedrock-models.md) |
| FR12 và NFR bảo mật: xác nhận trước khi ghi; tool mặc định bị từ chối | Cedar mặc định từ chối chạy đúng. Cờ xác nhận trong tham số do LLM điền nên giả mạo được; token xác nhận do server cấp qua 13 ca đúng kỳ vọng. Cơ chế này khác proposal §9, chủ dự án chốt 21/11 ([ADR-0002](../decisions/0002-xac-nhan-truoc-khi-ghi.md)). Dữ liệu tách theo người dùng: interceptor ghi đè `user_id` + Cedar + RLS đều đã chạy | [Gateway §3–§5](../research/spike-agentcore-gateway-identity.md), [Aurora §4](../research/spike-aurora-data-api.md) |
| NFR quyền riêng tư: che thông tin định danh trước khi vào LLM | **[đọc tài liệu]** Guardrails không kiểm kết quả tool và không có mẫu PII Việt Nam: che ở Lambda tool và bước nạp dữ liệu. Chưa tạo guardrail thử. Dữ liệu có thể được xử lý ngoài Singapore vì các model gọi được đều qua profile `global.` (**[đã chạy thử]**) | [bedrock.md](../research/bedrock.md), [Bedrock §2](../research/spike-bedrock-models.md) |
| NFR độ tin cậy: LLM lỗi vẫn trả thẻ số | Lỗi ném giữa luồng SSE là HTTP 200 với thân rỗng, không có `RUN_ERROR`: UI phải coi luồng rỗng hoặc đứt là lỗi. Structured output không đặt `structured_output_attempts` có thể lặp không dừng. Graph của Strands không rẽ lỗi (**[đọc tài liệu]**, [strands-agui.md](../research/strands-agui.md)): F3 viết bằng code tuần tự | [Runtime §1](../research/spike-agentcore-runtime-cors.md), [Strands §2.2](../research/spike-strands-agui-local.md) |
| NFR giải thích và kiểm toán: 100% lượt có trace (FR11) | `trace_id` do client sinh bằng `traceparent` và được giữ nguyên tới app. Span trong CloudWatch chưa xem được (chưa bật Transaction Search) | [Runtime §6](../research/spike-agentcore-runtime-cors.md) |
| NFR chi phí: prompt caching cho phần lặp | Haiku 4.5 chỉ cache khi prompt từ khoảng 4.096 token (router ngắn không cache được); Sonnet 4.6 từ khoảng 1.024; Kimi K3 và model open-weight không cache | [Bedrock §4](../research/spike-bedrock-models.md) |

## MVP và mở rộng

- **Làm lát dọc F1, F2, F3 trước** (§13 giảm thiểu rủi ro "phạm vi quá rộng"). Sao kê PDF, bản tin, bảng vận hành là phần mở rộng.
- **Ngoài MVP, đã có hướng thiết kế (§4)**: tự phát hiện khoản định kỳ; nhận diện loại tiền vào; thu nhập không đều (freelancer, tài xế, người bán online); lương về ngân hàng thay vì ví.
- Mở rộng kỹ thuật: Automated Reasoning checks, AgentCore Evaluations và Code Interpreter (§14), contextual bandit cho F7, Chronos-2 ("MVP nếu kịp"; chủ dự án chốt để ngoài ngày 21/11, xem [open-questions](open-questions.md) và [ADR-0004](../decisions/0004-lech-so-voi-proposal.md)).
- Cắt đầu tiên nếu đội 2 người: F6 (§15).
- **Bộ hũ (chủ dự án chốt 26/11, issue #39):** tài khoản mới nhận 3 hũ mặc định theo mục đích; muốn theo dõi riêng một khoản (dự báo, ngày cạn, phát hiện đổi hành vi) thì tách hũ riêng. Để sau hạn nộp: phân tích theo nhóm loại chi bên trong hũ gộp (hướng: gợi ý tách hũ khi hũ gộp có dấu hiệu tăng), bộ hũ theo giai đoạn sống (BR-70, BR-71), mục tiêu và khóa mềm hũ đệm (BR-64), cổng hũ dài hạn (BR-68), bắt buộc mục đích cho hũ để dành và chặn hũ đệm thứ hai (BR-63; hiện hũ để dành cũ có thể chưa có mục đích, có nhiều hũ đệm thì lấy hũ đệm đầu tiên theo thứ tự). Không làm: hũ "Khác" cho khoản nhỏ một lần (#28).

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
