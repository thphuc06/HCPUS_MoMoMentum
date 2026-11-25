"""scripts/seed_demo.py: gán nhóm Cognito cho tài khoản demo (issue #17), bằng Cognito giả, không gọi AWS.

Tài khoản giám khảo không bao giờ ở nhóm `ops` (nhóm này xem trace của mọi người dùng); chạy lại script gỡ `ops`
khỏi tài khoản giám khảo đang có nó. Chỉ tài khoản vận hành khai trong `ops_accounts` của accounts.json ở nhóm `ops`.
"""

from __future__ import annotations

import importlib.util
import json
import sys

import pytest
from botocore.exceptions import ClientError
from conftest import REPO

POOL = "ap-southeast-1_TEST"
CFG = json.loads((REPO / "data" / "personas" / "accounts.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sd():
    scripts = str(REPO / "scripts")
    sys.path.insert(0, scripts)  # seed_demo nạp _yofina, _demo_auth theo tên
    try:
        spec = importlib.util.spec_from_file_location(
            "seed_demo", REPO / "scripts" / "seed_demo.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.path.remove(scripts)


class FakeCognito:
    """Đủ các lệnh seed_demo dùng; giữ nhóm của từng user trong bộ nhớ và ghi lại lệnh GHI."""

    def __init__(self, groups: dict[str, set[str]], existing_groups: set[str]):
        self.groups = {u: set(g) for u, g in groups.items()}
        self.existing = set(existing_groups)
        self.writes: list[tuple] = []

    def create_group(self, *, UserPoolId, GroupName, Description):
        assert UserPoolId == POOL
        if GroupName in self.existing:
            raise ClientError({"Error": {"Code": "GroupExistsException"}}, "CreateGroup")
        self.existing.add(GroupName)
        self.writes.append(("create_group", GroupName))

    def admin_list_groups_for_user(self, *, UserPoolId, Username):
        assert UserPoolId == POOL
        return {
            "Groups": [{"GroupName": g} for g in sorted(self.groups.setdefault(Username, set()))]
        }

    def admin_add_user_to_group(self, *, UserPoolId, Username, GroupName):
        assert UserPoolId == POOL and GroupName in self.existing
        self.groups.setdefault(Username, set()).add(GroupName)
        self.writes.append(("add", Username, GroupName))

    def admin_remove_user_from_group(self, *, UserPoolId, Username, GroupName):
        assert UserPoolId == POOL
        self.groups[Username].discard(GroupName)
        self.writes.append(("remove", Username, GroupName))


class FakeSsm:
    def get_parameter(self, *, Name, WithDecryption):
        assert Name == "/yofina/auth/user-pool-id"
        return {"Parameter": {"Value": POOL}}


class FakeSession:
    def __init__(self, idp: FakeCognito):
        self.clients = {"cognito-idp": idp, "ssm": FakeSsm()}

    def client(self, name):
        return self.clients[name]


def email(name: str) -> str:
    return f"{name}@demo.yofina.example"


def accounts(names) -> dict:
    return {n: {"email": email(n)} for n in names}


def hom_nay() -> FakeCognito:
    """Trạng thái pool trên AWS ngày 25/11 (HANDOFF, docs/aws-resources.md): `minh`, `giamkhao1` thuộc `ops`."""
    mapping = CFG["demo_accounts"]
    groups = {email(n): {CFG["group_prefix"] + p} for n, p in mapping.items()}
    groups[email("minh")].add("ops")
    groups[email("giamkhao1")].add("ops")
    existing = {"ops"} | {CFG["group_prefix"] + p for p in mapping.values()}
    return FakeCognito(groups, existing)


def test_chay_lai_go_ops_khoi_giam_khao_va_giu_ops_cho_tai_khoan_van_hanh(sd):
    idp = hom_nay()
    mapping = CFG["demo_accounts"]
    sd.ensure_groups(
        FakeSession(idp),
        mapping,
        CFG["group_prefix"],
        accounts(mapping),
        ops_accounts=CFG["ops_accounts"],
    )
    for n in ("giamkhao1", "giamkhao2", "giamkhao3"):
        assert idp.groups[email(n)] == {"persona-minh"}
    assert idp.groups[email("minh")] == {"persona-minh", "ops"}
    assert ("remove", email("giamkhao1"), "ops") in idp.writes
    assert not [
        w for w in idp.writes if w[0] == "add" and w[2] == "ops"
    ]  # minh đã có, không thêm lại


def test_giam_khao_trong_ops_accounts_bi_tu_choi_truoc_moi_lenh_ghi(sd):
    idp = hom_nay()
    before = {u: set(g) for u, g in idp.groups.items()}
    with pytest.raises(SystemExit, match="giamkhao2"):
        sd.ensure_groups(
            FakeSession(idp),
            CFG["demo_accounts"],
            CFG["group_prefix"],
            accounts(CFG["demo_accounts"]),
            ops_accounts=["minh", "giamkhao2"],
        )
    assert idp.writes == [] and idp.groups == before


def test_chi_nap_mot_tai_khoan_giam_khao_van_go_ops_va_khong_dung_tai_khoan_khac(sd):
    # `seed_demo.py giamkhao1` hoặc `seed_persona.py giamkhao1 --apply` chỉ truyền một tài khoản
    idp = hom_nay()
    sd.ensure_groups(
        FakeSession(idp),
        {"giamkhao1": "minh"},
        CFG["group_prefix"],
        accounts(["giamkhao1"]),
        ops_accounts=CFG["ops_accounts"],
    )
    assert idp.writes == [("remove", email("giamkhao1"), "ops")]
    assert "ops" in idp.groups[email("minh")]


def test_tai_khoan_van_hanh_chua_co_ops_thi_duoc_them_va_accounts_json_khong_co_giam_khao(sd):
    assert CFG["ops_accounts"] == ["minh"]  # minh không đưa giám khảo (giám khảo dùng giamkhao1-3)
    assert set(CFG["ops_accounts"]) <= set(CFG["demo_accounts"])
    idp = FakeCognito({email("minh"): {"persona-minh"}}, {"ops", "persona-minh"})
    sd.ensure_groups(
        FakeSession(idp),
        {"minh": "minh"},
        CFG["group_prefix"],
        accounts(["minh"]),
        ops_accounts=CFG["ops_accounts"],
    )
    assert idp.writes == [("add", email("minh"), "ops")]
