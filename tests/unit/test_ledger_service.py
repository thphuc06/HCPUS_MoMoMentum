"""Nghiệp vụ ledger và đường Gateway, với kho dữ liệu giả (tests/unit/ledger_fakes.py).

Mọi kết quả tool được kiểm bằng JSON Schema thật của hợp đồng (contracts/tools/ledger.results)."""

from __future__ import annotations

import pytest
from conftest import BASE
from jsonschema import Draft202012Validator
from ledger_fakes import SETTINGS, gateway_context, make_service

from yofina_core.blocks import parse_block
from yofina_core.confirm import params_hash
from yofina_core.errors import ErrorCode, YofinaError
from yofina_ledger.gateway_api import handle_gateway, tool_name

MINH, LAN = "sub-minh", "sub-lan"
MOVE = {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100_000}
RESULTS = f"{BASE}/tools/ledger.results.schema.json"


@pytest.fixture
def check(registry):
    def run(def_name: str, instance):
        v = Draft202012Validator({"$ref": f"{RESULTS}#/$defs/{def_name}"}, registry=registry)
        errors = sorted(v.iter_errors(instance), key=lambda e: list(e.path))
        assert not errors, [f"{list(e.path)}: {e.message}" for e in errors]

    return run


def call(service, tool: str, event: dict):
    return handle_gateway(event, gateway_context(f"ledger___{tool}"), service)


# --- tên tool và danh tính ------------------------------------------------------------------
def test_ten_tool_cat_tien_to_target():
    assert tool_name(gateway_context("ledger___get_jar_balances")) == "get_jar_balances"
    assert tool_name(gateway_context("ledger___move_between_jars")) == "move_between_jars"
    assert tool_name(gateway_context(None)) == ""


def test_thieu_user_id_thi_unauthenticated(check):
    svc, _, _ = make_service()
    res = call(svc, "get_jar_balances", {})
    check("ToolError", res)
    assert res["code"] == "UNAUTHENTICATED"


def test_tool_la_bi_tu_choi(check):
    svc, _, _ = make_service()
    res = call(svc, "drop_all_tables", {"user_id": MINH})
    check("ToolError", res)
    assert res["code"] == "PARAMS_INVALID"


# --- get_jar_balances ---------------------------------------------------------------------
def test_get_jar_balances_dung_so_va_dung_hop_dong(check):
    svc, _, _ = make_service()
    res = call(svc, "get_jar_balances", {"user_id": MINH, "tham_so_la": "bo qua"})
    check("GetJarBalancesResult", res)
    assert res["status"] == "OK"
    assert res["app_date"] == "2026-11-21"  # offset -19 so với 2026-12-10
    jars = res["data"]["jars"]
    assert [j["code"] for j in jars] == ["an_uong", "giai_tri", "di_lai"]
    assert res["data"]["jars_total_vnd"] == 380_000 + 760_000 + 640_000


def test_get_jar_balances_tra_loai_va_muc_tieu_goc_tu_bang_jars(check):
    from datetime import date
    from decimal import Decimal

    svc, repo, _ = make_service()
    jars = repo.users[MINH]["jars"]
    # dạng hàng của app_get_jar_state: numeric -> Decimal, date -> date, NULL -> None
    jars["an_uong"].update(kind="spending", goal_vnd=None, goal_date=None)
    jars["giai_tri"].update(kind="saving", goal_vnd=Decimal(6_000_000), goal_date=date(2027, 3, 31))
    jars["di_lai"].update(kind="saving", goal_vnd=Decimal(9_000_000), goal_date=None)
    jars["tien_vao_khac"] = {
        "code": "tien_vao_khac", "name": "Tiền vào khác", "color_key": "gray", "icon_key": "inbox",
        "balance_vnd": Decimal(50_000), "split_percent": Decimal(0), "sort_order": 99,
        "kind": "system", "goal_vnd": None, "goal_date": None,
    }  # fmt: skip
    res = call(svc, "get_jar_balances", {"user_id": MINH})
    check("GetJarBalancesResult", res)
    by_code = {j["code"]: j for j in res["data"]["jars"]}
    assert list(by_code) == ["an_uong", "giai_tri", "di_lai"]  # không gồm hũ hệ thống
    assert by_code["an_uong"] == {
        "code": "an_uong", "name": "Ăn uống", "color_key": "violet", "icon_key": "utensils",
        "balance_vnd": 380_000, "split_percent": 30, "kind": "spending",
    }  # fmt: skip
    assert (by_code["giai_tri"]["goal_vnd"], by_code["giai_tri"]["goal_date"]) == (6_000_000, "2027-03-31")
    assert isinstance(by_code["giai_tri"]["goal_vnd"], int)
    assert by_code["di_lai"]["goal_vnd"] == 9_000_000 and "goal_date" not in by_code["di_lai"]
    assert res["data"]["jars_total_vnd"] == 380_000 + 760_000 + 640_000


