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
        # hũ goal của ví demo dựng từ hũ Du lịch của persona: cùng ánh xạ mã hũ với đặt lại demo
        "travel": "muc_tieu",
    }  # fmt: skip
    assert route[_THREE_JAR_WALLET] == {
        "food_drink": "chi_hang_ngay", "grocery": "chi_hang_ngay", "ride_hailing": "chi_hang_ngay",
        "fuel": "chi_hang_ngay", "entertainment": "chi_hang_ngay", "subscription": "nghia_vu",
        **dict.fromkeys(bills, "nghia_vu"), "travel": "chi_hang_ngay",
    }  # fmt: skip


def test_moi_loai_giao_dich_mac_dinh_hu_du_lich_vao_hu_goal_cua_vi_demo_qua_anh_xa():
    """Mọi loại giao dịch có hũ mặc định `du_lich` (đọc từ db/seed/tx_type_map.sql, không chép tay) đi vào hũ mà ánh xạ của
    bộ hũ demo gộp Du lịch vào, trên ví demo cũ và ví demo có Chi hằng ngày; ví ba hũ giữ Chi hằng ngày, trừ khi người dùng thêm
    hũ Mục tiêu (hũ riêng thắng hũ chung)."""
    import re
    from pathlib import Path

    seed = (Path(__file__).resolve().parents[3] / "db" / "seed" / "tx_type_map.sql").read_text("utf-8")
    travel_types = re.findall(r"\('([a-z_]+)',\s*'[^']*',\s*'out',\s*'du_lich'", seed)
    assert travel_types  # hiện có `travel`
    goal_jar = wallet.LEGACY_JAR_ALIASES["du_lich"]
    with_goal = (*_THREE_JAR_WALLET, goal_jar)
    for tx_type in travel_types:
        assert wallet.transaction_jar("du_lich", _DEMO_WALLET, tx_type=tx_type) == goal_jar
        assert wallet.transaction_jar("du_lich", _DEMO_DAILY_WALLET, tx_type=tx_type) == goal_jar
        assert wallet.transaction_jar("du_lich", _THREE_JAR_WALLET, tx_type=tx_type) == "chi_hang_ngay"
        # hũ riêng (hũ goal mà ánh xạ gộp Du lịch vào) thắng hũ chung Chi hằng ngày (issue #39, 26/11)
        assert wallet.transaction_jar("du_lich", with_goal, tx_type=tx_type) == goal_jar
        # ví bảy hũ cũ còn hũ Du lịch: giữ hũ đó
        assert wallet.transaction_jar("du_lich", (*_DEMO_WALLET, "du_lich"), tx_type=tx_type) == "du_lich"
    # không có hũ nào nhận: hỏi hũ
    assert wallet.transaction_jar("du_lich", ("an_uong", "du_phong"), tx_type="travel") is None


#: ví demo từ 26/11 (issue #39): ba hũ mặc định rồi các hũ tự thêm
_DEMO_DAILY_WALLET = (
    "chi_hang_ngay", "nghia_vu", "du_phong", "an_uong", "di_lai", "giai_tri", "muc_tieu", "dau_tu",
)  # fmt: skip
_LEGACY_WALLET = ("an_uong", "di_lai", "hoa_don", "giai_tri", "du_lich", "du_phong", "nghia_vu")
_BILLS = ("bill_electricity", "bill_water", "bill_internet", "bill_phone", "phone_topup", "rent")


