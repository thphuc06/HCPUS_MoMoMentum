"""Hợp đồng phase 6, luồng K (agent như người tư vấn): khối `reasoning`. Hình dạng chung (schema, fixture, Zod) đã được
`test_contracts_blocks.py` và `ts/blocks.fixtures.test.mjs` kiểm; ở đây là `build_reasoning` và các bất biến mà JSON Schema không diễn
đạt được (Pydantic quyết định)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from conftest import CONTRACTS, load_json
from pydantic import ValidationError

from yofina_core import blocks as b

TRACE = "8f3a21c94b7e4d0aa1c25e6f7b8c9d01"
AS_OF = datetime(2026, 12, 10, 3, 0, tzinfo=UTC)
APP_DATE = date(2026, 11, 21)


def fx(name: str) -> dict[str, Any]:
    return load_json(CONTRACTS / "fixtures" / "blocks" / "valid" / f"{name}.json")


@pytest.mark.parametrize(
    "name", ["reasoning.what_if", "reasoning.dang_can_nhac", "reasoning.roadmap"]
)
def test_build_reasoning_dung_fixture_va_fallback_do_ma_dung(name):
    want = fx(name)
    built = b.block_to_wire(
        b.build_reasoning(
            data=want["data"], trace_id=TRACE, source_tool="agent", as_of=AS_OF, app_date=APP_DATE
        )
    )
    assert built == want
    assert built["id"] == f"reasoning:{TRACE}"
    # fallback_text không chép chữ do model viết (bước, kết luận)
    data = want["data"]
    model_texts = [s[k] for s in data["steps"] for k in ("seen", "why", "effect")]
    if "conclusion" in data:
        model_texts.append(data["conclusion"]["text"])
    assert all(t not in built["fallback_text"] for t in model_texts)


def _data(**changes: Any) -> dict[str, Any]:
    return {**fx("reasoning.what_if")["data"], **changes}


STEP = fx("reasoning.what_if")["data"]["steps"][0]


@pytest.mark.parametrize(
    ("changes", "why"),
    [
        ({"steps": [{**STEP, "step_id": "s2"}]}, "step_id không bắt đầu từ s1"),
        ({"steps": [STEP, {**STEP, "step_id": "s3"}]}, "step_id nhảy cóc"),
        ({"complete": False}, "bản chưa xong mà đã có kết luận"),
        ({"complete": False, "steps": [], "conclusion": None}, "bản chưa xong không có bước nào"),
        ({"steps": [], "conclusion": None}, "không có bước lẫn kết luận"),
        (
            {"conclusion": {"text": "Nên hoãn.", "step_id": "bu_an_uong"}},
            "what_if trỏ bước lộ trình",
        ),
        ({"context": "roadmap"}, "lộ trình trỏ phương án"),
        (
            {
                "conclusion": {
                    "text": "Nên hoãn.",
                    "option_id": "defer",
                    "personal": ["behavior", "behavior"],
                }
            },
            "personal lặp",
        ),
    ],
)
def test_bat_bien_pydantic_tu_choi(changes, why):
    data = {k: v for k, v in _data(**changes).items() if v is not None}
    with pytest.raises(ValidationError):
        b.ReasoningData.model_validate(data)


def test_chi_ket_luan_khong_buoc_van_hop_le_khi_da_xong():
    d = b.ReasoningData.model_validate(
        {
            "context": "what_if",
            "complete": True,
            "steps": [],
            "conclusion": {"text": "Nên hoãn.", "option_id": "defer"},
        }
    )
    block = b.build_reasoning(
        data=d, trace_id=TRACE, source_tool="agent", as_of=AS_OF, app_date=APP_DATE
    )
    assert block.fallback_text == "Yofina có một gợi ý cho bạn."
