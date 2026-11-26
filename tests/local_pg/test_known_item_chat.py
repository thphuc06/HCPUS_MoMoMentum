"""Khai khoản biết trước qua Gateway trên ví Minh thật trong Postgres cục bộ."""

import json

from conftest import REPO
from jsonschema import Draft202012Validator
from ledger_fakes import gateway_context, http_event
from referencing import Registry, Resource

from yofina_ledger.gateway_api import handle_gateway
from yofina_ledger.rest_api import handle_http


def test_known_item_chat_matches_rest_on_reset_minh(env):
    user = "minh-tet-chat"
    response = handle_http(
        http_event("POST", "/demo/reset", sub=user, groups="persona-minh"), env.svc
    )
    assert response["statusCode"] == 200, response
    before = env.svc.jars_response(user, trace_id="minh-tet")
    sent_before = list(env.events.sent)
    body = {
        "sinking_items": [{"name": "Tết", "amount_vnd": 5_000_000, "needed_date": "2027-02-05"}]
    }

    result = handle_gateway(
        {"user_id": user, **body}, gateway_context("ledger___propose_jar_split"), env.svc
    )
    assert result["status"] == "OK", result
    data = result["data"]
    assert data["app_date"] == "2026-11-21"
    assert data["status"] == "proposed"
    jars = data["params"]["jars"]
    (sinking,) = [j for j in jars if j.get("purpose") == "sinking"]
    assert sinking["code"] == "quy_don" and sinking["sinking_items"] == body["sinking_items"]
    assert sum(j["split_percent"] for j in jars) == 100

    rest = handle_http(http_event("POST", "/jars/split-proposal", sub=user, body=body), env.svc)
    assert rest["statusCode"] == 200, rest
    assert {key: value for key, value in data.items() if key != "confirm"} == json.loads(
        rest["body"]
    )

    schemas = [
        json.loads((REPO / "contracts/blocks" / f"{name}.schema.json").read_text(encoding="utf-8"))
        for name in ("envelope", "confirm_action")
    ]
    registry = Registry().with_resources(
        (doc["$id"], Resource.from_contents(doc)) for doc in schemas
    )
    Draft202012Validator(
        {"$ref": f"{schemas[1]['$id']}#/$defs/ConfirmActionData"}, registry=registry
    ).validate(data["confirm"])
    assert data["confirm"]["tool"] == "save_jars"
    assert data["confirm"]["params"] == data["params"]
    assert env.svc.jars_response(user, trace_id="minh-tet") == before
    assert env.events.sent == sent_before

    (plan,) = data["sinking_items"]
    assert (sinking["split_percent"], plan["per_payday_vnd"]) == (28, 2_500_000)
    changed = [
        (j["code"], j["split_before"], j["split_after"])
        for j in data["jars"]
        if j["split_before"] != j["split_after"]
    ]
    print(
        f"status={data['status']}, Quỹ dồn={sinking['split_percent']}%, mỗi kỳ={plan['per_payday_vnd']} ₫"
    )
    print(f"Hũ đổi: {changed}")
    print(f"checks: {data['checks']}")
