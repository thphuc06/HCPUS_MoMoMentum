# data/personas/

Dữ liệu persona **seed** cho demo: hồ sơ, hũ và sổ cái giao dịch tất định theo seed, nạp vào Aurora khi bấm "Đặt lại dữ liệu" (`POST /demo/reset`) hoặc chạy `scripts/seed_demo.py`. Dự án không có API giao dịch thật nên seed là cách duy nhất đưa dữ liệu vào; theo master-plan ("Không hardcode, không giả lập") thì **dữ liệu này nằm ở đây, không nằm trong mã nghiệp vụ Lambda hay frontend**, và mọi con số trên màn hình vẫn đi từ Aurora qua tool.

| File | Nội dung |
|---|---|
| `specs/<persona>.json` | Dữ liệu đầu vào của một persona: lương, ngày lương, mức rủi ro, số ngày lịch sử, seed, danh sách hũ (mã, tên, khóa màu/biểu tượng, tỷ lệ chia, số dư đầu kỳ, **số dư cần đạt**, số khoản chi, cửa hàng) |
| `generator.py` | `generate(persona, anchor=...)` dựng sổ cái; `materialize(...)` ghép với đồng hồ mô phỏng ([ADR-0003](../../docs/decisions/0003-dong-ho-mo-phong.md)); `persona_from_groups`, `parse_groups_claim` |
| `accounts.json` | Ánh xạ tài khoản demo → persona và tiền tố nhóm Cognito (`persona-`). Mã sản phẩm không rẽ nhánh theo email: persona của người gọi lấy từ nhóm Cognito (claim `cognito:groups`) |

## Persona

| Persona | Dùng cho | Hồ sơ | Hũ | Lịch sử |
|---|---|---|---|---|
| `minh` | `minh`, `giamkhao1`–`3` | Lương 9.000.000 ₫ ngày 5, rủi ro vừa | 7 hũ khớp [bảng số Figma §5](../../docs/research/figma-ui-design.md): Ăn uống 380.000, Đi lại 640.000, Hóa đơn 450.000, Giải trí 760.000, Du lịch 1.800.000, Dự phòng 2.700.000, Nghĩa vụ 1.000.000 (tổng 7.730.000), tỷ lệ chia 30/7/31/7/10/10/5 | 47 ngày trước ngày neo 21/11/2026 (từ 5/10, hai kỳ lương), 72 dòng |
| `lan` | `lan` (sinh viên làm thêm) | Lương 4.500.000 ₫ ngày 5, rủi ro thấp | 5 hũ (Ăn uống, Đi lại, Hóa đơn, Giải trí, Dự phòng) | 47 ngày, 57 dòng |
| `khoa` | `khoa` (tài khoản mới, ít dữ liệu: độ tin cậy thấp) | Lương 7.000.000 ₫ ngày 5 | 5 hũ | 18 ngày, một kỳ lương, 30 dòng |

Phase 1 chưa có "Tiền vào khác" 350.000 ₫ và "Chưa phân loại" 180.000 ₫ của bảng số Figma (cần giao dịch chưa gán hũ; phase 2).

## Cách bộ sinh dựng sổ cái

1. Mỗi hũ: dòng `income` "Số dư đầu kỳ" (nếu có `opening_vnd`) + một dòng `income` "Lương" mỗi ngày lương trong lịch sử (lương × tỷ lệ chia).
2. Tổng chi `T = đầu kỳ + lương chia - số dư cần đạt` (phải ≥ 0, bội của 1.000). `recent_share` của `T` rơi vào khoảng sau ngày lương gần nhất (chi tiêu dồn về cuối kỳ: hũ Ăn uống của Minh cạn dần tới ngày 23/11); phần còn lại chia theo số ngày cho các khoảng trước.
3. Mỗi khoảng sinh vài khoản chi: ngày, giờ, cửa hàng, số tiền lấy từ `random.Random(f"{seed}:{persona}:{hũ}")`, làm tròn 1.000 ₫, khoản lớn nhất nhận phần dư để tổng khớp.
4. Bất biến (bộ sinh tự kiểm, test kiểm lại): số dư cuối từng hũ bằng đúng `target_vnd`; số dư chạy không bao giờ âm; cùng (persona, seed, ngày neo) cho cùng kết quả.

Số dư cần đạt (`target_vnd`) là **đầu vào** (hiệu chỉnh persona để ra đúng tình huống demo là hợp lệ); cả sổ cái là đầu ra tính toán. Engine dự báo của phase 2 cho số khác Figma thì dùng số của engine.

## Đồng hồ mô phỏng

`materialize` đặt `clock_offset_days = clock_offset_for(ngày_neo, now, múi giờ)` để ngày mô phỏng của tài khoản bằng ngày neo (21/11/2026) ngay sau khi đặt lại, rồi trôi theo thời gian thật. Mỗi dòng sổ cái có `app_date` mô phỏng và `occurred_at` thật (UTC) nhất quán với offset (ngày thật = hôm nay thật − số ngày trước). Ngày neo và múi giờ là cấu hình (`YOFINA_DEMO_ANCHOR_DATE`, `YOFINA_APP_TIMEZONE`).

## Thêm persona

Thêm `specs/<tên>.json` (theo mẫu), thêm tài khoản vào `accounts.json`, chạy `uv run pytest tests/unit/test_personas.py` (kiểm bất biến), rồi `uv run scripts/seed_demo.py <tài khoản>`. Test đóng gói: `uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 --extra data/personas:personas` kèm thư mục này vào Lambda ledger.
