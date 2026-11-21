# Spike: Aurora PostgreSQL Serverless v2 + Data API + pgvector + RLS (đo trên AWS thật)

Ngày chạy: 2026-11-21. Region `ap-southeast-1`. Mã, script, đầu ra thô: `spikes/aurora-data-api/` (thư mục `results/`). Manifest tài nguyên: `spikes/aurora-data-api/RESOURCES.md`.

Quy ước: **[Đo]** là số/kết quả chạy thật trong spike này; **[Suy luận]** là giải thích hoặc ngoại suy của tôi, chưa kiểm.

## 0. Tóm tắt

- **Data API đủ nhanh cho `affordability_check`.** Từ Lambda Python (arm64, 512 MB) ngoài VPC cùng Region, khi Aurora đang thức: một `ExecuteStatement` p50 = 12–52 ms, p95 ≤ 57 ms (trừ truy vấn trả 210 dòng: p95 42 ms). Luồng 3 truy vấn (số dư 7 hũ + dự báo 30 ngày × 7 hũ + giao dịch có lọc) chạy tuần tự: **p50 91 ms, p95 113 ms, max 179 ms** (100 lần, môi trường ấm). Ngân sách 2 giây còn dư khoảng 17 lần. [Đo]
- Với RLS đúng cách (có `set_config`), con số vẫn thấp: 3 truy vấn trong một transaction (Begin + set_config + 3 truy vấn + Commit = 6 lệnh gọi) p50 160 ms, p95 201 ms; bọc trong hàm plpgsql (1 lệnh gọi mỗi truy vấn) p50 93 ms, p95 106 ms. [Đo]
- **Rủi ro thật nằm ở auto-pause, không ở Data API**: lần gọi đầu sau pause mất **16,4 giây** mới thành công, và 4 lần đầu bị `DatabaseResumingException` (mỗi lần treo 2–4 giây). Client phải tự retry. [Đo]
- Hai nhận định trong ghi chú cũ cần sửa: (1) `FORCE ROW LEVEL SECURITY` **không** ép được master user của Aurora (xem mục 4); (2) mẹo "set_config trong CTE rồi SELECT" trong một lệnh **không đáng tin** (đúng với bảng nhỏ, sai với bảng có index). Nhận định "Data API reset phiên nên `set_config` phải nằm trong transaction" **được xác nhận**.

## 1. Dựng cluster

**Cách thử.** `aws rds create-db-cluster` + `create-db-instance` (CLI, `--region ap-southeast-1` ở mọi lệnh): engine `aurora-postgresql` **18.6** (bản mới nhất ở Region lúc chạy; tài liệu Data API ghi 18.3 trở lên và 17.4 trở lên), `db.serverless`, Serverless v2 min 0,5 / max 2 ACU, `--enable-http-endpoint`, `--manage-master-user-password`, `--no-publicly-accessible`, mã hóa lưu trữ, retention 1 ngày, subnet của VPC mặc định, security group mặc định của VPC mặc định (không mở inbound).

| Mốc | Thời gian [Đo] |
|---|---|
| Cluster ở trạng thái `available` (chưa có instance) | dưới khoảng 3 phút (quan sát thô, không đo chính xác) |
| Instance `available`, Data API dùng được | **429 giây (≈ 7 phút 9 giây)** từ lệnh tạo cluster |

Phát hiện:
- Region **không có DB subnet group tên `default`** (chỉ có một subnet group của stack khác ở VPC khác). Phải tạo `yofina-spike-db-subnets` từ 3 subnet của VPC mặc định. Khi viết CDK hãy cho `DatabaseCluster` tự tạo subnet group, đừng giả định có `default`. [Đo]
- `HttpEndpointEnabled = True` ngay khi tạo cluster; không cần bước bật riêng. Trường `SupportsHttpEndpoint` trong `describe-db-engine-versions` trả `null` cho aurora-postgresql nên **không dùng được để dò** phiên bản nào hỗ trợ Data API; phải đọc bảng trong tài liệu. [Đo]
- Aurora tạo secret master tên `rds!cluster-<uuid>` (không đặt được tiền tố), gắn sẵn vào cluster và bị xóa theo cluster. [Đo]
- PostgreSQL 18.6, pgvector **0.8.2** có sẵn (`pg_available_extensions`). Master user (`spikeadmin`) thuộc `rds_superuser` (không phải superuser thật). [Đo]

## 2. Độ trễ Data API (câu hỏi chính)

