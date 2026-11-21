# Dữ liệu, sự kiện/batch, hạ tầng và bảo mật trên AWS (ngoài AgentCore và Bedrock)

Ghi chú nghiên cứu cho Yofina Foresight, truy cập tài liệu ngày 2026-11-21. Quy ước nhãn nguồn: **[TL]** = đã đọc trong tài liệu chính thức AWS; **[BL]** = blog, repo mẫu, trang cộng đồng hoặc kết quả web search chưa mở trang gốc; **[API]** = giá lấy từ AWS Price List API qua connector AWS MCP (chỉ đọc); **[SĐ]** = suy đoán/kiến thức nền, cần chạy thử; **[chưa tìm được]**. Không ghi account ID. Phần AgentCore và Bedrock do agent khác lo, ở đây chỉ chạm tới chỗ giao nhau.

## 1. Câu hỏi cần trả lời

1. Aurora PostgreSQL Serverless v2 + pgvector: phiên bản, scale về 0 ACU và thời gian resume so với mục tiêu p95 < 2 giây; Data API / RDS Proxy / kết nối trực tiếp; IAM auth, Secrets Manager; HNSW; row-level security; migration; chi phí tối thiểu; so với Aurora DSQL và RDS thường.
2. Lambda Python: runtime, Powertools, đóng gói thư viện ML nặng, cold start, Lambda trong VPC, làm target cho AgentCore Gateway.
3. Sự kiện: EventBridge → SQS + DLQ → Lambda idempotent, partial batch, retry; Scheduler 02:00 giờ Việt Nam và nhắc một lần theo người dùng.
4. Step Functions: pipeline đêm, Standard hay Express, Distributed Map, lỗi/retry, gọi SageMaker hay Lambda container.
5. Hạ tầng chạy Chronos-2: serverless/async/batch transform/endpoint tắt/ Lambda container/Fargate.
6. CDK: ngôn ngữ, cấu trúc stack, bootstrap, L2 cho AgentCore, cdk-nag, secret, GitHub Actions OIDC, thay root bằng role deploy.
7. Frontend hosting và định danh: Amplify (SSR hay static), WAF, Cognito, JWT gọi AgentCore Runtime từ trình duyệt, CORS.
8. Bảo mật và quan sát: KMS, mã hóa, CloudTrail, CloudWatch, Budgets; danh sách thứ tốn tiền khi nhàn rỗi.
9. Mọi dịch vụ có ở `ap-southeast-1` không.

## 2. Kết luận ngắn: làm thế này

- **Region: giữ `ap-southeast-1`** và đặt `env: { account, region }` tường minh trong CDK. Mọi dịch vụ chính có ở đây (mục 9). Cái giá phải trả: ACU Aurora đắt hơn us-east-1 khoảng 1,7 lần (0,20 so với 0,12 USD/ACU-giờ) [API].
- **Aurora PostgreSQL 17.x** (hoặc 16.3+), Serverless v2, bật Data API, `enableDataApi: true`, mã hóa lưu trữ bật. pgvector đi kèm (0,8.x trên 17/18) [TL].
- **Auto-pause (min 0 ACU): chỉ dùng cho môi trường dev.** Resume thường ~15 giây, nằm ngoài ngân sách 2 giây; để quá 24 giờ thì 30 giây trở lên [TL]. Cho cửa sổ demo/chấm điểm đặt `min = 0.5` (và có thể 1). Aurora 0,5 ACU chạy liên tục ở Singapore ≈ 73 USD/tháng [API+tính].
- **Kết nối: dùng RDS Data API cho mọi Lambda** (tool, event, batch). Lambda không cần vào VPC, không cần NAT, không cần VPC endpoint, Data API tự đánh thức Aurora đang pause [TL]. **Không dùng RDS Proxy**: proxy giữ kết nối mở nên Aurora không bao giờ pause [TL]. Điều kiện: đo độ trễ Data API trên đường nóng (`affordability_check`); nếu không đạt, chỉ riêng Lambda đó chuyển sang psycopg trong VPC. **[Đã chạy thử 2026-11-21]** Điều kiện đã đạt: từ Lambda ngoài VPC cùng Region, 3 truy vấn tuần tự p50 91 ms, p95 113 ms, max 179 ms; không cần psycopg/VPC. Chi tiết: `docs/research/spike-aurora-data-api.md`. Lưu ý đi kèm: Data API **không** tự chờ resume (xem dòng auto-pause).
- **Tách dữ liệu theo người dùng 2 lớp**: mọi truy vấn có `WHERE user_id = :uid` do code tool ép, cộng RLS làm lớp phòng thủ thứ hai. Với Data API, đặt `set_config('app.user_id', :uid, true)` trong cùng một transaction [SĐ, cần thử]. **[Đã chạy thử 2026-11-21]** Xác nhận: ngoài transaction thì mất (kể cả `is_local=false`, 0/30 lần rò rỉ); trong transaction thì user A không đọc được B. Có cách rẻ hơn: hàm plpgsql `SECURITY INVOKER` có `set_config` bên trong (1 lệnh gọi, p50 flow 3 truy vấn 93 ms so với 160 ms của transaction tường minh). Chi tiết: `spike-aurora-data-api.md` mục 4.
- **Migration: file SQL đánh số + một Lambda migrator nhỏ chạy qua Data API** (bảng `schema_migrations`). Không cần Flyway/Alembic cho 3 tuần.
- **Không đổi sang Aurora DSQL** (không có pgvector, không PL/pgSQL, tối đa 3.000 dòng mỗi transaction, collation `C`) và **không đổi sang RDS thường** trừ khi ngân sách chặt (RDS `db.t4g.small` ≈ 37 USD/tháng, nhưng mất Data API và mất scale-down).
- **Lambda Python 3.13** (hoặc 3.14; `3.15` cũng đã có) trên Amazon Linux 2023, `arm64` cho Lambda zip, **`x86_64` cho Lambda container build trên Windows**. Powertools dùng qua Lambda layer của AWS (bản 44 lúc đọc, có `python313`/`python314`, `ap-southeast-1`).
- **Thư viện ML nặng (torch, Chronos-2, StatsForecast, OR-Tools, ruptures, PyOD) → Lambda container image** (tối đa 10 GB, 10 GB RAM, timeout tới 30 phút theo trang quota hiện hành). Zip + layer chỉ 250 MB sau giải nén nên không đủ [TL].
- **Chronos-2: chạy trong Lambda container, không dùng SageMaker ở MVP.** Model 120M tham số, nhẹ; số liệu bên thứ ba: 7.000 chuỗi mất ~40 giây trên CPU 32 vCPU [BL]. Demo chỉ vài trăm chuỗi. SageMaker Serverless Inference là lối thoát (CPU, tối đa 6 GB RAM, không GPU, không VPC) [TL].
- **Sự kiện: bus riêng → rule → SQS (+DLQ) → Lambda** với Powertools `BatchProcessor` + `idempotent_function` (DynamoDB on-demand), `ReportBatchItemFailures`, visibility timeout ≥ 6 × timeout hàm.
- **Lịch: EventBridge Scheduler** `cron(0 2 * * ? *)` múi giờ `Asia/Ho_Chi_Minh` → Step Functions Standard. Nhắc theo người dùng: schedule `at(...)` có `ActionAfterCompletion=DELETE`. Hiện đã có L2 `aws_scheduler` và `aws_scheduler_targets` trong `aws-cdk-lib` [TL].
- **Step Functions Standard**; Map inline (≤ 40 song song) trên các **khối** người dùng, không cần Distributed Map cho quy mô demo. Chỉ truyền ID, kết quả ghi thẳng vào Aurora (giới hạn payload 256 KiB).
- **CDK bằng TypeScript**; L2 `aws-cdk-lib/aws-bedrockagentcore` đã **stable** (không cần gói `-alpha`), riêng submodule Policy vẫn alpha [TL]. Một CDK app, 5–6 stack, stateful tách riêng, `cdk-nag` + `--strict` trong CI.
- **Thay root**: tạo người dùng quản trị bằng IAM Identity Center (hoặc IAM user có MFA), bootstrap bằng người đó; CI dùng GitHub OIDC + role chỉ có quyền `sts:AssumeRole` vào các role bootstrap của CDK. Chi tiết mục 6.5.
- **Frontend: Next.js static export (hoặc SPA) trên Amplify Hosting**, không SSR. Trình duyệt gọi AgentCore Runtime trực tiếp bằng Bearer JWT của Cognito. Phần CORS chưa kiểm chứng được, phải thử sớm (mục 7).
- **Ngân sách: bật AWS Budgets + cost allocation tag ngay hôm nay**; không tạo NAT Gateway, không để endpoint SageMaker real-time chạy.

## 3. Chi tiết

### 3.1 Aurora PostgreSQL Serverless v2 và pgvector

**Phiên bản và region.** Ở Singapore, Serverless v2 hỗ trợ PG 13.6+/14.3+/15.2+/16.1+/17.4+/18.3+; Data API hỗ trợ PG 13.11+/14.8+/15.3+/16.1+/17.4+/18.3+ [TL: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Concepts.Aurora_Fea_Regions_DB-eng.Feature.ServerlessV2.html, .../Concepts.Aurora_Fea_Regions_DB-eng.Feature.Data_API.html]. Platform version 4 (tới 384 ACU, hiệu năng cao hơn) có ở Singapore [TL: .../aurora-serverless-v2.how-it-works.html]. pgvector trong Aurora: 17.4–17.7 → 0.8.0, 17.9 → 0.8.1, 17.10–17.11 → 0.8.2; 18.3 → 0.8.1, 18.4/18.6 → 0.8.2 [TL: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraPostgreSQLReleaseNotes/AuroraPostgreSQL.Extensions.html]. HNSW có từ pgvector 0.5.0 [TL]. Mẫu CDK chính thức dùng `AuroraPostgresEngineVersion.VER_17_7` kèm chú thích "min 0 ACU cần 17.4 trở lên" [BL: repo serverless-patterns `sfn-aurora-data-api`].

