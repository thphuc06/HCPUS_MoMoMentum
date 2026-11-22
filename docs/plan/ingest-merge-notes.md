# Ghép nhánh `feat/ingest` (phase 5, luồng A: F6 nạp dữ liệu) vào `main`

Nhánh làm song song với phase 3, tách từ `e28b9e3` (bước 0 phase 3). Đọc file này trước khi merge. Thiết kế đầy đủ: [contracts/README.md](../../contracts/README.md) mục "Phase 5 (F6): nạp dữ liệu"; lịch sử: [docs/ai-log/2026-11.md](../ai-log/2026-11.md) (entry 22/11 23:30).

## Nhánh có gì

| Phần | Ở đâu |
|---|---|
| Migration `0050_ingest` (CHƯA chạy trên Aurora): `funding_source = 'external'`, bảng `ingest_jobs`, `ingest_rows`, `consents` (RLS FORCE), hàm luồng nạp, khử trùng chéo nguồn, độ phủ dữ liệu | `db/migrations/0050_ingest.sql` |
| Thư viện ingest: trích ảnh (Sonnet 4.6, dự phòng Kimi K3), parser CSV, che PII, khử trùng, gán hũ, worker, REST | `pipelines/ingest/yofina_ingest/`, `gateway/tools/ingest/handler_{api,worker}.py`, `libs/yofina_core/src/yofina_core/{ingest,pii}.py` |
| Stack `YofinaIngest` (CHƯA deploy): bucket, SQS + DLQ, Lambda `yofina-ingest-api` và `yofina-ingest`, 6 route `/ingest/*` gắn vào HTTP API `yofina-api` bằng JWT authorizer riêng; không sửa `YofinaTools` | `infra-cdk/lib/ingest-stack.ts`, `docs/aws-resources.md` |
| Frontend I1–I4 (nạp ảnh/CSV, tiến độ, duyệt dòng, độ phủ trước–sau) | `frontend/src/pages/IngestPage.tsx`, `frontend/src/features/ingest/` |
| Persona `vy` cho `giamkhao3` (thu nhập ngoài ví), tệp mẫu cho cảnh 5 | `data/personas/specs/vy.json`, `data/personas/samples/`, `scripts/seed_persona.py` |
| Bộ eval 58 mục (25 ảnh thật đã gán nhãn, 28 ảnh dựng, 5 CSV) | `evals/ingest/manifest.json`, `scripts/eval_ingest.py` (ảnh thật gitignored, tải lại bằng `--fetch`) |

## Xung đột đã biết khi merge với phase 3

Đa số là hai bên cùng thêm vào cuối một danh sách: giữ cả hai, phase 3 trước, ingest sau.

- `frontend` `REGISTERED_BY_FRONTEND` (`scripts/gen_contracts.mjs`): phase 3 đăng ký 6 khối, ingest 2 khối, gộp thành 16; chạy lại `node scripts/gen_contracts.mjs`, không sửa tay `frontend/src/contracts/*`. Sửa test đếm khối (`tests/unit/ts/blocks.fixtures.test.mjs`, `walletBlocks.test.tsx`, `registry.test.tsx`).
- `gateway/tools/ledger/yofina_ledger/repo.py` `RESET_DELETES`: phase 3 thêm `scenarios`, `nudges`, `feedback`; ingest thêm `ingest_rows`, `ingest_jobs`, `consents`. Giữ cả sáu, tất cả trước `transactions`.
- `wallet_writes.py`: ingest chỉ đổi một dòng (sự kiện `assign_jar` mang `funding_source` thật của dòng).
- `client.ts`, `schemas.ts` (frontend): ingest thêm `INGEST_TOOL_NAMES`, `AnyToolName`, client chọn cặp endpoint theo tool (`confirm_rows` đi `/ingest/*`).
- `contracts/rest/openapi.yaml`, `contracts/README.md`, `errors.py`, `wallet.py`: phase 3 trước, ingest sau.
- `docs/ai-log/2026-11.md`, `HANDOFF.md`: ghép tay (HANDOFF trên nhánh này không đổi).

