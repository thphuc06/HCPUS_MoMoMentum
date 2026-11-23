"""Cấu hình của phân hũ tự động (F2): đọc `classify_defaults.json` (đóng gói cùng module), ghi đè bằng biến môi trường.

Không có ngưỡng nào nằm trong logic: pipeline `yofina-classify`, Lambda ledger (`assign_jar`, `GET /review`) và bộ kiểm
`evals/classification` cùng đọc từ đây. Mỗi số trong JSON có `value`, `unit`, `note`, `source`; số đã hiệu chỉnh ghi nguồn là bộ kiểm.

Ghi đè: biến môi trường `YOFINA_CLASSIFY_<TÊN HOA>` (ví dụ `YOFINA_CLASSIFY_AUTO_MIN_CONFIDENCE`), CDK đặt. Cố ý chỉ đọc biến môi trường,
không đọc SSM: Lambda phân loại chạy theo từng giao dịch, mỗi khóa SSM vắng là một vòng mạng.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, fields
from importlib import resources
from typing import Any

DEFAULTS_FILE = "classify_defaults.json"
ENV_PREFIX = "YOFINA_CLASSIFY_"


class ClassifyConfigError(ValueError):
    """Số cấu hình sai định dạng hoặc ngoài miền hợp lệ."""


@dataclass(frozen=True)
class ClassifyThresholds:
    version: str
    auto_min_confidence: float
    review_min_confidence: float
    type_map_confidence: float
    rule_confidence: float
    exact_match_confidence: float
    exact_match_user_bonus: float
    knn_k: int
    knn_min_similarity: float
    knn_cal_intercept: float
    knn_cal_w_sim: float
    knn_cal_w_margin: float
    llm_cal_intercept: float
    llm_cal_slope: float
    history_min_count: int
    history_max_confidence: float
    conflict_weight: float
    small_one_off_max_vnd: int
    small_one_off_jar_code: str
    correction_min_count: int
    auto_min_confidence_step: float
    auto_min_confidence_cap: float
    suggestions_max: int

    def validate(self) -> ClassifyThresholds:
        unit = (
            "auto_min_confidence",
            "review_min_confidence",
            "type_map_confidence",
            "rule_confidence",
            "exact_match_confidence",
            "history_max_confidence",
            "conflict_weight",
            "auto_min_confidence_cap",
        )
        for name in unit:
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ClassifyConfigError(f"{name} phải nằm trong [0, 1]")
        if not self.review_min_confidence <= self.auto_min_confidence:
            raise ClassifyConfigError(
                "review_min_confidence không được lớn hơn auto_min_confidence"
            )
        if not 1 <= self.knn_k <= 20:
            raise ClassifyConfigError("knn_k phải từ 1 đến 20 (giới hạn của app_knn_labeled)")
        if not 0 <= self.suggestions_max <= 2:
            raise ClassifyConfigError("suggestions_max phải từ 0 đến 2 (CHECK của suggested_jars)")
        if self.small_one_off_max_vnd < 0:
            raise ClassifyConfigError("small_one_off_max_vnd không được âm")
        return self

    def auto_threshold_for(self, payee_auto_min: float | None) -> float:
        """Ngưỡng tự gán áp cho một người nhận: ngưỡng riêng (nếu đã nâng) không bao giờ thấp hơn ngưỡng chung."""
        if payee_auto_min is None:
            return self.auto_min_confidence
        return max(self.auto_min_confidence, float(payee_auto_min))


def load_raw() -> dict[str, Any]:
    text = resources.files("yofina_ledger").joinpath(DEFAULTS_FILE).read_text(encoding="utf-8")
    return json.loads(text)


def load_thresholds(env: Mapping[str, str] | None = None) -> ClassifyThresholds:
    """Số cấu hình đã ghi đè bằng môi trường và đã kiểm miền. Thiếu khóa trong JSON là lỗi (không đoán)."""
    env = os.environ if env is None else env
    raw = load_raw()
    table: Mapping[str, Mapping[str, Any]] = raw["thresholds"]
    values: dict[str, Any] = {"version": str(raw["version"])}
    for f in fields(ClassifyThresholds):
        if f.name == "version":
            continue
        if f.name not in table:
            raise ClassifyConfigError(f"classify_defaults.json thiếu khóa {f.name}")
        value = table[f.name]["value"]
        override = env.get(ENV_PREFIX + f.name.upper())
        if override not in (None, ""):
            value = override
        cast = {"int": int, "float": float, "str": str}[
            "int" if f.type == "int" else "str" if f.type == "str" else "float"
        ]
        try:
            values[f.name] = cast(value)
        except (TypeError, ValueError) as exc:
            raise ClassifyConfigError(f"{f.name}: không đọc được giá trị {value!r}") from exc
    return ClassifyThresholds(**values).validate()
