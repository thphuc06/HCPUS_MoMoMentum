"""Bộ sinh dữ liệu tổng hợp CHỈ ĐỂ BACKTEST (hai họ khác hẳn nhau). Không phải persona demo (đó là `data/personas/`)
và không được import từ mã sản phẩm của `yofina_ml`.

- `hurdle_lognormal`: họ (i), cùng họ với mô hình hurdle theo lịch (mô hình có lợi thế nội tại).
- `shopping_sessions`: họ (ii), theo phiên mua và giỏ hàng, ngân sách tự điều chỉnh, điểm gãy lối sống.
"""

from __future__ import annotations

from yofina_ml.synth import hurdle_lognormal, shopping_sessions
from yofina_ml.synth.base import SynthPersona

FAMILIES = {
    "hurdle_lognormal": hurdle_lognormal,
    "shopping_sessions": shopping_sessions,
}


def generate(family: str, config: str, seed: int, n_days: int = 330) -> SynthPersona:
    return FAMILIES[family].generate(config, seed, n_days)


def config_names(family: str) -> tuple[str, ...]:
    return FAMILIES[family].CONFIG_NAMES


__all__ = ["FAMILIES", "SynthPersona", "config_names", "generate"]