@pytest.mark.parametrize(
    ("wallet_codes", "expected"),
    [
        pytest.param(
            _DEMO_DAILY_WALLET,
            {
                "food_drink": "an_uong", "grocery": "an_uong", "ride_hailing": "di_lai", "fuel": "di_lai",
                "entertainment": "giai_tri", "subscription": "giai_tri", **dict.fromkeys(_BILLS, "nghia_vu"),
                "travel": "muc_tieu",
            },
            id="demo-8-hu",
        ),
        pytest.param(
            _THREE_JAR_WALLET,
            {
                "food_drink": "chi_hang_ngay", "grocery": "chi_hang_ngay", "ride_hailing": "chi_hang_ngay",
                "fuel": "chi_hang_ngay", "entertainment": "chi_hang_ngay", "subscription": "nghia_vu",
                **dict.fromkeys(_BILLS, "nghia_vu"), "travel": "chi_hang_ngay",
            },
            id="ba-hu",
        ),
        pytest.param(
            (*_THREE_JAR_WALLET, "an_uong"),
            {
                "food_drink": "an_uong", "grocery": "an_uong", "ride_hailing": "chi_hang_ngay",
                "fuel": "chi_hang_ngay", "entertainment": "chi_hang_ngay", "subscription": "nghia_vu",
                **dict.fromkeys(_BILLS, "nghia_vu"), "travel": "chi_hang_ngay",
            },
            id="ba-hu-them-an-uong",
        ),
        pytest.param(
            _LEGACY_WALLET,
            {
                "food_drink": "an_uong", "grocery": "an_uong", "ride_hailing": "di_lai", "fuel": "di_lai",
                "entertainment": "giai_tri", "subscription": "giai_tri", **dict.fromkeys(_BILLS, "hoa_don"),
                "travel": "du_lich",
            },
            id="bay-hu-cu",
        ),
    ],
)  # fmt: skip
def test_hu_rieng_khop_loai_giao_dich_thang_hu_chung(wallet_codes, expected):
    """Quy tắc phân loại theo loại giao dịch (issue #39, 26/11): ví có hũ riêng khớp loại (hũ mặc định của loại trong `tx_type_map`,
    hoặc hũ mà `LEGACY_JAR_ALIASES` gộp hũ đó vào) thì hũ riêng thắng; không có thì vào hũ chung của bộ ba (Chi hằng ngày, Nghĩa vụ)."""
    route = {t: wallet.transaction_jar(d, wallet_codes, tx_type=t) for t, d in _TYPE_DEFAULTS.items()}
    assert route == expected
    # hũ của nhãn (nhãn seed k-NN mang mã hũ của bộ bảy, không có loại giao dịch) đi cùng quy tắc
    labels = {code: wallet.transaction_jar(code, wallet_codes) for code in ("an_uong", "di_lai", "hoa_don", "du_lich")}
    assert labels == {
        "an_uong": expected["food_drink"], "di_lai": expected["ride_hailing"], "hoa_don": expected["rent"],
        "du_lich": expected["travel"],
    }  # fmt: skip


def test_obligation_kind_labels_match_frontend():
    """Nhãn loại nghĩa vụ phía server là CÙNG bảng `KIND_LABEL` của frontend (một bảng, hai ngôn ngữ): đủ mọi loại, chữ trùng."""
    import re
    from pathlib import Path

    source = (Path(__file__).resolve().parents[3] / "frontend/src/features/obligations/params.ts").read_text(encoding="utf-8")
    body = re.search(r"export const KIND_LABEL[^{]*\{(?P<body>[^}]*)\}", source)
    assert body is not None
    frontend = dict(re.findall(r"(\w+):\s*'([^']*)'", body["body"]))
    assert frontend == wallet.OBLIGATION_KIND_LABELS
    assert set(wallet.OBLIGATION_KIND_LABELS) == set(wallet.OBLIGATION_KINDS)


def test_danh_muc_loai_chi_trung_seed_tx_type_map():
    """`SPENDING_TX_TYPES` là bản Python của các dòng chiều `out` trong db/seed/tx_type_map.sql (dữ liệu sản phẩm): cùng mã, nhãn,
    hũ mặc định và thứ tự. Gói agent không mang tệp seed nên đọc danh mục từ đây; lệch là test đỏ."""
    import re
    from pathlib import Path

    seed = (Path(__file__).resolve().parents[3] / "db" / "seed" / "tx_type_map.sql").read_text("utf-8")
    rows = re.findall(r"\('([a-z_]+)',\s*'([^']*)',\s*'out',\s*(NULL|'[a-z_]+')", seed)
    assert len(rows) > 10
    expected = tuple((t, label, None if jar == "NULL" else jar.strip("'")) for t, label, jar in rows)
    assert expected == wallet.SPENDING_TX_TYPES


