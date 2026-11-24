# Tỷ giá cho chứng từ ngoại tệ khi nạp dữ liệu (F6)

Tra cứu ngày 24/11/2026 (giờ máy), nhánh `p5/ingest-fx`; 25/11 chuyển hàm sang `yofina_core` và thêm tool cho agent chat (nhánh `p5/fx-tool`, mục "Tool `get_exchange_rate` cho agent chat"). Mã: [`libs/yofina_core/src/yofina_core/fx.py`](../../libs/yofina_core/src/yofina_core/fx.py). Hợp đồng: [contracts/README.md](../../contracts/README.md), mục "Chứng từ ngoại tệ và `INGEST_NO_TRANSACTIONS`".

## Bài toán

Chủ dự án nạp ảnh hóa đơn dịch vụ thu tự động qua thẻ ghi "$111.11 USD, due November 10, 2026". Model đọc đúng loại tài liệu, nhưng dòng chỉ có `amount_vnd` nên bị loại và màn hình báo "không phải biên lai". Chủ dự án quyết định quy đổi ngoại tệ về VND. Cần một nguồn tỷ giá thật, công khai, có tỷ giá theo ngày cho VND, không cần đăng ký tài khoản hay khóa trả phí.

## Lambda có ra internet không

Lambda `yofina-ingest` (worker) và `yofina-ingest-api` trong `infra-cdk/lib/ingest-stack.ts` không có cấu hình VPC. Chỉ Aurora nằm trong VPC (subnet `PRIVATE_ISOLATED` ở `data-stack.ts`), và Lambda gọi Aurora qua Data API (HTTPS tới dịch vụ AWS), không qua VPC. Theo tài liệu Lambda, hàm không gắn VPC chạy trong VPC do Lambda quản lý và có internet ([Enable internet access for VPC-connected Lambda functions](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc-internet.html)). Không cần NAT hay thứ gì tính tiền theo giờ, không đổi IAM hay biến môi trường.

## Các nguồn đã xem

