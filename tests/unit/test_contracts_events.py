"""Hợp đồng sự kiện trên EventBridge bus `yofina-bus` (contracts/events): JSON Schema + fixture dùng chung."""

from __future__ import annotations

import pytest
from conftest import BASE, CONTRACTS, load_json
from jsonschema import Draft202012Validator

EVENT_DIR = CONTRACTS / "events"
FIXTURES = sorted((CONTRACTS / "fixtures" / "events").glob("*.json"))
INVALID = sorted((CONTRACTS / "fixtures" / "events" / "invalid").glob("*.json"))
#: detail-type -> source, đúng quy ước ở contracts/README.md (mục "Sự kiện").
EVENTS = {
    "transaction.recorded": "yofina.ledger",
    "salary.confirmed": "yofina.ledger",
    "obligation.changed": "yofina.ledger",
    "profile.updated": "yofina.ledger",
    "forecast.updated": "yofina.forecast",
    # phase 4
    "behavior.changed": "yofina.forecast",
    "roadmap.regeneration_requested": "yofina.ledger",
}


def validator(registry, detail_type: str) -> Draft202012Validator:
    ref = f"{BASE}/events/{detail_type}.schema.json"
    return Draft202012Validator({"$ref": ref}, registry=registry)


def detail_type(path) -> str:
    return ".".join(path.name.split(".")[:2])


def test_moi_su_kien_co_file_schema_va_khong_thua_file():
    files = {p.name.removesuffix(".schema.json") for p in EVENT_DIR.glob("*.schema.json")}
    assert files == set(EVENTS) | {"common"}


@pytest.mark.parametrize("name", sorted(EVENTS))
def test_phong_bi_chung_cua_su_kien(name):
    schema = load_json(EVENT_DIR / f"{name}.schema.json")
    assert schema["additionalProperties"] is False  # phía phát chặt: lỗi của producer lộ ngay
    for key in (
        "v",
        "event_id",
        "user_id",
        "occurred_at" if name != "forecast.updated" else "computed_at",
    ):
        assert key in schema["required"], key
    assert schema["properties"]["v"] == {"$ref": "common.schema.json#/$defs/EventVersion"}
    # không có chỗ nào để nhét token, mật khẩu hay nội dung hội thoại
    text = (EVENT_DIR / f"{name}.schema.json").read_text(encoding="utf-8")
    assert "confirm_token" not in schema["properties"] and "authorization" not in text.lower()


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_su_kien_hop_le(registry, path):
    assert detail_type(path) in EVENTS
    assert list(validator(registry, detail_type(path)).iter_errors(load_json(path))) == []


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.name)
def test_fixture_su_kien_sai_bi_tu_choi(registry, path):
    assert detail_type(path) in EVENTS
    assert not validator(registry, detail_type(path)).is_valid(load_json(path))


def test_moi_su_kien_co_it_nhat_mot_fixture_dung_va_mot_sai():
    assert {detail_type(p) for p in FIXTURES} == set(EVENTS)
    assert {detail_type(p) for p in INVALID} == set(EVENTS)


def test_event_id_cua_transaction_recorded_bang_transaction_id():
    for path in FIXTURES:
        if detail_type(path) == "transaction.recorded":
            d = load_json(path)
            assert (
                d["event_id"] == d["transaction_id"]
            )  # gửi lại cùng một lần ghi thì cùng event_id


def test_event_id_cua_salary_confirmed_va_forecast_updated_bang_id_doi_tuong():
    for path in FIXTURES:
        d = load_json(path)
        if detail_type(path) == "salary.confirmed":
            assert d["event_id"] == d["salary_event_id"]
        if detail_type(path) == "forecast.updated":
            assert d["event_id"] == d["run_id"]


def test_effects_nhat_quan_voi_jar_codes_va_so_tien():
    for path in FIXTURES:
        d = load_json(path)
        if detail_type(path) == "transaction.recorded":
            effect_jars = [e["jar_code"] for e in d["effects"]]
            assert set(effect_jars) <= set(
                d["jar_codes"]
            )  # hũ nào đổi số dư thì nằm trong jar_codes
            assert len(set(d["jar_codes"])) == len(d["jar_codes"])
            if d["funding_source"] == "credit":
                assert d["effects"] == []  # mua bằng hạn mức không đổi số dư hũ
                assert d["kind"] == "expense"
            if d["kind"] == "transfer":
                assert sum(e["delta_vnd"] for e in d["effects"]) == 0  # chuyển hũ bảo toàn tiền
        if detail_type(path) == "salary.confirmed" and d["decision"] == "split":
            assert (
                sum(e["delta_vnd"] for e in d["effects"]) == 0
            )  # tiền rời Tiền vào khác, vào các hũ
            assert (
                sum(e["delta_vnd"] for e in d["effects"] if e["delta_vnd"] > 0) == d["amount_vnd"]
            )


def test_su_kien_khong_chua_so_tai_khoan_hay_ten_nguoi_nhan():
    for path in FIXTURES:
        text = path.read_text(encoding="utf-8")
        assert "account_hint" not in text and "payee_name" not in text and "merchant" not in text
