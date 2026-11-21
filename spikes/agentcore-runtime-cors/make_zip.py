"""Đóng gói deployment_package.zip (deps ARM64 trong build/pkg + main.py) với quyền 644/755, bỏ __pycache__."""
import sys, zipfile, pathlib
root = pathlib.Path(__file__).parent
pkg_name = sys.argv[2] if len(sys.argv) > 2 else "pkg"
pkg, out = root / "build" / pkg_name, root / "build" / (sys.argv[1] if len(sys.argv) > 1 else "deployment_package.zip")
files = [(p, p.relative_to(pkg).as_posix()) for p in pkg.rglob("*") if p.is_file() and "__pycache__" not in p.parts and not (p.parent.name == "bin" and p.suffix in (".exe", ".py", ""))]
files.append((root / "agent" / "main.py", "main.py"))
if pkg_name == "pkg_otel":  # launcher POSIX thay cho .exe do uv sinh trên Windows
    files.append((root / "agent" / "opentelemetry-instrument", "bin/opentelemetry-instrument"))
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    dirs = set()
    for _, arc in files:
        parts = arc.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]) + "/")
    for d in sorted(dirs):
        zi = zipfile.ZipInfo(d); zi.external_attr = (0o40755 << 16) | 0x10; z.writestr(zi, b"")
    for p, arc in files:
        zi = zipfile.ZipInfo.from_file(p, arc)
        mode = 0o755 if arc.startswith("bin/") else 0o644
        zi.external_attr = (0o100000 | mode) << 16
        zi.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(zi, p.read_bytes())
print(out, round(out.stat().st_size / 1e6, 1), "MB zipped", len(files), "files")
