"""`knowledge___get_fee_schedule`: biểu phí CÓ CẤU TRÚC của sản phẩm Trả sau (mô phỏng), đọc từ bảng `fee_schedules`
(qua `ReferenceData` của ledger), kèm nguồn và ngày hiệu lực. Số để tính phí đi từ đây, không đi qua RAG.

Kết quả theo `contracts/tools/knowledge.results.schema.json` (`FeeScheduleData`): `FeeLine` cùng hình dạng với OpenAPI `GET /credit-line`.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.wallet import BNPL_PRODUCT_CODE

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


def fee_line(f: Any) -> dict[str, Any]:
    """Một dòng `FeeRow` -> `FeeLine` JSON (trường vắng bị bỏ)."""
    item: dict[str, Any] = {
        "fee_type": f.fee_type,
        "period": f.period,
        "condition_code": f.condition_code,
        "source_name": f.source_name,
        "source_url": f.source_url,
        "effective_from": f.effective_from.isoformat(),
    }
    if f.amount_vnd is not None:
        item["amount_vnd"] = f.amount_vnd
    if f.rate_percent is not None:
        item["rate_percent"] = float(f.rate_percent)
    if f.condition_note:
        item["condition_note"] = f.condition_note
    return item


def fee_schedule_data(
    ref: Any, today: date, *, product: Any = None, fee_type: Any = None
) -> dict[str, Any]:
    """`FeeScheduleData` của sản phẩm tại ngày mô phỏng `today`. Sản phẩm hoặc loại phí không có thì FEE_SCHEDULE_NOT_FOUND."""
    code = BNPL_PRODUCT_CODE if product in (None, "") else product
    if not isinstance(code, str) or not _CODE_RE.fullmatch(code):
        raise YofinaError(ErrorCode.PARAMS_INVALID, "Mã sản phẩm không hợp lệ.")
    if fee_type not in (None, "") and (
        not isinstance(fee_type, str) or not _CODE_RE.fullmatch(fee_type)
    ):
        raise YofinaError(ErrorCode.PARAMS_INVALID, "Loại phí không hợp lệ.")
    rows = ref.active_fees(code, today)
    if fee_type not in (None, ""):
        rows = [r for r in rows if r.fee_type == fee_type]
    if not rows:
        raise YofinaError(
            ErrorCode.FEE_SCHEDULE_NOT_FOUND,
            "Không có biểu phí đang hiệu lực cho sản phẩm hoặc loại phí này.",
        )
    # cùng loại phí chỉ giữ dòng hiệu lực muộn nhất (`active_fees` đã sắp mới trước)
    seen: set[str] = set()
    fees = []
    for r in rows:
        if r.fee_type in seen:
            continue
        seen.add(r.fee_type)
        fees.append(fee_line(r))
    return {
        "product_code": code,
        "product_label": ref.product_label(code, today)[:60],
        "fees": fees[:20],
    }