**Cách thử.** Schema `jars` (7 hũ × 3 user), `transactions` (6.000 dòng, 2.000/user, 90 ngày), `forecasts` (630 dòng = 3 user × 7 hũ × 30 ngày với p10/p50/p90), index `(user_id, jar_id, occurred_at DESC)`. Mỗi thao tác đo bằng `time.perf_counter()` quanh lệnh boto3 `rds-data` (đã tạo client trước, kết nối HTTPS giữ sẵn). Hai nơi chạy:
- (b) **Lambda `yofina-spike-db-bench`**: python3.13, arm64, 512 MB, không VPC, mỗi thao tác 100 lần (lần đầu đo riêng).
- (a) Máy local (Windows, từ Việt Nam đến Singapore) qua boto3, mỗi thao tác 60 lần.

Các thao tác: `select1`; `balances_jars` (đọc 7 dòng từ `jars`); `balances_agg` (`SUM(amount) GROUP BY jar_id` trên 2.000 dòng); `forecast_30x7` (210 dòng); `tx_filtered` (lọc theo user, hũ, 60 ngày, `LIMIT 50`); `flow3_plain` (3 truy vấn tuần tự: `balances_jars` + `forecast_30x7` + `tx_filtered`, mô phỏng `affordability_check`); `write_tx_2stmt` (`BeginTransaction` + `INSERT` + `UPDATE` + `CommitTransaction` = 4 lệnh gọi).

### 2.1 Lambda ngoài VPC, cùng Region (số có ý nghĩa), đơn vị ms, n = 100, môi trường ấm [Đo]

| Thao tác | p50 | p95 | max |
|---|---:|---:|---:|
| `select1` | 52,0 | 56,4 | 99,6 |
| `balances_jars` (7 hũ) | 52,1 | 56,2 | 122,8 |
| `balances_agg` (SUM trên 2.000 dòng) | 52,0 | 55,6 | 75,6 |
| `forecast_30x7` (210 dòng) | 24,0 | 41,6 | 129,8 |
| `tx_filtered` (50 dòng) | 14,1 | 16,0 | 59,4 |
| **`flow3_plain` (3 truy vấn tuần tự)** | **91,1** | **113,4** | **178,8** |
| `write_tx_2stmt` (4 lệnh gọi) | 120,8 | 128,4 | 244,7 |

Lần chạy thứ nhất (môi trường Lambda mới, cùng kịch bản) cho p50 gần như y hệt (select1 52,0 / flow3 87,1 / write 122,9). Chênh lệch nằm ở **lần gọi đầu**:

| Lần gọi đầu (ms) | Lambda môi trường mới (cold) | Lambda ấm, thao tác mới |
|---|---:|---:|
| `select1` (gồm TLS + kết nối tới endpoint Data API) | 199 | 10 |
| `balances_jars` | 52 | 51 |
| `forecast_30x7` | 22 | 25 |
| `flow3_plain` | 90 | 90 |
| `write_tx_2stmt` | 166 | 121 |

Kết luận phần "lạnh": thêm khoảng 150–190 ms ở lần gọi Data API đầu tiên của một execution environment mới (thiết lập kết nối HTTPS), sau đó như ấm. Thời gian khởi tạo Lambda (import boto3...) không nằm trong số này. [Đo]

### 2.2 Máy local qua boto3 (tham khảo, không đại diện cho Lambda), n = 60 [Đo]

| Thao tác | p50 | p95 | max | lần đầu |
|---|---:|---:|---:|---:|
| `select1` | 51,0 | 54,9 | 90,9 | 183 |
| `balances_jars` | 52,8 | 56,2 | 146,3 | 54 |
| `balances_agg` | 53,4 | 60,5 | 88,5 | 58 |
| `forecast_30x7` | 64,4 | 73,1 | 220,1 | 93 |
| `tx_filtered` | 55,0 | 81,4 | 190,1 | 52 |
| `flow3_plain` | 170,4 | 201,5 | 331,3 | 175 |
| `write_tx_2stmt` | 203,2 | 291,6 | 339,1 | 217 |

Từ Việt Nam thêm khoảng 40 ms mỗi lệnh gọi với các phản hồi lớn (so `tx_filtered` 55 ms với 14 ms trong Lambda). Với phản hồi nhỏ thì hai nơi gần như bằng nhau vì hiện tượng ở 2.3. [Đo + Suy luận]

### 2.3 Phát hiện: phản hồi nhỏ chịu thêm khoảng 40 ms (sàn thực của Data API khoảng 9–12 ms)