**Scale về 0 ACU (auto-pause)** [TL: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html]:
- Bật bằng `MinCapacity=0`; thời gian rảnh trước khi pause: tối thiểu 300 giây (mặc định), tối đa 86.400 giây (`SecondsUntilAutoPause`). Yêu cầu engine ≥ 16.3 / 15.7 / 14.12 / 13.15 / 17.4 / 18.3.
- Khi pause: không tính phí instance (chỉ còn phí lưu trữ), `ServerlessV2Usage = 0`.
- **Resume: "thời gian điển hình khoảng 15 giây"**, đề nghị đặt timeout client > 15 giây. Pause quá 24 giờ có thể vào "ngủ sâu", resume 30 giây trở lên (tương đương reboot). Resume xong dung lượng có thể thấp hơn trước khi pause. Nhiều kết nối đến dồn lúc đang resume có thể rớt, nên cần retry (ví dụ 3 lần).
- Tài liệu nói thẳng tính năng này hợp với hệ thống "không có SLO nghiêm ngặt" (dev/test, ứng dụng nội bộ).
- Những thứ **ngăn pause**: còn kết nối do người dùng mở; **RDS Proxy gắn vào cluster**; logical replication; global database (primary hoặc secondary); zero-ETL Redshift; Babelfish. `pg_cron` không đánh thức Aurora và job bị bỏ qua nếu rơi vào lúc đang pause. Đổi parameter group, đổi scaling range, nâng cấp engine, tải log đều đánh thức instance; sau bảo trì Aurora chờ ≥ 20 phút mới pause lại. Enhanced Monitoring/Performance Insights cũng làm instance không xuống tới mức tối thiểu [TL, trang setting-capacity, chỉ đọc tiêu đề tóm tắt].
- Data API: gửi request qua Data API thì Aurora tự resume writer rồi mới xử lý [TL]. **[Đã chạy thử 2026-11-21] Chỉ đúng một nửa:** Data API đánh thức cluster nhưng **không chờ**; 4 lần gọi đầu trả `DatabaseResumingException` (mỗi lần treo 2–4 giây), lần thứ 5 thành công; tổng **16,4 giây** tới lần thành công đầu (Lambda, 1 mẫu, pause ngắn). Cần vòng retry ở code. Pause xảy ra khoảng 10 phút sau khi đổi sang min 0 (300 giây rảnh là tối thiểu). Chi tiết: `spike-aurora-data-api.md` mục 6.

**Ảnh hưởng tới p95 < 2 giây.** Mọi tool đọc (`get_forecast`, `get_jar_balances`, `affordability_check`…) đều chạm Aurora. Lần gọi đầu sau pause tốn ≥ 15 giây nên chắc chắn vi phạm NFR và có thể làm demo "đơ". Quyết định: `serverlessV2MinCapacity: 0.5` cho stack demo; chỉ dùng `0` ở môi trường dev cá nhân. Nếu muốn tiết kiệm ngoài giờ demo, hạ `min` về 0 bằng một lệnh `modify-db-cluster` (hoặc tham số CDK + deploy) và đặt EventBridge Scheduler gọi một `SELECT 1` qua Data API 10 phút trước buổi demo để làm ấm [SĐ].

**Chi phí tối thiểu** [API, giá USD, Singapore]: Serverless v2 PostgreSQL 0,20/ACU-giờ (Aurora Standard; IO-Optimized 0,26); lưu trữ 0,11/GB-tháng; I/O 0,22/triệu yêu cầu. Chạy 0,5 ACU liên tục: 0,5 × 0,20 × 730 ≈ **73 USD/tháng** (us-east-1 0,12 → 44 USD). Dữ liệu demo nhỏ nên lưu trữ + I/O chỉ vài USD. 3 tuần ≈ 50 USD ở mức 0,5 ACU. Tham chiếu rẻ hơn: RDS PostgreSQL `db.t4g.micro` Single-AZ 0,025/giờ ≈ 18 USD/tháng, `db.t4g.small` 0,051/giờ ≈ 37 USD/tháng [API]. Bộ nhớ 0,5 ACU ≈ 1 GiB [TL: 1 ACU ≈ 2 GiB]; với dữ liệu demo cộng chỉ mục HNSW nhỏ thì đủ, nhưng nhớ rằng buffer pool bị bỏ khi pause.

**Kết nối từ Lambda: so sánh.**

| Cách | Cần VPC/NAT | Auth | Hợp auto-pause | Ghi chú |
|---|---|---|---|---|
| **RDS Data API** | Không (Lambda ngoài VPC) | IAM gọi `rds-data:*` + Secrets Manager chứa user/mật khẩu DB | Có, tự đánh thức | Chỉ writer; phản hồi tối đa 1 MiB; PG ≥ 14 chỉ `scram-sha-256`; không hỗ trợ lớp `T`; reset phiên bằng `DISCARD ALL` giữa các lần gọi [TL: .../data-api.limitations.html, .../data-api.session-management.html]. **[Đã chạy thử 2026-11-21]** Độ trễ từ Lambda ngoài VPC: 12–52 ms mỗi lệnh (p95 ≤ 57 ms), Begin/Commit 8/11 ms, transaction 2 câu p50 121 ms; phản hồi 1 MiB báo `UnsupportedResultException`; không hỗ trợ kiểu `interval`, không nhiều câu lệnh `;`. Chi tiết: `spike-aurora-data-api.md` |
| Trực tiếp trong VPC (psycopg) | Có: Lambda vào private subnet; muốn gọi Bedrock thì cần NAT hoặc VPC endpoint (interface endpoint 0,013 USD/giờ/AZ [API]) | Mật khẩu từ Secrets Manager hoặc **IAM DB auth** (token 15 phút) | Có, nhưng phải retry khi resume | Quản lý kết nối: 1 kết nối/mỗi execution environment, mở ngoài handler. Có thể dùng cho đường nóng nếu Data API chậm |
| RDS Proxy | Có | IAM hoặc Secrets Manager | **Không** (proxy giữ kết nối) | Giải quyết bão kết nối ở quy mô lớn; không cần cho demo [TL] |

Quyết định: **Data API là mặc định** vì bỏ được cả lớp VPC/NAT/endpoint (tiết kiệm ~43 USD NAT + ~9,5 USD mỗi interface endpoint mỗi AZ mỗi tháng [API]) và Lambda event (phân loại bằng Bedrock) vốn đã cần Internet/Bedrock. Cái giá: mất kiểu `vector` trả về tự nhiên (truyền vector dạng chuỗi `'[0.1,0.2,…]'` và `CAST(:emb AS vector)`; đọc cột vector ra thường không cần), và phải đo độ trễ. [SĐ cho phần pgvector qua Data API: cần thử `<=>` với tham số]. **[Đã chạy thử 2026-11-21]** Xác nhận: `CAST(:q AS vector)` hoặc `:q::vector` với chuỗi `'[...]'` chạy, `<=>` với tham số chạy, HNSW 1024 chiều dùng được (pgvector 0.8.2 trên Aurora PG 18.6); tham số chuỗi không cast bị từ chối; đọc cột vector ra được (là chuỗi ~9,6 KB/vector, cần `includeResultMetadata` mới thấy kiểu). kNN top 5 trên 302 dòng: p50 51 ms từ Lambda. Chi tiết: `spike-aurora-data-api.md` mục 3.

Cách dùng trong CDK (đúng cú pháp của mẫu chính thức [BL: aws-samples/serverless-patterns `sfn-aurora-data-api`]):

```ts
const cluster = new rds.DatabaseCluster(this, 'Ledger', {
  engine: rds.DatabaseClusterEngine.auroraPostgres({ version: rds.AuroraPostgresEngineVersion.VER_17_7 }),
  writer: rds.ClusterInstance.serverlessV2('writer'),
  serverlessV2MinCapacity: 0.5,           // 0 = auto-pause, chỉ cho dev
  serverlessV2MaxCapacity: 4,
  // serverlessV2AutoPauseDuration: Duration.minutes(5), // chỉ khi min = 0
  vpc,                                      // VPC chỉ có subnet PRIVATE_ISOLATED, natGateways: 0
  vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
  credentials: rds.Credentials.fromGeneratedSecret('app_admin'),
  defaultDatabaseName: 'yofina',
  enableDataApi: true,
  storageEncrypted: true,
  deletionProtection: true,                 // dev: false + removalPolicy DESTROY
});
// Lambda: cluster.grantDataApiAccess(fn); và grant đọc secret cho Data API
```

Lưu ý khi gọi Data API từ IAM: tên tiền tố IAM là `rds-data`, không phải `rdsdata` (mẫu chính thức phải truyền `iamAction` thủ công cho `CallAwsService` của Step Functions) [BL].

**Secrets Manager.** Data API bắt buộc có secret chứa thông tin đăng nhập DB; `fromGeneratedSecret` tạo secret (0,40 USD/secret/tháng [API]). Tắt rotation ở demo (rotation cần thêm Lambda). Bedrock Knowledge Bases dùng Aurora cũng yêu cầu Data API và secret [TL: .../AuroraPostgreSQL.VectorDB.html]; nếu agent Bedrock chọn Aurora làm vector store thì đặt **cluster/schema riêng** hoặc ít nhất schema `bedrock_integration` với role riêng, và nhớ cụm này cũng bị ràng buộc auto-pause như trên. (S3 Vectors là phương án khác, thuộc phần Bedrock.)

