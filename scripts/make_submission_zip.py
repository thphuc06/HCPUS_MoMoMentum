"""Đóng `.zip` mã nguồn cho bộ nộp bài (issue #36): nén đúng các tệp ĐÃ COMMIT ở một commit, sau khi quét bí mật.

    uv run python scripts/make_submission_zip.py --out ..\\yofina-source.zip            # từ HEAD
    uv run python scripts/make_submission_zip.py --out D:\\nop\\yofina.zip --ref p6/rc   # từ một commit hoặc nhánh khác
    uv run python scripts/make_submission_zip.py --out ..\\x.zip --scan-cmd "gitleaks git . --redact --exit-code 1"

Các bước, dừng ở bước đầu tiên lỗi và KHÔNG để lại tệp zip nào:

1. Tệp ra phải nằm NGOÀI repo (repo public; `*.zip` cũng bị `.gitignore` bỏ qua nên dễ quên mất tệp trong cây làm việc).
2. Quét bí mật bằng một lệnh bên ngoài, chạy ở gốc repo; mã thoát khác 0 là có phát hiện hoặc quét hỏng, và script dừng. Mặc định:
   `scripts/scan_repo.py --ref <commit>` (việc B2 của phase 6: quét đúng nội dung commit sắp nén, danh sách cho phép lấy từ
   `.gitleaks.toml` của commit đó) nếu có, không thì `gitleaks git` với `.gitleaks.toml` như job `secrets` của CI;
   không có công cụ nào thì dừng (không nén khi chưa quét). `--scan-cmd` thay lệnh mặc định. Script không in lại kết quả quét: bộ
   quét tự in (scan_repo.py chỉ in giá trị đã che, gitleaks chạy với `--redact`).
3. `git archive` của commit (không lẫn tệp chưa commit hay đang sửa dở), `core.autocrlf=false` nên byte trong zip là byte đã commit.
4. Bỏ các đường dẫn ở `EXCLUDED_DIR_NAMES`, `EXCLUDED_PREFIXES`, và tệp `.env*` (trừ `.env.example`); ghi zip vào tệp tạm cạnh
   tệp ra rồi đổi tên, nên lỗi giữa chừng không để lại zip dở.

Mọi tệp trong zip nằm dưới một thư mục gốc `yofina-foresight-<sha ngắn>/`. Không gọi AWS.
"""

from __future__ import annotations

import argparse
import io
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]

#: Thư mục bị bỏ ở mọi độ sâu (môi trường ảo, gói Node). Thư mục tên bắt đầu bằng `.venv-` cũng bị bỏ.
EXCLUDED_DIR_NAMES = frozenset({".venv", "venv", "node_modules", "__pycache__"})
#: Đường dẫn bị bỏ tính từ gốc repo: kết quả eval thô (chứa dữ liệu persona và câu trả lời của model) và ảnh thật tải từ web cho
#: bộ OCR (`evals/ingest/real/`, xem `evals/ingest/README.md`). Các thư mục này đã bị `.gitignore` bỏ; lọc thêm ở đây phòng khi ai
#: đó `git add -f`.
EXCLUDED_PREFIXES = ("evals/results/", "evals/ingest/results/", "evals/ingest/real/")
#: Tệp môi trường được giữ (mẫu không có giá trị thật).
ENV_ALLOWED = frozenset({".env.example"})


class SubmissionError(Exception):
    """Không tạo được zip; thông điệp nói bước nào dừng."""


@dataclass
class SubmissionResult:
    out: Path
    commit: str
    files: int
    size_bytes: int
    excluded: list[str] = field(default_factory=list)


def is_excluded(rel: str) -> bool:
    """`rel` là đường dẫn POSIX tính từ gốc repo (không có thư mục gốc của zip)."""
    path = PurePosixPath(rel)
    for part in path.parts[:-1]:
        if part in EXCLUDED_DIR_NAMES or part.startswith(".venv-"):
            return True
    if any(rel.startswith(p) for p in EXCLUDED_PREFIXES):
        return True
    name = path.name
    return (name == ".env" or name.startswith(".env.")) and name not in ENV_ALLOWED


def _git(root: Path, *args: str) -> bytes:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip()
        raise SubmissionError(f"git {' '.join(args[:2])} lỗi: {msg}")
    return proc.stdout


