# evals/classification/

Bộ kiểm **phân hũ tự động** (F2, phase 4 luồng B, tiêu chí hoàn thành số 6): giao dịch có nhãn của ba persona, script chạy ĐÚNG mã quyết định của Lambda `yofina-classify` và báo cáo độ đúng, tỷ lệ phải hỏi, ma trận nhầm; hiệu chỉnh ngưỡng trên tập hiệu chỉnh và đo trên tập kiểm. Mục tiêu: độ đúng của mục đã gán từ 90%, dưới 10% phải hỏi.

## Trạng thái hiệu chỉnh (đọc trước)

**CHƯA HIỆU CHỈNH BẰNG BEDROCK THẬT** (phiên AWS hết hạn lúc làm). Mọi số trong `gateway/tools/ledger/yofina_ledger/classify_defaults.json` là **giá trị khởi đầu chưa hiệu chỉnh** (`source` ghi rõ): `auto_min_confidence` 0,90, `review_min_confidence` 0,60, hệ số Platt của k-NN và của model nhỏ. Kết quả chế độ khô (embedding và model giả) KHÔNG đại diện và không dùng để hiệu chỉnh. Việc phải làm sau khi đăng nhập AWS (một lần, `ap-southeast-1`):

```powershell
$env:AWS_REGION='ap-southeast-1'; $env:YOFINA_USAGE_TABLE='yofina-usage'
uv run python evals/classification/run_eval.py warm                       # gọi model nhỏ cho từng giao dịch một lượt, lưu đệm (khoảng 330 lượt, 18 lượt/phút: chạy nền)
uv run python evals/classification/run_eval.py calibrate --write-config   # ước lượng hệ số, chọn ngưỡng trên nửa đầu, đo nửa sau, ghi classify_defaults.json
uv run python evals/classification/run_eval.py run                        # báo cáo với ngưỡng đã ghi
uv run python evals/classification/build_seed_labels.py                   # nhãn k-NN seed cho minh, lan, khoa (một lần gọi embedding mỗi persona)
```

Số thật rồi ghi vào "Kết quả thực hiện" của phase 4; chưa đạt thì ghi số đạt được và nguyên nhân (đọc `top_errors_test` và `by_category` trong báo cáo). Chi phí: vài lời gọi embedding (gom lô 96) và khoảng 330 lời gọi model nhỏ, tính vào trần ngày của vai (`embedding` 3.000, `small` 2.000).

## Tệp

| Tệp | Việc |
|---|---|
| `dataset.jsonl` | 334 giao dịch có nhãn (minh 118, lan 108, khoa 108), theo thời gian trong mỗi persona. Sinh bằng `build_dataset.py` (tất định; `--check` kiểm lệch) |
| `build_dataset.py` | bộ sinh và bất biến (đủ 300 dòng, mọi nhãn thuộc hũ của persona, có chuyển khoản tên riêng không lời nhắn) |
| `sim.py` | mô phỏng trực tuyến: kho nhãn k-NN trong bộ nhớ (cosine như `app_knn_labeled`), sổ cái, luật, người dùng mô phỏng hợp tác; chỉ số, ma trận nhầm |
| `run_eval.py` | `warm`, `calibrate`, `run`; chế độ `live` (Bedrock thật, có đệm), `dry` và `cache` (chỉ đọc đệm đã commit, không tạo client AWS; thiếu đệm thì dừng và báo số lời gọi cần). `--add-jar ma:tên:loại[:số dư]` thêm hũ cho mọi persona (đo hũ "Khác", xem [2026-11-26-hu-khac.md](../../docs/research/2026-11-26-hu-khac.md)); `--wallet multi\|three` chọn ví (mục "Ví 3 hũ" bên dưới); `--limit N` lấy N dòng đầu mỗi persona; `--out` ghi báo cáo ra tệp khác |
| `fakes.py` | embedding băm và model từ khóa GIẢ, chỉ cho chế độ khô (kiểm đường ống) |
| `build_seed_labels.py` | sinh nhãn seed của persona vào `data/personas/classify_labels/` bằng Bedrock thật |
| `results/` | báo cáo `classification-<chế độ>[-three]-<ngày>.json`, `calibration-*.json`, đệm `embedding_cache.json` (chung mọi ví), `llm_cache.json` (ví nhiều hũ) và `llm_cache_three.json` (ví 3 hũ, chưa có) (chỉ chế độ live ghi) |