| Nguồn | Có VND | Theo ngày | Khóa, giới hạn, điều khoản | Kết luận |
|---|---|---|---|---|
| Vietcombank, endpoint JSON của trang Tỷ giá: `https://www.vietcombank.com.vn/api/exchangerates?date=YYYY-MM-DD` | Có (20 ngoại tệ, đơn vị VND) | Có | Không khóa. Trang [Tỷ giá](https://www.vietcombank.com.vn/vi-VN/KHCN/Cong-cu-Tien-ich/Ty-gia) khai báo chính endpoint này trong cấu hình của trang (`"endpoint":"/api/exchangerates?date="`). Trang ghi bảng chỉ để tham khảo. Không thấy giới hạn gọi công bố cho JSON | **Chọn** |
| Vietcombank XML: `https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx` (liên kết "định dạng XML" trên trang Tỷ giá) | Có | Không, chỉ bảng hiện tại | Không khóa. Thân trả lời ghi "For reference only. Only one request every 5 minutes!" | Không chọn: không tra được ngày giao dịch |
| NHNN, tỷ giá trung tâm (sbv.gov.vn) | Chỉ USD/VND | Có (trang tin) | Không tìm thấy API công bố; trang HTML | Không chọn: không phải giá người dùng trả, không ổn định để đọc bằng mã |
| ExchangeRate-API open access: `https://open.er-api.com/v6/latest/USD` ([tài liệu](https://www.exchangerate-api.com/docs/free)) | Có | Không, chỉ mới nhất | Không khóa, giới hạn tần suất (trả 429, gỡ sau 20 phút), bắt buộc ghi nguồn, cấm phân phối lại | Không chọn: không có theo ngày, tỷ giá trung bình thị trường chứ không phải giá bán của ngân hàng |
| fawazahmed0/exchange-api qua jsDelivr ([GitHub](https://github.com/fawazahmed0/exchange-api)) | Có | Có (`@{date}`) | Không khóa, không giới hạn công bố | Không chọn làm nguồn chính: dữ liệu tổng hợp của một dự án cá nhân, không phải giá ngân hàng Việt Nam |
| Frankfurter (ECB) ([danh sách tiền tệ](https://api.frankfurter.dev/v1/currencies)) | Không | Có | Không khóa | Loại: không có VND |

Gọi thật một lần trong lúc làm (24/11/2026, `date=2026-11-10`): 200, `application/json; charset=utf-8`, `Count` 20, `Date` "2026-11-10T00:00:00", `UpdatedDate` "2026-11-10T23:00:00+07:00", mỗi ngoại tệ có `currencyCode`, `cash`, `transfer`, `sell` dạng chuỗi ("25790.00"). Ngoại tệ không mua tiền mặt có `cash` "0.00". Thử thêm hai ngày: Chủ nhật 08/11 vẫn có bảng (USD bán 25.780); ngày tương lai 30/12 trả `Count` 0, `Data` rỗng. Hóa đơn ca thật: 111,11 × 25.790 = 2.865.526,9, làm tròn thành **2.865.527 ₫**. Mẫu rút gọn của thân trả lời nằm trong `libs/yofina_core/tests/test_fx.py`.

## Chọn tỷ giá nào

Vietcombank công bố ba cột: Mua tiền mặt, Mua chuyển khoản, Bán. Khi chủ thẻ thanh toán bằng ngoại tệ, ngân hàng phát hành **bán** ngoại tệ cho chủ thẻ để trả tổ chức thẻ, nên dùng cột **Bán** (`sell`). Vietcombank không tách "bán tiền mặt" với "bán chuyển khoản"; cột Bán dùng chung. Số trên sao kê thẻ thường cao hơn vì còn phí chuyển đổi ngoại tệ theo biểu phí thẻ của ngân hàng phát hành, và thời điểm ghi nợ có thể lệch ngày. Vì vậy:

- Số VND là **ước tính**. Dòng ngoại tệ luôn vào hàng chờ duyệt (không bao giờ chọn sẵn), màn duyệt hiện số VND ngay, kèm dòng thu gọn "111,11 USD" mở ra tỷ giá, nguồn và ngày, và ô "Số VND sẽ ghi" để người dùng sửa theo sao kê thẻ trước khi chốt.
- Ngày tỷ giá là ngày giao dịch trên chứng từ (với hóa đơn thu tự động là ngày thu hoặc ngày đến hạn), không có thì ngày nạp (ngày mô phỏng `app_today`). Bảng chỉ có cho ngày đã qua hoặc hôm nay theo giờ Việt Nam thật, nên ngày sau hôm nay được kẹp về hôm nay; ngày chưa có bảng thì lùi từng ngày, tối đa 4 ngày. Ngày của bảng đã dùng được lưu ở `fx.rate_date`.
- Làm tròn tới đồng, nửa đồng làm tròn lên, tính bằng `Decimal`.

## Bộ nhớ đệm và lỗi

- Một lần gọi trả cả bảng của một ngày cho mọi ngoại tệ, nên bộ nhớ đệm theo ngày cũng là theo (tiền tệ, ngày). Bộ nhớ đệm nằm trong tiến trình Lambda: rẻ nhất, không cần bảng mới, không cần migration cho phần này. Bảng của ngày đã qua không đổi nên giữ tới khi môi trường thực thi tắt; bảng của hôm nay giữ 1 giờ (ngân hàng cập nhật trong ngày); lỗi hay ngày chưa có bảng giữ 10 phút để không gọi dồn. Một lần nạp gọi nguồn nhiều nhất 5 lần (ngày giao dịch và 4 ngày lùi), mỗi lần hết giờ sau 4 giây.
- Lỗi tra tỷ giá (mạng, hết giờ, trả lời lạ, ngoại tệ không có trong bảng): dòng vẫn vào hàng chờ với số gốc và `fx.status = rate_unavailable`, không có số VND. Người dùng nhập số VND trước khi chốt; không đoán.
- Tỷ giá đã dùng được lưu theo dòng (`ingest_rows.fx`, migration 0054), nên đọc lại bảng duyệt không gọi nguồn lần nữa.

## Tool `get_exchange_rate` cho agent chat

Kiến trúc đã chốt: OCR là pipeline backend nên gọi thẳng hàm; agent chat gọi qua AgentCore Gateway (MCP). Một hàm, một nguồn tỷ giá:

- **Hàm**: `yofina_core.fx` (chuyển nguyên từ `yofina_ingest.fx`, giữ hành vi và test; chỉ đổi tên logger thành `yofina.fx` và User-Agent thành `yofina/1.0`). Pipeline nạp import từ `yofina_core`; không còn bản trong `yofina_ingest` (test `test_tool_ty_gia_cua_agent_va_pipeline_nap_dung_chung_mot_ham`).
- **Tool**: `knowledge___get_exchange_rate`, cùng target và cùng Lambda `yofina-ledger` với `get_fee_schedule` (`gateway/tools/knowledge/yofina_knowledge/fx_rates.py`, nối ở `yofina_ledger/phase3.py` và `gateway_api.py`). Vào: `currency` (ISO 4217, khác VND), `date` (tùy chọn, mặc định ngày mô phỏng `app_today` của người gọi), `amount` (tùy chọn, số theo ngoại tệ, tối đa 4 chữ số lẻ; Gateway nhận kiểu `number` cho thuộc tính tool theo [Lambda function tool schema](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-lambda.md)). Ra (`ExchangeRateData` trong `contracts/tools/knowledge.results.schema.json`): `rate` (chuỗi thập phân như `IngestFx`), `rate_type` sell, `rate_source` vietcombank, `rate_date` (ngày của bảng đã dùng), `requested_date`, và khi có `amount` thì `amount_original` cùng `amount_vnd` làm tròn tới đồng.
- **Lỗi**: tham số sai hay ngoại tệ không có trong bảng là `PARAMS_INVALID`; nguồn không trả lời là `INTERNAL_ERROR` (lỗi tạm thời, agent thử lại một lần; bộ nhớ đệm giữ lỗi 10 phút nên lần thử lại không gọi nguồn). Chưa có mã riêng như `EXCHANGE_RATE_UNAVAILABLE` vì thêm mã phải sửa cả OpenAPI và `frontend/src/api/errors.ts`.
- **Mạng**: Lambda `yofina-ledger` cũng không gắn VPC (`tools-stack.ts`), nên ra internet như `yofina-ingest`; timeout của Lambda là 30 giây, một lần gọi nguồn hết giờ sau 4 giây và lỗi mạng không lùi ngày. Mỗi môi trường thực thi của ledger có bộ nhớ đệm riêng.
- **Cedar và CDK**: `gateway/policies/get_exchange_rate.cedar` (ép `user_id`, như `get_fee_schedule`). Danh sách tool của target lấy thẳng từ `contracts/tools/knowledge.json`, nên CDK không cần khai báo thêm; test `infra-cdk/test/agent-knowledge-target.test.ts` dựng cả `YofinaAgent` và khẳng định target có hai tool, mỗi tool một policy.
- **Agent** (`agent/src/yofina_agent/fx_chat.py`): router trích `currency` và `amount_original`, KHÔNG quy đổi. `Turn.flow` gọi tool ngay sau khi ghép câu cụt và trước khi hỏi lại ô thiếu, rồi đặt `params.amount_vnd` bằng `amount_vnd` của kết quả; mọi ý định dùng `amount_vnd` (what-if, kiểm tra trước khi chi, lộ trình) chạy như câu hỏi bằng VND. Kết quả tool vào `tool_log` nên NumericGrounding của Analyst nhận số từ đó như các tool khác; bản gọn `exchange_rate` (số đã định dạng) đi kèm dữ liệu của Analyst và người viết. Orchestrator đọc nhầm số ngoại tệ làm VND thì mã thay bằng số đã quy đổi (`whatif.with_converted_amount`). Câu hỏi chỉ về tỷ giá hay quy đổi là ý định `knowledge` có `currency`: câu trả lời dựng bằng mã từ kết quả tool, qua NumericGrounding trước khi phát. Tool lỗi thì khối `notice` với thông điệp của tool, không đoán số. Lý do chọn chỗ gắn: số tiền ngoại tệ là tham số của câu hỏi, không phải ý định; đổi ở một chỗ trước khi chia ý định là ít mã nhất và không thêm đường xử lý riêng.

## Rủi ro còn lại

- Endpoint JSON không có tài liệu hay cam kết công khai; Vietcombank có thể đổi đường dẫn hoặc định dạng. Khi đó dòng ngoại tệ rơi vào nhánh `rate_unavailable` (người dùng nhập số VND), không làm hỏng lần nạp. Log `fx_fetch_failed` và `fx_rate_unavailable` của Lambda `yofina-ingest` cho biết khi nào xảy ra.
- Nguồn dự phòng (fawazahmed0 hay ExchangeRate-API) chưa thêm: chúng là tỷ giá thị trường, khác giá bán của ngân hàng, và chủ dự án chưa quyết.
- Ký hiệu nhiều nghĩa (¥, "$" của nước khác) không đoán, trừ "$" và "US$" được hiểu là USD.
- Chat: câu cụt trả lời câu hỏi lại (ví dụ chỉ chọn cách trả) chỉ giữ ngoại tệ khi router đặt lại `currency` từ lịch sử; bộ đọc số bằng mã (`router._code_params`) không biết ngoại tệ và đọc "1200 USD" như 1.200 ₫. Agent chưa truyền `date` (luôn tỷ giá của ngày mô phỏng).
