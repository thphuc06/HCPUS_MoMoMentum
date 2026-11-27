"""Gateway đề xuất tỷ lệ dùng dữ liệu REST và bản xem trước save_jars thật."""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest
from ledger_fakes import KEY, SETTINGS, Clock, MemoryJtiStore, gateway_context

from yofina_core.blocks import ConfirmActionData
from yofina_core.confirm import ConfirmService, decode_token
from yofina_core.errors import ErrorCode, YofinaError
from yofina_ledger.gateway_api import handle_gateway
from yofina_ledger.repo import JarView, LedgerRepo
from yofina_ledger.service import LedgerService

USER = "sub-minh"
CONTEXT = gateway_context("ledger___propose_jar_split")
TET = {"name": "Tết", "amount_vnd": 5_000_000, "needed_date": "2027-02-05"}


class ReadOnlyRepo:
    """Chỉ có cổng đọc. Gọi ghi vào repo làm test thất bại ngay."""

    def __init__(self, status):
        rows = [
            ("chi_hang_ngay", "Chi hằng ngày", "spending", None, 42),
            ("nghia_vu", "Nghĩa vụ", "obligation", None, 33),
            ("du_phong", "Dự phòng", "saving", "buffer", 25),
        ]
        if status == "aligned":
            rows[0] = (*rows[0][:4], 14)
            rows.append(("quy_don", "Quỹ dồn", "saving", "sinking", 28))
        self.jars = [
            dict(code=code, name=name, kind=kind, purpose=purpose, split_percent=share,
                 color_key="teal", icon_key="wallet", balance_vnd=0, sort_order=i)
            for i, (code, name, kind, purpose, share) in enumerate(rows)
        ]  # fmt: skip
        if status == "aligned":
            self.jars[-1]["sinking_items"] = [dict(TET)]
        self.salary = 2_000_000 if status == "infeasible" else 9_000_000

    def jar_view(self, user_id):
        assert user_id == USER
        return JarView(-19, tuple(self.jars))

    def user_row(self, user_id):
        assert user_id == USER
        return {"monthly_salary_vnd": self.salary, "payday_day": 5}

    def reference_templates(self):
        return [
            dict(code="quy_don", name="Quỹ dồn", color_key="teal", icon_key="calendar", kind="saving",
                 purpose="sinking", default_split_percent=0, is_default=False, sort_order=0)
        ]  # fmt: skip

    def reference_tx_types(self):
        return []

    def spend_context(self, user_id, now, tz, window_days):
        return []

    def list_obligations(self, user_id, *, status, limit):
        return []

    def salary_events(self, user_id, status):
        return []

    def jars_usage(self, user_id):
        return []


def service_for(status, *, allow_signing=False):
    repo, clock = ReadOnlyRepo(status), Clock()
    used_tokens = MemoryJtiStore()

    def signing_key():
        if allow_signing:
            return KEY
        pytest.fail("Tool đọc không được yêu cầu khóa để ký token.")

    confirm = ConfirmService(
        signing_key, used_tokens, ttl_seconds=120, max_ttl_seconds=120, clock=clock
    )
    return LedgerService(repo, confirm, SETTINGS, clock=clock), repo, used_tokens


@pytest.mark.parametrize("status", ["proposed", "infeasible", "aligned"])
def test_propose_jar_split_matches_rest_and_previews_without_writes(status):
    service, repo, tokens = service_for(status)
    before = deepcopy(repo.jars)
    body = {"sinking_items": [TET]}
    rest = service.split_proposal_response(USER, body)
    assert rest["status"] == status

    result = handle_gateway({"user_id": USER, **body}, CONTEXT, service)
    assert result["status"] == "OK", result
    assert (result["app_date"], result["as_of"]) == (rest["app_date"], rest["as_of"])
    data = result["data"]
    assert {k: v for k, v in data.items() if k != "confirm"} == rest
    if status == "proposed":
        confirm = ConfirmActionData.model_validate(data["confirm"])
        assert confirm.tool == "save_jars"
        assert confirm.params == rest["params"]
        preview = service.needs_confirmation_for(
            USER, "save_jars", rest["params"], trace_id="b1test123"
        )
        assert data["confirm"] == preview["data"]
    else:
        assert "confirm" not in data
    assert repo.jars == before
    assert not tokens.used


def save_jars_changes(service, jars):
    result = service.needs_confirmation_for(USER, "save_jars", {"jars": jars}, trace_id="b1test123")
    return result["data"]["changes"]


def test_save_jars_previews_sinking_amount_change_without_new_ratio():
    service, repo, _ = service_for("aligned")
    jars = deepcopy(repo.jars)
    jars[-1]["sinking_items"] = [{**TET, "amount_vnd": 4_990_000}]
    changes = save_jars_changes(service, jars)
    assert {
        "label": "Khoản Tết",
        "before": "5.000.000 ₫",
        "after": "4.990.000 ₫, cần trước 05/02",
    } in changes
    assert any(line["label"] == "Lý do: hũ Quỹ dồn" for line in changes)
    assert {"label": "Danh sách hũ", "after": "không đổi"} not in changes


def test_save_jars_previews_goal_amount_and_date_on_one_line():
    service, repo, _ = service_for("aligned")
    repo.jars.append(
        {
            **repo.jars[-1],
            "code": "du_lich",
            "name": "Du lịch",
            "purpose": "goal",
            "split_percent": 0,
            "sort_order": 4,
            "sinking_items": [],
            "goal_vnd": 10_000_000,
            "goal_date": "2027-06-01",
        }
    )
    jars = deepcopy(repo.jars)
    jars[-1].update(goal_vnd=12_000_000, goal_date="2027-07-01")
    assert save_jars_changes(service, jars) == [
        {"label": "Du lịch", "after": "mục tiêu 10.000.000 ₫ → 12.000.000 ₫, hạn 01/06 → 01/07"}
    ]


