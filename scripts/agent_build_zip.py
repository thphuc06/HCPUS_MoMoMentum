# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Đóng gói agent thành zip ARM64 cho AgentCore Runtime (CodeZip, KHÔNG Docker). Chỉ build, không upload.

    uv run scripts/agent_build_zip.py                  # -> build/agent/agent-arm64.zip
    uv run scripts/agent_build_zip.py --out build/x --python-version 3.13

Cách làm (theo spikes/agentcore-runtime-cors/make_zip.py, đã chạy thật ở spike Runtime):
1. `uv export` lấy danh sách phụ thuộc đã khóa của gói `yofina-agent` từ `uv.lock` (đúng phiên bản đã
   test: strands-agents 1.65.0, ag-ui-protocol 1.0.0, ...), bỏ gói workspace.
2. `uv pip install --python-platform aarch64-manylinux2014 --only-binary=:all: --target ...` cài wheel Linux
   ARM64 ngay trên Windows (không cần QEMU/Docker). Thư viện chỉ có sdist sẽ báo lỗi.
3. Chép `agent/main.py` (entrypoint), `agent/src/yofina_agent` và `libs/yofina_core/src/yofina_core` vào gốc zip.
4. Dọn launcher `.exe`/`.py` của Windows trong `bin/`, `__pycache__`, test của thư viện; ghi zip với quyền 644/755.
5. In kích thước và kiểm nhanh: có `main.py` ở gốc, có wheel aarch64 (không lẫn x86/Windows).

boto3 được GIỮ trong zip (runtime CodeZip không bảo đảm có sẵn; spike Runtime chạy với boto3 trong zip).
Tạo Runtime (bước ghép): `entryPoint: ["main.py"]`, `runtime: PYTHON_3_13`, `serverProtocol: AGUI`, platform V2.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_lambda import IGNORE_COPY, PLATFORMS, ROOT, write_zip  # tái dùng bộ ghi zip đã có

PACKAGE = "yofina-agent"
# Giới hạn zip của direct code deployment (docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy.html)
ZIP_LIMIT_MB = 250
UNPACKED_LIMIT_MB = (
    250  # tài liệu chỉ nêu "package size 250 MB"; giữ ngưỡng thận trọng cho cả bản giải nén
)


def run(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd), file=sys.stderr)
    return subprocess.run(cmd, check=True, text=True, **kw)  # type: ignore[call-overload]


def locked_requirements(out_file: Path) -> list[str]:
    res = run(
        [
            "uv",
            "export",
            "--package",
            PACKAGE,
            "--no-dev",
            "--no-emit-workspace",
            "--no-hashes",
            "--frozen",
            "--no-header",
            "--no-annotate",
        ],
        capture_output=True,
        cwd=ROOT,
    )
    lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip() and not ln.startswith("#")]
    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", type=Path, default=ROOT / "build" / "agent")
    ap.add_argument("--arch", choices=sorted(PLATFORMS), default="arm64")
    ap.add_argument("--python-version", default="3.13")
    args = ap.parse_args()

    out: Path = args.out if args.out.is_absolute() else ROOT / args.out
    pkg = out / f"pkg-{args.arch}"
    zip_path = out / f"agent-{args.arch}.zip"
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)

    req_file = out / f"requirements-{args.arch}.txt"
    reqs = locked_requirements(req_file)
    print(f"{len(reqs)} phụ thuộc đã khóa -> {req_file.relative_to(ROOT)}", file=sys.stderr)
    run(
        [
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
    )

    (pkg / ".lock").unlink(missing_ok=True)
    for junk in ("bin", "Scripts"):  # launcher .exe/.py do uv sinh trên Windows vô dụng trên Linux
        shutil.rmtree(pkg / junk, ignore_errors=True)
    for tests_dir in pkg.rglob("tests"):
        if tests_dir.is_dir() and tests_dir.parent.parent == pkg:
            shutil.rmtree(tests_dir, ignore_errors=True)

    shutil.copy2(ROOT / "agent" / "main.py", pkg / "main.py")
    shutil.copytree(
        ROOT / "agent" / "src" / "yofina_agent", pkg / "yofina_agent", ignore=IGNORE_COPY
    )
    shutil.copytree(
        ROOT / "libs" / "yofina_core" / "src" / "yofina_core",
        pkg / "yofina_core",
        ignore=IGNORE_COPY,
    )
    for cache in pkg.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)

    n = write_zip(pkg, zip_path)
    unpacked = sum(p.stat().st_size for p in pkg.rglob("*") if p.is_file())
    zipped = zip_path.stat().st_size

    # kiểm nhanh nội dung zip
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
    want_arch = "aarch64" if args.arch == "arm64" else "x86_64"
    native = [x for x in names if x.endswith(".so") and "cpython" in x]
    wrong = [x for x in native if want_arch not in x]
    checks = {
        "main.py ở gốc zip": "main.py" in names,
        "yofina_agent có trong zip": "yofina_agent/app.py" in names,
        "yofina_core có trong zip (kèm llm_defaults.json)": "yofina_core/llm_defaults.json"
        in names,
        f"có {len(native)} thư viện native, tất cả {want_arch}": bool(native) and not wrong,
        "không có .exe": not any(x.endswith(".exe") for x in names),
    }
    print(f"\n{zip_path}")
    print(f"  {zipped / 1e6:.1f} MB nén, {unpacked / 1e6:.1f} MB giải nén, {n} tệp")
    for label, ok in checks.items():
        print(f"  [{'ok' if ok else 'LỖI'}] {label}")
    if wrong:
        print("  native sai kiến trúc:", wrong[:5], file=sys.stderr)
    if zipped / 1e6 > ZIP_LIMIT_MB or unpacked / 1e6 > UNPACKED_LIMIT_MB:
        print("CẢNH BÁO: vượt giới hạn kích thước của direct code deployment", file=sys.stderr)
        return 1
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