Trong Lambda, `select1`, `balances_jars`, `tx_filtered LIMIT 1`, `INSERT` trong transaction đều dừng ở **p50 52,0–52,1 ms với độ lệch rất nhỏ**, còn `tx_filtered` (50 dòng) chỉ 14 ms, `BeginTransaction` 8 ms, `Commit` 10,8 ms. Thăm dò thêm [Đo, Lambda ấm, p50 ms]:

| Biến thể | p50 |
|---|---:|
| `SELECT 1` | 52,0 |
| `SELECT 1, repeat('x',200)` | 52,0 |
| `SELECT 1, repeat('x',900)` | 52,0 |
| `SELECT 1, repeat('x',1200)` | 52,1 |
| `SELECT 1, repeat('x',1500)` | **8,9** |
| `SELECT 1, repeat('x',2000)` | 9,0 |
| `SELECT 1, repeat('x',3000)` | 9,8 |
| yêu cầu có comment SQL 3 KB, phản hồi nhỏ | 52,1 |
| `jars` có thêm cột `repeat('x',3000)` | 12,2 |
| `BeginTransaction` / `CommitTransaction` | 8,1 / 10,8 |

Ngưỡng nằm giữa 1.200 và 1.500 byte phản hồi; kích thước **yêu cầu** không ảnh hưởng. Đặt `TCP_QUICKACK` trên socket phía client không đổi gì (52,1). **[Suy luận]**: đây là kiểu "Nagle + delayed ACK" (server gửi header và body riêng; phản hồi dưới khoảng 1 MSS bị giữ khoảng 40 ms). Tôi chưa chứng minh được nguyên nhân ở tầng TCP, chỉ có quy luật đo được ở trên.

Ý nghĩa thực dụng: thêm một cột đệm (ví dụ `repeat(' ', 1500) AS _pad`) vào truy vấn nhỏ trên đường nóng đưa p50 từ 52 xuống khoảng 9–12 ms. **Không cần cho mục tiêu 2 giây** (đã dư rất nhiều), chỉ nên áp dụng nếu sau này cần tiết kiệm độ trễ; ghi lại để khỏi ngạc nhiên khi thấy 52 ms "đẹp quá mức".

### 2.4 Kết luận độ trễ cho Yofina

- **Dùng Data API cho mọi tool Lambda, kể cả `affordability_check`.** Luồng kiểm tra trước khi quẹt cần 2–3 truy vấn: 91 ms p50 / 113 ms p95 / 179 ms max (ba lệnh tuần tự). Có thể gộp lại (một truy vấn nhiều CTE trả 7 hũ + dự báo) còn 1 lệnh gọi ≈ 25–55 ms [Suy luận từ số đo từng lệnh]. Đường ghi (transaction 2 câu) ≈ 121 ms p50 / 128 p95.
- **Không có luồng nào cần kết nối trực tiếp (psycopg + VPC)** về mặt độ trễ. Lý do duy nhất còn lại để dùng kết nối trực tiếp là trả về >1 MiB mỗi lần (xem mục 5) hoặc cần tính năng Data API không hỗ trợ (kiểu `interval`, nhiều câu lệnh trong một lần gọi).
- Phần còn lại của p95 < 2 giây sẽ do **cold start Lambda, AgentCore, Bedrock** quyết định, không phải Data API. Ngân sách Aurora cho đường nóng nên tính khoảng **0,2–0,3 giây**, kể cả cold của lần gọi đầu trên một execution environment. [Suy luận]
- Điều kiện bắt buộc: Aurora không được ở trạng thái pause trong lúc chấm điểm (mục 6).

## 3. pgvector qua Data API

**Cách thử.** `CREATE EXTENSION vector`; bảng `docs(id serial, user_id text, content text, embedding vector(1024))`; chỉ mục HNSW `vector_cosine_ops (m=16, ef_construction=64)`; chèn 300 vector ngẫu nhiên 1024 chiều bằng `BatchExecuteStatement` (50 tham số mỗi lần); truy vấn `<=>` top 5. Script: `t_vector.py`. Đầu ra: `results/vector.txt`.

Kết quả [Đo]:

