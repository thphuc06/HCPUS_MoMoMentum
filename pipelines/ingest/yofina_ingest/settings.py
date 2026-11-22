"""Cấu hình chạy của hai Lambda nạp dữ liệu: biến `YOFINA_*` do CDK đặt (hoặc SSM qua `YOFINA_SSM_PREFIX`); thiếu thì báo lỗi.

Giới hạn và ngưỡng nghiệp vụ nằm ở `yofina_core.ingest.IngestSettings` (một nơi duy nhất). Ở đây chỉ có tên tài nguyên và tham số hạ tầng.
"""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from yofina_core.config import Config
from yofina_core.ingest import IngestSettings


@dataclass(frozen=True)
class IngestRuntime:
    settings: IngestSettings
    bucket: str
    #: tiền tố khóa S3 của tệp người dùng; khóa đầy đủ là `{upload_prefix}{user_id}/{job_id}`
    upload_prefix: str
    app_timezone: str
    #: cùng giá trị với `forecast_history_window_days` của dự báo (cửa sổ độ phủ dữ liệu)
    forecast_history_window_days: int
    #: tên Lambda `yofina-forecast-batch`; rỗng thì không kích hoạt tính lại dự báo
    forecast_function_name: str
    #: số lần SQS giao tối đa trước khi vào DLQ (cùng giá trị với hàng đợi); lần cuối thì job được đánh dấu `failed`
    max_receive_count: int
    #: hạn của đề nghị xác nhận hiển thị trong khối `confirm_action` (giây)
    offer_ttl_seconds: int
    forecast_sync_timeout_seconds: float = 8.0

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)

    @classmethod
    def from_config(cls, cfg: Config | None = None) -> IngestRuntime:
        cfg = cfg or Config()
        prefix = cfg.get("ingest_upload_prefix", default="u/")
        if not prefix.endswith("/"):
            raise ValueError("ingest_upload_prefix phải kết thúc bằng /")
        return cls(
            settings=IngestSettings.from_config(cfg),
            bucket=cfg.get("ingest_bucket"),
            upload_prefix=prefix,
            app_timezone=cfg.get("app_timezone"),
            forecast_history_window_days=cfg.get_int("forecast_history_window_days", default=330),
            forecast_function_name=cfg.get("forecast_function_name", default=""),
            max_receive_count=cfg.get_int("ingest_max_receive_count", default=3),
            offer_ttl_seconds=cfg.get_int("confirm_offer_ttl_seconds", default=600),
        )
