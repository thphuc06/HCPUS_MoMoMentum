"""Chuẩn hóa `params` của từng tool ghi (contracts/README.md, "Chuẩn hóa tham số"): tất định, idempotent, điền mặc định
phụ thuộc trạng thái chỉ khi có `NormContext`, và bản đã chuẩn hóa băm ra cùng một giá trị."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from yofina_core.confirm import ParamsError, hash_normalized_params, params_hash
from yofina_core.params import (
    NormContext,
    TxTypeInfo,
    compute_dedupe_key,
    fold_text,
    normalize_params,
    slugify_jar_code,
    unique_jar_code,
)

TODAY = date(2026, 11, 21)
TX_TYPES = {
    "food_drink": TxTypeInfo("food_drink", "out", "an_uong", None, "Ăn uống"),
    "ride_hailing": TxTypeInfo("ride_hailing", "out", "di_lai", None, "Gọi xe"),
    "other_expense": TxTypeInfo("other_expense", "out", None, "unclassified", "Chi khác"),
    "transfer_person": TxTypeInfo("transfer_person", "out", None, "unclassified", "Chuyển tiền"),
    "obligation_payment": TxTypeInfo("obligation_payment", "out", "nghia_vu", None, "Trả nghĩa vụ"),
    "salary": TxTypeInfo("salary", "in", None, "other_income", "Lương"),
    "income_other": TxTypeInfo("income_other", "in", None, "other_income", "Tiền vào khác"),
    "jar_transfer": TxTypeInfo("jar_transfer", "internal", None, None, "Chuyển hũ", False),
}
CTX = NormContext(
    today=TODAY,
    tx_types=TX_TYPES,
    jar_codes=frozenset(
        {"an_uong", "di_lai", "nghia_vu", "hoa_don", "tien_vao_khac", "chua_phan_loai"}
    ),
    obligation_jar="nghia_vu",
)
UUID1 = "6f1e2d3c-4b5a-4968-8777-665544332211"


def norm(tool, params, ctx=CTX):
    return normalize_params(tool, params, ctx)


def idempotent(tool, params, ctx=CTX):
    once = normalize_params(tool, params, ctx)
    assert normalize_params(tool, once, ctx) == once
    # chuẩn hóa lại KHÔNG cần ngữ cảnh vẫn không đổi (ConfirmService.issue/verify làm vậy)
    assert normalize_params(tool, once) == once
    assert params_hash(tool, once) == hash_normalized_params(tool, once)
    return once


# --- record_transaction -----------------------------------------------------------------------------
def test_chi_bo_tham_so_la_dien_mac_dinh_va_suy_hu_tu_loai():
    out = idempotent(
        "record_transaction",
        {
            "kind": "Expense",
            "amount_vnd": "200000",
            "tx_type": " Food_Drink ",
            "user_id": "x",
            "confirm_token": "a.b",
            "evil": 1,
        },
    )
    assert out == {
        "kind": "expense",
        "amount_vnd": 200000,
        "funding": "jar",
        "tx_type": "food_drink",
        "jar": "an_uong",
    }


def test_chi_khong_chon_hu_va_loai_khong_co_hu_chuan_thi_chua_phan_loai():
    assert (
        norm("record_transaction", {"kind": "expense", "amount_vnd": 5000})["jar"]
        == "chua_phan_loai"
    )  # other_expense
    assert (
        norm(
            "record_transaction",
            {"kind": "expense", "amount_vnd": 5000, "tx_type": "transfer_person"},
        )["jar"]
        == "chua_phan_loai"
    )


def test_loai_co_hu_chuan_nhung_nguoi_dung_khong_co_hu_do_thi_roi_ve_chua_phan_loai():
    ctx = NormContext(
        today=TODAY, tx_types=TX_TYPES, jar_codes=frozenset({"di_lai", "chua_phan_loai"})
    )
    assert (
        norm(
            "record_transaction",
            {"kind": "expense", "amount_vnd": 5000, "tx_type": "food_drink"},
            ctx,
        )["jar"]
        == "chua_phan_loai"
    )


def test_hu_nguoi_dung_chon_duoc_giu_nguyen_ke_ca_khi_khac_hu_chuan():
    out = idempotent(
        "record_transaction",
        {"kind": "expense", "amount_vnd": 5000, "tx_type": "food_drink", "jar": " DI_LAI "},
    )
    assert out["jar"] == "di_lai"


def test_tien_vao_luon_vao_tien_vao_khac_va_mac_dinh_income_other():
    out = idempotent(
        "record_transaction", {"kind": "income", "amount_vnd": 9_000_000, "jar": "an_uong"}
    )
    assert out == {
        "kind": "income",
        "amount_vnd": 9_000_000,
        "funding": "jar",
        "tx_type": "income_other",
        "jar": "tien_vao_khac",
    }
    assert (
        norm("record_transaction", {"kind": "income", "amount_vnd": 1, "tx_type": "salary"})[
            "tx_type"
        ]
        == "salary"
    )


def test_tra_nghia_vu_mac_dinh_loai_obligation_payment():
    out = idempotent(
        "record_transaction", {"kind": "expense", "amount_vnd": 1, "obligation_id": UUID1.upper()}
    )
    assert (
        out["obligation_id"] == UUID1
        and out["tx_type"] == "obligation_payment"
        and out["jar"] == "nghia_vu"
    )


def test_chuoi_cat_khoang_trang_va_chuoi_rong_la_vang():
    out = idempotent(
        "record_transaction",
        {
            "kind": "expense",
            "amount_vnd": 1,
            "jar": "an_uong",
            "note": "  ",
            "counterparty": "  Cơm tấm  ",
            "payee_id": None,
            "client_ref": " ref-1 ",
        },
    )
    assert (
        out["counterparty"] == "Cơm tấm"
        and "note" not in out
        and "payee_id" not in out
        and out["client_ref"] == "ref-1"
    )


@pytest.mark.parametrize(
    "params",
    [
        {"amount_vnd": 1},  # thiếu kind
        {"kind": "transfer", "amount_vnd": 1},
        {"kind": "expense"},
        {"kind": "expense", "amount_vnd": 0},
        {"kind": "expense", "amount_vnd": -5},
        {"kind": "expense", "amount_vnd": 1.5},
        {"kind": "expense", "amount_vnd": 10.0},  # float bị từ chối
        {"kind": "expense", "amount_vnd": True},
        {"kind": "income", "amount_vnd": 1, "funding": "credit"},
        {"kind": "income", "amount_vnd": 1, "obligation_id": UUID1},
        {"kind": "expense", "amount_vnd": 1, "funding": "credit", "obligation_id": UUID1},
        {"kind": "expense", "amount_vnd": 1, "funding": "ngan_hang"},
        {"kind": "expense", "amount_vnd": 1, "tx_type": "salary"},  # sai hướng
        {"kind": "income", "amount_vnd": 1, "tx_type": "food_drink"},
        {"kind": "expense", "amount_vnd": 1, "tx_type": "jar_transfer"},  # loại nội bộ
        {"kind": "expense", "amount_vnd": 1, "tx_type": "khong_co"},
        {"kind": "expense", "amount_vnd": 1, "tx_type": "Bad Type!"},
        {"kind": "expense", "amount_vnd": 1, "payee_id": "abc"},
        {"kind": "expense", "amount_vnd": 1, "client_ref": "co dau cach"},
        {"kind": "expense", "amount_vnd": 1, "client_ref": "x" * 65},
        {"kind": "expense", "amount_vnd": 1, "note": "x" * 201},
        {"kind": "expense", "amount_vnd": 1, "counterparty": "x" * 121},
        {"kind": "expense", "amount_vnd": 1, "jar": "Ăn uống"},
        {"kind": "expense", "amount_vnd": 10**14},
    ],
)
def test_record_transaction_tham_so_sai_bi_tu_choi(params):
    with pytest.raises(ParamsError):
        norm("record_transaction", params)


def test_khong_co_ngu_canh_thi_khong_doan_hu():
    out = normalize_params("record_transaction", {"kind": "expense", "amount_vnd": 5000}, None)
    assert "jar" not in out and out["tx_type"] == "other_expense"


# --- assign_jar, confirm_salary --------------------------------------------------------------------
def test_assign_jar_mac_dinh_once_va_idempotent():
    out = idempotent("assign_jar", {"transaction_id": UUID1, "jar": "An_Uong"})
    assert out == {"transaction_id": UUID1, "jar": "an_uong", "remember": "once"}
    assert (
        norm("assign_jar", {"transaction_id": UUID1, "jar": "an_uong", "remember": "ALWAYS"})[
            "remember"
        ]
        == "always"
    )


@pytest.mark.parametrize(
    "params",
    [
        {"jar": "an_uong"},
        {"transaction_id": "khong-phai-uuid", "jar": "an_uong"},
        {"transaction_id": UUID1, "jar": "an_uong", "remember": "forever"},
    ],
)
def test_assign_jar_sai(params):
    with pytest.raises(ParamsError):
        norm("assign_jar", params)


def test_confirm_salary_ep_false_khi_giu_o_tien_vao_khac():
    a = idempotent(
        "confirm_salary",
        {"salary_event_id": UUID1, "decision": "split", "update_declared_salary": True},
    )
    assert a["update_declared_salary"] is True
    b = idempotent(
        "confirm_salary",
        {"salary_event_id": UUID1, "decision": "keep_as_other", "update_declared_salary": True},
    )
    assert b["update_declared_salary"] is False
    assert (
        idempotent("confirm_salary", {"salary_event_id": UUID1, "decision": "split"})[
            "update_declared_salary"
        ]
        is False
    )
    with pytest.raises(ParamsError):
        norm(
            "confirm_salary",
            {"salary_event_id": UUID1, "decision": "split", "update_declared_salary": "yes"},
        )
    with pytest.raises(ParamsError):
        norm("confirm_salary", {"salary_event_id": UUID1, "decision": "maybe"})


# --- update_profile ---------------------------------------------------------------------------------
def test_update_profile_chi_giu_truong_co_mat():
    out = idempotent(
        "update_profile",
        {
            "monthly_salary_vnd": "12000000",
            "payday_day": 10,
            "display_name": " Hà ",
            "risk_tolerance": "HIGH",
        },
    )
    assert out == {
        "monthly_salary_vnd": 12_000_000,
        "payday_day": 10,
        "display_name": "Hà",
        "risk_tolerance": "high",
    }
    with pytest.raises(ParamsError):
        norm("update_profile", {})
    with pytest.raises(ParamsError):
        norm("update_profile", {"user_id": "x"})
    for bad in (
        {"payday_day": 0},
        {"payday_day": 32},
        {"payday_day": True},
        {"monthly_salary_vnd": 0},
        {"risk_tolerance": "mid"},
    ):
        with pytest.raises(ParamsError):
            norm("update_profile", bad)


def test_obligation_moi_dien_mac_dinh_hu_obligation_dau_tien_va_han_tu_due_day():
    out = idempotent(
        "update_profile",
        {
            "obligation": {
                "op": "upsert",
                "kind": "rent",
                "name": "Tiền trọ",
                "amount_vnd": 2_500_000,
                "due_day": 1,
            }
        },
    )
    ob = out["obligation"]
    assert ob == {
        "op": "upsert", "kind": "rent", "name": "Tiền trọ", "amount_vnd": 2_500_000, "due_day": 1, "cycle": "monthly",
        "fee_vnd": 0, "is_essential": False, "pay_jar": "nghia_vu", "due_date": "2026-12-01",
    }  # fmt: skip


def test_due_day_hom_nay_thi_lay_hom_nay_con_da_qua_thi_thang_sau():
    def due(day):
        ob = {"op": "upsert", "kind": "bill", "name": "x", "amount_vnd": 1, "due_day": day}
        return norm("update_profile", {"obligation": ob})["obligation"]["due_date"]

    assert due(21) == "2026-11-21" and due(20) == "2026-12-20" and due(31) == "2026-11-30"


def test_obligation_khoang_so_tien_lay_trung_diem_lam_tron_xuong():
    ob = idempotent(
        "update_profile",
        {
            "obligation": {
                "op": "upsert",
                "kind": "bill",
                "name": "Điện",
                "amount_min_vnd": 300_001,
                "amount_max_vnd": 450_000,
                "due_day": 26,
            }
        },
    )["obligation"]
    assert (
        ob["amount_vnd"] == 375_000
        and ob["amount_min_vnd"] == 300_001
        and ob["amount_max_vnd"] == 450_000
    )
    for bad in (
        {"amount_min_vnd": 5, "amount_max_vnd": 1},
        {"amount_min_vnd": 5},
        {"amount_min_vnd": 1, "amount_max_vnd": 9, "amount_vnd": 10},
    ):
        with pytest.raises(ParamsError):
            norm(
                "update_profile",
                {"obligation": {"op": "upsert", "kind": "bill", "name": "x", "due_day": 1, **bad}},
            )


def test_sua_nghia_vu_khong_dien_mac_dinh_de_khong_ghi_de():
    out = idempotent(
        "update_profile",
        {"obligation": {"op": "upsert", "obligation_id": UUID1, "amount_vnd": 79_000}},
    )
    assert out["obligation"] == {"op": "upsert", "obligation_id": UUID1, "amount_vnd": 79_000}
    out = idempotent(
        "update_profile", {"obligation": {"op": "delete", "obligation_id": UUID1, "name": "bo qua"}}
    )
    assert out["obligation"] == {"op": "delete", "obligation_id": UUID1}


@pytest.mark.parametrize(
    "ob",
    [
        {
            "op": "upsert",
            "kind": "bnpl",
            "name": "x",
            "amount_vnd": 1,
            "due_day": 5,
        },  # trả sau không khai được
        {"op": "upsert", "name": "x", "amount_vnd": 1, "due_day": 5},  # thiếu kind
        {"op": "upsert", "kind": "rent", "amount_vnd": 1, "due_day": 5},  # thiếu name
        {"op": "upsert", "kind": "rent", "name": "x", "due_day": 5},  # thiếu số tiền
        {"op": "upsert", "kind": "rent", "name": "x", "amount_vnd": 1},  # thiếu hạn
        {
            "op": "upsert",
            "kind": "rent",
            "name": "x",
            "amount_vnd": 1,
            "cycle": "once",
        },  # một lần cần due_date
        {"op": "delete"},
        {"op": "remove", "obligation_id": UUID1},
        {
            "op": "upsert",
            "kind": "rent",
            "name": "x",
            "amount_vnd": 1,
            "due_day": 5,
            "due_date": "21/11/2026",
        },
        {"op": "upsert", "kind": "rent", "name": "x" * 81, "amount_vnd": 1, "due_day": 5},
    ],
)
def test_obligation_sai(ob):
    with pytest.raises(ParamsError):
        norm("update_profile", {"obligation": ob})


def test_obligation_mot_lan_voi_due_date_va_chu_ky_thang_suy_due_day_tu_ngay():
    ob = norm(
        "update_profile",
        {
            "obligation": {
                "op": "upsert",
                "kind": "loan",
                "name": "Vay",
                "amount_vnd": 1,
                "due_date": "2026-12-15",
            }
        },
    )["obligation"]
    assert ob["due_day"] == 15 and ob["due_date"] == "2026-12-15"
    once = norm(
        "update_profile",
        {
            "obligation": {
                "op": "upsert",
                "kind": "loan",
                "name": "Vay",
                "amount_vnd": 1,
                "due_date": "2026-12-15",
                "cycle": "once",
            }
        },
    )["obligation"]
    assert "due_day" not in once


# --- save_jars --------------------------------------------------------------------------------------------
JARS = [
    {
        "name": "Ăn uống",
        "color_key": "violet",
        "icon_key": "utensils",
        "kind": "spending",
        "split_percent": "60.005",
    },
    {
        "name": "Du lịch",
        "color_key": "teal",
        "icon_key": "plane",
        "kind": "saving",
        "split_percent": Decimal("39.99"),
        "goal_vnd": 6_000_000,
        "goal_date": "2027-04-01",
    },
]


def test_save_jars_sinh_ma_tu_ten_lam_tron_ty_le_va_giu_thu_tu():
    out = idempotent("save_jars", {"jars": JARS}, NormContext(today=TODAY))
    assert [j["code"] for j in out["jars"]] == ["an_uong", "du_lich"]
    assert [j["split_percent"] for j in out["jars"]] == [60.01, 39.99]
    assert out["jars"][1]["goal_vnd"] == 6_000_000 and out["jars"][1]["goal_date"] == "2027-04-01"


def test_save_jars_ma_trung_them_hau_to_va_ma_he_thong_duoc_giu_cho():
    ctx = NormContext(today=TODAY, jar_codes=frozenset({"an_uong", "tien_vao_khac"}))
    jars = [
        {
            "name": "Ăn uống",
            "color_key": "violet",
            "icon_key": "u",
            "kind": "spending",
            "split_percent": 50,
        },
        {
            "name": "Tiền vào khác",
            "color_key": "gray",
            "icon_key": "u",
            "kind": "spending",
            "split_percent": 50,
        },
    ]
    out = normalize_params("save_jars", {"jars": jars}, ctx)
    assert [j["code"] for j in out["jars"]] == ["an_uong_2", "tien_vao_khac_2"]
    # đã có mã thì giữ nguyên: sửa hũ cũ không đổi mã
    jars[0]["code"] = "an_uong"
    out = normalize_params("save_jars", {"jars": jars}, ctx)
    assert out["jars"][0]["code"] == "an_uong"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda j: j[0].update(split_percent=10),  # tổng khác 100
        lambda j: j[1].update(code="an_uong") or j[0].update(code="an_uong"),  # mã trùng
        lambda j: j[0].update(code="tien_vao_khac"),  # mã của hũ hệ thống
        lambda j: j[0].update(kind="system"),
        lambda j: j[0].update(color_key="Mau Do"),
        lambda j: j[1].pop("goal_vnd"),  # goal_date không có goal_vnd
        lambda j: j[0].update(split_percent=-1),
        lambda j: j[0].update(name=""),
    ],
)
def test_save_jars_sai(mutate):
    jars = [dict(j) for j in JARS]
    jars[0]["split_percent"], jars[1]["split_percent"] = 60, 40
    mutate(jars)
    with pytest.raises(ParamsError):
        norm("save_jars", {"jars": jars})
    with pytest.raises(ParamsError):
        norm("save_jars", {"jars": []})
    with pytest.raises(ParamsError):
        norm("save_jars", {"jars": [{}] * 21})


def test_move_giu_nguyen_phase_1_va_cho_phep_tien_vao_khac_lam_nguon():
    out = norm(
        "move_between_jars",
        {"from_jar": "Tien_Vao_Khac", "to_jar": "an_uong", "amount_vnd": 350000},
    )
    assert out == {"from_jar": "tien_vao_khac", "to_jar": "an_uong", "amount_vnd": 350000}


def test_tool_la_bi_tu_choi():
    with pytest.raises(ParamsError):
        norm("drop_tables", {})


# --- hash ----------------------------------------------------------------------------------------------------
def test_hash_khong_phu_thuoc_thu_tu_khoa_va_khoa_la_nhung_phu_thuoc_gia_tri():
    a = norm("record_transaction", {"kind": "expense", "amount_vnd": 5, "jar": "an_uong"})
    b = norm(
        "record_transaction",
        {
            "jar": "an_uong",
            "amount_vnd": 5,
            "kind": "expense",
            "user_id": "u",
            "confirm_token": "t",
        },
    )
    assert hash_normalized_params("record_transaction", a) == hash_normalized_params(
        "record_transaction", b
    )
    c = norm("record_transaction", {"kind": "expense", "amount_vnd": 6, "jar": "an_uong"})
    assert hash_normalized_params("record_transaction", a) != hash_normalized_params(
        "record_transaction", c
    )
    assert hash_normalized_params("record_transaction", a) != hash_normalized_params(
        "assign_jar", a
    )


# --- tiện ích -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name,code",
    [
        ("Ăn uống", "an_uong"),
        ("Đi lại", "di_lai"),
        ("  Quỹ  Du-lịch 2027!! ", "quy_du_lich_2027"),
        ("2027", "hu_2027"),
        ("!!!", "hu"),
        ("a" * 50, "a" * 32),
    ],
)
def test_slugify_jar_code(name, code):
    assert slugify_jar_code(name) == code


def test_unique_jar_code_cat_de_vua_32_ky_tu():
    base = "a" * 32
    assert unique_jar_code("a" * 40, {base}) == "a" * 30 + "_2"
    assert unique_jar_code("a" * 40, {base, "a" * 30 + "_2"}) == "a" * 30 + "_3"


def test_khoa_khu_trung_theo_cong_thuc_hop_dong():
    import hashlib

    k = compute_dedupe_key(
        app_date=date(2026, 11, 21),
        amount_vnd=-200_000,
        payee_id=None,
        counterparty="  Cơm TẤM  Cô Ba ",
        client_ref="r1",
    )
    assert k == hashlib.sha256(b"2026-11-21|200000|com tam co ba|r1").hexdigest()
    assert fold_text(" Đỗ   Hoàng ") == "do hoang"
    p = compute_dedupe_key(
        app_date="2026-11-21", amount_vnd=200_000, payee_id=UUID1, counterparty="x", client_ref="r1"
    )
    assert p == hashlib.sha256(f"2026-11-21|200000|{UUID1}|r1".encode()).hexdigest()
    assert k != compute_dedupe_key(
        app_date=date(2026, 11, 22),
        amount_vnd=200_000,
        payee_id=None,
        counterparty="Cơm tấm Cô Ba",
        client_ref="r1",
    )
