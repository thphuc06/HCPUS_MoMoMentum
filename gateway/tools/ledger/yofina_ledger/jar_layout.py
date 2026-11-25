"""Jar layouts for onboarding and demo reset."""

from dataclasses import dataclass
from os import getenv

from yofina_core.wallet import DEFAULT_GOAL_JAR, DEFAULT_OBLIGATION_JAR

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
    """One jar of the demo layout. Its balance, split share, history and goal come from the persona jars listed in
    `personas.six_jars.JAR_ALIASES` (none for a new jar); the layout only fixes code, label, kind and purpose. A goal jar needs an amount and a date, so it
    is left out for a persona without a source jar that has a goal."""

    code: str
    name: str
    color_key: str
    icon_key: str
    kind: str
    sort_order: int
    purpose: str | None = None


# Demo wallet after reset (issue #39): the two onboarding defaults plus the jars the user added after splitting
# Chi h?ng ng?y into ?n u?ng, ?i l?i, Gi?i tr? (behaviour signals are per jar code). There is no `chi_hang_ngay`.
# Order follows the persona wallets (Ngh?a v? takes the place of H?a ??n).
DEMO_LAYOUT = (
    DemoJar("an_uong", "?n u?ng", "violet", "utensils", "spending", 10),
    DemoJar("di_lai", "?i l?i", "sky", "bus", "spending", 20),
    DemoJar(DEFAULT_OBLIGATION_JAR, "Ngh?a v?", "slate", "wallet", "obligation", 30),
    DemoJar("giai_tri", "Gi?i tr?", "orchid", "gamepad", "spending", 40),
    DemoJar(DEFAULT_GOAL_JAR, "M?c ti?u", "teal", "target", "saving", 50, purpose="goal"),
    DemoJar("du_phong", "D? ph?ng", "blue", "shield", "saving", 60, purpose="buffer"),
    DemoJar("dau_tu", "??u t?", "brown", "landmark", "saving", 70, purpose="long_term"),
)
