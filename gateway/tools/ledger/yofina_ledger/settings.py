"""Cấu hình của Lambda ledger: toàn bộ lấy từ biến môi trường `YOFINA_*` do CDK đặt (hoặc SSM qua
`YOFINA_SSM_PREFIX`), thiếu thì báo lỗi, không có giá trị mặc định gắn với tài khoản hay môi trường.

Ngưỡng, hạn mức và thời hạn của nghiệp vụ đều đi qua đây (master-plan: "không hardcode"); biểu phí không nằm ở đây mà ở
bảng `fee_schedules`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
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
    #: hạn mức số tiền một giao dịch ghi bằng `record_transaction` (VND), cùng giá trị với luật Cedar
    transaction_max_amount_vnd: int = 0
    #: số nhận lệch lương đã khai quá ngưỡng này (phần trăm, tuyệt đối) thì hỏi có cập nhật lương không
    salary_deviation_ask_percent: Decimal = Decimal(0)
    #: hạn mức Trả sau (mô phỏng) của tài khoản mới (VND)
    default_credit_limit_vnd: int = 0
    #: tên hiển thị khi tài khoản chưa có hồ sơ và JWT không có tên
    default_display_name: str = ""
    #: độ tươi của dự báo (giây): quá hạn này thì đánh dấu `stale`
    forecast_freshness_seconds: int = 0
    #: thẻ chủ động báo nghĩa vụ đến hạn trong N ngày tới
    proactive_obligation_days: int = 3
    #: giữ bảng tra (loại giao dịch, biểu phí, hũ mẫu) trong bộ nhớ bao lâu (giây)
    reference_cache_seconds: int = 300
    #: tên EventBridge bus; rỗng thì không phát sự kiện (chỉ log)
    event_bus_name: str = ""
    #: tên Lambda `yofina-forecast-batch` (đặt lại demo và đọc dự báo cũ gọi nó); rỗng thì ledger không tự tính dự báo
    forecast_function_name: str = ""
    #: thời gian tối đa chờ một lần tính dự báo đồng bộ (giây); nhỏ hơn timeout của Lambda và của API
    forecast_sync_timeout_seconds: float = 22.0
    #: kỳ tính tổng nghĩa vụ của luật `obligation_to_income` (số ngày tới), cùng giá trị với horizon dự báo
    suitability_window_days: int = 30

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
            transaction_max_amount_vnd=cfg.get_int("transaction_max_amount_vnd"),
            salary_deviation_ask_percent=cfg.get_decimal("salary_deviation_ask_percent"),
            default_credit_limit_vnd=cfg.get_int("default_credit_limit_vnd"),
            default_display_name=cfg.get("default_display_name"),
            forecast_freshness_seconds=cfg.get_int("forecast_freshness_seconds"),
            proactive_obligation_days=cfg.get_int("proactive_obligation_days"),
            reference_cache_seconds=cfg.get_int("reference_cache_seconds"),
            event_bus_name=cfg.get("event_bus_name", default=""),
            forecast_function_name=cfg.get("forecast_function_name", default=""),
            forecast_sync_timeout_seconds=float(
                cfg.get("forecast_sync_timeout_seconds", default="22")
            ),
            suitability_window_days=cfg.get_int("suitability_window_days"),
        )