| Hạng mục | Kết quả |
|---|---|
| Phiên bản pgvector | **0.8.2** (Aurora PG 18.6) |
| Tạo chỉ mục HNSW trên bảng rỗng | 52–90 ms |
| `INSERT ... VALUES (:emb)` (tham số chuỗi không cast) | **Lỗi**: `column "embedding" is of type vector but expression is of type text` |
| `CAST(:emb AS vector)` với chuỗi `'[0.1,0.2,...]'` | **Chạy** |
| `:emb::vector` | **Chạy** (Data API chấp nhận cú pháp `::` sau tham số có tên) |
| Sai số chiều (`'[1,2,3]'` vào `vector(1024)`) | Lỗi rõ: `expected 1024 dimensions, not 3` |
| Chèn 300 vector × 1024 chiều (6 batch × 50) | 1.223–1.474 ms tổng (khoảng 4–5 ms mỗi vector) |
| Đọc cột `vector` ra | `stringValue` dạng `'[-0.58,...]'` (khoảng 9,6 KB mỗi vector 1024 chiều); `columnMetadata.typeName = "vector"` (chỉ có khi truyền `includeResultMetadata=True`) |
| Truy vấn kNN top 5, 1024 chiều, 302 dòng, tham số 9,6 KB | Lambda ấm p50 **51,3** ms, p95 55,7, max 86,1 (n=60); local p50 50,5, p95 89,5 |
| Lọc theo user + kNN | Chạy (5 dòng) |
| Kế hoạch | Với 302 dòng planner chọn Sort + Seq Scan; khi tắt `enable_seqscan` thì dùng `Index Scan using docs_hnsw` (xác nhận chỉ mục dùng được) |

Số 51 ms của kNN là sàn "phản hồi nhỏ" ở mục 2.3 cộng truy vấn gần như tức thì trên 302 dòng, nên **không rút ra được độ trễ kNN ở quy mô lớn** từ spike này. Mẫu chạy được:

```python
def vec_param(v):  # v: list[float] -> chuỗi pgvector
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"

sql = ("SELECT id, content, embedding <=> CAST(:q AS vector) AS dist "
       "FROM docs WHERE user_id = :u ORDER BY embedding <=> CAST(:q AS vector) LIMIT 5")
rds.execute_statement(resourceArn=C, secretArn=S, database="spike", sql=sql,
    parameters=[{"name": "q", "value": {"stringValue": vec_param(q)}},
                {"name": "u", "value": {"stringValue": "user-a"}}])
# chèn hàng loạt
rds.batch_execute_statement(resourceArn=C, secretArn=S, database="spike",
    sql="INSERT INTO docs (user_id, content, embedding) VALUES (:u, :c, CAST(:e AS vector))",
    parameterSets=[[{"name":"u","value":{"stringValue":u}}, {"name":"c","value":{"stringValue":c}},
                    {"name":"e","value":{"stringValue":vec_param(e)}}] for u, c, e in rows])
```

## 4. Row-level security

**Cách thử.** `ENABLE ROW LEVEL SECURITY` + policy `USING (user_id = current_setting('app.user_id', true)) WITH CHECK (...)` trên 3 bảng. Role `yofina_app` (`LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`, **không phải owner**, chỉ có `GRANT SELECT/INSERT/UPDATE/DELETE`), secret riêng `yofina-spike-db-app` `{"username","password"}`; Data API dùng role nào là do **secret truyền vào mỗi lệnh gọi** quyết định. Script: `t_rls.py`, `t_rls2.py`, `setup_rls_fn.py`; đầu ra `results/rls*.txt`.

Kết quả [Đo]:

| # | Thử | Kết quả |
|---|---|---|
| 1 | Role app, không `set_config` | `count(*)` = **0** (policy ra NULL, an toàn mặc định) |
| 2 | `set_config(..., true)` **ngoài** transaction rồi gọi `SELECT` riêng | 0 dòng; `current_setting` = `''`. Giá trị không sống sang lệnh sau |
| 3 | `set_config(..., false)` (cấp phiên) rồi gọi `SELECT` riêng, lặp 30 lần | **0 lần rò rỉ**: Data API reset phiên giữa các lần gọi |
| 4 | Trong `BeginTransaction`: `set_config('app.user_id','user-a',true)` rồi đọc | `jars` 7, `transactions` 2.000, `forecasts` 210; `WHERE user_id='user-b'` ra **0** (A không đọc được B) |
| 5 | Trong transaction của A: `INSERT` hộ user-b | **Lỗi** `new row violates row-level security policy` (WITH CHECK hoạt động) |
| 6 | Transaction mới sau khi commit | `current_setting` = `''`, đọc ra 0 dòng (không rò sang transaction sau) |
| 7 | Role app: `ALTER TABLE jars DISABLE ROW LEVEL SECURITY` | Lỗi `must be owner of table jars` |
| 8 | Master user `spikeadmin` (owner, `rds_superuser`), không `set_config` | thấy **21/21** dòng (owner bỏ qua RLS như kỳ vọng) |
| 9 | Master user **sau `FORCE ROW LEVEL SECURITY`**, kể cả khi đã `set_config('app.user_id','user-a',true)` | **vẫn thấy cả 3 user** (`relforcerowsecurity = true`, `rolbypassrls = false`, nhưng RLS vẫn không áp) |
| 10 | Role app tự khai `set_config(...,'user-b')` | thấy dữ liệu của B: RLS chỉ bảo vệ khi **code tin cậy** là bên đặt `app.user_id` |

