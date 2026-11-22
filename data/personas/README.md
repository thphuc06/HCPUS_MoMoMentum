# data/personas/

Dữ liệu persona **seed** cho demo: hồ sơ, hũ (kể cả hai hũ hệ thống), người nhận, nghĩa vụ, hạn mức Trả sau và sổ cái giao dịch tất định theo seed, nạp vào Aurora khi bấm "Đặt lại dữ liệu" (`POST /demo/reset`) hoặc chạy `scripts/seed_demo.py`. Dự án không có API giao dịch thật nên seed là cách duy nhất đưa dữ liệu vào; theo master-plan ("Không hardcode, không giả lập") thì **dữ liệu này nằm ở đây, không nằm trong mã nghiệp vụ Lambda hay frontend**, và mọi con số trên màn hình vẫn đi từ Aurora qua tool.

| File | Nội dung |
|---|---|
| `specs/<persona>.json` | Dữ liệu đầu vào của một persona: lương, ngày lương, mức rủi ro, số ngày lịch sử, seed, **nhịp chi tiêu** (`rhythm_defaults`, `rhythm` của từng hũ), danh sách hũ (mã, tên, loại, khóa màu/biểu tượng, tỷ lệ chia, số dư đầu kỳ, **số dư cần đạt**, số khoản chi, cửa hàng kèm `tx_type`, mục tiêu), `payees`, `obligations`, `credit_line`, `bnpl.purchases`, `system_jars` |
| `generator.py` | `generate(persona, anchor=...)` dựng sổ cái; `materialize(...)` ghép với đồng hồ mô phỏng ([ADR-0003](../../docs/decisions/0003-dong-ho-mo-phong.md)) và dựng id tất định; `persona_from_groups`, `parse_groups_claim` |
| `accounts.json` | Ánh xạ tài khoản demo → persona và tiền tố nhóm Cognito (`persona-`). Mã sản phẩm không rẽ nhánh theo email: persona của người gọi lấy từ nhóm Cognito (claim `cognito:groups`) |

## Persona

| Persona | Dùng cho | Hồ sơ | Hũ | Lịch sử |
|---|---|---|---|---|
| `minh` | `minh`, `giamkhao1`–`3` | Lương 9.000.000 ₫ ngày 5, rủi ro vừa | 7 hũ khớp [bảng số Figma §5](../../docs/research/figma-ui-design.md): Ăn uống 380.000, Đi lại 640.000, Hóa đơn 450.000, Giải trí 760.000, Du lịch 1.800.000 (mục tiêu 6.000.000 ₫ đến 1/4/2027), Dự phòng 2.700.000, Nghĩa vụ 1.000.000 (tổng 7.730.000), tỷ lệ chia 30/7/31/7/10/10/5. Hai hũ hệ thống: **Tiền vào khác +350.000** (Huy trả lại tiền ăn) và **Chưa phân loại −180.000** (hai khoản CHI chưa xếp hũ: QR 120.000 và chuyển tiền 60.000). Tổng số dư 7.900.000 ₫ (Figma ghi 8.260.000 vì coi Chưa phân loại là +180.000; hợp đồng cho số dư có dấu, xem quyết định số 2 của phase 2) | 47 ngày trước ngày neo 21/11/2026 (từ 5/10, hai kỳ lương), 166 dòng |
| `lan` | `lan` (sinh viên làm thêm) | Lương 4.500.000 ₫ ngày 5, rủi ro thấp | 5 hũ (Ăn uống, Đi lại, Hóa đơn, Giải trí, Dự phòng); hạn mức Trả sau 2.000.000 ₫, không có khoản trả sau sẵn | 47 ngày, 106 dòng |
| `khoa` | `khoa` (tài khoản mới, ít dữ liệu: độ tin cậy thấp) | Lương 7.000.000 ₫ ngày 5 | 5 hũ; tiền thuê phòng 1.400.000 ₫ đến hạn ngày 1 (chưa trả trong 18 ngày lịch sử) | 18 ngày, một kỳ lương, 46 dòng |

**Nghĩa vụ của `minh`** (ngày đến hạn kế tiếp tính từ ngày neo): Tiền điện 375.000 ₫ (khoảng 300.000 đến 450.000, ngày 26, hũ Hóa đơn), Trả sau (mô phỏng) **1.000.000 ₫ = gốc 967.000 + phí 33.000** đến hạn 5/12 trả từ hũ Nghĩa vụ (phí lấy từ bảng `fee_schedules` lúc nạp, không gắn cứng), Tiền thuê phòng 2.000.000 ₫ (ngày 6), Internet FPT 220.000 ₫ (ngày 12), Netflix 180.000 ₫ (ngày 15, hũ Giải trí), Cước điện thoại 100.000 ₫ (ngày 20). Tiền cơm văn phòng 300.000 ₫ (ngày 23, trả từ hũ Ăn uống; thêm ở đợt hiệu chỉnh cảnh 1, xem dưới). Hạn mức Trả sau 5.000.000 ₫, dư nợ gốc 967.000 ₫ (hai giao dịch mua bằng hạn mức trong lịch sử: 520.000 và 447.000). Người nhận: Trần Quang Huy (yêu thích, người nhận của cảnh chuyển tiền demo), Nguyễn Thu Hà, Mẹ, Lê Minh Châu. Hóa đơn tháng 11 chưa tới hạn tiền điện nên hũ Hóa đơn (450.000) "sát" như Figma.

