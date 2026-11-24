# Tỷ giá cho chứng từ ngoại tệ khi nạp dữ liệu (F6)

Tra cứu ngày 24/11/2026 (giờ máy), nhánh `p5/ingest-fx`. Mã: [`pipelines/ingest/yofina_ingest/fx.py`](../../pipelines/ingest/yofina_ingest/fx.py). Hợp đồng: [contracts/README.md](../../contracts/README.md), mục "Chứng từ ngoại tệ và `INGEST_NO_TRANSACTIONS`".

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

Gọi thật một lần trong lúc làm (24/11/2026, `date=2026-11-10`): 200, `application/json; charset=utf-8`, `Count` 20, `Date` "2026-11-10T00:00:00", `UpdatedDate` "2026-11-10T23:00:00+07:00", mỗi ngoại tệ có `currencyCode`, `cash`, `transfer`, `sell` dạng chuỗi ("25790.00"). Ngoại tệ không mua tiền mặt có `cash` "0.00". Thử thêm hai ngày: Chủ nhật 08/11 vẫn có bảng (USD bán 25.780); ngày tương lai 30/12 trả `Count` 0, `Data` rỗng. Hóa đơn ca thật: 111,11 × 25.790 = 2.865.526,9, làm tròn thành **2.865.527 ₫**. Mẫu rút gọn của thân trả lời nằm trong `tests/unit/ingest/test_fx.py`.

## Chọn tỷ giá nào

Vietcombank công bố ba cột: Mua tiền mặt, Mua chuyển khoản, Bán. Khi chủ thẻ thanh toán bằng ngoại tệ, ngân hàng phát hành **bán** ngoại tệ cho chủ thẻ để trả tổ chức thẻ, nên dùng cột **Bán** (`sell`). Vietcombank không tách "bán tiền mặt" với "bán chuyển khoản"; cột Bán dùng chung. Số trên sao kê thẻ thường cao hơn vì còn phí chuyển đổi ngoại tệ theo biểu phí thẻ của ngân hàng phát hành, và thời điểm ghi nợ có thể lệch ngày. Vì vậy:

- Số VND là **ước tính**. Dòng ngoại tệ luôn vào hàng chờ duyệt (không bao giờ chọn sẵn), màn duyệt hiện số VND ngay, kèm dòng thu gọn "111,11 USD" mở ra tỷ giá, nguồn và ngày, và ô "Số VND sẽ ghi" để người dùng sửa theo sao kê thẻ trước khi chốt.
- Ngày tỷ giá là ngày giao dịch trên chứng từ (với hóa đơn thu tự động là ngày thu hoặc ngày đến hạn), không có thì ngày nạp (ngày mô phỏng `app_today`). Bảng chỉ có cho ngày đã qua hoặc hôm nay theo giờ Việt Nam thật, nên ngày sau hôm nay được kẹp về hôm nay; ngày chưa có bảng thì lùi từng ngày, tối đa 4 ngày. Ngày của bảng đã dùng được lưu ở `fx.rate_date`.
- Làm tròn tới đồng, nửa đồng làm tròn lên, tính bằng `Decimal`.

## Bộ nhớ đệm và lỗi

- Một lần gọi trả cả bảng của một ngày cho mọi ngoại tệ, nên bộ nhớ đệm theo ngày cũng là theo (tiền tệ, ngày). Bộ nhớ đệm nằm trong tiến trình Lambda: rẻ nhất, không cần bảng mới, không cần migration cho phần này. Bảng của ngày đã qua không đổi nên giữ tới khi môi trường thực thi tắt; bảng của hôm nay giữ 1 giờ (ngân hàng cập nhật trong ngày); lỗi hay ngày chưa có bảng giữ 10 phút để không gọi dồn. Một lần nạp gọi nguồn nhiều nhất 5 lần (ngày giao dịch và 4 ngày lùi), mỗi lần hết giờ sau 4 giây.
- Lỗi tra tỷ giá (mạng, hết giờ, trả lời lạ, ngoại tệ không có trong bảng): dòng vẫn vào hàng chờ với số gốc và `fx.status = rate_unavailable`, không có số VND. Người dùng nhập số VND trước khi chốt; không đoán.
- Tỷ giá đã dùng được lưu theo dòng (`ingest_rows.fx`, migration 0054), nên đọc lại bảng duyệt không gọi nguồn lần nữa.

## Rủi ro còn lại

- Endpoint JSON không có tài liệu hay cam kết công khai; Vietcombank có thể đổi đường dẫn hoặc định dạng. Khi đó dòng ngoại tệ rơi vào nhánh `rate_unavailable` (người dùng nhập số VND), không làm hỏng lần nạp. Log `fx_fetch_failed` và `fx_rate_unavailable` của Lambda `yofina-ingest` cho biết khi nào xảy ra.
- Nguồn dự phòng (fawazahmed0 hay ExchangeRate-API) chưa thêm: chúng là tỷ giá thị trường, khác giá bán của ngân hàng, và chủ dự án chưa quyết.
- Ký hiệu nhiều nghĩa (¥, "$" của nước khác) không đoán, trừ "$" và "US$" được hiểu là USD.
