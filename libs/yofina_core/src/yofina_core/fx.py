"""Quy đổi số tiền ngoại tệ sang VND theo tỷ giá THẬT của một ngày. Không gọi model, không ghi DB.

MỘT hàm, MỘT nguồn tỷ giá cho hai nơi dùng: pipeline nạp chứng từ (F6, `yofina_ingest`, gọi thẳng `default_converter()` trong
Lambda `yofina-ingest`) và tool `knowledge___get_exchange_rate` của agent chat (Lambda `yofina-ledger` sau AgentCore Gateway,
`yofina_knowledge.fx_rates`). Hai Lambda đều nằm ngoài VPC nên ra được internet; mỗi môi trường thực thi có bộ nhớ đệm riêng.

Nguồn: bảng tỷ giá công bố của Vietcombank, đúng endpoint JSON mà trang "Tỷ giá" chính thức của ngân hàng dùng
(`/api/exchangerates?date=YYYY-MM-DD`, công khai, không cần khóa). Cột dùng là **Bán** (`sell`): thanh toán thẻ hay chuyển tiền ra
nước ngoài là ngân hàng BÁN ngoại tệ cho chủ thẻ. Số trên sao kê thẻ thường cao hơn vì còn phí chuyển đổi ngoại tệ của ngân hàng
phát hành, nên số VND ở đây là số ƯỚC TÍNH: dòng luôn vào hàng chờ duyệt và người dùng sửa được trước khi chốt. Lý do chọn nguồn,
điều khoản và giới hạn gọi: docs/research/ingest-fx-rates.md.

- **Ngày tỷ giá**: ngày giao dịch trên chứng từ (không có thì ngày nạp). Bảng chỉ có cho ngày đã qua hoặc hôm nay theo giờ Việt Nam,
  nên ngày sau hôm nay (thật) được kẹp về hôm nay; ngày chưa có bảng thì lùi từng ngày, tối đa `MAX_LOOKBACK_DAYS`. `FxRate.rate_date`
  là ngày của bảng đã dùng.
- **Làm tròn**: `amount_original * rate` làm tròn tới đồng, nửa đồng làm tròn lên (`ROUND_HALF_UP`), tính bằng `Decimal`.
- **Bộ nhớ đệm** trong tiến trình theo ngày (một lần gọi trả cả bảng mọi ngoại tệ của ngày đó), nên mọi (tiền tệ, ngày) dùng chung
  một lần gọi. Bảng của ngày đã qua không đổi nên giữ tới khi Lambda tắt; bảng của hôm nay giữ `TODAY_TTL_SECONDS` (ngân hàng cập
  nhật trong ngày); lỗi mạng hay ngày không có bảng giữ `MISS_TTL_SECONDS` để không gọi dồn. Không cần bảng hay chỗ lưu mới.
- **Lỗi** (mạng, hết giờ, trả lời lạ, tiền tệ không có trong bảng): `RateUnavailable`. Người gọi để dòng vào hàng chờ với số gốc và
  yêu cầu người dùng nhập số VND, không đoán.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Protocol
from zoneinfo import ZoneInfo

log = logging.getLogger("yofina.fx")

SOURCE = "vietcombank"
RATE_TYPE = "sell"
VCB_URL = "https://www.vietcombank.com.vn/api/exchangerates?date={day}"
#: giờ của bảng tỷ giá (ngân hàng công bố theo giờ Việt Nam, không theo đồng hồ mô phỏng của ứng dụng)
SOURCE_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
HTTP_TIMEOUT_SECONDS = 4.0
MAX_LOOKBACK_DAYS = 4
TODAY_TTL_SECONDS = 3600
MISS_TTL_SECONDS = 600
CACHE_MAX_DAYS = 400
USER_AGENT = "yofina/1.0"


class RateUnavailable(Exception):
    """Không có tỷ giá dùng được cho (tiền tệ, ngày). `reason`: network, bad_response, no_table, unknown_currency."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class FxRate:
    currency: str
    rate_vnd: Decimal
    rate_date: date
    source: str = SOURCE
    rate_type: str = RATE_TYPE


@dataclass(frozen=True)
class RateTable:
    """Bảng tỷ giá bán của một ngày: `rates` là tiền tệ -> VND cho một đơn vị (chỉ số dương)."""

    day: date
    rates: Mapping[str, Decimal]


class RateSource(Protocol):
    def fetch(self, day: date) -> RateTable | None:
        """Bảng của `day`; None nếu ngày đó chưa có bảng. Lỗi mạng hay trả lời lạ ném `RateUnavailable`."""
        ...