## Hiệu chỉnh cảnh 1 (phase 2, luồng C)

Mục tiêu: sau `POST /demo/reset`, **engine thật** (`yofina_ml`, 10.000 đường, đọc từ Aurora qua pipeline) báo hũ Ăn uống cạn ngày 23/11/2026 mô phỏng (hôm nay 21/11, lương 5/12: "còn 12 ngày nữa mới tới kỳ lương"), số dư bảy hũ giữ đúng bảng Figma, dữ liệu vẫn tự nhiên. Chỉ sửa **đầu vào** trong `specs/minh.json`; không số đầu ra nào nằm trong mã sản phẩm.

Quét tham số trên PostgreSQL cục bộ với pipeline thật cho thấy: chỉ thay nhịp và mức chi của hũ Ăn uống KHÔNG đủ. Mô hình hurdle theo lịch (cửa sổ 180 ngày, nửa đời 180 ngày) dự báo gần bằng mức chi trung bình của cả 47 ngày (khoảng 100.000 ₫ mỗi ngày với số dư đầu 0 và lương chia 2,7 triệu), nên với 380.000 ₫ hũ chỉ cạn quanh 26/11. Để cạn ngày 23/11 chỉ bằng nhịp chi phải đẩy mức chi lên khoảng 200.000 ₫ mỗi ngày (cần số dư đầu kỳ trên 4 triệu ₫ cho một hũ ăn uống): không tự nhiên. Cách tự nhiên là thêm một **khoản nợ nhỏ có lịch**, đúng tinh thần "tính cả nợ nhỏ" của đề bài:

| Số đã chỉnh | Giá trị | Ý nghĩa |
|---|---|---|
| Nghĩa vụ mới `Tiền cơm văn phòng` | 300.000 ₫, ngày 23 hằng tháng, trả từ hũ Ăn uống, đã trả đủ trong lịch sử (23/10) | suất cơm trưa văn phòng trả theo tháng; đến hạn 23/11, đúng lúc số dư dự báo của hũ chỉ còn khoảng 190.000 ₫ |
| Hũ Ăn uống: `expense_count` 70 -> 110, `rhythm` {`weekend_multiplier` 2,6; `max_per_day` 5; `amount_sigma` 0,45}, `recent_share` 0,5 -> 0,58 | | nhiều khoản nhỏ hơn mỗi ngày (ăn sáng, cà phê, ăn trưa, đặt đồ), cuối tuần chi nhiều hơn rõ, chi dồn về cuối kỳ như spec ghi; `target_vnd` vẫn 380.000 ₫ và mọi hũ khác không đổi |