## Ví 3 hũ (`--wallet three`)

Số 92% / 17,4% ở trên đo trên ví nhiều hũ của persona. Tài khoản mới nhận 3 hũ (Chi hằng ngày, Nghĩa vụ, Dự phòng; issue #39), và phần có model của ví này chưa đo ([2026-11-26-do-vi-ba-hu.md](../../docs/research/2026-11-26-do-vi-ba-hu.md), khuyến nghị P1). `--wallet three` đo nó bằng đúng mã quyết định của Lambda:

- Ví là các hũ `is_default` của migration 0059; danh sách hũ trong lời nhắn model nhỏ là 3 hũ đó (hũ thêm bằng `--add-jar` xếp sau).
- Đáp án, cờ "luôn luôn" của người dùng mô phỏng và nhãn seed đổi mã theo đúng quy tắc sản phẩm qua `scripts/measure_three_jars.py` (`yofina_core.wallet.transaction_jar`); bước 0 của mô phỏng và của tập thông điệp cần gọi cũng đi qua `transaction_jar` như `Classifier.classify`, nên loại giao dịch có hũ chung không tới model. `--seed-labels mapped` (mặc định, nhãn seed của persona đổi mã, như lượt C của ghi chú đo) hoặc `none` (tài khoản mới không có nhãn seed, như lượt F); hai chế độ cùng thông điệp nên cùng đệm.
- Đệm phán quyết riêng `results/llm_cache_three.json` (khóa đệm là băm thông điệp, mà thông điệp chứa danh sách hũ); đệm embedding dùng chung.
- Chỉ `run` và `warm`. `calibrate` từ chối `--wallet three` vì nó ghi ngưỡng của sản phẩm.
- Chế độ live in ước tính TRƯỚC lời gọi đầu tiên và ghi đệm sau mỗi 10 phán quyết mới cùng lúc kết thúc (kể cả khi lỗi), nên đứt giữa chừng thì chạy lại cùng lệnh chỉ gọi phần còn thiếu. Lời gọi model lỗi trong `run` thì quyết định đó suy giảm như Lambda; báo cáo ghi `llm_errors` và in cảnh báo.

Ước tính đo được từ đệm đã commit (26/11, chạy `run --mode cache --wallet three`, không gọi gì): **294 lời gọi model nhỏ** (Nova 2 Lite, vai `small`), 1 lời gọi embedding (4 chuỗi mất khóa đệm do bộ che PII đổi ở #16), khoảng 107.000 token vào và tối đa 75.000 token ra, **khoảng 0,30 USD** (tối đa 0,97 USD nếu mọi lời gọi phải thử lại ở giá Haiku 4.5), khoảng 16 phút ở 18 lượt/phút. Giá lấy từ AWS Price List ngày 25/11 (`SMALL_PRICE_USD_PER_MTOK`); token ước bằng số ký tự chia 3, chưa tính schema của tool. Tính vào trần ngày của vai `small` (2.000), không tính vào trần lượt chat.

```powershell
# không cần AWS: chỉ in ước tính rồi dừng (mã thoát 3)
uv run python evals/classification/run_eval.py run --mode cache --wallet three
# cần AWS ap-southeast-1 (hỏi chủ dự án trước): thử ít trước, rồi cả bộ; đứt thì chạy lại cùng lệnh
$env:AWS_REGION='ap-southeast-1'; $env:YOFINA_USAGE_TABLE='yofina-usage'
uv run python evals/classification/run_eval.py warm --wallet three --limit 5
uv run python evals/classification/run_eval.py warm --wallet three
# chấm từ đệm (không gọi gì), hai chế độ nhãn seed
uv run python evals/classification/run_eval.py run --mode cache --wallet three --out $env:TEMP/cls-three.json
uv run python evals/classification/run_eval.py run --mode cache --wallet three --seed-labels none --out $env:TEMP/cls-three-noseed.json
```

## Bộ dữ liệu

Hư cấu, do dự án soạn; nhãn do cấu trúc sinh quyết định: một cửa hàng luôn thuộc đúng một hũ; người nhận có thói quen (hũ chính chiếm `main_share`, còn lại là nhiễu), nên chuyển khoản tên riêng không lời nhắn KHÔNG thể đúng 100% với bất kỳ bộ phân loại nào. Bảy loại: `mapped_type` 12% (bước 0 xử lý: chỉ kiểm bảng tra, đúng theo cấu trúc), `known_qr` 14% (cửa hàng đã biết, loại `qr_other`), `unseen_qr` 34% (cửa hàng chưa từng thấy; test kiểm không trùng nhãn seed), `note_only` 14%, `person_no_note` 11%, `informal` 12% (viết tắt, không dấu), `injection` 3% (lời nhắn chứa chỉ dẫn giả). Hũ lấy từ `data/personas/specs`. Báo cáo luôn tách theo loại để số tổng không che điểm yếu: `mapped_type` kéo độ đúng tổng lên một cách dễ dãi.

## Mô phỏng và chỉ số

- Người dùng mô phỏng biết đáp án và hợp tác: mục `review` thì bấm "đúng rồi" hoặc sửa; mục `ask` thì trả lời đúng hũ; chọn "luôn luôn" (luật) khi cửa hàng hoặc người nhận có hũ nhất quán, không thì "chỉ lần này"; sửa một lần gán tự động sai thì nâng ngưỡng riêng của người nhận. Nhãn k-NN nguồn `user` và luật tích lũy qua cả hai nửa như sản phẩm thật. Nhãn seed: cửa hàng trong spec persona cộng `data/personas/classify_labels/base_vocabulary.json`.
- Tập hiệu chỉnh = nửa đầu theo thời gian của mỗi persona; tập kiểm = nửa sau.
- Chỉ số (mỗi tập): `accuracy_assigned` (đúng trong số mục đã gán, mức auto và review), `accuracy_auto`, `accuracy_review`, `ask_rate`, `review_rate`, `correct_end_to_end` (đúng trên tổng), `silent_error_rate` (tự gán sai trên tổng), `by_category`, ma trận nhầm (cột `HOI` là chuyển sang hỏi gộp), 25 lỗi tự gán tự tin nhất.
- Chọn ngưỡng (`choose_thresholds`): quét lưới `(review_min, auto_min)` trên tập hiệu chỉnh; `review_min` thấp nhất mà độ đúng của mục đã gán đạt 90% với tỷ lệ hỏi nhỏ nhất; `auto_min` thấp nhất mà độ đúng của mục tự gán đạt 95%. Hệ số Platt ước lượng bằng hồi quy logistic (Newton) trên số đo thô của k-NN (độ giống, biên) và của model (độ chắc báo).
- Lưu đệm: embedding theo chuỗi chuẩn hóa; phán quyết model nhỏ theo băm thông điệp (thông điệp KHÔNG chứa gợi ý từ embedding, và lịch sử cùng người nhận chỉ phụ thuộc đáp án, nên quét ngưỡng không phát sinh lời gọi mới sau `warm`).

## Giới hạn đã biết

- Bộ dữ liệu hư cấu và sinh theo mẫu: độ đúng đo được là ước lượng lạc quan so với giao dịch thật; nó kiểm cơ chế (chuẩn hóa, k-NN, trộn bằng chứng, ba mức, học từ sửa), không thay thế đo trên dữ liệu người dùng.
- Người dùng mô phỏng hợp tác hoàn hảo (luôn trả lời đúng).
- Hũ "Khác" không có trong persona nên nhánh "khoản nhỏ một lần vào Khác" chỉ được kiểm bằng unit test, không có trong bộ này. `--add-jar khac:Khác:spending` đo được nhánh đó, nhưng thông điệp model nhỏ chứa danh sách hũ nên cần `warm` lại (294 lời gọi model nhỏ); số trước, phần còn thiếu và lệnh chạy ở [2026-11-26-hu-khac.md](../../docs/research/2026-11-26-hu-khac.md).
