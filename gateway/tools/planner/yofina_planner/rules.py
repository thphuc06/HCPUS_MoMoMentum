"""Nạp bộ luật suitability từ `gateway/tools/planner/rules/*.yaml` (dữ liệu, không phải mã).

Mỗi file một luật, tên file trùng `id`. Ngưỡng nằm trong `thresholds` của file nên chủ dự án chỉnh được mà không động tới mã.
Thư mục luật: biến môi trường `YOFINA_SUITABILITY_RULES_DIR` nếu có, không thì thư mục `rules/` cạnh gói này (trong repo:
`gateway/tools/planner/rules`; trong zip Lambda: `rules/` ở gốc, do `build_lambda.py --extra gateway/tools/planner/rules:rules`).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

from yofina_core.suitability import EVALUATORS, SuitabilityRule, parse_rule


def default_rules_dir() -> Path:
    env = os.environ.get("YOFINA_SUITABILITY_RULES_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[1] / "rules"


def load_rules(directory: Path | None = None) -> tuple[SuitabilityRule, ...]:
    """Mọi luật trong thư mục, theo thứ tự bộ đánh giá (năm luật của hợp đồng). Luật sai định dạng thì ném lỗi (không bỏ qua
    âm thầm: một luật bị mất làm người dùng tưởng đã được kiểm)."""
    base = directory or default_rules_dir()
    rules: list[SuitabilityRule] = []
    for path in sorted(base.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        rule = parse_rule(raw)
        if rule.id != path.stem:
            raise ValueError(f"id luật {rule.id!r} không trùng tên file {path.name}")
        rules.append(rule)
    order = {name: i for i, name in enumerate(EVALUATORS)}
    rules.sort(key=lambda r: (order[r.evaluator], r.id))
    if not rules:
        raise ValueError(f"không có luật nào trong {base}")
    return tuple(rules)


@lru_cache(maxsize=1)
def cached_rules() -> tuple[SuitabilityRule, ...]:
    return load_rules()


def rules_version(rules: tuple[SuitabilityRule, ...]) -> str:
    """Phiên bản bộ luật để truy vết: `v` cộng phiên bản từng luật theo thứ tự, ví dụ `v1.1.1.1.1`."""
    return "v" + ".".join(str(r.version) for r in rules)
