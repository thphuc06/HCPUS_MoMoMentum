"""Quét rộng tham số xác nhận đổi hành vi (PELT): CHỌN trên seed 101–108, ĐO LẠI trên seed 201–208 chưa thấy (tránh khớp quá).

CÔNG CỤ ĐO TRÊN MÁY, không phải mã sản phẩm. Dùng chung cách mô phỏng và chấm của `change_calibration` (mỗi đêm một lần, chỉ nhìn dữ liệu
tới hôm qua). Cột cuối quy ra tỷ lệ báo đúng nếu ngoài đời mỗi hũ đổi hành vi thật 0,5 hoặc 1 lần mỗi năm (bộ sinh cho chuỗi nào cũng có
điểm gãy nên tỷ lệ đúng đo thẳng trên bộ sinh lạc quan). Kết quả 23/11 ghi trong `change_defaults.json` (nguồn của `pelt_penalty_c`).

    uv run python -m yofina_ml.backtest.change_holdout [calib|holdout|both]
"""

from __future__ import annotations

import itertools
import json
import sys
from dataclasses import replace

from yofina_ml import change as ch
from yofina_ml.backtest import change_calibration as cc

BASE = ch.load_params()
GRID = {
    "pelt_penalty_c": [3.0, 4.0, 5.0, 6.0, 8.0],
    "min_relative_change": [0.3, 0.4, 0.5],
    "pelt_min_size_weeks": [2, 3],
}
COMBOS = [dict(zip(GRID, v, strict=True)) for v in itertools.product(*GRID.values())]


def run(seeds: list[int]) -> list[dict]:
    cases = cc.build_cases(seeds, BASE)
    per_case = cc._pool_map(cc._grid_job, [(c, BASE, COMBOS) for c in cases], None)
    out = []
    for i, combo in enumerate(COMBOS):
        sims = [pc[i] for pc in per_case]
        r = cc.evaluate(cases, sims, replace(BASE, **combo), "confirm")
        r.pop("by_family", None)
        out.append({**combo, **r})
    return out


def realistic(r: dict, shifts_per_jar_year: float) -> float | None:
    """Tỷ lệ báo đúng khi đổi hành vi thật xảy ra `shifts_per_jar_year` lần mỗi hũ-năm (ngoài đời hiếm hơn bộ sinh)."""
    tp = (r["recall_any"] or 0) * shifts_per_jar_year
    fa = r["fa_per_jar_year"] or 0
    return round(tp / (tp + fa), 3) if tp + fa else None


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    sets = {
        "calib": [101, 102, 103, 104, 105, 106, 107, 108],
        "holdout": [201, 202, 203, 204, 205, 206, 207, 208],
    }
    res = {}
    for name, seeds in sets.items():
        if which in (name, "both"):
            res[name] = run(seeds)
    print(json.dumps(res, ensure_ascii=False))
    for name, rows in res.items():
        print(
            f"\n== {name} ==  c  minrel  hold | recall(>=30%) recall(>=50%) FA/hũ-năm  trễ_med p90 | đúng@0.5/năm đúng@1/năm"
        )
        for r in rows:
            print(
                f"   {r['pelt_penalty_c']:>4} {r['min_relative_change']:>5} {r['pelt_min_size_weeks']:>3}  | "
                f"{r['recall_any']:>6} {r['recall_big_shift']:>6} {r['fa_per_jar_year']:>8}  "
                f"{r['delay_days_median']} {r['delay_days_p90']} | {realistic(r, 0.5)} {realistic(r, 1.0)}"
            )


if __name__ == "__main__":
    main()