def _decimal(raw: Any) -> Decimal | None:
    try:
        d = Decimal(str(raw).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() and d > 0 else None


def parse_vcb(payload: Mapping[str, Any], requested: date) -> RateTable | None:
    """Đọc thân JSON của endpoint Vietcombank. `Count = 0` (ngày chưa có bảng) thì None. Ô `sell` bằng 0 bị bỏ."""
    data = payload.get("Data")
    if not isinstance(data, list):
        raise RateUnavailable("bad_response")
    if not data:
        return None
    raw_day = str(payload.get("Date") or "")[:10]
    try:
        day = date.fromisoformat(raw_day)
    except ValueError:
        raise RateUnavailable("bad_response") from None
    if day.year < 2000 or day > requested:
        raise RateUnavailable("bad_response")
    rates: dict[str, Decimal] = {}
    for item in data:
        if not isinstance(item, Mapping):
            continue
        code = str(item.get("currencyCode") or "").strip().upper()
        sell = _decimal(item.get(RATE_TYPE))
        if len(code) == 3 and code.isalpha() and sell is not None:
            rates[code] = sell
    if not rates:
        raise RateUnavailable("bad_response")
    return RateTable(day=day, rates=rates)


class VietcombankSource:
    """Gọi endpoint JSON công khai của Vietcombank bằng `urllib` (không thêm gói). Lambda `yofina-ingest` và `yofina-ledger` không nằm
    trong VPC nên ra được internet (không cần NAT)."""

    def __init__(
        self, *, url: str = VCB_URL, timeout: float = HTTP_TIMEOUT_SECONDS, opener: Any = None
    ) -> None:
        self.url = url
        self.timeout = timeout
        self._open = opener or urllib.request.urlopen

    def fetch(self, day: date) -> RateTable | None:
        req = urllib.request.Request(
            self.url.format(day=day.isoformat()),
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with self._open(req, timeout=self.timeout) as resp:
                body = resp.read(200_000)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            log.warning(json.dumps({"msg": "fx_fetch_failed", "error": type(exc).__name__}))
            raise RateUnavailable("network") from exc
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise RateUnavailable("bad_response") from exc
        if not isinstance(payload, Mapping):
            raise RateUnavailable("bad_response")
        return parse_vcb(payload, day)


def to_vnd(amount_original: Decimal, rate_vnd: Decimal) -> int:
    """`amount_original * rate_vnd` làm tròn tới đồng (nửa đồng làm tròn lên)."""
    return int((amount_original * rate_vnd).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def decimal_text(d: Decimal, places: int) -> str:
    """Chuỗi thập phân cố định `places` chữ số lẻ (không ký hiệu khoa học), như hợp đồng `IngestFx`."""
    return f"{d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP):f}"


class FxConverter:
    """Tra tỷ giá bán của (tiền tệ, ngày) qua `source`, có bộ nhớ đệm theo ngày. Dùng chung trong tiến trình (`default_converter`)."""

    def __init__(
        self,
        source: RateSource,
        *,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        max_lookback_days: int = MAX_LOOKBACK_DAYS,
    ) -> None:
        self.source = source
        self._now = now or (lambda: datetime.now(UTC))
        self._mono = monotonic or time.monotonic
        self.max_lookback_days = max_lookback_days
        self._cache: dict[date, tuple[RateTable | RateUnavailable | None, float | None]] = {}
        self._lock = threading.Lock()
        self.fetches = 0

    def source_today(self) -> date:
        return self._now().astimezone(SOURCE_TZ).date()

    def _table(self, day: date, today: date) -> RateTable | None:
        now = self._mono()
        with self._lock:
            hit = self._cache.get(day)
        if hit is not None and (hit[1] is None or hit[1] > now):
            # lỗi vừa gặp: báo lại, không gọi dồn và không lùi ngày
            if isinstance(hit[0], RateUnavailable):
                raise RateUnavailable(hit[0].reason)
            return hit[0]
        self.fetches += 1
        try:
            table = self.source.fetch(day)
        except RateUnavailable as exc:
            with self._lock:
                self._cache[day] = (exc, now + MISS_TTL_SECONDS)
            raise
        if table is None:
            expires: float | None = now + MISS_TTL_SECONDS
        elif day >= today:
            expires = now + TODAY_TTL_SECONDS
        else:
            expires = None
        with self._lock:
            if len(self._cache) >= CACHE_MAX_DAYS:
                self._cache.clear()
            self._cache[day] = (table, expires)
        return table

    def rate(self, currency: str, day: date) -> FxRate:
        code = currency.strip().upper()
        today = self.source_today()
        probe = min(day, today)
        for _ in range(self.max_lookback_days + 1):
            table = self._table(probe, today)
            if table is not None:
                value = table.rates.get(code)
                if value is None:
                    raise RateUnavailable("unknown_currency")
                return FxRate(currency=code, rate_vnd=value, rate_date=table.day)
            probe -= timedelta(days=1)
        raise RateUnavailable("no_table")


_default: FxConverter | None = None
_default_lock = threading.Lock()


def default_converter() -> FxConverter:
    """Bộ quy đổi của tiến trình (nguồn thật), dựng lần đầu cần tới; bộ nhớ đệm sống cùng môi trường thực thi của Lambda."""
    global _default
    with _default_lock:
        if _default is None:
            _default = FxConverter(VietcombankSource())
        return _default
