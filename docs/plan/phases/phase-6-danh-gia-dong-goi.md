# Phase 6 — Đánh giá, cứng hóa, đóng gói

Ngày dự kiến: 9–10/12/2026 (nộp trước 11/12). Kế hoạch tổng: [master-plan.md](../master-plan.md). Điều kiện vào: phase 5 đạt, hoặc đã hết thời gian cho phase 5: khi đó phase này chạy trên những gì đã xong và ghi rõ phần thiếu.

## Mục tiêu

Có số đo cho các NFR, bộ đánh giá chạy lại được trong giới hạn quota, không còn lỗi chặn demo, và bộ tài liệu nộp bài. Giám khảo tự dùng tài khoản demo đi được cả 6 cảnh; nếu model hoặc mạng trục trặc thì app vẫn trả thẻ số liệu.

## Phạm vi

Batch tuần, bộ 50 câu chuẩn và 50 câu đối kháng, đo NFR, kiểm bảo mật và chi phí, hoàn thiện giao diện (tối, điện thoại thật, a11y), tài liệu nộp. Không thêm tính năng mới.

## Đọc trước

| Luồng | Đọc |
|---|---|
| Mọi luồng | "Kết quả thực hiện" của phase 1–5; [requirements.md](../../requirements/requirements.md); bảng NFR ở [proposal-summary.md §5](../../proposal/proposal-summary.md); §6 (KPI), §13 (rủi ro) |
| A | [agentcore.md](../../research/agentcore.md) §3.6; [spike-bedrock-models.md](../../research/spike-bedrock-models.md) §2a, §9 |
| B | [spike-ml-forecasting.md](../../research/spike-ml-forecasting.md) §3, §5 |
| C | [spike-agentcore-gateway-identity.md](../../research/spike-agentcore-gateway-identity.md) §8; skill `aws-core:aws-billing-and-cost-management`, `/security-review` |
| D | [figma-ui-design.md](../../research/figma-ui-design.md) §7, node giao diện tối `28:2742`, `28:2967`, `28:3074`; [demo-script.md](../demo-script.md) |

## Luồng A — Bộ đánh giá agent

Sở hữu: `evals/`.

- Gộp và bổ sung cho đủ: 50 câu chuẩn có quỹ đạo tool mong đợi (phủ F1–F7, sáu loại kịch bản, câu thiếu tham số, tra cứu) và 50 câu đối kháng (prompt injection trực tiếp và qua tệp, đòi dữ liệu người khác, ép ghi không xác nhận, khuyên chứng khoán, khuyên vay để tiêu, moi system prompt).
- Evaluator viết bằng code: `NumericGrounding`, `SchemaValidity`, `SuitabilityCompliance`, khớp quỹ đạo tool, có trace cho 100% lượt. Điểm hữu ích của lời giải thích chấm bằng LLM judge trên mẫu 20 câu (Sonnet 4.6, giãn nhịp).
- Runner: tuần tự, giãn nhịp dưới quota (mặc định 8 request/phút mỗi model), lưu kết quả từng câu, chạy tiếp khi đứt, tôn trọng trần lượt gọi mỗi ngày (ước tính số lượt trước khi chạy; nếu vượt trần thì chia hai ngày hoặc nâng trần tạm có ghi lại). Chạy trên tài khoản `giamkhao3` đã đặt lại.
- AgentCore Evaluations online (nếu còn thời gian): lấy mẫu thấp, evaluator dựng sẵn; ghi chi phí. Không bắt buộc.
- Báo cáo `docs/research/eval-report.md`: tỷ lệ đạt theo nhóm, từng câu trượt và nguyên nhân, chi phí và số lượt gọi.

## Luồng B — Batch tuần và chất lượng dự báo

Sở hữu: `pipelines/weekly/`.

- Step Functions `yofina-weekly` (Chủ nhật): backtest rolling-origin trên dữ liệu trong DB, hiệu chỉnh lại ACI và hệ số khoảng tổng 30 ngày, ghi kết quả; đồng bộ kho tri thức; chạy bộ đánh giá rút gọn (10 câu).
- Báo cáo cuối `docs/research/backtest-final.md`: pinball so với seasonal naive, độ phủ khoảng 80% (theo ngày và tổng 30 ngày), số ngày cảnh báo trước khi hũ cạn và tỷ lệ cảnh báo đúng trên ba persona (KPI §6), mô phỏng có và không có trợ lý (số lần trễ hạn, phí phát sinh).

## Luồng C — Cứng hóa: độ trễ, tin cậy, bảo mật, chi phí

Sở hữu: `tests/`, `scripts/`, sửa lỗi ở mọi thư mục theo phân công của người điều phối.

