# scripts/

Script triển khai và tiện ích (deploy frontend, nạp dữ liệu persona, đặt lại tài khoản demo...). Proposal §14, §13 (nút đặt lại cho giám khảo).

- `gen_contracts.mjs`: sinh Zod (`frontend/src/contracts/blocks.ts`) từ `contracts/blocks/*.schema.json`; `--check` báo lệch. Xem [contracts/README.md](../contracts/README.md).
- `migrate.py`: gọi Lambda `yofina-migrator` chạy `db/migrations/*.sql` chưa chạy (`--dry-run` chỉ liệt kê); `--seed` nạp `db/seed/*.sql` (bảng tra `tx_type_map`, `fee_schedules`, `jar_templates`; version `seed_<tên>_<sha256 8 ký tự>`, viết lại được). Xem [../db/README.md](../db/README.md).
- `db_local_check.py`: chạy thử mọi migration và seed trên PostgreSQL cục bộ (pgserver, Python 3.12 tự ghim) rồi kiểm RLS, ràng buộc, quyền và hàm đọc; không gọi AWS. `uv run scripts/db_local_check.py`.
- `seed_demo.py` (luồng B): gán nhóm Cognito `persona-*` cho 6 tài khoản demo theo `data/personas/accounts.json` rồi đăng nhập SRP từng tài khoản và gọi `POST /demo/reset` (xóa dữ liệu của chính tài khoản đó, sinh lại persona, đặt đồng hồ mô phỏng về ngày neo). Chạy lại bao nhiêu lần cũng được: `uv run scripts/seed_demo.py [tài khoản...]`.
- `agent_deploy.py` (bước ghép): build zip agent ARM64 -> upload `builds/agent-<hash>.zip` lên bucket artifact -> ghi SSM `/yofina/agent/zip-key` -> `cdk deploy YofinaAgent` -> chờ Runtime READY. `uv run scripts/agent_deploy.py [--skip-build] [-c khóa=giá trị]`; mỗi lần cập nhật Runtime V2 mất khoảng 5 phút. Chi tiết: [../agent/README.md](../agent/README.md).
- `measure_latency.py` (luồng B): đo p50/p95 của `GET /jars`, `POST /confirmations`, `POST /actions` và luồng chuyển hũ qua REST thật.
- `_demo_auth.py`: hàm dùng chung (đăng nhập SRP tài khoản demo, gọi REST bằng `urllib`); `build_lambda.py` có thêm `--extra NGUỒN[:ĐÍCH]` để đóng kèm thư mục (dữ liệu persona) vào Lambda.
