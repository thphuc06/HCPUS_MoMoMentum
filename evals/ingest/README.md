# evals/ingest/

Bộ thử F6 (nạp ảnh và CSV). Nội dung thư mục, cách tải ảnh thật và cách chạy: [evals/README.md](../README.md#ingest-bộ-thử-f6-nạp-ảnh-và-csv). Interface backend và dạng kết quả: docstring của [`scripts/eval_ingest.py`](../../scripts/eval_ingest.py). File này chỉ ghi cách chấm.

## Cách chấm (`scripts/eval_ingest.py`)

- **Bốn trường** (ngày, số tiền, đối tác, nội dung) và chiều, hũ: theo `match_rule` của từng giao dịch trong `manifest.json`. Dòng trích ghép với dòng mong đợi theo số tiền trước (`pair_rows`).
- **Lộ PII** (`leaks`): so bằng băm sha256, manifest không lưu bản rõ.
  - Tên: văn bản kết quả được bỏ dấu, chữ thường rồi tách theo MỌI ký tự không phải chữ hay số (`name_tokens`). Mọi cụm `n` token liền nhau được băm và so với `name_hashes`, với `n` lấy từ `name_token_counts`. Nhờ vậy tên dính dấu câu vẫn bị bắt, ví dụ `"<tên>;nop tien;"` ở cột nội dung sao kê (r12), `"<tên>."` hay `"<HO>_<TEN>"`. Trước 24/11 hàm tách theo khoảng trắng nên bỏ sót các ca này.
  - Số: khoảng trắng, dấu chấm, gạch ngang nằm giữa hai chữ số được bỏ, rồi mọi dãy từ 8 chữ số được băm và so với `number_hashes`. Dạng đã che `****1234` không tính là lộ.
- **Báo lỗi đúng** (`not_financial_error_ok`): so theo mã lỗi API mà người dùng nhận (`API_ERROR_CODE`, bản sao của `yofina_ingest.extract.ERROR_CODE_OF`, test giữ hai bảng khớp nhau). Không so theo mã chữ thường của backend. Backend trả `no_transactions` cho bảng phí, menu và màn ATM; từ 25/11 mã này có mã API riêng `INGEST_NO_TRANSACTIONS` (kèm lý do con `error_reason`), tách khỏi `INGEST_NOT_FINANCIAL` của ảnh không phải chứng từ tài chính. Nhãn `not_financial` của manifest được gán trước khi tách mã, nên đạt với cả hai mã API (`REJECTED_NO_ROWS` của `scripts/eval_ingest.py`). Có dòng nào tự thêm (`auto_add`) thì vẫn trượt.
- **Trùng lặp**: chế độ `eval` không có DB nên không đo được việc đánh dấu dòng trùng với sổ cái. Khử trùng thật kiểm bằng `tests/unit/ingest/test_dedupe.py` (sổ cái `vy` dựng lại và nhãn `s02`, `c01`) và `tests/local_pg`.

## Quy ước nhãn

- **Không phải giao dịch** (bảng phí, menu, quảng cáo, màn ATM, ảnh hướng dẫn): `transactions` rỗng, `expected_error: "not_financial"`, `kind_of_image: "other"`.
- **Màn chưa thực hiện** (xác nhận, OTP, biểu mẫu trống): `transactions` rỗng, `no_auto_rows: true`.
- **Chuyển sang tiền của chính mình** không phải thu hay chi: nạp ví từ thẻ hay tài khoản của mình, chuyển giữa tài khoản của mình, và rút tiền mặt (ATM, tại quầy; quyết định của chủ dự án 24/11, vì ứng dụng không theo dõi tiền mặt). Backend bỏ các dòng này (`own_account_transfer`), không vào sổ, không vào hàng chờ duyệt. Nhãn không đưa chúng vào `transactions`. Từ 24/11, các dòng này ghi ở `excluded_rows` (`date`, `amount_vnd`, `direction`, `description`, `reason`) để lưu lại điều đã thấy trên ảnh (r15). Script không chấm `excluded_rows`, và cũng không phạt dòng trích thừa. Phí rút tiền là khoản chi bình thường.
- **Tra soát, khiếu nại, yêu cầu hoàn tiền** về một giao dịch đã có (quyết định 24/11): không phải chứng từ giao dịch mới, nạp vào sẽ ghi trùng. Nhãn theo quy ước "không phải giao dịch". Giao dịch gốc nếu cần thì ghi ở `excluded_rows` với `reason: "dispute_of_existing"` (r14).