def default_scan_cmd(root: Path, commit: str) -> list[str]:
    """Lệnh quét mặc định; không có công cụ nào thì `SubmissionError` (không nén khi chưa quét). `scripts/scan_repo.py --ref`
    quét đúng nội dung của commit sắp nén (không phải cây làm việc)."""
    scan_repo = root / "scripts" / "scan_repo.py"
    if scan_repo.is_file():
        return [sys.executable, str(scan_repo), "--ref", commit]
    gitleaks = shutil.which("gitleaks")
    if gitleaks:
        cmd = [
            gitleaks,
            "git",
            str(root),
            f"--log-opts=--full-history {commit}",
            "--redact",
            "--no-banner",
            "--exit-code",
            "1",
        ]
        config = root / ".gitleaks.toml"
        if config.is_file():
            cmd[3:3] = ["--config", str(config)]
        return cmd
    raise SubmissionError(
        "Không có công cụ quét bí mật: thiếu scripts/scan_repo.py và không thấy gitleaks trên PATH. "
        "Cài gitleaks hoặc truyền --scan-cmd; script không nén khi chưa quét."
    )


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def make_submission_zip(
    repo: Path, out: Path, *, ref: str = "HEAD", scan_cmd: Sequence[str] | None = None
) -> SubmissionResult:
    """Quét bí mật rồi nén các tệp đã commit ở `ref` vào `out` (ngoài repo). Lỗi ở bất kỳ bước nào: `SubmissionError`, không có
    tệp `out`."""
    root = Path(_git(Path(repo), "rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()
    out = Path(out).resolve()
    if _inside(out, root):
        raise SubmissionError(f"Tệp ra phải nằm ngoài repo ({root}); nhận {out}.")
    commit = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}").decode("ascii").strip()

    cmd = list(scan_cmd) if scan_cmd is not None else default_scan_cmd(root, commit)
    try:
        scan = subprocess.run(cmd, cwd=root)
    except OSError as exc:
        raise SubmissionError(f"Không chạy được lệnh quét bí mật {cmd[0]!r}: {exc}") from exc
    if scan.returncode != 0:
        raise SubmissionError(f"Quét bí mật báo lỗi (mã thoát {scan.returncode}); không tạo zip.")

    tar_bytes = _git(root, "-c", "core.autocrlf=false", "archive", "--format=tar", commit)
    prefix = f"yofina-foresight-{commit[:8]}/"
    excluded: list[str] = []
    files = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".yofina-zip-", suffix=".tmp", dir=out.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with (
            tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as tar,
            zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf,
        ):
            for member in tar:
                if not member.isfile():
                    continue
                if is_excluded(member.name):
                    excluded.append(member.name)
                    continue
                stamp = datetime.fromtimestamp(max(member.mtime, 315532800), UTC).timetuple()[:6]
                info = zipfile.ZipInfo(prefix + member.name, date_time=stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (member.mode & 0o777) << 16
                data = tar.extractfile(member)
                zf.writestr(info, data.read() if data else b"")
                files += 1
        os.replace(tmp, out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return SubmissionResult(
        out=out, commit=commit, files=files, size_bytes=out.stat().st_size, excluded=excluded
    )


def _split_cmd(text: str) -> list[str]:
    if os.name == "nt":
        return [
            t[1:-1] if len(t) >= 2 and t[0] == t[-1] == '"' else t
            for t in shlex.split(text, posix=False)
        ]
    return shlex.split(text)


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--out", type=Path, required=True, help="đường dẫn tệp .zip, phải nằm ngoài repo"
    )
    ap.add_argument("--ref", default="HEAD", help="commit, nhánh hoặc tag để nén (mặc định HEAD)")
    ap.add_argument(
        "--scan-cmd",
        default=None,
        help="lệnh quét bí mật thay cho mặc định; mã thoát khác 0 là dừng",
    )
    ap.add_argument("--repo", type=Path, default=REPO, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    scan_cmd = _split_cmd(args.scan_cmd) if args.scan_cmd else None
    try:
        res = make_submission_zip(args.repo, args.out, ref=args.ref, scan_cmd=scan_cmd)
    except SubmissionError as exc:
        print(f"DỪNG: {exc}", file=sys.stderr)
        return 1
    print(
        f"Commit {res.commit[:12]}: {res.files} tệp, bỏ {len(res.excluded)} tệp theo luật loại trừ."
    )
    print(f"Đã ghi {res.out} ({res.size_bytes / 1_000_000:.1f} MB).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
