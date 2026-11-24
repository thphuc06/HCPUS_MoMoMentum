# evals/ingest/

Bộ thử F6 (nạp ảnh và CSV). Nội dung thư mục, cách tải ảnh thật và cách chạy: [evals/README.md](../README.md#ingest-bộ-thử-f6-nạp-ảnh-và-csv). Interface backend và dạng kết quả: docstring của [`scripts/eval_ingest.py`](../../scripts/eval_ingest.py). File này chỉ ghi cách chấm.

## Cách chấm (`scripts/eval_ingest.py`)

- **Bốn trường** (ngày, số tiền, đối tác, nội dung) và chiều, hũ: theo `match_rule` của từng giao dịch trong `manifest.json`. Dòng trích ghép với dòng mong đợi theo số tiền trước (`pair_rows`).
- **Lộ PII** (`leaks`): so bằng băm sha256, manifest không lưu bản rõ.
  - Tên: văn bản kết quả được bỏ dấu, chữ thường rồi tách theo MỌI ký tự không phải chữ hay số (`name_tokens`). Mọi cụm `n` token liền nhau được băm và so với `name_hashes`, với `n` lấy từ `name_token_counts`. Nhờ vậy tên dính dấu câu vẫn bị bắt, ví dụ `"<tên>;nop tien;"` ở cột nội dung sao kê (r12), `"<tên>."` hay `"<HO>_<TEN>"`. Trước 24/11 hàm tách theo khoảng trắng nên bỏ sót các ca này.
  - Số: khoảng trắng, dấu chấm, gạch ngang nằm giữa hai chữ số được bỏ, rồi mọi dãy từ 8 chữ số được băm và so với `number_hashes`. Dạng đã che `****1234` không tính là lộ.
- **Báo lỗi đúng** (`not_financial_error_ok`): so theo mã lỗi API mà người dùng nhận (`API_ERROR_CODE`, bản sao của `yofina_ingest.extract.ERROR_CODE_OF`, test giữ hai bảng khớp nhau). Không so theo mã chữ thường của backend. Backend trả `no_transactions` cho bảng phí, menu và màn ATM, còn job thì vẫn ra `INGEST_NOT_FINANCIAL` như ảnh `not_financial`, nên cả hai mã đều đạt khi nhãn là `not_financial`. Có dòng nào tự thêm (`auto_add`) thì vẫn trượt.
- **Trùng lặp**: chế độ `eval` không có DB nên không đo được việc đánh dấu dòng trùng với sổ cái. Khử trùng thật kiểm bằng `tests/unit/ingest/test_dedupe.py` (sổ cái `vy` dựng lại và nhãn `s02`, `c01`) và `tests/local_pg`.
