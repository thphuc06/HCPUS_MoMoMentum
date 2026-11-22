# evals/

Đánh giá chất lượng agent (proposal §9 Observability và đánh giá, §6 KPI, §15 tuần 3).

- Bộ câu chuẩn có quỹ đạo tool mong đợi (đánh giá offline, chạy mỗi lần đổi prompt/model); bộ 50 câu đối kháng cho đội rủi ro.
- Evaluator tự viết bằng code: `NumericGrounding` (mọi số có trong kết quả tool), `SchemaValidity` (JSON đúng schema), `SuitabilityCompliance` (không gợi ý vi phạm). AgentCore Evaluations (Correctness, Helpfulness, GoalSuccessRate) cho đánh giá online (phần mở rộng).
- Backtest dự báo (pinball loss so với seasonal naive, độ phủ khoảng 80%) chạy ở [../pipelines/](../pipelines/README.md) batch tuần. Khung backtest đã thử và lưu ý độ phủ tổng 30 ngày phủ thiếu: [spike-ml-forecasting.md](../docs/research/spike-ml-forecasting.md).
- Claude 4.x chỉ 10 request/phút mỗi model: chạy bộ đánh giá lớn cần Nova hoặc `us-east-1` (quota rộng hơn), không chạy chung xô với demo ([spike-bedrock-models.md](../docs/research/spike-bedrock-models.md) mục 9).

## `ingest/`: bộ thử F6 (nạp ảnh và CSV)

- `manifest.json` (commit): mỗi mục có `set` (`real` | `synthetic`), `kind_of_image`, `bank_or_wallet`, `quality`, `readable`, `label_status` (`agent_read` | `needs_human` | `orchestrator_checked`) và `expected` (giao dịch mong đợi với `match_rule` từng trường, `expected_jar` theo mã hũ persona `minh`, `expected_error`, `attack`, `duplicate_of`). Tên người chỉ giữ chữ cái đầu + `***`, số tài khoản/SĐT chỉ `****` + 4 số cuối; mục kiểm PII và tấn công lưu băm sha256, không lưu bản rõ.
- `real/` (**gitignored**): 25 ảnh minh họa từ các bài hướng dẫn công khai trên mytour.vn (Vietcombank, Techcombank, MoMo, VPBank, ACB, BIDV, VietinBank, MB, ViettelPay, Grab, EVN). Tải lại bằng `uv run scripts/eval_ingest.py --fetch` (kiểm magic bytes và sha256). Chưa có nhãn trường (`needs_human`): `kind_of_image`/`bank_or_wallet` hiện chỉ là gợi ý từ ngữ cảnh trang.
- `synthetic/` (commit): sinh lại bằng `uv run --with pillow scripts/make_ingest_synthetic.py` (tất định). 28 ảnh: biên lai kiểu app Việt, SMS, thông báo đẩy, hóa đơn siêu thị và tiền điện, lịch sử nhiều giao dịch, bản mờ/nghiêng/độ phân giải thấp/cắt, trùng lặp (bản sao byte-giống và bản nén lại), ảnh có tên và STK người khác, 4 ảnh tấn công, 3 ảnh không phải tài liệu tài chính. 5 CSV dựng theo cấu trúc cột sao kê VCB/BIDV công khai (PDF, nguồn ghi trong `structure_source_url`): 50 dòng tiếng Việt có dấu, tiếng Anh một cột số tiền có dấu, không dấu phân cách `;`, câu tấn công trong nội dung, ô công thức (CSV injection).
- Chạy: `uv run scripts/eval_ingest.py --set synthetic|real|all [--limit N] [--only ID ...] [--sleep 8] [--via-lambda yofina-ingest]`; `--check-manifest` chỉ kiểm manifest. Gọi `yofina_ingest.extract` (interface trong docstring của script), tuần tự, nghỉ 8 giây giữa hai mục. Thiếu backend thì thoát mã 2. Kết quả ghi `ingest/results/<timestamp>.json` (chỉ cờ đúng/sai và số đếm, không có văn bản OCR), báo riêng `real` và `synthetic`.