## Phải kiểm khi merge

1. **Hàm SQL bị thay**: 0050 `CREATE OR REPLACE` năm hàm (`app_get_daily_spend`, `app_get_forecast_context`, `app_get_cashflow_summary`, `app_get_overview`, `app_get_overview_extras`). Migrator chạy theo tên tệp nên 0050 luôn chạy SAU mọi `001x`. Nếu phase 3 có migration mới thay một trong năm hàm này, phải gộp tay phần đổi của hai bên vào một migration chạy sau cùng. Lúc tạo nhánh: 0010 của phase 3 không thay hàm nào trong năm hàm.
2. **`confirm_rows` không còn qua ledger**: `wallet.ACTION_TOOLS` bỏ `confirm_rows` (nay ở `INGEST_ACTION_TOOLS`); ledger trả 400 `PARAMS_INVALID` nếu nhận nó. Test phase 3 so tool của khối `options` với `ACTION_TOOLS` đã được giản lược theo.
3. **`cdk synth` cả app** trên nhánh này lỗi "Thiếu luật Cedar cho tool run_scenario" vì luật Cedar phase 3 nằm ở nhánh của Học; hết khi gộp.
4. Sau merge chạy: `uv run pytest`, local_pg (lệnh trong docstring `tests/local_pg/conftest.py`, thêm `--with boto3`), `npm run typecheck`/`lint`/`vitest`/`build`/`check:bundle` trong `frontend/`, `npx tsc --noEmit` + `npm test` trong `infra-cdk/`.

## Deploy sau khi merge (một người deploy mỗi stack mỗi lúc)

1. `uv run scripts/migrate.py` (chạy 0050; người dùng không có dòng external thì mọi số liệu y hệt trước, có test).
2. Build zip ledger (kèm `--extra data/personas:personas` để có persona `vy`) và deploy `YofinaTools`: `RESET_DELETES` mới và consumer dự báo chạy đầy đủ khi gặp dòng external mới có hiệu lực.
3. Build zip ingest (`INGEST_BUILD_COMMAND` trong `infra-cdk/lib/ingest-stack.ts`) và `uv run scripts/cdk.py deploy YofinaIngest`. Không có thứ tính tiền theo giờ.
4. `uv run scripts/seed_demo.py giamkhao3` (nhóm `persona-vy`, đặt lại dữ liệu).
5. `print_env.py frontend --write`, build và deploy frontend.
6. Kiểm: đăng nhập `giamkhao3` trên localhost, Tổng quan → Tiền vào → "Nạp ảnh / sao kê ngoài ví", nạp `data/personas/samples/vy_sao_ke_vcb.csv`: độ phủ khoảng 66% lên 84%; nạp lại cùng tệp bị báo trùng; ảnh không phải tài liệu tài chính bị từ chối. Chạy `scripts/eval_ingest.py` tuần tự (`--sleep 8`).

## Chưa làm (để phase 5 hoặc lúc ghép)

- Tool Gateway `ingest___start_job`, `ingest___get_job_status`, `ingest___confirm_rows` và intent "mình vừa nạp ảnh" trong chat (target Gateway, Cedar `has confirm_token`, agent): đụng `agent/`, `YofinaAgent`.
- Phân loại theo pipeline phase 4 (hiện: bảng loại giao dịch, `category_rules`, rồi hũ model đề xuất).
- Quyết định có bật thu nhập ngoài ví cho `minh` hay không: buổi demo cuối đi cả 6 cảnh bằng `giamkhao1` (persona `minh`); bật thì phải kiểm lại cảnh 1 (hũ Ăn uống cạn 23/11). Hiện chỉ `giamkhao3` dùng persona `vy`.
- Mã lỗi riêng `INGEST_NO_TRANSACTIONS` (hiện tệp không còn dòng nào sau khi lọc dùng `INGEST_NOT_FINANCIAL` với câu báo khác).
