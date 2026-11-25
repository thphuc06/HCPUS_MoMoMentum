"""Đo hệ số tăng chi tối thiểu của hũ Ăn uống trong hai tuần gần nhất để PELT xác nhận điểm gãy trên lịch sử 120 ngày của `minh`
(cảnh 4 chạy thật, issue #22). CÔNG CỤ ĐO TRÊN MÁY: không gọi AWS, không gọi model, không ghi gì.

    uv run python scripts/measure_scene4_pelt.py                  # bảng hệ số -> phát hiện, hệ số tối thiểu, độ bền
    uv run python scripts/measure_scene4_pelt.py --json           # thêm bản JSON của các bảng

Cách dựng (đúng như `scripts/inject_behavior_shift.py`, dùng lại chính hàm `plan_shift` của nó, không chép mã):

- Lịch sử: persona `minh` sinh lại tất định ở ngày neo (`personas.generate`), chi tiêu từng NGÀY của hũ Ăn uống giống nguồn của bộ phát
  hiện (`app_get_daily_spend`: chi trừ tiền hũ, không gắn nghĩa vụ), ngày cuối là hôm qua. Không cài điểm gãy nào vào lịch sử.
- Mức chi tuần cũ là trung vị các tuần đầy đủ có chi trước hai tuần cuối (`baseline_weekly`). Với hệ số `f`, mỗi tuần trong hai tuần
  cuối được thêm khoản chi cho tới `f` lần mức cũ, chia thành số khoản điển hình mỗi tuần của hũ, rơi vào ngày ngẫu nhiên trong tuần
  đó, nơi chi lấy từ lịch sử của hũ (`plan_shift`). Khoản thêm là dòng nạp ngoài ví, cũng vào chuỗi chi của hũ (`external`).
- Phát hiện: `yofina_ml.change.prepare_weekly` rồi `detect_confirmed` với `change_defaults.json` hiện tại (không ghi đè tham số).

"Hệ số tối thiểu" là hệ số nhỏ nhất trên lưới mà PELT xác nhận với MỌI hạt chia khoản (cách chia số tiền và chọn ngày của
`plan_shift` có ngẫu nhiên) và với mọi hệ số lớn hơn trên lưới. Bảng phụ: lệch ngày mô phỏng (tải tệp sau ngày neo vài ngày) và các
seed persona khác (độ nhạy của ngưỡng với dữ liệu sinh ra). Kết quả và cách đọc ở `docs/research/2026-11-26-canh4-pelt.md`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
for _extra in ("data", "libs/yofina_core/src"):
    if str(REPO / _extra) not in sys.path:
        sys.path.insert(0, str(REPO / _extra))

from yofina_ml import change as ch  # noqa: E402

PERSONA = "minh"
JAR = "an_uong"
SHIFT_WEEKS = 2
#: cùng ngày neo với YOFINA_DEMO_ANCHOR_DATE (infra-cdk, context `demoAnchorDate` của YofinaTools)
DEFAULT_ANCHOR = date(2026, 11, 21)
#: lưới hệ số và số hạt chia khoản của phép đo chính
GRID_STEP = 0.1
GRID_LO = 1.1
GRID_HI = 4.0
SPLIT_SEEDS = 20


def load_shift_module():
    """`scripts/inject_behavior_shift.py` dưới tên module của nó (dataclass cần tra module theo tên)."""
    name = "inject_behavior_shift"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@dataclass(frozen=True)
class History:
    """Lịch sử của persona ở ngày neo, đủ cho kế hoạch và phát hiện.

    `spends`: khoản chi của hũ (kiểu `Spend` của inject_behavior_shift), tới hôm qua. `daily`: chi từng ngày của hũ, cũ tới mới, ngày
    cuối là hôm qua. `expenses`: MỌI khoản chi của persona (mọi hũ, mọi nguồn) dạng (ngày, số tiền dương, đối tác), để tránh dòng nạp bị
    coi là trùng sổ cái. `merchants`: đối tác của hũ, nhiều khoản trước."""

    persona: str
    anchor: date
    history_days: int
    spends: tuple[Any, ...]
    daily: np.ndarray
    expenses: tuple[tuple[date, int, str | None], ...]
    merchants: tuple[str, ...]

    @property
    def first_day(self) -> date:
        return self.anchor - timedelta(days=self.history_days)


def persona_history(
    persona: str = PERSONA,
    anchor: date = DEFAULT_ANCHOR,
    *,
    jar: str = JAR,
    seed: int | None = None,
) -> History:
    """Lịch sử của `persona` (seed của spec, hoặc `seed`) ở ngày neo `anchor`, cho hũ `jar`."""
    from collections import Counter

    from personas import generate

    sc = load_shift_module()
    d = (
        generate(persona, anchor=anchor)
        if seed is None
        else generate(persona, anchor=anchor, seed=seed)
    )
    own = [
        t
        for t in d.transactions
        if t.kind == "expense"
        and t.jar_code == jar
        and t.funding_source == "jar"
        and t.obligation_key is None
        and t.days_ago >= 1
    ]
    spends = tuple(
        sc.Spend(anchor - timedelta(days=t.days_ago), -t.amount_vnd, t.merchant) for t in own
    )
    daily = np.zeros(d.history_days)
    for t in own:
        if t.days_ago <= d.history_days:
            daily[d.history_days - t.days_ago] += -t.amount_vnd
    expenses = tuple(
        (anchor - timedelta(days=t.days_ago), abs(t.amount_vnd), t.merchant)
        for t in d.transactions
        if t.kind == "expense"
    )
    merchants = tuple(m for m, _ in Counter(s.merchant for s in spends if s.merchant).most_common())
    return History(persona, anchor, d.history_days, spends, daily, expenses, merchants)


def split_seed(i: int) -> str:
    """Hạt chia khoản thứ `i` (0 là hạt mặc định của inject_behavior_shift)."""
    sc = load_shift_module()
    return sc.SEED if i == 0 else f"{sc.SEED}:{i}"


def plan(
    history: History,
    factor: float,
    *,
    merchants: Sequence[str] | None = None,
    seed: str | None = None,
) -> list[Any]:
    """Các khoản chi thêm (kiểu `PlannedRow`) để mỗi tuần trong hai tuần cuối đạt `factor` lần mức cũ (`plan_shift`). `merchants`
    giới hạn nơi chi được chọn (các khoản khác vẫn tính vào mức cũ và số khoản mỗi tuần, chỉ không làm tên nơi chi)."""
    sc = load_shift_module()
    spends = history.spends
    if merchants is not None:
        keep = set(merchants)
        spends = tuple(
            sc.Spend(s.day, s.amount_vnd, s.merchant if s.merchant in keep else None)
            for s in spends
        )
    return sc.plan_shift(
        list(spends),
        history.anchor,
        factor=factor,
        shift_weeks=SHIFT_WEEKS,
        seed=seed or sc.SEED,
    )


def daily_with(history: History, rows: Sequence[Any], *, drift_days: int = 0) -> np.ndarray:
    """Chuỗi chi từng ngày của hũ sau khi thêm `rows`, khi ngày mô phỏng là ngày neo + `drift_days` (các ngày sau ngày neo không có chi
    nào của lịch sử seed)."""
    out = np.concatenate([history.daily, np.zeros(max(drift_days, 0))])
    last = history.anchor + timedelta(days=drift_days - 1)
    for r in rows:
        if history.first_day <= r.day <= last:
            out[(r.day - history.first_day).days] += r.amount_vnd
    return out


def detect(
    history: History, rows: Sequence[Any], params: ch.ChangeParams, *, drift_days: int = 0
) -> ch.Confirmed | None:
    return ch.detect_confirmed(
        ch.prepare_weekly(daily_with(history, rows, drift_days=drift_days), params), params
    )


def grid(lo: float = GRID_LO, hi: float = GRID_HI, step: float = GRID_STEP) -> list[float]:
    n = round((hi - lo) / step)
    return [round(lo + i * step, 4) for i in range(n + 1)]


def scan(
    history: History,
    params: ch.ChangeParams,
    factors: Sequence[float],
    *,
    merchants: Sequence[str] | None = None,
    split_seeds: int = SPLIT_SEEDS,
    drift_days: int = 0,
) -> list[dict[str, Any]]:
    """Mỗi hệ số: số hạt chia khoản PELT xác nhận (trên `split_seeds`), và mức cũ/mới của lần xác nhận với hạt mặc định."""
    sc = load_shift_module()
    base = sc.baseline_weekly(list(history.spends), history.anchor, SHIFT_WEEKS)
    out = []
    for f in factors:
        hits = []
        for i in range(split_seeds):
            try:
                rows = plan(history, f, merchants=merchants, seed=split_seed(i))
            except sc.ShiftError:  # hai tuần cuối đã cao hơn mức cần đạt: không có gì để thêm
                rows = []
            hits.append(detect(history, rows, params, drift_days=drift_days))
        first = hits[0]
        out.append(
            {
                "factor": f,
                "target_weekly_vnd": round(base * f),
                "confirmed": sum(h is not None for h in hits),
                "of": split_seeds,
                "old_weekly_vnd": first.old_weekly_vnd if first else None,
                "new_weekly_vnd": first.new_weekly_vnd if first else None,
                "weeks_held": first.weeks_held if first else None,
            }
        )
    return out


def minimal_factor(
    history: History,
    params: ch.ChangeParams,
    *,
    merchants: Sequence[str] | None = None,
    factors: Sequence[float] | None = None,
    split_seeds: int = SPLIT_SEEDS,
) -> float | None:
    """Hệ số nhỏ nhất trên lưới mà PELT xác nhận với mọi hạt chia khoản, và mọi hệ số lớn hơn trên lưới cũng vậy. None nếu không có."""
    rows = scan(history, params, factors or grid(), merchants=merchants, split_seeds=split_seeds)
    best: float | None = None
    for r in reversed(rows):
        if r["confirmed"] != r["of"]:
            break
        best = r["factor"]
    return best


def exact_threshold(
    history: History, params: ch.ChangeParams, *, lo: float, hi: float, step: float = 0.01
) -> float | None:
    """Hệ số nhỏ nhất (lưới mịn `step`) mà PELT xác nhận với hạt chia khoản mặc định."""
    for f in grid(lo, hi, step):
        if detect(history, plan(history, f), params) is not None:
            return f
    return None


def _fmt_table(rows: Sequence[dict[str, Any]]) -> str:
    lines = ["  hệ số  mức tuần cần đạt  xác nhận   mức cũ -> mới (hạt mặc định)"]
    for r in rows:
        level = (
            f"{r['old_weekly_vnd']:,} -> {r['new_weekly_vnd']:,} (giữ {r['weeks_held']} tuần)"
            if r["old_weekly_vnd"] is not None
            else "-"
        )
        lines.append(
            f"  {r['factor']:<5}  {r['target_weekly_vnd']:>16,}  {r['confirmed']:>3}/{r['of']:<4}  {level}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--anchor", type=date.fromisoformat, default=DEFAULT_ANCHOR, help="ngày neo (YYYY-MM-DD)"
    )
    ap.add_argument("--json", action="store_true", help="in thêm JSON của các bảng")
    ap.add_argument(
        "--drift-days", type=int, default=3, help="số ngày lệch ngày mô phỏng tối đa để đo độ bền"
    )
    ap.add_argument(
        "--persona-seeds", type=int, default=8, help="số seed persona khác để đo độ nhạy (1..N)"
    )
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    params = ch.load_params()
    sc = load_shift_module()
    h = persona_history(anchor=args.anchor)
    base = sc.baseline_weekly(list(h.spends), h.anchor, SHIFT_WEEKS)
    weeks = ch.prepare_weekly(h.daily, params)
    print(
        f"persona {h.persona}, hũ {JAR}, ngày neo {h.anchor}, {h.history_days} ngày lịch sử, {weeks.n_weeks} tuần đầy đủ; "
        f"tham số {params.version} (c={params.pelt_penalty_c}, min_relative_change={params.min_relative_change})"
    )
    print(f"chi theo tuần (cũ tới mới): {[round(float(x)) for x in weeks.raw]}")
    print(f"mức chi tuần cũ (trung vị trước {SHIFT_WEEKS} tuần cuối): {base:,} ₫")
    print(f"lịch sử chưa thêm gì: xác nhận={ch.detect_confirmed(weeks, params) is not None}")

    table = scan(h, params, grid(1.5, 3.0, GRID_STEP))
    print(f"\nHệ số -> PELT xác nhận ({SPLIT_SEEDS} hạt chia khoản, ngày mô phỏng = ngày neo):")
    print(_fmt_table(table))
    fmin = minimal_factor(h, params)
    exact = exact_threshold(
        h, params, lo=max(GRID_LO, (fmin or GRID_HI) - GRID_STEP), hi=fmin or GRID_HI
    )
    print(f"\nhệ số tối thiểu (lưới {GRID_STEP}, mọi hạt chia khoản): {fmin}")
    print(f"ngưỡng mịn (lưới 0,01, hạt mặc định): {exact}")

    drift = {
        k: scan(h, params, grid(1.5, 4.0, 0.5), split_seeds=5, drift_days=k)
        for k in range(0, args.drift_days + 1)
    }
    print("\nĐộ bền khi tải tệp sau ngày neo (số hạt chia khoản xác nhận trên 5):")
    for k, rows in drift.items():
        print(f"  lệch {k} ngày: " + "  ".join(f"{r['factor']}:{r['confirmed']}" for r in rows))

    seeds = {}
    for s in range(1, args.persona_seeds + 1):
        hs = persona_history(anchor=args.anchor, seed=s)
        pre = ch.detect_confirmed(ch.prepare_weekly(hs.daily, params), params) is not None
        seeds[s] = {"minimal_factor": minimal_factor(hs, params, split_seeds=5), "preexisting": pre}
    print("\nĐộ nhạy theo seed persona (lưới 0,1, 5 hạt chia khoản):")
    for s, r in seeds.items():
        print(
            f"  seed {s}: hệ số tối thiểu {r['minimal_factor']}, lịch sử tự có điểm gãy: {r['preexisting']}"
        )

    if args.json:
        print(
            json.dumps(
                {
                    "anchor": h.anchor.isoformat(),
                    "params_version": params.version,
                    "baseline_weekly_vnd": base,
                    "table": table,
                    "minimal_factor": fmin,
                    "exact_threshold": exact,
                    "drift": drift,
                    "persona_seeds": seeds,
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
