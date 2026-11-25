"""Bảng tra dùng chung (loại giao dịch, biểu phí, hũ mẫu): đọc từ Aurora, giữ trong bộ nhớ vài phút.

Đây là dữ liệu sản phẩm (db/seed/*.sql), không phải dữ liệu người dùng: không RLS, không `user_id`. Nằm trong DB để đổi
biểu phí hay thêm loại giao dịch mà không sửa mã (master-plan: "giá trị cấu hình nằm trong cấu hình, SSM hoặc bảng DB").
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from yofina_core.money import to_vnd
from yofina_core.params import TxTypeInfo
from yofina_core.wallet import BNPL_MONTHLY_FEE_TYPE, BNPL_PRODUCT_CODE


class ReferenceSource(Protocol):
    def reference_tx_types(self) -> list[dict[str, Any]]: ...
    def reference_fees(self) -> list[dict[str, Any]]: ...
    def reference_templates(self) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class FeeRow:
    id: str
    product_code: str
    product_label: str
    fee_type: str
    amount_vnd: int | None
    rate_percent: Decimal | None
    period: str
    condition_code: str
    condition_note: str | None
    source_name: str
    source_url: str
    effective_from: date
    effective_to: date | None

    def active_on(self, day: date) -> bool:
        return self.effective_from <= day and (
            self.effective_to is None or day <= self.effective_to
        )


@dataclass(frozen=True)
class TemplateRow:
    code: str
    name: str
    color_key: str
    icon_key: str
    kind: str
    default_split_percent: Decimal
    is_default: bool
    sort_order: int
    purpose: str | None = None


class ReferenceData:
    """Cache theo thời gian (`ttl_seconds`); đọc lại khi hết hạn. Không giữ trạng thái người dùng."""

    def __init__(
        self,
        source: ReferenceSource,
        ttl_seconds: float,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source = source
        self._ttl = ttl_seconds
        self._mono = monotonic
        self._loaded_at: dict[str, float] = {}
        self._cache: dict[str, Any] = {}

    def _get(self, key: str, load: Callable[[], Any]) -> Any:
        now = self._mono()
        if key not in self._cache or now - self._loaded_at[key] > self._ttl:
            self._cache[key] = load()
            self._loaded_at[key] = now
        return self._cache[key]

    def tx_types(self) -> dict[str, TxTypeInfo]:
        def load() -> dict[str, TxTypeInfo]:
            return {
                r["tx_type"]: TxTypeInfo(
                    tx_type=r["tx_type"],
                    direction=r["direction"],
                    default_jar_code=r["default_jar_code"],
                    system_role=r["system_role"],
                    label=r["label"],
                    is_selectable=bool(r["is_selectable"]),
                    is_person_transfer=bool(r.get("is_person_transfer", False)),
                )
                for r in self._source.reference_tx_types()
            }

        return self._get("tx_types", load)

    def fees(self) -> list[FeeRow]:
        def load() -> list[FeeRow]:
            return [
                FeeRow(
                    id=str(r["id"]),
                    product_code=r["product_code"],
                    product_label=r["product_label"],
                    fee_type=r["fee_type"],
                    amount_vnd=to_vnd(r["amount_vnd"]) if r["amount_vnd"] is not None else None,
                    rate_percent=r["rate_percent"],
                    period=r["period"],
                    condition_code=r["condition_code"],
                    condition_note=r["condition_note"],
                    source_name=r["source_name"],
                    source_url=r["source_url"],
                    effective_from=r["effective_from"],
                    effective_to=r["effective_to"],
                )
                for r in self._source.reference_fees()
            ]

        return self._get("fees", load)

    def templates(self) -> list[TemplateRow]:
        def load() -> list[TemplateRow]:
            return [
                TemplateRow(
                    code=r["code"],
                    name=r["name"],
                    color_key=r["color_key"],
                    icon_key=r["icon_key"],
                    kind=r["kind"],
                    default_split_percent=Decimal(str(r["default_split_percent"])),
                    is_default=bool(r["is_default"]),
                    sort_order=int(r["sort_order"]),
                    purpose=r.get("purpose"),
                )
                for r in self._source.reference_templates()
            ]

        return self._get("templates", load)

    def active_fees(self, product_code: str, today: date) -> list[FeeRow]:
        """Dòng phí đang hiệu lực tại `today`; cùng loại phí thì dòng có `effective_from` MUỘN nhất đứng trước (bản mới
        thay bản cũ chưa kết thúc)."""
        rows = [f for f in self.fees() if f.product_code == product_code and f.active_on(today)]
        return sorted(rows, key=lambda f: f.effective_from, reverse=True)

    def bnpl_monthly_fee(self, today: date) -> FeeRow | None:
        """Phí dịch vụ hằng tháng của Trả sau (mô phỏng) đang hiệu lực, lấy từ bảng `fee_schedules` (không gắn cứng
        số tiền trong mã). Hiện chỉ phí cố định (`amount_vnd`) được áp dụng; phí theo tỷ lệ chưa có nguồn."""
        for f in self.active_fees(BNPL_PRODUCT_CODE, today):
            if f.fee_type == BNPL_MONTHLY_FEE_TYPE and f.amount_vnd is not None:
                return f
        return None

    def product_label(self, product_code: str, today: date) -> str:
        """Tên hiển thị của sản phẩm tín dụng từ biểu phí (mới hiệu lực nhất)."""
        rows = sorted(
            (f for f in self.fees() if f.product_code == product_code),
            key=lambda f: f.effective_from,
            reverse=True,
        )
        active = [f for f in rows if f.active_on(today)] or rows
        return active[0].product_label if active else product_code
