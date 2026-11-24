"""Quy đổi ngoại tệ (`yofina_ingest.fx`): đọc đúng định dạng của Vietcombank, làm tròn tới đồng, bộ nhớ đệm theo ngày, lùi ngày khi
chưa có bảng, kẹp ngày tương lai, lỗi tra tỷ giá. Nguồn trong mã là nguồn thật; ở đây chỉ thay bằng nguồn giả đếm lượt gọi."""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from yofina_ingest import fx

# Thân trả lời rút gọn của https://www.vietcombank.com.vn/api/exchangerates?date=2026-11-10 (gọi thật một lần ngày 24/11/2026,
# bỏ trường `icon` và các ngoại tệ khác). DKK có `cash` 0.00: ô bằng 0 bị bỏ, ô `sell` vẫn dùng.
VCB_2026_11_10 = {
    "Count": 3,
    "Date": "2026-11-10T00:00:00",
    "UpdatedDate": "2026-11-10T23:00:00+07:00",
    "Data": [
        {"currencyName": "US DOLLAR", "currencyCode": "USD", "cash": "25380.00", "transfer": "25410.00", "sell": "25790.00"},
        {"currencyName": "EURO", "currencyCode": "EUR", "cash": "28027.46", "transfer": "28310.56", "sell": "29506.30"},
        {"currencyName": "DANISH KRONE", "currencyCode": "DKK", "cash": "0.00", "transfer": "3777.86", "sell": "3922.48"},
    ],
}  # fmt: skip
#: ngày chưa có bảng (ví dụ ngày tương lai): Vietcombank trả Count 0 và Data rỗng
VCB_EMPTY = {
    "Count": 0,
    "Date": "0001-01-01T00:00:00",
    "UpdatedDate": "0001-01-01T00:00:00",
    "Data": [],
}
NOW = datetime(2026, 11, 24, 11, 30, tzinfo=UTC)  # 18:30 giờ Việt Nam


class FakeSource:
    """Nguồn giả: `tables[ngày]` là bảng của ngày đó, vắng là chưa có bảng; `fail` thì ném lỗi mạng."""

    def __init__(self, tables=None, fail=False):
        self.tables = tables or {}
        self.fail = fail
        self.calls: list[date] = []

    def fetch(self, day):
        self.calls.append(day)
        if self.fail:
            raise fx.RateUnavailable("network")
        rates = self.tables.get(day)
        return None if rates is None else fx.RateTable(day=day, rates=rates)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def converter(source, clock=None, now=NOW):
    return fx.FxConverter(source, now=lambda: now, monotonic=clock or Clock())


# --- định dạng của nguồn thật ---------------------------------------------------------------------------------------------------
def test_doc_dung_dinh_dang_vietcombank_lay_cot_ban():
    table = fx.parse_vcb(VCB_2026_11_10, date(2026, 11, 10))
    assert table.day == date(2026, 11, 10)
    assert table.rates == {
        "USD": Decimal("25790.00"),
        "EUR": Decimal("29506.30"),
        "DKK": Decimal("3922.48"),
    }


def test_ngay_chua_co_bang_la_none_tra_loi_la_thi_loi():
    assert fx.parse_vcb(VCB_EMPTY, date(2026, 12, 30)) is None
    for bad in (
        {"Data": "x"},
        {"Data": [{"currencyCode": "USD"}], "Date": "2026-11-10"},
        {"Data": [{}], "Date": "rac"},
    ):
        with pytest.raises(fx.RateUnavailable) as e:
            fx.parse_vcb(bad, date(2026, 11, 10))
        assert e.value.reason == "bad_response"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_nguon_vietcombank_goi_dung_url_va_bao_loi_mang():
    seen = {}

    def opener(req, timeout):
        seen["url"], seen["timeout"] = req.full_url, timeout
        seen["accept"] = req.get_header("Accept")
        return _Resp(json.dumps(VCB_2026_11_10).encode("utf-8"))

    table = fx.VietcombankSource(opener=opener).fetch(date(2026, 11, 10))
    assert seen["url"] == "https://www.vietcombank.com.vn/api/exchangerates?date=2026-11-10"
    assert seen["timeout"] == fx.HTTP_TIMEOUT_SECONDS and seen["accept"] == "application/json"
    assert table.rates["USD"] == Decimal("25790.00")

    def down(req, timeout):
        raise urllib.error.URLError("dns")

    with pytest.raises(fx.RateUnavailable) as e:
        fx.VietcombankSource(opener=down).fetch(date(2026, 11, 10))
    assert e.value.reason == "network"
    with pytest.raises(fx.RateUnavailable) as e:
        fx.VietcombankSource(opener=lambda r, timeout: _Resp(b"<html>")).fetch(date(2026, 11, 10))
    assert e.value.reason == "bad_response"


