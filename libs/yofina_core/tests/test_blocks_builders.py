from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from yofina_core import blocks as b
from yofina_core.confirm import ParamsError

NOW = datetime(2026, 12, 10, 3, 0, 5, tzinfo=UTC)
TODAY = date(2026, 11, 21)
TRACE = "8f3a21c94b7e4d0aa1c25e6f7b8c9d01"


def _jar(code, name, balance, pct="10.00"):
    return {
        "code": code,
        "name": name,
        "color_key": "violet",
        "icon_key": "wallet",
        "balance_vnd": balance,
        "split_percent": pct,
    }


def test_jar_summary_tinh_tong_tu_so_du_that_va_nhan_numeric_cua_data_api():
    blk = b.build_jar_summary(
        jars=[_jar("a", "A", Decimal("380000"), "30.00"), _jar("b", "B", "620000", "7.50")],
        trace_id=TRACE,
        source_tool="ledger___get_jar_balances",
        as_of=NOW,
        app_date=TODAY,
    )
    wire = b.block_to_wire(blk)
    assert wire["data"]["jars_total_vnd"] == 1_000_000
    assert wire["data"]["jars"][0]["balance_vnd"] == 380000
    assert wire["data"]["jars"][0]["split_percent"] == 30
    assert wire["data"]["jars"][1]["split_percent"] == 7.5
    assert wire["fallback_text"] == "Số dư 2 hũ, tổng 1.000.000 ₫."
    assert wire["id"] == f"jar_summary:{TRACE}"
    assert wire["source"] == {
        "tool": "ledger___get_jar_balances",
        "as_of": "2026-12-10T03:00:05Z",
        "app_date": "2026-11-21",
    }
    assert b.parse_block(wire) == blk


def test_jar_summary_rong_va_tien_le_bi_tu_choi():
    blk = b.build_jar_summary(jars=[], trace_id=TRACE, source_tool="t", as_of=NOW, app_date=TODAY)
    assert b.block_to_wire(blk)["data"] == {"jars": [], "jars_total_vnd": 0}
    with pytest.raises(ValueError):
        b.build_jar_summary(
            jars=[_jar("a", "A", Decimal("1.5"))],
            trace_id=TRACE,
            source_tool="t",
            as_of=NOW,
            app_date=TODAY,
        )