def test_nguoi_dung_chua_co_du_lieu_thi_khong_co_hu(check):
    svc, _, _ = make_service(users=())
    res = call(svc, "get_jar_balances", {"user_id": "sub-moi"})
    check("GetJarBalancesResult", res)
    assert res["data"] == {"jars": [], "jars_total_vnd": 0}


def test_hai_nguoi_dung_thay_du_lieu_rieng():
    svc, repo, _ = make_service()
    repo.users[LAN]["jars"]["an_uong"]["balance_vnd"] = 5
    a = call(svc, "get_jar_balances", {"user_id": MINH})["data"]["jars"][0]["balance_vnd"]
    b = call(svc, "get_jar_balances", {"user_id": LAN})["data"]["jars"][0]["balance_vnd"]
    assert (a, b) == (380_000, 5)


# --- move_between_jars: không token thì không ghi -------------------------------------------
def test_khong_token_thi_needs_confirmation_va_khong_ghi_gi(check):
    svc, repo, _ = make_service()
    before = repo.users[MINH]["jars"]["giai_tri"]["balance_vnd"]
    # LLM tự điền "user_confirmed": cờ lạ bị bỏ qua, không có tác dụng
    res = call(svc, "move_between_jars", {"user_id": MINH, **MOVE, "user_confirmed": True})
    check("MoveBetweenJarsResult", res)
    assert res["status"] == "NEEDS_CONFIRMATION"
    d = res["data"]
    assert d["params"] == MOVE
    assert d["params_hash"] == params_hash("move_between_jars", MOVE)
    assert d["preview"]["from"] == {
        "code": "giai_tri",
        "name": "Giải trí",
        "before_vnd": 760_000,
        "after_vnd": 660_000,
    }
    assert d["preview"]["to"]["after_vnd"] == 480_000
    assert repo.users[MINH]["jars"]["giai_tri"]["balance_vnd"] == before
    assert not repo.moves and not repo.audits


def test_khoi_confirm_dung_tu_ket_qua_tool_la_hop_le():
    from yofina_core.blocks import build_confirm  # noqa: F401  (cùng đường dựng với agent)

    svc, _, _ = make_service()
    block = svc.prepare_move(MINH, MOVE, trace_id="t1", source_tool="ledger___move_between_jars")
    parse_block(block.model_dump(mode="json", by_alias=True))
    assert block.data.expires_at.endswith("Z")


def test_tham_so_chuan_hoa_truoc_khi_bam():
    svc, _, _ = make_service()
    res = call(
        svc,
        "move_between_jars",
        {"user_id": MINH, "from_jar": " Giai_Tri ", "to_jar": "AN_UONG", "amount_vnd": "100000"},
    )
    assert res["data"]["params"] == MOVE


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"from_jar": "giai_tri", "to_jar": "giai_tri", "amount_vnd": 1}, "PARAMS_INVALID"),
        ({"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 0}, "PARAMS_INVALID"),
        ({"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": -1}, "PARAMS_INVALID"),
        ({"from_jar": "giai_tri", "to_jar": "an_uong"}, "PARAMS_INVALID"),
        ({"from_jar": "giai_tri", "to_jar": "khong_co", "amount_vnd": 1000}, "JAR_NOT_FOUND"),
        (
            {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 760_001},
            "INSUFFICIENT_FUNDS",
        ),
        (
            {
                "from_jar": "giai_tri",
                "to_jar": "an_uong",
                "amount_vnd": SETTINGS.move_max_amount_vnd + 1,
            },
            "AMOUNT_LIMIT_EXCEEDED",
        ),
    ],
)
def test_loi_nghiep_vu_khong_dung_khoi_confirm(check, params, code):
    svc, repo, _ = make_service()
    res = call(svc, "move_between_jars", {"user_id": MINH, **params})
    check("ToolError", res)
    assert res["code"] == code
    assert not repo.moves


