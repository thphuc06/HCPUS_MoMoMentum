# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Đóng gói Lambda/Runtime Python bằng uv, KHÔNG dùng Docker, ngay trên Windows.

    uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64
    uv run scripts/build_lambda.py agent --arch arm64 --name agent --no-core
    uv run scripts/build_lambda.py <thư mục nguồn> --arch x86_64 --requirements <file>
    uv run scripts/build_lambda.py gateway/tools/ledger --arch arm64 --extra data/personas:personas
    uv run scripts/build_lambda.py pipelines/forecast --arch arm64 --name forecast --slim \
        --extra ml/yofina_ml:yofina_ml --extra gateway/tools/ledger/yofina_ledger:yofina_ledger

`--extra NGUỒN[:ĐÍCH]` (lặp được) chép thêm một thư mục (đường dẫn tính từ gốc repo) vào bản build, ví dụ
dữ liệu persona seed để Lambda ledger đặt lại tài khoản demo; ĐÍCH mặc định là tên thư mục nguồn.

Kết quả (mặc định dưới build/, đã nằm trong .gitignore):
    build/lambda/<name>-<arch>/        thư mục đã giải nén (dùng cho lambda.Code.fromAsset(<thư mục>))
    build/lambda/<name>-<arch>.zip     zip có quyền 644/755 (dùng cho Code.fromAsset(<zip>) hoặc Runtime codeConfiguration)

Cách làm: `uv pip install --python-platform <aarch64|x86_64>-manylinux2014 --python-version 3.13 --only-binary=:all:
--target <thư mục>` cài wheel của nền tảng Linux đích ngay trên máy Windows (kỹ thuật của
spikes/agentcore-runtime-cors/make_zip.py). Thư viện chỉ có sdist (cần biên dịch) sẽ báo lỗi: chọn bản có wheel.

Phụ thuộc lấy từ --requirements, hoặc `<nguồn>/requirements.txt`, hoặc `[project].dependencies` trong `<nguồn>/pyproject.toml`.
Nếu libs/yofina_core tồn tại (và không có --no-core): chép gói `yofina_core` vào bản build và cài luôn phụ thuộc của nó.
boto3/botocore đã có sẵn trong runtime Lambda nên bị gỡ khỏi bản build (dùng --keep-boto để giữ).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):  # console Windows mặc định cp1252
    _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS = {"arm64": "aarch64-manylinux2014", "x86_64": "x86_64-manylinux2014"}
BOTO_PREFIXES = (
    "boto3",
    "botocore",
    "s3transfer",
    "jmespath",
    "python_dateutil",
    "dateutil",
    "six",
    "urllib3",
)
IGNORE_COPY = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    "tests",
    "test_*.py",
    ".venv",
    "node_modules",
    "requirements.txt",
    "uv.lock",
    ".pytest_cache",
)


def deps_of(pyproject: Path) -> list[str]:
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return list(data.get("project", {}).get("dependencies", []))


def collect_requirements(src: Path, explicit: Path | None) -> list[str]:
    if explicit:
        return [
            ln.strip()
            for ln in explicit.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        ]
    req = src / "requirements.txt"
    if req.is_file():
        return collect_requirements(src, req)
    pp = src / "pyproject.toml"
    return deps_of(pp) if pp.is_file() else []


def core_package_dir() -> tuple[Path, Path] | None:
    base = ROOT / "libs" / "yofina_core"
    for cand in (base / "src" / "yofina_core", base / "yofina_core"):
        if cand.is_dir():
            return cand, base
    return None