Kết quả đã đo (engine thật, ngày mô phỏng 21/11/2026): hũ Ăn uống số dư P50 ngày 22/11 khoảng 275.000 đến 310.000 ₫ (còn dương), ngày 23/11 khoảng -75.000 đến -105.000 ₫ nên **ngày cạn 23/11** ổn định qua tám seed khác nhau (không phải một ca may mắn) và qua nhiều lần đặt lại (hạt tất định theo người dùng); hũ Hóa đơn "sát" (xác suất hụt khoảng 0,2 đến 0,35 vì tiền điện 26/11), Đi lại, Giải trí, Du lịch, Dự phòng, Nghĩa vụ "đủ". Số liệu chi tiết và so với Figma ở [phase-2-vi-va-du-bao.md](../../docs/plan/phases/phase-2-vi-va-du-bao.md#kết-quả-thực-hiện). Hệ quả khác: tổng chi Ăn uống trong lịch sử giảm từ 5.020.000 xuống 4.720.000 ₫ (300.000 ₫ nay là khoản trả nghĩa vụ ngày 23/10, không tính vào chi tiêu), `minh` có 7 nghĩa vụ và 166 dòng sổ cái (trước đó 6 và 125).

## Cách bộ sinh dựng sổ cái

Mô tả đầy đủ ở đầu [generator.py](generator.py). Tóm tắt:

1. **Lương đúng cách ví thật ghi**: mỗi ngày lương một dòng `income` (`tx_type salary`) vào Tiền vào khác, rồi dòng chuyển `salary_split` (cùng `transfer_id`) trừ Tiền vào khác và cộng các hũ theo `yofina_core.wallet.split_amount` (cùng quy tắc `confirm_salary`). Số dư đầu kỳ (`opening_vnd`) là dòng chuyển một phía.
2. **Khoản trả nghĩa vụ định kỳ** (`paid_in_history`) là dòng chi gắn `obligation_id` đúng ngày đến hạn từng tháng; dự báo bỏ qua dòng này (lịch nghĩa vụ đã có), nên không đếm hai lần. Khoản biến động (tiền điện) lấy số tiền trong khoảng theo seed.
3. **Chi tiêu còn lại** `T = đầu kỳ + lương chia − số dư cần đạt − tổng khoản trả nghĩa vụ` (≥ 0, bội của 1.000). `recent_share` của `T` nằm sau ngày lương gần nhất (chi tiêu dồn về cuối kỳ), phần còn lại chia theo số ngày cho các kỳ trước.
4. **Nhịp**: trong mỗi khoảng, số khoản chi của từng ngày theo hạn ngạch tỷ lệ với trọng số (`weekend_multiplier` cho thứ bảy và chủ nhật, `early_period_multiplier` cho `early_period_days` ngày đầu kỳ lương; phần lẻ phát theo nhiễu nhỏ của seed), mỗi ngày tối đa `max_per_day` khoản; số tiền theo lognormal (`amount_sigma`), làm tròn 1.000 ₫, khoản lớn nhất nhận phần dư. Hũ Ăn uống của `minh`: 110 khoản trải trên cả 47 ngày (tối đa 5 khoản mỗi ngày), chi mỗi ngày cuối tuần cao hơn ngày thường khoảng 1,4 đến 1,6 lần tùy seed; `lan` khoảng 2,2 lần (test khẳng định trên 1,15 cho `minh`).
5. **Bất biến** (bộ sinh tự kiểm, test kiểm lại): số dư cuối từng hũ bằng đúng `target_vnd`; số dư chạy không bao giờ âm (trừ Chưa phân loại); mỗi nhóm chuyển có tổng 0; tổng gốc Trả sau không vượt hạn mức; cùng (persona, seed, ngày neo) cho cùng kết quả. Khi nạp vào DB, số dư hũ **được dựng lại từ sổ cái** (`UPDATE jars ... sum(amount_vnd)`), nên số dư luôn đúng bất biến "bằng tổng các dòng trả bằng hũ".

Số dư cần đạt (`target_vnd`), số khoản chi và mọi tham số nhịp là **đầu vào** (hiệu chỉnh persona để ra đúng tình huống demo là hợp lệ); sổ cái là đầu ra tính toán. **Mức chi trung bình mỗi hũ** = `(đầu kỳ + lương chia − target_vnd − khoản trả nghĩa vụ) / số ngày`: chỉnh bằng `opening_vnd`, `target_vnd`, `recent_share` và `expense_count` của hũ; **nhịp** chỉnh bằng khối `rhythm_defaults` (hoặc `rhythm` của một hũ). Việc hiệu chỉnh để hũ Ăn uống cạn đúng 23/11 mô phỏng đã làm ở phase 2 luồng C với engine thật (mục "Hiệu chỉnh cảnh 1" dưới): chỉ sửa các số trong `specs/minh.json`, không sửa mã. `seed_salary_events` (mặc định `false`) bật việc nạp sự kiện lương `confirmed` của các kỳ trong lịch sử; mặc định tắt để kỳ lương hiện tại ở trạng thái `expected` như bảng số Figma ("còn 14 ngày tới kỳ lương").

## Nạp vào Aurora

`LedgerService.reset_demo` (xem [gateway/tools/ledger/README.md](../../gateway/tools/ledger/README.md)) gọi `generate` + `materialize` (truyền `user_id` để id dòng là `uuid5(người dùng, persona, khóa)`: hai tài khoản cùng persona như `minh` và `giamkhao1` không đụng khóa chính toàn cục) rồi `LedgerRepo.reset_user`: MỘT transaction xóa đúng thứ tự khóa ngoại (`forecast_runs`, `salary_events`, `category_rules`, `transactions`, `obligations`, `payees`, `credit_lines`, `turn_blocks`, `conversation_turns`, `confirm_resolutions`, `jars`), nạp hũ, gọi `app_ensure_system_jars`, nạp người nhận, nghĩa vụ, hạn mức, sổ cái, rồi dựng lại số dư hũ. `audit_events` chỉ thêm, không xóa. Sau đó phát `profile.updated` để pipeline dự báo tính lại.

## Đồng hồ mô phỏng

`materialize` đặt `clock_offset_days = clock_offset_for(ngày_neo, now, múi giờ)` để ngày mô phỏng của tài khoản bằng ngày neo (21/11/2026) ngay sau khi đặt lại, rồi trôi theo thời gian thật. Mỗi dòng sổ cái có `app_date` mô phỏng và `occurred_at` thật (UTC) nhất quán với offset (ngày thật = hôm nay thật − số ngày trước). Ngày neo và múi giờ là cấu hình (`YOFINA_DEMO_ANCHOR_DATE`, `YOFINA_APP_TIMEZONE`).

## Thêm persona

Thêm `specs/<tên>.json` (theo mẫu `minh.json`), thêm tài khoản vào `accounts.json`, chạy `uv run pytest tests/unit/test_personas.py` (kiểm bất biến), rồi `uv run scripts/seed_demo.py <tài khoản>`. Đóng gói: `uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 --extra data/personas:personas` kèm thư mục này vào Lambda ledger.
