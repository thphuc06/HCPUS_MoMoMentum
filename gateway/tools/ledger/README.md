# gateway/tools/ledger/

Lambda `yofina-ledger` (Python 3.13, arm64, ngoài VPC): ví mô phỏng trên Aurora qua Data API. **Một mã, hai đường vào**; mã nghiệp vụ không biết đường nào gọi mình. Proposal §9; FR1, FR3 (phần đọc), FR4, FR12. Quyết định: [ADR-0002](../../../docs/decisions/0002-xac-nhan-truoc-khi-ghi.md) (xác nhận bằng token một lần), [ADR-0003](../../../docs/decisions/0003-dong-ho-mo-phong.md) (đồng hồ mô phỏng); thiết kế hợp đồng phase 2: [contracts/README.md](../../../contracts/README.md#phase-2-ví-mô-phỏng-và-dự-báo).

| Đường vào | Danh tính (`user_id`) lấy từ | Dùng bởi |
|---|---|---|
| **HTTP API** (payload v2, `yofina-api`) | claim `sub` của JWT authorizer, **không bao giờ** từ thân yêu cầu hay query | frontend: các route trong [openapi.yaml](../../../contracts/rest/openapi.yaml) (mục "Route") |
| **AgentCore Gateway** (Lambda target) | trường `user_id` của sự kiện, do interceptor ghi đè bằng `sub` của JWT; tên tool ở `context.client_context.custom["bedrockAgentCoreToolName"]`, cắt tiền tố `ledger___`; tham số lạ bị bỏ qua | agent: mười tool của [ledger.json](../../../contracts/tools/ledger.json) (năm đọc, bốn ghi, `save_turn`), kết quả theo [ledger.results.schema.json](../../../contracts/tools/ledger.results.schema.json) |

## Cấu trúc

```
handler.py                 điểm vào: nhận diện HTTP (requestContext.http) hay Gateway, dựng dịch vụ một lần
yofina_ledger/
  settings.py              cấu hình từ biến môi trường YOFINA_* (CDK đặt); thiếu thì báo lỗi, không mặc định theo môi trường
  service.py               LedgerService: token (cấp, kiểm, tiêu), chuyển hũ, hội thoại, đặt lại demo; ghép hai mixin dưới
  wallet_reads.py          mixin ĐỌC: Tổng quan, chi tiết hũ, giao dịch (con trỏ), nghĩa vụ, hạn mức, lương, dòng tiền, chưa phân loại, dự báo
  wallet_writes.py         mixin GHI: chuẩn hóa, kiểm nghiệp vụ, xem trước (confirm_action), biên nhận (receipt_action), sự kiện
  repo.py                  SQL phase 1 (số dư, chuyển hũ, hội thoại, đề nghị đã xử lý, audit) và đặt lại demo
  repo_wallet.py           SQL ví: hàm đọc gộp, bảng tra, và các thao tác ghi (mỗi thao tác MỘT transaction)
  refdata.py               bảng tra dùng chung (loại giao dịch, biểu phí, hũ mẫu) đọc từ Aurora, giữ trong bộ nhớ vài phút
  proactive.py             chọn thẻ chủ động bằng luật tất định (không LLM)
  convert.py               dòng DB (Python hoặc jsonb) -> JSON của hợp đồng
  events.py                dựng và phát sự kiện lên EventBridge sau commit (lỗi không làm hỏng việc ghi)
  rest_api.py              định tuyến HTTP, lỗi {"error": {code, message, trace_id}}, status theo HTTP_STATUS
  gateway_api.py           định tuyến tool, kết quả {"status": OK | NEEDS_CONFIRMATION | ERROR, ...}
```

Dùng chung `yofina_core`: `db` (Data API), `confirm` (token), `params` (chuẩn hóa tham số), `schedule` (chu kỳ nghĩa vụ, mốc biểu đồ), `blocks` (dựng khối), `clock` (`app_today`), `wallet` (hằng số, `split_amount`), `errors`. Dữ liệu persona (`data/personas`) được đóng kèm vào zip.

Từ 26/11 (#39): `split_proposal.py` (đề xuất tỷ lệ khi kê khai, `POST /jars/split-proposal`) tính sàn chi từ mức nền bền (`yofina_core.spend_baseline`, cùng khóa cấu hình với LP) và kiểm tra theo kỳ lương theo cửa sổ chung `schedule.due_before_payday` (khoản đúng ngày lương thuộc kỳ trước, trả bằng số dư trước khi lương về). Lambda này cũng chạy tool `knowledge___resolve_date` (`yofina_knowledge.dates`, hôm nay và ngày lương đọc từ hồ sơ người gọi) cho Gateway và cho job sinh lại lộ trình.

## Route (HTTP API) và tool (Gateway)

| REST | Việc | Tool Gateway |
|---|---|---|
| `GET /overview` | Tổng quan: **một lệnh gọi** hàm `app_get_overview` (hồ sơ, mọi hũ, tóm tắt dự báo, hạn mức, nghĩa vụ sắp đến hạn, lương chờ, 5 giao dịch gần nhất, số cần xem lại); tổng số dư = mọi hũ kể cả hai hũ hệ thống; kỳ lương kế; thẻ chủ động | |
| `GET /profile`, `GET /jars`, `GET /jars/{jar_code}`, `GET /transactions`, `GET /obligations`, `GET /credit-line`, `GET /salary-events`, `GET /payees`, `GET /tx-types`, `GET /jar-templates` | Đọc cho màn hình. `GET /jars` không gồm hũ hệ thống; `GET /transactions` lọc theo hũ, loại, khoảng ngày, cần xem lại và phân trang bằng con trỏ mờ (LIMIT cứng ở SQL) | `get_jar_balances`, `query_transactions` (kind, tx_type, cursor), `get_cashflow_summary`, `get_obligations`, `get_unclassified` |
| `GET /forecasts/{jar_code}` | Khối `forecast_timeline`: đọc `forecasts`, `forecast_runs`, `forecast_jar_summaries` qua hàm `app_*`, ghép mốc nghĩa vụ và lương lúc đọc. Chưa có dự báo hoặc quá hạn độ tươi (`YOFINA_FORECAST_FRESHNESS_SECONDS`) thì **tính lại đồng bộ** bằng Lambda `yofina-forecast-batch` rồi mới trả; không tính được mà còn bản cũ thì trả bản cũ với `stale: true`, không có gì thì 503 `FORECAST_UNAVAILABLE` (`wallet_reads.forecast_response`). `GET /overview` thì chỉ kích hoạt tính lại ở nền để giữ p95 thấp | |
| `POST /confirmations` rồi `POST /actions` | Mọi thao tác ghi, sáu `tool`: `move_between_jars`, `record_transaction`, `assign_jar`, `update_profile`, `save_jars`, `confirm_salary` | bốn tool ghi đầu (không token thì `NEEDS_CONFIRMATION`); `save_jars` và `confirm_salary` chỉ có ở REST |
| `POST /confirmations/cancel` | Ghi việc người dùng bấm "Không" (`cancelled`) | |
| `POST /jars/split-proposal` | Đề xuất tỷ lệ chia lương theo nghĩa vụ và khoản biết trước | `ledger___propose_jar_split` (#41) nhận 1–5 `sinking_items`, dùng cùng luồng đọc và thêm dữ liệu thẻ xem trước `save_jars` khi có đề xuất |
| `GET /conversations`, `GET /conversations/{id}`, `POST /demo/reset` | Hội thoại đã lưu (kèm `resolutions`), đặt lại demo | `save_turn` |

## Lộ trình (phase 4, F5): `roadmap_*.py`

Lambda này CŨNG phục vụ ba tool của target `planner` về lộ trình và tám REST `/roadmap*`. Hợp đồng và lý do: [phase 4, "Quyết định hợp đồng phase 4"](../../../docs/plan/phases/phase-4-chong-chiu-lo-trinh.md#quyết-định-hợp-đồng-phase-4) (mục 3 đến 5, 14 đến 17, 19 đến 23).

```
yofina_ledger/
  roadmap_logic.py     logic THUẦN: bản nháp -> kiểm -> plan, dòng bảng -> RoadmapData (gộp trạng thái bước), so phiên bản, sửa một bước, lý do bằng chữ, lỗi từ DB
  roadmap_repo.py      SQL của roadmaps, roadmap_jobs, behavior_flags (đọc), audit_events và feedback; `save_in_tx` và `set_step_in_tx` dùng chung với seed
  roadmap_service.py   RoadmapOps: ba tool và logic tám REST; đứng cạnh LedgerService (`roadmap_ops(service)`), không sửa service.py
  roadmap_rest.py      phân tuyến và kiểm đầu vào tám REST (trường lạ trong thân bị từ chối, không có user_id)
  roadmap_seed.py      nạp lộ trình seed của persona khi đặt lại demo (`data/personas/roadmaps/<persona>.json`)
```

| Tool Gateway (`planner___*`) | Việc |
|---|---|
| `optimize_allocation` | Proxy mỏng (N1): `Invoke` ĐỒNG BỘ Lambda `yofina-forecast-batch` với `{"op": "optimize_allocation", "user_id", "args"}` (scipy nằm ở đó, không nằm ở zip ledger) và trả NGUYÊN VĂN phong bì của nó (kể cả phong bì lỗi nghiệp vụ). Lỗi gọi (hết giờ, Lambda lỗi, phản hồi lạ) hoặc chưa cấu hình `YOFINA_FORECAST_FUNCTION_NAME`: `FORECAST_UNAVAILABLE`, không đoán số. `ForecastClient.optimize_allocation` |
| `save_roadmap` | GHI không đổi số dư, KHÔNG qua token. Nhận `RoadmapDraft`; Lambda điền phiên bản, trạng thái (`status_for_new_version`: bản đầu và `step_edited` là `active`, còn lại `proposed`), `reason.text` (dựng từ sự kiện), `headline`, `counts`, `basis` (lần dự báo mới nhất; chưa có thì `FORECAST_UNAVAILABLE`), `rules_version`, `checked_rules` (luật đã kiểm thật, thay giá trị agent khai). Chạy lại `check_suitability` cho TỪNG bước bằng `yofina_planner`: vi phạm mức block thì `ROADMAP_INVALID` kèm mã luật, không lưu. Từ chối thêm: mã hũ không phải hũ của người dùng, `action` chuyển hũ lệch bước, lý do `step_edited` (chỉ người dùng tự sửa mới có), `behavior_flag_id` không phải dấu hiệu ĐÃ XÁC NHẬN của chính người gọi. `behavior_changed` đánh dấu dấu hiệu `confirmed` thành `applied` cùng transaction |
| `get_roadmap` | Đọc một phiên bản (`version` hoặc `which` active, proposed, latest) đã gộp trạng thái từng bước. `ROADMAP_NOT_FOUND` |

| REST | Luồng |
|---|---|
| `GET /roadmap` | Khối `roadmap` (`version` hoặc `which`; mặc định bản đang dùng) |
| `GET /roadmap/versions` | Danh sách gọn, `active_version`, `proposed_version`, `current_job` (job queued hoặc running) |
| `GET /roadmap/diff` | Khối `roadmap_diff`: vắng `to_version` thì bản chờ (không có thì bản đang dùng), vắng `from_version` thì bản gốc của bản `to`; hai bản trùng nhau là 400 |
| `POST /roadmap/steps/{step_id}/decision` | `accepted`, `rejected` (kèm `reason`), `pending` (hoàn tác) cho bước của bản `active` hoặc `proposed`; bản đã bị thay là 409. Idempotent: quyết định trùng không ghi gì. Ghi `audit_events` (`roadmap_step_decided`) và một dòng `feedback` (`block_id` là id khối `roadmap`, `option_id` là `step_id`) |
| `POST /roadmap/steps/{step_id}/edit` | Đổi số tiền hoặc ngày: lưu bản MỚI `active` (lý do `step_edited`), bước đã sửa `accepted` và `edited`, bước khác giữ trạng thái; bản gốc `superseded`, bản chờ bị bỏ. Số cũ trong tiêu đề và `action.params` đổi theo; chạy lại suitability cho bước đã sửa (422 `ROADMAP_INVALID`, không lưu). Không gọi model, không sinh lại toàn bộ. Feedback `accepted` lý do `edited` |
| `POST /roadmap/versions/{version}/decision` | `adopt` ("Dùng bản mới") hoặc `keep_previous` ("Giữ bản cũ") với bản chờ; idempotent; trả khối của bản được chọn. Feedback `version_adopt` hoặc `version_keep_previous` |
| `POST /roadmap/regenerate` | Ghi `roadmap_jobs` (`user_request`, `queued`), phát `roadmap.regeneration_requested` SAU commit (`event_id` bằng `job_id`; ghi chú tự do ở lại job, không vào sự kiện), trả job (HTTP 200). Đang có job chạy thì trả CHÍNH job đó, không ghi và không phát thêm |
| `GET /roadmap/jobs/{job_id}` | Tiến độ một job; của người khác, không tồn tại hay sai dạng đều 404 `ROADMAP_NOT_FOUND` |

Không có đường ghi tiền mới: lưu và đổi trạng thái lộ trình không ghi sổ cái; hành động trong một bước (`action`) vẫn đi qua `POST /confirmations` rồi `POST /actions`. Lỗi: `ROADMAP_NOT_FOUND` (404), `ROADMAP_INVALID` (422), `ROADMAP_VERSION_CONFLICT` (409); lỗi nghiệp vụ trong hàm SQL (`RAISE EXCEPTION 'MÃ: ...'`) được `roadmap_logic.db_business_error` đổi về đúng mã.

**Seed persona** (`data/personas/roadmaps/minh.json`, đọc README cùng thư mục; ví demo sau `POST /demo/reset` dùng cùng file, mã hũ đổi theo `JAR_ALIASES` của bộ hũ demo trong `jar_layout.py` và `data/personas/six_jars.py`, issue #39; từ 26/11 sáng ví demo có thêm hũ Chi hằng ngày của khối `demo_jars` trong spec persona, ba hũ mặc định đứng trước): đặt lại `minh` ra hai phiên bản, v1 `superseded` và v2 `active` (sửa bước `bu_an_uong`), để màn So với bản cũ có hai bản để so. Từ issue #22 file seed **không** có bản đề xuất v3 hay dấu hiệu `behavior_flags` cài sẵn: một dấu hiệu `confirmed` có sẵn sẽ làm batch đêm bỏ qua hũ đó và chặn cảnh 4 chạy thật (tải `minh_sao_ke_2_tuan.csv`, PELT xác nhận, Lambda sinh lại tạo bản đề xuất). Nạp TRONG transaction đặt lại (`LedgerRepo.reset_user` gọi `roadmap_seed`), mỗi phiên bản đi qua đúng đường thật; lộ trình seed vi phạm suitability thì đặt lại báo lỗi thay vì lưu. `reset_user` nhận thêm `app_date` tùy chọn (ngày neo); `LedgerService.reset_demo` chưa truyền nó nên hiện lấy ngày sau giao dịch mới nhất của persona (đúng với mọi persona hiện có).

**`RESET_DELETES`** có đủ bảng mới của 0052 (`roadmap_jobs`, `roadmaps`, `resilience_scores`, `review_asks`, `tx_embeddings`, `tx_embeddings_labeled`, `behavior_flags`) theo thứ tự khóa ngoại.

Test: `tests/unit/test_ledger_roadmap.py` (logic thuần, proxy, sự kiện, phân tuyến, `RoadmapOps` trên kho giả) và `tests/local_pg/test_roadmap_flow.py` (SQL, RLS, seed, REST, tool trên PostgreSQL thật; lệnh ở docstring của `tests/local_pg/conftest.py`).

## Luồng ghi (mọi tool)

1. `normalize_params(tool, params, ctx)` ([yofina_core/params.py](../../../libs/yofina_core/src/yofina_core/params.py)): bản chuẩn hóa tất định và idempotent; điền mặc định phụ thuộc trạng thái (hũ từ `tx_type_map`, hũ trả của nghĩa vụ, `due_date` từ `due_day`, mã hũ mới) bằng `NormContext` dựng từ DB và bảng tra. Thứ ký là thứ hiển thị.
2. Kiểm nghiệp vụ và dựng khối `confirm_action` (hoặc `confirm` cho chuyển hũ): hũ tồn tại, đủ số dư, hạn mức giao dịch, hạn mức Trả sau, người nhận và nghĩa vụ thuộc người gọi, lương và đề nghị chưa xử lý...
3. `POST /confirmations` kiểm lại rồi ký token HMAC (hạn 2 phút, `jti`) và trả kèm `preview` (`summary`, `changes`, `warnings`) do server tính, không ghi gì: số dư hũ trước và sau, với Trả sau thì khoản phải trả ngày đến hạn gồm phí từ `fee_schedules` và hạn mức còn lại. Màn "Xem lại" chỉ hiển thị, không tự tính.
4. `POST /actions` (hoặc tool có `confirm_token`): kiểm chữ ký, hạn, người, tool, hash; kiểm đề nghị (đã thực hiện, đã hủy, hết hạn); kiểm nghiệp vụ; **rồi mới** tiêu `jti` (nghiệp vụ sai không làm mất token); một transaction Data API khóa dòng liên quan (`FOR UPDATE`) rồi một câu CTE ghi sổ cái, số dư, nghĩa vụ, audit và (có `conversation_id` + `confirm_block_id`) biên nhận vào `confirm_resolutions`; **sau commit** phát sự kiện.

| Tool | Việc ghi |
|---|---|
| `record_transaction` chi bằng hũ | Dòng chi `funding_source jar` + trừ số dư (hũ Chưa phân loại được âm; hũ khác không). Không chọn hũ thì bước 0 `tx_type_map`, không khớp thì Chưa phân loại (`needs_review`). Người nhận (`payee_id`) cập nhật `last_used_at`, tên người nhận thành đối tác của dòng |
| `record_transaction` chi bằng Trả sau (`funding credit`) | Dòng chi `funding_source credit` (KHÔNG đổi số dư hũ) + nghĩa vụ `bnpl` sinh hoặc cộng dồn (ON CONFLICT trên chỉ mục duy nhất một phần theo ngày đến hạn) + dư nợ gốc tăng. Ngày đến hạn là `credit_lines.due_day` kế tiếp sau ngày mua; phí lấy từ `fee_schedules` (`ReferenceData.bnpl_monthly_fee`), tính MỘT lần cho mỗi nghĩa vụ; hạn mức kiểm trên dòng `credit_lines` đã khóa nên hai lần mua song song không vượt hạn mức |
| `record_transaction` trả nghĩa vụ (`obligation_id`) | Dòng chi gắn `obligation_id` từ một hũ; nghĩa vụ một lần thành `paid`, nghĩa vụ lặp dời `due_date` theo chu kỳ; trả sau giảm dư nợ gốc |
| `record_transaction` tiền vào | Vào hũ Tiền vào khác (không phải thu nhập). `tx_type salary` thêm `salary_events` `pending` kèm `deviation_percent` và cờ hỏi cập nhật lương theo ngưỡng cấu hình |
| `confirm_salary` | `split`: chia số nhận vào hũ bằng `split_amount` (dòng chuyển `salary_split`, cùng `transfer_id`); `keep_as_other`: giữ ở Tiền vào khác. `update_declared_salary` đặt lương đã khai bằng số nhận. Xử lý lần hai: 409 `ALREADY_APPLIED` |
| `assign_jar` | Dòng sổ cái chuyển sang hũ mới (UPDATE cột phân loại), số dư hai hũ đổi tương ứng; `remember` ghi `category_rules` (`once` hoặc `always`, theo người nhận hoặc đối tác) |
| `update_profile` | Lương, ngày nhận, mức rủi ro, tên, và MỘT nghĩa vụ mỗi lần (thêm, sửa, hủy; trả sau không khai, không sửa). Onboarding (chưa có hồ sơ): cần cả lương và ngày nhận, server tạo hồ sơ, hai hũ hệ thống, hũ `is_default` của `jar_templates` và hạn mức mặc định |
| `save_jars` | Thay cả danh sách hũ người dùng (tổng tỷ lệ bằng 100); hũ bị bỏ chỉ khi số dư 0, không nghĩa vụ trả bằng nó và chưa có dòng sổ cái nào (khóa ngoại), nếu không `JAR_PROTECTED` |
| `move_between_jars` | Như phase 1; hũ nguồn có thể là Tiền vào khác (cách gán tiền vào hũ) |

Mã lỗi: `NEEDS_CONFIRMATION` (428), `TOKEN_INVALID` / `TOKEN_EXPIRED` (403), `TOKEN_REUSED` / `PARAMS_MISMATCH` / `ALREADY_APPLIED` / `DUPLICATE_TRANSACTION` (409), `INSUFFICIENT_FUNDS` / `AMOUNT_LIMIT_EXCEEDED` / `CREDIT_LIMIT_EXCEEDED` / `JAR_PROTECTED` / `PROFILE_INCOMPLETE` (422), `JAR_NOT_FOUND` / `TRANSACTION_NOT_FOUND` / `OBLIGATION_NOT_FOUND` / `PAYEE_NOT_FOUND` / `SALARY_EVENT_NOT_FOUND` (404), `PARAMS_INVALID` (400), `FORECAST_UNAVAILABLE` / `DATABASE_UNAVAILABLE` (503; Aurora đang thức dậy, đã retry trong Lambda).

## Một đề nghị chỉ được thực hiện một lần, hủy được, và có hạn (migration 0004 và 0007)

`POST /confirmations` và `POST /actions` nhận thêm hai trường tùy chọn đi cùng nhau, `conversation_id` và `confirm_block_id` (id của khối `confirm` hoặc `confirm_action`, dạng `confirm:{trace_id}:{params_hash[:12]}`; `parse_confirm_ref` kiểm định dạng và 12 ký tự cuối phải khớp hash của tham số đang thực hiện, nếu không `PARAMS_MISMATCH`). Có hai trường này:

1. **Đã thực hiện hoặc đã hủy**: `repo.resolution` có dòng thì từ chối 409 `ALREADY_APPLIED` (thông điệp nói "đã thực hiện" hoặc "đã bị hủy"), trước khi tiêu `jti` và trước kiểm số dư; ghi một dòng `audit_events` `rejected`.
2. **Hết hạn** (server ép, không chỉ giao diện): `repo.confirm_block` đọc khối đã lưu (`turn_blocks`, do `save_turn` ghi) và so `data.expires_at` với giờ hiện tại; quá hạn thì 403 `TOKEN_EXPIRED` ("đề nghị đã hết hạn, hãy hỏi lại"). Khối chưa lưu được (lỗi lưu lượt) thì không có hạn để ép; token 2 phút dùng một lần vẫn là lớp bảo vệ. Chỉ khi có `confirm_block_id`: gọi REST trực tiếp và đường Gateway của agent không có kiểm tra này.
3. Cùng transaction ghi sổ cái chèn một dòng `confirm_resolutions` (khóa unique `(user_id, confirm_block_id)`, kèm biên nhận đã dựng): trùng khóa thì ném `ALREADY_APPLIED` và **cả transaction rollback**. Đây là lưới chắc chắn khi hai yêu cầu chạy song song (đã thử thật, kể cả hai lần xác nhận lương song song và hai lần mua Trả sau song song).
4. **Bấm "Không"**: `POST /confirmations/cancel` ghi dòng `status = 'cancelled'` (không biên nhận, không sổ cái). `GET /conversations/{id}` trả `resolutions` có `cancelled` (kèm `resolved_at`), `done` (kèm `receipt`), `expired`, `pending`; đã xử lý luôn thắng hết hạn. Hủy lại thì trả đúng kết quả cũ; đề nghị đã thực hiện thì không hủy được; đề nghị không thuộc người gọi: 400 (không lộ sự tồn tại).

Khóa theo `(user_id, confirm_block_id)` nên id của người khác chỉ tạo dòng của chính người gọi (RLS), không đánh dấu hay chặn đề nghị của ai. Đặt lại demo xóa `confirm_resolutions`.

## Sự kiện (EventBridge bus `yofina-bus`)

Sau MỖI lần ghi commit: `transaction.recorded` (chi, tiền vào, chuyển hũ, chia lương, gán hũ, trả nghĩa vụ; `event_id` = id dòng sổ cái hoặc `transfer_id`; gán hũ dùng `event_id` mới vì cùng giao dịch đã có sự kiện lúc ghi), `salary.confirmed` (cùng `transaction.recorded` của lần chia), `obligation.changed` (khai, sửa, hủy, trả, trả sau mới sinh hoặc cộng dồn), `profile.updated` (onboarding, lương, ngày nhận, hũ, mức rủi ro, tên, và đặt lại demo). Chi tiết đúng [contracts/events/](../../../contracts/events/); test kiểm từng sự kiện bằng JSON Schema. Không PII: chỉ id, mã hũ, số tiền. Lỗi phát (kể cả thất bại một phần) **không** làm hỏng việc ghi: log JSON + metric EMF `EventPublishFailed` (namespace `Yofina/Ledger`, có alarm `yofina-ledger-event-publish-failed` gửi SNS `yofina-alerts`), và một dòng `audit_events` mã `EVENT_PUBLISH_FAILED` để nightly bù. Bên nhận: `yofina-on-transaction` (dự báo theo sự kiện, [pipelines/event](../../../pipelines/event/README.md)), `yofina-classify` (phân hũ, [pipelines/classify](../../../pipelines/classify/README.md)), `yofina-roadmap-regen` ([pipelines/roadmap](../../../pipelines/roadmap/README.md)).

## Hiệu năng (đo thật, 2026-11-22, `uv run scripts/measure_wallet.py`)

Phía Lambda (log `rest_request`, ms trong handler, tài khoản `minh`, Lambda 512 MB đã ấm): `GET /overview` n=54 p50 15 ms, p95 16 ms, max 95 ms (một lệnh gọi Data API) so với mục tiêu p95 < 300 ms; `POST /confirmations` p50 14, p95 18 ms; `POST /actions` (chi 1.000 ₫: khóa hũ, ghi CTE, tiêu `jti` ở DynamoDB, phát sự kiện) p50 213, p95 236 ms. Phía máy gọi qua Internet: `GET /overview` p50 133, p95 215 ms; luồng ghi hai bước p50 475, p95 500 ms.

## Cấu hình (biến môi trường, do `infra-cdk/lib/tools-stack.ts` đặt)

`YOFINA_REGION`, `YOFINA_DB_CLUSTER_ARN`, `YOFINA_DB_APP_SECRET_ARN` (secret của role `yofina_app`, **không** phải master), `YOFINA_DB_NAME`, `YOFINA_DB_RESUME_MAX_WAIT_SECONDS`, `YOFINA_CONFIRM_JTI_TABLE`, `YOFINA_CONFIRM_HMAC_SECRET_ARN`, `YOFINA_CONFIRM_TOKEN_TTL_SECONDS`, `YOFINA_CONFIRM_TOKEN_MAX_TTL_SECONDS`, `YOFINA_CONFIRM_OFFER_TTL_SECONDS`, `YOFINA_MOVE_MAX_AMOUNT_VND`, `YOFINA_TRANSACTION_MAX_AMOUNT_VND`, `YOFINA_TRANSACTIONS_DEFAULT_LIMIT`, `YOFINA_TRANSACTIONS_MAX_LIMIT`, `YOFINA_SALARY_DEVIATION_ASK_PERCENT`, `YOFINA_DEFAULT_CREDIT_LIMIT_VND`, `YOFINA_DEFAULT_DISPLAY_NAME`, `YOFINA_FORECAST_FRESHNESS_SECONDS`, `YOFINA_PROACTIVE_OBLIGATION_DAYS`, `YOFINA_REFERENCE_CACHE_SECONDS`, `YOFINA_EVENT_BUS_NAME`, `YOFINA_APP_TIMEZONE`, `YOFINA_DEMO_ANCHOR_DATE`, `YOFINA_LOG_LEVEL`. Giá trị mặc định ở `ToolsConfig` của stack, đổi bằng context (`-c transactionMaxAmountVnd=...`). Biểu phí và loại giao dịch không ở đây mà ở bảng DB (`fee_schedules`, `tx_type_map`).

## Đóng gói, deploy, kiểm

```bash
uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 --keep-boto --extra data/personas:personas --extra gateway/tools/planner/yofina_planner:yofina_planner --extra gateway/tools/planner/rules:rules --extra gateway/tools/knowledge/yofina_knowledge:yofina_knowledge --extra gateway/tools/audit/yofina_audit:yofina_audit   # LEDGER_BUILD_COMMAND của infra-cdk/lib/tools-stack.ts; --keep-boto: boto3 ghim trong requirements.txt
uv run scripts/migrate.py                                              # 0007_wallet_ops (và --seed khi đổi bảng tra)
uv run scripts/cdk.py deploy YofinaTools --require-approval never      # cần zip ở build/lambda/ledger-arm64.zip
uv run scripts/cdk.py deploy YofinaAgent --require-approval never      # target 10 tool + Cedar mỗi tool (khi đổi contracts/tools/ledger.json)
uv run scripts/seed_demo.py                                            # nạp persona cho 6 tài khoản demo
uv run pytest libs tests/unit                                          # unit (kho giả, hàm thuần, hợp đồng, sự kiện theo JSON Schema)
uv run --python 3.12 --no-project --with pgserver --with "psycopg[binary]" --with pydantic --with pytest --with jsonschema --with pyyaml --with referencing --with numpy --with boto3 pytest tests/local_pg -p no:cacheprovider
uv run pytest tests/integration -m integration                         # thật: REST, Gateway, RLS, sự kiện, onboarding (tạo rồi dọn tài khoản thử)
uv run scripts/measure_wallet.py                                       # p50/p95 GET /overview và luồng ghi (cả phía Lambda)
```

`tests/local_pg/` chạy NGUYÊN `DataApi` và `LedgerRepo` trên PostgreSQL thật cục bộ (pgserver, role `yofina_app` không phải owner nên RLS và quyền được kiểm thật; bản giả của client `rds-data` ở `local_data_api.py`): nhanh hơn deploy để bắt lỗi SQL, và là nơi thử đua song song bằng nhiều luồng.

Giới hạn đã biết: `query_transactions` đọc tối đa 50 dòng mỗi lần (giới hạn 1 MiB của Data API); tin vào `user_id` của sự kiện Gateway nghĩa là interceptor bắt buộc phải ghi đè nó (Lambda không thấy JWT); hũ có lịch sử giao dịch không xóa được qua `save_jars` (khóa ngoại của sổ cái; chỉ hũ mới tạo chưa dùng mới bỏ được); phí Trả sau chỉ hỗ trợ dạng số tiền cố định (`amount_vnd`), chưa có dạng phần trăm vì chưa có nguồn.
