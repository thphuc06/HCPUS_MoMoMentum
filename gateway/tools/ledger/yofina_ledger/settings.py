"""Cấu hình của Lambda ledger: toàn bộ lấy từ biến môi trường `YOFINA_*` do CDK đặt (hoặc SSM qua
`YOFINA_SSM_PREFIX`), thiếu thì báo lỗi, không có giá trị mặc định gắn với tài khoản hay môi trường."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from yofina_core.config import Config


@dataclass(frozen=True)
class LedgerSettings:
    #: hạn của đề nghị xác nhận hiển thị trong khối `confirm` (giây)
    offer_ttl_seconds: int
    #: hạn mức số tiền một lần chuyển hũ (VND), cùng giá trị với luật Cedar
    move_max_amount_vnd: int
    #: số dòng mặc định và tối đa của query_transactions
    transactions_default_limit: int
    transactions_max_limit: int
    #: múi giờ ứng dụng và ngày neo của đồng hồ mô phỏng (ADR-0003)
    app_timezone: str
    demo_anchor_date: date

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @classmethod
    def from_config(cls, cfg: Config | None = None) -> LedgerSettings:
        cfg = cfg or Config()
        default_limit = cfg.get_int("transactions_default_limit")
        max_limit = cfg.get_int("transactions_max_limit")
        if not 1 <= default_limit <= max_limit <= 50:
            raise ValueError("transactions_default_limit <= transactions_max_limit <= 50")
        return cls(
            offer_ttl_seconds=cfg.get_int("confirm_offer_ttl_seconds"),
            move_max_amount_vnd=cfg.get_int("move_max_amount_vnd"),
            transactions_default_limit=default_limit,
            transactions_max_limit=max_limit,
            app_timezone=cfg.get("app_timezone"),
            demo_anchor_date=date.fromisoformat(cfg.get("demo_anchor_date")),
        )