**Bị bác bỏ so với ghi chú cũ:** dòng `ALTER TABLE ... FORCE ROW LEVEL SECURITY; -- chủ bảng cũng bị áp` không đúng với master user của Aurora/RDS: nó bỏ qua RLS ngay cả khi FORCE (dòng 9). [Suy luận: `rds_superuser` được xử lý như superuser trong kiểm tra RLS của RDS]. Hệ quả: **mọi tool phải dùng secret của role `yofina_app`, không dùng secret master**; migrator mới dùng master. Lambda tool không được cấp quyền đọc secret master.

**Xác nhận:** nhận định "set_config phải nằm trong cùng transaction" đúng. Ngoài transaction thì kể cả `is_local=false` cũng mất sạch.

### 4.1 Mẹo "một lệnh duy nhất" bằng CTE: **không dùng**

`WITH s AS (SELECT set_config('app.user_id', :u, true)) SELECT ... FROM jars, s` trả đúng cho bảng `jars` nhỏ (quét tuần tự) nhưng trả **0 dòng** cho `transactions`/`forecasts` và cho truy vấn có lọc theo index (kết quả `isNull` ở cả 7 thử). Lý do **[Suy luận]**: hàm STABLE trong policy được tính một lần khi bắt đầu quét index, trước khi CTE chạy. Thêm nữa, thứ tự này không được PostgreSQL bảo đảm. Câu lệnh nhiều dấu `;` bị Data API từ chối: `ValidationException: Multistatements aren't supported`.

### 4.2 Hai cách đúng, có số đo (Lambda ấm, n = 100, ms)

| Cách | Lệnh gọi mỗi truy vấn | `balances` p50 / p95 | `flow3` (3 truy vấn) p50 / p95 | max flow3 |
|---|---|---|---|---:|
| Không RLS, `WHERE user_id = :u` (owner) | 1 | 52,1 / 56,2 | 91,1 / 113,4 | 178,8 |
| **RLS qua transaction** (Begin, `set_config`, truy vấn, Commit) | 4 (flow3: 6 lệnh gọi, các truy vấn dùng chung 1 transaction) | 119,8 / 128,6 | 160,4 / 201,3 | 250,1 |
| **RLS qua hàm plpgsql** `SECURITY INVOKER` | 1 | 52,1 / 55,8 | **92,9 / 105,5** | 150,5 |

Cách hàm plpgsql: hàm gọi `PERFORM set_config('app.user_id', p_user, true)` rồi `RETURN QUERY SELECT ...` (mỗi câu trong plpgsql lập kế hoạch sau câu trước nên policy thấy giá trị mới); vì `SECURITY INVOKER`, RLS vẫn áp theo role gọi. Kiểm chứng: gọi `rls_jars('user-a')` trả 7, `rls_forecast` trả 210 (tức đã lọc đúng user, không phải 630), `rls_txs` trả 50; không gọi hàm thì app thấy 0 dòng. **Khuyến nghị: dùng hàm cho đường đọc nóng; dùng transaction tường minh cho đường ghi.** Chi phí RLS qua hàm gần như bằng 0 so với không RLS.

```sql
-- chạy bằng master (migrator)
CREATE OR REPLACE FUNCTION rls_jars(p_user text) RETURNS TABLE(code text, balance numeric)
LANGUAGE plpgsql AS $$ BEGIN
  PERFORM set_config('app.user_id', p_user, true);
  RETURN QUERY SELECT j.code, j.balance FROM jars j ORDER BY j.code;
END $$;
GRANT EXECUTE ON FUNCTION rls_jars(text) TO yofina_app;

ALTER TABLE jars ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_iso ON jars
  USING (user_id = current_setting('app.user_id', true))
  WITH CHECK (user_id = current_setting('app.user_id', true));
```

