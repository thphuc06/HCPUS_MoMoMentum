"""`knowledge___resolve_date`: tính một ngày dương lịch từ đặc tả có cấu trúc (issue #39).

Cùng hàm thuần mà mã của agent dùng trong tiến trình (`yofina_core.dates.resolve_date`): mốc, độ lệch, lùi một ngày; bảng Mùng 1 Tết
là dữ liệu tra của `yofina_core`. Tham số của tool là các trường của `DateSpec` (`yofina_core.dates.SPEC_FIELDS`); hôm nay (ngày mô
phỏng, `app_today`) và ngày lương lấy phía server theo người gọi, tool KHÔNG nhận `today` từ model. Không gọi model, không ghi DB.

Kết quả theo `contracts/tools/knowledge.results.schema.json` (`ResolvedDateData`). Lỗi: `PARAMS_INVALID` (đặc tả sai, có `field`),
`PROFILE_INCOMPLETE` (mốc ngày lương khi chưa khai), `LUNAR_YEAR_UNSUPPORTED` (năm Tết ngoài bảng), `DATE_IN_PAST` (ngày tính ra
trước hôm nay, không tự dời).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from yofina_core.dates import SPEC_FIELDS, DateSpec, parse_spec, resolve_date

#: tham số của tool (trừ `user_id`), cũng là khóa `_ARG_KEYS` của Lambda ledger
TOOL_ARGS = SPEC_FIELDS


def date_spec(args: Mapping[str, Any]) -> DateSpec:
    """Đặc tả từ tham số của tool; sai thì PARAMS_INVALID ngay, trước khi đọc hồ sơ của người gọi."""
    return parse_spec(args)


def resolve_date_data(spec: DateSpec, today: date, payday_day: int | None) -> dict[str, Any]:
    """`ResolvedDateData` của đặc tả; `today` là ngày mô phỏng của người gọi, `payday_day` là ngày lương đã khai (hoặc None)."""
    return resolve_date(spec, today, payday_day=payday_day).to_wire()
