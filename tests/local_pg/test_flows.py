"""Luồng nghiệp vụ của ví trên Postgres thật (SQL thật, RLS thật), qua `LedgerService` thật.

Mọi khối trả về được kiểm bằng model Pydantic của hợp đồng (`parse_block`), mọi sự kiện bằng JSON Schema của `contracts/events`.
Con số kỳ vọng suy từ dữ liệu trong DB (bảng `fee_schedules`, persona) chứ không gắn cứng phí trong mã sản phẩm.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from conftest import REPO

from yofina_core.blocks import block_to_wire, parse_block
from yofina_core.errors import ErrorCode, YofinaError

MINH, LAN, KHOA = "sub-minh", "sub-lan", "sub-khoa"


def _unit_conftest():
    spec = importlib.util.spec_from_file_location("unit_conftest", REPO / "tests/unit/conftest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def schema():
    from jsonschema import Draft202012Validator

    uc = _unit_conftest()
    reg = uc.build_registry()

    def check(ref: str, instance):
        v = Draft202012Validator({"$ref": f"{uc.BASE}/{ref}"}, registry=reg)
        errors = [f"{list(e.path)}: {e.message}" for e in v.iter_errors(instance)]
        assert not errors, errors

    return check


def balances(env, user):
    return {j["code"]: j["balance_vnd"] for j in env.svc.overview_response(user)["jars"]}


def sys_balances(env, user):
    return {j["code"]: j["balance_vnd"] for j in env.svc.overview_response(user)["system_jars"]}


def fee_from_table(env) -> int:
    with env.master() as c:
        return int(
            c.execute(
                "select amount_vnd from fee_schedules where product_code='bnpl_sim'"
            ).fetchone()[0]
        )


def check_events(env, schema):
    for e in env.events.sent:
        schema(f"events/{e.detail_type}.schema.json", e.detail)


# --- chi tiêu ---------------------------------------------------------------------------------------
def test_chi_200k_tu_an_uong_doi_so_du_ngay_va_phat_su_kien(env, schema):
    env.reset(MINH)
    env.events.sent.clear()
    r = env.act(
        MINH,
        "record_transaction",
        {
            "kind": "expense",
            "amount_vnd": 200_000,
            "jar": "an_uong",
            "tx_type": "food_drink",
            "counterparty": "Cơm tấm Cô Ba",
        },
    )
    block = parse_block(r)
    assert block.type == "receipt_action" and block.data.amount_vnd == 200_000
    assert block.data.jars_after[0].balance_after_vnd == 180_000
    assert balances(env, MINH)["an_uong"] == 180_000
    assert [e.detail_type for e in env.events.sent] == ["transaction.recorded"]
    d = env.events.sent[0].detail
    assert d["effects"] == [
        {"jar_code": "an_uong", "delta_vnd": -200_000, "balance_after_vnd": 180_000}
    ]
    check_events(env, schema)
    # sổ cái: dòng chi đúng loại, nguồn trả bằng hũ
    page = env.svc.transactions_response(MINH, limit=1)
    t = page["transactions"][0]
    assert (
        t["amount_vnd"] == -200_000
        and t["tx_type"] == "food_drink"
        and t["funding_source"] == "jar"
    )
    schema("tools/ledger.results.schema.json#/$defs/Transaction", t)


def test_chi_vuot_so_du_bi_tu_choi_khong_ghi_gi(env):
    env.reset(MINH)
    with pytest.raises(YofinaError) as e:
        env.act(
            MINH, "record_transaction", {"kind": "expense", "amount_vnd": 400_000, "jar": "an_uong"}
        )
    assert e.value.code == ErrorCode.INSUFFICIENT_FUNDS
    assert balances(env, MINH)["an_uong"] == 380_000


def test_chi_khong_chon_hu_thi_theo_loai_giao_dich_hoac_chua_phan_loai(env):
    env.reset(MINH)
    r = env.act(
        MINH,
        "record_transaction",
        {"kind": "expense", "amount_vnd": 50_000, "tx_type": "ride_hailing"},
    )
    assert parse_block(r).data.jars_after[0].code == "di_lai"
    r = env.act(MINH, "record_transaction", {"kind": "expense", "amount_vnd": 30_000})
    jar = parse_block(r).data.jars_after[0]
    assert jar.code == "chua_phan_loai" and jar.balance_after_vnd == -210_000
    assert parse_block(r).data.follow_up.kind == "review_unclassified"
    assert sys_balances(env, MINH)["chua_phan_loai"] == -210_000


def test_gui_trung_client_ref_khong_ghi_hai_lan(env):
    env.reset(MINH)
    p = {
        "kind": "expense",
        "amount_vnd": 20_000,
        "jar": "di_lai",
        "tx_type": "public_transport",
        "counterparty": "Xe buýt",
        "client_ref": "ref-001",
    }
    env.act(MINH, "record_transaction", p)
    with pytest.raises(YofinaError) as e:
        env.act(MINH, "record_transaction", p)
    assert e.value.code == ErrorCode.DUPLICATE_TRANSACTION
    assert balances(env, MINH)["di_lai"] == 620_000  # chỉ trừ một lần
    # hai khoản giống hệt NHƯNG không client_ref thì hợp lệ
    q = {k: v for k, v in p.items() if k != "client_ref"}
    env.act(MINH, "record_transaction", q)
    env.act(MINH, "record_transaction", q)
    assert balances(env, MINH)["di_lai"] == 580_000


# --- Trả sau (mô phỏng) ----------------------------------------------------------------------------------
def test_mua_300k_bang_tra_sau_sinh_nghia_vu_gom_phi_tu_bang_va_han_ngay_5(env, schema):
    env.reset(LAN)
    fee = fee_from_table(env)
    before = balances(env, LAN)
    env.events.sent.clear()
    r = env.act(
        LAN,
        "record_transaction",
        {
            "kind": "expense",
            "amount_vnd": 300_000,
            "jar": "giai_tri",
            "tx_type": "entertainment",
            "funding": "credit",
            "counterparty": "Tiki",
        },
    )
    block = parse_block(r)
    assert block.data.jars_after == []  # trả sau không đổi số dư hũ
    assert balances(env, LAN) == before
    obs = env.svc.obligations_response(LAN)["obligations"]
    bnpl = [o for o in obs if o["kind"] == "bnpl"]
    assert len(bnpl) == 1
    o = bnpl[0]
    assert (
        o["amount_vnd"] == 300_000 + fee == 333_000
        and o["principal_vnd"] == 300_000
        and o["fee_vnd"] == fee
    )
    assert o["due_date"] == "2026-12-05" and o["status"] == "active" and o["source"] == "bnpl_auto"
    schema("tools/ledger.results.schema.json#/$defs/Obligation", o)
    line = env.svc.credit_line_response(LAN)["credit_line"]
    assert line["outstanding_vnd"] == 300_000 and line["available_vnd"] == 1_700_000
    assert line["product_label"] == "Trả sau (mô phỏng)"
    assert [e.detail_type for e in env.events.sent] == [
        "transaction.recorded",
        "obligation.changed",
    ]
    assert (
        env.events.sent[0].detail["effects"] == []
        and env.events.sent[1].detail["change"] == "created"
    )
    check_events(env, schema)
    # mua thêm cộng dồn vào cùng nghĩa vụ, phí không tính lại
    env.act(
        LAN,
        "record_transaction",
        {"kind": "expense", "amount_vnd": 100_000, "jar": "giai_tri", "funding": "credit"},
    )
    o2 = next(x for x in env.svc.obligations_response(LAN)["obligations"] if x["kind"] == "bnpl")
    assert o2["amount_vnd"] == 400_000 + fee and o2["principal_vnd"] == 400_000
    assert env.events.sent[-1].detail["change"] == "updated"


def test_minh_co_san_khoan_tra_sau_nen_mua_them_thi_cong_don(env):
    env.reset(MINH)
    fee = fee_from_table(env)
    start = next(
        o for o in env.svc.obligations_response(MINH)["obligations"] if o["kind"] == "bnpl"
    )
    assert (
        start["amount_vnd"] == 1_000_000 == start["principal_vnd"] + fee
    )  # khớp hũ Nghĩa vụ giữ sẵn 1.000.000
    env.act(
        MINH,
        "record_transaction",
        {"kind": "expense", "amount_vnd": 300_000, "jar": "giai_tri", "funding": "credit"},
    )
    now = next(o for o in env.svc.obligations_response(MINH)["obligations"] if o["kind"] == "bnpl")
    assert now["amount_vnd"] == 1_300_000 and now["due_date"] == start["due_date"] == "2026-12-05"


def test_vuot_han_muc_tra_sau(env):
    env.reset(LAN)
    with pytest.raises(YofinaError) as e:
        env.act(
            LAN,
            "record_transaction",
            {"kind": "expense", "amount_vnd": 2_100_000, "jar": "giai_tri", "funding": "credit"},
        )
    assert e.value.code == ErrorCode.CREDIT_LIMIT_EXCEEDED


def test_tra_nghia_vu_tra_sau_giam_du_no_goc_va_xong(env):
    env.reset(MINH)
    ob = next(o for o in env.svc.obligations_response(MINH)["obligations"] if o["kind"] == "bnpl")
    r = env.act(
        MINH,
        "record_transaction",
        {"kind": "expense", "amount_vnd": 1_000_000, "jar": "nghia_vu", "obligation_id": ob["id"]},
    )
    assert parse_block(r).data.jars_after[0].balance_after_vnd == 0
    assert balances(env, MINH)["nghia_vu"] == 0
    paid = env.svc.obligations_response(MINH, status="paid")["obligations"]
    assert [o["id"] for o in paid] == [ob["id"]]
    assert env.svc.credit_line_response(MINH)["credit_line"]["outstanding_vnd"] == 0
    assert env.events.sent[-1].detail["change"] == "paid"


def test_tra_nghia_vu_dinh_ky_doi_han(env):
    env.reset(MINH)
    env.act(
        MINH,
        "move_between_jars",
        {"from_jar": "du_phong", "to_jar": "hoa_don", "amount_vnd": 1_600_000},
    )
    rent = next(
        o
        for o in env.svc.obligations_response(MINH)["obligations"]
        if o["name"] == "Tiền thuê phòng"
    )
    env.act(
        MINH,
        "record_transaction",
        {"kind": "expense", "amount_vnd": 2_000_000, "jar": "hoa_don", "obligation_id": rent["id"]},
    )
    after = next(
        o for o in env.svc.obligations_response(MINH)["obligations"] if o["id"] == rent["id"]
    )
    assert after["status"] == "active" and after["due_date"] == "2027-01-06"


# --- lương ---------------------------------------------------------------------------------------------
def test_luong_ve_la_hai_buoc_nhan_roi_xac_nhan_chia_dung_luat(env, schema):
    from datetime import timedelta

    env.reset(MINH)
    env.clock.now += timedelta(days=14)  # ngày mô phỏng 5/12: lương kỳ mới về
    before = balances(env, MINH)
    env.events.sent.clear()
    r = env.act(
        MINH, "record_transaction", {"kind": "income", "amount_vnd": 9_000_000, "tx_type": "salary"}
    )
    fu = parse_block(r).data.follow_up
    assert (
        fu.kind == "confirm_salary" and fu.ask_update_salary is False and fu.deviation_percent == 0
    )
    assert sys_balances(env, MINH)["tien_vao_khac"] == 9_350_000
    assert balances(env, MINH) == before  # chưa chia
    ev = env.svc.salary_events_response(MINH)["salary_events"]
    assert len(ev) == 1 and ev[0]["status"] == "pending" and ev[0]["id"] == fu.salary_event_id
    ov = env.svc.overview_response(MINH)
    assert (
        ov["next_payday"]["state"] == "pending_confirmation"
        and ov["next_payday"]["salary_event_id"] == fu.salary_event_id
    )
    assert ov["proactive_card"]["data"]["kind"] == "salary_pending"

    env.events.sent.clear()
    r2 = env.act(
        MINH, "confirm_salary", {"salary_event_id": fu.salary_event_id, "decision": "split"}
    )
    assert parse_block(r2).type == "receipt_action"
    after = balances(env, MINH)
    shares = {
        "hoa_don": 2_790_000,
        "an_uong": 2_700_000,
        "di_lai": 630_000,
        "giai_tri": 630_000,
        "du_lich": 900_000,
        "du_phong": 900_000,
        "nghia_vu": 450_000,
    }
    for code, part in shares.items():
        assert after[code] == before[code] + part
    assert sys_balances(env, MINH)["tien_vao_khac"] == 350_000  # tiền vào khác ban đầu còn nguyên
    assert env.svc.salary_events_response(MINH)["salary_events"] == []
    assert [e.detail_type for e in env.events.sent] == ["salary.confirmed", "transaction.recorded"]
    assert env.events.sent[1].detail["event_id"] == env.events.sent[1].detail["transaction_id"]
    check_events(env, schema)
    with pytest.raises(YofinaError) as e:  # xác nhận lần hai
        env.act(
            MINH, "confirm_salary", {"salary_event_id": fu.salary_event_id, "decision": "split"}
        )
    assert e.value.code == ErrorCode.ALREADY_APPLIED
    # tổng số dư bảo toàn tiền
    assert env.svc.overview_response(MINH)["balance"]["total_vnd"] == 7_900_000 + 9_000_000


def test_luong_lech_nhieu_thi_hoi_cap_nhat_luong_va_cap_nhat_duoc(env):
    env.reset(MINH)
    r = env.act(
        MINH,
        "record_transaction",
        {"kind": "income", "amount_vnd": 10_500_000, "tx_type": "salary"},
    )
    fu = parse_block(r).data.follow_up
    assert fu.ask_update_salary is True and fu.deviation_percent == pytest.approx(16.67)
    env.act(
        MINH,
        "confirm_salary",
        {
            "salary_event_id": fu.salary_event_id,
            "decision": "split",
            "update_declared_salary": True,
        },
    )
    assert env.svc.profile_response(MINH)["profile"]["monthly_salary_vnd"] == 10_500_000
    assert sum(balances(env, MINH).values()) == 7_730_000 + 10_500_000


def test_giu_luong_o_tien_vao_khac_khong_chia(env):
    env.reset(MINH)
    r = env.act(
        MINH, "record_transaction", {"kind": "income", "amount_vnd": 9_000_000, "tx_type": "salary"}
    )
    eid = parse_block(r).data.follow_up.salary_event_id
    env.act(MINH, "confirm_salary", {"salary_event_id": eid, "decision": "keep_as_other"})
    assert sys_balances(env, MINH)["tien_vao_khac"] == 9_350_000
    assert (
        env.svc.salary_events_response(MINH, status="kept_other")["salary_events"][0]["id"] == eid
    )


def test_tien_vao_khac_luong_khong_tinh_thu_nhap_va_gan_vao_hu_bang_assign(env):
    env.reset(MINH)
    env.act(
        MINH,
        "record_transaction",
        {"kind": "income", "amount_vnd": 500_000, "tx_type": "friend_repay", "counterparty": "Huy"},
    )
    cf = env.svc.cashflow_result(MINH)["data"]
    # trong kỳ lương hiện tại (từ 5/11): lương 9.000.000 của persona là thu nhập; tiền vào khác (350.000 + 500.000) thì không
    assert cf["salary_income_vnd"] == 9_000_000 and cf["other_income_vnd"] == 850_000
    tx = env.svc.transactions_response(MINH, kind="income", limit=1)["transactions"][0]
    r = env.act(MINH, "assign_jar", {"transaction_id": tx["id"], "jar": "du_lich"})
    assert parse_block(r).type == "receipt_action"
    assert sys_balances(env, MINH)["tien_vao_khac"] == 350_000
    assert balances(env, MINH)["du_lich"] == 2_300_000
    # gán Tiền vào khác bằng chuyển hũ cũng được
    env.act(
        MINH,
        "move_between_jars",
        {"from_jar": "tien_vao_khac", "to_jar": "an_uong", "amount_vnd": 350_000},
    )
    assert (
        sys_balances(env, MINH)["tien_vao_khac"] == 0 and balances(env, MINH)["an_uong"] == 730_000
    )


# --- gán hũ cho khoản chưa phân loại ---------------------------------------------------------------------
def test_assign_jar_chuyen_khoan_chi_chua_phan_loai_ve_hu_that(env):
    env.reset(MINH)
    items = env.svc.unclassified_result(MINH)["data"]["items"]
    assert (
        len(items) == 2
        and env.svc.unclassified_result(MINH)["data"]["pending_total_vnd"] == 180_000
    )
    qr = next(i for i in items if i["transaction"]["tx_type"] == "qr_other")
    assert qr["transaction"]["amount_vnd"] == -120_000
    env.act(
        MINH,
        "assign_jar",
        {"transaction_id": qr["transaction"]["id"], "jar": "an_uong", "remember": "always"},
    )
    assert sys_balances(env, MINH)["chua_phan_loai"] == -60_000
    assert balances(env, MINH)["an_uong"] == 260_000
    with env.master() as c:
        rule = c.execute("select match_type, scope, jar_code from category_rules").fetchall()
    assert rule == [("merchant", "always", "an_uong")]
    assert env.svc.unclassified_result(MINH)["data"]["count"] == 1


def test_assign_jar_hu_dich_thieu_tien_bi_tu_choi(env):
    env.reset(MINH)
    env.act(
        MINH,
        "move_between_jars",
        {"from_jar": "an_uong", "to_jar": "du_phong", "amount_vnd": 380_000},
    )
    qr = next(
        i
        for i in env.svc.unclassified_result(MINH)["data"]["items"]
        if i["transaction"]["tx_type"] == "qr_other"
    )
    with pytest.raises(YofinaError) as e:
        env.act(MINH, "assign_jar", {"transaction_id": qr["transaction"]["id"], "jar": "an_uong"})
    assert e.value.code == ErrorCode.INSUFFICIENT_FUNDS
    assert sys_balances(env, MINH)["chua_phan_loai"] == -180_000


# --- hồ sơ, onboarding, nghĩa vụ, hũ ---------------------------------------------------------------------
def test_onboarding_tai_khoan_trang_chi_voi_luong_va_ngay_nhan(env, schema):
    ov = env.svc.overview_response("sub-moi", name_hint="Hà")
    assert (
        ov["profile"] == {"display_name": "Hà", "onboarded": False}
        and ov["jars"] == []
        and ov["next_payday"] is None
    )
    assert ov["proactive_card"] is None and ov["credit_line"] is None
    r = env.act(
        "sub-moi",
        "update_profile",
        {"monthly_salary_vnd": 12_000_000, "payday_day": 15},
        name_hint="Hà",
    )
    assert parse_block(r).data.summary.startswith("Đã tạo hồ sơ")
    ov = env.svc.overview_response("sub-moi")
    assert ov["profile"]["onboarded"] and ov["profile"]["display_name"] == "Hà"
    assert len(ov["jars"]) == 6 and sum(j["split_percent"] for j in ov["jars"]) == 100
    assert [j["code"] for j in ov["system_jars"]] == ["tien_vao_khac", "chua_phan_loai"]
    assert ov["next_payday"]["date"] == "2026-12-15" and ov["credit_line"]["limit_vnd"] == 3_000_000
    assert ov["balance"]["total_vnd"] == 0
    assert [e.detail_type for e in env.events.sent][-1] == "profile.updated"
    assert env.events.sent[-1].detail["fields"] == ["onboarding", "salary", "payday"]


def test_onboarding_thieu_ngay_nhan_la_loi(env):
    with pytest.raises(YofinaError) as e:
        env.act("sub-moi-2", "update_profile", {"monthly_salary_vnd": 12_000_000})
    assert e.value.code == ErrorCode.PROFILE_INCOMPLETE


def test_khai_sua_xoa_mot_nghia_vu(env, schema):
    env.reset(KHOA)
    r = env.act(
        KHOA,
        "update_profile",
        {
            "obligation": {
                "op": "upsert",
                "kind": "subscription",
                "name": "Spotify",
                "amount_vnd": 59_000,
                "due_day": 25,
                "pay_jar": "giai_tri",
            }
        },
    )
    assert parse_block(r).data.summary == "Đã khai khoản Spotify"
    ob = next(
        o for o in env.svc.obligations_response(KHOA)["obligations"] if o["name"] == "Spotify"
    )
    assert (
        ob["due_date"] == "2026-11-25"
        and ob["cycle"] == "monthly"
        and ob["pay_jar"] == "giai_tri"
        and ob["fee_vnd"] == 0
    )
    env.act(
        KHOA,
        "update_profile",
        {"obligation": {"op": "upsert", "obligation_id": ob["id"], "amount_vnd": 79_000}},
    )
    ob2 = next(o for o in env.svc.obligations_response(KHOA)["obligations"] if o["id"] == ob["id"])
    assert ob2["amount_vnd"] == 79_000 and ob2["cycle"] == "monthly"
    env.act(KHOA, "update_profile", {"obligation": {"op": "delete", "obligation_id": ob["id"]}})
    assert all(o["id"] != ob["id"] for o in env.svc.obligations_response(KHOA)["obligations"])
    assert [
        e.detail["change"] for e in env.events.sent if e.detail_type == "obligation.changed"
    ] == ["created", "updated", "cancelled"]
    check_events(env, schema)


def test_khong_khai_duoc_khoan_tra_sau(env):
    env.reset(KHOA)
    with pytest.raises(YofinaError) as e:
        env.act(
            KHOA,
            "update_profile",
            {
                "obligation": {
                    "op": "upsert",
                    "kind": "bnpl",
                    "name": "x",
                    "amount_vnd": 1000,
                    "due_day": 5,
                }
            },
        )
    assert e.value.code == ErrorCode.PARAMS_INVALID


def test_save_jars_sua_ty_le_tao_hu_moi_va_bao_ve_hu_con_tien(env):
    env.reset(KHOA)
    cur = {j["code"]: j for j in env.svc.overview_response(KHOA)["jars"]}
    jars = [
        {
            "code": c,
            "name": j["name"],
            "color_key": j["color_key"],
            "icon_key": j["icon_key"],
            "kind": j["kind"],
            "split_percent": j["split_percent"],
        }
        for c, j in cur.items()
    ]
    jars[0]["split_percent"] = 25
    jars.append(
        {
            "name": "Học tiếng Anh",
            "color_key": "teal",
            "icon_key": "plane",
            "kind": "saving",
            "split_percent": 5,
            "goal_vnd": 3_000_000,
            "goal_date": "2027-06-01",
        }
    )
    r = env.act(KHOA, "save_jars", {"jars": jars})
    assert parse_block(r).data.summary.startswith("Đã lưu 6 hũ")
    after = {j["code"]: j for j in env.svc.overview_response(KHOA)["jars"]}
    assert (
        after["an_uong"]["split_percent"] == 25 and after["hoc_tieng_anh"]["goal_vnd"] == 3_000_000
    )
    assert after["hoc_tieng_anh"]["balance_vnd"] == 0
    # bỏ hũ còn tiền thì bị bảo vệ
    with pytest.raises(YofinaError) as e:
        env.act(
            KHOA,
            "save_jars",
            {
                "jars": [
                    *[j for j in jars if j.get("code") != "du_phong"][:-1],
                    {**jars[0], "split_percent": 25},
                ]
            },
        )
    assert e.value.code in (ErrorCode.JAR_PROTECTED, ErrorCode.PARAMS_INVALID)
    # tổng tỷ lệ khác 100 là lỗi tham số
    bad = [dict(j) for j in jars]
    bad[0]["split_percent"] = 50
    with pytest.raises(YofinaError) as e:
        env.act(KHOA, "save_jars", {"jars": bad})
    assert e.value.code == ErrorCode.PARAMS_INVALID


# --- cô lập người dùng ---------------------------------------------------------------------------------
def test_a_khong_doc_khong_ghi_duoc_du_lieu_cua_b(env):
    env.reset(MINH)
    env.reset(LAN)
    minh_tx = env.svc.transactions_response(MINH, limit=1)["transactions"][0]["id"]
    minh_ob = env.svc.obligations_response(MINH)["obligations"][0]["id"]
    minh_payee = env.svc.payees_response(MINH)["payees"][0]["id"]
    assert minh_payee not in {p["id"] for p in env.svc.payees_response(LAN)["payees"]}
    assert minh_tx not in {
        t["id"] for t in env.svc.transactions_response(LAN, limit=50)["transactions"]
    }
    with pytest.raises(YofinaError) as e:
        env.act(LAN, "assign_jar", {"transaction_id": minh_tx, "jar": "an_uong"})
    assert e.value.code == ErrorCode.TRANSACTION_NOT_FOUND
    with pytest.raises(YofinaError) as e:
        env.act(
            LAN,
            "record_transaction",
            {"kind": "expense", "amount_vnd": 10_000, "jar": "an_uong", "obligation_id": minh_ob},
        )
    assert e.value.code == ErrorCode.OBLIGATION_NOT_FOUND
    with pytest.raises(YofinaError) as e:
        env.act(
            LAN,
            "record_transaction",
            {"kind": "expense", "amount_vnd": 10_000, "jar": "an_uong", "payee_id": minh_payee},
        )
    assert e.value.code == ErrorCode.PAYEE_NOT_FOUND
    with pytest.raises(YofinaError) as e:
        env.act(LAN, "update_profile", {"obligation": {"op": "delete", "obligation_id": minh_ob}})
    assert e.value.code == ErrorCode.OBLIGATION_NOT_FOUND
    with pytest.raises(YofinaError):
        env.svc.jar_detail_response(LAN, "du_lich")  # Lan không có hũ Du lịch
    assert balances(env, MINH)["an_uong"] == 380_000


def test_chuyen_tien_cho_nguoi_nhan(env):
    env.reset(MINH)
    huy = next(p for p in env.svc.payees_response(MINH)["payees"] if p["name"] == "Trần Quang Huy")
    r = env.act(
        MINH,
        "record_transaction",
        {
            "kind": "expense",
            "amount_vnd": 250_000,
            "jar": "giai_tri",
            "tx_type": "transfer_person",
            "payee_id": huy["id"],
            "note": "Tiền điện nước chia đôi",
        },
    )
    assert parse_block(r).data.summary == "Đã chi 250.000 ₫ từ hũ Giải trí"
    t = env.svc.transactions_response(MINH, limit=1)["transactions"][0]
    assert (
        t["payee_name"] == "Trần Quang Huy"
        and t["merchant"] == "Trần Quang Huy"
        and t["note"] == "Tiền điện nước chia đôi"
    )
    assert next(p for p in env.svc.payees_response(MINH)["payees"] if p["id"] == huy["id"])[
        "last_used_at"
    ]


# --- đề nghị: hết hạn, hủy, đã thực hiện -----------------------------------------------------------------
def _save_confirm_block(env, user, conv, block):
    env.svc.save_turn_result(
        user,
        conversation_id=conv,
        trace_id="tr" + block["id"][-6:],
        user_text="x",
        assistant_text="y",
        blocks=[{"seq": 0, "block": block}],
    )


def _confirm_block_for(env, user, tool, params):
    from yofina_core.blocks import block_to_wire

    prep, block = env.svc.prepare_action(
        user, tool, params, trace_id="t" * 12, source_tool="ledger___" + tool
    )
    return prep, block_to_wire(block)


def test_de_nghi_het_han_bi_server_tu_choi(env):
    from datetime import timedelta

    env.reset(MINH)
    params = {"kind": "expense", "amount_vnd": 10_000, "jar": "di_lai"}
    prep, wire = _confirm_block_for(env, MINH, "record_transaction", params)
    _save_confirm_block(env, MINH, "conv-1", wire)
    env.clock.now += timedelta(seconds=env.svc.settings.offer_ttl_seconds + 5)
    with pytest.raises(YofinaError) as e:
        env.svc.issue_confirmation(
            MINH,
            tool="record_transaction",
            params=prep.norm,
            client_params_hash=None,
            trace_id="a" * 8,
            conversation_id="conv-1",
            confirm_block_id=wire["id"],
        )
    assert e.value.code == ErrorCode.OFFER_EXPIRED
    # token cấp bằng đường khác cũng không thực hiện được đề nghị đã hết hạn
    issued = env.svc.issue_confirmation(
        MINH, tool="record_transaction", params=prep.norm, client_params_hash=None, trace_id="a" * 8
    )
    with pytest.raises(YofinaError) as e:
        env.svc.apply_action(
            MINH,
            "record_transaction",
            prep.norm,
            issued.token,
            trace_id="a" * 8,
            channel="rest",
            source_tool="rest:POST /actions",
            conversation_id="conv-1",
            confirm_block_id=wire["id"],
        )
    assert e.value.code == ErrorCode.OFFER_EXPIRED
    assert balances(env, MINH)["di_lai"] == 640_000


def test_bam_khong_luu_o_server_va_de_nghi_da_huy_khong_thuc_hien_duoc(env):
    env.reset(MINH)
    params = {"kind": "expense", "amount_vnd": 10_000, "jar": "di_lai"}
    prep, wire = _confirm_block_for(env, MINH, "record_transaction", params)
    _save_confirm_block(env, MINH, "conv-2", wire)
    out = env.svc.cancel_offer(
        MINH, conversation_id="conv-2", confirm_block_id=wire["id"], trace_id="t" * 8
    )
    assert out["status"] == "cancelled" and out["block_id"] == wire["id"]
    again = env.svc.cancel_offer(
        MINH, conversation_id="conv-2", confirm_block_id=wire["id"], trace_id="t" * 8
    )
    assert again["status"] == "cancelled"
    turn = env.svc.conversation_response(MINH, "conv-2")["turns"][0]
    assert turn["resolutions"] == [
        {"block_id": wire["id"], "status": "cancelled", "resolved_at": out["resolved_at"]}
    ]
    with pytest.raises(YofinaError) as e:
        env.svc.issue_confirmation(
            MINH,
            tool="record_transaction",
            params=prep.norm,
            client_params_hash=None,
            trace_id="a" * 8,
            conversation_id="conv-2",
            confirm_block_id=wire["id"],
        )
    assert e.value.code == ErrorCode.ALREADY_APPLIED
    assert balances(env, MINH)["di_lai"] == 640_000
    # người khác không hủy được đề nghị của mình (không thấy khối)
    with pytest.raises(YofinaError):
        env.svc.cancel_offer(
            LAN, conversation_id="conv-2", confirm_block_id=wire["id"], trace_id="t" * 8
        )


def test_de_nghi_da_thuc_hien_thi_thuc_hien_lai_bi_chan_va_receipt_duoc_phat_lai(env):
    env.reset(MINH)
    params = {"kind": "expense", "amount_vnd": 10_000, "jar": "di_lai"}
    prep, wire = _confirm_block_for(env, MINH, "record_transaction", params)
    _save_confirm_block(env, MINH, "conv-3", wire)
    r = env.act(
        MINH, "record_transaction", prep.norm, conversation_id="conv-3", confirm_block_id=wire["id"]
    )
    turn = env.svc.conversation_response(MINH, "conv-3")["turns"][0]
    res = turn["resolutions"][0]
    assert res["status"] == "done" and res["receipt"] == r
    with pytest.raises(YofinaError) as e:
        env.act(
            MINH,
            "record_transaction",
            prep.norm,
            conversation_id="conv-3",
            confirm_block_id=wire["id"],
        )
    assert e.value.code == ErrorCode.ALREADY_APPLIED
    assert balances(env, MINH)["di_lai"] == 630_000
    with pytest.raises(YofinaError):  # hủy đề nghị đã thực hiện
        env.svc.cancel_offer(
            MINH, conversation_id="conv-3", confirm_block_id=wire["id"], trace_id="t" * 8
        )


# --- Gateway: tool ghi không token chỉ xem trước ------------------------------------------------------
def test_tool_ghi_khong_token_tra_needs_confirmation_khong_ghi(env, schema):
    from ledger_fakes import gateway_context

    from yofina_ledger.gateway_api import handle_gateway

    env.reset(MINH)
    res = handle_gateway(
        {
            "user_id": MINH,
            "kind": "expense",
            "amount_vnd": 90_000,
            "jar": "an_uong",
            "tx_type": "food_drink",
        },
        gateway_context("ledger___record_transaction"),
        env.svc,
    )
    assert res["status"] == "NEEDS_CONFIRMATION"
    schema("tools/ledger.results.schema.json#/$defs/RecordTransactionResult", res)
    assert balances(env, MINH)["an_uong"] == 380_000
    args = {
        "user_id": MINH,
        "kind": "expense",
        "amount_vnd": 90_000,
        "jar": "an_uong",
        "tx_type": "food_drink",
    }
    issued = env.svc.issue_confirmation(
        MINH,
        tool="record_transaction",
        params=res["data"]["params"],
        client_params_hash=res["data"]["params_hash"],
        trace_id="a" * 8,
    )
    ok = handle_gateway(
        {**args, "confirm_token": issued.token},
        gateway_context("ledger___record_transaction"),
        env.svc,
    )
    assert ok["status"] == "OK"
    schema("tools/ledger.results.schema.json#/$defs/RecordTransactionResult", ok)
    assert balances(env, MINH)["an_uong"] == 290_000


def test_cac_tool_doc_dung_hop_dong(env, schema):
    from ledger_fakes import gateway_context

    from yofina_ledger.gateway_api import handle_gateway

    env.reset(MINH)

    def call(tool, **kw):
        return handle_gateway({"user_id": MINH, **kw}, gateway_context("ledger___" + tool), env.svc)

    schema(
        "tools/ledger.results.schema.json#/$defs/GetCashflowSummaryResult",
        call("get_cashflow_summary"),
    )
    r = call("get_obligations")
    schema("tools/ledger.results.schema.json#/$defs/GetObligationsResult", r)
    assert r["data"]["credit_line"]["limit_vnd"] == 5_000_000 and r["data"]["total_due_vnd"] > 0
    schema(
        "tools/ledger.results.schema.json#/$defs/GetUnclassifiedResult", call("get_unclassified")
    )
    q = call("query_transactions", limit=5)
    schema("tools/ledger.results.schema.json#/$defs/QueryTransactionsResult", q)
    assert q["data"]["has_more"] is True and len(q["data"]["transactions"]) == 5
    nxt = call("query_transactions", limit=5, cursor=q["data"]["next_cursor"])
    ids = {t["id"] for t in q["data"]["transactions"]} & {
        t["id"] for t in nxt["data"]["transactions"]
    }
    assert not ids
    schema("tools/ledger.results.schema.json#/$defs/GetJarBalancesResult", call("get_jar_balances"))
    assert len(call("get_jar_balances")["data"]["jars"]) == 7  # không gồm hũ hệ thống


# --- sổ cái nhất quán ---------------------------------------------------------------------------------
@pytest.mark.parametrize("who,persona", [(MINH, "minh"), (LAN, "lan"), (KHOA, "khoa")])
def test_so_du_hu_bang_tong_dong_tra_bang_hu_sau_reset_va_sau_giao_dich(env, who, persona):
    env.reset(who, persona)
    if persona == "minh":
        env.act(
            who, "record_transaction", {"kind": "expense", "amount_vnd": 12_000, "jar": "di_lai"}
        )
        env.act(
            who,
            "record_transaction",
            {"kind": "expense", "amount_vnd": 5_000, "jar": "giai_tri", "funding": "credit"},
        )
        env.act(
            who,
            "move_between_jars",
            {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100_000},
        )
    with env.master() as c:
        rows = c.execute(
            "select j.code, j.balance_vnd, coalesce((select sum(t.amount_vnd) from transactions t where t.user_id=j.user_id and t.jar_code=j.code and t.funding_source='jar'),0) "
            "from jars j where j.user_id=%s",
            (who,),
        ).fetchall()
        assert rows and all(int(b) == int(s) for _, b, s in rows)
        # mỗi nhóm chuyển (transfer_id) tổng bằng 0 trừ số dư đầu kỳ một phía
        sums = c.execute(
            "select transfer_id, sum(amount_vnd), count(*) from transactions where user_id=%s and transfer_id is not null group by 1",
            (who,),
        ).fetchall()
        assert all(int(s) == 0 or n == 1 for _, s, n in sums)
        n_sys = c.execute(
            "select count(*) from jars where user_id=%s and kind='system'", (who,)
        ).fetchone()[0]
        assert n_sys == 2


def test_lich_su_chi_tieu_theo_ngay_du_day_va_co_nhip(env):
    env.reset(MINH)
    rows = env.db.query(
        "SELECT * FROM app_get_daily_spend(:uid, CAST(:a AS date), CAST(:b AS date))",
        {"uid": MINH, "a": "2026-10-05", "b": "2026-11-20"},
    )
    an = [r for r in rows if r["jar_code"] == "an_uong"]
    assert len(an) >= 28 and sum(int(r["spent_vnd"]) for r in an) == 4_720_000  # 5.020.000 trừ 300.000 tiền cơm văn phòng đã trả 23/10
    # nhịp cuối tuần: tính theo ngày LỊCH (kể cả ngày không chi), 5/10 đến 20/11 có 14 ngày cuối tuần và 33 ngày thường
    wk = sum(int(r["spent_vnd"]) for r in an if r["day"].weekday() >= 5) / 14
    wd = sum(int(r["spent_vnd"]) for r in an if r["day"].weekday() < 5) / 33
    assert wk > 1.15 * wd
    # khoản trả nghĩa vụ định kỳ KHÔNG nằm trong lịch sử chi tiêu (đã có trong lịch nghĩa vụ)
    hd = [r for r in rows if r["jar_code"] == "hoa_don"]
    assert sum(int(r["spent_vnd"]) for r in hd) < 400_000


def test_tong_quan_thu_hu_chi_tiet_va_dong_thoi_khong_vo_khi_co_du_bao(env, schema):
    env.reset(MINH)
    ov = env.svc.overview_response(MINH)
    schema("rest/openapi.yaml#/components/schemas/OverviewResponse", ov)
    d = env.svc.jar_detail_response(MINH, "an_uong")
    schema("rest/openapi.yaml#/components/schemas/JarDetailResponse", d)
    assert len(d["recent_transactions"]) == 10 and d["forecast"] is None
    sysd = env.svc.jar_detail_response(MINH, "chua_phan_loai")
    assert sysd["jar"]["balance_vnd"] == -180_000 and sysd["jar"]["kind"] == "system"
    schema("rest/openapi.yaml#/components/schemas/JarDetailResponse", sysd)
    with pytest.raises(YofinaError) as e:
        env.svc.jar_detail_response(MINH, "khong_co")
    assert e.value.code == ErrorCode.JAR_NOT_FOUND
    for name, fn in (
        ("PayeesResponse", env.svc.payees_response),
        ("TxTypesResponse", lambda u: env.svc.tx_types_response()),
        ("JarTemplatesResponse", lambda u: env.svc.jar_templates_response()),
        ("SalaryEventsResponse", env.svc.salary_events_response),
        ("CreditLineResponse", env.svc.credit_line_response),
        ("ObligationsResponse", env.svc.obligations_response),
        ("ProfileResponse", env.svc.profile_response),
        ("TransactionsResponse", env.svc.transactions_response),
        ("JarsResponse", lambda u: env.svc.jars_response(u, trace_id="t" * 8)),
    ):
        schema(f"rest/openapi.yaml#/components/schemas/{name}", fn(MINH))


def test_du_bao_chua_co_thi_tra_ma_chua_co_du_bao_va_doc_khoi_khi_co_du_lieu(env, schema):
    env.reset(MINH)
    with pytest.raises(YofinaError) as e:
        env.svc.forecast_response(MINH, "an_uong", trace_id="t" * 8)
    assert e.value.code == ErrorCode.FORECAST_UNAVAILABLE
    # nạp một lần chạy dự báo giả bằng quyền master (chỉ để thử đường đọc; việc tính là của luồng C)
    import uuid
    from datetime import date, timedelta

    run = str(uuid.uuid4())
    origin = date(2026, 11, 21)
    with env.master() as c:
        c.execute(
            "insert into forecast_runs (id,user_id,model,computed_at,app_date,horizon_days,history_days,data_coverage,confidence_label,is_initial_estimate,trigger) "
            "values (%s,%s,'hurdle_calendar',%s,%s,30,47,0.62,'medium',false,'reset')",
            (run, MINH, env.clock.now, origin),
        )
        c.execute(
            "insert into forecast_jar_summaries (run_id,user_id,jar_code,start_balance_vnd,payday_date,days_to_payday,runout_date,p_shortfall,status,confidence_band,show_probability,series_kind) "
            "values (%s,%s,'an_uong',380000,'2026-12-05',14,'2026-11-23',0.71,'short','medium',true,'dense')",
            (run, MINH),
        )
        for i in range(1, 31):
            d = origin + timedelta(days=i)
            bal = 380_000 - 150_000 * i
            c.execute(
                "insert into forecasts values (%s,%s,'an_uong',%s,0,100000,200000,%s,%s,%s)",
                (run, MINH, d, bal - 100_000, bal, bal + 100_000),
            )
    block = env.svc.forecast_response(MINH, "an_uong", trace_id="t" * 8)
    parsed = parse_block(block)
    assert (
        parsed.type == "forecast_timeline"
        and parsed.data.status == "short"
        and parsed.data.runout_date == "2026-11-23"
    )
    assert parsed.data.p_shortfall == pytest.approx(0.71) and parsed.data.stale is False
    kinds = {(e.kind, e.label) for e in parsed.data.events}
    assert ("salary", "Lương về") in kinds
    ov = env.svc.overview_response(MINH)
    assert ov["forecast"]["model"] == "hurdle_calendar"
    card = ov["proactive_card"]["data"]
    assert (
        card["kind"] == "runout_warning"
        and card["jar_code"] == "an_uong"
        and "23/11" in card["title"]
    )
    assert "71%" in card["reason"]
    assert next(j for j in ov["jars"] if j["code"] == "an_uong")["status"] == "short"
    assert json.loads(json.dumps(block_to_wire(parsed)))["type"] == "forecast_timeline"
    # qua một ngày mô phỏng thì dự báo bị đánh dấu cũ
    env.clock.now += timedelta(days=1)
    assert env.svc.overview_response(MINH)["forecast"]["stale"] is True


def test_loi_phat_su_kien_khong_lam_hong_viec_ghi_va_de_lai_audit(env):
    env.reset(MINH)
    env.events.fail = True
    env.act(MINH, "record_transaction", {"kind": "expense", "amount_vnd": 10_000, "jar": "di_lai"})
    assert balances(env, MINH)["di_lai"] == 630_000
    with env.master() as c:
        n = c.execute(
            "select count(*) from audit_events where user_id=%s and code='EVENT_PUBLISH_FAILED'",
            (MINH,),
        ).fetchone()[0]
    assert n == 1


def test_rls_that_role_ung_dung_khong_thay_dong_cua_nguoi_khac(env):
    env.reset(MINH)
    env.reset(LAN)
    rows = env.db.query("SELECT * FROM app_list_obligations(:uid, 'all', NULL, 100)", {"uid": LAN})
    with env.master() as c:
        lan_ids = {
            str(r[0])
            for r in c.execute("select id from obligations where user_id=%s", (LAN,)).fetchall()
        }
    assert {str(r["id"]) for r in rows} == lan_ids
    # truy vấn thẳng bảng khi chưa đặt app.user_id thì không thấy dòng nào
    assert env.db.query("SELECT id FROM obligations LIMIT 5") == []
    assert Path(__file__).exists()


# --- đua song song: khóa dòng và khóa unique giữ sổ cái đúng ----------------------------------------------
def test_hai_yeu_cau_song_song_cung_client_ref_chi_ghi_mot_lan(env):
    import threading

    env.reset(MINH)
    p = {
        "kind": "expense",
        "amount_vnd": 30_000,
        "jar": "di_lai",
        "tx_type": "public_transport",
        "client_ref": "race-1",
    }
    outcomes: list[str] = []

    def run():
        try:
            env.act(MINH, "record_transaction", p)
            outcomes.append("ok")
        except YofinaError as exc:
            outcomes.append(str(exc.code))

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["DUPLICATE_TRANSACTION", "ok"]
    assert balances(env, MINH)["di_lai"] == 610_000


def test_hai_lan_mua_tra_sau_song_song_cong_don_dung_va_phi_chi_tinh_mot_lan(env):
    import threading

    env.reset(LAN)
    fee = fee_from_table(env)
    p = {"kind": "expense", "amount_vnd": 300_000, "jar": "giai_tri", "funding": "credit"}
    errors: list[Exception] = []

    def run():
        try:
            env.act(LAN, "record_transaction", p)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    (ob,) = [o for o in env.svc.obligations_response(LAN)["obligations"] if o["kind"] == "bnpl"]
    assert ob["principal_vnd"] == 600_000 and ob["amount_vnd"] == 600_000 + fee
    assert env.svc.credit_line_response(LAN)["credit_line"]["outstanding_vnd"] == 600_000


def test_hai_lan_xac_nhan_luong_song_song_chi_chia_mot_lan(env):
    import threading

    env.reset(MINH)
    r = env.act(
        MINH, "record_transaction", {"kind": "income", "amount_vnd": 9_000_000, "tx_type": "salary"}
    )
    eid = parse_block(r).data.follow_up.salary_event_id
    p = {"salary_event_id": eid, "decision": "split"}
    outcomes: list[str] = []

    def run():
        try:
            env.act(MINH, "confirm_salary", p)
            outcomes.append("ok")
        except YofinaError as exc:
            outcomes.append(str(exc.code))

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["ALREADY_APPLIED", "ok"]
    assert balances(env, MINH)["an_uong"] == 380_000 + 2_700_000
    assert sys_balances(env, MINH)["tien_vao_khac"] == 350_000


# --- gợi ý cho giao diện do server tính: xem trước, cờ chuyển tiền cho người, mực dự báo -------------------------------
def test_xem_truoc_do_server_tinh_gom_phi_tra_sau_va_khong_ghi_gi(env):
    env.reset(LAN)
    fee = fee_from_table(env)
    before = balances(env, LAN)
    p = {"kind": "expense", "amount_vnd": 300_000, "jar": "giai_tri", "funding": "credit"}
    issued, preview = env.svc.issue_confirmation_with_preview(
        LAN, tool="record_transaction", params=p, client_params_hash=None, trace_id="a" * 8
    )
    assert issued.token and preview["summary"].startswith("Mua 300.000 ₫ bằng Trả sau (mô phỏng)")
    by_label = {c["label"]: c for c in preview["changes"]}
    assert by_label["Phải trả ngày 05/12"] == {
        "label": "Phải trả ngày 05/12",
        "before": "chưa có",
        "after": f"{300_000 + fee:,}".replace(",", ".") + " ₫",
    }
    assert by_label["Hạn mức còn lại"]["before"] == "2.000.000 ₫"
    assert by_label["Hạn mức còn lại"]["after"] == "1.700.000 ₫"
    assert any("33.000" in w for w in preview["warnings"]) or fee != 33_000
    assert balances(env, LAN) == before
    assert [
        o for o in env.svc.obligations_response(LAN)["obligations"] if o["kind"] == "bnpl"
    ] == []
    # chi bằng hũ: số dư hũ trước và sau
    _, prev2 = env.svc.issue_confirmation_with_preview(
        LAN,
        tool="record_transaction",
        params={"kind": "expense", "amount_vnd": 100_000, "jar": "an_uong"},
        client_params_hash=None,
        trace_id="a" * 8,
    )
    assert prev2["changes"][0] == {
        "label": "Hũ Ăn uống",
        "before": "520.000 ₫",
        "after": "420.000 ₫",
    }
    # chuyển hũ cũng có xem trước cùng hình dạng
    _, prev3 = env.svc.issue_confirmation_with_preview(
        LAN,
        tool="move_between_jars",
        params={"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 50_000},
        client_params_hash=None,
        trace_id="a" * 8,
    )
    assert [c["label"] for c in prev3["changes"]] == ["Hũ Giải trí", "Hũ Ăn uống"]
    assert prev3["changes"][1]["after"] == "570.000 ₫"


def test_tx_types_co_co_chuyen_tien_cho_nguoi_khac(env):
    env.reset(MINH)
    types = env.svc.tx_types_response()["tx_types"]
    flagged = [t["tx_type"] for t in types if t["is_person_transfer"]]
    assert flagged == ["transfer_person"] and all("is_person_transfer" in t for t in types)


def test_jar_templates_mac_dinh_cong_lai_dung_100(env):
    t = [x for x in env.svc.jar_templates_response()["templates"] if x["is_default"]]
    assert round(sum(x["default_split_percent"] for x in t), 2) == 100


def test_muc_du_bao_la_so_du_p50_thap_nhat_truoc_ky_luong(env):
    import uuid
    from datetime import date, timedelta

    env.reset(MINH)
    run = str(uuid.uuid4())
    origin = date(2026, 11, 21)
    with env.master() as c:
        c.execute(
            "insert into forecast_runs (id,user_id,model,computed_at,app_date,horizon_days,history_days,confidence_label,is_initial_estimate,trigger) "
            "values (%s,%s,'hurdle_calendar',%s,%s,30,47,'medium',false,'reset')",
            (run, MINH, env.clock.now, origin),
        )
        for code in ("an_uong", "di_lai"):
            c.execute(
                "insert into forecast_jar_summaries (run_id,user_id,jar_code,start_balance_vnd,payday_date,days_to_payday,status,confidence_band,show_probability) "
                "values (%s,%s,%s,380000,'2026-12-05',14,'short','medium',false)",
                (run, MINH, code),
            )
        for i in range(1, 31):
            bal = (
                380_000 - 150_000 * i if i < 20 else 5_000_000
            )  # sau lương số dư vọt lên: không được tính vào mực
            c.execute(
                "insert into forecasts values (%s,%s,'an_uong',%s,0,1,2,%s,%s,%s)",
                (run, MINH, origin + timedelta(days=i), bal - 1, bal, bal + 1),
            )
        c.execute(
            "insert into forecasts values (%s,%s,'di_lai','2026-12-10',0,1,2,0,10,20)", (run, MINH)
        )
    ov = env.svc.overview_response(MINH)
    jars = {j["code"]: j for j in ov["jars"]}
    # ngày dự báo 22/11 đến 4/12 (i = 1..13), thấp nhất ở i = 13
    assert jars["an_uong"]["forecast_floor_vnd"] == 380_000 - 150_000 * 13
    assert "forecast_floor_vnd" not in jars["di_lai"]  # không có ngày nào trước kỳ lương
    assert "forecast_floor_vnd" not in jars["giai_tri"]  # chưa có dự báo
    d = env.svc.jar_detail_response(MINH, "an_uong")
    assert d["jar"]["forecast_floor_vnd"] == 380_000 - 150_000 * 13