```python
# đường ghi: transaction tường minh, secret của role app
tx = rds.begin_transaction(resourceArn=C, secretArn=APP_SECRET, database="spike")["transactionId"]
rds.execute_statement(resourceArn=C, secretArn=APP_SECRET, database="spike", transactionId=tx,
    sql="SELECT set_config('app.user_id', :u, true)", parameters=[{"name":"u","value":{"stringValue":uid}}])
rds.execute_statement(resourceArn=C, secretArn=APP_SECRET, database="spike", transactionId=tx,
    sql="INSERT INTO transactions (user_id, jar_id, amount, occurred_at) VALUES (:u, :j, :a, now())", parameters=[...])
rds.commit_transaction(resourceArn=C, secretArn=APP_SECRET, transactionId=tx)
```

Cạm bẫy đã vấp: một `BeginTransaction` bị bỏ dở (không commit/rollback) giữ khóa bảng và chặn `ALTER TABLE` cho tới khi Data API tự hủy (khoảng 3 phút; tôi phải `pg_terminate_backend`). Luôn có `try/finally rollback_transaction` trong code tool.

## 5. Giới hạn và kiểu dữ liệu

### 5.1 Phản hồi 1 MiB [Đo]

| Truy vấn | Kết quả |
|---|---|
| 500 dòng × 1.000 ký tự (≈ 0,48 MiB) | OK |
| 900 dòng × 1.000 ký tự (≈ 0,86 MiB) | OK |
| 1.100 dòng × 1.000 ký tự (≈ 1,05 MiB) | **Lỗi** `UnsupportedResultException: The result exceeds the size limit 1 MB.` |
| 3.000 dòng; một dòng 1,2 MB; `formatRecordsAs=JSON` | cùng lỗi |
| Dự báo 210 dòng, giao dịch 50 dòng | OK, nhỏ |

Không có dữ liệu trả một phần: cả lệnh gọi thất bại. Cần phân trang (`LIMIT/OFFSET` hoặc keyset) cho mọi truy vấn có thể lớn (lịch sử giao dịch, đọc vector). Một vector 1024 chiều đọc ra khoảng 9,6 KB nên một lần gọi đọc được tối đa khoảng 100 vector. [Suy luận từ số đo trên]

### 5.2 `BatchExecuteStatement` [Đo]

- 1.000 bộ tham số trong một lệnh (INSERT vào `transactions`): 278–350 ms. Nhanh hơn nhiều so với 1.000 lệnh riêng lẻ (ước tính ≥ 14 giây nếu mỗi lệnh ≥ 14 ms; không đo).
- **1.001 bộ tham số vẫn chạy** (không gặp giới hạn 1.000 như nhiều người nhớ); giới hạn thực sự nhiều khả năng nằm ở kích thước yêu cầu (chưa thử tới biên).
- Batch trong transaction rồi rollback: hoạt động (200 dòng; sau rollback không còn dòng nào của batch).
- Phản hồi của batch là `updateResults` theo từng bộ tham số.

### 5.3 Kiểu dữ liệu trả về (mặc định) [Đo]

| Kiểu PG | Dạng Data API trả | Ví dụ |
|---|---|---|
| `numeric(14,0)`, `numeric(20,4)` | `stringValue` (giữ nguyên độ chính xác) | `'100000'`, `'12345678901234.5678'` |
| `timestamptz` | `stringValue`, **múi giờ UTC, không có hậu tố** | `'2026-11-21 02:13:37.658608'` |
| `date` | `stringValue` | `'2026-11-21'` |
| `jsonb` | `stringValue` chứa JSON | `'{"a":1,"b":[1,2]}'` (phải `json.loads`) |
| `bool` | `booleanValue` | |
| `int8` (bigint) | `longValue` | `9223372036854775807` |
| `float8` | `doubleValue` | |
| `uuid` | `stringValue` | |
| `int4[]` | `arrayValue.longValues` | |
| `bytea` | `blobValue` (bytes) | |
| `vector` | `stringValue` | `'[0.1,0.2,...]'` |
| `interval` | **Lỗi** `UnsupportedResultException: ... unsupported data type INTERVAL` | cast `::text` |