**pgvector.** Kích thước vector theo mô hình embedding (do agent Bedrock chọn): ví dụ Titan v2 hỗ trợ 1024/512/256, Cohere Embed Multilingual v3 là 1024, Titan v1.2 là 1536 [TL: .../AuroraPostgreSQL.VectorDB.html]. Với bước "tìm giao dịch gần nhất đã có nhãn", dữ liệu nhỏ (hàng nghìn dòng mỗi người dùng): có thể bỏ qua chỉ mục và quét tuần tự có lọc `user_id`; khi cần: `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) WITH (ef_construction = 256)` (khuyến nghị của tài liệu Bedrock cho pgvector ≥ 0.6.0) [TL]. Lưu ý: chỉ mục HNSW lọc theo `user_id` có thể trả ít kết quả hơn mong muốn nếu lọc sau; pgvector ≥ 0.8.0 có iterative scan để giảm vấn đề này [SĐ, kiến thức từ pgvector]. Với quy mô demo, cách an toàn nhất: `WHERE user_id = :uid ORDER BY embedding <=> :q LIMIT 5` không chỉ mục (hoặc chỉ mục B-tree trên `user_id`). Giới hạn 2.000 chiều cho chỉ mục HNSW của kiểu `vector` [SĐ, kiến thức từ pgvector]: dùng ≤ 1024 chiều là an toàn.

**Row-level security.**
```sql
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions FORCE ROW LEVEL SECURITY;   -- chủ bảng cũng bị áp
CREATE POLICY own_rows ON transactions
  USING (user_id = current_setting('app.user_id', true)::uuid)
  WITH CHECK (user_id = current_setting('app.user_id', true)::uuid);
```
**[Đã chạy thử 2026-11-21] Bác bỏ dòng `FORCE ... -- chủ bảng cũng bị áp`:** trên Aurora, master user (thuộc `rds_superuser`) **vẫn bỏ qua RLS kể cả sau `FORCE ROW LEVEL SECURITY`** (thấy đủ 3 user dù `rolbypassrls=false`, `relforcerowsecurity=true`). Vì vậy tool phải dùng secret của role riêng (non-owner), không dùng secret master. Mẹo `WITH s AS (SELECT set_config(...)) SELECT ... FROM bang, s` trong một lệnh **không đáng tin** (đúng với bảng nhỏ quét tuần tự, trả 0 dòng khi có index); dùng transaction tường minh hoặc hàm plpgsql. Chi tiết: `spike-aurora-data-api.md` mục 4.

Ứng dụng nên kết nối bằng role không phải chủ bảng, không có `BYPASSRLS` [SĐ, ngữ nghĩa PostgreSQL chuẩn; đã xác nhận bằng role `yofina_app`]. Với Data API, giữa các lần gọi Data API chạy `DISCARD ALL` (xóa tham số phiên) [TL], nên không đặt `app.user_id` kiểu session. Phải đặt **trong cùng transaction** (`BeginTransaction` → `set_config('app.user_id', :uid, true)` → câu lệnh → `CommitTransaction`) [SĐ, cần thử]. Vì tốn thêm vòng gọi, **lớp bảo vệ chính vẫn là `WHERE user_id = :uid`** do một hàm truy cập dữ liệu duy nhất ép buộc; RLS là lớp phụ cho đường batch/tool không ngờ tới. `user_id` lấy từ đâu: xem phát hiện về danh tính ở mục 3.2.

**Migration.** Thư mục `db/schema/NNNN_name.sql` + Lambda `db-migrator` (zip, Data API) chạy từng file chưa có trong `schema_migrations`, kích hoạt bằng CDK `Trigger` hoặc `aws lambda invoke` trong CI. Nếu muốn chạy test cục bộ: Postgres + pgvector trong Docker và một lớp truy cập có hai backend (Data API / psycopg) [SĐ]. Công cụ nặng hơn (Alembic, Flyway) chỉ đáng khi có ORM; proposal dùng SQL có tham số nên không cần.

**So sánh nhanh và có nên đổi không.**

| | Aurora PG Serverless v2 | Aurora DSQL | RDS PostgreSQL thường |
|---|---|---|---|
| Scale về 0 | Có (resume ~15 giây) | Có (tính theo DPU) | Không (có thể dừng, tự bật lại sau 7 ngày [SĐ]) |
| pgvector | Có (0,8.x) | **Không** [BL: web search tóm tắt tài liệu DSQL, trang gốc chưa mở được] | Có |
| Data API | Có | Không [SĐ] | Không (Data API chỉ Aurora) |
| Khác biệt SQL | Gần như PG đầy đủ | Không PL/pgSQL, không temp table, tối đa 3.000 dòng/transaction, kết nối hết hạn sau 1 giờ, collation `C`, OCC cần retry [TL: .../working-with-postgresql-compatibility-migration-guide.html] | PG đầy đủ |
| Có ở Singapore | Có | Có [TL: .../what-is-aurora-dsql.html] | Có |
| Chi phí tối thiểu | ~73 USD/tháng ở 0,5 ACU | DPU 0,000009 USD, lưu trữ 0,4 USD/GB-tháng [API] | ~18–37 USD/tháng (t4g.micro/small) |

**Khuyến nghị: không đổi.** DSQL thiếu pgvector (bước embedding của F2/FR2 là cốt lõi), collation `C` làm sắp xếp tiếng Việt sai thứ tự, và giới hạn transaction gây phiền. RDS thường chỉ đáng nếu ngân sách còn dưới ~50 USD cho Aurora; khi đó mất Data API, kéo theo Lambda phải vào VPC. Chỉ đổi nếu Data API đo ra quá chậm cho đường nóng (khi đó cả cụm vẫn là Aurora, chỉ một Lambda đổi cách kết nối).

### 3.2 Lambda Python

**Runtime** [TL: https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html]: `python3.12` (hết hỗ trợ 31/10/2028), `python3.13` và `python3.14` (30/6/2029), `python3.15` cũng đã có (30/6/2029); `python3.11` còn trên Amazon Linux 2 (30/6/2027), Amazon Linux 2 đã hết vòng đời 30/6/2026. Chọn **3.13** làm mặc định cho toàn bộ Lambda (AgentCore Runtime dán code cũng hỗ trợ 3.12–3.14 [TL]); tránh 3.11. Mọi runtime hỗ trợ cả `x86_64` và `arm64`. Lưu ý: bản CDK mới có thể bỏ enum `PYTHON_3_13` khi thay bằng 3.14 (một trang hỗ trợ MDAA nhắc tới `python3.13` bị gỡ ở CDK 2.258.0) [BL]; ghim phiên bản CDK và đọc `cdk diff` sau mỗi lần nâng.

**Hạn mức** [TL: https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html]: RAM 128–10.240 MB (1.769 MB = 1 vCPU); **timeout 1.800 giây**; payload đồng bộ 6 MB mỗi chiều; zip ≤ 250 MB sau giải nén *kể cả layer*, tối đa 5 layer; **container image ≤ 10 GB** không nén; `/tmp` 512–10.240 MB; tăng đồng thời 1.000 môi trường mỗi 10 giây mỗi hàm. Layer chỉ dùng với zip, không dùng với container; SnapStart không hỗ trợ container [TL: skill aws-serverless].

