"""Màu và biểu tượng của hũ Chi hằng ngày (issue #39, 26/11): trên ví demo hũ này đứng cạnh Ăn uống nên không được trùng màu và biểu
tượng với Ăn uống, và biểu tượng không trùng hũ nào khác (Nghĩa vụ dùng ví). Kiểm tĩnh, nhất quán giữa bộ hũ demo (`jar_layout.py`), seed
danh mục (`db/seed/jar_templates.sql`, ghi đè hàng mà migration 0059 đã tạo) và bộ khóa frontend (`frontend/src/components/jarTheme.ts`:
khóa lạ rơi về màu, biểu tượng trung tính)."""

from __future__ import annotations

import re

from conftest import REPO

from yofina_core.wallet import DEFAULT_SPENDING_JAR
from yofina_ledger.jar_layout import DEMO_LAYOUT

THEME = (REPO / "frontend" / "src" / "components" / "jarTheme.ts").read_text(encoding="utf-8")
SEED = (REPO / "db" / "seed" / "jar_templates.sql").read_text(encoding="utf-8")
SQL_0059 = (REPO / "db" / "migrations" / "0059_activate_onboarding_jar_layout.sql").read_text(encoding="utf-8")


def _keys(const: str) -> set[str]:
    body = THEME.split(f"const {const}", 1)[1].split("}", 1)[0]
    return set(re.findall(r"^\s+(\w+):", body, re.M))


def _template_rows(sql: str) -> dict[str, tuple[str, str]]:
    """(color_key, icon_key) theo mã hũ của các bộ giá trị INSERT jar_templates."""
    return {code: (color, icon) for code, color, icon in re.findall(r"\('(\w+)',\s*'[^']*',\s*'(\w+)',\s*'(\w+)'", sql)}


LAYOUT = {jar.code: (jar.color_key, jar.icon_key) for jar in DEMO_LAYOUT}


def test_moi_hu_demo_dung_khoa_mau_va_bieu_tuong_frontend_co():
    colors, icons = _keys("COLOR_VAR"), _keys("ICONS")
    for code, (color, icon) in LAYOUT.items():
        assert color in colors and icon in icons, code


def test_chi_hang_ngay_khac_an_uong_va_bieu_tuong_rieng():
    daily = LAYOUT[DEFAULT_SPENDING_JAR]
    assert daily[0] != LAYOUT["an_uong"][0] and daily[1] != LAYOUT["an_uong"][1]
    assert [code for code, (_, icon) in LAYOUT.items() if icon == daily[1]] == [DEFAULT_SPENDING_JAR]


def test_seed_ghi_de_mau_cua_hang_danh_muc_bang_mau_cua_bo_hu_demo():
    # migration 0059 (đã chạy, không sửa) tạo hàng Chi hằng ngày với màu, biểu tượng của Ăn uống; seed chạy sau migration ghi đè đúng
    # hai cột đó (không tạo hàng, không đụng is_default, tỷ lệ, thứ tự: seed không bật bộ hũ)
    assert _template_rows(SQL_0059)[DEFAULT_SPENDING_JAR] == _template_rows(SQL_0059)["an_uong"]
    update = re.search(
        r"UPDATE jar_templates SET color_key = '(\w+)', icon_key = '(\w+)' WHERE code = '(\w+)';", SEED
    )
    assert update is not None and update.group(3) == DEFAULT_SPENDING_JAR
    assert (update.group(1), update.group(2)) == LAYOUT[DEFAULT_SPENDING_JAR]
    assert DEFAULT_SPENDING_JAR not in _template_rows(SEED)  # hàng do migration 0059 tạo
