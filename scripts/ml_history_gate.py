"""Độ phủ dải số dư theo độ dài lịch sử (30 đến 120 ngày và lịch sử đủ) và ngưỡng hiện % của BR-31 (issue #9). Ví dụ:

    uv run scripts/ml_history_gate.py --out ml/backtest-results/history-gate.json                 # đo, in bảng (~30 phút)
    uv run scripts/ml_history_gate.py --out ml/backtest-results/history-gate.json --write-calibration  # đo và ghi ngưỡng
    uv run scripts/ml_history_gate.py --quick                                                     # kiểm khói

`--write-calibration` ghi `probability_min_history_days` của hũ dày và thưa vào `ml/yofina_ml/calibration/default.py` (giữ nguyên
rho, level_sigma, probability_ok). Phương pháp và số đo: docs/research/backtest-final.md. Không gọi AWS, không đọc DB.
"""

import argparse
import json
import sys
from pathlib import Path

from yofina_ml.backtest import history_gate, report
from yofina_ml.backtest.cli import CALIBRATION_PATH
from yofina_ml.calibration import default as calibration_default


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="2 seed, origin bước 28 (kiểm khói)")
    ap.add_argument("--paths", type=int, default=2000, help="số đường Monte Carlo")
    ap.add_argument("--out", type=Path, default=None, help="ghi kết quả JSON")
    ap.add_argument(
        "--write-calibration", action="store_true", help="ghi ngưỡng vào calibration/default.py"
    )
    args = ap.parse_args()
    result = history_gate.run(quick=args.quick, n_paths=args.paths)
    print(history_gate.render(result))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    if args.write_calibration:
        payload = history_gate.calibration_payload(calibration_default.CALIBRATION, result)
        report.write_default_calibration(CALIBRATION_PATH, payload)
        print(f"đã ghi {CALIBRATION_PATH}")


if __name__ == "__main__":
    main()