- Đo NFR độ trễ (30 lượt mỗi loại, phiên ấm và phiên lạnh, từ trình duyệt): ký tự đầu, kiểm tra trước khi quẹt p95, what-if p95. Ghi bảng "mục tiêu / đo được"; mục không đạt thì ghi nguyên nhân và biện pháp đã áp (làm nóng phiên, khối đến trước).
- Tin cậy: ép lỗi từng thành phần (model bị chặn, tool quá thời gian, Aurora chậm, Gateway từ chối, luồng SSE đứt) và xác nhận app trả thẻ số liệu hoặc thông báo rõ; sự kiện gửi trùng; DLQ rỗng sau các bài thử.
- Bảo mật: chạy `/security-review` trên repo; test CI (GitHub Actions, chỉ phần không cần AWS, cộng test cấu hình chạy bằng tay) khẳng định Gateway có interceptor và Policy ở `ENFORCE`, mọi bảng có RLS, Lambda tool không đọc được secret master; quét repo tìm account ID, ARN, secret, email; kiểm IAM của từng Lambda không có wildcard thừa; S3 chặn public.
- Chi phí: đối chiếu Cost Explorer với ước tính, kiểm Budgets đã gửi được cảnh báo thử, ghi chi phí mỗi lượt hội thoại từ trace; trần lượt gọi mỗi ngày đặt lại cho ngày chấm.
- Aurora không tự pause; làm nóng Lambda và phiên trước giờ demo bằng script `scripts/warmup.py`.
- Dọn: xóa tài nguyên thử còn sót, đối chiếu `docs/aws-resources.md` với tài khoản; viết `scripts/teardown.md` (thứ tự hủy stack sau cuộc thi; không chạy).

## Luồng D — Hoàn thiện giao diện và tổng duyệt

Sở hữu: `frontend/`.

- So từng màn với frame Figma ở 390×844; sửa lệch khoảng cách, chữ, màu. Giao diện tối cho các màn có frame tối và kiểm biểu đồ, hũ thủy tinh ở chế độ tối (cắt được nếu thiếu thời gian).
- A11y: tương phản, vùng chạm tối thiểu 44 px, nhãn cho nút biểu tượng, `prefers-reduced-motion`.
- Điện thoại thật: bàn phím ảo che ô nhập, vuốt sheet, vùng an toàn; cài như PWA (manifest, icon chữ "Yofina"). Chủ dự án thử trên Safari iPhone, agent sửa theo lỗi báo về.
- Kích thước bundle: tách chunk biểu đồ và chat; ghi số.
- Kiểm không còn chữ "MoMo", "Ví Trả Sau" hay "FinHealth" trên giao diện; mọi màn có nhãn "Ví mô phỏng"; nội dung AI có nhãn.
- Tổng duyệt: đi 6 cảnh ba lần liên tiếp từ tài khoản vừa đặt lại, bấm giờ; chụp ảnh từng cảnh vào `docs/plan/assets/demo/` để làm slide và làm phương án dự phòng.

## Luồng E — Tài liệu nộp

Sở hữu: `README.md`, `docs/`.

- README: sản phẩm làm gì, kiến trúc (sơ đồ cập nhật theo thực tế), cách chạy lại (deploy từ đầu), tài khoản demo lấy ở đâu (không ghi mật khẩu), giới hạn đã biết.
- Cập nhật [overview.md](../../architecture/overview.md): đổi nhãn [đề xuất] thành [đã chạy thử] ở những chỗ đã làm, ghi các chỗ lệch cuối cùng. Cập nhật cột trạng thái trong [requirements.md](../../requirements/requirements.md) và tick [open-questions.md](../../requirements/open-questions.md).
- `docs/plan/demo-runbook.md`: kịch bản bấm cho video 3 phút theo app thật, việc cần làm trước khi quay (đặt lại, làm nóng), phương án khi lỗi.
- Dàn ý slide 10 trang với số đo thật (`docs/plan/slide-outline.md`). Quay video và dựng slide là việc của chủ dự án.

## Tiêu chí hoàn thành

1. Bộ 50 câu chuẩn: quỹ đạo tool đúng từ 85%, `SchemaValidity` 100%, `NumericGrounding` 100% trên câu trả lời đã phát, 100% lượt có trace. Bộ 50 câu đối kháng: 0 gợi ý vi phạm luật lọt ra, 0 lượt ghi không xác nhận, 0 rò dữ liệu người khác. Báo cáo có trong repo.
2. Bảng NFR "mục tiêu / đo được" đầy đủ; mục không đạt có giải thích.
3. Báo cáo backtest cuối có trong repo; batch tuần chạy tay thành công.
4. Mọi bài ép lỗi ở luồng C cho kết quả suy giảm có kiểm soát; không có màn trắng hay luồng treo.
5. `/security-review` không còn phát hiện mức cao chưa xử lý; quét repo sạch; test cấu hình đạt.
6. Tổng duyệt 6 cảnh ba lần liên tiếp không lỗi, mỗi lần trong 3 phút rưỡi; chủ dự án xác nhận chạy được trên iPhone.
7. Tài nguyên trên tài khoản khớp `docs/aws-resources.md`; chi phí thực đã ghi.
8. README, demo-runbook, slide-outline, overview, requirements, open-questions, HANDOFF đã cập nhật; đã commit và push.

## Cách kiểm (người điều phối)

- Tự chạy lại runner đánh giá trên một mẫu 15 câu ngẫu nhiên và so với báo cáo.
- Tự làm ba bài ép lỗi; tự đi tổng duyệt một lần bằng trình duyệt trong app ở khổ điện thoại.
- `git grep` các mẫu account ID, `arn:aws`, `AKIA`, mật khẩu; liệt kê tài nguyên theo tag.
- Làm theo README từ đầu ở mức đọc khô để chắc không thiếu bước.

## Kết quả thực hiện

(Điền khi đóng phase.)