def _confirm(**over):
    kw = dict(
        tool="move_between_jars",
        params={"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100000},
        from_jar={"code": "giai_tri", "name": "Giải trí", "balance_vnd": Decimal("760000")},
        to_jar={"code": "an_uong", "name": "Ăn uống", "balance_vnd": "380000"},
        trace_id=TRACE,
        source_tool="ledger___move_between_jars",
        as_of=NOW,
        app_date=TODAY,
        expires_at=NOW + timedelta(minutes=10),
    )
    kw.update(over)
    return b.build_confirm(**kw)


def test_confirm_chua_dung_thu_se_duoc_ky_va_xem_truoc_hai_hu():
    wire = b.block_to_wire(_confirm())
    data = wire["data"]
    assert data["params"] == {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100000}
    assert data["params_hash"] == (
        "52a35d69448e3621190f43bbc8fa12356d2cfdd9895fac320e0557dfa779a962"
    )
    assert data["preview"] == {
        "from": {"code": "giai_tri", "name": "Giải trí", "before_vnd": 760000, "after_vnd": 660000},
        "to": {"code": "an_uong", "name": "Ăn uống", "before_vnd": 380000, "after_vnd": 480000},
    }
    assert data["summary"] == "Chuyển 100.000 ₫ từ Giải trí sang Ăn uống"
    assert data["expires_at"] == "2026-12-10T03:10:05Z"
    assert wire["id"] == f"confirm:{TRACE}:52a35d69448e"
    assert b.parse_block(wire).type == "confirm"


def test_confirm_chuan_hoa_tham_so_truoc_khi_bam():
    a = _confirm(params={"from_jar": " Giai_Tri", "to_jar": "AN_UONG", "amount_vnd": 100000})
    c = _confirm(
        params={
            "from_jar": "giai_tri",
            "to_jar": "an_uong",
            "amount_vnd": 100000,
            "user_id": "u",
            "confirm_token": "x.y",
        }
    )
    assert a.data.params_hash == c.data.params_hash


def test_confirm_tu_choi_khi_khong_the_xem_truoc_dung():
    with pytest.raises(ValueError, match="không đủ"):
        _confirm(from_jar={"code": "giai_tri", "name": "Giải trí", "balance_vnd": 99_999})
    with pytest.raises(ValueError, match="không khớp"):
        _confirm(to_jar={"code": "khac", "name": "Khác", "balance_vnd": 1})
    with pytest.raises(ParamsError):
        _confirm(params={"from_jar": "a", "to_jar": "a", "amount_vnd": 1})
    with pytest.raises(ValueError):
        _confirm(tool="delete_everything")


def test_receipt_co_id_giao_dich_thoi_diem_va_so_du_sau():
    rid = "3b9f6c1e-7a52-4d8e-9c4b-0e1f2a3b4c5d"
    blk = b.build_receipt(
        tool="move_between_jars",
        transaction_id=rid,
        occurred_at=datetime(2026, 12, 10, 10, 2, 11, tzinfo=timezone(timedelta(hours=7))),
        app_date=TODAY,
        amount_vnd=Decimal("100000"),
        from_jar={"code": "giai_tri", "name": "Giải trí", "balance_vnd": "660000"},
        to_jar={"code": "an_uong", "name": "Ăn uống", "balance_vnd": Decimal("480000")},
        trace_id=TRACE,
        source_tool="rest:POST /actions",
    )
    wire = b.block_to_wire(blk)
    assert wire["id"] == f"receipt:{rid}"
    assert wire["data"]["occurred_at"] == "2026-12-10T03:02:11Z"  # đổi sang UTC
    assert wire["data"]["from_jar"]["balance_after_vnd"] == 660000
    assert wire["data"]["to_jar"]["balance_after_vnd"] == 480000
    assert wire["fallback_text"] == "Đã chuyển 100.000 ₫ từ Giải trí sang Ăn uống."
    assert b.parse_block(wire) == blk


def test_notice_khong_phat_null_khi_khong_co_code():
    blk = b.build_notice(
        kind="out_of_scope",
        title="Ngoài phạm vi",
        message="Mình chỉ hỗ trợ về chi tiêu và các hũ.",
        trace_id=TRACE,
        source_tool="agent",
        as_of=NOW,
        app_date=TODAY,
    )
    wire = b.block_to_wire(blk)
    assert "code" not in wire["data"]
    assert wire["id"] == f"notice:{TRACE}:out_of_scope"
    blk2 = b.build_notice(
        kind="degraded",
        title="Rút gọn",
        message="Hết lượt AI hôm nay.",
        code="MODEL_BUDGET_EXCEEDED",
        trace_id=TRACE,
        source_tool="agent",
        as_of=NOW,
        app_date=TODAY,
    )
    assert b.block_to_wire(blk2)["id"] == f"notice:{TRACE}:MODEL_BUDGET_EXCEEDED"
    assert b.parse_block(b.block_to_wire(blk2)) == blk2


def test_model_tu_choi_truong_la_va_kieu_sai():
    wire = b.block_to_wire(
        b.build_notice(
            kind="error",
            title="Lỗi",
            message="Có lỗi.",
            trace_id=TRACE,
            source_tool="agent",
            as_of=NOW,
            app_date=TODAY,
        )
    )
    bad = {**wire, "extra": 1}
    with pytest.raises(ValidationError):
        b.parse_block(bad)
    with pytest.raises(ValidationError):
        b.parse_block({**wire, "v": 2})
    with pytest.raises(ValidationError):
        b.parse_block({**wire, "type": "hologram_3d"})


def test_format_instant_can_mui_gio():
    with pytest.raises(ValueError):
        b.format_instant(datetime(2026, 1, 1, 0, 0))


def test_trace_id_tu_traceparent():
    tp = "00-8f3a21c94b7e4d0aa1c25e6f7b8c9d01-00f067aa0ba902b7-01"
    assert b.trace_id_from_traceparent(tp) == "8f3a21c94b7e4d0aa1c25e6f7b8c9d01"
    assert b.trace_id_from_traceparent(tp.upper()) == "8f3a21c94b7e4d0aa1c25e6f7b8c9d01"
    assert b.trace_id_from_traceparent(None) is None
    assert b.trace_id_from_traceparent("garbage") is None
    assert b.trace_id_from_traceparent("00-" + "0" * 32 + "-00f067aa0ba902b7-01") is None
    t = b.new_trace_id()
    assert len(t) == 32
    int(t, 16)
