"""Jar layouts for onboarding and demo reset."""

from dataclasses import dataclass
from datetime import date
from os import getenv

from yofina_core.wallet import DEFAULT_GOAL_JAR, DEFAULT_OBLIGATION_JAR, DEFAULT_SPENDING_JAR

DEMO_LAYOUT_ID = "six_jars"  # Existing suffix of the Minh roadmap seed filename.

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
    code: str
    name: str
    color_key: str
    icon_key: str
    kind: str
    split_percent: int
    sort_order: int
    purpose: str | None = None
    goal_vnd: int | None = None
    goal_date: date | None = None


DEMO_LAYOUT = (
    DemoJar(DEFAULT_SPENDING_JAR, "Chi hằng ngày", "violet", "utensils", "spending", 45, 10),
    DemoJar(DEFAULT_OBLIGATION_JAR, "Nghĩa vụ", "slate", "wallet", "obligation", 35, 20),
    DemoJar("du_phong", "Dự phòng", "blue", "shield", "saving", 15, 30, purpose="buffer"),
    DemoJar(
        DEFAULT_GOAL_JAR,
        "Mục tiêu",
        "orchid",
        "target",
        "saving",
        5,
        40,
        purpose="goal",
        goal_vnd=6_000_000,
        goal_date=date(2027, 4, 1),
    ),
)
