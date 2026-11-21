# Spike: Aurora PostgreSQL Serverless v2 + Data API + pgvector + RLS

Chạy ngày 2026-11-21 trên AWS thật (ap-southeast-1). Kết quả và kết luận: `docs/research/spike-aurora-data-api.md`.
Tài nguyên đã tạo và trạng thái dọn: `RESOURCES.md`.

## Tệp

| Tệp | Việc |
|---|---|
| `bench_core.py` | Lớp bọc `rds-data` (Api), các truy vấn đo, `run_bench`, `probe`, `vector_bench`. Dùng chung local và Lambda |
| `cfg.py` | Lấy ARN cluster/secret động (không ghi account ID vào file) |
| `setup_schema.py` | Extension `vector`, bảng `jars`/`transactions`/`forecasts`, dữ liệu giả 3 user, role `yofina_app` (non-owner) + secret, bật RLS |
| `setup_rls_fn.py` | Hàm plpgsql `rls_jars/rls_forecast/rls_txs`: `set_config` + truy vấn trong 1 lệnh Data API |
| `bench_local.py` | Đo từ máy local qua boto3 |
| `lambda_function.py` | Handler Lambda đo (ngoài VPC). Mode: bench (mặc định), `vector`, `probe`, `probe2`, `wake` |
| `t_rls.py`, `t_rls2.py` | Thử RLS (trong/ngoài transaction, owner vs app, CTE một lệnh) |
| `t_vector.py` | pgvector: tham số, HNSW, kNN, độ trễ |
| `t_limits.py` | Giới hạn 1 MiB, Batch, kiểu dữ liệu |
| `wait_pause.py` | Chờ auto-pause qua CloudWatch `ServerlessDatabaseCapacity` |
| `results/` | Đầu ra thô (JSON/text) của các lần chạy |

## Chạy lại

```bash
# 1) tạo cluster/instance theo RESOURCES.md (aurora-postgresql 18.6, --enable-http-endpoint, --manage-master-user-password)
python setup_schema.py && python setup_rls_fn.py
python bench_local.py 60
# 2) Lambda: zip lambda_function.py + bench_core.py, biến môi trường CLUSTER_ARN, ADMIN_SECRET_ARN, APP_SECRET_ARN
aws lambda invoke --region ap-southeast-1 --function-name yofina-spike-db-bench --payload fileb://ev.json out.json   # ev.json: {"n":100}
python t_rls.py; python t_rls2.py; python t_vector.py; python t_limits.py
```

Lưu ý: không bao giờ để một `BeginTransaction` mở dở (script RLS đầu tiên làm vậy): transaction treo giữ khóa
bảng và chặn `ALTER TABLE` tới khi Data API tự hủy (khoảng 3 phút) hoặc `pg_terminate_backend`.