# --- luồng đủ: cấp token rồi ghi ----------------------------------------------------------------
def issue(svc, uid=MINH, params=MOVE):
    return svc.issue_confirmation(
        uid, tool="move_between_jars", params=params, client_params_hash=None, trace_id="t"
    )


def test_luong_day_du_cap_token_roi_ghi_qua_gateway(check):
    svc, repo, _ = make_service()
    tok = issue(svc).token
    res = call(svc, "move_between_jars", {"user_id": MINH, **MOVE, "confirm_token": tok})
    check("MoveBetweenJarsResult", res)
    assert res["status"] == "OK"
    assert res["data"]["from_jar"]["balance_after_vnd"] == 660_000
    assert res["data"]["to_jar"]["balance_after_vnd"] == 480_000
    jars = repo.users[MINH]["jars"]
    assert (jars["giai_tri"]["balance_vnd"], jars["an_uong"]["balance_vnd"]) == (660_000, 480_000)
    # hai dòng sổ cái cùng transfer_id, một âm một dương
    txs = repo.transactions[MINH]
    assert len(txs) == 2 and {t["transfer_id"] for t in txs} == {res["data"]["transaction_id"]}
    assert sorted(int(t["amount_vnd"]) for t in txs) == [-100_000, 100_000]
    assert repo.audits[-1]["outcome"] == "ok" and repo.audits[-1]["channel"] == "gateway"


def test_token_dung_mot_lan_replay_bi_tu_choi_va_ghi_audit(check):
    svc, repo, _ = make_service()
    tok = issue(svc).token
    ev = {"user_id": MINH, **MOVE, "confirm_token": tok}
    assert call(svc, "move_between_jars", ev)["status"] == "OK"
    res = call(svc, "move_between_jars", ev)
    check("ToolError", res)
    assert res["code"] == "TOKEN_REUSED"
    assert len(repo.moves) == 1
    assert repo.audits[-1] == {
        "uid": MINH,
        "outcome": "rejected",
        "code": "TOKEN_REUSED",
        "params": MOVE,
    }


def test_token_doi_tham_so_bi_tu_choi_va_khong_ghi(check):
    svc, repo, _ = make_service()
    tok = issue(svc).token
    res = call(
        svc,
        "move_between_jars",
        {"user_id": MINH, **{**MOVE, "amount_vnd": 700_000}, "confirm_token": tok},
    )
    check("ToolError", res)
    assert res["code"] == "PARAMS_MISMATCH"
    assert not repo.moves
    # token chưa bị tiêu: dùng lại đúng tham số vẫn được
    ok = call(svc, "move_between_jars", {"user_id": MINH, **MOVE, "confirm_token": tok})
    assert ok["status"] == "OK"


def test_token_cua_nguoi_khac_bi_tu_choi(check):
    svc, repo, _ = make_service()
    tok_lan = issue(svc, LAN).token
    res = call(svc, "move_between_jars", {"user_id": MINH, **MOVE, "confirm_token": tok_lan})
    check("ToolError", res)
    assert res["code"] == "TOKEN_INVALID"
    assert not repo.moves


def test_token_het_han(check):
    svc, repo, clock = make_service()
    tok = issue(svc).token
    clock.advance(121)
    res = call(svc, "move_between_jars", {"user_id": MINH, **MOVE, "confirm_token": tok})
    check("ToolError", res)
    assert res["code"] == "TOKEN_EXPIRED"
    assert not repo.moves


def test_token_bia_va_token_sai_kieu(check):
    svc, repo, _ = make_service()
    for tok, code in (("abc.def", "TOKEN_INVALID"), (12345, "PARAMS_INVALID")):
        res = call(svc, "move_between_jars", {"user_id": MINH, **MOVE, "confirm_token": tok})
        check("ToolError", res)
        assert res["code"] == code
    assert not repo.moves


