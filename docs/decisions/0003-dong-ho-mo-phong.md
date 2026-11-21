# ADR-0003: Đồng hồ mô phỏng theo tài khoản

- **Trạng thái**: Đã chốt
- **Ngày**: 2026-11-21
- **Người/agent quyết định**: chủ dự án (duyệt kế hoạch tổng, [master-plan mục 2](../plan/master-plan.md#đồng-hồ-mô-phỏng-)); Claude Sonnet 5.5 viết ADR
- **Liên quan**: [demo-script](../plan/demo-script.md), [figma-ui-design.md mục 5](../research/figma-ui-design.md) (bảng số liệu thống nhất), FR1; [contracts/README.md](../../contracts/README.md)

## Bối cảnh

Bảng số liệu của thiết kế Figma và kịch bản demo giả định hôm nay là 21/11/2026: hũ Ăn uống cạn ngày 23/11, lương về ngày 5/12, khoản trả sau đến hạn 5/12. Video quay và việc chấm bài diễn ra khoảng 9–11/12, khi ngày thật đã khác. Giám khảo có thể mở app bất cứ lúc nào và cảnh 1 vẫn phải ra đúng con số. Dự án không có API giao dịch thật; mọi dữ liệu persona được seed.

## Các lựa chọn đã cân nhắc

1. **Dùng ngày thật, seed dữ liệu tương đối theo hôm nay** — số liệu (ngày cạn, ngày lương) trôi theo ngày thật, không khớp Figma, kịch bản và video; mỗi lần demo phải kiểm lại.
2. **Một ngày giả toàn cục (tham số SSM)** — mọi người dùng chung một ngày; giám khảo đặt lại hay thay ngày thì ảnh hưởng người khác; ngày đứng yên nên cảm giác như ảnh chụp.
3. **Đồng hồ theo tài khoản: `users.clock_offset_days`** — mỗi tài khoản có độ lệch riêng; đặt lại thì quay về ngày neo rồi trôi theo thời gian thật.

## Quyết định

Chọn lựa chọn 3.

- Cột `users.clock_offset_days` (số nguyên, mặc định 0). **Ngày mô phỏng = ngày hiện tại theo múi giờ ứng dụng (Asia/Ho_Chi_Minh, là cấu hình) + offset.**
- **Mọi nơi cần "hôm nay" đi qua một hàm duy nhất**: `yofina_core.clock.app_today(clock_offset_days, now, tz)`. Thuần hàm: `now` truyền vào và phải có múi giờ, nên test tất định. Tool, pipeline, engine và REST không tự gọi `date.today()` hay `now()` để lấy ngày nghiệp vụ.
- **"Đặt lại dữ liệu"** (`POST /demo/reset`): xóa dữ liệu của chính người gọi, sinh lại persona tất định theo seed, rồi đặt `clock_offset_days = clock_offset_for(ngày_neo, now)` để ngày mô phỏng quay về **ngày neo** (21/11/2026). Ngày neo là cấu hình, không gắn trong thư viện. Sau đó ngày mô phỏng trôi theo thời gian thật (24 giờ sau là 22/11), nên các sự kiện theo ngày (cạn hũ, lương, đến hạn) tự xảy ra.
- **Hiển thị**: giao diện ghi rõ "Ví mô phỏng · ngày mô phỏng ..." (không dùng nhãn khiến người xem tưởng là ngày thật). Khối UI mang `source.app_date`; mốc thời gian thật (`as_of`, `occurred_at`) vẫn là giờ thật UTC.
- Dòng sổ cái lưu cả `occurred_at` (giờ thật) lẫn `app_date` (ngày mô phỏng lúc ghi).

## Hệ quả

- Dễ hơn: cảnh 1 dựng lại được với đúng số vào bất cứ ngày nào; mỗi giám khảo có tài khoản và đồng hồ riêng; engine dự báo và test chạy với `now` truyền vào, không cần đóng băng đồng hồ hệ thống.
- Khó hơn: kỷ luật "mọi ngày nghiệp vụ qua `app_today`" phải giữ ở mọi tool, pipeline và truy vấn SQL (không dùng `current_date`/`now()` của PostgreSQL cho nghiệp vụ); pipeline đêm (02:00) chạy theo ngày mô phỏng của từng người dùng chứ không theo ngày chung; giao diện phải luôn nhắc đây là mô phỏng.
- Phải làm: lấy ngày neo và múi giờ từ cấu hình (`yofina_core.config`); phase 2 trở đi mỗi tool mới đọc `clock_offset_days` qua `app_get_user`; thêm kiểm tra (test hoặc lint) cấm `date.today()`/`datetime.now()` trong mã nghiệp vụ.
- Hạn chế: persona tất định nên mọi tài khoản đặt lại cho cùng một trạng thái ở ngày neo; ngày mô phỏng không thể lùi trước ngày dữ liệu seed.

## Nguồn đã tra

- [figma-ui-design.md mục 5](../research/figma-ui-design.md) — bảng số liệu giả định ngày 21/11/2026.
- [master-plan mục 2](../plan/master-plan.md) — quyết định của người điều phối, chủ dự án duyệt khi duyệt kế hoạch.
