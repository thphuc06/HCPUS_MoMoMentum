# gateway/tools/knowledge/

Tool `knowledge___*` (target `knowledge`): `get_fee_schedule` (biểu phí có cấu trúc kèm tên nguồn, đường dẫn và ngày hiệu lực, `yofina_knowledge/fees.py`), `get_exchange_rate` (tỷ giá bán ngoại tệ theo ngày và số VND quy đổi, `yofina_knowledge/fx_rates.py`; cùng hàm và cùng nguồn Vietcombank với pipeline nạp chứng từ: `yofina_core.fx`), `resolve_date` (tính một ngày dương lịch từ đặc tả có cấu trúc, `yofina_knowledge/dates.py`; cùng hàm thuần `yofina_core.dates.resolve_date` mà mã của agent dùng trong tiến trình, issue #39). Ba tool chạy trong Lambda `yofina-ledger` (`yofina_ledger/phase3.py`, `gateway_api.py`). Không có tool `search`: RAG (Bedrock Knowledge Bases) đã cắt ngày 24/11 vì mọi con số lấy từ bảng có cấu trúc và không cảnh demo nào cần tìm tài liệu ([phase 5](../../../docs/plan/phases/phase-5-nap-du-lieu-ho-so-trace.md), [ADR-0004](../../../docs/decisions/0004-lech-so-voi-proposal.md)); trích dẫn phí dựng từ nguồn của chính bảng biểu phí (`agent/src/yofina_agent/fee_citation.py`). Proposal §9 (RAG).

## `resolve_date`

Model hiểu cách nói thời gian và điền đặc tả; phép tính lịch do hàm tất định làm. Tham số là các trường của `yofina_core.dates.DateSpec` (hợp đồng: `contracts/tools/knowledge.json`, kết quả `ResolveDateResult` trong `knowledge.results.schema.json`):

| Trường | Nghĩa |
|---|---|
| `anchor` (bắt buộc) | `today`, `next_payday` (ngày lương kế sau hôm nay), `start_of` / `end_of` (cần `period`), `lunar_new_year` (Mùng 1 Tết), `date` (cần `day`) |
| `period`, `period_offset` | Kỳ `week` (thứ Hai tới Chủ nhật), `month`, `quarter`, `year`; số kỳ tính từ kỳ chứa hôm nay (0 kỳ này, 1 kỳ sau). Với `date`: `month` hoặc `year` chọn tháng hay năm tương đối; với `lunar_new_year`: `year` |
| `lunar_year` | Năm dương lịch chứa Mùng 1 Tết; vắng thì Tết gần nhất sau hôm nay |
| `day`, `month`, `year` | Ngày cụ thể của `date`; thiếu năm (hoặc thiếu tháng) thì lần gần nhất sau hôm nay |
| `offset` | `{years, months, weeks, days}`, có thể âm hoặc lẻ (tối đa 4 chữ số lẻ). Năm là 12 tháng, phần lẻ của tổng số tháng tính 30 ngày mỗi tháng, tuần là 7 ngày, số ngày làm tròn tới ngày. Cộng tháng trước (giữ ngày, vượt cuối tháng thì ngày cuối tháng), ngày sau |
| `before` | Hạn là ngày liền trước ngày tính được |

Hôm nay (ngày mô phỏng, ADR-0003) và ngày lương lấy phía server từ hồ sơ của người gọi (một lần đọc `app_get_user`); tool không nhận `today` từ model. Kết quả: `date` kèm trường giải thích (`anchor_date`, `period`, `payday_day`, `lunar_new_year {year, date, name}`, `offset {months, days}` đã quy đổi, `next_occurrence`, `month_end_clamped`, `weekday`, `days_from_today`). Lỗi: `PARAMS_INVALID` (có `field`), `PROFILE_INCOMPLETE` (mốc ngày lương khi chưa khai), `LUNAR_YEAR_UNSUPPORTED` (năm Tết ngoài bảng 2026–2035), `DATE_IN_PAST` (ngày tính ra trước hôm nay; không tự dời, agent hỏi lại). Chỉ đọc. Bảng Tết và nguồn: [libs/yofina_core](../../../libs/yofina_core/README.md) (`lunar_new_year.json`).