def test_save_jars_previews_identical_jars_as_unchanged():
    service, repo, _ = service_for("aligned")
    assert save_jars_changes(service, deepcopy(repo.jars)) == [
        {"label": "Danh sách hũ", "after": "không đổi"}
    ]


def test_save_jars_keeps_new_sinking_jar_when_preview_exceeds_twenty_lines():
    service, repo, _ = service_for("proposed")
    repo.jars.extend(
        {
            **repo.jars[-1],
            "code": f"quy_{i}",
            "name": f"Quỹ {i}",
            "purpose": "sinking",
            "split_percent": 0,
            "sort_order": i + 3,
            "sinking_items": [TET],
        }
        for i in range(16)
    )
    jars = deepcopy(repo.jars)
    jars[0]["split_percent"] = 16
    for jar in jars[3:]:
        jar["split_percent"] = 1
    jars.append({**jars[-1], "code": "quy_don", "name": "Quỹ dồn", "split_percent": 10})

    changes = save_jars_changes(service, jars)
    assert len(changes) == 20
    assert any(line["label"] == "Hũ mới: Quỹ dồn" for line in changes)


def test_save_jars_preview_version_ignores_row_order_and_tracks_commitments():
    service, repo, _ = service_for("aligned")

    def version():
        params = {"jars": deepcopy(repo.jars)}
        preview = service.needs_confirmation_for(USER, "save_jars", params, trace_id="b1test123")
        return preview["data"]["params"]["base_version"]

    original = version()
    assert isinstance(original, str) and original
    repo.jars.reverse()
    assert version() == original
    repo.jars[0]["sinking_items"] = [{**TET, "amount_vnd": 4_990_000}]
    assert version() != original


def test_propose_jar_split_version_is_shared_with_rest_proposal():
    service, _, _ = service_for("proposed")
    body = {"sinking_items": [TET]}
    proposal = service.split_proposal_response(USER, body)
    result = handle_gateway({"user_id": USER, **body}, CONTEXT, service)
    version = proposal["params"]["base_version"]
    assert version
    assert result["data"]["confirm"]["params"]["base_version"] == version


def test_save_jars_rest_confirmation_signs_the_version_from_the_preview():
    service, repo, _ = service_for("aligned", allow_signing=True)
    params = {"jars": deepcopy(repo.jars)}
    expected = service.needs_confirmation_for(USER, "save_jars", params, trace_id="b1test123")[
        "data"
    ]
    issued, _ = service.issue_confirmation_with_preview(
        USER, tool="save_jars", params=params, client_params_hash=None, trace_id="b1test123"
    )
    assert issued.params["base_version"] == expected["params"]["base_version"]
    assert issued.params_hash == expected["params_hash"]
    token_payload = decode_token(
        issued.token, key=KEY, now_epoch=service.now().timestamp(), max_ttl_seconds=120
    )
    assert token_payload.h == expected["params_hash"]
    with pytest.raises(YofinaError) as exc:
        service.apply_action(
            USER,
            "save_jars",
            {**issued.params, "base_version": "0" * 16},
            issued.token,
            trace_id="b1test123",
            channel="rest",
            source_tool="rest:POST /actions",
        )
    assert exc.value.code == ErrorCode.PARAMS_MISMATCH
    assert exc.value.message == "Tham số khác với tham số bạn đã xác nhận; hãy xác nhận lại."


def test_save_jars_rejects_stale_version_against_rows_read_in_write_transaction():
    _, snapshot, _ = service_for("aligned")
    db = MagicMock()
    tx = db.transaction.return_value.__enter__.return_value
    locked_rows = snapshot.jars

    def execute(sql, _):
        return locked_rows if "FROM jars j" in sql else []

    tx.execute.side_effect = execute
    with pytest.raises(YofinaError) as exc:
        LedgerRepo(db).write_save_jars(
            USER,
            norm={"jars": locked_rows, "base_version": "0" * 16},
            now=Clock()(),
            app_date=Clock()().date(),
            audit={"trace_id": "b1test123", "event_type": "save_jars", "params": {}, "details": {}},
            claim=None,
            tool="save_jars",
        )
    assert exc.value.code == ErrorCode.PARAMS_MISMATCH
    assert exc.value.message == "Danh sách hũ đã thay đổi sau khi tạo thẻ này, hãy xem lại."


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({}, id="missing"),
        pytest.param({"sinking_items": []}, id="empty"),
        pytest.param(
            {"sinking_items": [{**TET, "name": f"Khoản {i}"} for i in range(6)]}, id="six"
        ),
        pytest.param({"sinking_items": [{**TET, "amount_vnd": -1}]}, id="negative"),
        pytest.param({"sinking_items": [{**TET, "amount_vnd": "1000"}]}, id="numeric-string"),
        pytest.param({"sinking_items": [{**TET, "needed_date": "2026-11-20"}]}, id="past"),
        pytest.param({"sinking_items": [{**TET, "needed_date": "2026-11-21"}]}, id="today"),
        pytest.param(
            {"sinking_items": [{**TET, "needed_date": "2027-11-22"}]}, id="beyond-horizon"
        ),
        pytest.param({"sinking_items": [{**TET, "name": ""}]}, id="empty-name"),
    ],
)
def test_propose_jar_split_invalid_inputs(body):
    service, _, _ = service_for("proposed")
    result = handle_gateway({"user_id": USER, **body}, CONTEXT, service)
    assert result["status"] == "ERROR" and result["code"] == "PARAMS_INVALID"
    assert result["message"] != "Tool không tồn tại."