- `resultSetOptions={"decimalReturnType": "DOUBLE_OR_LONG"}` đổi `numeric` thành `doubleValue`/`longValue` (không nên dùng cho tiền; dù `numeric(14,0)` VND vẫn là số nguyên nhưng sẽ thành `longValue` khi không có phần thập phân). `longReturnType=STRING` đổi bigint thành chuỗi.
- `formatRecordsAs="JSON"` trả `formattedRecords` là chuỗi JSON mảng object theo tên cột (tiện hơn nhiều so với mảng `{"stringValue":..}`); `numeric` và `timestamptz` ở đó vẫn là chuỗi; `jsonb` thành chuỗi JSON lồng trong chuỗi (cần parse 2 lần).
- Tham số: **không tự ép kiểu chuỗi**. `WHERE now() > :t` với `stringValue` báo `operator does not exist: timestamp with time zone > text`; phải `CAST(:t AS timestamptz)` (hoặc `typeHint`: `TIMESTAMP`, `DECIMAL`, `JSON`, `UUID`, `DATE`, `TIME`). `CAST(:j AS jsonb)` hoạt động. `typeHint=DECIMAL` với `'12.50'` + 1 trả `'13.50'`.

## 6. Auto-pause (min 0 ACU)

**Cách thử.** `modify-db-cluster --serverless-v2-scaling-configuration MinCapacity=0,MaxCapacity=2,SecondsUntilAutoPause=300` (300 giây là tối thiểu theo tài liệu), để rảnh, theo dõi CloudWatch `ServerlessDatabaseCapacity` (script `wait_pause.py`), rồi gọi Data API từ Lambda ngoài VPC (môi trường mới) với vòng retry cách nhau 1 giây (`lambda_function.py`, mode `wake`).

Kết quả [Đo]:

| Mốc | Giá trị |
|---|---|
| Từ lúc đổi cấu hình tới khi capacity về 0,0 | **613 giây (≈ 10 phút 13 giây)** (cluster đang ở 1,5 ACU sau tải đo; mất khoảng 7 phút để tụt về 0,5, rồi 300 giây rảnh mới pause) |
| Lần gọi Data API đầu tiên sau pause (Lambda) | 4 lần liên tiếp `DatabaseResumingException` (mỗi lần treo 4,0 / 3,3 / 2,1 / 2,0 giây), lần thứ 5 thành công sau 0,9 giây |
| **Tổng thời gian tới lần thành công đầu tiên** | **16,4 giây** (gồm 4 lần nghỉ 1 giây) |
| 5 lần gọi kế tiếp | 81, 52, 52, 52, 51 ms (hoạt động bình thường ngay) |

Thông điệp lỗi: `The Aurora DB instance db-... is resuming after being auto paused.` Phát hiện:
- **Data API KHÔNG tự chờ resume**: nó trả `DatabaseResumingException` và client phải retry. Nhận định cũ "Data API tự đánh thức Aurora" đúng một nửa: nó đánh thức, nhưng lệnh gọi đầu thất bại, không phải chỉ chậm. boto3 mặc định không retry loại lỗi này (đã thấy lỗi trả thẳng ra). Mọi tool phải có vòng retry riêng (khoảng 20 giây tổng) hoặc, hợp lý hơn, **giữ min 0,5 ACU trong cửa sổ demo**. [Đo]
- Số 16,4 giây khớp tài liệu ("khoảng 15 giây"). Đo một lần duy nhất (n = 1), pause ngắn (khoảng 1 phút), chưa đo pause dài (> 24 giờ, tài liệu nói 30 giây trở lên).
- Instance không bật Enhanced Monitoring/Performance Insights (MonitoringInterval 0, PI tắt) nên không bị chặn pause; sự kiện `max_wal_senders ... adjusted from 10 to 20` xuất hiện sau khi đổi cấu hình, vô hại với pause ở lần này.

## 7. Kết luận cho Yofina

