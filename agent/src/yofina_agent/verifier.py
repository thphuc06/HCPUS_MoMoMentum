"""L4 Verifier (mã Python, không model): `NumericGrounding` và phán quyết suitability cho từng phương án.

`NumericGrounding`: mọi con số tiền và phần trăm trong văn bản do model viết phải có trong kết quả tool của CHÍNH lượt đó (cho phép làm
tròn kiểu "1,2 triệu", "1tr2", "300k", "250 nghìn" theo `textutil.extract_amounts`); số người dùng tự nói trong câu hỏi cũng hợp lệ. Số mà
model tự tính ra (tổng, hiệu) không có trong tool nên bị bắt: Analyst chỉ được chép số của tool.
Không kiểm ngày tháng và số đếm nhỏ (< 1.000 không đơn vị): chúng không phải số tiền và bản gọn đã cho sẵn ngày dạng `dd/mm`.

`assemble_verdict` ghép grounding và suitability thành `schemas.Verdict` kèm phản hồi có cấu trúc để Analyst sửa. Số vòng sửa tối đa là
cấu hình của harness (`verifier_max_rounds`), không nằm ở đây.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from yofina_agent.schemas import GroundingResult, OptionSuitability, UngroundedNumber, Verdict
from yofina_agent.textutil import extract_amounts
from yofina_core.blocks import RuleId
from yofina_core.money import format_vnd
from yofina_core.suitability import SuitabilityVerdict

_PERCENT_RE = re.compile(r"(?<![\d.,/])(\d{1,3}(?:[.,]\d+)?)\s*%")


@dataclass
class Allowed:
    """Tập số hợp lệ của một lượt: số tiền (VND, giá trị tuyệt đối) và phần trăm (làm tròn)."""

    money: set[int] = field(default_factory=set)
    percent: set[int] = field(default_factory=set)

    def add_payload(self, node: Any) -> None:
        """Duyệt JSON kết quả tool: mọi số nguyên, mọi số thực (cũng là phần trăm khi nhỏ), và số tiền nằm trong chuỗi định dạng."""
        if isinstance(node, bool) or node is None:
            return
        if isinstance(node, int):
            self.money.add(abs(node))
            if 0 <= node <= 100:
                self.percent.add(node)
        elif isinstance(node, float):
            self.money.add(abs(round(node)))
            if 0 <= node <= 1.5:
                self.percent.add(round(node * 100))
            if 0 <= node <= 100:
                self.percent.add(round(node))
        elif isinstance(node, str):
            self.money.update(v for v, _ in extract_amounts(node))
            self.percent.update(round(float(m.replace(",", "."))) for m in _PERCENT_RE.findall(node))
        elif isinstance(node, Mapping):
            for v in node.values():
                self.add_payload(v)
        elif isinstance(node, Sequence):
            for v in node:
                self.add_payload(v)

    def add_text(self, text: str) -> None:
        self.add_payload(text)

    @classmethod
    def from_payloads(cls, payloads: Iterable[Any], user_texts: Iterable[str] = ()) -> Allowed:
        a = cls()
        for p in payloads:
            a.add_payload(p)
        for t in user_texts:
            a.add_text(t)
        return a


def _snippet(text: str) -> str:
    return " ".join(text.split())[:200]


class NumericGrounding:
    """Kiểm căn cứ của số trong văn bản. Hàm thuần, có unit test."""

    @staticmethod
    def check(
        texts: Mapping[str, str],
        allowed: Allowed,
        *,
        extra_amounts: Mapping[str, int] | None = None,
    ) -> GroundingResult:
        """`texts`: nơi -> văn bản (ví dụ `narrative`, `option:x:summary`). `extra_amounts`: số tiền model đặt trong tham số hành động."""
        checked = 0
        bad: list[UngroundedNumber] = []
        for where, text in texts.items():
            for value, tol in extract_amounts(text):
                checked += 1
                if not any(abs(value - a) <= max(tol, 0.5) for a in allowed.money):
                    bad.append(
                        UngroundedNumber(text=format_vnd(value)[:60], value_vnd=value, context=_snippet(f"{where}: {text}"))
                    )
            for raw in _PERCENT_RE.findall(text):
                checked += 1
                value = float(raw.replace(",", "."))
                if not any(abs(value - p) <= 0.5 for p in allowed.percent):
                    bad.append(UngroundedNumber(text=f"{raw}%"[:60], context=_snippet(f"{where}: {text}")))
        for where, amount in (extra_amounts or {}).items():
            checked += 1
            if amount not in allowed.money:
                bad.append(
                    UngroundedNumber(text=format_vnd(amount)[:60], value_vnd=amount, context=_snippet(f"tham số hành động của {where}"))
                )
        return GroundingResult(ok=not bad, checked_count=checked, ungrounded=bad)


def suitability_status(v: SuitabilityVerdict) -> str:
    """Trạng thái của phương án nếu chọn, suy ra từ luật: có vi phạm `block` là hụt, chỉ `warn` là sát, sạch là đủ."""
    if any(x.severity == "block" for x in v.violations):
        return "short"
    return "tight" if v.violations else "ok"


def passed_rules(v: SuitabilityVerdict, limit: int = 8) -> list[RuleId]:
    return [c.rule_id for c in v.checked if c.outcome == "pass"][:limit]


def assemble_verdict(
    grounding: GroundingResult,
    suitability: Sequence[OptionSuitability],
    *,
    attempt: int,
    max_rounds: int,
    extra_feedback: Sequence[str] = (),
) -> Verdict:  # noqa: PLR0913
    """`action`: pass nếu mọi thứ đạt; retry nếu còn vòng sửa; fallback khi hết vòng (chỉ phát khối số liệu tất định + notice)."""
    feedback: list[str] = list(extra_feedback)
    failed: list[str] = []
    for g in grounding.ungrounded:
        feedback.append(
            f"Số {g.text} không có trong dữ liệu tool ({g.context or 'văn bản'}). Chỉ chép số đã cho trong dữ liệu, không tự tính."[:300]
        )
        failed.append("numeric_grounding")
    for s in suitability:
        for v in s.verdict.violations:
            if v.severity == "block":
                feedback.append(f"Phương án {s.option_id} vi phạm luật {v.rule_id}: {v.message}"[:300])
                failed.append(v.rule_id)
    ok = grounding.ok and all(s.verdict.ok for s in suitability)
    if ok:
        feedback = []
    if ok:
        action = "pass"
    elif attempt <= max_rounds:
        action = "retry"
    else:
        action = "fallback"
    return Verdict(
        ok=ok,
        grounding=grounding,
        suitability=list(suitability),
        feedback=feedback[:10],
        failed_rules=list(dict.fromkeys(failed)),  # type: ignore[arg-type]
        attempt=attempt,
        action=action,  # type: ignore[arg-type]
    )
