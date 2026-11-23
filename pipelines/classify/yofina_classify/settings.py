"""Cấu hình hạ tầng của Lambda phân loại: biến `YOFINA_*` do CDK đặt (thiếu thì `ConfigError`, không có giá trị mặc định gắn với môi trường).

Ngưỡng nghiệp vụ KHÔNG ở đây mà ở `yofina_ledger.classify_config` (`classify_defaults.json`, ghi đè `YOFINA_CLASSIFY_<TÊN>`).
"""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from yofina_core.config import Config


@dataclass(frozen=True)
class ClassifySettings:
    app_timezone: str
    event_bus_name: str
    idempotency_table: str
    idempotency_ttl_seconds: int
    #: một sự kiện đang xử lý giữ khóa thuê từng này giây; quá hạn thì lần giao lại được giành khóa
    idempotency_lease_seconds: int
    #: số lần SQS giao tối đa trước khi vào DLQ (cùng giá trị với hàng đợi); lần cuối thì suy giảm thay vì thử lại
    max_receive_count: int
    reference_cache_seconds: int

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @classmethod
    def from_config(cls, cfg: Config | None = None) -> ClassifySettings:
        cfg = cfg or Config()
        return cls(
            app_timezone=cfg.get("app_timezone"),
            event_bus_name=cfg.get("event_bus_name", default=""),
            idempotency_table=cfg.get("classify_idempotency_table"),
            idempotency_ttl_seconds=cfg.get_int("classify_idempotency_ttl_seconds"),
            idempotency_lease_seconds=cfg.get_int("classify_idempotency_lease_seconds"),
            max_receive_count=cfg.get_int("classify_max_receive_count"),
            reference_cache_seconds=cfg.get_int("reference_cache_seconds", default=300),
        )
