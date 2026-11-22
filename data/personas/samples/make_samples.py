"""Sinh tệp mẫu để tải lên trong cảnh 5 của demo (nạp dữ liệu ngân hàng khác), cho persona `vy`.

Chạy từ gốc repo (cần Pillow và font Windows, như scripts/make_ingest_synthetic.py):

    uv run --with pillow python data/personas/samples/make_samples.py

Đầu ra (ghi đè, tất định theo seed của spec và ngày neo `--anchor`, mặc định ngày neo của demo):

- `vy_sao_ke_vcb.csv`: sao kê kiểu Vietcombank (cùng cột và cách ghi với evals/ingest/synthetic/csv/c01_vcb_50.csv): các khoản chi
  ngoài ví của nguồn `statement` trong spec, cộng hai dòng tiền vào trùng thu nhập ngoài ví đã seed (để cảnh 5 cho thấy khử trùng);
- `vy_bien_lai_1.png`, `vy_bien_lai_2.png`: ảnh biên lai chuyển khoản dựng bằng Pillow theo bố cục app ngân hàng (cùng hàm `receipt`
  của scripts/make_ingest_synthetic.py), một khoản mỗi ảnh, ở ngày gần nhất (hôm qua), khác các dòng của sao kê.

Mọi tên, mã, số tham chiếu trong tệp đều hư cấu. Ngày lấy theo ngày mô phỏng của persona (`anchor - days_ago`), số tiền ra từ khối
`out_of_wallet` của data/personas/specs/vy.json qua `personas.generate_out_of_wallet`; không số nào gõ tay ở đây.
"""

from __future__ import annotations

import argparse
import importlib.util
import random
import sys
from datetime import date
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):  # console Windows mặc định cp1252
    _stream.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for extra in ("data", "libs/yofina_core/src"):
    sys.path.insert(0, str(REPO / extra))

from personas import generate_out_of_wallet, statement_csv  # noqa: E402

PERSONA = "vy"
DEFAULT_ANCHOR = (
    "2026-11-21"  # cùng ngày neo với YOFINA_DEMO_ANCHOR_DATE (infra-cdk, context demoAnchorDate)
)
CSV_NAME = "vy_sao_ke_vcb.csv"


def _load_synthetic():
    """Dùng lại hàm vẽ biên lai của bộ dữ liệu thử F6 (không chép mã)."""
    spec = importlib.util.spec_from_file_location(
        "make_ingest_synthetic", REPO / "scripts" / "make_ingest_synthetic.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_receipt(syn, row, anchor: date, rng: random.Random):
    """Một biên lai theo `receipt_style` của giao dịch (mb, tcb, vcb, momo...), nhãn người nhận theo spec."""
    when = f"{row.app_date(anchor):%d/%m/%Y} {row.local_time:%H:%M}"
    ref = f"FT26{rng.randrange(10**8, 10**9)}"
    label = row.recipient_label or "Người nhận"
    time_label = "Ngày giao dịch" if row.receipt_style == "mb" else "Thời gian giao dịch"
    ref_label = "Mã giao dịch" if row.receipt_style == "mb" else "Mã tham chiếu"
    rows = [
        (label, row.merchant),
        (time_label, when),
        ("Nội dung", row.bank_text),
        (ref_label, ref),
    ]
    im, _ = syn.receipt(row.receipt_style, f"{syn.dots(row.amount_vnd)} VND", rows)
    return im


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--anchor", default=DEFAULT_ANCHOR, help="ngày mô phỏng (YYYY-MM-DD)")
    ap.add_argument("--out", type=Path, default=HERE, help="thư mục ghi (mặc định: thư mục này)")
    args = ap.parse_args()
    anchor = date.fromisoformat(args.anchor)

    oow = generate_out_of_wallet(PERSONA, anchor=anchor)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / CSV_NAME).write_bytes(statement_csv(oow))
    stmt = oow.source("statement")
    print(
        f"{CSV_NAME}: {len(stmt.rows)} dòng ({len(stmt.expenses)} chi, {len(stmt.incomes)} tiền vào), "
        f"chi {sum(r.amount_vnd for r in stmt.expenses):,} đ, "
        f"{stmt.rows[0].app_date(anchor)} .. {stmt.rows[-1].app_date(anchor)}"
    )

    syn = _load_synthetic()
    syn.check_fonts()
    rng = random.Random(f"{PERSONA}:receipts")
    for old in args.out.glob("vy_bien_lai_*.png"):
        old.unlink()
    for i, row in enumerate(oow.source("receipts").expenses, start=1):
        im = build_receipt(syn, row, anchor, rng)
        path = args.out / f"vy_bien_lai_{i}.png"
        im.save(path, "PNG", optimize=True)
        print(f"{path.name}: {row.merchant} {row.amount_vnd:,} đ ngày {row.app_date(anchor)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
