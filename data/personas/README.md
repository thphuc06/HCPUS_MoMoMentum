# data/personas/

Dữ liệu persona **seed** cho demo: hồ sơ, hũ (kể cả hai hũ hệ thống), người nhận, nghĩa vụ, hạn mức Trả sau và sổ cái giao dịch tất định theo seed, nạp vào Aurora khi bấm "Đặt lại dữ liệu" (`POST /demo/reset`) hoặc chạy `scripts/seed_demo.py`. Dự án không có API giao dịch thật nên seed là cách duy nhất đưa dữ liệu vào; theo master-plan ("Không hardcode, không giả lập") thì **dữ liệu này nằm ở đây, không nằm trong mã nghiệp vụ Lambda hay frontend**, và mọi con số trên màn hình vẫn đi từ Aurora qua tool.

| File | Nội dung |
|---|---|
| `specs/<persona>.json` | Dữ liệu đầu vào của một persona: lương, ngày lương, mức rủi ro, số ngày lịch sử, seed, **nhịp chi tiêu** (`rhythm_defaults`, `rhythm` của từng hũ), danh sách hũ (mã, tên, loại, khóa màu/biểu tượng, tỷ lệ chia, số dư đầu kỳ, **số dư cần đạt**, số khoản chi, cửa hàng kèm `tx_type`, mục tiêu), `payees`, `obligations`, `credit_line`, `bnpl.purchases`, `system_jars` |
| `generator.py` | `generate(persona, anchor=...)` dựng sổ cái; `materialize(...)` ghép với đồng hồ mô phỏng ([ADR-0003](../../docs/decisions/0003-dong-ho-mo-phong.md)) và dựng id tất định; `persona_from_groups`, `parse_groups_claim` |
| `out_of_wallet.py` | `generate_out_of_wallet(persona, anchor=...)`: dựng khoản chi NGOÀI ví (thứ người dùng sẽ nạp từ sao kê hoặc ảnh) từ khối `out_of_wallet` của spec; `statement_csv` ghi sao kê CSV kiểu VCB. Không vào sổ cái seed |
| `samples/` | Tệp mẫu để tải lên ở cảnh 5 (`vy_sao_ke_vcb.csv`, `vy_bien_lai_1.png`, `vy_bien_lai_2.png`) và `make_samples.py` sinh ra chúng; xem mục "Tệp mẫu cho cảnh 5" |
| `accounts.json` | Ánh xạ tài khoản demo → persona và tiền tố nhóm Cognito (`persona-`). Mã sản phẩm không rẽ nhánh theo email: persona của người gọi lấy từ nhóm Cognito (claim `cognito:groups`) |

## Persona