@pytest.mark.parametrize(
    ("wallet_codes", "tx_type", "expected"),
    [
        pytest.param(_DEMO_DAILY_WALLET, "travel", "muc_tieu", id="du-lich-vi-demo-vao-hu-goal"),
        pytest.param(_DEMO_DAILY_WALLET, "food_drink", "an_uong", id="an-uong-vi-demo"),
        pytest.param(_THREE_JAR_WALLET, "food_drink", "chi_hang_ngay", id="an-uong-vi-ba-hu"),
        pytest.param((*_THREE_JAR_WALLET, "an_uong"), "food_drink", "an_uong", id="an-uong-vi-ba-hu-them-an-uong"),
        pytest.param(_THREE_JAR_WALLET, "travel", "chi_hang_ngay", id="du-lich-vi-ba-hu"),
        pytest.param(_THREE_JAR_WALLET, "bill_electricity", "nghia_vu", id="hoa-don-vao-nghia-vu"),
        pytest.param(_THREE_JAR_WALLET, "subscription", "nghia_vu", id="thue-bao-vi-ba-hu"),
        pytest.param(_DEMO_DAILY_WALLET, "obligation_payment", "nghia_vu", id="tra-nghia-vu"),
        # loại không có hũ nhận (rơi về Chưa phân loại), loại lạ, không có loại, ví không có hũ nào nhận
        pytest.param(_DEMO_DAILY_WALLET, "transfer_person", None, id="chuyen-cho-nguoi-khac"),
        pytest.param(_DEMO_DAILY_WALLET, "other_expense", None, id="chi-tieu-khac"),
        pytest.param(_DEMO_DAILY_WALLET, "salary", None, id="tien-vao-khong-phai-loai-chi"),
        pytest.param(_DEMO_DAILY_WALLET, None, None, id="khong-co-loai"),
        pytest.param(("du_phong", "dau_tu"), "travel", None, id="vi-khong-co-hu-nhan"),
    ],
)  # fmt: skip
def test_hu_cua_khoan_chi_theo_loai_cung_quy_tac_phan_loai(wallet_codes, tx_type, expected):
    assert wallet.spending_tx_type_jar(tx_type, wallet_codes) == expected
    if expected is not None:
        default = next(jar for code, _, jar in wallet.SPENDING_TX_TYPES if code == tx_type)
        assert expected == wallet.transaction_jar(default, wallet_codes, tx_type=tx_type)


def test_hu_cua_khoan_chi_khong_bao_gio_la_hu_he_thong():
    system = tuple(wallet.SYSTEM_JAR_CODES.values())
    assert wallet.spending_tx_type_jar("transfer_person", (*_DEMO_DAILY_WALLET, *system)) is None
    assert wallet.spending_tx_type_jar("food_drink", system) is None


@pytest.mark.parametrize(
    ("default", "tx_type", "chain"),
    [
        ("an_uong", "grocery", ("an_uong", "chi_hang_ngay")),
        ("du_lich", "travel", ("du_lich", "muc_tieu", "chi_hang_ngay")),
        ("hoa_don", "bill_electricity", ("hoa_don", "nghia_vu")),
        ("giai_tri", "subscription", ("giai_tri", "nghia_vu")),
        ("nghia_vu", "obligation_payment", ("nghia_vu",)),
        (None, "transfer_person", ()),
    ],
)
def test_chuoi_hu_cua_loai_giao_dich_hu_rieng_truoc_hu_chung_sau(default, tx_type, chain):
    """Mọi hũ "của" một loại theo thứ tự `transaction_jar` chọn (#39): `transaction_jar` là hũ đầu tiên của chuỗi mà ví có."""
    assert wallet.transaction_jar_chain(default, tx_type=tx_type) == chain
    for wallet_codes in (_DEMO_WALLET, _DEMO_DAILY_WALLET, _THREE_JAR_WALLET):
        expected = next((code for code in chain if code in wallet_codes), None)
        assert wallet.transaction_jar(default, wallet_codes, tx_type=tx_type) == expected