**Powertools for AWS Lambda (Python)** [TL: https://docs.aws.amazon.com/powertools/python/latest/]: logger, tracer (X-Ray), metrics (CloudWatch EMF), event handler (API Gateway, Function URL, Bedrock Agents…), parameters (SSM/Secrets), **idempotency**, **batch processing** (SQS/Kinesis/DynamoDB Streams), **parser** (Pydantic), validation, data masking (hữu ích để che số tài khoản/điện thoại trước LLM), feature flags, và hai tiện ích mới: `Auth` (xác minh JWT access token) và `Circuit Breaker`. Dùng qua Lambda layer của AWS, mẫu ARN: `arn:aws:lambda:ap-southeast-1:<tài khoản công bố của Powertools>:layer:AWSLambdaPowertoolsPythonV3-python313-arm64:<phiên bản>` (bản 44 lúc đọc, có đủ python310–314 và x86_64/arm64 ở `ap-southeast-1`; ARN đầy đủ ở trang cài đặt [BL: WebFetch tóm tắt https://docs.aws.amazon.com/powertools/python/latest/getting-started/install/index.md]; trang đó lưu ý ví dụ chung còn ghi `:37`, nên tra lại số phiên bản). Phần "extras" như `parser` (pydantic) **không** nằm trong layer, phải tự cài; vì `pydantic-core` là mã nhị phân theo nền tảng, cần đóng gói đúng nền tảng (xem dưới).

Mẫu handler tối thiểu cho tool (theo skill `aws-serverless` và tài liệu Powertools):
```python
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.utilities.typing import LambdaContext
logger, tracer, metrics = Logger(), Tracer(), Metrics(namespace="Yofina")

@logger.inject_lambda_context(correlation_id_path="trace_id")
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict, context: LambdaContext):
    tool = context.client_context.custom["bedrockAgentCoreToolName"].split("___", 1)[1]
    return TOOLS[tool](event)
```

**Đóng gói.**
- Phân tầng: (1) *tool Lambda nhẹ* (ledger, planner, knowledge, audit, ingest) = zip + layer Powertools, phụ thuộc chỉ gồm boto3 (đã có trong runtime) và pydantic nếu dùng `parser`; do dùng Data API nên không cần thư viện driver. (2) *Lambda ML* (forecast batch, resilience, behavior, breakpoint, Monte Carlo nếu nặng) = **container image** chứa torch CPU, Chronos-2, StatsForecast, ruptures, PyOD, scikit-learn, OR-Tools. Torch + scipy + numba + pandas vượt 250 MB zip [SĐ về kích thước, giới hạn 250 MB là [TL]].
- `forecast.run_scenario` / `affordability_check` nằm trên đường nóng (Monte Carlo nhẹ) nên **giữ trong zip, chỉ dùng numpy** nếu được; đừng kéo torch vào đó vì cold start container + import torch tính bằng giây [SĐ].
- Máy phát triển là Windows: `DockerImageFunction`/`DockerImageCode.fromImageAsset` cần Docker Desktop; build `arm64` trên máy x86 phải qua emulation chậm, nên **image dùng `x86_64`** (hoặc build trong GitHub Actions). Zip có phụ thuộc nhị phân cần cài đúng nền tảng Linux (`pip install --platform manylinux2014_<arch> --only-binary=:all:` hoặc bundling bằng Docker). `PythonFunction` của CDK nằm trong gói `@aws-cdk/aws-lambda-python-alpha` (alpha tại thời điểm tôi biết; chưa kiểm xem đã vào `aws-cdk-lib` chưa [chưa tìm được]).
- Chronos-2: tải trọng số khi build image (`huggingface_hub`), đặt `HF_HUB_OFFLINE=1` lúc chạy để tránh tải khi cold start. Giấy phép Apache-2.0 [BL: model card https://huggingface.co/amazon/chronos-2]. Chi tiết mô hình thuộc agent ML.
- ECR: đặt lifecycle rule giữ vài image gần nhất.

**Cold start.** Với zip Python + Powertools: thường dưới 1 giây [SĐ]. Với container ML: nhiều giây (import torch + nạp model) [SĐ], chấp nhận được ở batch đêm. Chỉ cần quan tâm cold start ở đường nóng: giữ Lambda tool trong zip, bộ nhớ ≥ 512–1024 MB (CPU tỷ lệ với bộ nhớ), khởi tạo client boto3/Data API ngoài handler. Provisioned Concurrency hoặc SnapStart (Python zip, bản phát hành đã publish) chỉ khi đo thấy cần [TL: skill]. Chi phí cold start của Lambda trong VPC hiện nhỏ nhờ cơ chế ENI dùng chung [SĐ].

**Lambda trong VPC để vào Aurora.** Nếu dùng Data API thì **không cần**. Nếu bắt buộc vào VPC: private subnet, security group Lambda → security group Aurora cổng 5432; muốn gọi Bedrock/Secrets Manager/S3 thì cần NAT (0,059 USD/giờ ≈ 43 USD/tháng [API]) hoặc VPC endpoint (0,013 USD/giờ/AZ [API]). Aurora vẫn bắt buộc nằm trong VPC (subnet group), dùng VPC chỉ có `PRIVATE_ISOLATED` và `natGateways: 0`.

**Lambda làm target của AgentCore Gateway** [TL: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-lambda.html]:
- `event` = map các thuộc tính của `inputSchema`; tên tool nằm ở `context.client_context.custom['bedrockAgentCoreToolName']` dạng `${target}___${tool}` (ba dấu gạch dưới), phải tự cắt tiền tố. Tên tool proposal (`ledger.get_jar_balances`) cần chuyển thành target `ledger` + tool `get_jar_balances`. Hàm phải trả JSON hợp lệ. Gateway gọi bằng `GATEWAY_IAM_ROLE` (role cần `lambda:InvokeFunction`) [TL: ví dụ CLI]. L2: `gateway.addLambdaTarget(id, {...})` trong `aws-cdk-lib/aws-bedrockagentcore` [TL: constructs.dev API 2.277.0].
- Một Lambda mỗi nhóm tool (`ledger`, `forecast`, `planner`, `knowledge`, `ingest`, `audit`) với router theo tên tool: khớp với cấu trúc thư mục `gateway/tools/*` và giảm số cold start.
- **Phát hiện về danh tính (quan trọng cho RLS và NFR "tool chỉ đọc dữ liệu của chủ JWT")**: Lambda target **không** nhận JWT của người dùng mặc định. Header `Authorization` bị cấm đưa vào allowlist của target; chỉ được chuyển tiếp nếu **Gateway interceptor Lambda** đặt vào, và tối đa 10 header mỗi target, mỗi giá trị ≤ 4 KB [TL: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-headers.html]. Vậy `user_id` không được lấy từ tham số do LLM sinh (có thể bị tiêm lệnh). Cần một trong hai cách (phối hợp với agent AgentCore): (a) interceptor lấy claim `sub` đã được Gateway xác minh và gắn vào header allowlisted `x-user-id`; (b) agent runtime tự thêm header lúc gọi Gateway từ claim JWT đã xác minh (không qua LLM). Quyết định này chưa được kiểm; xem mục 5.

### 3.3 Sự kiện: EventBridge → SQS → Lambda

Dựa trên skill `aws-serverless` (event-sources.md, orchestration.md) [TL]:

```
ledger Lambda --PutEvents(detail-type=TransactionRecorded, source=yofina.ledger)--> EventBridge bus "yofina"
   rule(pattern) --> SQS queue "classify" (SSE-SQS) --redrive(maxReceiveCount 3-5)--> DLQ
   SQS --ESM(batch 10, ReportBatchItemFailures, MaxConcurrency ~5)--> Lambda classify (Powertools)
```
- Bus riêng theo miền ứng dụng, một target mỗi rule, DLQ ở **target của rule** (bắt lỗi giao event vào SQS) và DLQ ở **hàng đợi** (bắt tin nhắn độc). Mẫu bắt buộc: `visibilityTimeout ≥ 6 × timeout hàm`, `ReportBatchItemFailures`, redrive policy của SQS (không dùng DLQ ở mức event source mapping cho SQS) [TL: skill].
- `SqsEventSource` có `maxConcurrency` (2–1.000); khoảng 5–10 đủ để không dồn kết nối/thu phí Bedrock. Chú thích: SQS filter chỉ lọc trên `body` và tin không khớp bị **xóa** [TL: skill].
- Dùng khóa SSE-SQS mặc định thay vì CMK để khỏi phải sửa key policy cho `events.amazonaws.com` [SĐ].
- **Idempotency hai lớp.** (1) Phân phối: `idempotent_function(data_keyword_argument="record")` + `DynamoDBPersistenceLayer` (bảng on-demand) khóa theo `detail.event_id`, đặt quanh bước tốn tiền (gọi LLM/embedding) để trùng lặp không gọi lại model. Mẫu mã nằm trong skill: `BatchProcessor(event_type=EventType.SQS)` + `process_partial_response` + `IdempotencyConfig(event_key_jmespath=...)` [TL]. (2) Nghiệp vụ: "khóa băm từ ngày, số tiền, đối tác, kèm cửa sổ sai lệch thời gian" của §7 là **khử trùng giao dịch**, lưu thành cột `dedup_hash` với ràng buộc `UNIQUE (user_id, dedup_hash)` và `INSERT ... ON CONFLICT DO NOTHING`. Hai việc khác nhau, đừng gộp.
- Phát sự kiện sau khi commit; rủi ro "ghi DB thành công nhưng PutEvents lỗi" chấp nhận ở demo, bù bằng retry; outbox chỉ làm nếu còn thời gian [SĐ].
- Hàng đợi nạp tệp (F6): S3 → EventBridge/S3 notification → SQS riêng, cùng cấu hình (Lambda ingest dài hơn nên visibility timeout dài hơn).

**EventBridge Scheduler** [TL: https://docs.aws.amazon.com/scheduler/latest/UserGuide/schedule-types.html]:
- Lịch đêm: `schedule-expression "cron(0 2 * * ? *)"` với `--schedule-expression-timezone "Asia/Ho_Chi_Minh"`, flexible time window `OFF`, độ chính xác 60 giây. Việt Nam không có giờ mùa hè nên không có chuyện lệch giờ. Cron có 6 trường (phút giờ ngày-tháng tháng thứ năm); không được dùng `*` đồng thời ở ngày-tháng và thứ (dùng `?`).
- Nhắc một lần theo người dùng: `at(yyyy-mm-ddThh:mm:ss)` kèm múi giờ; schedule một lần **vẫn tính vào quota sau khi chạy xong**, nên đặt `ActionAfterCompletion = DELETE` hoặc xóa chủ động [TL]. Đặt tên `nudge-<user>-<hash>`, dùng schedule group riêng, và `ClientToken` để tạo idempotent [SĐ]. Tool `planner.schedule_nudge` gọi `CreateSchedule`; target là SQS/Lambda/bus sự kiện.
- CDK: `aws-cdk-lib/aws-scheduler` (`Schedule`, `ScheduleExpression.cron({..., timeZone: TimeZone.of('Asia/Ho_Chi_Minh')})`) và `aws_scheduler_targets.StepFunctionsStartExecution` đã có trong `aws-cdk-lib` 2.277.0 [TL: constructs.dev]. Schedule động theo người dùng tạo lúc chạy bằng SDK, không qua CDK.
- pg_cron **không** dùng được thay Scheduler vì Aurora pause sẽ bỏ qua job [TL].

### 3.4 Step Functions (pipeline đêm)

- **Chọn Standard** [TL: skill orchestration.md]: Express tối đa 5 phút, không có `.sync`, không callback, không Distributed Map; pipeline đêm có bước mô hình chạy vài phút và cần lịch sử 90 ngày để gỡ lỗi. Giá Standard: 0,000025 USD mỗi lần chuyển trạng thái (giá us-east-1), 4.000 lần miễn phí mỗi tháng [BL: WebFetch trang pricing]; một đêm ≈ vài trăm chuyển trạng thái, rất rẻ.
- **Distributed Map không cần** ở quy mô demo (nó chạy tới 10.000 execution con, đọc từ S3, chỉ Standard [TL: skill]). Dùng **Map inline** (tối đa 40 song song) trên các *khối* ~20–50 người dùng do một Lambda `plan` sinh ra, vì Lambda container ML nên nạp model **một lần** cho cả khối (nạp Chronos từng người rất lãng phí). Giới hạn payload 256 KiB (`States.DataLimitExceeded` là lỗi không thể retry): chỉ truyền ID, kết quả ghi thẳng Aurora.
- Khung: `Plan(Lambda)` → `Map(chunk)` { `Forecast(container)` → `Parallel`{ `Resilience`, `Behavior` } → `Breakpoint` → `NudgeGate` } → `Summarize`; nhánh người dùng cần sinh lại lộ trình đẩy một sự kiện lên bus (job nền AgentCore) thay vì gọi agent đồng bộ trong pipeline.
- Lỗi/retry [TL: skill]: đặt `TimeoutSeconds` cho mọi Task; `Retry` cho `Lambda.ServiceException`, `Lambda.SdkClientException`, `Lambda.TooManyRequestsException` (thêm), `States.Timeout`, `JitterStrategy: "FULL"`, `States.ALL` đặt cuối; `Catch` trả về trạng thái "đánh dấu người dùng lỗi" (ResultPath `$.error`) để một người lỗi không làm hỏng cả khối; `toleratedFailurePercentage` nếu dùng Distributed Map. Đẩy sự kiện thất bại (`aws.states`, `FAILED`/`TIMED_OUT`) vào SNS/email hoặc alarm.
- Gọi Lambda bằng tích hợp tối ưu `lambda:invoke` (đồng bộ). SageMaker `CreateTransformJob` có tích hợp tối ưu `.sync` nếu sau này dùng batch transform [TL: https://docs.aws.amazon.com/step-functions/latest/dg/connect-sagemaker.html]. Gọi Data API từ Step Functions: dùng `CallAwsService` với `iamAction: 'rds-data:ExecuteStatement'` [BL].
- Idempotency của lần chạy: đặt tên execution `nightly-YYYYMMDD`; Standard từ chối trùng tên trong 90 ngày [TL: skill].

### 3.5 Chronos-2: hạ tầng chạy

| Cách | Chi phí lúc nhàn rỗi | Hợp với | Giới hạn |
|---|---|---|---|
| **Lambda container (khuyến nghị)** | 0 | Batch đêm vài trăm chuỗi | 10 GB image, 10 GB RAM (~5,8 vCPU), 30 phút, không GPU |
| SageMaker Serverless Inference | 0 (scale về 0) | Gọi lẻ theo yêu cầu, ít | RAM 1–6 GB, **CPU, không GPU, không VPC**, image ≤ 10 GB, cold start tuỳ kích thước model; tối đa 50 endpoint, concurrency 1.000 mỗi region ở Singapore [TL: https://docs.aws.amazon.com/sagemaker/latest/dg/serverless-endpoints.html] |
| SageMaker Async Inference | Có thể về 0 nhờ autoscaling, tin đợi trong hàng | Tải lớn tới 1 GB, tối đa 60 phút | Khởi động instance lâu (phút) [SĐ]; cần cấu hình autoscaling riêng [TL: .../async-inference-autoscale.html] |
| SageMaker Batch Transform | Instance chỉ tồn tại lúc chạy job | Chạy theo file S3 | Timeout tối đa 3.600 giây, 100 MB mỗi mini-batch [TL: .../hosting-faqs.html] |
| SageMaker real-time `ml.m5.xlarge` | **0,288 USD/giờ ≈ 210 USD/tháng** [API] | Không cần | Chỉ bật trong cửa sổ demo nếu ép buộc |
| Fargate | Chỉ trả khi chạy | Nếu vượt giới hạn Lambda | Thêm ECS/VPC/ECR, phức tạp hơn |

Khuyến nghị: **Lambda container**, nạp trọng số trong image, chạy theo khối người dùng từ Step Functions. Căn cứ: model 120M tham số hỗ trợ CPU; số liệu bên thứ ba cho 7.000 chuỗi ~40 giây trên `m6i.8xlarge` (32 vCPU) [BL: web search tóm tắt, Decathlon]; demo chỉ ~vài chục người × 7 hũ. Ghi nhận: model card nói hỗ trợ CPU nhưng ví dụ chính thức dùng GPU, và hướng dẫn AWS cho SageMaker/AutoGluon-Cloud nhắc serverless chỉ CPU và có cold start [BL]. Mục tiêu: nếu một khối 25 người chạy quá 15 phút, hạ cỡ khối hoặc nâng RAM Lambda, rồi mới nghĩ tới SageMaker. "Endpoint tắt khi không dùng" trong §13 proposal nghĩa là *xóa* endpoint; việc xóa/tạo lại chậm và dễ quên, nên bỏ hẳn SageMaker khỏi MVP là hướng giảm rủi ro chi phí tốt nhất.

### 3.6 CDK

**Ngôn ngữ: TypeScript.** Lý do: Node đã bắt buộc cho CDK CLI và frontend; mọi mẫu chính thức tìm thấy cho Gateway+Lambda, Aurora+Data API+Step Functions đều bằng TypeScript [BL: aws-samples/serverless-patterns]; có kiểm tra kiểu đối với props L2 mới (AgentCore). Python CDK cũng có đủ L2 (`aws_cdk.aws_bedrockagentcore`) nên nếu người viết hạ tầng chỉ biết Python thì dùng Python vẫn được [TL: constructs.dev có cả `lang=python`]. Skill `aws-cdk`: dùng `tsx` thay `ts-node`, `eslint-plugin-awscdk`, ghim `aws-cdk-lib`/`constructs`/`aws-cdk` chính xác, gọi qua `npx cdk` [TL: skill]. Lúc đọc trang constructs.dev: `aws-cdk-lib` 2.277.0 [TL].

**Cấu trúc stack** (một app trong `infra-cdk/`, mỗi stack gán `env` tường minh, `cdk.context.json` được commit):

| Stack | Nội dung | Ghi chú |
|---|---|---|
| `Foundation` | VPC isolated (0 NAT), KMS (nếu dùng CMK), S3 (tệp nạp, artifact, audit; `enforceSSL`, chặn public), Budgets, SNS cảnh báo, ECR | `terminationProtection` |
| `Data` | Aurora + secret, DynamoDB idempotency | **Tách riêng, bật `terminationProtection: true`**, không đổi ID construct (đổi ID = thay thế tài nguyên mất dữ liệu) [TL: skill] |
| `Identity` | Cognito User Pool, app client, domain | |
| `Tools` | Lambda (zip + container), layer Powertools, bus, SQS+DLQ, Scheduler, Step Functions, dashboard/alarm | |
| `Agent` | AgentCore Runtime, Gateway (+ target Lambda), Memory, Identity (agent AgentCore viết) | `aws-cdk-lib/aws-bedrockagentcore` |
| `Frontend` | Amplify app (`CfnApp`/L1) hoặc S3+CloudFront, WAF | |
| `CiAccess` (tách riêng, deploy bằng admin) | Nhà cung cấp OIDC GitHub + role CI | |

Tránh "deadly embrace" giữa stack: truyền tham số qua prop thay vì `Fn::ImportValue` cứng, hoặc qua SSM; nếu phải xóa tham chiếu chéo thì làm hai lần deploy [TL: skill].

**Bootstrap** [TL: skill bootstrap-and-project-setup.md]: `npx cdk bootstrap aws://<ACCOUNT>/ap-southeast-1` (cần quyền gần như quản trị; **không** xóa stack `CDKToolkit`; bật termination protection; chạy lại khi nâng CDK đòi phiên bản bootstrap mới). Tạo S3, ECR, 4 role cho người dùng assume (deploy, lookup, file-publishing, image-publishing), role thực thi CloudFormation (mặc định `AdministratorAccess`) và tham số SSM. Dùng `--custom-permissions-boundary` nếu muốn giới hạn role do CDK tạo.

**L2 cho AgentCore:** `aws-bedrockagentcore` đã **chuyển sang stable trong `aws-cdk-lib`** (từ v2.255.0): runtime, memory, gateway, identity…, **riêng Policy submodule vẫn alpha** [TL: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html]. Có mẫu `import * as agentcore from "aws-cdk-lib/aws-bedrockagentcore"` và `Gateway.addLambdaTarget` [TL+BL]. Vậy Policy (Cedar) phải dùng L1 (`CfnPolicy*`) hoặc gói alpha; chi tiết để agent AgentCore xác nhận.

**cdk-nag**: `Aspects.of(app).add(new AwsSolutionsChecks({ verbose: true }))`, kèm `cdk synth --strict`; chỉ dùng `NagSuppressions` với lý do rõ ràng và phạm vi hẹp (ví dụ wildcard IAM của Gateway/Scheduler) [TL: skill; BL: trang ADDF]. Bật ở CI; ở local có thể bật khi `cdk synth`. Mong đợi nhiều cảnh báo ban đầu (Lambda không VPC, SQS không SSL, Cognito không MFA…); chọn lọc để khỏi mất thời gian: quyết định khai báo `suppress` có chủ đích cho các mục không áp dụng demo.

**Quản lý secret**: không lưu secret trong mã/CDK context; mật khẩu DB do Secrets Manager sinh; khóa API bên ngoài (nếu có) vào SSM Parameter Store `SecureString` hoặc Secrets Manager; secret GitHub chỉ cho thứ không phải AWS (AWS dùng OIDC, không khóa tĩnh) [TL: skill "OIDC for CI/CD"].

**Tính năng CDK mới đáng biết** [TL: skill]: `cdk drift --fail` trong CI, `cdk refactor` để đổi tên không thay thế tài nguyên (không đổi thuộc tính trong cùng lần deploy), `cdk import`.

### 3.6.5 Role deploy thay cho root: các bước cụ thể

Tình trạng hiện tại: CLI và connector đều chạy bằng root (HANDOFF). Các bước:

1. **Đăng nhập root một lần** để: bật MFA cho root; bật IAM Identity Center (chọn Region gốc `ap-southeast-1`, chọn lúc đầu vì khó đổi [SĐ]) hoặc tạo IAM user; khóa root (không tạo access key).
2. **Tạo danh tính con người**: ưu tiên IAM Identity Center: tạo user, permission set `AdministratorAccess` cho 3 tuần đầu (chỉ người quản trị hạ tầng); các thành viên khác dùng `PowerUserAccess` + quyền `sts:AssumeRole` bên dưới. Dùng `aws configure sso` hoặc `aws login` với danh tính này; đặt `region = ap-southeast-1` trong profile, và đặt `AWS_PROFILE`/`--profile` tường minh để tránh mặc định `us-east-1`. Ghi lại: connector AWS MCP trên claude.ai là đăng nhập riêng, cần đăng nhập lại bằng danh tính mới (không phải root) [TL: docs/references/aws-tooling.md].
3. **Bootstrap bằng danh tính quản trị (không phải root)**: `npx cdk bootstrap aws://<ACCOUNT>/ap-southeast-1`. Từ đó người deploy chỉ cần quyền assume các role bootstrap, mẫu chính thức của CDK [TL: https://docs.aws.amazon.com/cdk/v2/guide/best-practices-security.html]:
   ```json
   {"Version":"2012-10-17","Statement":[{"Sid":"AssumeCDKRoles","Effect":"Allow","Action":"sts:AssumeRole","Resource":"*",
     "Condition":{"StringEquals":{"iam:ResourceTag/aws-cdk:bootstrap-role":["image-publishing","file-publishing","deploy","lookup"]}}}]}
   ```
   Role thực thi CloudFormation vẫn mang `AdministratorAccess` mặc định; CDK khuyên *không* cố viết chính sách tối thiểu chi tiết vì khó và dễ làm hỏng rollback, mà dùng permissions boundary/SCP/CloudTrail làm rào chắn [TL: cùng trang].
4. **GitHub OIDC** (không khóa tĩnh): tạo nhà cung cấp danh tính OIDC `token.actions.githubusercontent.com` (audience `sts.amazonaws.com`), một lần cho cả tài khoản, trong stack `CiAccess`. Role CI có trust policy hẹp [TL: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html]:
   ```json
   {"Effect":"Allow","Principal":{"Federated":"arn:aws:iam::<ACCOUNT>:oidc-provider/token.actions.githubusercontent.com"},
    "Action":"sts:AssumeRoleWithWebIdentity",
    "Condition":{"StringEquals":{"token.actions.githubusercontent.com:aud":"sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub":"repo:<ORG>/<REPO>:ref:refs/heads/main"}}}
   ```
   IAM bắt buộc khóa `sub` phải có và không chỉ là ký tự đại diện, nếu không từ chối tạo/cập nhật trust policy [TL]. Quyền của role CI = chính sách `AssumeCDKRoles` ở trên (và đọc thêm nếu cần). Có thể tách hai role: `ci-diff` (cho nhánh PR: chỉ lookup, chạy `cdk synth/diff`) và `ci-deploy` (chỉ nhánh `main`, kèm GitHub Environment có luật bảo vệ) [TL: khuyến nghị environment protection].
5. **Workflow**: `permissions: { id-token: write, contents: read }`, bước `aws-actions/configure-aws-credentials` với `role-to-assume` và `aws-region: ap-southeast-1` (ghim phiên bản/SHA [SĐ]), rồi `npm ci && npx cdk synth --strict && npx cdk diff` (PR) / `npx cdk deploy --all --require-approval never` (main).
6. Đặt cảnh báo CloudTrail/Budgets (mục 3.8) trước khi cho CI chạm vào tài khoản.

### 3.7 Frontend hosting và định danh

**Amplify Hosting.** Hosting compute của Amplify quản lý SSR cho Next.js 12–15 (App Router của 13 được hỗ trợ); **không** hỗ trợ Edge API routes, On-Demand ISR, **Next.js streaming**, `unstable_after` [TL: https://docs.aws.amazon.com/amplify/latest/userguide/ssr-amplify-support.html]. Next.js 16 chưa thấy trong trang chính thức; có nguồn cộng đồng nói chạy được [BL]. Vì client AG-UI nhận SSE **trực tiếp từ AgentCore Runtime**, không đi qua máy chủ Next.js, nên **không cần SSR**: dùng `output: 'export'` (SSG thuần) hoặc SPA Vite. Lợi: không phụ thuộc giới hạn "streaming" của Amplify, build đơn giản, rẻ. Với bản export tĩnh, tài liệu Amplify hướng dẫn thiết lập `baseDirectory`; ví dụ chính thức cho Next 14+ SSG dùng `.next` (cùng cấu hình với `WEB_COMPUTE`) [TL: .../deploy-nextjs-app.html]; thư mục `out` là mặc định của `output: 'export'` nên cần thử kiểm [SĐ].
- Triển khai: kết nối repo GitHub (CI của Amplify) hoặc deploy thủ công bằng zip/S3 qua API (không cần Git) [TL: .../manual-deploys.html]. Dùng cách thứ hai nếu muốn một pipeline CI duy nhất. CDK: L1 `aws_amplify.CfnApp`/`CfnBranch` (L2 `-alpha` riêng; [chưa kiểm]).
- **WAF**: Amplify tích hợp trực tiếp với AWS WAF, web ACL gắn vào Amplify app, có hướng dẫn CDK hai stack (một stack Amplify, một stack WAF) [TL: https://docs.aws.amazon.com/amplify/latest/userguide/WAF-integration.html]. Cảnh báo kiến trúc: WAF này chỉ bảo vệ **trang tĩnh**, còn luồng nhạy cảm (trình duyệt → AgentCore Runtime) **không đi qua** nó. Giá trị WAF cho demo thấp; để cuối danh sách. (Giá WAF: 0,60 USD/triệu request ở Singapore [API]; phí web ACL/rule theo tháng chưa tra [chưa tìm được].)
- **CloudFront riêng** chỉ cần nếu muốn domain tuỳ chỉnh/WAF riêng; Amplify đã dùng CloudFront phía sau.

**Cognito User Pool.**
- Gói tính năng: Lite (hosted UI cũ), **Essentials** (mở khóa *managed login*, mức thấp nhất có managed login), Plus (bảo vệ chống tấn công) [TL: https://docs.aws.amazon.com/cognito/latest/developerguide/feature-plans-features-essentials.html]. Cho demo: Essentials + managed login, hoặc Lite + hosted UI nếu muốn rẻ nhất; Essentials ở Singapore có giá riêng [API: có mục giá `CognitoEssentials…` cho `ap-southeast-1`]; mức miễn phí theo MAU [SĐ].
- App client **công khai (không secret)** với authorization code + **PKCE**, callback là URL Amplify và `http://localhost:3000` cho dev; không dùng implicit flow [SĐ, thực hành OAuth chuẩn]. Dùng đăng nhập bằng email/mật khẩu, tài khoản demo tạo sẵn bằng script (đặt mật khẩu cố định), nút "đặt lại" không đụng Cognito.
- **JWT gọi AgentCore Runtime**: Runtime/Gateway cấu hình `CustomJWTAuthorizerConfiguration` với discovery URL `https://cognito-idp.ap-southeast-1.amazonaws.com/<poolId>/.well-known/openid-configuration` và ít nhất một trong `allowedAudience` / `allowedClients` / `allowedScopes` / claim bắt buộc; nếu dùng nhiều thì kiểm tất cả [TL: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/inbound-jwt-authorizer.html]. Lưu ý thực tế [SĐ]: access token của Cognito có claim `client_id` nhưng không có `aud`; ID token có `aud`, không có `client_id`. Nên gửi **access token** và dùng `allowedClients = [<clientId>]` (xác nhận cùng agent AgentCore).
- Gọi từ trình duyệt: `Authorization: Bearer <token>` và header `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id: <id>` (id ≥ 33 ký tự) [TL: .../runtime-agui-protocol-contract.html]. Có hỗ trợ trình duyệt dùng OAuth bearer cho WebSocket không qua proxy [TL: release notes].
- **CORS: chưa tìm được tài liệu nói endpoint của AgentCore Runtime tự trả header CORS.** Trang troubleshooting chỉ hướng dẫn thêm `CORSMiddleware` vào `BedrockAgentCoreApp` trong code container (và xử lý `OPTIONS /invocations`) cho trình duyệt gọi runtime tự dựng [TL: .../browser-tool-troubleshooting.html]. Điều này gợi ý trình duyệt có thể gọi trực tiếp nếu container trả đúng header, nhưng tiền kiểm (preflight có qua lớp xác thực của AgentCore hay bị chặn trước khi tới container?) **phải thử ngay tuần 1**. Phương án dự phòng: một Lambda Function URL/API Gateway HTTP API với JWT authorizer làm proxy streaming (Lambda response streaming hỗ trợ tới 200 MB mỗi phản hồi [TL: gettingstarted-limits]).
- **Khoảng trống của proposal**: các màn hình khai báo/hũ/tiến độ nạp tệp cần API CRUD cho người dùng; proposal chỉ có đường agent. Khuyến nghị thêm **API Gateway HTTP API + JWT authorizer của Cognito → cùng các Lambda `ledger`** cho thao tác không cần LLM (đọc số dư, lưu khai báo, danh sách "Xem lại"); đường chat đi AgentCore. [SĐ, quyết định thiết kế; HTTP API giá thấp]. Nếu không, mọi thao tác của UI đều phải đi qua agent (chậm, tốn token, và nằm ngoài ngân sách 2 giây).

### 3.8 Bảo mật và quan sát

- **Mã hóa**: dùng khóa do AWS quản lý cho Aurora (`storageEncrypted: true`), DynamoDB, SQS (SSE-SQS), S3 (SSE-S3, chặn public, `enforceSSL`) để khỏi tốn 1 USD/khóa/tháng + 0,03 USD/10.000 request [API]. Chỉ dùng **một CMK** nếu muốn kiểm soát/thu hồi cho bucket tệp nạp nhạy cảm và Secrets Manager. Đang truyền: Data API và mọi dịch vụ AWS qua HTTPS; bucket S3 `enforceSSL`. Quyền riêng tư: che PII trước khi vào LLM bằng Powertools `data_masking` hoặc bước riêng (agent Bedrock lo Guardrails) [TL: danh sách utility].
- **CloudTrail**: nhật ký sự kiện quản lý 90 ngày có sẵn miễn phí (Event history); gọi Data API có trong CloudTrail [TL: mục lục trang Data API]. Tạo trail S3 chỉ khi cần giữ lâu hơn 90 ngày hoặc muốn chứng cứ kiểm toán cho giám khảo [SĐ]. `audit_events` trong Aurora là kiểm toán mức ứng dụng, không thay CloudTrail.
- **Quan sát** (skill `aws-observability` chưa nạp; theo Powertools [TL]): Logger JSON có `correlation_id` = `trace_id`; Metrics EMF (độ trễ tool, số lần luật chặn, số giao dịch chưa phân loại, độ phủ dữ liệu) không tốn API riêng; Tracer X-Ray cho Lambda; đặt retention log 7–30 ngày (CDK `logGroup` với `retention`) để log không phình. Dashboard CDK `cloudwatch.Dashboard`: p95 từng tool, lỗi Lambda, độ sâu DLQ, `ServerlessDatabaseCapacity` của Aurora (0 = đang pause) [TL], thời lượng và lỗi Step Functions.
- **Alarm đề xuất**: DLQ `ApproximateNumberOfMessagesVisible > 0`; Step Functions `ExecutionsFailed/TimedOut`; Lambda `Errors` của `classify`/`forecast`; Aurora `ServerlessDatabaseCapacity` bất thường; chi phí (Budgets). Gửi về một SNS topic gắn email.
- **AWS Budgets**: ngân sách chi phí theo tháng, ngưỡng 50/80/100% thực tế và dự báo, thông báo qua email hoặc SNS [TL: https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-best-practices.html]. Dự báo cần khoảng 5 tuần dữ liệu nên **ngưỡng thực tế quan trọng hơn** cho dự án 3 tuần [TL: relationship của kết quả tìm kiếm]. Gắn thẻ `project=yofina` và kích hoạt cost allocation tag (có hiệu lực sau ~24 giờ [SĐ]).

**Dịch vụ tốn tiền kể cả khi không dùng, và cách giảm cho demo** (giá Singapore từ [API] nếu không ghi khác):

| Thứ | Chi phí nhàn rỗi | Cách giảm |
|---|---|---|
| Aurora Serverless v2 | 0,5 ACU ≈ 73 USD/tháng; lưu trữ 0,11 USD/GB | Min 0 ngoài cửa sổ demo; dev dùng cụm riêng bật/tắt |
| NAT Gateway | 0,059 USD/giờ ≈ 43 USD/tháng + tiền dữ liệu | **Không tạo**: Lambda ngoài VPC + Data API |
| VPC interface endpoint | 0,013 USD/giờ/AZ ≈ 9,5 USD/tháng mỗi cái mỗi AZ | Không cần nếu không đặt Lambda trong VPC |
| SageMaker real-time endpoint | `ml.m5.xlarge` 0,288 USD/giờ ≈ 210 USD/tháng | Không dùng; Lambda container |
| Secrets Manager | 0,40 USD/secret/tháng | Một secret DB; còn lại SSM |
| KMS CMK | 1 USD/khóa/tháng | Dùng khóa AWS quản lý |
| WAF web ACL | Phí tháng theo ACL/rule [chưa tìm được] | Bỏ hoặc để cuối |
| ECR, CloudWatch Logs, S3 | Nhỏ | Lifecycle rule, retention log |
| Địa chỉ IPv4 công khai (nếu có) | [SĐ] ~0,005 USD/giờ mỗi địa chỉ | Aurora không public |
| AgentCore, Bedrock, Knowledge Bases | Phần của agent khác | — |

Nguyên tắc: tên gọi `cdk destroy` các stack không stateful (`Tools`, `Agent`, `Frontend`) sau demo; `Data` có `terminationProtection` nên huỷ riêng.

### 3.9 Region

`get_regional_availability` (connector AWS MCP, `ap-southeast-1`, cấp sản phẩm) báo **có**: Amazon Aurora, Aurora DSQL, Cognito, Amplify, EventBridge, Step Functions, SageMaker AI, WAF, CloudFront, Lambda, SQS, Secrets Manager, KMS, CloudTrail, Bedrock AgentCore, Fargate, ECR, X-Ray, CloudWatch [TL: tool]. Cấp tính năng (đọc trong tài liệu): Aurora Serverless v2 PG 13.6+…18.3+ và platform v4; Data API PG ≥ 13.11…; SageMaker Serverless Inference có ở Singapore (concurrency 1.000); Powertools layer có ở `ap-southeast-1`; Aurora DSQL có endpoint `ap-southeast-1` (không dùng). Chưa kiểm riêng được: EventBridge Scheduler và Cognito managed login ở Singapore (filter tên "Amazon EventBridge Scheduler" không có trong danh mục; theo mục giá Cognito Essentials `ap-southeast-1` thì có [API]); Amplify Hosting compute (SSR) ở Singapore; AWS Budgets (dịch vụ toàn cầu). Từng tính năng AgentCore ở Singapore thuộc agent AgentCore.

## 4. Khuyến nghị cho Yofina (kiến trúc tối giản đủ cho demo)

**Sơ đồ rút gọn.**
```
Trình duyệt (Amplify static) --Cognito PKCE--> JWT
  ├─ chat: SSE → AgentCore Runtime (Bearer JWT)  → Gateway → Lambda tool (zip, ngoài VPC) → Aurora Data API
  └─ CRUD: API Gateway HTTP API (JWT authorizer) → Lambda ledger (cùng mã) → Aurora Data API
Event: ledger Lambda → EventBridge bus → SQS(+DLQ) → Lambda classify (Bedrock + Data API, idempotent bằng DynamoDB)
Batch: Scheduler cron(0 2 * * ? *) Asia/Ho_Chi_Minh → Step Functions Standard → Map(khối người dùng) → Lambda container (Chronos-2, StatsForecast, ruptures, PyOD, OR-Tools)
Aurora PG17 Serverless v2 (min 0.5), VPC isolated, 0 NAT. Budgets + dashboard + alarm DLQ.
```
**Chỉnh proposal.**
1. §14 "Chronos-2 trên SageMaker": đổi thành **Lambda container (CPU)**; SageMaker chỉ là phương án dự phòng. §13 "endpoint ML tắt khi không dùng" thành "không dùng endpoint".
2. §8/§13: ghi rõ **Aurora không scale về 0 trong lúc demo** (min 0,5 ACU) vì resume ~15 giây vi phạm NFR 2 giây; chi phí ~73 USD/tháng ở Singapore, không phải "thấp".
3. Thêm **API CRUD người dùng** (HTTP API + JWT authorizer) cho các màn không cần LLM; hiện proposal chỉ có đường agent.
4. §9/§10.3: ghi cơ chế **truyền danh tính người dùng tới Lambda tool** (interceptor/header), vì Gateway không đưa JWT vào Lambda và không cho allowlist `Authorization`.
5. §10.3: tách "khử trùng giao dịch" (khóa băm trong Aurora) khỏi "idempotency sự kiện" (DynamoDB theo `event_id`).
6. §14 "AWS CDK, khởi đầu từ khung FAST": đã chốt không dùng FAST; L2 AgentCore trong `aws-cdk-lib` nay stable (trừ Policy alpha).
7. WAF/CloudFront: đưa xuống ưu tiên thấp; không che chắn được luồng trình duyệt → AgentCore.
8. Thứ tự tuần 1 (hạ tầng): (a) danh tính IAM Identity Center + Budgets; (b) bootstrap + stack `Foundation`/`Data` (min 0,5, NAT 0); (c) migrator + schema; (d) Lambda `ledger` + HTTP API + Cognito; (e) thử CORS/SSE trình duyệt → AgentCore sớm.

## 5. Điều chưa chắc / cần chạy thử

1. **Độ trễ RDS Data API** (p50/p95) trên truy vấn đơn giản khi Aurora đang thức, và với tham số `CAST(:emb AS vector)`: [chưa tìm được số trong tài liệu]. Quyết định giữ Data API hay chuyển psycopg+VPC cho `affordability_check` phụ thuộc đo này. **[Đã chạy thử 2026-11-21] Đã trả lời:** 12–52 ms mỗi lệnh, flow 3 truy vấn p50 91 / p95 113 ms từ Lambda ngoài VPC; giữ Data API. kNN với `CAST(:q AS vector)` p50 51 ms (302 dòng). Xem `spike-aurora-data-api.md`.
2. RLS với Data API: giữ `set_config(..., true)` trong một transaction qua `BeginTransaction`/`transactionId` có hoạt động như mong đợi không (mỗi lần gọi ngoài transaction bị `DISCARD ALL`). **[Đã chạy thử 2026-11-21] Xác nhận**, kèm hai phát hiện: master user bỏ qua RLS kể cả khi `FORCE`; CTE `set_config` một lệnh không đáng tin. Xem `spike-aurora-data-api.md` mục 4.
3. **Danh tính xuống Lambda tool**: interceptor Gateway có đặt được header `x-user-id` từ claim JWT không; hoặc agent runtime thêm header từ claim đã xác minh. Cần xác nhận với agent AgentCore.
4. **CORS/preflight** từ trình duyệt tới endpoint AgentCore Runtime có JWT; có cần Lambda proxy streaming không.
5. Access token Cognito (`client_id`, không có `aud`) khớp `allowedClients` của AgentCore Runtime: [SĐ], chưa kiểm.
6. Aurora DSQL không có pgvector: dựa vào kết quả web search tóm tắt trang "unsupported features"; trang gốc bị chuyển hướng khi đọc, nên kiểm lại nếu thật sự cân nhắc DSQL.
7. `PythonFunction` của CDK đã vào `aws-cdk-lib` chưa hay vẫn ở `@aws-cdk/aws-lambda-python-alpha`; trạng thái L2 Amplify (`-alpha`); phiên bản `aws-cdk-lib` nên ghim (trang constructs.dev đang ở 2.277.0).
8. Cold start thực tế của Lambda container (torch + Chronos-2) và thời gian chạy một khối 25 người; kích thước image.
9. Thời gian Aurora resume thực tế ở Singapore, số lần resume mỗi ngày, và việc Performance Insights/Enhanced Monitoring/ghi log CloudWatch có chặn scale-down ở 0,5 ACU không (tài liệu có liệt kê nhưng tôi chỉ đọc tiêu đề tóm tắt). **[Đã chạy thử 2026-11-21] Một phần:** resume 16,4 giây (1 mẫu, ap-southeast-1, Aurora PG 18.6, pause khoảng 10 phút); instance không bật Enhanced Monitoring/PI nên pause được. Chưa đo pause dài, số lần resume/ngày, tác động của log CloudWatch.
10. Amplify Hosting với Next.js 16 và vị trí `baseDirectory` đúng cho `output: 'export'`; Amplify compute ở Singapore.
11. Phí web ACL/rule của WAF theo tháng và mức miễn phí Cognito: chưa tra.
12. Ghi chú: trang quota Lambda nay có thêm khái niệm "MicroVM" (thời gian chạy tối đa 8 giờ), khác với "Event Functions"; tôi không dùng nhưng có thể đáng xem cho job nền dài [TL: gettingstarted-limits].

## 6. Nguồn (truy cập 2026-11-21)

Tài liệu chính thức AWS [TL]:
- Aurora auto-pause: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2-auto-pause.html
- Aurora serverless capacity/platform: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.how-it-works.html
- Aurora serverless theo Region/phiên bản: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Concepts.Aurora_Fea_Regions_DB-eng.Feature.ServerlessV2.html
- Data API theo Region/phiên bản: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Concepts.Aurora_Fea_Regions_DB-eng.Feature.Data_API.html
- Data API giới hạn: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/data-api.limitations.html ; phiên: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/data-api.session-management.html ; tổng quan: https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/data-api.html
- Phiên bản extension (pgvector): https://docs.aws.amazon.com/AmazonRDS/latest/AuroraPostgreSQLReleaseNotes/AuroraPostgreSQL.Extensions.html
- Aurora PG làm vector store (dimension, HNSW, Data API, secret): https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.VectorDB.html
- Aurora DSQL Region: https://docs.aws.amazon.com/aurora-dsql/latest/userguide/what-is-aurora-dsql.html ; tương thích/giới hạn: https://docs.aws.amazon.com/aurora-dsql/latest/userguide/working-with-postgresql-compatibility-migration-guide.html
- Lambda runtime: https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html ; quota: https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html
- Powertools Python: https://docs.aws.amazon.com/powertools/python/latest/
- AgentCore Gateway Lambda target: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-add-target-lambda.html ; header: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-headers.html
- AgentCore inbound JWT: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/inbound-jwt-authorizer.html ; AG-UI contract: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-agui-protocol-contract.html ; CORS: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-tool-troubleshooting.html ; release notes (L2 stable): https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html
- EventBridge Scheduler: https://docs.aws.amazon.com/scheduler/latest/UserGuide/schedule-types.html
- Step Functions SageMaker: https://docs.aws.amazon.com/step-functions/latest/dg/connect-sagemaker.html ; Lambda: https://docs.aws.amazon.com/step-functions/latest/dg/connect-lambda.html
- SageMaker Serverless Inference: https://docs.aws.amazon.com/sagemaker/latest/dg/serverless-endpoints.html ; hosting FAQ (batch, async): https://docs.aws.amazon.com/sagemaker/latest/dg/hosting-faqs.html ; async autoscale: https://docs.aws.amazon.com/sagemaker/latest/dg/async-inference-autoscale.html
- CDK bootstrap/role: https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping-customizing.html ; bảo mật triển khai: https://docs.aws.amazon.com/cdk/v2/guide/best-practices-security.html
- IAM OIDC (GitHub): https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html
- Amplify Next.js: https://docs.aws.amazon.com/amplify/latest/userguide/ssr-amplify-support.html ; https://docs.aws.amazon.com/amplify/latest/userguide/deploy-nextjs-app.html ; WAF: https://docs.aws.amazon.com/amplify/latest/userguide/WAF-integration.html ; deploy thủ công: https://docs.aws.amazon.com/amplify/latest/userguide/manual-deploys.html
- Cognito feature plan/managed login: https://docs.aws.amazon.com/cognito/latest/developerguide/feature-plans-features-essentials.html
- Budgets: https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-best-practices.html
- Skill `aws-core:aws-serverless` (orchestration.md, event-sources.md, lambda.md) và `aws-core:aws-cdk` (bootstrap-and-project-setup.md) trong plugin aws-core 1.1.0.
- Công cụ `get_regional_availability` (connector AWS MCP, ap-southeast-1, nhiều sản phẩm).

Giá [API] (AWS Price List API qua connector AWS MCP, Singapore trừ khi ghi): Aurora Serverless v2 PG 0,20/ACU-giờ (IO-Opt 0,26), lưu trữ 0,11/GB-tháng, I/O 0,22/triệu; RDS `db.t4g.micro` 0,025/giờ, `db.t4g.small` 0,051/giờ; NAT 0,059/giờ; VPC endpoint 0,013/giờ; SageMaker host `ml.m5.xlarge` 0,288/giờ, `ml.c5.xlarge` 0,235/giờ; Secrets Manager 0,40/secret; KMS 1 USD/khóa, 0,03/10.000 request; WAF 0,60/triệu request; DSQL 0,000009/DPU, 0,4/GB-tháng; Aurora us-east-1 0,12/ACU-giờ.

Blog, repo mẫu, tìm kiếm web [BL]:
- Repo mẫu Aurora Data API + Step Functions (CDK TS): https://github.com/aws-samples/serverless-patterns/tree/main/sfn-aurora-data-api/typescript/cdk/lib/sfn-aurora-data-api-stack.ts
- Repo mẫu AgentCore Gateway + Lambda (CDK TS): https://github.com/aws-samples/serverless-patterns/tree/main/agentcore-gateway-lambda/typescript/cdk/lib/agentcore-gateway-lambda-stack.ts
- constructs.dev `aws-cdk-lib` 2.277.0 (Gateway, DatabaseCluster, Scheduler): https://constructs.dev/packages/aws-cdk-lib/v/2.277.0
- Powertools layer ARN (bản 44) theo trang cài đặt: https://docs.aws.amazon.com/powertools/python/latest/getting-started/install/index.md (đọc qua tóm tắt WebFetch)
- Giá Step Functions (0,000025/chuyển trạng thái us-east-1, 4.000 miễn phí/tháng): https://aws.amazon.com/step-functions/pricing/
- Chronos-2 (120M tham số, CPU/GPU, Apache-2.0, ví dụ Decathlon 7.000 chuỗi ~40 giây): https://huggingface.co/amazon/chronos-2 và các kết quả web search liên quan
- Tài liệu DSQL "unsupported features" (không có pgvector) qua web search: https://docs.aws.amazon.com/aurora-dsql/latest/userguide/working-with-postgresql-compatibility-unsupported-features.html (trang gốc chưa đọc được trực tiếp)
- Amplify với Next.js 16 (cộng đồng): https://dev.classmethod.jp/articles/aws-amplify-adapter-nextjs-v1-7-0-next-js-16/
