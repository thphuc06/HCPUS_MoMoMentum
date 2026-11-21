import hashlib
import json
from decimal import Decimal

import pytest

from yofina_core.confirm import ParamsError, canonical_json, normalize_move_params, params_hash

TOOL = "move_between_jars"


def test_chuan_hoa_giu_dung_ba_khoa_va_bo_tham_so_la():
    out = normalize_move_params(
        {
            "from_jar": "  Giai_Tri ",
            "to_jar": "an_uong",
            "amount_vnd": Decimal("100000"),
            "user_id": "x",
            "confirm_token": "a.b",
            "evil": 1,
        }
    )
    assert out == {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100000}


def test_chuan_hoa_idempotent():
    once = normalize_move_params({"from_jar": "A_b", "to_jar": "c", "amount_vnd": "5"})
    assert normalize_move_params(once) == once


@pytest.mark.parametrize(
    "params",
    [
        {"from_jar": "a", "to_jar": "b"},  # thiếu amount
        {"from_jar": "a", "to_jar": "a", "amount_vnd": 1},  # cùng hũ
        {"from_jar": "Ăn uống", "to_jar": "b", "amount_vnd": 1},  # mã có dấu/khoảng trắng
        {"from_jar": "a", "to_jar": "b", "amount_vnd": 0},
        {"from_jar": "a", "to_jar": "b", "amount_vnd": -5},
        {"from_jar": "a", "to_jar": "b", "amount_vnd": 1.5},
        {"from_jar": "a", "to_jar": "b", "amount_vnd": 100000.0},  # float bị từ chối
        {"from_jar": "a", "to_jar": "b", "amount_vnd": "abc"},
        {"from_jar": "a", "to_jar": "b", "amount_vnd": 10**14},
        {"from_jar": 1, "to_jar": "b", "amount_vnd": 1},
        {"from_jar": "1abc", "to_jar": "b", "amount_vnd": 1},
    ],
)
def test_tham_so_sai_bi_tu_choi(params):
    with pytest.raises(ParamsError):
        normalize_move_params(params)


def test_hash_khop_cong_thuc_da_ghi():
    params = {"from_jar": "giai_tri", "to_jar": "an_uong", "amount_vnd": 100000}
    expected = hashlib.sha256(
        b'{"params":{"amount_vnd":100000,"from_jar":"giai_tri","to_jar":"an_uong"},'
        b'"tool":"move_between_jars"}'
    ).hexdigest()
    assert params_hash(TOOL, params) == expected
    # giá trị này được khóa lại để mọi bên (Python, Lambda, test frontend nếu cần) tính ra y hệt
    assert expected == "52a35d69448e3621190f43bbc8fa12356d2cfdd9895fac320e0557dfa779a962"


def test_hash_khong_phu_thuoc_thu_tu_khoa_hay_tham_so_la():
    a = params_hash(TOOL, {"from_jar": "a", "to_jar": "b", "amount_vnd": 5})
    b = params_hash(TOOL, {"amount_vnd": 5, "to_jar": "B", "from_jar": "A", "user_id": "u"})
    assert a == b


def test_hash_doi_khi_doi_tham_so_hoac_tool():
    base = params_hash(TOOL, {"from_jar": "a", "to_jar": "b", "amount_vnd": 5})
    assert base != params_hash(TOOL, {"from_jar": "a", "to_jar": "b", "amount_vnd": 6})
    assert base != params_hash(TOOL, {"from_jar": "b", "to_jar": "a", "amount_vnd": 5})
    with pytest.raises(ParamsError):
        params_hash("other_tool", {"from_jar": "a", "to_jar": "b", "amount_vnd": 5})


def test_canonical_json_on_dinh():
    assert canonical_json({"b": 1, "a": "ă"}) == '{"a":"ă","b":1}'
    assert json.loads(canonical_json({"x": [1, 2]})) == {"x": [1, 2]}
