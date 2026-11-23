"""Bộ đánh giá suitability: sáu luật của `rules/*.yaml`, mỗi luật một hàm theo tên `evaluator`. Tất định, không model.

`evaluate(proposal, facts, rules)` trả `SuitabilityVerdict` có `checked` LIỆT KÊ ĐỦ mọi luật (luật không áp dụng thì `skipped`),
`violations` (mỗi vi phạm kèm mức block hoặc warn theo luật và theo nguồn của đề xuất) và `ok` (đúng khi không có block).

Ngưỡng (số tháng dự phòng, tỷ lệ nghĩa vụ trên thu nhập, tỷ lệ phủ nghĩa vụ, mức rủi ro tối đa) đọc từ `thresholds` của file
luật, KHÔNG nằm trong mã. Câu cảnh báo (`message`) lấy từ file luật; phần `detail` của `RuleCheck` do code dựng từ số liệu thật.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from yofina_core.blocks import RuleCheck
from yofina_core.money import format_vnd
from yofina_core.suitability import (
    AppliesWhen,
    Proposal,
    SuitabilityRule,
    SuitabilityVerdict,
    Violation,
)
from yofina_planner.facts import SuitabilityFacts
from yofina_planner.rules import rules_version

#: loại đề xuất mặc định là chi tùy ý khi người gọi không nói `is_essential` (mua một lần, mua trả sau, khoản định kỳ mới).
DISCRETIONARY_KINDS = frozenset({"one_time_purchase", "bnpl_purchase", "recurring_expense"})
#: loại đề xuất làm tăng nghĩa vụ phải trả (tính vào tỷ lệ nghĩa vụ trên thu nhập).
OBLIGATION_ADDING_KINDS = frozenset({"bnpl_purchase", "use_credit", "recurring_expense"})
RISK_RANK = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class Outcome:
    outcome: str  # pass | fail | skipped
    detail: str | None = None


Evaluator = Callable[[SuitabilityRule, Proposal, SuitabilityFacts, "Context"], Outcome]


@dataclass(frozen=True)
class Context:
    added_obligation_vnd: int | None = None


def effective_essential(proposal: Proposal) -> bool | None:
    """`is_essential` do người gọi nói; không nói thì chi tiêu mua sắm mặc định là tùy ý, loại khác là chưa rõ (None)."""
    if proposal.is_essential is not None:
        return proposal.is_essential
    return False if proposal.kind in DISCRETIONARY_KINDS else None


def applies(when: AppliesWhen | None, proposal: Proposal) -> bool:
    if when is None:
        return True
    if when.categories is not None and proposal.category not in when.categories:
        return False
    if when.origins is not None and proposal.origin not in when.origins:
        return False
    if when.funding_sources is not None and proposal.funding_source not in when.funding_sources:
        return False
    return not (when.essential is not None and effective_essential(proposal) != when.essential)


def _threshold(rule: SuitabilityRule, name: str) -> float | int | str | bool:
    return rule.thresholds[name].value


def _essential_covered(
    rule: SuitabilityRule, proposal: Proposal, facts: SuitabilityFacts, ctx: Context
) -> Outcome:
    """Nghĩa vụ thiết yếu đến hạn trước kỳ lương kế phải còn được phủ đủ sau khi trừ khoản đề xuất khỏi hũ nguồn."""
    if facts.next_payday is None:
        return Outcome("skipped", "Chưa khai ngày nhận lương nên chưa xét nghĩa vụ trước kỳ lương.")
    first = facts.today + timedelta(days=1)
    last = facts.next_payday - timedelta(days=1)
    need: dict[str, int] = {}
    for ob, _due in facts.dues_between(first, last):
        jar = facts.pay_jar_of(ob)
        if ob.is_essential and jar:
            need[jar] = need.get(jar, 0) + ob.amount_vnd
    if not need:
        return Outcome("pass", "Không có nghĩa vụ thiết yếu đến hạn trước kỳ lương kế.")
    cover = float(_threshold(rule, "cover_ratio"))
    spent_from = proposal.jar_code if proposal.funding_source == "jar" else None
    worst: tuple[float, str] | None = None
    for code, total in need.items():
        jar = facts.jar(code)
        balance = jar.balance_vnd if jar else 0
        if spent_from == code and proposal.amount_vnd:
            balance -= proposal.amount_vnd
        ratio = balance / total
        if worst is None or ratio < worst[0]:
            worst = (ratio, jar.name if jar else code)
    assert worst is not None
    ok = worst[0] >= cover
    pct = f"{max(worst[0], 0) * 100:.0f}".replace(".", ",")
    return Outcome(
        "pass" if ok else "fail",
        f"Hũ {worst[1]} còn phủ {pct}% nghĩa vụ thiết yếu trước kỳ lương kế.",
    )


def _emergency_before_investing(
    rule: SuitabilityRule, proposal: Proposal, facts: SuitabilityFacts, ctx: Context
) -> Outcome:
    monthly = facts.essential_monthly_vnd()
    fund = facts.emergency_fund_vnd()
    need_months = float(_threshold(rule, "min_emergency_months"))
    if monthly <= 0:
        return Outcome("pass", "Chưa có nghĩa vụ thiết yếu nào để ước lượng chi tiêu thiết yếu.")
    months = float(fund / monthly)
    text = (
        f"Quỹ dự phòng {format_vnd(fund)} đủ khoảng {months:.1f} tháng chi tiêu thiết yếu.".replace(
            ".", ","
        )
    )
    return Outcome("pass" if months >= need_months else "fail", text)


def _risk_within_tolerance(
    rule: SuitabilityRule, proposal: Proposal, facts: SuitabilityFacts, ctx: Context
) -> Outcome:
    tolerance = facts.risk_tolerance
    if tolerance not in RISK_RANK:
        tolerance = str(_threshold(rule, "unknown_tolerance_assumes"))
    allowed = str(_threshold(rule, f"max_risk_for_{tolerance}"))
    risk = proposal.risk_level or "high"  # chưa rõ mức rủi ro thì coi là cao (thận trọng)
    ok = RISK_RANK[risk] <= RISK_RANK[allowed]
    return Outcome(
        "pass" if ok else "fail",
        f"Mức rủi ro {risk} so với mức tối đa {allowed} theo khẩu vị rủi ro đã khai."
        if facts.risk_tolerance in RISK_RANK
        else f"Mức rủi ro {risk} so với mức tối đa {allowed} (chưa khai khẩu vị rủi ro).",
    )


def _no_credit_for_discretionary(
    rule: SuitabilityRule, proposal: Proposal, facts: SuitabilityFacts, ctx: Context
) -> Outcome:
    # Luật chỉ tới đây khi `applies_when` khớp (nguồn tín dụng, khoản không thiết yếu).
    return Outcome("fail", "Khoản chi tùy ý dùng nguồn tín dụng.")


def _obligation_income_ratio(
    rule: SuitabilityRule, proposal: Proposal, facts: SuitabilityFacts, ctx: Context
) -> Outcome:
    added = ctx.added_obligation_vnd
    if added is None:
        added = (proposal.amount_vnd or 0) if proposal.kind in OBLIGATION_ADDING_KINDS else 0
    if added <= 0:
        return Outcome("skipped", "Đề xuất không thêm nghĩa vụ phải trả.")
    income = facts.monthly_income_vnd
    if not income:
        return Outcome("skipped", "Chưa khai thu nhập nên chưa tính tỷ lệ nghĩa vụ.")
    total = facts.window_obligations_vnd() + added
    ratio = total / income
    limit = float(_threshold(rule, "max_ratio"))
    return Outcome(
        "pass" if ratio <= limit else "fail",
        f"Nghĩa vụ trong kỳ sẽ bằng {ratio * 100:.0f}% thu nhập (mức nên giữ {limit * 100:.0f}%).",
    )


def _source_jar_covers(
    rule: SuitabilityRule, proposal: Proposal, facts: SuitabilityFacts, ctx: Context
) -> Outcome:
    """Khoản lấy từ hũ nguồn (`funding_source` jar, `jar_code`) không vượt số dư hiện có của hũ trừ mức phải giữ lại."""
    if not proposal.amount_vnd or not proposal.jar_code:
        return Outcome("skipped", "Đề xuất không lấy một khoản tiền cụ thể từ hũ nào.")
    jar = facts.jar(proposal.jar_code)
    if jar is None:
        return Outcome("skipped", "Không thấy hũ nguồn trong ví để đối chiếu số dư.")
    keep = int(_threshold(rule, "min_remaining_vnd"))
    left = jar.balance_vnd - proposal.amount_vnd
    if left >= keep:
        return Outcome(
            "pass",
            f"Hũ {jar.name} có {format_vnd(jar.balance_vnd)}, còn {format_vnd(left)} sau khi lấy {format_vnd(proposal.amount_vnd)}.",
        )
    return Outcome(
        "fail",
        f"Hũ {jar.name} chỉ có {format_vnd(jar.balance_vnd)}, thiếu {format_vnd(keep - left)} cho khoản {format_vnd(proposal.amount_vnd)}.",
    )


EVALUATORS_BY_NAME: dict[str, Evaluator] = {
    "essential_obligations_covered": _essential_covered,
    "emergency_fund_before_investing": _emergency_before_investing,
    "risk_within_tolerance": _risk_within_tolerance,
    "no_credit_for_discretionary": _no_credit_for_discretionary,
    "obligation_income_ratio": _obligation_income_ratio,
    "source_jar_balance_covers": _source_jar_covers,
}


def evaluate(
    proposal: Proposal,
    facts: SuitabilityFacts,
    rules: tuple[SuitabilityRule, ...],
    *,
    added_obligation_vnd: int | None = None,
) -> SuitabilityVerdict:
    """Kiểm một đề xuất với toàn bộ luật. `added_obligation_vnd`: nghĩa vụ phát sinh chính xác do người gọi tính (gồm phí);
    vắng thì suy từ `amount_vnd` cho loại đề xuất làm tăng nghĩa vụ."""
    ctx = Context(added_obligation_vnd=added_obligation_vnd)
    checked: list[RuleCheck] = []
    violations: list[Violation] = []
    for rule in rules:
        if not applies(rule.applies_when, proposal):
            checked.append(
                RuleCheck(
                    rule_id=rule.id,
                    label=rule.title,
                    outcome="skipped",
                    detail="Luật này không áp dụng cho đề xuất này.",
                )
            )
            continue
        res = EVALUATORS_BY_NAME[rule.evaluator](rule, proposal, facts, ctx)
        if res.outcome == "fail":
            severity = rule.severity_for(proposal.origin)
            violations.append(Violation(rule_id=rule.id, severity=severity, message=rule.message))
            outcome = "fail" if severity == "block" else "warn"
        else:
            outcome = res.outcome
        checked.append(
            RuleCheck(
                rule_id=rule.id,
                label=rule.title,
                outcome=outcome,  # type: ignore[arg-type]
                detail=(res.detail or None) and res.detail[:200],
            )
        )
    return SuitabilityVerdict(
        ok=not any(v.severity == "block" for v in violations),
        violations=violations,
        checked=checked,
        rules_version=rules_version(rules),
    )


def obligation_ratio_figures(
    facts: SuitabilityFacts, added_vnd: int, rules: tuple[SuitabilityRule, ...]
) -> dict[str, float | int | bool] | None:
    """Số của luật `obligation_to_income` cho khối `obligation_impact`: tổng nghĩa vụ trong kỳ sau khi thêm `added_vnd`, thu nhập
    đã khai, tỷ lệ, ngưỡng của luật và có vượt không. None khi chưa khai thu nhập hoặc bộ luật không có luật này."""
    rule = next((r for r in rules if r.evaluator == "obligation_income_ratio"), None)
    income = facts.monthly_income_vnd
    if rule is None or not income:
        return None
    total = facts.window_obligations_vnd() + max(added_vnd, 0)
    ratio = total / income
    limit = float(_threshold(rule, "max_ratio"))
    return {
        "obligations_vnd": total,
        "income_vnd": income,
        "ratio": round(ratio, 4),
        "threshold": limit,
        "exceeds": ratio > limit,
    }


def passed_rule_ids(verdict: SuitabilityVerdict) -> list[str]:
    """Luật đã xét và qua (cho `checked_rules` của phương án)."""
    return [c.rule_id for c in verdict.checked if c.outcome == "pass"]