# --- làm tròn --------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("original", "rate", "vnd"),
    [
        ("111.11", "25790.00", 2_865_527),  # 2.865.526,9: làm tròn lên
        ("20", "25790.00", 515_800),
        ("0.5", "1", 1),  # nửa đồng làm tròn lên
        ("0.49", "1", 0),
        ("1000", "166.64", 166_640),  # JPY, tỷ giá có phần lẻ
        ("19.99", "29506.30", 589_831),  # 589.830,937
    ],
)
def test_lam_tron_toi_dong(original, rate, vnd):
    assert fx.to_vnd(Decimal(original), Decimal(rate)) == vnd


def test_chuoi_thap_phan_khong_ky_hieu_khoa_hoc():
    assert fx.decimal_text(Decimal("25790"), 2) == "25790.00"
    assert fx.decimal_text(Decimal("1E+2"), 2) == "100.00"


# --- tra tỷ giá và bộ nhớ đệm ------------------------------------------------------------------------------------------------
def test_mot_lan_goi_cho_moi_tien_te_cua_cung_ngay_va_ngay_da_qua_khong_goi_lai():
    src = FakeSource({date(2026, 11, 10): {"USD": Decimal("25790.00"), "EUR": Decimal("29506.30")}})
    clock = Clock()
    c = converter(src, clock)
    usd = c.rate("usd", date(2026, 11, 10))
    assert (usd.currency, usd.rate_vnd, usd.rate_date) == (
        "USD",
        Decimal("25790.00"),
        date(2026, 11, 10),
    )
    assert (usd.source, usd.rate_type) == ("vietcombank", "sell")
    assert c.rate("EUR", date(2026, 11, 10)).rate_vnd == Decimal("29506.30")
    clock.t += 10 * 86400  # bảng của ngày đã qua không đổi: giữ tới khi tiến trình tắt
    c.rate("USD", date(2026, 11, 10))
    assert src.calls == [date(2026, 11, 10)]


def test_bang_hom_nay_het_han_sau_mot_gio():
    today = date(2026, 11, 24)
    src = FakeSource({today: {"USD": Decimal("25800")}})
    clock = Clock()
    c = converter(src, clock)
    c.rate("USD", today)
    clock.t += fx.TODAY_TTL_SECONDS - 1
    c.rate("USD", today)
    assert len(src.calls) == 1
    clock.t += 2
    c.rate("USD", today)
    assert len(src.calls) == 2


def test_ngay_chua_co_bang_thi_lui_ngay_va_bao_ngay_cua_bang():
    src = FakeSource({date(2026, 11, 8): {"USD": Decimal("25780")}})
    r = converter(src).rate("USD", date(2026, 11, 10))
    assert r.rate_date == date(2026, 11, 8) and r.rate_vnd == Decimal("25780")
    assert src.calls == [date(2026, 11, 10), date(2026, 11, 9), date(2026, 11, 8)]


def test_ngay_sau_hom_nay_kep_ve_hom_nay_theo_gio_viet_nam():
    # 23:30 UTC ngày 24/11 là 06:30 ngày 25/11 ở Việt Nam
    late = datetime(2026, 11, 24, 23, 30, tzinfo=UTC)
    src = FakeSource({date(2026, 11, 25): {"USD": Decimal("25810")}})
    r = converter(src, now=late).rate("USD", date(2026, 12, 10))
    assert r.rate_date == date(2026, 11, 25) and src.calls == [date(2026, 11, 25)]


def test_qua_so_ngay_lui_toi_da_thi_khong_co_ty_gia():
    src = FakeSource({})
    with pytest.raises(fx.RateUnavailable) as e:
        converter(src).rate("USD", date(2026, 11, 10))
    assert e.value.reason == "no_table" and len(src.calls) == fx.MAX_LOOKBACK_DAYS + 1


def test_loi_mang_khong_lui_ngay_va_khong_goi_don():
    src = FakeSource(fail=True)
    clock = Clock()
    c = converter(src, clock)
    for _ in range(3):
        with pytest.raises(fx.RateUnavailable) as e:
            c.rate("USD", date(2026, 11, 10))
        assert e.value.reason == "network"
    assert src.calls == [date(2026, 11, 10)]  # lỗi được nhớ MISS_TTL_SECONDS
    clock.t += fx.MISS_TTL_SECONDS + 1
    with pytest.raises(fx.RateUnavailable):
        c.rate("USD", date(2026, 11, 10))
    assert len(src.calls) == 2


def test_tien_te_khong_co_trong_bang():
    src = FakeSource({date(2026, 11, 10): {"USD": Decimal("25790")}})
    with pytest.raises(fx.RateUnavailable) as e:
        converter(src).rate("XAU", date(2026, 11, 10))
    assert e.value.reason == "unknown_currency"


def test_bo_quy_doi_mac_dinh_dung_nguon_that_va_dung_chung():
    a, b = fx.default_converter(), fx.default_converter()
    assert a is b and isinstance(a.source, fx.VietcombankSource)
    assert a.source.url == fx.VCB_URL
