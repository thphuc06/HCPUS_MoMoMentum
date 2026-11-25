"""Sinh tệp sao kê "hai tuần gần nhất" cho cảnh 4 chạy thật (issue #22), persona `minh`.

    uv run python data/personas/samples/make_scene4_csv.py            # ghi data/personas/samples/ và frontend/public/samples/
    uv run python data/personas/samples/make_scene4_csv.py --check    # chỉ so với hai tệp đã có, mã thoát 1 nếu lệch

Tải tệp này lên (Nạp dữ liệu, CSV) ngay sau "Đặt lại dữ liệu demo": các dòng tự chọn sẵn vào hũ Ăn uống, người dùng chốt một lần, batch
dự báo chạy PELT trên chuỗi chi tuần của hũ và xác nhận mức chi mới giữ hai tuần, rồi lộ trình được sinh lại.

Một tệp dùng chung cho bốn tài khoản persona `minh` (`minh`, `giamkhao1`–`3`, xem `data/personas/accounts.json`): cùng persona, cùng
seed, cùng ngày neo nên sổ cái sau khi đặt lại giống hệt nhau, và tệp không chứa gì riêng của một tài khoản.

Mọi số ra từ dữ liệu persona và bộ đo, không số nào gõ tay:

- Hệ số tăng chi: `minimal_factor` của `scripts/measure_scene4_pelt.py`, hệ số nhỏ nhất trên lưới 0,1 mà PELT (`yofina_ml.change` với
  `change_defaults.json` hiện tại) xác nhận với mọi hạt chia khoản, trên lịch sử 120 ngày của `minh` ở ngày neo, với đúng các nơi chi
  của tệp này.
- Khoản chi: `plan_shift` của `scripts/inject_behavior_shift.py` (mức chi tuần cũ là trung vị các tuần trước hai tuần cuối, mỗi tuần
  thêm cho tới hệ số lần mức cũ, số khoản mỗi tuần điển hình của hũ, ngày trong đúng tuần đó).
- Nơi chi: đối tác trong lịch sử hũ Ăn uống mà bộ phân loại của luồng nạp (`yofina_ingest.classify.classify_rows`) tự xếp vào Ăn uống
  mức `auto` mà KHÔNG gọi model: chuỗi đã chuẩn hóa và đã che của đối tác khớp đúng một nhãn seed của persona
  (`data/personas/classify_labels/minh.json`, nạp khi đặt lại demo). Không có cột nội dung vì chuỗi so khớp gồm cả đối tác lẫn nội
  dung; thêm nội dung thì chuỗi không còn bằng nhãn và dòng phải qua embedding hoặc model.
- Không trùng sổ cái: bộ khử trùng của luồng nạp so giao dịch cùng số tiền lệch không quá `ingest_dedupe_window_days` ngày. Khoản nào
  cùng số tiền với một khoản chi đã seed trong cửa sổ đó được cộng 1.000 ₫, lấy bớt 1.000 ₫ ở khoản lớn nhất khác cùng tuần (tổng tuần
  giữ nguyên).

Định dạng: UTF-8 có BOM, CRLF, cột `STT`, `Ngày giao dịch` (dd/mm/yyyy), `Mã giao dịch`, `Đối tác`, `Số tiền ghi nợ`, `Số tiền ghi
có` mà `pipelines/ingest/yofina_ingest/csvparse.py` nhận bằng bảng tên cột (không cần model ánh xạ cột). Mã giao dịch hư cấu, tất định.

Tệp gắn với ngày neo (mặc định `2026-11-21`, như YOFINA_DEMO_ANCHOR_DATE). Ngày mô phỏng đi theo ngày thật kể từ lần đặt lại, nên phải
đặt lại rồi tải trong cùng ngày; tải sau một ngày trở lên thì hai tuần lệch không còn trùng hai tuần cuối và PELT không xác nhận (bảng
lệch ngày ở `docs/research/2026-11-26-canh4-pelt.md`).
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import random
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for _extra in (
    "data",
    "libs/yofina_core/src",
    "pipelines/ingest",
    "pipelines/classify",
    "gateway/tools/ledger",
):
    if str(REPO / _extra) not in sys.path:
        sys.path.insert(0, str(REPO / _extra))

PERSONA = "minh"
JAR = "an_uong"
NAME = "minh_sao_ke_2_tuan.csv"
OUT_DIRS = (HERE, REPO / "frontend" / "public" / "samples")
HEADER = ["STT", "Ngày giao dịch", "Mã giao dịch", "Đối tác", "Số tiền ghi nợ", "Số tiền ghi có"]
STEP_VND = 1000  # số tiền làm tròn tới nghìn, như bộ sinh persona
WEEK = 7


def _load_measure():
    """`scripts/measure_scene4_pelt.py` (bộ đo của issue #22), dùng lại chứ không chép."""
    name = "measure_scene4_pelt"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class SeedLabelStore:
    """Kho nhãn của một tài khoản vừa đặt lại: chỉ có nhãn seed của persona (như `classify_seed.apply_seed_labels`), tra khớp chính xác
    như `app_find_labeled_exact`. Chưa có lịch sử nạp, chưa có lần sửa hũ nào; không có k-NN (cần vector của model embedding)."""

    def __init__(self, persona: str, jar_codes: set[str]) -> None:
        from yofina_classify.model import ExactLabel

        from yofina_ledger.classify_seed import load_seed_set

        seed = load_seed_set(persona)
        if seed is None:
            raise SystemExit(f"persona {persona} chưa có nhãn seed (data/personas/classify_labels)")
        self._exact: dict[str, list[Any]] = {}
        for i, lab in enumerate(x for x in seed.labels if x.jar_code in jar_codes):
            self._exact.setdefault(lab.text_norm, []).append(ExactLabel(lab.jar_code, "seed", i))

    def find_exact(self, user_id: str, text_norm: str) -> list[Any]:
        return list(self._exact.get(text_norm, []))

    def knn(self, user_id: str, vector: Sequence[float], k: int) -> list[Any]:
        return []

    def history(self, user_id: str, merchants: Sequence[str]) -> dict[str, dict[str, int]]:
        return {}

    def corrections(self, user_id: str, merchant_keys: Sequence[str]) -> dict[str, int]:
        return {}


def deterministic_merchants(persona: str, anchor: date, candidates: Sequence[str]) -> list[str]:
    """Các đối tác trong `candidates` mà bộ phân loại của luồng nạp xếp vào hũ `JAR` mức `auto` khi KHÔNG có model nào (không đề xuất
    của lượt đọc tệp, không embedding), với ngữ cảnh như worker dựng cho tài khoản persona vừa đặt lại."""
    from yofina_ingest.classify import ClassifyInputs, RowInput, classify_rows
    from yofina_ingest.context import find_seed_dir, load_seed_type_map

    from personas import generate
    from yofina_core.pii import PiiPolicy

    d = generate(persona, anchor=anchor)
    jars = [
        {"code": j.code, "name": j.name, "kind": j.kind, "balance_vnd": j.balance_vnd}
        for j in d.jars
        if j.kind != "system"
    ]
    seed_dir = find_seed_dir()
    inputs = ClassifyInputs(
        user_id=f"{persona}-demo",
        jars=jars,
        type_map=load_seed_type_map(seed_dir) if seed_dir else {},
        rules=[],
        policy=PiiPolicy.build(keep=[p.name for p in d.payees], self_names=[d.display_name]),
        store=SeedLabelStore(persona, {j["code"] for j in jars}),
        gateway=None,
    )
    rows = [RowInput(anchor, STEP_VND, m, None, None, None, None, None) for m in candidates]
    choices = classify_rows(rows, inputs)
    return [
        m
        for m, c in zip(candidates, choices, strict=True)
        if c is not None and c.code == JAR and c.tier == "auto"
    ]


def avoid_duplicates(
    rows: Sequence[Any], seeded: Sequence[tuple[date, int, Any]], window_days: int, last_day: date
) -> list[Any]:
    """Dịch số tiền (bội của 1.000 ₫, nhỏ nhất trước) giữa hai khoản cùng tuần cho tới khi không khoản nào cùng số tiền với một khoản
    chi đã seed lệch không quá `window_days` ngày. Mỗi lần dịch không tạo trùng mới ở cả hai khoản, và tổng mỗi tuần (tuần cắt lùi từ
    `last_day`) giữ nguyên."""
    out = list(rows)

    def clash(day: date, amount: int) -> bool:
        return any(a == amount and abs((d - day).days) <= window_days for d, a, _ in seeded)

    def week(r: Any) -> int:
        return (last_day - r.day).days // WEEK

    steps = [s * k * STEP_VND for k in range(1, 50) for s in (1, -1)]
    while (
        bad := next((i for i, r in enumerate(out) if clash(r.day, r.amount_vnd)), None)
    ) is not None:
        b = out[bad]
        peers = sorted(
            (i for i, r in enumerate(out) if i != bad and week(r) == week(b)),
            key=lambda i: (-out[i].amount_vnd, i),
        )
        for delta in steps:
            if b.amount_vnd + delta <= 0 or clash(b.day, b.amount_vnd + delta):
                continue
            donor = next(
                (
                    i
                    for i in peers
                    if out[i].amount_vnd - delta > 0
                    and not clash(out[i].day, out[i].amount_vnd - delta)
                ),
                None,
            )
            if donor is not None:
                out[bad] = replace(b, amount_vnd=b.amount_vnd + delta)
                out[donor] = replace(out[donor], amount_vnd=out[donor].amount_vnd - delta)
                break
        else:
            raise SystemExit(f"không tránh được trùng sổ cái cho khoản {b}")
    return out


def csv_bytes(rows: Sequence[Any], *, seed: str) -> bytes:
    """Sao kê CSV (UTF-8 có BOM, CRLF), dòng theo ngày rồi số tiền. Mã giao dịch hư cấu, tất định theo `seed`."""
    rng = random.Random(seed)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(HEADER)
    for i, r in enumerate(sorted(rows, key=lambda r: (r.day, r.amount_vnd, r.description)), 1):
        ref = f"FT{r.day:%y%j}{rng.randrange(10**6, 10**7)}"
        w.writerow([i, r.day.strftime("%d/%m/%Y"), ref, r.description, f"{r.amount_vnd:,}", ""])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


@dataclass(frozen=True)
class Output:
    data: bytes
    factor: float
    merchants: tuple[str, ...]
    rows: tuple[Any, ...]
    baseline_weekly_vnd: int
    detected: Any


def generate(anchor: date) -> Output:
    """Nội dung tệp ở ngày neo `anchor` cùng các số đã dùng (hệ số, nơi chi, mức cũ, kết quả PELT)."""
    from yofina_core.ingest import IngestSettings
    from yofina_ml import change as ch

    m = _load_measure()
    sc = m.load_shift_module()
    params = ch.load_params()
    history = m.persona_history(PERSONA, anchor, jar=JAR)
    merchants = deterministic_merchants(PERSONA, anchor, history.merchants)
    if not merchants:
        raise SystemExit("không có nơi chi nào bộ phân loại tự xếp vào Ăn uống mà không cần model")
    factor = m.minimal_factor(history, params, merchants=merchants)
    if factor is None:
        raise SystemExit(
            "PELT không xác nhận ở hệ số nào trên lưới: xem scripts/measure_scene4_pelt.py"
        )
    rows = avoid_duplicates(
        m.plan(history, factor, merchants=merchants),
        history.expenses,
        IngestSettings().ingest_dedupe_window_days,
        anchor - timedelta(days=1),
    )
    detected = m.detect(history, rows, params)
    if detected is None:  # tránh trùng sổ cái chỉ dịch 1.000 ₫ nên không được làm mất phát hiện
        raise SystemExit("sau khi tránh trùng sổ cái, PELT không còn xác nhận")
    return Output(
        data=csv_bytes(rows, seed=f"scene4:{PERSONA}:{anchor.isoformat()}"),
        factor=factor,
        merchants=tuple(merchants),
        rows=tuple(rows),
        baseline_weekly_vnd=sc.baseline_weekly(list(history.spends), anchor, m.SHIFT_WEEKS),
        detected=detected,
    )


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--anchor", type=date.fromisoformat, default=None, help="ngày neo (YYYY-MM-DD)")
    ap.add_argument("--check", action="store_true", help="chỉ so với tệp đã có, không ghi")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # console Windows mặc định cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    anchor = args.anchor or _load_measure().DEFAULT_ANCHOR
    out = generate(anchor)
    total = sum(r.amount_vnd for r in out.rows)
    days = sorted({r.day for r in out.rows})
    print(
        f"{NAME}: {len(out.rows)} dòng chi, tổng {total:,} ₫, {days[0]} .. {days[-1]}; hệ số {out.factor} lần mức chi tuần cũ "
        f"{out.baseline_weekly_vnd:,} ₫; nơi chi: {', '.join(out.merchants)}"
    )
    hit = out.detected
    print(
        f"PELT: {hit.old_weekly_vnd:,} -> {hit.new_weekly_vnd:,} ₫ mỗi tuần, giữ {hit.weeks_held} tuần ({hit.direction})"
    )
    stale = []
    for folder in OUT_DIRS:
        path = folder / NAME
        if args.check:
            have = path.read_bytes().replace(b"\r\n", b"\n") if path.is_file() else None
            if have != out.data.replace(b"\r\n", b"\n"):
                stale.append(path)
            continue
        folder.mkdir(parents=True, exist_ok=True)
        path.write_bytes(out.data)
        print(f"đã ghi {path.relative_to(REPO)}")
    if stale:
        print("lệch với bộ sinh: " + ", ".join(str(p.relative_to(REPO)) for p in stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