1. **Data API cho mọi tool Lambda, luồng nóng cũng vậy.** Không cần psycopg trong VPC, không cần NAT/endpoint cho Aurora. Số đo: 1 lệnh 12–52 ms, flow 3 truy vấn p95 113 ms, ghi qua transaction p95 128 ms.
2. **Min 0,5 ACU trong lúc demo/chấm điểm; min 0 chỉ cho dev**, và code tool vẫn nên retry `DatabaseResumingException` (tối đa 3–4 lần, nghỉ 1–2 giây) vì cluster có thể bị đánh thức/ pause ở môi trường khác.
3. **RLS: dùng role `yofina_app` (non-owner) + secret riêng cho Lambda tool; master chỉ cho migrator.** Đường đọc: hàm plpgsql `SECURITY INVOKER` có `set_config(..., true)` bên trong (1 lệnh gọi); đường ghi: `BeginTransaction` → `set_config` → câu lệnh → `Commit`. Không dùng CTE `set_config` một lệnh. Vẫn giữ `WHERE user_id = :uid` do code ép, RLS chỉ là lớp phụ (vì app tự khai được `app.user_id`).
4. **pgvector qua Data API chạy**: `CAST(:q AS vector)` với chuỗi `'[...]'` (hoặc `:q::vector`); đọc vector ra là chuỗi; chèn hàng loạt qua `BatchExecuteStatement`. Mỗi vector 1024 chiều ≈ 9,6 KB trên đường truyền, nên chặn số vector trả về mỗi lần dưới khoảng 100.
5. **Mọi truy vấn có thể trả nhiều dòng phải có `LIMIT`** (1 MiB cứng, lỗi cả lệnh). Cast `interval` sang text; `numeric`/`timestamptz` đến dưới dạng chuỗi nên lớp truy cập phải parse (dùng `Decimal` cho tiền; `timestamptz` là UTC không hậu tố).
6. Thiết kế lớp truy cập: một hàm duy nhất dựng tham số (kèm `CAST` cho vector/jsonb/timestamptz), parse kết quả theo `columnMetadata` hoặc dùng `formatRecordsAs="JSON"`, retry resume, luôn rollback transaction trong `finally`.

## 8. Điều chưa thử được

- Pause dài (> 24 giờ) và số đo resume lặp lại (chỉ có 1 mẫu 16,4 giây).
- Độ trễ kNN và HNSW với quy mô thật (chục nghìn vector trở lên); recall của HNSW so với quét tuần tự; iterative scan (pgvector 0.8) với lọc theo `user_id`.
- Độ trễ Data API khi nhiều Lambda gọi đồng thời (đo này tuần tự, một luồng); throttling của `rds-data`.
- Ảnh hưởng của scale ACU: tải đo đẩy cluster lên 1,5 ACU, chưa so sánh độ trễ ở 0,5 ACU lúc rảnh với lúc đang scale.
- Cold start Lambda đầy đủ (init Python + boto3) cộng lần gọi Data API đầu; chỉ đo phần Data API (150–190 ms thêm).
- Nguyên nhân tầng TCP của hiện tượng +40 ms (mục 2.3); ngưỡng chính xác (giữa 1.200 và 1.500 byte) và việc có đổi theo Region/phiên bản không.
- Giới hạn tối đa của `BatchExecuteStatement` (kích thước yêu cầu), giới hạn thời gian 45 giây của lệnh, thời hạn transaction 3 phút (chỉ quan sát gián tiếp).
- IAM database authentication, Data API với secret xoay vòng, `ManageMasterUserPassword` + rotation.
- Ảnh hưởng chi phí của chế độ IO-Optimized, Data API trên Aurora MySQL.
- Aurora PG 17.x (đo trên 18.6); khác biệt hiệu năng giữa 17 và 18 chưa kiểm.

## 9. Tài nguyên đã tạo và trạng thái dọn

Chi tiết từng tài nguyên và lệnh xóa: `spikes/aurora-data-api/RESOURCES.md`. Tiền tố `yofina-spike-db-`, tag `project=yofina-spike`. Đã tạo: 1 DB subnet group, 1 cluster Aurora, 1 instance serverless, secret master (do RDS tạo), 1 secret role app, 1 IAM role + inline policy, 1 Lambda, 1 log group. Không tạo VPC/NAT/RDS Proxy/access key.

**Trạng thái dọn: đã xóa sạch và đã liệt kê lại để xác nhận** (instance, cluster với `--skip-final-snapshot --delete-automated-backups`, subnet group, 2 secret, Lambda, IAM role, log group; không còn snapshot hay automated backup). Chỉ còn `<cluster có sẵn>` và secret `<secret có sẵn>` là tài nguyên có sẵn của người khác, không đụng tới. Chi tiết ở cuối `RESOURCES.md`. Xóa instance serverless mất khoảng 10 phút, xóa cluster thêm vài phút.

Chi phí ước tính (từ giờ tạo đến giờ xóa, khoảng 55 phút tuổi cluster): Aurora 0,5–1,5 ACU × ≈ 0,8 giờ × 0,20 USD ≈ 0,15–0,25 USD; lưu trữ + I/O + backup 1 ngày không đáng kể; Secrets Manager prorated vài xu; Lambda và log trong mức miễn phí. **Tổng khoảng 0,3–0,6 USD** (ước tính, chưa đối chiếu hóa đơn).
