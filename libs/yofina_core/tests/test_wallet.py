import pytest

from yofina_core import wallet
from yofina_core.wallet import split_amount


def test_chia_luong_theo_ty_le_tong_bang_so_tien():
    shares = [
        ("an_uong", 30),
        ("di_lai", 7),
        ("hoa_don", 31),
        ("giai_tri", 7),
        ("du_lich", 10),
        ("du_phong", 10),
        ("nghia_vu", 5),
    ]
    out = split_amount(9_000_000, shares)
    assert out == {
        "an_uong": 2_700_000, "di_lai": 630_000, "hoa_don": 2_790_000, "giai_tri": 630_000,
        "du_lich": 900_000, "du_phong": 900_000, "nghia_vu": 450_000,
    }  # fmt: skip
    assert sum(out.values()) == 9_000_000


def test_phan_du_do_lam_tron_vao_hu_ty_le_lon_nhat_hoa_thi_hu_dung_truoc():
    assert split_amount(100, [("a", "33.33"), ("b", "33.33"), ("c", "33.34")]) == {
        "a": 33,
        "b": 33,
        "c": 34,
    }
    assert split_amount(10, [("a", 50), ("b", 50)]) == {"a": 5, "b": 5}
    out = split_amount(101, [("a", 50), ("b", 50)])
    assert out == {"a": 51, "b": 50}  # hòa tỷ lệ: phần dư vào hũ đứng trước
    out = split_amount(7, [("a", 10), ("b", 60), ("c", 30)])
    assert sum(out.values()) == 7 and out["b"] == max(out.values())


@pytest.mark.parametrize("amount", [0, 1, 2, 99, 12_345_678, 99_999_999_999_999])
def test_tong_cac_phan_luon_bang_so_tien_voi_ty_le_le(amount):
    shares = [("a", "12.5"), ("b", "37.5"), ("c", "33.33"), ("d", "16.67")]
    assert sum(split_amount(amount, shares).values()) == amount


def test_hu_ty_le_0_van_co_mat_va_nhan_0():
    assert split_amount(1000, [("a", 100), ("b", 0)]) == {"a": 1000, "b": 0}


@pytest.mark.parametrize(
    "shares",
    [[], [("a", 99)], [("a", 60), ("b", 50)], [("a", 110), ("b", -10)], [("a", 50), ("a", 50)]],
)
def test_ty_le_sai_bi_tu_choi(shares):
    with pytest.raises(ValueError):
        split_amount(1000, shares)


def test_so_tien_am_bi_tu_choi():
    with pytest.raises(ValueError):
        split_amount(-1, [("a", 100)])


def test_tool_ghi_tren_man_hinh_va_cho_agent_khong_trung_nhau_o_nhom_con_lai():
    assert set(wallet.AGENT_WRITE_TOOLS) <= set(wallet.ACTION_TOOLS)
    assert wallet.MOVE_BETWEEN_JARS not in wallet.GENERIC_ACTION_TOOLS
    # phase 5: confirm_rows (target ingest) KHÔNG nằm trong ACTION_TOOLS của ledger; nó đi qua /ingest/confirmations và
    # /ingest/actions của Lambda ingest, nhưng vẫn dùng khối confirm_action / receipt_action
    assert len(set(wallet.ACTION_TOOLS)) == len(wallet.ACTION_TOOLS) == 7
    assert wallet.CONFIRM_ROWS not in wallet.ACTION_TOOLS
    assert wallet.INGEST_ACTION_TOOLS == (wallet.CONFIRM_ROWS,)
    assert not set(wallet.INGEST_ACTION_TOOLS) & set(wallet.ACTION_TOOLS)
    assert wallet.CONFIRM_ROWS in wallet.GENERIC_ACTION_TOOLS
    assert wallet.GENERIC_ACTION_TOOLS[-1] == wallet.CONFIRM_ROWS


def test_obligation_source_uses_saved_jar_or_shared_jar_and_requires_legacy_choice():
    resolve = wallet.resolve_obligation_pay_jar
    legacy = [("hoa_don", "obligation"), ("daily", "spending"), ("system", "system")]
    modern = [*legacy, ("nghia_vu", "obligation")]
    # ví cũ không có nghia_vu: hũ obligation đầu tiên, như trước khi có hũ chung
    assert resolve(legacy) == "hoa_don"
    assert resolve(legacy, saved="system") == "hoa_don"
    # không có hũ obligation nào: không có mặc định, phải chọn
    no_obligation = [("daily", "spending"), ("system", "system")]
    assert resolve(no_obligation) is None
    assert resolve(no_obligation, saved="system") is None
    assert resolve(legacy, selected="daily") == "daily"
    assert resolve(modern, saved="daily", selected="hoa_don") == "daily"
    assert resolve(modern, saved="removed") == "nghia_vu"


# hũ mặc định của từng loại giao dịch trong db/seed/tx_type_map.sql (hũ cũ của bộ bảy)
_TYPE_DEFAULTS = {
    "food_drink": "an_uong", "grocery": "an_uong", "ride_hailing": "di_lai", "fuel": "di_lai",
    "entertainment": "giai_tri", "subscription": "giai_tri", "bill_electricity": "hoa_don",
    "bill_water": "hoa_don", "bill_internet": "hoa_don", "bill_phone": "hoa_don", "phone_topup": "hoa_don",
    "rent": "hoa_don", "travel": "du_lich",
}  # fmt: skip
_DEMO_WALLET = ("an_uong", "di_lai", "nghia_vu", "giai_tri", "muc_tieu", "du_phong", "dau_tu")
_THREE_JAR_WALLET = ("chi_hang_ngay", "nghia_vu", "du_phong")


def test_hu_cua_giao_dich_moi_tren_vi_demo_va_vi_ba_hu():
    """Ví demo (issue #39, không có Chi hằng ngày): ăn uống, đi lại, giải trí vào đúng hũ; hóa đơn, nạp điện thoại, tiền nhà vào Nghĩa
    vụ. Ví ba hũ mới: mọi khoản chi vào Chi hằng ngày, hóa đơn vào Nghĩa vụ."""
    route = {
        wallet_codes: {t: wallet.transaction_jar(d, wallet_codes, tx_type=t) for t, d in _TYPE_DEFAULTS.items()}
        for wallet_codes in (_DEMO_WALLET, _THREE_JAR_WALLET)
    }
    bills = ("bill_electricity", "bill_water", "bill_internet", "bill_phone", "phone_topup", "rent")
    assert route[_DEMO_WALLET] == {
        "food_drink": "an_uong", "grocery": "an_uong", "ride_hailing": "di_lai", "fuel": "di_lai",
        "entertainment": "giai_tri", "subscription": "giai_tri", **dict.fromkeys(bills, "nghia_vu"),
        "travel": None,  # ví demo không có hũ Du lịch hay Chi hằng ngày: hỏi hũ
    }  # fmt: skip
    assert route[_THREE_JAR_WALLET] == {
        "food_drink": "chi_hang_ngay", "grocery": "chi_hang_ngay", "ride_hailing": "chi_hang_ngay",
        "fuel": "chi_hang_ngay", "entertainment": "chi_hang_ngay", "subscription": "nghia_vu",
        **dict.fromkeys(bills, "nghia_vu"), "travel": "chi_hang_ngay",
    }  # fmt: skip
