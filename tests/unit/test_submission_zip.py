"""Bộ nộp bài (#36): `scripts/make_submission_zip.py` nén mã nguồn ĐÃ COMMIT, bỏ các đường dẫn bị loại, và không tạo zip khi
bước quét bí mật báo lỗi. Test dựng một repo git tạm (cần `git` trên PATH, như CI); bộ quét là một tiến trình Python trả mã thoát
0 hoặc 1, đi qua đúng đường `subprocess` của script."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

SCAN_OK = [sys.executable, "-c", "raise SystemExit(0)"]
SCAN_FINDINGS = [sys.executable, "-c", "raise SystemExit(1)"]

KEPT = {
    "README.md": "# demo\n",
    "agent/src/app.py": "print('ok')\n",
    "evals/golden/phase3.jsonl": "{}\n",
    "evals/ingest/manifest.json": "{}\n",
    "evals/ingest/synthetic/img/s01.png": "png\n",
    ".env.example": "YOFINA_REGION=\n",
}
EXCLUDED = {
    ".venv/lib/site.py": "x\n",
    "frontend/node_modules/pkg/index.js": "x\n",
    "evals/results/run-1.json": "{}\n",
    "evals/ingest/results/run-1.json": "{}\n",
    "evals/ingest/real/r01.jpg": "jpg\n",
    ".env": "SECRET=x\n",
    "frontend/.env.local": "X=1\n",
}


@pytest.fixture
def tool():
    path = REPO / "scripts" / "make_submission_zip.py"
    spec = importlib.util.spec_from_file_location("make_submission_zip", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
        yield mod
    finally:
        sys.modules.pop(spec.name, None)


def _git(cwd: Path, *args: str) -> None:
    ident = ["-c", "user.name=yofina-test", "-c", "user.email=", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", *ident, *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Repo tạm: mọi tệp KEPT và EXCLUDED đều được commit; sau commit có một tệp chưa theo dõi và một sửa chưa commit."""
    root = tmp_path / "repo"
    for rel, text in {**KEPT, **EXCLUDED}.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    _git(root, "init", "-q")
    _git(root, "add", "-f", "-A")
    _git(root, "commit", "-q", "-m", "init")
    (root / "chua_commit.txt").write_text("wip\n", encoding="utf-8")
    (root / "README.md").write_text("# sửa dở, chưa commit\n", encoding="utf-8")
    return root


def _entries(zip_path: Path) -> dict[str, bytes]:
    """Tên tệp trong zip, bỏ thư mục gốc chung, kèm nội dung."""
    with zipfile.ZipFile(zip_path) as z:
        out = {}
        for name in z.namelist():
            if name.endswith("/"):
                continue
            _, _, rel = name.partition("/")
            out[rel] = z.read(name)
        return out


def test_zip_chi_chua_tep_da_commit_va_khong_chua_duong_dan_bi_loai(tool, repo, tmp_path):
    out = tmp_path / "ngoai_repo" / "yofina.zip"

    tool.make_submission_zip(repo, out, scan_cmd=SCAN_OK)

    entries = _entries(out)
    assert set(entries) == set(KEPT)
    assert entries["README.md"].replace(b"\r\n", b"\n") == b"# demo\n"


def test_quet_bi_mat_bao_loi_thi_khong_tao_zip(tool, repo, tmp_path):
    out = tmp_path / "ngoai_repo" / "yofina.zip"

    with pytest.raises(tool.SubmissionError):
        tool.make_submission_zip(repo, out, scan_cmd=SCAN_FINDINGS)

    assert not out.exists()
    assert not out.parent.exists() or not any(out.parent.iterdir())  # không để lại tệp tạm


def test_tu_choi_ghi_zip_vao_trong_repo(tool, repo):
    out = repo / "build" / "yofina.zip"

    with pytest.raises(tool.SubmissionError):
        tool.make_submission_zip(repo, out, scan_cmd=SCAN_OK)

    assert not out.exists()
