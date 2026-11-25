"""Backtest rolling-origin của gói ML (dữ liệu tổng hợp, hai họ bộ sinh). Ví dụ:

    uv run scripts/ml_backtest.py --all --out ml/backtest-results/phase-2.json --tables ml/backtest-results/phase-2.md
    uv run scripts/ml_backtest.py --evaluate --quick
    uv run scripts/ml_backtest.py --k5 --out k5.json --tables k5.md   # K5 (#26), docs/research/backtest-final.md mục "K5"
    uv run --with statsforecast==2.1.1 scripts/ml_backtest.py --statsforecast   # so với StatsForecast (tùy chọn)

Chi tiết cờ: `--help`. Phương pháp và số đo: docs/research/backtest-phase-2.md. Không gọi AWS, không đọc DB.
"""

from yofina_ml.backtest.cli import main

if __name__ == "__main__":
    main()
