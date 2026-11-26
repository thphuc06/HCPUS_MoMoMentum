"""Jar layouts for onboarding and demo reset."""

from dataclasses import dataclass
from os import getenv

from yofina_core.wallet import DEFAULT_GOAL_JAR, DEFAULT_OBLIGATION_JAR, DEFAULT_SPENDING_JAR

DEMO_LAYOUT_ID = "demo"  # recorded in the reset audit event; the roadmap seed is mapped with the same aliases

# The active onboarding layout comes from jar_templates.is_default. The override
# restores the legacy shares and ordering even after catalogue activation.
LEGACY_ONBOARDING_LAYOUT = (
    ("an_uong", 25, 10),
    ("di_lai", 10, 20),
    ("hoa_don", 30, 30),
    ("giai_tri", 10, 40),
    ("du_lich", 5, 50),
    ("du_phong", 15, 60),
    (DEFAULT_OBLIGATION_JAR, 5, 70),
)


def onboarding_override() -> list[dict[str, str | int]] | None:
    layout = getenv("YOFINA_ONBOARDING_JAR_LAYOUT", "catalogue")
    if layout == "catalogue":
        return None
    if layout != "legacy":
        raise ValueError("YOFINA_ONBOARDING_JAR_LAYOUT must be 'catalogue' or 'legacy'")
    return [
        {"code": code, "split_percent": split, "sort_order": order}
        for code, split, order in LEGACY_ONBOARDING_LAYOUT
    ]


@dataclass(frozen=True)
class DemoJar:
    """One jar of the demo layout. Its balance, split share, history and goal come from the persona jars that
    `personas.six_jars.JAR_ALIASES` folds into it, or, for a jar no persona jar folds into, from the persona spec block
    `demo_jars` (Chi hằng ngày) or nothing (Đầu tư: 0 ₫, 0%); the layout only fixes code, label, kind and purpose. A goal jar
    needs an amount and a date, so it is left out for a persona without a source jar that has a goal; it is a jar the user
    added for that goal, so it shows the name of the source jar (Du lịch), not the layout label."""

    code: str
    name: str
    color_key: str
    icon_key: str
    kind: str
    sort_order: int
    purpose: str | None = None


# Demo wallet after reset (issue #39, changed 26/11 morning): the three onboarding defaults first (Chi hằng ngày, Nghĩa vụ, Dự
# phòng), then the jars the user added: Ăn uống, Đi lại, Giải trí (behaviour signals are per jar code), Mục tiêu and Đầu tư. Chi
# hằng ngày keeps the small everyday spending that no added jar takes (spec `demo_jars`); colour and icon as `jar_templates`.
DEMO_LAYOUT = (
    DemoJar(DEFAULT_SPENDING_JAR, "Chi hằng ngày", "violet", "utensils", "spending", 10),
    DemoJar(DEFAULT_OBLIGATION_JAR, "Nghĩa vụ", "slate", "wallet", "obligation", 20),
    DemoJar("du_phong", "Dự phòng", "blue", "shield", "saving", 30, purpose="buffer"),
    DemoJar("an_uong", "Ăn uống", "violet", "utensils", "spending", 40),
    DemoJar("di_lai", "Đi lại", "sky", "bus", "spending", 50),
    DemoJar("giai_tri", "Giải trí", "orchid", "gamepad", "spending", 60),
    DemoJar(DEFAULT_GOAL_JAR, "Mục tiêu", "teal", "target", "saving", 70, purpose="goal"),
    DemoJar("dau_tu", "Đầu tư", "brown", "landmark", "saving", 80, purpose="long_term"),
)
