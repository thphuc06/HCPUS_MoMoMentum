"""Gateway đề xuất tỷ lệ dùng dữ liệu REST và bản xem trước save_jars thật."""

from copy import deepcopy

import pytest
from ledger_fakes import SETTINGS, Clock, MemoryJtiStore, gateway_context

from yofina_core.blocks import ConfirmActionData
from yofina_core.confirm import ConfirmService
from yofina_ledger.gateway_api import handle_gateway
from yofina_ledger.repo import JarView
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


def service_for(status):
    repo, clock = ReadOnlyRepo(status), Clock()
    used_tokens = MemoryJtiStore()

    def signing_key():
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
