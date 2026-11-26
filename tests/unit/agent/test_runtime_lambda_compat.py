"""Tương thích Runtime ↔ Lambda khi phát hành bộ hũ mặc định (#39): Runtime MỚI đọc được kết quả tool của Lambda CŨ và của Lambda MỚI.

Runtime cũ kiểm chặt (`extra=forbid`) nên thứ tự phát hành là Runtime mới trước, Lambda sau. Giữa hai lần deploy, Runtime mới gặp
kết quả của Lambda cũ (`ed95134`: không có `purpose`, `sinking_items`, `obligations_before_payday`, `field` của lỗi); sau đó gặp kết
quả của Lambda mới (có các trường đó). Test chạy MỌI bộ đọc kết quả tool của agent (dựng khối, đọc dữ liệu của lộ trình) trên hai
dạng:

- dạng cũ: fixture `contracts/fixtures/tools/*.json`. Các fixture kết quả OK không đổi từ `ed95134` (`git diff ed95134 --
  contracts/fixtures/tools` chỉ thêm ba fixture lỗi `*.error_pay_jar_required.json`), và test kiểm chúng không có trường mới.
  Fixture số dư hũ viết trước phase 4 nên thêm một biến thể có cột `jars` mà Ledger `ed95134` đã phát (`kind`, `goal_vnd`,
  `goal_date`); fixture dự báo là hũ Ăn uống nên thêm một biến thể của hũ Nghĩa vụ (hũ duy nhất Lambda mới phát khung khoản đến hạn);
- dạng mới: cùng các payload đó, thêm trường mới đúng chỗ và đúng luật Lambda mới phát (`purpose` chỉ ở hũ để dành, khung khoản đến
  hạn dựng bằng chính `obligation_window` cho hũ Nghĩa vụ, `recent_spend` chỉ ở dòng phân bổ của hũ chi: GG, #39), và phải hợp lệ với
  schema kết quả HIỆN TẠI của `contracts/tools/*.results.schema.json` (nên không dựng tay một dạng Lambda không phát được).
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from conftest import BASE, build_registry
from jsonschema import Draft202012Validator
from test_contracts_tools import RESULT_DEF, RESULT_FILE
from yofina_agent import tools as T
from yofina_agent.roadmap_agent import _parse
from yofina_agent.tools import ToolKind, ToolOutcome, asks_pay_jar, classify_result

from yofina_core import blocks as B
from yofina_core.errors import PAY_JAR_FIELD
from yofina_core.roadmap import AllocationPlanData, Roadmap
from yofina_core.schedule import obligation_window
from yofina_core.wallet import DEFAULT_OBLIGATION_JAR

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "contracts" / "fixtures" / "tools"
#: ví persona mà fixture số dư hũ chép (cùng mã, tên, màu, số dư): nguồn của cột `jars` Ledger phát
PERSONA_SPEC = REPO / "data" / "personas" / "specs" / "minh.json"
NEW_FIELDS = (
    "purpose", "sinking_items", "obligations_before_payday", "field", "recent_spend", "high_since", "change_confirmed",
)  # fmt: skip
TRACE = "8f3a21c94b7e4d0aa1c25e6f7b8c9d01"
#: mục đích của hũ để dành trong fixture, như sau 0057 (ví demo, tài khoản mới)
PURPOSES = {"du_phong": "buffer", "du_lich": "goal", "muc_tieu": "goal", "dau_tu": "long_term"}


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _mcp(payload: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success", "toolUseId": "t", "content": [{"text": json.dumps(payload)}]}


def _outcome(tool: str, payload: dict[str, Any]) -> ToolOutcome:
    return classify_result(f"x___{tool}", _mcp(payload))


def _block(fn: Callable[[ToolOutcome, str], Any]) -> Callable[[ToolOutcome], Any]:
    return lambda o: fn(o, TRACE)


def _model(model: Any) -> Callable[[ToolOutcome], Any]:
    def read(o: ToolOutcome) -> Any:
        parsed = _parse(o, model)
        assert parsed is not None, f"không đọc được {model.__name__}"
        return parsed

    return read


#: tool -> bộ đọc của agent cho kết quả OK / NEEDS_CONFIRMATION (cùng hàm `Turn` và `roadmap_agent` dùng)
READERS: dict[str, Callable[[ToolOutcome], Any]] = {
    "get_jar_balances": _block(T.jar_summary_block),
    "move_between_jars": _block(T.confirm_block),
    "get_forecast": _block(T.forecast_block),
    "update_profile": _block(T.confirm_action_block),
    "record_transaction": _block(T.confirm_action_block),
    "assign_jar": _block(T.confirm_action_block),
    "schedule_nudge": _block(T.confirm_action_block),
    "affordability_check": _block(T.affordability_block),
    "get_resilience_score": _block(T.resilience_block),
    "stress_test": _block(T.stress_block),
    "get_roadmap": _block(T.roadmap_block),
    "run_scenario": _block(T.scenario_blocks),
    "optimize_allocation": _model(AllocationPlanData),
}


#: tool ghi: agent chỉ dựng khối từ NEEDS_CONFIRMATION (kết quả OK là biên nhận của đường REST, agent không đọc)
WRITE_TOOLS = {
    "move_between_jars",
    "update_profile",
    "record_transaction",
    "assign_jar",
    "schedule_nudge",
}


def _fixtures(tool: str) -> list[Path]:
    kinds = ("needs_confirmation",) if tool in WRITE_TOOLS else ("ok",)
    return sorted(
        p for p in FIXTURES.glob(f"{tool}.*.json") if p.name.split(".")[1].startswith(kinds)
    )


def _with_ledger_columns(payload: dict[str, Any]) -> dict[str, Any]:
    """Số dư hũ như Ledger `ed95134` phát: mỗi hũ có `kind` (cột NOT NULL), hũ có mục tiêu có `goal_vnd`/`goal_date` (phase 4)."""
    out = copy.deepcopy(payload)
    spec = {j["code"]: j for j in json.loads(PERSONA_SPEC.read_text(encoding="utf-8"))["jars"]}
    for jar in out["data"]["jars"]:
        src = spec[jar["code"]]
        jar["kind"] = src["kind"]
        jar.update({k: src[k] for k in ("goal_vnd", "goal_date") if src.get(k) is not None})
    return out


def _as_obligation_jar(payload: dict[str, Any]) -> dict[str, Any]:
    """Cùng dự báo, của hũ Nghĩa vụ (đầu hũ lấy từ fixture số dư hũ): câu "dự báo hũ Nghĩa vụ" mà review nêu."""
    out = copy.deepcopy(payload)
    jar = next(
        j
        for j in _load("get_jar_balances.ok.json")["data"]["jars"]
        if j["code"] == DEFAULT_OBLIGATION_JAR
    )
    out["data"]["jar"] = {k: jar[k] for k in ("code", "name", "color_key", "icon_key")}
    return out


def old_lambda_payloads(tool: str, path: Path) -> list[tuple[str, dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out = [("fixture", payload)]
    if tool == "get_jar_balances":
        out.append(("cot_jars", _with_ledger_columns(payload)))
    if tool == "get_forecast" and payload["data"]["jar"]["code"] != DEFAULT_OBLIGATION_JAR:
        out.append(("hu_nghia_vu", _as_obligation_jar(payload)))
    return out


CASES = [
    pytest.param(tool, label, payload, id=f"{path.name}-{label}")
    for tool in READERS
    for path in _fixtures(tool)
    for label, payload in old_lambda_payloads(tool, path)
]


def _has_new_field(node: Any) -> bool:
    if isinstance(node, dict):
        return any(k in NEW_FIELDS for k in node) or any(_has_new_field(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_new_field(v) for v in node)
    return False


def _with_purpose(node: Any) -> None:
    """Thêm `purpose` cho tham chiếu hũ để dành (có `code` và `color_key`), như Lambda mới đọc từ cột `jars.purpose`. Cột chỉ nhận
    giá trị ở hũ `saving` (CHECK của 0057), nên hũ có `kind` khác thì không có."""
    if isinstance(node, dict):
        is_jar = isinstance(node.get("code"), str) and "color_key" in node
        if is_jar and node["code"] in PURPOSES and node.get("kind", "saving") == "saving":
            node["purpose"] = PURPOSES[node["code"]]
        for v in node.values():
            _with_purpose(v)
    elif isinstance(node, list):
        for v in node:
            _with_purpose(v)


def _with_window(timeline: dict[str, Any]) -> None:
    """`obligations_before_payday` của hũ Nghĩa vụ, dựng bằng `obligation_window` như `blocks.py` (dự báo) và `scenario.py` (what-if:
    cả đường trước và đường sau)."""
    if timeline.get("jar", {}).get("code") != DEFAULT_OBLIGATION_JAR:
        return
    payday = timeline["payday"]["date"]
    opening = timeline["start_balance_vnd"]
    events = timeline.get("events") or []
    timeline["obligations_before_payday"] = obligation_window(
        events,
        payday,
        {d["date"]: d["p50_vnd"] for d in timeline["days"]},
        opening_balance_vnd=opening,
    )
    after = (timeline.get("compare") or {}).get("after")
    if after is not None:
        after["obligations_before_payday"] = obligation_window(
            after.get("events") or events, payday, {d["date"]: d["p50_vnd"] for d in after["days"]},
            opening_balance_vnd=opening,
        )  # fmt: skip


def new_lambda_payload(tool: str, payload: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(payload)
    data = out.get("data") or {}
    if tool == "get_jar_balances":
        if not all("kind" in j for j in data["jars"]):
            data = _with_ledger_columns(out)["data"]
            out["data"] = data
        data["jars"].append(
            {
                "code": "quy_don", "name": "Quỹ dồn", "color_key": "teal", "icon_key": "calendar", "balance_vnd": 0,
                "split_percent": 0, "kind": "saving", "purpose": "sinking", "goal_vnd": 920_000, "goal_date": "2027-01-03",
                "sinking_items": [{"name": "Tết", "amount_vnd": 920_000, "needed_date": "2027-01-03"}],
            }
        )  # fmt: skip
    _with_purpose(data)
    if tool == "get_forecast":
        _with_window(data)
    if tool == "run_scenario":
        for t in data.get("timelines", []):
            _with_window(t)
    if tool == "optimize_allocation":
        _with_recent_spend(data)
    return out


def _with_recent_spend(plan: dict[str, Any]) -> None:
    """`recent_spend` của Lambda forecast mới (#39, GG): chỉ ở dòng hũ chi; mức nền và cờ chi cao bất thường tùy chọn như Lambda phát. Từ
    26/11 tối (II) dòng có đợt chi tăng còn có ngày bắt đầu, cờ đã xác nhận đổi hành vi và ngày dự báo hũ cạn (đều tùy chọn)."""
    for k, line in enumerate(x for x in plan["lines"] if x["kind"] == "spending"):
        recent = {"recent_monthly_vnd": line["current_monthly_vnd"], "keep_floor_vnd": line["current_monthly_vnd"] // 2}
        recent["unusually_high"] = k == 0
        if k == 0:
            recent["baseline_monthly_vnd"] = line["current_monthly_vnd"] // 3
            recent.update(high_since="2026-11-07", change_confirmed=True, runout_date="2026-11-23")
        line["recent_spend"] = recent


@pytest.fixture(scope="module")
def validators() -> dict[str, Draft202012Validator]:
    registry = build_registry()
    return {
        tool: Draft202012Validator(
            {
                "$ref": f"{BASE}/tools/{RESULT_FILE[tool]}.results.schema.json#/$defs/{RESULT_DEF[tool]}"
            },
            registry=registry,
        )
        for tool in READERS
    }


def _schema_errors(validator: Draft202012Validator, payload: dict[str, Any]) -> list[str]:
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    return [f"{list(e.path)}: {e.message}" for e in errors[:3]]


def test_moi_bo_doc_co_fixture():
    assert {p.values[0] for p in CASES} == set(READERS)


@pytest.mark.parametrize(("tool", "label", "payload"), CASES)
def test_runtime_moi_doc_duoc_ket_qua_cua_lambda_cu(tool, label, payload, validators):
    assert not _has_new_field(payload), "dạng cũ không được có trường mới của #39"
    assert not _schema_errors(validators[tool], payload)
    outcome = _outcome(tool, payload)
    assert outcome.kind in (ToolKind.OK, ToolKind.NEEDS_CONFIRMATION)
    READERS[tool](outcome)


@pytest.mark.parametrize(("tool", "label", "payload"), CASES)
def test_runtime_moi_doc_duoc_ket_qua_cua_lambda_moi(tool, label, payload, validators):
    new = new_lambda_payload(tool, payload)
    assert not _schema_errors(validators[tool], new)
    READERS[tool](_outcome(tool, new))


def test_dang_moi_that_su_co_truong_moi():
    """Bộ dựng dạng mới đặt đúng các trường mới (không thì test trên chỉ chạy lại dạng cũ), kể cả khung khoản đến hạn có khoản."""
    seen: set[str] = set()
    windows = []
    for p in CASES:
        tool, _, payload = p.values
        new = new_lambda_payload(tool, payload)
        text = json.dumps(new)
        seen |= {f for f in NEW_FIELDS if f'"{f}"' in text}
        if tool == "get_forecast" and "obligations_before_payday" in new["data"]:
            windows.append(new["data"]["obligations_before_payday"])
    assert {"purpose", "sinking_items", "obligations_before_payday", "recent_spend", "high_since", "change_confirmed"} <= seen
    assert any(w["items"] for w in windows)
    # `runout_date` của dữ kiện đợt chi tăng (tên trùng trường sẵn có của dự báo nên kiểm riêng trong `recent_spend`)
    plan = new_lambda_payload("optimize_allocation", _load("optimize_allocation.ok.json"))
    assert any("runout_date" in (x.get("recent_spend") or {}) for x in plan["data"]["lines"])


def test_purpose_chi_o_hu_de_danh():
    """Ledger phát `purpose` từ cột `jars.purpose`, CHECK của 0057 chỉ cho hũ `saving`; dạng mới theo đúng luật đó."""
    new = new_lambda_payload("get_jar_balances", _load("get_jar_balances.ok.json"))
    jars = new["data"]["jars"]
    assert all(j.get("kind") for j in jars)
    assert {j["code"] for j in jars if "purpose" in j} == {"du_lich", "du_phong", "quy_don"}
    assert all(j["kind"] == "saving" for j in jars if "purpose" in j)


def test_get_roadmap_doc_bang_model_cua_turn():
    for path in _fixtures("get_roadmap"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for p in (payload, new_lambda_payload("get_roadmap", payload)):
            Roadmap.model_validate(p["data"])


def test_khoi_dung_tu_ket_qua_moi_giu_truong_moi():
    """Trường mới không bị bỏ khi dựng khối (giao diện nhận `purpose`, `sinking_items` và khung khoản đến hạn trước kỳ lương)."""
    jars = new_lambda_payload("get_jar_balances", _load("get_jar_balances.ok.json"))
    block = T.jar_summary_block(_outcome("get_jar_balances", jars), TRACE)
    assert any(j.purpose == "sinking" and j.sinking_items for j in block.data.jars)
    assert next(j for j in block.data.jars if j.code == "du_phong").purpose == "buffer"
    fc = new_lambda_payload("get_forecast", _as_obligation_jar(_load("get_forecast.ok.json")))
    fblock = T.forecast_block(_outcome("get_forecast", fc), TRACE)
    assert isinstance(fblock, B.ForecastTimelineBlock)
    window = fblock.data.obligations_before_payday
    assert window is not None
    assert [i.label for i in window.items] == [
        i["label"] for i in fc["data"]["obligations_before_payday"]["items"]
    ]


# --- phong bì lỗi: có và không có `field` -----------------------------------------------------
PAY_JAR_ERRORS = [
    ("affordability_check", "affordability_check.error_pay_jar_required.json"),
    ("run_scenario", "run_scenario.error_pay_jar_required.json"),
    ("update_profile", "update_profile.error_pay_jar_required.json"),
]


def test_fixture_loi_thieu_hu_tra_du_bo():
    assert {p.name for p in FIXTURES.glob("*.error_pay_jar_required.json")} == {
        name for _, name in PAY_JAR_ERRORS
    }


@pytest.mark.parametrize(("tool", "name"), PAY_JAR_ERRORS)
def test_loi_thieu_hu_tra_co_field_thi_hoi_hu_tra(tool, name, validators):
    """Lambda mới: lỗi thiếu hũ trả có `field: "pay_jar"`, Runtime mới hỏi hũ trả."""
    new = _load(name)
    assert new["field"] == PAY_JAR_FIELD
    assert not _schema_errors(validators[tool], new)
    outcome = _outcome(tool, new)
    assert outcome.kind is ToolKind.TOOL_ERROR
    assert outcome.code == new["code"] and outcome.message == new["message"]
    assert outcome.error_field == PAY_JAR_FIELD and asks_pay_jar(outcome)


@pytest.mark.parametrize(("tool", "name"), PAY_JAR_ERRORS)
def test_loi_khong_co_field_thi_hien_loi_khong_hoi_hu_tra(tool, name, validators):
    """Phong bì lỗi kiểu Lambda cũ (không có `field`, cùng câu chữ): vẫn là lỗi tool đọc được, Runtime mới không đoán từ câu chữ.

    Ledger `ed95134` không bao giờ phát lỗi thiếu hũ trả (lùi về hũ chi đầu tiên), nên giữa hai lần deploy không có ca nào mất câu hỏi."""
    old = {k: v for k, v in _load(name).items() if k != "field"}
    assert not _schema_errors(validators[tool], old)
    outcome = _outcome(tool, old)
    assert outcome.kind is ToolKind.TOOL_ERROR
    assert outcome.code == old["code"] and outcome.message == old["message"]
    assert outcome.error_field is None and not asks_pay_jar(outcome)


@pytest.mark.parametrize("bad", ["date", "Pay_Jar", "pay jar", 7, None, ["pay_jar"]])
def test_field_khac_hoac_sai_dang_khong_hoi_hu_tra(bad):
    """`field` gắn tham số khác (lỗi ngày sai...) hoặc sai dạng: vẫn là lỗi tool, không hỏi hũ trả, không thành lệch hợp đồng."""
    payload = {**_load("affordability_check.error_pay_jar_required.json"), "field": bad}
    outcome = _outcome("affordability_check", payload)
    assert outcome.kind is ToolKind.TOOL_ERROR and not asks_pay_jar(outcome)
    assert outcome.error_field == ("date" if bad == "date" else None)


def test_moi_fixture_loi_cu_doc_duoc_va_khong_hoi_hu_tra():
    """Mọi fixture lỗi không có `field` (dạng Lambda cũ) đọc thành lỗi tool có mã và câu, không hỏi hũ trả."""
    olds = [
        p
        for p in FIXTURES.glob("*.error*.json")
        if "field" not in json.loads(p.read_text(encoding="utf-8"))
    ]
    assert olds
    for path in olds:
        payload = json.loads(path.read_text(encoding="utf-8"))
        outcome = classify_result(f"x___{path.name.split('.')[0]}", _mcp(payload))
        assert outcome.kind is ToolKind.TOOL_ERROR, path.name
        assert (
            outcome.message == payload["message"]
            and outcome.error_field is None
            and not asks_pay_jar(outcome)
        )
