# pipelines/classify/

**Lambda `yofina-classify`** (phase 4 luồng B, F2 phân hũ tự động): nghe `transaction.recorded` có `needs_classification` (khoản chi đang ở Chưa phân loại) qua SQS và gán hũ. Construct hạ tầng: [../../infra-cdk/lib/classify.ts](../../infra-cdk/lib/classify.ts) (CHƯA nối vào stack nào). Phần ghi nằm ở `yofina_ledger/classify_write.py`, phần đọc và REST ở `yofina_ledger/review_*.py`; ngưỡng ở `yofina_ledger/classify_defaults.json`.

## Thứ tự phân loại (`yofina_classify/pipeline.py`)

| Bước | Việc | Độ tin cậy |
|---|---|---|
| 1 | Luật `category_rules` "luôn luôn" của người dùng (người nhận, hoặc đối tác theo `fold_text(merchant)[:120]`) | `rule_confidence`, luôn mức `auto`. Thắng bảng tra khi hai bên khác nhau (như luồng nạp phase 5) |
| 0 | Bảng `tx_type_map` (hũ chuẩn của loại giao dịch, nếu người dùng có hũ đó) | `type_map_confidence` |
| 2 | Embedding Cohere Embed v3: chuỗi đã chuẩn hóa (bỏ dấu, chữ thường, mở rộng viết tắt, bỏ số) và đã che PII; khớp chính xác `app_find_labeled_exact` trước (không tốn lời gọi), rồi nhúng và `app_knn_labeled` | xác suất đúng đã hiệu chỉnh (Platt trên độ giống và biên); KHÔNG dùng ngưỡng cosine 0,97 (spike Bedrock §6) |
| 3 | Model nhỏ (vai `small`) từ lời nhắn, số tiền, giờ, thứ, tín hiệu hành vi (lặp lại cùng người nhận theo hũ, số tiền tròn); trộn với bằng chứng embedding bằng noisy-or có phạt mâu thuẫn (`decide.fuse`) | `llm_cal_*` |

Ba mức (`wallet.CLASSIFICATION_TIERS`): `auto` (từ `auto_min_confidence`, hoặc ngưỡng riêng cao hơn của người nhận sau nhiều lần sửa), `review` (tự gán, `needs_review`, vào "Xem lại"), `ask` (ở lại Chưa phân loại, `suggested_jars` tối đa 2, mở hoặc cập nhật `review_asks` của ngày). Khoản nhỏ một lần không rõ vào hũ `small_one_off_jar_code` ("Khác") và không hỏi, NẾU người dùng có hũ đó (jar_templates và persona hiện KHÔNG có hũ này). Hũ đích không đủ số dư thì ở lại hỏi gộp.

Ghi: `classify_write.write_auto_assign` dùng lại ĐÚNG các đoạn SQL của `WalletRepo.write_assign_jar` (khóa dòng, khóa hai hũ, đổi hũ, cộng trừ số dư, audit) trong MỘT transaction rồi sửa nhãn (`classified_by` = bước đã gán, độ tin cậy, `needs_review`, gợi ý thay thế) và ghi `tx_embeddings`. Không có SQL cập nhật số dư tự viết. Sau commit phát `transaction.recorded` (`tx_type` `jar_assign`, không có `needs_classification`) để dự báo hai hũ chỉnh nhanh.

An toàn: tên người nhận và số tài khoản bị che trước khi vào model (`yofina_core.pii`, `text.mask_tx`); đối tác là người thì tên không vào chuỗi nhúng (danh tính nằm ở `payee_id`); lời nhắn là dữ liệu, đầu ra model ép qua tool có schema và mã hũ phải thuộc danh sách của người dùng; audit không có tên đối tác.

Idempotency hai lớp: DynamoDB theo `event_id` (`idempotency.py`, khóa `classify:<event_id>`, bảng riêng do CDK tạo) và trạng thái nghiệp vụ (giao dịch đã ra khỏi Chưa phân loại thì bỏ qua). Lỗi hạ tầng thì trả `batchItemFailures` để SQS giao lại, quá `maxReceiveCount` vào DLQ (alarm). Model nghẽn (`AllModelsFailed`) thử lại tới lần giao cuối rồi suy giảm về hỏi gộp; hết trần ngày (`ModelBudgetExceeded`) suy giảm ngay.

## Bố cục

| Tệp | Việc |
|---|---|
| `handler_classify.py` | vỏ Lambda (`handler_classify.lambda_handler`) |
| `yofina_classify/pipeline.py` | `Classifier.classify(facts, ctx)`: quyết định; ba cổng `LabelIndex`, `Embedder`, `judge` |
| `yofina_classify/decide.py` | hàm thuần: k-NN, trộn bằng chứng, mức tin cậy |
| `yofina_classify/text.py`, `abbreviations.json` | chuẩn hóa chuỗi, che PII, từ điển viết tắt |
| `yofina_classify/llm_step.py` | prompt, đầu ra có cấu trúc, kiểm mã hũ |
| `yofina_classify/repo.py` | đọc Aurora (`app_get_transaction`, một câu SELECT gom ngữ cảnh), `PgLabelIndex` |
| `yofina_classify/service.py` | một giao dịch từ đầu đến cuối: đọc, quyết định, ghi, phát sự kiện |
| `yofina_classify/consumer.py`, `idempotency.py` | SQS, idempotency |
| `yofina_classify/adapters.py`, `bootstrap.py`, `settings.py` | cổng Bedrock thật (`yofina_core.llm`), dựng thành phần, cấu hình hạ tầng |

## Đóng gói và deploy (người điều phối)

```bash
uv run scripts/build_lambda.py pipelines/classify --arch arm64 --name classify \
  --extra gateway/tools/ledger/yofina_ledger:yofina_ledger
```

Zip không cần numpy hay scipy. Nối `new ClassifyPipeline(...)` (`infra-cdk/lib/classify.ts`) vào `YofinaTools`: bus `yofina-bus`, topic cảnh báo, ARN cluster và secret role `yofina_app`, tên bảng `yofina-usage`. Ghi đè ngưỡng khi cần bằng context `-c classifyThresholds='{"auto_min_confidence":0.92}'`.

## Kiểm

- Unit (không cần AWS): `uv run pytest tests/unit/classify libs/yofina_core/tests/test_llm_embed.py`.
- PostgreSQL thật cục bộ (pgvector 0.6.2, RLS thật): `tests/local_pg/test_classify_flow.py` (lệnh ở docstring của `tests/local_pg/conftest.py`).
- Bộ kiểm chất lượng: [../../evals/classification/README.md](../../evals/classification/README.md).