| Persona | Dùng cho | Hồ sơ | Hũ | Lịch sử |
|---|---|---|---|---|
| `minh` | `minh`, `giamkhao1`, `giamkhao2`, `giamkhao3` | Lương 9.000.000 ₫ ngày 5, rủi ro vừa | 7 hũ khớp [bảng số Figma §5](../../docs/research/figma-ui-design.md): Ăn uống 380.000, Đi lại 640.000, Hóa đơn 450.000, Giải trí 760.000, Du lịch 1.800.000 (mục tiêu 6.000.000 ₫ đến 1/4/2027), Dự phòng 2.700.000, Nghĩa vụ 1.000.000 (tổng 7.730.000), tỷ lệ chia 30/7/31/7/10/10/5. Hai hũ hệ thống: **Tiền vào khác +350.000** (Huy trả lại tiền ăn) và **Chưa phân loại −180.000** (hai khoản CHI chưa xếp hũ: QR 120.000 và chuyển tiền 60.000). Tổng số dư 7.900.000 ₫ (Figma ghi 8.260.000 vì coi Chưa phân loại là +180.000; hợp đồng cho số dư có dấu, xem quyết định số 2 của phase 2) | 120 ngày trước ngày neo 21/11/2026 (từ 24/7, bốn kỳ lương 5/8 đến 5/11; issue #8), 413 dòng, mật độ chi như bản 47 ngày cũ. Không cài điểm gãy hành vi: cuối ba kỳ trước Minh bù hũ Ăn uống từ Du lịch, Dự phòng, Nghĩa vụ (`jar_transfers`, ngày 21/8, 21/9, 21/10) để mức chi mỗi ngày của các kỳ ngang kỳ hiện tại |
| `lan` | `lan` (sinh viên làm thêm) | Lương 4.500.000 ₫ ngày 5, rủi ro thấp | 5 hũ (Ăn uống, Đi lại, Hóa đơn, Giải trí, Dự phòng); hạn mức Trả sau 2.000.000 ₫, không có khoản trả sau sẵn | 47 ngày, 106 dòng |
| `khoa` | `khoa` (tài khoản mới, ít dữ liệu: độ tin cậy thấp) | Lương 7.000.000 ₫ ngày 5 | 5 hũ; tiền thuê phòng 1.400.000 ₫ đến hạn ngày 1 (chưa trả trong 18 ngày lịch sử) | 18 ngày, một kỳ lương, 46 dòng |
| `vy` | nạp bằng `scripts/seed_persona.py --persona vy` (cảnh 5: nạp dữ liệu ngân hàng khác, F6; không còn tài khoản giám khảo nào dùng) | Nhà thiết kế, lương 8.000.000 ₫ ngày 5 vào ví, **cộng 4.800.000 ₫ mỗi tháng freelance về tài khoản Vietcombank khác** (ngày 18), rủi ro vừa | 6 hũ (Ăn uống, Đi lại, Hóa đơn, Giải trí, Du lịch, Dự phòng), 5 nghĩa vụ (thuê phòng, Internet, điện thoại, điện, Spotify), hạn mức Trả sau 3.000.000 ₫ | 47 ngày, hai kỳ lương, 147 dòng (2 dòng là thu nhập ngoài ví) |

**Nghĩa vụ của `minh`** (ngày đến hạn kế tiếp tính từ ngày neo): Tiền điện 375.000 ₫ (khoảng 300.000 đến 450.000, ngày 26, hũ Hóa đơn), Trả sau (mô phỏng) **1.000.000 ₫ = gốc 967.000 + phí 33.000** đến hạn 5/12 trả từ hũ Nghĩa vụ (phí lấy từ bảng `fee_schedules` lúc nạp, không gắn cứng), Tiền thuê phòng 2.000.000 ₫ (ngày 6), Internet FPT 220.000 ₫ (ngày 12), Netflix 180.000 ₫ (ngày 15, hũ Giải trí), Cước điện thoại 100.000 ₫ (ngày 20). Tiền cơm văn phòng 300.000 ₫ (ngày 23, trả từ hũ Ăn uống; thêm ở đợt hiệu chỉnh cảnh 1, xem dưới). Hạn mức Trả sau 5.000.000 ₫, dư nợ gốc 967.000 ₫ (hai giao dịch mua bằng hạn mức trong lịch sử: 520.000 và 447.000). Người nhận: Trần Quang Huy (yêu thích, người nhận của cảnh chuyển tiền demo), Nguyễn Thu Hà, Mẹ, Lê Minh Châu. Hóa đơn tháng 11 chưa tới hạn tiền điện nên hũ Hóa đơn (450.000) "sát" như Figma.

## Hiệu chỉnh cảnh 1 (phase 2, luồng C)

Mục tiêu: sau `POST /demo/reset`, **engine thật** (`yofina_ml`, 10.000 đường, đọc từ Aurora qua pipeline) báo hũ Ăn uống cạn ngày 23/11/2026 mô phỏng (hôm nay 21/11, lương 5/12: "còn 12 ngày nữa mới tới kỳ lương"), số dư bảy hũ giữ đúng bảng Figma, dữ liệu vẫn tự nhiên. Chỉ sửa **đầu vào** trong `specs/minh.json`; không số đầu ra nào nằm trong mã sản phẩm.

Quét tham số trên PostgreSQL cục bộ với pipeline thật cho thấy: chỉ thay nhịp và mức chi của hũ Ăn uống KHÔNG đủ. Mô hình hurdle theo lịch (cửa sổ 180 ngày, nửa đời 180 ngày) dự báo gần bằng mức chi trung bình của cả 47 ngày (khoảng 100.000 ₫ mỗi ngày với số dư đầu 0 và lương chia 2,7 triệu), nên với 380.000 ₫ hũ chỉ cạn quanh 26/11. Để cạn ngày 23/11 chỉ bằng nhịp chi phải đẩy mức chi lên khoảng 200.000 ₫ mỗi ngày (cần số dư đầu kỳ trên 4 triệu ₫ cho một hũ ăn uống): không tự nhiên. Cách tự nhiên là thêm một **khoản nợ nhỏ có lịch**, đúng tinh thần "tính cả nợ nhỏ" của đề bài:

| Số đã chỉnh | Giá trị | Ý nghĩa |
|---|---|---|
| Nghĩa vụ mới `Tiền cơm văn phòng` | 300.000 ₫, ngày 23 hằng tháng, trả từ hũ Ăn uống, đã trả đủ trong lịch sử (23/10) | suất cơm trưa văn phòng trả theo tháng; đến hạn 23/11, đúng lúc số dư dự báo của hũ chỉ còn khoảng 190.000 ₫ |
| Hũ Ăn uống: `expense_count` 70 -> 110, `rhythm` {`weekend_multiplier` 2,6; `max_per_day` 5; `amount_sigma` 0,45}, `recent_share` 0,5 -> 0,58 | | nhiều khoản nhỏ hơn mỗi ngày (ăn sáng, cà phê, ăn trưa, đặt đồ), cuối tuần chi nhiều hơn rõ, chi dồn về cuối kỳ như spec ghi; `target_vnd` vẫn 380.000 ₫ và mọi hũ khác không đổi |

Kết quả đã đo (engine thật, ngày mô phỏng 21/11/2026): hũ Ăn uống số dư P50 ngày 22/11 khoảng 275.000 đến 310.000 ₫ (còn dương), ngày 23/11 khoảng -75.000 đến -105.000 ₫ nên **ngày cạn 23/11** ổn định qua tám seed khác nhau (không phải một ca may mắn) và qua nhiều lần đặt lại (hạt tất định theo người dùng); hũ Hóa đơn "sát" (xác suất hụt khoảng 0,2 đến 0,35 vì tiền điện 26/11), Đi lại, Giải trí, Du lịch, Dự phòng, Nghĩa vụ "đủ". Số liệu chi tiết và so với Figma ở [phase-2-vi-va-du-bao.md](../../docs/plan/phases/phase-2-vi-va-du-bao.md#kết-quả-thực-hiện). Hệ quả khác: tổng chi Ăn uống trong lịch sử giảm từ 5.020.000 xuống 4.720.000 ₫ (300.000 ₫ nay là khoản trả nghĩa vụ ngày 23/10, không tính vào chi tiêu), `minh` có 7 nghĩa vụ và 166 dòng sổ cái (trước đó 6 và 125).

## Thu nhập ngoài ví và độ phủ dữ liệu (F6, persona `vy`)

Ba persona cũ có ví đóng: mọi thu nhập là lương vào ví nên độ phủ dữ liệu `clamp((spend + balance_end - balance_start) / income, 0, 1)` luôn là 1 (test `test_ba_persona_cu_phu_tron_theo_cong_thuc_0050`), và câu chuyện "độ phủ tăng sau khi nạp sao kê ngân hàng khác" không kể được. `vy` có một dòng thu nhập về ngân hàng khác mà phần chi từ đó chưa được ghi, nên độ phủ nhỏ hơn 1 cho tới khi người dùng nạp sao kê.

Tham số spec mới (đều tùy chọn; vắng thì bộ sinh cho ĐÚNG kết quả cũ, ba persona cũ không đổi một byte):

| Khóa | Ý nghĩa |
|---|---|
| `external_income_monthly_vnd` | Thu nhập hằng tháng về tài khoản ngân hàng khác. Mỗi tháng trong lịch sử một dòng `income`, `funding_source external`, **không hũ**, không đổi số dư hũ nào, `tx_type` mặc định `income_other` |
| `external_income.day` | Ngày trong tháng (mặc định 15; lớn hơn số ngày của tháng thì lấy ngày cuối tháng) |
| `external_income.merchant`, `.note`, `.tx_type`, `.hour` | Nhãn, ghi chú, loại giao dịch, giờ của dòng |
| `external_income.statement_text` | Nội dung dòng tiền vào trong sao kê CSV mẫu |
| `out_of_wallet` | Khối khai khoản chi ngoài ví KHÔNG có trong sổ cái seed (người dùng sẽ nạp): `bank`, `opening_balance_vnd` (số dư đầu sao kê), `dedupe_margin_days`, và `sources` (mỗi nguồn: `id`, `channel` csv hoặc image, khoảng `from_days_ago`..`to_days_ago`, `rhythm`, `groups` theo hũ gồm `count`, `total_vnd`, `merchants` kèm `tx_type` và `bank_text`). Chỉ `generate_out_of_wallet` đọc nó; `generate` bỏ qua |

Số tiền chi ngoài ví ra từ tổng mỗi nhóm hũ trong spec qua cùng hàm chia lognormal và chọn ngày theo nhịp với bộ sinh persona. Mỗi `tx_type` là loại mà `db/seed/tx_type_map.sql` đã gán hũ mặc định, nên hũ của từng dòng đoán được ngay ở bước 0 của phân loại (test kiểm). Không khoản chi ngoài ví nào trùng số tiền với giao dịch trong ví (hay nguồn nạp khác) trong `dedupe_margin_days` ngày (rộng hơn cửa sổ khử trùng mặc định 3 ngày), nếu không worker sẽ loại nhầm nó thành bản sao. Ngược lại hai dòng TIỀN VÀO của sao kê cố ý trùng ngày và số tiền với hai dòng thu nhập ngoài ví đã seed: khử trùng loại chúng, thu nhập không bị cộng đôi (không thì độ phủ tụt xuống dưới dải, test phản chứng kiểm điều đó).

Công thức trên dữ liệu `vy`: `income` = lương vào ví + thu nhập ngoài ví; `spend + net_jar` = số dư đầu kỳ + lương (số chi trong ví tự triệt tiêu); nạp thêm chi ngoài ví `S` thì tử số tăng đúng `S`. Số đo (đầu ra tính toán, test dựng lại bằng `yofina_ml.quality.data_coverage` rồi so với `app_get_data_coverage` trên PostgreSQL thật; test chỉ khẳng định dải 0,60 đến 0,70 trước và 0,80 đến 0,90 sau):

| Thời điểm | Thu nhập | Tử số | Độ phủ |
|---|---|---|---|
| Sau `POST /demo/reset` (chưa nạp) | 25.600.000 ₫ | 17.000.000 ₫ | **0,664** |
| Sau khi nạp `vy_sao_ke_vcb.csv` (39 dòng chi, 4.490.000 ₫; 2 dòng tiền vào bị khử trùng) | 25.600.000 ₫ | 21.490.000 ₫ | **0,839** |
| Sau khi nạp thêm hai ảnh biên lai (265.000 ₫) | 25.600.000 ₫ | 21.755.000 ₫ | 0,850 |

Muốn đổi số kịch bản thì sửa các số trong `specs/vy.json` (`external_income_monthly_vnd`, `total_vnd` của nhóm), không sửa mã. Sau khi nạp, chi ngoài ví cũng vào lịch sử chi của hũ (`app_get_daily_spend`), nên dự báo từng hũ đổi theo: đó là ý của cảnh 5.

## Tệp mẫu cho cảnh 5

`samples/` do `samples/make_samples.py` sinh, tất định theo seed của spec và ngày neo (chạy lại: `uv run --with pillow python data/personas/samples/make_samples.py`, cần font Windows như `scripts/make_ingest_synthetic.py`). Test `test_tep_csv_da_commit_khop_bo_sinh` bắt tệp CSV lệch bộ sinh. Mọi tên, mã, số tham chiếu là hư cấu; ngày lấy theo ngày mô phỏng của `vy` (ngày neo 21/11/2026, nên tệp chỉ hợp lệ trên tài khoản đã đặt lại về ngày neo).

| Tệp | Nội dung | Dùng ở cảnh 5 |
|---|---|---|
| `vy_sao_ke_vcb.csv` | Sao kê kiểu Vietcombank (cùng cột và cách ghi với `evals/ingest/synthetic/csv/c01_vcb_50.csv`), 41 dòng từ 7/10 đến 19/11: 39 khoản chi (Highlands, GrabFood, Bách Hóa Xanh, Grab, CGV, Viettel, vé máy bay Vietjet...) và 2 dòng tiền vào freelance | **TẢI TỆP NÀY TRƯỚC**: độ phủ 0,664 -> 0,839, hai dòng tiền vào hiện là "trùng", hũ gợi ý đúng cho hầu hết dòng chi |
| `vy_bien_lai_1.png`, `vy_bien_lai_2.png` | Ảnh biên lai chuyển khoản dựng bằng Pillow (kiểu Techcombank trả Grab, kiểu MB trả CGV), ngày 20/11, KHÁC mọi dòng của sao kê | Cảnh tải ảnh (nếu kịch bản cần một giao dịch lẻ); tải sau CSV thì độ phủ lên 0,850 |

Tài khoản demo: `giamkhao3` (persona `vy`). Trước buổi demo bấm "Đặt lại dữ liệu" để độ phủ về 0,664 và xóa sạch lần nạp trước (đặt lại xóa cả dòng external, job nạp và đồng ý).

## Nạp persona mới lên AWS (giamkhao3 nhận `vy`)

Hiện trạng đã đọc từ mã (chưa chạm AWS): persona của người gọi lấy từ nhóm Cognito `persona-<tên>` (claim `cognito:groups`), và `POST /demo/reset` của Lambda `yofina-ledger` chỉ nhận tên có trong `personas.available_personas()` của thư mục `data/personas` ĐÃ ĐÓNG TRONG ZIP của nó (`--extra data/personas:personas`). Lambda đang deploy là bản trước `vy`, nên có hai việc tách bạch: đổi nhóm của tài khoản và đưa dữ liệu vào Aurora.

**Điều kiện trước**: migration `0050_ingest` phải đã chạy trên Aurora (Lambda migrator). Thiếu nó thì ràng buộc `transactions_funding_check` từ chối `funding_source external`; việc nạp là MỘT transaction nên thất bại không để lại dữ liệu dở dang, `giamkhao3` giữ nguyên dữ liệu cũ.

Hai đường, chọn một:

1. **Chờ ledger được deploy lại lúc ghép nhánh** (đường chính thức): `uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 --extra data/personas:personas`, rồi `uv run scripts/cdk.py deploy YofinaTools` (chủ stack là đồng đội). Sau đó `uv run scripts/seed_demo.py giamkhao3`: bước 1 đổi `giamkhao3` sang nhóm `persona-vy` (tạo nhóm nếu thiếu, gỡ khỏi `persona-minh`), bước 2 đăng nhập và gọi `POST /demo/reset` nạp `vy` cùng dự báo. LƯU Ý thứ tự: chạy `seed_demo.py giamkhao3` TRƯỚC khi ledger biết `vy` thì nhóm đã đổi nhưng `POST /demo/reset` trả 403 `FORBIDDEN` ("không phải tài khoản demo") và dữ liệu cũ (minh) vẫn còn; chạy lại sau khi deploy là xong. Zip ledger sẽ kèm cả `data/personas/samples/` (khoảng 100 KB tệp mẫu, vô hại; muốn gọn thì thêm `samples` vào `IGNORE_COPY` của `scripts/build_lambda.py`).
2. **Nạp độc lập, không cần deploy ledger**: `uv run scripts/seed_persona.py giamkhao3` (mặc định CHẠY THỬ, không gọi AWS: in số dòng theo nguồn trả, số dư hũ, độ phủ dự kiến) rồi `uv run scripts/seed_persona.py giamkhao3 --apply [--forecast]`. Script dùng chính `LedgerService.reset_demo` làm thư viện (bộ sinh, `materialize`, `LedgerRepo.reset_user`, dựng lại số dư từ dòng trả bằng hũ nên bất biến "số dư mỗi hũ = tổng dòng `jar`" giữ cả khi có dòng `external`), đọc secret của role `yofina_app` qua Data API (RLS theo `sub` của tài khoản, lấy từ Cognito `AdminGetUser`), lấy ngày neo và múi giờ từ cấu hình Lambda đã deploy, và đổi nhóm Cognito như `seed_demo.py`. Quyền cần: `ssm:GetParameter` `/yofina/*`, `cognito-idp:AdminGetUser`, `AdminListGroupsForUser`, `CreateGroup`, `AdminAddUserToGroup`, `AdminRemoveUserFromGroup`, `lambda:GetFunctionConfiguration` trên `yofina-ledger`, `rds-data:*Statement` và `*Transaction` trên cluster, `secretsmanager:GetSecretValue` trên `yofina-db-app`, `events:PutEvents` (phát `profile.updated`); thêm `lambda:InvokeFunction` trên `yofina-forecast-batch` nếu dùng `--forecast`. Nhóm đã là `persona-vy` mà ledger chưa deploy lại thì nút "Đặt lại dữ liệu" của tài khoản đó trả 403 cho tới khi ledger được deploy lại (dữ liệu vẫn đúng). Nếu cần nút này dùng được ngay thì thêm `--skip-group` (giữ nhóm `persona-minh`): khi đó nút sẽ đặt lại `giamkhao3` về `minh` và mất `vy` cho tới khi nạp lại.

Cả hai đường đều ghi trên AWS thật (xóa và nạp lại dữ liệu của MỘT tài khoản demo), nên hỏi chủ dự án trước khi chạy (CLAUDE.md, thói quen 5). `giamkhao1` và `giamkhao2` vẫn là `minh`: cảnh 1 hiệu chỉnh trên minh (hũ Ăn uống cạn 23/11) không đổi.

## Cách bộ sinh dựng sổ cái

Mô tả đầy đủ ở đầu [generator.py](generator.py). Tóm tắt:

1. **Lương đúng cách ví thật ghi**: mỗi ngày lương một dòng `income` (`tx_type salary`) vào Tiền vào khác, rồi dòng chuyển `salary_split` (cùng `transfer_id`) trừ Tiền vào khác và cộng các hũ theo `yofina_core.wallet.split_amount` (cùng quy tắc `confirm_salary`). Số dư đầu kỳ (`opening_vnd`) là dòng chuyển một phía.
2. **Khoản trả nghĩa vụ định kỳ** (`paid_in_history`) là dòng chi gắn `obligation_id` đúng ngày đến hạn từng tháng; dự báo bỏ qua dòng này (lịch nghĩa vụ đã có), nên không đếm hai lần. Khoản biến động (tiền điện) lấy số tiền trong khoảng theo seed.
3. **Chi tiêu còn lại** `T = đầu kỳ + lương chia − số dư cần đạt − tổng khoản trả nghĩa vụ` (≥ 0, bội của 1.000). `recent_share` của `T` nằm sau ngày lương gần nhất (chi tiêu dồn về cuối kỳ), phần còn lại chia theo số ngày cho các kỳ trước.
4. **Nhịp**: trong mỗi khoảng, số khoản chi của từng ngày theo hạn ngạch tỷ lệ với trọng số (`weekend_multiplier` cho thứ bảy và chủ nhật, `early_period_multiplier` cho `early_period_days` ngày đầu kỳ lương; phần lẻ phát theo nhiễu nhỏ của seed), mỗi ngày tối đa `max_per_day` khoản; số tiền theo lognormal (`amount_sigma`), làm tròn 1.000 ₫, khoản lớn nhất nhận phần dư. Hũ Ăn uống của `minh`: 281 khoản trải trên cả 120 ngày (bản 47 ngày cũ: 110 khoản) (tối đa 5 khoản mỗi ngày), chi mỗi ngày cuối tuần cao hơn ngày thường khoảng 1,4 đến 1,6 lần tùy seed; `lan` khoảng 2,2 lần (test khẳng định trên 1,15 cho `minh`).
5. **Bất biến** (bộ sinh tự kiểm, test kiểm lại): số dư cuối từng hũ bằng đúng `target_vnd`; số dư chạy không bao giờ âm (trừ Chưa phân loại); mỗi nhóm chuyển có tổng 0; tổng gốc Trả sau không vượt hạn mức; cùng (persona, seed, ngày neo) cho cùng kết quả. Khi nạp vào DB, số dư hũ **được dựng lại từ sổ cái** (`UPDATE jars ... sum(amount_vnd)`), nên số dư luôn đúng bất biến "bằng tổng các dòng trả bằng hũ".

Số dư cần đạt (`target_vnd`), số khoản chi và mọi tham số nhịp là **đầu vào** (hiệu chỉnh persona để ra đúng tình huống demo là hợp lệ); sổ cái là đầu ra tính toán. **Mức chi trung bình mỗi hũ** = `(đầu kỳ + lương chia − target_vnd − khoản trả nghĩa vụ) / số ngày`: chỉnh bằng `opening_vnd`, `target_vnd`, `recent_share` và `expense_count` của hũ; **nhịp** chỉnh bằng khối `rhythm_defaults` (hoặc `rhythm` của một hũ). Việc hiệu chỉnh để hũ Ăn uống cạn đúng 23/11 mô phỏng đã làm ở phase 2 luồng C với engine thật (mục "Hiệu chỉnh cảnh 1" dưới): chỉ sửa các số trong `specs/minh.json`, không sửa mã. `seed_salary_events` (mặc định `false`) bật việc nạp sự kiện lương `confirmed` của các kỳ trong lịch sử; mặc định tắt để kỳ lương hiện tại ở trạng thái `expected` như bảng số Figma ("còn 14 ngày tới kỳ lương").

## Nạp vào Aurora

`LedgerService.reset_demo` (xem [gateway/tools/ledger/README.md](../../gateway/tools/ledger/README.md)) gọi `generate` + `materialize` (truyền `user_id` để id dòng là `uuid5(người dùng, persona, khóa)`: hai tài khoản cùng persona như `minh` và `giamkhao1` không đụng khóa chính toàn cục) rồi `LedgerRepo.reset_user`: MỘT transaction xóa đúng thứ tự khóa ngoại (`forecast_runs`, `salary_events`, `category_rules`, `transactions`, `obligations`, `payees`, `credit_lines`, `turn_blocks`, `conversation_turns`, `confirm_resolutions`, `jars`), nạp hũ, gọi `app_ensure_system_jars`, nạp người nhận, nghĩa vụ, hạn mức, sổ cái, rồi dựng lại số dư hũ. `audit_events` chỉ thêm, không xóa. Sau đó phát `profile.updated` để pipeline dự báo tính lại.

## Đồng hồ mô phỏng

`materialize` đặt `clock_offset_days = clock_offset_for(ngày_neo, now, múi giờ)` để ngày mô phỏng của tài khoản bằng ngày neo (21/11/2026) ngay sau khi đặt lại, rồi trôi theo thời gian thật. Mỗi dòng sổ cái có `app_date` mô phỏng và `occurred_at` thật (UTC) nhất quán với offset (ngày thật = hôm nay thật − số ngày trước). Ngày neo và múi giờ là cấu hình (`YOFINA_DEMO_ANCHOR_DATE`, `YOFINA_APP_TIMEZONE`).

## Thêm persona

Thêm `specs/<tên>.json` (theo mẫu `minh.json`), thêm tài khoản vào `accounts.json`, chạy `uv run pytest tests/unit/test_personas.py` (kiểm bất biến), rồi `uv run scripts/seed_demo.py <tài khoản>` (hoặc `scripts/seed_persona.py` khi ledger chưa được deploy lại, mục "Nạp persona mới lên AWS"). Ba persona `minh`, `lan`, `khoa` được khóa bằng băm đầu ra bộ sinh (`tests/unit/persona_digest.py`, mốc trong `tests/unit/test_persona_external.py`): sửa spec của chúng một cách có chủ đích thì chạy `PYTHONPATH="libs/yofina_core/src;data" uv run python tests/unit/persona_digest.py` rồi cập nhật mốc. Đóng gói: `uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 --extra data/personas:personas` kèm thư mục này vào Lambda ledger.
