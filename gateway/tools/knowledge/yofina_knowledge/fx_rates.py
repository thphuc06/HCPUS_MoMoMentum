"""`knowledge___get_exchange_rate`: tỷ giá BÁN của một ngoại tệ theo ngày, kèm số VND quy đổi của một số tiền (tùy chọn).

Cùng một hàm và cùng một nguồn với pipeline nạp chứng từ (`yofina_core.fx`): bảng công bố của Vietcombank, kẹp ngày tương lai về hôm
nay, lùi tối đa 4 ngày khi ngày đó chưa có bảng, làm tròn tới đồng bằng `Decimal`. Không gọi model, không ghi DB.

Kết quả theo `contracts/tools/knowledge.results.schema.json` (`ExchangeRateData`): số gốc và tỷ giá là chuỗi thập phân như `IngestFx`
của khối `ingest_review`; `amount_vnd` là số nguyên VND. Lỗi: tham số sai hay ngoại tệ không có trong bảng là `PARAMS_INVALID`; nguồn
không trả lời được (mạng, hết giờ, trả lời lạ, không có bảng trong khoảng lùi) là `INTERNAL_ERROR` (lỗi tạm thời, agent thử lại).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from yofina_core import fx
from yofina_core.errors import ErrorCode, YofinaError
from yofina_core.params import MAX_VND

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
#: số gốc: tối đa 12 chữ số phần nguyên, 4 chữ số lẻ (cùng dạng `amount_original` của `IngestFx`)
_AMOUNT_RE = re.compile(r"^[0-9]{1,12}(\.[0-9]{1,4})?$")
_MIN_DATE = date(2000, 1, 1)


def _currency(raw: Any) -> str:
    code = raw.strip().upper() if isinstance(raw, str) else ""
    if not _CURRENCY_RE.fullmatch(code) or code == "VND":
        raise YofinaError(
            ErrorCode.PARAMS_INVALID, "currency phải là mã ngoại tệ ISO 4217 (3 chữ cái, khác VND)."
        )
    return code


def _day(raw: Any, today: date) -> date:
    if raw in (None, ""):
        return today
    try:
        day = date.fromisoformat(raw) if isinstance(raw, str) else None
    except ValueError:
        day = None
    if day is None or day < _MIN_DATE:
        raise YofinaError(ErrorCode.PARAMS_INVALID, "date phải là ngày YYYY-MM-DD.")
    return day


def _amount(raw: Any) -> Decimal | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise YofinaError(ErrorCode.PARAMS_INVALID, "amount phải là số.")
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation:
        value = None
    if value is None or not value.is_finite() or value <= 0:
        raise YofinaError(ErrorCode.PARAMS_INVALID, "amount phải là số dương.")
    text = f"{value.normalize():f}"
    if not _AMOUNT_RE.fullmatch(text):
        raise YofinaError(
            ErrorCode.PARAMS_INVALID, "amount có tối đa 12 chữ số phần nguyên và 4 chữ số lẻ."
        )
    return Decimal(text)


def exchange_rate_data(
    converter: fx.FxConverter, today: date, *, currency: Any, day: Any = None, amount: Any = None
) -> dict[str, Any]:
    """`ExchangeRateData` của (ngoại tệ, ngày); `today` là ngày mô phỏng của người gọi (`app_today`), dùng khi không nêu ngày."""
    code = _currency(currency)
    requested = _day(day, today)
    original = _amount(amount)
    try:
        rate = converter.rate(code, requested)
    except fx.RateUnavailable as exc:
        if exc.reason == "unknown_currency":
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, f"Bảng tỷ giá của Vietcombank không có ngoại tệ {code}."
            ) from None
        raise YofinaError(
            ErrorCode.INTERNAL_ERROR, "Chưa tra được tỷ giá lúc này, bạn thử lại sau."
        ) from None
    data: dict[str, Any] = {
        "currency": code,
        "rate": fx.decimal_text(rate.rate_vnd, 2),
        "rate_type": rate.rate_type,
        "rate_source": rate.source,
        "rate_date": rate.rate_date.isoformat(),
        "requested_date": requested.isoformat(),
    }
    if original is not None:
        vnd = fx.to_vnd(original, rate.rate_vnd)
        if not 1 <= vnd <= MAX_VND:
            raise YofinaError(
                ErrorCode.PARAMS_INVALID, "Số tiền quy đổi nằm ngoài khoảng cho phép."
            )
        data["amount_original"] = f"{original:f}"
        data["amount_vnd"] = vnd
    return data
