"""Zip Lambda ledger mang theo SDK đủ mới cho AgentCore Memory (phase 5): requirements ghim boto3/botocore, lệnh build giữ boto.

`scripts/build_lambda.py` mặc định gỡ boto3/botocore khỏi zip (dùng bản của runtime Lambda, tùy phiên bản runtime và Region). REST
`/memory*` và "Xóa dữ liệu của tôi" gọi `ListMemoryRecords(namespacePath=...)`, có từ botocore 1.42.90 (CHANGELOG của botocore).
"""

from __future__ import annotations

import re

from conftest import REPO

REQ = REPO / "gateway" / "tools" / "ledger" / "requirements.txt"
TOOLS_STACK = REPO / "infra-cdk" / "lib" / "tools-stack.ts"
NAMESPACE_PATH_SINCE = (1, 42, 90)


def pins() -> dict[str, tuple[int, ...]]:
    out = {}
    for line in REQ.read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"\s*(boto3|botocore)==([0-9]+(?:\.[0-9]+)*)\s*", line)
        if m:
            out[m.group(1)] = tuple(int(x) for x in m.group(2).split("."))
    return out


def ledger_build_command() -> str:
    src = TOOLS_STACK.read_text(encoding="utf-8")
    m = re.search(r"export const LEDGER_BUILD_COMMAND =\s*((?:'[^']*'\s*\+?\s*)+);", src)
    assert m, "thiếu LEDGER_BUILD_COMMAND trong tools-stack.ts"
    return "".join(re.findall(r"'([^']*)'", m.group(1)))


def test_requirements_ledger_ghim_boto3_va_botocore_co_namespace_path():
    p = pins()
    assert set(p) == {"boto3", "botocore"}, p
    assert p["botocore"] >= NAMESPACE_PATH_SINCE
    assert p["boto3"][:2] == p["botocore"][:2]  # boto3 1.x.y đòi botocore cùng nhánh 1.x


def test_lenh_build_ledger_giu_boto_va_duoc_dung_trong_loi_thieu_zip():
    cmd = ledger_build_command()
    assert cmd.startswith("uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 ")
    assert "--keep-boto" in cmd.split()
    for extra in ("data/personas:personas", "gateway/tools/audit/yofina_audit:yofina_audit"):
        assert f"--extra {extra}" in cmd
    assert "Chạy: ${LEDGER_BUILD_COMMAND}" in TOOLS_STACK.read_text(encoding="utf-8")


def test_tai_lieu_ghi_cung_lenh_build_ledger():
    cmd = ledger_build_command()
    for doc in ("scripts/README.md", "infra-cdk/README.md", "gateway/tools/ledger/README.md"):
        assert cmd in (REPO / doc).read_text(encoding="utf-8"), doc


def test_botocore_cua_moi_truong_test_co_namespace_path():
    """Cùng bản đã ghim (uv.lock): client `bedrock-agentcore` nhận `namespacePath` (điều `memory_store._check_sdk` kiểm lúc chạy)."""
    import boto3
    import botocore

    assert tuple(int(x) for x in botocore.__version__.split(".")[:3]) == pins()["botocore"]
    client = boto3.session.Session().client("bedrock-agentcore", region_name="ap-southeast-1")
    members = client.meta.service_model.operation_model("ListMemoryRecords").input_shape.members
    assert "namespacePath" in members