def write_zip(pkg: Path, out: Path) -> int:
    files = [p for p in sorted(pkg.rglob("*")) if p.is_file()]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        dirs: set[str] = set()
        for p in files:
            parts = p.relative_to(pkg).as_posix().split("/")[:-1]
            for i in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:i]) + "/")
        for d in sorted(dirs):
            zi = zipfile.ZipInfo(d)
            zi.external_attr = (0o40755 << 16) | 0x10
            z.writestr(zi, b"")
        for p in files:
            arc = p.relative_to(pkg).as_posix()
            zi = zipfile.ZipInfo.from_file(p, arc)
            zi.external_attr = (0o100000 | (0o755 if arc.startswith("bin/") else 0o644)) << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, p.read_bytes())
    return len(files)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("src", type=Path, help="thư mục nguồn của hàm (chứa handler/main.py)")
    ap.add_argument("--arch", choices=sorted(PLATFORMS), required=True)
    ap.add_argument("--name", help="tên bản build (mặc định: tên thư mục nguồn)")
    ap.add_argument("--out", type=Path, default=ROOT / "build" / "lambda")
    ap.add_argument("--python-version", default="3.13")
    ap.add_argument("--requirements", type=Path)
    ap.add_argument("--no-core", action="store_true", help="không kèm libs/yofina_core")
    ap.add_argument("--keep-boto", action="store_true")
    ap.add_argument(
        "--slim",
        action="store_true",
        help="gỡ thư mục tests (trừ numpy) và tệp .pyi khỏi thư viện bên thứ ba (scipy: giảm hàng chục MB)",
    )
    ap.add_argument(
        "--extra",
        action="append",
        default=[],
        metavar="NGUỒN[:ĐÍCH]",
        help="chép thêm thư mục (từ gốc repo) vào bản build; lặp được",
    )
    args = ap.parse_args()

    src = args.src if args.src.is_absolute() else (Path.cwd() / args.src)
    src = src.resolve()
    if not src.is_dir():
        raise SystemExit(f"không thấy thư mục nguồn: {src}")
    name = args.name or src.name
    pkg = args.out / f"{name}-{args.arch}"
    out_zip = args.out / f"{name}-{args.arch}.zip"
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)

    reqs = collect_requirements(src, args.requirements)
    core = None if args.no_core else core_package_dir()
    if core:
        reqs += (
            deps_of(core[1] / "pyproject.toml") if (core[1] / "pyproject.toml").is_file() else []
        )
    reqs = sorted(set(reqs))
    if reqs:
        req_file = args.out / f"{name}-{args.arch}.requirements.txt"
        req_file.write_text("\n".join(reqs) + "\n", encoding="utf-8")
        cmd = [
            "uv",
            "pip",
            "install",
            "--python-platform",
            PLATFORMS[args.arch],
            "--python-version",
            args.python_version,
            "--only-binary=:all:",
            "--target",
            str(pkg),
            "-r",
            str(req_file),
        ]
        print("+", " ".join(cmd), file=sys.stderr)
        subprocess.run(cmd, check=True)
        req_file.unlink()
    else:
        print("không có phụ thuộc bên ngoài để cài", file=sys.stderr)

    (pkg / ".lock").unlink(missing_ok=True)
    # launcher .exe/.py do uv sinh trên Windows vô dụng trên Linux
    for junk in ("bin", "Scripts"):
        if (pkg / junk).exists() and not (src / junk).exists():
            shutil.rmtree(pkg / junk)
    if not args.keep_boto:
        for child in list(pkg.iterdir()):
            stem = child.name.lower().replace("-", "_")
            if stem.startswith(BOTO_PREFIXES) and child.name != "bin":
                shutil.rmtree(child) if child.is_dir() else child.unlink()

    if args.slim:
        # numpy tự nhập `numpy._core.tests` lúc khởi động (đã gặp ImportModuleError) nên KHÔNG đụng vào numpy.
        for d in list(pkg.rglob("tests")):
            top = d.relative_to(pkg).parts[0]
            if d.is_dir() and d.parent != pkg and top not in {"numpy", "numpy.libs"}:
                shutil.rmtree(d, ignore_errors=True)
        for stub in pkg.rglob("*.pyi"):
            stub.unlink(missing_ok=True)

    # mã nguồn của hàm và gói yofina_core
    for item in src.iterdir():
        if (
            item.name
            in {
                "__pycache__",
                ".venv",
                "node_modules",
                "requirements.txt",
                "uv.lock",
                "tests",
                ".pytest_cache",
            }
            or item.suffix == ".pyc"
            or item.name.startswith("test_")
        ):
            continue
        out_resolved = args.out.resolve()
        if item.resolve() == out_resolved or item.resolve() in out_resolved.parents:
            continue  # thư mục đầu ra nằm trong thư mục nguồn: không chép chính nó
        dest = pkg / item.name
        if item.is_dir():
            shutil.copytree(item, dest, ignore=IGNORE_COPY, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
    if core:
        shutil.copytree(core[0], pkg / "yofina_core", ignore=IGNORE_COPY, dirs_exist_ok=True)
        print(f"kèm yofina_core từ {core[0].relative_to(ROOT)}", file=sys.stderr)
    for spec in args.extra:
        src_rel, _, dest_rel = spec.partition(":")
        extra_src = (ROOT / src_rel).resolve()
        if not extra_src.is_dir() or ROOT not in extra_src.parents:
            raise SystemExit(f"--extra: không thấy thư mục trong repo: {src_rel}")
        dest = pkg / (dest_rel or extra_src.name)
        shutil.copytree(extra_src, dest, ignore=IGNORE_COPY, dirs_exist_ok=True)
        print(f"kèm {extra_src.relative_to(ROOT)} -> {dest.relative_to(pkg)}", file=sys.stderr)
    for pyc in pkg.rglob("__pycache__"):
        shutil.rmtree(pyc, ignore_errors=True)

    args.out.mkdir(parents=True, exist_ok=True)
    n = write_zip(pkg, out_zip)
    size_dir = sum(p.stat().st_size for p in pkg.rglob("*") if p.is_file())
    print(f"{pkg}  ({size_dir / 1e6:.1f} MB giải nén)")
    print(f"{out_zip}  ({out_zip.stat().st_size / 1e6:.1f} MB nén, {n} tệp)")
    if size_dir > 250 * 1024 * 1024:
        print("CẢNH BÁO: vượt giới hạn 250 MB giải nén của Lambda zip", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
