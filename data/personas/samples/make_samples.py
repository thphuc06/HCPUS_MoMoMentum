"""Sinh tệp mẫu để tải lên trong cảnh 5 của demo (nạp dữ liệu ngân hàng khác), cho persona `vy` và `minh`.

Chạy từ gốc repo (cần Pillow và font Windows, như scripts/make_ingest_synthetic.py):

    uv run --with pillow python data/personas/samples/make_samples.py

Đầu ra (ghi đè, tất định theo seed của spec và ngày neo `--anchor`, mặc định ngày neo của demo):

- `vy_sao_ke_vcb.csv`: sao kê kiểu Vietcombank (cùng cột và cách ghi với evals/ingest/synthetic/csv/c01_vcb_50.csv): các khoản chi
  ngoài ví của nguồn `statement` trong spec, cộng hai dòng tiền vào trùng thu nhập ngoài ví đã seed (để cảnh 5 cho thấy khử trùng);
- `vy_bien_lai_1.png`, `vy_bien_lai_2.png`: ảnh biên lai chuyển khoản dựng bằng Pillow theo bố cục app ngân hàng (cùng hàm `receipt`
  của scripts/make_ingest_synthetic.py), một khoản mỗi ảnh, ở ngày gần nhất (hôm qua), khác các dòng của sao kê.
- `minh_bien_lai_1.png` (chuyển khoản góp tiền ăn cho một người, hũ Ăn uống), `minh_bien_lai_2.png` (thanh toán hóa đơn tiền nước,
  hũ Hóa đơn): ảnh chứng từ có PII nhìn rõ (họ tên, số điện thoại, số tài khoản) cho tài khoản giám khảo (`giamkhao1`–`giamkhao3` đều
  là persona `minh`, issue #16). Ghi vào `--out` VÀ chép sang `--public` (mặc định frontend/public/samples/), nên sau khi build và
  deploy frontend, Amplify phục vụ ở `/samples/minh_bien_lai_1.png`, `/samples/minh_bien_lai_2.png`.

Mọi tên, mã, số tham chiếu, số điện thoại, số tài khoản trong tệp đều hư cấu. Ngày lấy theo ngày mô phỏng của persona
(`anchor - days_ago`), số tiền ra từ khối `out_of_wallet` qua `personas.generate_out_of_wallet`; không số nào gõ tay ở đây. Với `vy`,
khối đó nằm trong data/personas/specs/vy.json. Với `minh`, khối nằm ở `minh_receipts.json` cạnh file này (kèm PII hư cấu của từng ảnh)
và chỉ được ghép vào spec của minh lúc sinh mẫu: sổ cái seed của minh không đổi, còn số tiền vẫn qua bộ chống trùng số tiền với giao
dịch đã seed (khử trùng của bước nạp ghép theo số tiền và ngày), nên dòng nạp từ ảnh không bị coi là trùng.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import shutil
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for extra in ("data", "libs/yofina_core/src"):
    sys.path.insert(0, str(REPO / extra))

from personas import generate_out_of_wallet, statement_csv  # noqa: E402
from personas.generator import load_spec  # noqa: E402

PERSONA = "vy"
DEFAULT_ANCHOR = (
    "2026-11-21"  # cùng ngày neo với YOFINA_DEMO_ANCHOR_DATE (infra-cdk, context demoAnchorDate)
)
CSV_NAME = "vy_sao_ke_vcb.csv"

MINH = "minh"
MINH_SPEC = HERE / "minh_receipts.json"
#: thư mục tĩnh của frontend (Vite chép `public/` vào gốc `dist/`), Amplify phục vụ ở `/samples/<tên tệp>`
PUBLIC_DIR = REPO / "frontend" / "public" / "samples"
TIME_LABEL = "Thời gian giao dịch"


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


# --- persona minh: ảnh chứng từ có PII -----------------------------------------------------------------------------------
@dataclass(frozen=True)
class SampleReceipt:
    """Một ảnh chứng từ mẫu (chưa vẽ): chữ trên ảnh và PII hư cấu nhìn thấy trên đó."""

    file_name: str
    style: str  # khóa STYLES của scripts/make_ingest_synthetic.py
    title: str
    amount_vnd: int
    app_date: date
    jar_code: str  # hũ của nhóm trong spec (hũ mà kịch bản mong được gợi ý)
    rows: tuple[tuple[str, str], ...]  # (nhãn, giá trị) theo thứ tự trên ảnh
    names: tuple[str, ...]
    phones: tuple[str, ...]
    accounts: tuple[str, ...]

    @property
    def amount_text(self) -> str:
        return f"{self.amount_vnd:,} VND".replace(",", ".")

    @property
    def lines(self) -> list[str]:
        """Các dòng chữ riêng của biên lai theo thứ tự vẽ (tiêu đề, số tiền, rồi nhãn và giá trị từng dòng)."""
        return [self.title, self.amount_text, *(s for row in self.rows for s in row)]


def minh_receipts(anchor: date) -> list[SampleReceipt]:
    """Dữ liệu ảnh chứng từ mẫu của `minh`, mỗi merchant của `minh_receipts.json` một ảnh, theo thứ tự trong spec.

    Số tiền, ngày, giờ: khối `out_of_wallet` của `minh_receipts.json` ghép vào spec của minh rồi qua `generate_out_of_wallet`.
    Họ tên, số điện thoại, số tài khoản: nguyên văn từ `minh_receipts.json` (hư cấu)."""
    cfg = json.loads(MINH_SPEC.read_text(encoding="utf-8"))
    block = cfg["out_of_wallet"]
    oow = generate_out_of_wallet(
        MINH, anchor=anchor, spec={**load_spec(MINH), "out_of_wallet": block}
    )
    merchants = [m for s in block["sources"] for g in s["groups"] for m in g["merchants"]]
    order = [m["name"] for m in merchants]
    detail_of = {m["name"]: m["receipt"] for m in merchants}
    expenses = sorted(
        (r for s in oow.sources for r in s.expenses), key=lambda r: order.index(r.merchant)
    )
    src = cfg["source_account"]
    rng = random.Random(f"{MINH}:receipts")
    out: list[SampleReceipt] = []
    for i, row in enumerate(expenses, start=1):
        d = detail_of[row.merchant]
        if d["kind"] == "transfer":
            fields = [
                ("Tài khoản nguồn", src),
                (row.recipient_label, row.merchant),
                ("Tài khoản người hưởng", d["account"]),
                ("Ngân hàng người hưởng", d["bank"]),
                ("Số điện thoại người hưởng", d["phone"]),
            ]
            names, accounts = (row.merchant,), (src, d["account"])
        elif d["kind"] == "bill":
            fields = [
                ("Tài khoản nguồn", src),
                ("Dịch vụ", d["service"]),
                (row.recipient_label, row.merchant),
                ("Tên khách hàng", d["customer"]),
                ("Số điện thoại", d["phone"]),
            ]
            names, accounts = (d["customer"],), (src,)
        else:
            raise ValueError(f"{MINH_SPEC.name}: loại biên lai lạ {d['kind']!r}")
        fields += [
            (TIME_LABEL, f"{row.app_date(anchor):%d/%m/%Y} {row.local_time:%H:%M}"),
            ("Nội dung", row.bank_text),
            ("Mã tham chiếu", f"FT26{rng.randrange(10**8, 10**9)}"),
        ]
        out.append(
            SampleReceipt(
                file_name=f"{MINH}_bien_lai_{i}.png",
                style=row.receipt_style,
                title=d["title"],
                amount_vnd=row.amount_vnd,
                app_date=row.app_date(anchor),
                jar_code=row.jar_code,
                rows=tuple(fields),
                names=names,
                phones=(d["phone"],),
                accounts=accounts,
            )
        )
    return out


def write_minh(syn, anchor: date, out_dir: Path, public_dir: Path) -> None:
    """Vẽ ảnh của `minh_receipts` vào `out_dir` và chép sang `public_dir` (xóa ảnh `minh_bien_lai_*` cũ ở cả hai)."""
    receipts = minh_receipts(anchor)
    for d in (out_dir, public_dir):
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob(f"{MINH}_bien_lai_*.png"):
            old.unlink()
    for r in receipts:
        im, _ = syn.receipt(r.style, r.amount_text, list(r.rows), title=r.title)
        path = out_dir / r.file_name
        im.save(path, "PNG", optimize=True)
        shutil.copyfile(path, public_dir / r.file_name)
        print(f"{r.file_name}: {r.title} {r.amount_vnd:,} đ ngày {r.app_date}, hũ {r.jar_code}")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # console Windows mặc định cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--anchor", default=DEFAULT_ANCHOR, help="ngày mô phỏng (YYYY-MM-DD)")
    ap.add_argument("--out", type=Path, default=HERE, help="thư mục ghi (mặc định: thư mục này)")
    ap.add_argument(
        "--public",
        type=Path,
        default=PUBLIC_DIR,
        help="thư mục web công khai nhận bản chép ảnh của minh (mặc định: frontend/public/samples)",
    )
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

    write_minh(syn, anchor, args.out, args.public)
    return 0


if __name__ == "__main__":
    sys.exit(main())