def test_tieu_token_roi_het_tien_thi_loi_nghiep_vu_va_khong_ghi(check):
    svc, repo, _ = make_service()
    big = {**MOVE, "amount_vnd": 760_000}
    tok = issue(svc, params=big).token
    repo.users[MINH]["jars"]["giai_tri"]["balance_vnd"] = 10  # số dư đổi sau khi bấm xác nhận
    res = call(svc, "move_between_jars", {"user_id": MINH, **big, "confirm_token": tok})
    check("ToolError", res)
    assert res["code"] == "INSUFFICIENT_FUNDS"
    assert not repo.moves


def test_cap_token_kiem_nghiep_vu_va_hash_khach(check):
    svc, _, _ = make_service()
    with pytest.raises(YofinaError) as ei:
        svc.issue_confirmation(
            MINH,
            tool="move_between_jars",
            params={**MOVE, "amount_vnd": 9_999_999},
            client_params_hash=None,
            trace_id="t",
        )
    assert ei.value.code == ErrorCode.INSUFFICIENT_FUNDS
    with pytest.raises(YofinaError) as ei:
        svc.issue_confirmation(
            MINH, tool="move_between_jars", params=MOVE, client_params_hash="0" * 64, trace_id="t"
        )
    assert ei.value.code == ErrorCode.PARAMS_MISMATCH
    good = params_hash("move_between_jars", MOVE)
    issued = svc.issue_confirmation(
        MINH, tool="move_between_jars", params=MOVE, client_params_hash=good, trace_id="t"
    )
    assert issued.params_hash == good
    with pytest.raises(YofinaError):
        svc.issue_confirmation(
            MINH, tool="drop_table", params=MOVE, client_params_hash=None, trace_id="t"
        )


# --- query_transactions -----------------------------------------------------------------------
def test_query_transactions_loc_phan_trang_va_hop_dong(check):
    svc, _, _ = make_service()
    for _ in range(3):
        tok = issue(svc).token
        call(svc, "move_between_jars", {"user_id": MINH, **MOVE, "confirm_token": tok})
    res = call(svc, "query_transactions", {"user_id": MINH, "limit": 4})
    check("QueryTransactionsResult", res)
    assert len(res["data"]["transactions"]) == 4 and res["data"]["has_more"] is True
    res = call(svc, "query_transactions", {"user_id": MINH, "jar": "an_uong", "limit": 50})
    check("QueryTransactionsResult", res)
    assert len(res["data"]["transactions"]) == 3 and res["data"]["has_more"] is False
    assert all(t["jar"] == "an_uong" for t in res["data"]["transactions"])
    res = call(svc, "query_transactions", {"user_id": LAN})
    assert res["data"]["transactions"] == []


@pytest.mark.parametrize(
    "args",
    [{"jar": "Ăn uống"}, {"from_date": "21/11/2026"}, {"to_date": "x"}, {"limit": "nhieu"}],
)
def test_query_transactions_tham_so_sai(check, args):
    svc, _, _ = make_service()
    res = call(svc, "query_transactions", {"user_id": MINH, **args})
    check("ToolError", res)
    assert res["code"] == "PARAMS_INVALID"


def test_query_transactions_gioi_han_limit_theo_cau_hinh():
    svc, repo, _ = make_service()
    seen = []
    orig = repo.list_transactions
    repo.list_transactions = lambda uid, **kw: (seen.append(kw["limit"]), orig(uid, **kw))[1]
    call(svc, "query_transactions", {"user_id": MINH, "limit": 9999})
    call(svc, "query_transactions", {"user_id": MINH})
    call(svc, "query_transactions", {"user_id": MINH, "limit": 0})
    assert seen == [SETTINGS.transactions_max_limit + 1, SETTINGS.transactions_default_limit + 1, 2]


def test_loi_bat_ngo_tro_thanh_internal_error_khong_ro_chi_tiet(check):
    svc, repo, _ = make_service()

    def boom(uid):
        raise RuntimeError("chi tiet noi bo: mat khau db")

    repo.jar_view = boom
    res = call(svc, "get_jar_balances", {"user_id": MINH})
    check("ToolError", res)
    assert res["code"] == "INTERNAL_ERROR" and "mat khau" not in res["message"]
