"""Chạy phía TypeScript của hợp đồng: Zod sinh ra không lệch schema và qua cùng fixture.

Cần Node và `npm install` ở gốc repo (cài zod). Thiếu Node hoặc zod thì bỏ qua (skip) kèm lý do,
vì test Python vẫn đủ để khóa hợp đồng; CI sau này phải cài đủ để các test này chạy.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest
from conftest import REPO

NODE = shutil.which("node")
HAS_ZOD = (REPO / "node_modules" / "zod" / "package.json").exists()

pytestmark = pytest.mark.skipif(
    not (NODE and HAS_ZOD), reason="cần Node và `npm install` ở gốc repo (zod) để chạy test Zod"
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [NODE or "node", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )


def test_zod_sinh_ra_khop_json_schema():
    r = run("scripts/gen_contracts.mjs", "--check")
    assert r.returncode == 0, r.stdout + r.stderr


def test_zod_qua_cac_fixture_dung_chung():
    tests = sorted(
        p.relative_to(REPO).as_posix() for p in (REPO / "tests/unit/ts").glob("*.test.mjs")
    )
    assert tests
    r = run("--test", *tests)
    assert r.returncode == 0, r.stdout + r.stderr
